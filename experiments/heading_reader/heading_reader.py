"""Heading-aware reader, Phase 1 runner (design: docs/design/heading-aware-reader-design.md section 6). Deterministic, no model, no network.

   python heading_reader.py --labelled   the 15 labelled pages (experiments/sentence_picking/labels.json, locked)
   python heading_reader.py --holdout    the 10 holdout pages (holdout_labels.json, locked before the reader was run)

Reader = units / purpose / dated from experiments/purpose_audit/purpose_audit.py, unchanged. A unit date is ACCEPTED as a submission deadline when its purpose is SUB,
it is the closing date of its unit (single date, or the END of a range) and its year is stated (explicit, '(26)', shared range year) or taken from the heading path.
A year taken from the nearest earlier text ('nearby') or not found ('needs-year') is reported but never accepted. Accepted evidence = heading + unit line, both cut from the page.
"""
import hashlib, json, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "experiments" / "purpose_audit"))
import purpose_audit as pa                                              # noqa: E402
sp = pa.sp

ACCEPT_YEAR = {"explicit", "two-digit", "range", "heading"}


def read_page(text, url=""):
    pa.set_page_context(url)
    """[{date, year_source, role, purpose, why, heading, unit, accepted}] for every date in every unit of the page."""
    out = []
    for u in pa.units(text):
        for k, d in enumerate(u["dates"]):
            iso_, ysrc = pa.dated(text, u, k)
            p, why = pa.purpose(u, k)
            role = "single" if len(u["dates"]) == 1 else ("end" if k == len(u["dates"]) - 1 else "start")
            acc = bool(iso_) and p == "SUB" and role in ("end", "single") and ysrc in ACCEPT_YEAR
            out.append({"date": iso_, "year_source": ysrc, "role": role, "purpose": p, "why": why, "heading": u["heading"], "unit": u["line"], "accepted": acc})
    return out


def run(pages, labels, tag):
    tp = wrong = unl = rec = tot = 0
    detail = {"wrong": [], "unlabelled": [], "missed": []}
    per_page = {}
    for url, lab in labels.items():
        text = (pages.get(url) or {}).get("text") or ""
        res = read_page(text, url) if text else []
        acc = {}
        for r in res:
            if r["accepted"]:
                acc.setdefault(r["date"], r)
        sub = {l["date"] for l in lab["labels"] if l["class"] == "SUB"}
        non = {l["date"]: l["class"] for l in lab["labels"] if l["class"] not in ("SUB", "SUB_RECURRING")}
        for d, r in acc.items():
            if d in sub:
                tp += 1
            elif d in non:
                wrong += 1; detail["wrong"].append((url[-45:], d, non[d], r["unit"][:60]))
            else:
                unl += 1; detail["unlabelled"].append((url[-45:], d, r["unit"][:60]))
        for d in sub - set(acc):
            detail["missed"].append((url[-45:], d))
        rec += len(sub & set(acc)); tot += len(sub)
        per_page[url[-45:]] = {"units_with_dates": len(res), "accepted": sorted(acc), "sub_labels": sorted(sub)}
    n = tp + wrong + unl
    summary = {"set": tag, "pages": len(labels), "accepted": n, "correct": tp, "wrong_purpose": wrong, "unlabelled": unl,
               "precision_strict": round(tp / n, 3) if n else None, "recall": f"{rec}/{tot}"}
    (HERE / f"scored_{tag}.json").write_text(json.dumps({"summary": summary, "detail": detail, "per_page": per_page}, indent=1), encoding="utf-8")
    print(json.dumps(summary)); print(json.dumps(detail, indent=1)[:3000])
    return summary


if __name__ == "__main__":
    if "--labelled" in sys.argv:
        Lp = ROOT / "experiments" / "sentence_picking"
        assert hashlib.sha256((Lp / "labels.json").read_bytes()).hexdigest() == (Lp / "labels.sha256").read_text().split()[0], "labelled key changed"
        L = json.loads((Lp / "labels.json").read_text(encoding="utf-8"))["pages"]
        run(sp.PAGES, L, "labelled")
    if "--holdout" in sys.argv:
        assert hashlib.sha256((HERE / "holdout_labels.json").read_bytes()).hexdigest() == (HERE / "holdout_labels.sha256").read_text().split()[0], "holdout key changed"
        L = json.loads((HERE / "holdout_labels.json").read_text(encoding="utf-8"))["pages"]
        run(json.loads((HERE / "holdout_pages.json").read_text(encoding="utf-8")), L, "holdout")
