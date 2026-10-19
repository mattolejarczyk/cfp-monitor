"""Ask the cheap model the RIGHT question about the collected pages: 'how does a company get a speaking slot here, and must it pay?' (2026-10-19, read-only; writes only under --out-dir).

    python experiments/sponsor_reader/judge.py <collect-dir> --out-dir <dir> [--model openrouter/deepseek/deepseek-chat] [--prompt v2] [--per-page 6000]

WHY. The old question was a one-page sentence hunt for 'speaking requires sponsorship', and upstream's own question counted any event that sells sponsorship as 'Yes' (211 of 220 rows). The practical question
is about the ROUTE to a speaking slot, and it needs several pages at once (is there an open call anyone can submit to? does the sponsorship page sell or promise speaking slots? does any page say a company MUST
sponsor to speak?). This gives the model all the pages of one event together, labelled by kind, and asks for four separate answers, each with a word-for-word quote. CODE then checks every quote is on the
pages and derives the route; the model never decides the final label.
Routes (derived by code):  MUST_SPONSOR (a verified quote says companies must sponsor/exhibit/pay to speak or speaking is reserved for sponsors)
                           OPEN_CALL (a public call exists, and nothing says speaking is for sale)
                           OPEN_CALL_AND_PAID_SLOTS (a public call exists, and speaking slots are also part of sponsor packages)
                           PAID_SLOTS_NO_CALL_SEEN (speaking slots come with sponsor packages and no open call was found: NOT proof that none exists)
                           INVITE_ONLY (a verified quote says speakers are invited or chosen by the organizer, and nothing says speaking is for sale)
                           UNCLEAR"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

SYSTEM_V3 = """You help a company that wants to SPEAK at a conference. You are given the text of several pages from the conference's own website, each labelled with its kind (home, call = a call-for-speakers page,
sponsor = a sponsorship or exhibitor page, cited-sponsor = the sponsorship page a researcher cited). Use ONLY this text. The edition we care about is stated in the first line (CONFERENCE and EDITION). A call, deadline or page that is clearly for a DIFFERENT year or edition (for example "Due July 30, 2021", or a page about the 2026 call when the edition is 2027) does not count: treat that as "unclear". Answer four questions. For each, quote the exact words (copy them exactly; never reword)
or leave the quote empty.

1. open_call: "yes" if the pages describe a public call for speakers, papers, abstracts or proposals that people can submit to (a form, a link, instructions or a deadline), whether or not the person is a vendor;
   "no" ONLY if a page says speakers are by invitation only, chosen by the organizer or its analysts, or that there is no public call (quote that sentence); otherwise "unclear".
2. paid_slots: "yes" if the pages say speaking, presenting, a keynote, a panel, a session or a speaking slot is INCLUDED in, or can be BOUGHT as part of, a sponsorship or exhibitor package; "no" if they say it is not; otherwise "unclear".
   A package that only lists a logo, a booth, passes or branding is "no".
3. must_pay: "yes" ONLY if a page says that companies or vendors MUST sponsor, exhibit or pay to speak, or that speaking is reserved for sponsors; "no" if a page says sponsoring does not buy or guarantee a speaking slot, or that speakers are chosen
   independently of sponsorship; otherwise "unclear".
4. summary: one plain sentence saying how a company gets a speaking slot here.

