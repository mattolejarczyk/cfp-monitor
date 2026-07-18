"""Streamlit UI for the CFP monitor.

Two tabs:
- Run & Crawl:   paste conference URLs, crawl, view results — and persist them to the
                 source-of-truth DB.
- Review & Verify: the human-in-the-loop layer — edit deadline/status, mark rows
                 verified (verified values are preserved against future crawls), and
                 see per-conference change history.

Run:  streamlit run app.py
"""
from __future__ import annotations

import asyncio
import json

import streamlit as st
import pandas as pd

from src.cfp_monitor import run_urls, Settings
from src.cfp_monitor.models import Fact
from src.cfp_monitor.storage import Store, normalize_key
from src.cfp_monitor.quality_gate import classify_result
from src.cfp_monitor.scoring import normalize_url
from src.cfp_monitor.customer_format import (
    CUSTOMER_HEADERS, to_customer_rows, to_customer_csv_text, _STATUS_MAP,
)

import os
import time

from src.cfp_monitor.uploads import (
    URL_RE,
    normalize_urls_and_contexts,
    uploaded_urls_and_contexts,
)

DB_PATH = "cfp_monitor.db"   # source of truth


def _fmt_dur(seconds: float) -> str:
    """Compact human duration: '45s', '4m 10s', '1h 3m'."""
    s = max(0, int(round(seconds)))
    if s < 60:
        return f"{s}s"
    if s < 3600:
        return f"{s // 60}m {s % 60}s"
    return f"{s // 3600}h {(s % 3600) // 60}m"

st.set_page_config(page_title="CFP Monitor", page_icon="🎤", layout="wide")
st.title("🎤 Conference CFP Monitor")

# License status banner (only meaningful for licensed customer builds; silent in dev/direct mode).
from src.cfp_monitor.licensing import check_license
_LIC = check_license(Settings())
_LICENSE_BLOCKS = _LIC["mode"] == "proxy" and _LIC["ok"] is False
if _LIC["mode"] == "proxy":
    if _LIC["ok"] is True:
        st.caption(f"🔑 License active — {_LIC['info'].get('plan') or 'subscription'}.")
    elif _LIC["ok"] is False:
        st.error(f"🔒 License inactive: {_LIC['detail']}  ·  Please contact support to restore service.")
    else:
        st.warning(f"🔑 {_LIC['detail']}")

_STATUS_ICON = {"open": "🟢", "upcoming": "🟡", "unclear": "⚪", "closed": "🔴", "none": "⚫"}

# Review-sheet editing: map each customer column to how it persists.
#  _PLAIN_COLS   -> human-owned column, saved directly (store.set_fields)
#  _TRACKED_COLS -> crawl-produced field, saved with correction-precedence (store.correct)
#  STATUS is tracked but shown with the customer wording, so it reverse-maps on save.
_PLAIN_COLS = {"CONFERENCE": "name", "PRIORITY": "priority", "STATUS DETAILS": "status_details",
               "COORDINATOR EMAIL": "coordinator_email", "OVERVIEW": "overview", "NOTES": "notes"}
_TRACKED_COLS = {"LOCATION": "location", "START DATES": "conference_dates",
                 "SUBMISSION DEADLINE": "cfp_close_date", "SUBMISSION URL": "submission_url",
                 "CATEGORIES": "categories"}
_STATUS_INV = {v: k for k, v in _STATUS_MAP.items()}          # "Open" -> "open", "Needs Review" -> "unclear"
_STATUS_CHOICES = [""] + list(_STATUS_MAP.values())
_READONLY_COLS = ["CONFERENCE URL", "LATEST UPDATE"]           # identity + system timestamp


def _fact_line(label: str, fact: Fact) -> str:
    if not fact.value:
        return f"**{label}:** _unknown_"
    return f"**{label}:** {fact.value}  ·  _{fact.confidence.value}_"


tab_run, tab_review = st.tabs(["▶️  Run & Crawl", "✅  Review & Verify"])

