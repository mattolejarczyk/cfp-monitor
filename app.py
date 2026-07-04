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
from src.cfp_monitor.storage import Store
from src.cfp_monitor.quality_gate import classify_result
from src.cfp_monitor.scoring import normalize_url

import io
import re
import zipfile

DB_PATH = "cfp_monitor.db"   # source of truth
_URL_RE = re.compile(r'https?://[^\s"\'<>)\]]+')


def _urls_from_upload(name: str, data: bytes) -> list[str]:
    """Extract every http(s) URL from an uploaded .txt/.csv/.xlsx (dependency-free)."""
    if name.lower().endswith(".xlsx"):
        try:
            z = zipfile.ZipFile(io.BytesIO(data))
            text = ""
            for n in z.namelist():
                if n == "xl/sharedStrings.xml" or (n.startswith("xl/worksheets/") and n.endswith(".xml")):
                    text += z.read(n).decode("utf-8", "ignore")
            return _URL_RE.findall(text)
        except Exception:
            return []
    return _URL_RE.findall(data.decode("utf-8", "ignore"))


def _normalize(raw: list[str]) -> list[str]:
    """Strip, keep only http(s), dedupe by normalized form (order-preserving)."""
    seen, out = set(), []
    for u in raw:
        u = (u or "").strip().rstrip(",;")
        if not u.lower().startswith("http"):
            continue
        key = normalize_url(u)
        if key in seen:
            continue
        seen.add(key)
        out.append(u)
    return out

st.set_page_config(page_title="CFP Monitor", page_icon="🎤", layout="wide")
st.title("🎤 Conference CFP Monitor")

_STATUS_ICON = {"open": "🟢", "upcoming": "🟡", "unclear": "⚪", "closed": "🔴", "none": "⚫"}


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
        cdp_url = st.text_input("CDP url (real Chrome, optional)", "",
                                help="e.g. http://localhost:9222 — beats hard anti-bot sites. Launch scripts/launch_chrome_cdp.bat first.")
        st.caption("Set OPENROUTER_API_KEY in your environment / .env before running.")

    urls_text = st.text_area(
        "Paste conference URLs (any text — links are auto-extracted)",
        placeholder="https://conf-a.example.com\nhttps://conf-b.example.org",
        height=140,
    )
    uploaded = st.file_uploader("…or upload a list (.txt / .csv / .xlsx)", type=["txt", "csv", "xlsx"])

    raw = _URL_RE.findall(urls_text or "")
    if uploaded is not None:
        raw += _urls_from_upload(uploaded.name, uploaded.read())
    urls = _normalize(raw)
    st.caption(f"**{len(urls)} unique URL(s)** after normalize + dedupe.")
    if urls:
        with st.expander("Preview normalized URLs"):
            st.write(urls)

    if st.button("Run", type="primary", disabled=not urls):
        settings = Settings()
        settings.max_pages, settings.max_depth, settings.max_extract_pages = max_pages, max_depth, max_extract
        settings.llm_provider = provider
        if cdp_url.strip():
            settings.cdp_url = cdp_url.strip()
        try:
            settings.require_llm_key()
        except Exception as e:
            st.error(str(e)); st.stop()

        with st.spinner(f"Crawling {len(urls)} conference(s)…"):
            results = asyncio.run(run_urls(urls, settings))

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

        st.success(f"Done — analyzed {len(results)} conference(s) · saved to {DB_PATH} · "
                   f"{ {k: v for k, v in counts.items() if k != 'url_count'} }")
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
                st.caption(f"Pages crawled: {r.pages_crawled} · start: {r.start_url}")
                if r.evidence:
                    with st.expander("Evidence"):
                        for e in r.evidence:
                            st.markdown(f"- **{e.field}** — [{e.source_url}]({e.source_url})\n\n  > {e.snippet}")

        st.download_button("Download JSON",
                           data=json.dumps([r.model_dump(mode="json") for r in results], indent=2, ensure_ascii=False),
                           file_name="cfp_results.json", mime="application/json")

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
        df = pd.DataFrame([{
            "key": r["key"],
            "Conference": r["name"] or "",
            "Status": r["cfp_status"] or "",
            "Deadline": r["cfp_close_date"] or "",
            "Verified": r["verification_status"] == "verified",
            "Last Checked": (r["last_checked"] or "")[:10],
            "Categories": r["categories"] or "",
            "Details": r["status_details"] or "",
        } for r in records])

        edited = st.data_editor(
            df, use_container_width=True, hide_index=True, height=460,
            disabled=["key", "Conference", "Last Checked", "Categories", "Details"],
            column_config={
                "key": None,  # hide
                "Verified": st.column_config.CheckboxColumn("Verified"),
                "Deadline": st.column_config.TextColumn("Deadline"),
                "Status": st.column_config.TextColumn("Status"),
            },
            key="review_editor",
        )

        if st.button("💾 Save verifications", type="primary"):
            by_key = {r["key"]: r for r in records}
            n = 0
            for _, row in edited.iterrows():
                orig = by_key.get(row["key"])
                if orig is None:
                    continue
                newly_verified = row["Verified"] and orig["verification_status"] != "verified"
                changed = (row["Deadline"] or "") != (orig["cfp_close_date"] or "") or \
                          (row["Status"] or "") != (orig["cfp_status"] or "")
                if newly_verified or (row["Verified"] and changed):
                    store.verify(row["key"], {"cfp_close_date": row["Deadline"], "cfp_status": row["Status"]})
                    n += 1
            st.success(f"Saved {n} verification(s). Verified values will survive future crawls.")
            st.rerun()

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
