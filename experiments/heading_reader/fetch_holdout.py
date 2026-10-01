"""Render the 10 HOLDOUT pages once and save their text (page loads only, 2 s apart). Selection rule, fixed before any page was read:
the first P1 (call/submission) page of the v3.1 plan for every inventory site not already read by the sentence-picking or purpose-audit steps,
ordered by sha256(host); cyberdefenseconferences.com dropped because it is an event-listing aggregator, not an event. Run once."""
import asyncio, json, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
from src.cfp_monitor import fetch as _f                    # noqa: E402
from src.cfp_monitor.config import Settings                # noqa: E402

URLS = ["https://www.techshowlondon.co.uk/apply-to-speak-2027", "https://decarbconnectnorthamerica.com/awards/next-gen-awards-submission/",
        "https://www.shmoocon.org/cfp/", "https://lascon.org/cfp-now-closed/", "https://www.indiaenergyweek.com/conference/call-for-papers/",
        "https://www.crowdstrike.com/en-us/events/fal-con/las-vegas/call-for-papers/", "https://www.offensivecon.org/cfp.html",
        "https://www.innovationzero.com/event-partners/cfp-green-buildings", "https://www.hydrogenexpo.com/awards/submit-your-nomination/",
        "https://nullcon.net/event/nullcon-goa-2026/cfp/"]
STORE = HERE / "holdout_pages.json"


class _Q:
    def log(self, *a, **k):
        pass


async def main():
    settings = Settings()
    store = json.loads(STORE.read_text(encoding="utf-8")) if STORE.exists() else {}
    for u in URLS:
        if u in store:
            continue
        try:
            html, anchors, status, body, _c = await _f._render_with_consent(u, settings, _Q(), prefer_cdp=True)
            store[u] = {"text": body or "", "status": status}
        except Exception as e:                              # noqa: BLE001
            store[u] = {"text": "", "error": type(e).__name__}
        print(f"{len(store[u]['text']):>6} {store[u].get('error', '')} {u}", flush=True)
        STORE.write_text(json.dumps(store), encoding="utf-8")
        await asyncio.sleep(2)
    try:
        await _f.close_fallback_browser()
    except Exception:                                       # noqa: BLE001
        pass

asyncio.run(main())