# ─────────────────────────────────────────────────────────────── Run & Crawl ──
with tab_run:
    with st.sidebar:
        st.header("Settings")
        max_pages = st.slider("Max pages / site", 3, 40, 12)
        max_depth = st.slider("Max crawl depth", 1, 4, 2)
        max_extract = st.slider("Max pages to LLM-extract", 2, 15, 8)
        provider = st.text_input("LLM provider (LiteLLM string)", "openrouter/deepseek/deepseek-chat")
        cdp_url = st.text_input("CDP url (real Chrome — auto-set by the launcher)", os.getenv("CFP_CDP_URL", ""),
                                help="Used automatically for hard anti-bot sites (e.g. Reuters) when the CDP Chrome is running. The desktop launcher sets this for you.")
        st.caption("Set OPENROUTER_API_KEY in your environment / .env before running.")

    urls_text = st.text_area(
        "Paste conference URLs (any text — links are auto-extracted)",
        placeholder="https://conf-a.example.com\nhttps://conf-b.example.org",
        height=140,
    )
    uploaded = st.file_uploader("…or upload a list (.txt / .csv / .xlsx)", type=["txt", "csv", "xlsx"])

    raw = URL_RE.findall(urls_text or "")
    contexts: list[dict | None] = [None] * len(raw)
    if uploaded:
        uploaded_urls, uploaded_contexts = uploaded_urls_and_contexts(uploaded.name, uploaded.read())
        raw += uploaded_urls
        contexts += uploaded_contexts
    urls, contexts = normalize_urls_and_contexts(raw, contexts)
    st.caption(f"**{len(urls)} unique URL(s)** after normalize + dedupe.")
    if any(contexts):
        st.caption("Spreadsheet row context is active for directory/organization-page resolution.")
    if urls:
        with st.expander("Preview normalized URLs"):
            st.write(urls)

    if st.button("Run", type="primary", disabled=not urls or _LICENSE_BLOCKS):
        settings = Settings()
        settings.max_pages, settings.max_depth, settings.max_extract_pages = max_pages, max_depth, max_extract
        settings.llm_provider = provider
        if cdp_url.strip():
            settings.cdp_url = cdp_url.strip()
        try:
            settings.require_llm_key()
        except Exception as e:
            st.error(str(e)); st.stop()

        # Live progress: "Crawling 15 of 51: <site>… · ~4m left". run_urls calls this back
        # once before each conference (and once at the end). Sites are crawled one at a time,
        # so a bar that sits on the same number is a sign that site is slow/stuck — each is
        # capped at the per-site timeout, then it advances on its own.
        prog = st.progress(0.0, text=f"Starting… 0 of {len(urls)}")
        t_start = time.monotonic()

        def _on_progress(done: int, total: int, current: str | None) -> None:
            if not total:
                return
            if current is None:
                prog.progress(1.0, text=f"Done — {total} of {total} crawled")
                return
            eta = ""
            if done:
                per = (time.monotonic() - t_start) / done
                eta = f" · ~{_fmt_dur(per * (total - done))} left"
            site = current.split("://", 1)[-1][:52]
            prog.progress(done / total, text=f"Crawling {done + 1} of {total}: {site}…{eta}")

        results = asyncio.run(run_urls(urls, settings, contexts=contexts, on_progress=_on_progress))
        prog.empty()

        # Persist to the source-of-truth DB (gate quality + record the run).
        store = Store(DB_PATH)
        run_id = store.start_run()
        counts = {"url_count": len(results)}
        for r in results:
            q = classify_result(r).verdict
            counts[q.value] = counts.get(q.value, 0) + 1
            store.upsert(r, q, run_id=run_id)
        store.finish_run(run_id, counts)
        store.close()

        # Reload the just-crawled rows in the customer 15-column format (URL included, so every
        # row ties back to its source). Stash everything in session_state so the results survive
        # a rerun — clicking a download button reruns the script, and we don't want the results
        # (or the page) to disappear when that happens.
        keys = {normalize_key(r.canonical_url or r.start_url) for r in results}
        rstore = Store(DB_PATH)
        run_rows = [d for d in rstore.export_dicts() if d["key"] in keys]
        rstore.close()
        st.session_state["last_run"] = {
            "results": results,
            "run_rows": run_rows,
            "cust": to_customer_rows(run_rows),
            "counts": counts,
        }

    # ── Results (rendered from session_state, OUTSIDE the Run button block) ────────
    # Because this reads session_state rather than the transient Run-button value, downloads
    # are non-destructive: the table, buttons, and detail all stay put after a download. This
    # tab is read-only — to change any value, use the Review & Verify tab.
    lr = st.session_state.get("last_run")
    if lr:
        results, run_rows, counts = lr["results"], lr["run_rows"], lr["counts"]
        head, clear = st.columns([5, 1])
        head.success(f"Done — analyzed {len(results)} conference(s) · saved to {DB_PATH} · "
                     f"{ {k: v for k, v in counts.items() if k != 'url_count'} }")
        if clear.button("Clear results", width="stretch"):
            del st.session_state["last_run"]
            st.rerun()

        st.subheader("Results — customer format")
        st.dataframe(pd.DataFrame(lr["cust"], columns=CUSTOMER_HEADERS),
                     width="stretch", hide_index=True)

        st.markdown("**Download** — these save a file only; they don't change your data "
                    "or this page. Editing lives in the **Review & Verify** tab.")
        c_csv, c_json = st.columns(2)
        c_csv.download_button("⬇️ Customer CSV (15-col)", data=to_customer_csv_text(run_rows),
                              file_name="cfp_customer.csv", mime="text/csv", width="stretch",
                              key="dl_run_csv")
        c_json.download_button("⬇️ Raw JSON", width="stretch", key="dl_run_json",
                               data=json.dumps([r.model_dump(mode="json") for r in results], indent=2, ensure_ascii=False),
                               file_name="cfp_results.json", mime="application/json")

        st.subheader("Per-conference detail + evidence")
        for r in results:
            icon = _STATUS_ICON.get(r.cfp_status.value, "⚪")
            with st.expander(f"{icon} {r.name.value or r.start_url} — CFP: {r.cfp_status.value}", expanded=False):
                if r.error:
                    st.error(f"Error: {r.error}")
                if r.reason:
                    st.info(f"**Why:** {r.reason}")
                c1, c2 = st.columns(2)
                with c1:
                    st.markdown(_fact_line("Conference", r.name))
                    st.markdown(_fact_line("Dates", r.conference_dates))
                    st.markdown(_fact_line("Location", r.location))
                with c2:
                    st.markdown(_fact_line("CFP deadline", r.cfp_close_date))
                    st.markdown(_fact_line("Submit at", r.submission_url))
                    if r.submission_platform:
                        st.markdown(f"**Platform:** {r.submission_platform}")
                st.caption(f"URL: {r.start_url} · pages crawled: {r.pages_crawled}")
                if r.evidence:
                    st.markdown("**Evidence**")
                    for e in r.evidence:
                        st.markdown(f"- **{e.field}** — [{e.source_url}]({e.source_url})\n\n  > {e.snippet}")

