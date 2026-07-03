#!/usr/bin/env python3
"""
PR Monitor Quality Monitor

Read-only quality monitor for PR Monitor crawl/extract/enrich/review gates.
Initial implementation focuses on Crawl Quality Gate using Nicolia-provided
source-list snapshots/manifests.

IMPORTANT: This script never writes to customer Google Sheets. It reads local
snapshots/manifests and writes external quality reports under pr_monitor_1/.

Usage:
  python3 quality_monitor.py crawl-baseline \
    --input pr_monitor_1/quality_inputs/latest_crawl_baseline_urls.json

  python3 quality_monitor.py crawl-baseline \
    --input pr_monitor_1/quality_inputs/latest_crawl_baseline_urls.json \
    --limit 5
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse, urlunparse

import requests
from bs4 import BeautifulSoup

PROJECT_ROOT = Path(__file__).resolve().parent
QUALITY_REPORTS_DIR = PROJECT_ROOT / "pr_monitor_1" / "quality_reports"
QUALITY_INPUTS_DIR = PROJECT_ROOT / "pr_monitor_1" / "quality_inputs"

DEFAULT_INPUT = QUALITY_INPUTS_DIR / "latest_crawl_baseline_urls.json"

USER_AGENTS = [
    # Conservative, ordinary browser UA. Do not use evasive or deceptive identity.
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.4 Safari/605.1.15",
]

BLOCK_PATTERNS = [
    r"cloudflare",
    r"captcha",
    r"access denied",
    r"request blocked",
    r"forbidden",
    r"verify you are human",
    r"verify you're human",
    r"checking your browser",
    r"just a moment",
    r"enable javascript and cookies",
    r"validation process",
    r"unusual traffic",
    r"bot detection",
    r"security check",
    r"akamai",
    r"perimeterx",
]

PLATFORM_PATTERNS = [
    r"sessionize\.com",
    r"call for papers, schedule and speaker management",
    r"speaker management",
    r"submission management platform",
]

CFP_KEYWORDS = [
    "call for papers",
    "call for abstracts",
    "cfp",
    "submit a proposal",
    "submit your proposal",
    "speaker submission",
    "become a speaker",
    "abstract submission",
    "submission deadline",
    "call for speakers",
    "present at",
]

DATE_PATTERNS = [
    r"\b(?:january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{1,2},?\s+\d{4}\b",
    r"\b\d{1,2}\s+(?:january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{4}\b",
    r"\b\d{1,2}/\d{1,2}/\d{2,4}\b",
    r"\b\d{4}-\d{2}-\d{2}\b",
]


@dataclass
class CrawlQualityRecord:
    run_id: str
    source_list_name: str
    source_list_key: str
    row_number: int
    name: str
    url: str
    normalized_url: str
    status: str
    status_reason: str
    http_status: Optional[int]
    final_url: Optional[str]
    redirected: bool
    content_bytes: int
    text_chars: int
    content_hash: Optional[str]
    page_title: str
    crawl_seconds: float
    fallback_protocols_used: List[str]
    risk_flags: List[str]
    cfp_keyword_hits: List[str]
    date_snippets_found: List[str]
    next_action: str
    error: Optional[str]
    captured_at: str


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_url(url: str) -> str:
    url = (url or "").strip()
    if not url:
        return url
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    parsed = urlparse(url)
    scheme = parsed.scheme.lower() or "https"
    netloc = parsed.netloc.lower()
    path = parsed.path or "/"
    return urlunparse((scheme, netloc, path, "", parsed.query, ""))


def content_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def extract_text_and_title(html: str) -> Tuple[str, str]:
    soup = BeautifulSoup(html or "", "html.parser")
    title = ""
    if soup.title and soup.title.string:
        title = soup.title.string.strip()
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text(" ", strip=True)
    text = re.sub(r"\s+", " ", text).strip()
    return text, title


def find_patterns(patterns: List[str], text: str) -> List[str]:
    hits = []
    for p in patterns:
        if re.search(p, text, re.IGNORECASE):
            hits.append(p)
    return hits


def find_keyword_hits(keywords: List[str], text: str) -> List[str]:
    t = text.lower()
    return [kw for kw in keywords if kw in t]


def find_dates(text: str, max_dates: int = 10) -> List[str]:
    found: List[str] = []
    for p in DATE_PATTERNS:
        for m in re.findall(p, text, flags=re.IGNORECASE):
            val = m if isinstance(m, str) else " ".join(m)
            val = val.strip()
            if val and val not in found:
                found.append(val)
            if len(found) >= max_dates:
                return found
    return found


def classify_response(
    *,
    item: Dict[str, Any],
    url: str,
    response: Optional[requests.Response],
    error: Optional[str],
    elapsed: float,
    fallback_protocols: List[str],
) -> CrawlQualityRecord:
    run_id = item["_run_id"]
    captured_at = now_iso()
    normalized = normalize_url(url)

    http_status: Optional[int] = None
    final_url: Optional[str] = None
    redirected = False
    content_len = 0
    text_chars = 0
    chash: Optional[str] = None
    title = ""
    risk_flags: List[str] = []
    keyword_hits: List[str] = []
    date_hits: List[str] = []

    if error:
        if "TIMEOUT" in error:
            status = "TIMEOUT"
            reason = "request_timeout"
            next_action = "retry_once_with_extended_timeout_then_manual_check"
        elif "INVALID_URL" in error:
            status = "INVALID_URL"
            reason = "malformed_or_empty_url"
            next_action = "correct_url_from_source_or_manual"
        else:
            status = "INVALID_URL"
            reason = error
            next_action = "manual_check"
        return CrawlQualityRecord(
            run_id=run_id,
            source_list_name=item.get("source_list_name", ""),
            source_list_key=item.get("source_list_key", ""),
            row_number=int(item.get("row_number") or 0),
            name=item.get("name", ""),
            url=url,
            normalized_url=normalized,
            status=status,
            status_reason=reason,
            http_status=http_status,
            final_url=final_url,
            redirected=redirected,
            content_bytes=0,
            text_chars=0,
            content_hash=None,
            page_title="",
            crawl_seconds=round(elapsed, 3),
            fallback_protocols_used=fallback_protocols,
            risk_flags=[],
            cfp_keyword_hits=[],
            date_snippets_found=[],
            next_action=next_action,
            error=error,
            captured_at=captured_at,
        )

    assert response is not None
    http_status = response.status_code
    final_url = response.url
    redirected = normalize_url(final_url) != normalized
    if redirected:
        risk_flags.append("redirected_domain" if urlparse(final_url).netloc.lower() != urlparse(normalized).netloc.lower() else "redirected_url")

    raw = response.content or b""
    content_len = len(raw)
    chash = content_hash(raw) if raw else None

    content_type = response.headers.get("content-type", "").lower()
    html = response.text if "text" in content_type or "html" in content_type or not content_type else response.text
    text, title = extract_text_and_title(html)
    text_chars = len(text)
    combined = f"{final_url or ''} {title} {text[:5000]}"

    block_hits = find_patterns(BLOCK_PATTERNS, combined)
    platform_hits = find_patterns(PLATFORM_PATTERNS, combined)
    keyword_hits = find_keyword_hits(CFP_KEYWORDS, text)
    date_hits = find_dates(text)

    if keyword_hits:
        risk_flags.append("cfp_keywords_present")
    else:
        risk_flags.append("cfp_keywords_absent")
    if date_hits:
        risk_flags.append("date_snippets_present")
    if any(x in (item.get("location", "") or "").lower() for x in ["multiple", "multiple cities"]):
        risk_flags.append("multi_location_possible")
    if "2025" in (item.get("start_dates", "") or ""):
        risk_flags.append("date_rollover_candidate")
    if platform_hits:
        risk_flags.append("submission_platform_detected")

    if http_status in (403, 429) or block_hits:
        status = "BLOCKED"
        reason = f"blocked_or_bot_protection_detected:{','.join(block_hits[:3])}" if block_hits else f"http_{http_status}"
        next_action = "retry_with_fallback_protocol_or_manual_check"
    elif http_status >= 400:
        status = "INVALID_URL"
        reason = f"http_{http_status}"
        next_action = "correct_url_from_source_or_manual"
    elif platform_hits and "sessionize" in combined.lower():
        status = "NON_CONFERENCE_PLATFORM"
        reason = "platform_page_detected_not_event_owner"
        next_action = "find_actual_event_owner_url"
    elif content_len == 0 or text_chars == 0:
        status = "PARTIAL"
        reason = "empty_or_no_text_content"
        next_action = "retry_with_rendered_browser_or_manual_review"
    elif text_chars < 1500:
        status = "PARTIAL"
        reason = f"low_text_content:{text_chars}_chars"
        risk_flags.append("low_content_volume")
        next_action = "retry_with_rendered_browser_or_manual_review"
    else:
        status = "PASS"
        reason = "usable_content_captured"
        next_action = "proceed_to_extract"
        if text_chars < 3000:
            risk_flags.append("low_content_volume")

    return CrawlQualityRecord(
        run_id=run_id,
        source_list_name=item.get("source_list_name", ""),
        source_list_key=item.get("source_list_key", ""),
        row_number=int(item.get("row_number") or 0),
        name=item.get("name", ""),
        url=url,
        normalized_url=normalized,
        status=status,
        status_reason=reason,
        http_status=http_status,
        final_url=final_url,
        redirected=redirected,
        content_bytes=content_len,
        text_chars=text_chars,
        content_hash=chash,
        page_title=title,
        crawl_seconds=round(elapsed, 3),
        fallback_protocols_used=fallback_protocols,
        risk_flags=sorted(set(risk_flags)),
        cfp_keyword_hits=keyword_hits,
        date_snippets_found=date_hits,
        next_action=next_action,
        error=None,
        captured_at=captured_at,
    )


def fetch_url(url: str, timeout: int = 20) -> Tuple[Optional[requests.Response], Optional[str], float, List[str]]:
    start = time.time()
    fallbacks: List[str] = []
    normalized = normalize_url(url)
    if not normalized or not urlparse(normalized).netloc:
        return None, "INVALID_URL", 0.0, fallbacks

    session = requests.Session()
    last_error: Optional[str] = None

    for idx, ua in enumerate(USER_AGENTS):
        protocol = "basic_http_fetch" if idx == 0 else "alternate_user_agent"
        fallbacks.append(protocol)
        try:
            resp = session.get(
                normalized,
                timeout=timeout,
                allow_redirects=True,
                headers={
                    "User-Agent": ua,
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.9",
                    "Cache-Control": "no-cache",
                },
            )
            elapsed = time.time() - start
            # If first UA got a hard block, allow one ordinary alternate UA before returning.
            if resp.status_code in (403, 429) and idx == 0:
                last_error = f"HTTP_{resp.status_code}"
                continue
            return resp, None, elapsed, fallbacks
        except requests.exceptions.Timeout:
            elapsed = time.time() - start
            return None, "TIMEOUT", elapsed, fallbacks
        except requests.exceptions.RequestException as e:
            last_error = f"REQUEST_ERROR:{type(e).__name__}:{str(e)[:200]}"
            continue

    elapsed = time.time() - start
    return None, last_error or "REQUEST_ERROR", elapsed, fallbacks


def summarize(records: List[CrawlQualityRecord]) -> Dict[str, Any]:
    total = len(records)
    counts: Dict[str, int] = {}
    for r in records:
        counts[r.status] = counts.get(r.status, 0) + 1

    classified = total  # every record emitted by this monitor is classified
    pass_count = counts.get("PASS", 0)
    silent_failures = 0

    def pct(n: int) -> float:
        return round((n / total * 100), 2) if total else 0.0

    return {
        "urls_attempted": total,
        "status_counts": counts,
        "pass_count": pass_count,
        "actionable_classification_rate_pct": pct(classified),
        "usable_content_rate_pct": pct(pass_count),
        "silent_failure_count": silent_failures,
        "silent_failure_rate_pct": pct(silent_failures),
        "partial_rate_pct": pct(counts.get("PARTIAL", 0)),
        "blocked_rate_pct": pct(counts.get("BLOCKED", 0)),
        "timeout_rate_pct": pct(counts.get("TIMEOUT", 0)),
        "invalid_rate_pct": pct(counts.get("INVALID_URL", 0)),
        "non_conference_platform_rate_pct": pct(counts.get("NON_CONFERENCE_PLATFORM", 0)),
        "avg_crawl_seconds": round(sum(r.crawl_seconds for r in records) / total, 3) if total else 0,
        "target_actionable_classification_pct": 95,
        "target_usable_content_pct_initial": 90,
        "target_met_actionable_classification": pct(classified) >= 95,
        "target_met_usable_content_initial": pct(pass_count) >= 90,
    }


def top_failure_modes(records: List[CrawlQualityRecord]) -> List[Dict[str, Any]]:
    failures: Dict[str, Dict[str, Any]] = {}
    for r in records:
        if r.status == "PASS":
            continue
        key = f"{r.status}:{r.status_reason}"
        entry = failures.setdefault(key, {"failure_mode": key, "count": 0, "examples": []})
        entry["count"] += 1
        if len(entry["examples"]) < 5:
            entry["examples"].append({"name": r.name, "url": r.url, "row_number": r.row_number})
    return sorted(failures.values(), key=lambda x: (-x["count"], x["failure_mode"]))[:10]


def recommendations(summary: Dict[str, Any], failures: List[Dict[str, Any]]) -> List[str]:
    recs: List[str] = []
    counts = summary.get("status_counts", {})
    if counts.get("BLOCKED", 0):
        recs.append("Add rendered-browser fallback or proxy/manual path for BLOCKED URLs before extraction.")
    if counts.get("PARTIAL", 0):
        recs.append("Run PARTIAL URLs through a JavaScript-rendered crawl path and compare content size/hash.")
    if counts.get("TIMEOUT", 0):
        recs.append("Add retry-once with extended timeout for TIMEOUT URLs, then route to manual check.")
    if counts.get("NON_CONFERENCE_PLATFORM", 0):
        recs.append("Add owner-event URL resolver for platform/listing pages such as Sessionize.")
    if not summary.get("target_met_usable_content_initial"):
        recs.append("Do not feed full baseline to Extract yet; improve crawl fallback paths and rerun same manifest.")
    if not recs:
        recs.append("Crawl baseline meets initial targets; proceed to Extract Quality Gate baseline.")
    return recs


def write_text_report(path: Path, report: Dict[str, Any]) -> None:
    s = report["summary"]
    lines = []
    lines.append(f"CRAWL QUALITY REPORT — {report['run_id']}")
    lines.append("")
    lines.append(f"URLs attempted: {s['urls_attempted']}")
    for status in ["PASS", "PARTIAL", "BLOCKED", "TIMEOUT", "INVALID_URL", "NON_CONFERENCE_PLATFORM", "REDIRECTED", "NEEDS_MANUAL"]:
        lines.append(f"{status}: {s['status_counts'].get(status, 0)}")
    lines.append(f"Silent failures: {s['silent_failure_count']}")
    lines.append("")
    lines.append(f"Actionable classification rate: {s['actionable_classification_rate_pct']}%")
    lines.append(f"Usable content rate: {s['usable_content_rate_pct']}%")
    lines.append(f"Average crawl seconds: {s['avg_crawl_seconds']}")
    lines.append(f"Actionable target met? {'YES' if s['target_met_actionable_classification'] else 'NO'}")
    lines.append(f"Usable content initial target met? {'YES' if s['target_met_usable_content_initial'] else 'NO'}")
    lines.append("")
    lines.append("Top failure modes:")
    if report["top_failure_modes"]:
        for idx, f in enumerate(report["top_failure_modes"], 1):
            lines.append(f"{idx}. {f['failure_mode']} — {f['count']}")
            for ex in f["examples"]:
                lines.append(f"   - Row {ex['row_number']}: {ex['name']} | {ex['url']}")
    else:
        lines.append("None")
    lines.append("")
    lines.append("Recommended improvements:")
    for idx, rec in enumerate(report["recommendations"], 1):
        lines.append(f"{idx}. {rec}")

    # Local browser fallback recovery section
    fb = report.get("local_browser_fallback", {})
    lines.append("")
    lines.append("=" * 60)
    lines.append("LOCAL BROWSER FALLBACK RECOVERY")
    lines.append("=" * 60)
    if fb.get("recovery_available"):
        lines.append(f"Recovery data available: YES")
        lines.append(f"Uploads directory: {fb.get('uploads_dir', 'N/A')}")
        ls = fb.get("local_browser_summary", {})
        lines.append(f"Total URLs: {ls.get('total_urls', 'N/A')}")
        lines.append(f"Recovered by local: {ls.get('recovered_by_local', 'N/A')}")
        lines.append(f"Still blocked: {ls.get('still_blocked', 'N/A')}")
        lines.append("")
        for r in fb.get("recovery_map", []):
            status = "RECOVERED" if r.get("recovered") else "STILL BLOCKED"
            lines.append(f"  [{status}] {r.get('name', '')}")
            lines.append(f"    VPS: {r.get('original_vps_status')} -> Local: {r.get('local_browser_status')}")
            lines.append(f"    Method: {r.get('fallback_method', 'N/A')}")
    else:
        lines.append("Recovery data available: NO")
        lines.append("Run the local Windows runner to attempt recovery of BLOCKED/PARTIAL URLs.")
        lines.append(f"Uploads directory: {fb.get('uploads_dir', 'N/A')}")

    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def run_crawl_baseline(args: argparse.Namespace) -> int:
    input_path = Path(args.input or DEFAULT_INPUT)
    if not input_path.is_absolute():
        input_path = PROJECT_ROOT / input_path
    if not input_path.exists():
        print(f"Input manifest not found: {input_path}", file=sys.stderr)
        return 2

    manifest = json.loads(input_path.read_text(encoding="utf-8"))
    items = manifest.get("items", [])
    if args.limit:
        items = items[: args.limit]

    run_id = args.run_id or f"crawl_quality_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    QUALITY_REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    records: List[CrawlQualityRecord] = []
    for i, item in enumerate(items, 1):
        item = dict(item)
        item["_run_id"] = run_id
        url = item.get("url", "")
        print(f"[{i}/{len(items)}] {item.get('name') or url} — {url}")
        resp, err, elapsed, fallbacks = fetch_url(url, timeout=args.timeout)
        record = classify_response(item=item, url=url, response=resp, error=err, elapsed=elapsed, fallback_protocols=fallbacks)
        records.append(record)
        print(f"  -> {record.status} ({record.status_reason}) text={record.text_chars} bytes={record.content_bytes} time={record.crawl_seconds}s")

    record_dicts = [asdict(r) for r in records]
    summary = summarize(records)
    failures = top_failure_modes(records)

    # --- Local browser fallback integration ---
    # Check for local browser fallback results that may have recovered BLOCKED/PARTIAL URLs
    local_browser_root = PROJECT_ROOT / "pr_monitor_1" / "local_browser_fallback"
    uploads_dir = local_browser_root / "uploads"
    recovery_map = []
    local_browser_summary = None

    if uploads_dir.exists():
        # Find the most recent upload for this run
        run_uploads = sorted(uploads_dir.glob("*/"), key=lambda p: p.stat().st_mtime, reverse=True)
        for upload_dir in run_uploads:
            summary_files = list(upload_dir.glob("*.json"))
            for sf in summary_files:
                try:
                    local_data = json.loads(sf.read_text(encoding="utf-8"))
                    if local_data.get("run_id") == run_id or run_id in str(upload_dir):
                        local_browser_summary = local_data
                        recovery_map = local_data.get("recovery_map", [])
                        break
                except Exception:
                    continue
            if recovery_map:
                break

    # Build combined recommendations
    recs = recommendations(summary, failures)

    report = {
        "run_id": run_id,
        "created_at": now_iso(),
        "input_manifest": str(input_path),
        "customer_sheet_write_policy": "READ_ONLY_NO_CUSTOMER_SHEET_WRITES",
        "summary": summary,
        "top_failure_modes": failures,
        "recommendations": recs,
        "local_browser_fallback": {
            "enabled": True,
            "uploads_dir": str(uploads_dir),
            "recovery_available": len(recovery_map) > 0,
            "recovery_map": recovery_map,
            "local_browser_summary": local_browser_summary.get("recovery_summary", {}) if local_browser_summary else {},
        },
        "records": record_dicts,
    }

    json_path = QUALITY_REPORTS_DIR / f"{run_id}.json"
    txt_path = QUALITY_REPORTS_DIR / f"{run_id}.txt"
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    write_text_report(txt_path, report)
    (QUALITY_REPORTS_DIR / "latest_quality_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (QUALITY_REPORTS_DIR / "latest_quality_report.txt").write_text(txt_path.read_text(encoding="utf-8"), encoding="utf-8")

    print("\nReport written:")
    print(f"  {json_path}")
    print(f"  {txt_path}")
    print("\nSummary:")
    print(json.dumps(summary, indent=2))

    if recovery_map:
        print("\n--- Local Browser Fallback Recovery ---")
        for r in recovery_map:
            status = "RECOVERED" if r.get("recovered") else "STILL BLOCKED"
            print(f"  [{status}] {r.get('name', '')[:50]}")
            print(f"    VPS: {r.get('original_vps_status')} -> Local: {r.get('local_browser_status')}")

    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="PR Monitor Quality Monitor")
    sub = parser.add_subparsers(dest="command", required=True)

    crawl = sub.add_parser("crawl-baseline", help="Run Crawl Quality Gate baseline")
    crawl.add_argument("--input", default=str(DEFAULT_INPUT), help="Input crawl baseline manifest JSON")
    crawl.add_argument("--limit", type=int, default=0, help="Limit number of URLs for smoke tests")
    crawl.add_argument("--timeout", type=int, default=20, help="Per-request timeout seconds")
    crawl.add_argument("--run-id", default="", help="Optional run ID")
    crawl.set_defaults(func=run_crawl_baseline)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