Return ONLY this JSON:
{"open_call": "yes|no|unclear", "open_call_quote": "", "paid_slots": "yes|no|unclear", "paid_slots_quote": "", "must_pay": "yes|no|unclear", "must_pay_quote": "", "summary": ""}"""


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").replace(" ", " ").replace("Â", " ")).strip().lower()


def quote_on_pages(quote: str, pages: list[dict]) -> bool:
    q = norm(quote)
    return bool(q) and any(q in norm(p["text"]) for p in pages)


# A quote must SAY what the answer claims, in words the code can check (a model that over-reads a weak sentence is caught here, not trusted).
SAYS = {
    ("open_call", "yes"): re.compile(r"call for|call-for|submit|submission|propos|abstract|apply|application|nominat|cfp|become a speaker|propose a speaker|register your interest|speaker form|interested in (speaking|presenting)|e-?mail .{0,60}(speaker|present|synopsis)", re.I),
    ("open_call", "no"): re.compile(r"invit|curated|selected by the|chosen by|by the (organi[sz]|program|advisory|analyst)|analyst|no (public )?call|not (accept|open)", re.I),
    ("paid_slots", "yes"): re.compile(r"speak|present|keynote|panel|session|stage|slot|moderat|fireside|spotlight", re.I),
    ("must_pay", "yes"): re.compile(r"must|required|requires|only|reserved|exclusive|solely|need to", re.I),
}


def route(ans: dict, pages: list[dict]) -> dict:
    for (k, v), rx in SAYS.items():
        if ans.get(k) == v and not rx.search(ans.get(k + "_quote", "") or ""):
            ans = {**ans, k: "unclear"}                                       # the quote does not say it: back to unclear
    ok = {k: quote_on_pages(ans.get(k + "_quote", ""), pages) for k in ("open_call", "paid_slots", "must_pay")}
    oc = ans.get("open_call") if (ans.get("open_call") not in ("yes", "no") or ok["open_call"]) else "unclear"
    ps = ans.get("paid_slots") if (ans.get("paid_slots") != "yes" or ok["paid_slots"]) else "unclear"
    mp = ans.get("must_pay") if (ans.get("must_pay") != "yes" or ok["must_pay"]) else "unclear"
    if mp == "yes":
        r = "MUST_SPONSOR"
    elif oc == "no" and ps != "yes":
        r = "INVITE_ONLY"
    elif oc == "yes" and ps == "yes":
        r = "OPEN_CALL_AND_PAID_SLOTS"
    elif oc == "yes":
        r = "OPEN_CALL"
    elif ps == "yes":
        r = "PAID_SLOTS_NO_CALL_SEEN"
    else:
        r = "UNCLEAR"
    return {"route": r, "open_call": oc, "paid_slots": ps, "must_pay": mp, "unproven_quotes": [k for k, v in ok.items() if ans.get(k) == "yes" and not v]}


def build_user(rec: dict, per_page: int) -> str:
    parts = [f"CONFERENCE: {rec['name']}   EDITION: {rec.get('edition') or 'not stated'}"]
    for p in rec["pages"]:
        if p["text"].strip():
            parts.append(f"\n=== PAGE kind={p['kind']} url={p['url']} ===\n{re.sub(chr(10) + '{3,}', chr(10) * 2, p['text'])[:per_page]}")
    parts.append("\nReturn ONLY the JSON object.")
    return "\n".join(parts)


async def ask(system: str, user: str, model: str, settings):
    import litellm
    kwargs = dict(model=model, messages=[{"role": "system", "content": system}, {"role": "user", "content": user}], api_key=settings.provider_key(), temperature=0.0, max_tokens=700)
    try:
        resp = await litellm.acompletion(**kwargs, response_format={"type": "json_object"})
    except Exception:
        resp = await litellm.acompletion(**kwargs)
    raw = resp.choices[0].message.content or ""
    u = getattr(resp, "usage", None)
    m = re.search(r"\{.*\}", raw, re.S)
    data = json.loads(m.group(0)) if m else {}
    return data, (getattr(u, "prompt_tokens", 0) or 0, getattr(u, "completion_tokens", 0) or 0)


async def main(a):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    from src.cfp_monitor.config import Settings
    s = Settings()
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    files = sorted((Path(a.collect_dir) / "pages").glob("*.json"))
    import sqlite3
    con = sqlite3.connect("file:C:/Users/matts/AppData/Local/CFP-Monitor/cfp_monitor.db?mode=ro", uri=True)
    editions = {r[0]: str(r[1] or "") for r in con.execute("select event_id, edition from grounding_facts")}
    con.close()
    sem, results = asyncio.Semaphore(4), {}

    async def work(f):
        rec = json.loads(f.read_text(encoding="utf-8"))
        if not any(p["text"].strip() for p in rec["pages"]):
            results[f.stem] = {"name": rec["name"], "ours": rec["ours"], "route": "NO_PAGES"}
            return
        async with sem:
            try:
                rec["edition"] = editions.get(rec["event_id"], "")
                ans, toks = await ask(SYSTEM_V3, build_user(rec, a.per_page), a.model, s)
            except Exception as e:                                     # noqa: BLE001
                results[f.stem] = {"name": rec["name"], "ours": rec["ours"], "route": "ERROR", "error": f"{type(e).__name__}: {e}"[:160]}
                return
        results[f.stem] = {"name": rec["name"], "ours": rec["ours"], **route(ans, rec["pages"]), "answer": ans, "tokens": toks}

    await asyncio.gather(*(work(f) for f in files))
    (out / f"judged_{a.tag}.json").write_text(json.dumps(dict(sorted(results.items())), ensure_ascii=False, indent=1), encoding="utf-8")
    from collections import Counter
    print(a.model, dict(Counter(r["route"] for r in results.values())), "tokens in/out:", sum(r.get("tokens", (0, 0))[0] for r in results.values()), sum(r.get("tokens", (0, 0))[1] for r in results.values()))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("collect_dir")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--model", default="openrouter/deepseek/deepseek-chat")
    ap.add_argument("--tag", default="deepseek")
    ap.add_argument("--per-page", type=int, default=6000)
    asyncio.run(main(ap.parse_args()))