# ────────────────────────────────────────────────────────── Review & Verify ──
with tab_review:
    st.header("Review & Verify — source of truth")
    st.caption("Edit deadline/status and tick **Verified** to lock a human-checked value. "
               "Verified values are preserved against future crawls (correction-precedence).")
    store = Store(DB_PATH)
    records = store.all_records()

    if not records:
        st.info("No records yet — run a crawl in the first tab.")
    else:
        # The full customer 15-column sheet, editable in place. Edits to crawl-produced fields
        # are protected from future crawls (correction-precedence); human-owned columns
        # (PRIORITY, NOTES, ...) save directly. CONFERENCE URL + LATEST UPDATE are read-only.
        cust_rows = to_customer_rows(store.export_dicts())
        keys = [r["key"] for r in records]
        df = pd.DataFrame(cust_rows, columns=CUSTOMER_HEADERS)
        df.insert(0, "_key", keys)
        # SUBMISSION DATE VERIFIED as a real checkbox instead of Yes/Needs Verification text.
        df["SUBMISSION DATE VERIFIED"] = [r["verification_status"] == "verified" for r in records]

        edited = st.data_editor(
            df, use_container_width=True, hide_index=True, height=520,
            disabled=["_key", *_READONLY_COLS],
            column_config={
                "_key": None,
                "SUBMISSION DATE VERIFIED": st.column_config.CheckboxColumn("SUBMISSION DATE VERIFIED"),
                "STATUS": st.column_config.SelectboxColumn("STATUS", options=_STATUS_CHOICES),
            },
            key="review_editor",
        )

        st.caption("Editing a crawl field (status, deadline, dates, location, categories, submission URL) "
                   "locks that value against future crawls. Tick **SUBMISSION DATE VERIFIED** to mark a "
                   "row human-checked.")

        if st.button("💾 Save changes", type="primary"):
            orig_by_key = {r["_key"]: r for r in df.to_dict("records")}
            n_rows = 0
            for row in edited.to_dict("records"):
                k = row["_key"]
                before = orig_by_key.get(k, {})
                plain, tracked = {}, {}
                for col, dbcol in _PLAIN_COLS.items():
                    if (row.get(col) or "") != (before.get(col) or ""):
                        plain[dbcol] = row.get(col) or None
                for col, dbcol in _TRACKED_COLS.items():
                    if (row.get(col) or "") != (before.get(col) or ""):
                        tracked[dbcol] = row.get(col) or None
                if (row.get("STATUS") or "") != (before.get("STATUS") or ""):
                    tracked["cfp_status"] = _STATUS_INV.get(row.get("STATUS") or "", row.get("STATUS")) or None
                touched = False
                if plain:
                    store.set_fields(k, plain); touched = True
                if tracked:
                    store.correct(k, tracked); touched = True
                if bool(row.get("SUBMISSION DATE VERIFIED")) != bool(before.get("SUBMISSION DATE VERIFIED")):
                    store.set_verified(k, bool(row.get("SUBMISSION DATE VERIFIED"))); touched = True
                n_rows += 1 if touched else 0
            st.success(f"Saved changes to {n_rows} row(s).")
            st.rerun()

        st.download_button("⬇️ Download full sheet (customer CSV)",
                           data=to_customer_csv_text(store.export_dicts()),
                           file_name="cfp_customer_full.csv", mime="text/csv")

        st.divider()
        names = {r["name"] or r["key"]: r["key"] for r in records}
        pick = st.selectbox("Change history for:", ["—"] + list(names))
        if pick != "—":
            changes = store.changes_for(names[pick])
            if changes:
                st.dataframe(pd.DataFrame(changes)[["detected_at", "field", "old_value", "new_value", "change_type"]],
                             use_container_width=True, hide_index=True)
            else:
                st.caption("No recorded changes yet.")
    store.close()
