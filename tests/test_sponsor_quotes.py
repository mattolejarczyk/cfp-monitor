"""Extracting SPONSOR_QUOTE - our half of v1.5.

There is no real sponsor data yet; upstream's first 43-column delivery lands 2026-08-26. So
these are synthetic, and they test the DECISIONS rather than the plumbing - which is the part
that would cost the customer money if it were wrong.

A cost figure either kills an opportunity or commits real budget. It gets the same standard as
a deadline: the model may only point at text we already hold, and what we store is sliced out
of the page.
"""
from __future__ import annotations

import asyncio
import importlib.util
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location(
    "esq", ROOT / "scripts" / "extract_sponsor_quotes.py")
esq = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(esq)


# ------------------------------------------- a booth is not a speaking slot --
def test_a_booth_price_is_not_a_speaking_cost():
    assert esq.NOT_SPEAKING.search("Exhibition booths start at $4,500.")
    assert not esq.SPEAKING.search("Exhibition booths start at $4,500.")


def test_a_sentence_tying_speaking_to_sponsorship_survives_the_filter():
    s = "Speaking slots are reserved for Gold and Platinum sponsors."
    assert esq.SPEAKING.search(s)


def test_a_sentence_naming_both_is_kept():
    """A prospectus often lists booth AND speaking in one line. Rejecting anything that
    mentions a booth would throw away the sentence we actually want."""
    s = "Gold sponsorship includes a 6m booth and a 30-minute speaking session."
    assert esq.NOT_SPEAKING.search(s) and esq.SPEAKING.search(s)


# ------------------------------------------------- the verbatim guarantee --
def test_a_quote_the_page_does_not_contain_is_refused():
    page = "Sponsorship packages begin at $12,000 and include a speaking slot."
    assert esq.locate_verbatim(page, "Sponsorship costs roughly twelve thousand dollars") is None


def test_a_re_spaced_copy_is_accepted_and_corrected_back_to_the_page():
    page = "Sponsorship  packages\nbegin at $12,000 and include a speaking slot."
    got = esq.locate_verbatim(page, "sponsorship packages begin at $12,000")
    assert got is not None
    assert got in page, "what we keep must be the page's own characters"


# ------------------------------------------------ which rows are candidates --
def _db(tmp_path, rows):
    p = tmp_path / "t.db"
    con = sqlite3.connect(p)
    con.execute("""create table grounding_facts (event_id text primary key, name text,
                   sponsor_url text, sponsor_cost text, sponsor_required text,
                   sponsor_quote text)""")
    con.executemany("insert into grounding_facts values (?,?,?,?,?,?)", rows)
    con.commit()
    con.close()
    return str(p)


def test_only_rows_needing_a_quote_are_picked_up(tmp_path):
    db = _db(tmp_path, [
        ("a", "Wants one", "https://x.com/s", "$10k", "Yes", ""),        # <- the only candidate
        ("b", "Already has one", "https://x.com/s", "$10k", "Yes", "a quote we already extracted"),
        ("c", "No page to read", "", "$10k", "Yes", ""),
        ("d", "Not required", "https://x.com/s", "", "No", ""),
        ("e", "Unknown", "https://x.com/s", "", "Unknown", ""),
    ])
    assert [r["event_id"] for r in esq.candidates(db, None)] == ["a"]


def test_a_pre_v15_database_is_refused_rather_than_crashing(tmp_path):
    p = tmp_path / "old.db"
    con = sqlite3.connect(p)
    con.execute("create table grounding_facts (event_id text primary key, name text)")
    con.commit()
    con.close()
    with pytest.raises(SystemExit) as e:
        esq.candidates(str(p), None)
    assert "predates v1.5" in str(e.value)


# ------------------------------------- an outage is not "the page says nothing" --
def test_an_llm_outage_reports_unavailable_not_blank(monkeypatch):
    """A considered blank means the page does not say it, and stands. An outage means try
    again. Recording one as the other writes a false finding into the database."""
    class Boom:
        async def acompletion(self, **kw):
            raise RuntimeError("provider down")
    class Stub:                       # a real Settings has these; the stub only needs them
        llm_proxy_url = ""
        llm_provider = "test/model"
        license_key = ""
        client_version = "t"

        def provider_key(self):
            return "k"

    monkeypatch.setitem(sys.modules, "litellm", Boom())
    q, kind, status = asyncio.run(esq.choose("some page text", "Conf", "", Stub()))
    assert status == "unavailable" and q == "", "an outage must not be recorded as a blank"
