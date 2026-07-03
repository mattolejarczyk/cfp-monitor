"""Streamlit UI for the CFP monitor.

Paste a fixed list of conference URLs, tune the crawl budget, run, and view each
conference's CFP verdict, evidence, and the crawl decision trace.

Run:  streamlit run app.py
"""
from __future__ import annotations

import asyncio

import streamlit as st

from src.cfp_monitor import run_urls, Settings
from src.cfp_monitor.models import Fact

st.set_page_config(page_title="CFP Monitor", page_icon="🎤", layout="wide")
st.title("🎤 Conference CFP Monitor")
st.caption("Fixed-list conference URLs → agentic crawl4ai exploration → evidence-backed CFP results.")

with st.sidebar:
    st.header("Settings")
    max_pages = st.slider("Max pages / site", 3, 40, 12)
    max_depth = st.slider("Max crawl depth", 1, 4, 2)
    max_extract = st.slider("Max pages to LLM-extract", 2, 15, 8)
    provider = st.text_input("LLM provider (LiteLLM string)", "openrouter/deepseek/deepseek-chat")
    st.caption("Set OPENROUTER_API_KEY in your environment / .env before running.")

urls_text = st.text_area(
    "Conference URLs (one per line)",
    placeholder="https://conf-a.example.com\nhttps://conf-b.example.org",
    height=160,
)

_STATUS_ICON = {"open": "🟢", "upcoming": "🟡", "unclear": "⚪", "closed": "🔴", "none": "⚫"}


def _fact_line(label: str, fact: Fact) -> str:
    if not fact.value:
        return f"**{label}:** _unknown_"
    return f"**{label}:** {fact.value}  ·  _{fact.confidence.value}_"


if st.button("Run", type="primary"):
    urls = [u.strip() for u in urls_text.splitlines() if u.strip() and not u.startswith("#")]
    if not urls:
        st.warning("Enter at least one URL.")
        st.stop()

    settings = Settings()
    settings.max_pages = max_pages
    settings.max_depth = max_depth
    settings.max_extract_pages = max_extract
    settings.llm_provider = provider
    try:
        settings.require_llm_key()
    except Exception as e:
        st.error(str(e))
        st.stop()

    with st.spinner(f"Crawling {len(urls)} conference(s)…"):
        results = asyncio.run(run_urls(urls, settings))

    st.success(f"Done — analyzed {len(results)} conference(s).")
    for r in results:
        icon = _STATUS_ICON.get(r.cfp_status.value, "⚪")
        title = r.name.value or r.start_url
        with st.expander(f"{icon} {title} — CFP: {r.cfp_status.value}", expanded=True):
            if r.error:
                st.error(f"Error: {r.error}")
            # Trust summary — one plain sentence (details still below in Evidence/trace).
            if r.reason:
                st.info(f"**Why:** {r.reason}")
            c1, c2 = st.columns(2)
            with c1:
                st.markdown(_fact_line("Conference", r.name))
                st.markdown(_fact_line("Dates", r.conference_dates))
                st.markdown(_fact_line("Location", r.location))
                st.markdown(_fact_line("Audience / topics", r.audience_topics))
            with c2:
                basis = f"  ·  _{r.status_basis}_" if r.status_basis else ""
                st.markdown(f"**Has CFP:** {r.has_cfp}  ·  **Status:** {icon} {r.cfp_status.value}{basis}")
                st.markdown(_fact_line("CFP opens", r.cfp_open_date))
                st.markdown(_fact_line("CFP deadline", r.cfp_close_date))
                st.markdown(_fact_line("Submit at", r.submission_url))
                if r.submission_platform:
                    st.markdown(f"**Platform:** {r.submission_platform}")
                if r.opportunity_types:
                    st.markdown(f"**Opportunity types:** {', '.join(r.opportunity_types)}")
                st.markdown(f"**Submission form found:** {r.submission_form_found}")
            if r.possible_multi_edition_site:
                st.warning("Possible multi-edition site — facts may span editions: " + "; ".join(r.competing_event_mentions))
            if r.submission_forms:
                with st.expander(f"Forms discovered ({len(r.submission_forms)})"):
                    for f in r.submission_forms:
                        st.markdown(f"- **{f.get('platform','form')}** — [{f['url']}]({f['url']})  ·  {f.get('context','')}")
            st.caption(f"Pages crawled: {r.pages_crawled} · skipped: {r.pages_skipped} · start: {r.start_url}")

            if r.evidence:
                with st.expander("Evidence"):
                    for e in r.evidence:
                        st.markdown(f"- **{e.field}** — [{e.source_url}]({e.source_url})\n\n  > {e.snippet}")
            if r.trace:
                with st.expander("Crawl trace (decisions)"):
                    st.dataframe(r.trace, use_container_width=True, height=260)

    st.download_button(
        "Download JSON",
        data=__import__("json").dumps([r.model_dump(mode="json") for r in results], indent=2, ensure_ascii=False),
        file_name="cfp_results.json",
        mime="application/json",
    )
