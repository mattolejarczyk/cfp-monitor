#!/usr/bin/env python3
"""
PR FIRM TEXAS - UNIVERSAL BATCH PROCESSOR
Production-ready conference extraction system

Version: 1.0
Date: March 7, 2026
Purpose: Process any CSV with CONFERENCE URL column → 54-column output

Usage:
    python3 batch_processor.py --input <csv_file> --output <prefix>
    
Example:
    python3 batch_processor.py --input media/inbound/conferences.csv --output BATCH3

Output:
    - {prefix}_CONFERENCES_54COLUMNS.csv (54 columns, all rows)
    - {prefix}_EXECUTIVE_REPORT.txt (plain text report)
    - {prefix}_results.json (raw extraction data)
"""

import asyncio
import argparse
import csv
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from models import ReviewStatus, DEFAULT_REVIEW_STATUS

try:
    import source_registry as pr_source_registry
except Exception:  # source registry is an MVP enhancement; extraction can still run without it
    pr_source_registry = None

try:
    import change_detection as pr_change_detection
except Exception:  # change detection is an MVP enhancement; extraction can still run without it
    pr_change_detection = None

try:
    import deadline_intelligence as pr_deadline_intelligence
except Exception:  # deadline intelligence is an MVP enhancement; extraction can still run without it
    pr_deadline_intelligence = None

# Add workspace to path for imports
sys.path.insert(0, '/home/ubuntu/.openclaw/workspace')

try:
    from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, CacheMode
    from crawl4ai.extraction_strategy import LLMExtractionStrategy
except ImportError:
    print("ERROR: crawl4ai not installed. Run: pip install crawl4ai")
    sys.exit(1)

# =============================================================================
# CONFIGURATION - LOCKED STANDARD
# =============================================================================

# 55-Column Schema (53 data + 1 metrics + 1 qa_status)
COLUMN_SCHEMA = [
    # Group 1: Conference Info (11 columns)
    'conf_page_url', 'conf_name', 'conf_name_found', 'conf_dates', 'conf_dates_found',
    'conf_location', 'conf_location_found', 'conf_description', 'conf_description_found',
    'conf_page_cost', 'conf_page_paths_tried',

    # Group 2: Contact Info (11 columns)
    'contact_page_url', 'contact_name', 'contact_name_found', 'contact_email',
    'contact_email_found', 'contact_phone', 'contact_phone_found', 'contact_org',
    'contact_org_found', 'contact_page_cost', 'contact_paths_tried',

    # Group 3: CFP Info (10 columns)
    'cfp_page_url', 'cfp_status', 'cfp_status_found', 'cfp_deadline',
    'cfp_deadline_found', 'cfp_deadline_normalized', 'deadline_urgency', 'action_state',
    'cfp_opens', 'cfp_opens_found', 'cfp_sub_requirements',
    'cfp_sub_requirements_found', 'cfp_page_cost',

    # Group 4: Submission Portal (9 columns)
    'sub_page_url', 'sub_link', 'sub_link_found', 'sub_portal_name',
    'sub_portal_name_found', 'sub_instructions', 'sub_instructions_found',
    'sub_page_cost', 'sub_paths_tried',

    # Group 5: Summary (11 columns)
    'conference_name', 'base_url', 'domain', 'crawl_date', 'total_cost',
    'fields_with_value', 'fields_with_placeholder', 'fields_unavailable',
    'completeness_pct', 'budget_exceeded',

    # Column 52-53: Metadata (2 columns)
    'notable_info', 'crawl_notes',

    # Column 54: Metrics (REQUIRED)
    'metrics',

    # Column 55: QA review status
    'qa_status',
]

# Extraction schema for LLM
EXTRACTION_SCHEMA = {
    "conference_name": "string",
    "conference_dates": "string",
    "conference_location": "string", 
    "conference_description": "string",
    "contact_name": "string or N/A",
    "contact_email": "string or N/A",
    "contact_phone": "string or N/A",
    "contact_org": "string or N/A",
    "cfp_status": "string (Open/Closed/Unknown)",
    "cfp_deadline": "string or N/A",
    "cfp_link": "string or N/A"
}

LLM_INSTRUCTION = """Extract conference information from this website. Look for:
- Conference name, dates, location, description
- Contact information (name, email, phone, organization)
- Call for Papers (CFP) status, deadline, submission link
- Speaker submission information

Return as JSON with these exact keys: conference_name, conference_dates, conference_location, conference_description, contact_name, contact_email, contact_phone, contact_org, cfp_status, cfp_deadline, cfp_link"""

# =============================================================================
# CORE FUNCTIONS - LOCKED IMPLEMENTATION
# =============================================================================

def _source_registry_path_for_output(output_prefix: str) -> Path:
    if os.getenv("PR_MONITOR_SOURCE_REGISTRY"):
        return Path(os.environ["PR_MONITOR_SOURCE_REGISTRY"]).expanduser().resolve()
    runtime_root = os.getenv("PR_MONITOR_RUNTIME_ROOT")
    if runtime_root:
        return Path(runtime_root).expanduser().resolve() / "source_registry.json"
    return Path(output_prefix).expanduser().resolve().parent / "source_registry.json"


def _change_snapshot_path_for_output(output_prefix: str) -> Path:
    if os.getenv("PR_MONITOR_CHANGE_SNAPSHOTS"):
        return Path(os.environ["PR_MONITOR_CHANGE_SNAPSHOTS"]).expanduser().resolve()
    runtime_root = os.getenv("PR_MONITOR_RUNTIME_ROOT")
    if runtime_root:
        return Path(runtime_root).expanduser().resolve() / "change_snapshots.json"
    return Path(output_prefix).expanduser().resolve().parent / "change_snapshots.json"


def _prefer_remembered_paths(urls: list, registry_path: Path) -> list:
    if pr_source_registry is None:
        return urls
    try:
        return pr_source_registry.preferred_urls_for_sources(urls, registry_path)
    except Exception:
        return urls


def _update_source_registry_from_csv_rows(csv_rows: list, output_prefix: str, paths: dict) -> dict:
    if pr_source_registry is None:
        return {"ok": False, "error": "source_registry module unavailable"}
    registry_path = _source_registry_path_for_output(output_prefix)
    try:
        return pr_source_registry.update_registry_from_extraction_rows(
            registry_path=registry_path,
            rows=csv_rows,
            extract_id=Path(output_prefix).name,
            artifact_refs=paths,
        )
    except Exception as e:
        return {"registry_path": str(registry_path), "error": str(e), "updated_sources": 0}


def calculate_metrics(data: dict) -> str:
    """Calculate per-category completeness metrics for Column 54.
    
    Format: CONF X/Y (Z%), CONTACT X/Y (Z%), CFP X/Y (Z%), SUB X/Y (Z%)
    """
    # CONF: 4 fields
    conf_fields = ['conference_name', 'conference_dates', 'conference_location', 'conference_description']
    conf_found = sum(1 for f in conf_fields if data.get(f) and data.get(f) != 'N/A')
    conf_total = 4
    
    # CONTACT: 4 fields
    contact_fields = ['contact_name', 'contact_email', 'contact_phone', 'contact_org']
    contact_found = sum(1 for f in contact_fields if data.get(f) and data.get(f) != 'N/A')
    contact_total = 4
    
    # CFP: 4 fields (only count if cfp_status is not Unknown)
    cfp_fields = ['cfp_status', 'cfp_deadline', 'cfp_link']
    cfp_status = data.get('cfp_status', 'Unknown')
    if cfp_status and cfp_status != 'Unknown':
        cfp_found = sum(1 for f in cfp_fields if data.get(f) and data.get(f) not in ['N/A', 'Unknown', ''])
        cfp_total = 4  # Including implicit cfp_sub_requirements
    else:
        cfp_found = 0
        cfp_total = 0
    
    # SUB: 3 fields
    sub_fields = ['cfp_link']  # sub_link maps to cfp_link
    sub_found = sum(1 for f in sub_fields if data.get(f) and data.get(f) not in ['N/A', ''])
    sub_total = 3
    
    # Calculate percentages
    conf_pct = int((conf_found / conf_total) * 100) if conf_total > 0 else 0
    contact_pct = int((contact_found / contact_total) * 100) if contact_total > 0 else 0
    cfp_pct = int((cfp_found / cfp_total) * 100) if cfp_total > 0 else 0
    sub_pct = int((sub_found / sub_total) * 100) if sub_total > 0 else 0
    
    return f"CONF {conf_found}/{conf_total} ({conf_pct}%), CONTACT {contact_found}/{contact_total} ({contact_pct}%), CFP {cfp_found}/{cfp_total} ({cfp_pct}%), SUB {sub_found}/{sub_total} ({sub_pct}%)"


def determine_tier(dates_str: str, current_month: int = 3) -> str:
    """Determine conference tier based on dates."""
    if not dates_str:
        return '4'  # Uncertain
    
    if '2026' in dates_str:
        return '1'  # 2026 Confirmed
    elif '2025' in dates_str:
        # Check month
        months = {
            'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
            'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12,
            'january': 1, 'february': 2, 'march': 3, 'april': 4, 'june': 6,
            'july': 7, 'august': 8, 'september': 9, 'october': 10, 'november': 11, 'december': 12
        }
        
        dates_lower = dates_str.lower()
        for month_name, month_num in months.items():
            if month_name in dates_lower:
                if month_num >= current_month:
                    return '2'  # Likely 2026
                else:
                    return '3'  # Likely past
        return '4'  # Uncertain
    elif '2024' in dates_str:
        return '3'  # Likely past
    else:
        return '4'  # Uncertain


def build_csv_row(row_num: int, source_url: str, data: dict, status: str | ReviewStatus = DEFAULT_REVIEW_STATUS) -> dict:
    """Build a single 54-column row from extracted data."""
    enriched_deadline = {}
    if pr_deadline_intelligence is not None:
        try:
            enriched_deadline = pr_deadline_intelligence.enrich_row(data)
        except Exception:
            enriched_deadline = {}
    cfp_deadline_normalized = enriched_deadline.get('cfp_deadline_normalized') or 'unknown'
    deadline_urgency = enriched_deadline.get('deadline_urgency') or 'unknown'
    action_state = enriched_deadline.get('action_state') or 'unknown'
    
    # Calculate value counts
    all_values = [
        data.get('conference_name'), data.get('conference_dates'),
        data.get('conference_location'), data.get('conference_description'),
        data.get('contact_name'), data.get('contact_email'),
        data.get('contact_phone'), data.get('contact_org'),
        data.get('cfp_status'), data.get('cfp_deadline'), data.get('cfp_link')
    ]
    fields_with_value = sum(1 for v in all_values if v and v != 'N/A')
    fields_unavailable = 51 - fields_with_value
    completeness_pct = round(fields_with_value / 51 * 100, 1)
    
    # Determine tier
    tier = determine_tier(data.get('conference_dates', ''))
    
    # Build row
    return {
        # Group 1: Conference Info
        'conf_page_url': source_url,
        'conf_name': data.get('conference_name', ''),
        'conf_name_found': 'VALUE_FOUND' if data.get('conference_name') else 'UNAVAILABLE',
        'conf_dates': data.get('conference_dates', ''),
        'conf_dates_found': 'VALUE_FOUND' if data.get('conference_dates') else 'UNAVAILABLE',
        'conf_location': data.get('conference_location', ''),
        'conf_location_found': 'VALUE_FOUND' if data.get('conference_location') else 'UNAVAILABLE',
        'conf_description': data.get('conference_description', ''),
        'conf_description_found': 'VALUE_FOUND' if data.get('conference_description') else 'UNAVAILABLE',
        'conf_page_cost': '0.001',
        'conf_page_paths_tried': source_url,
        
        # Group 2: Contact Info
        'contact_page_url': source_url,
        'contact_name': data.get('contact_name', ''),
        'contact_name_found': 'VALUE_FOUND' if data.get('contact_name') and data.get('contact_name') != 'N/A' else 'UNAVAILABLE',
        'contact_email': data.get('contact_email', ''),
        'contact_email_found': 'VALUE_FOUND' if data.get('contact_email') and data.get('contact_email') != 'N/A' else 'UNAVAILABLE',
        'contact_phone': data.get('contact_phone', ''),
        'contact_phone_found': 'VALUE_FOUND' if data.get('contact_phone') and data.get('contact_phone') != 'N/A' else 'UNAVAILABLE',
        'contact_org': data.get('contact_org', ''),
        'contact_org_found': 'VALUE_FOUND' if data.get('contact_org') and data.get('contact_org') != 'N/A' else 'UNAVAILABLE',
        'contact_page_cost': '0.001',
        'contact_paths_tried': source_url,
        
        # Group 3: CFP Info
        'cfp_page_url': data.get('cfp_link', 'UNAVAILABLE'),
        'cfp_status': data.get('cfp_status', 'Unknown'),
        'cfp_status_found': 'VALUE_FOUND' if data.get('cfp_status') and data.get('cfp_status') != 'Unknown' else 'UNAVAILABLE',
        'cfp_deadline': data.get('cfp_deadline', ''),
        'cfp_deadline_found': 'VALUE_FOUND' if data.get('cfp_deadline') and data.get('cfp_deadline') != 'N/A' else 'UNAVAILABLE',
        'cfp_deadline_normalized': cfp_deadline_normalized,
        'deadline_urgency': deadline_urgency,
        'action_state': action_state,
        'cfp_opens': 'N/A',
        'cfp_opens_found': 'UNAVAILABLE',
        'cfp_sub_requirements': 'N/A',
        'cfp_sub_requirements_found': 'UNAVAILABLE',
        'cfp_page_cost': '0.001',
        
        # Group 4: Submission Portal
        'sub_page_url': data.get('cfp_link', 'UNAVAILABLE'),
        'sub_link': data.get('cfp_link', ''),
        'sub_link_found': 'VALUE_FOUND' if data.get('cfp_link') and data.get('cfp_link') not in ['N/A', ''] else 'UNAVAILABLE',
        'sub_portal_name': 'N/A',
        'sub_portal_name_found': 'UNAVAILABLE',
        'sub_instructions': 'N/A',
        'sub_instructions_found': 'UNAVAILABLE',
        'sub_page_cost': '0.001',
        'sub_paths_tried': source_url,
        
        # Group 5: Summary
        'conference_name': data.get('conference_name', ''),
        'base_url': source_url,
        'domain': source_url.split('/')[2] if source_url and '/' in source_url else '',
        'crawl_date': datetime.now().isoformat(),
        'total_cost': '0.003',
        'fields_with_value': str(fields_with_value),
        'fields_with_placeholder': '0',
        'fields_unavailable': str(fields_unavailable),
        'completeness_pct': str(completeness_pct),
        'budget_exceeded': 'False',
        
        # Column 52-53: Metadata
        'notable_info': f"[TIER: {tier}] Extracted from {source_url}",
        'crawl_notes': f"Status: {status}, Time: {datetime.now().isoformat()}",
        
        # Column 54: Metrics (REQUIRED)
        'metrics': calculate_metrics(data),

        # Column 55: QA review status
        'qa_status': str(status),
    }


async def extract_conference(row_num: int, name: str, url: str) -> dict:
    """Extract data from a single conference website."""
    print(f"  [{row_num}] Extracting: {name[:50]}...")
    
    try:
        strategy = LLMExtractionStrategy(
            instruction=LLM_INSTRUCTION,
            schema=EXTRACTION_SCHEMA,
            extraction_type="schema"
        )
        
        config = CrawlerRunConfig(
            extraction_strategy=strategy,
            cache_mode=CacheMode.BYPASS,
            page_timeout=60000
        )
        
        async with AsyncWebCrawler() as crawler:
            result = await crawler.arun(url, config=config)
            
            if result.extracted_content:
                try:
                    data = json.loads(result.extracted_content)
                    if isinstance(data, list) and len(data) > 0:
                        data = data[0]
                    print(f"      ✓ Success: {data.get('conference_name', 'N/A')[:40]}...")
                    return {'row': row_num, 'name': name, 'url': url, 'data': data, 'status': 'success'}
                except Exception as e:
                    print(f"      ✗ Parse error: {str(e)[:50]}")
                    return {'row': row_num, 'name': name, 'url': url, 'data': {}, 'status': f'parse_error: {str(e)[:30]}'}
            else:
                print(f"      ✗ No content extracted")
                return {'row': row_num, 'name': name, 'url': url, 'data': {}, 'status': 'no_content'}
                
    except Exception as e:
        print(f"      ✗ Error: {str(e)[:50]}")
        return {'row': row_num, 'name': name, 'url': url, 'data': {}, 'status': f'error: {str(e)[:30]}'}


async def process_batch(input_file: str, output_prefix: str):
    """Main batch processing function."""
    
    print("="*70)
    print("PR FIRM TEXAS - BATCH PROCESSOR v1.0")
    print("="*70)
    print(f"Input:  {input_file}")
    print(f"Output: {output_prefix}")
    print("="*70)
    
    # Read input CSV
    conferences = []
    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for i, row in enumerate(reader, 1):
                url = row.get('CONFERENCE URL', row.get('conference_url', row.get('url', '')))
                name = row.get('CONFERENCE', row.get('conference_name', row.get('name', f'Conference {i}')))
                if url:
                    conferences.append({'row': i, 'name': name, 'url': url})
    except Exception as e:
        print(f"ERROR: Could not read input file: {e}")
        sys.exit(1)
    
    if not conferences:
        print("ERROR: No conferences found with URL column")
        print("Expected columns: 'CONFERENCE URL' or 'conference_url' or 'url'")
        sys.exit(1)
    
    print(f"\nFound {len(conferences)} conferences to process")
    registry_path = _source_registry_path_for_output(output_prefix)
    remembered_urls = _prefer_remembered_paths([c['url'] for c in conferences], registry_path)
    if remembered_urls and len(remembered_urls) != len(conferences):
        conferences = [
            {'row': i, 'name': f"Conference {i}", 'url': u}
            for i, u in enumerate(remembered_urls, 1)
        ]
        print(f"Path memory added known high-signal URLs; processing {len(conferences)} URLs")
    print("")
    
    # Extract all conferences
    results = []
    for conf in conferences:
        result = await extract_conference(conf['row'], conf['name'], conf['url'])
        results.append(result)
        await asyncio.sleep(2)  # Rate limiting
    
    # Build CSV rows
    print("\nBuilding 54-column output...")
    csv_rows = []
    for r in results:
        if r['status'] == 'success':
            row = build_csv_row(r['row'], r['url'], r['data'], r['status'])
            csv_rows.append(row)
        else:
            # Create empty row for failed extraction
            empty_data = {k: '' for k in EXTRACTION_SCHEMA.keys()}
            row = build_csv_row(r['row'], r['url'], empty_data, r['status'])
            csv_rows.append(row)
    
    # Write CSV
    csv_file = f"{output_prefix}_CONFERENCES_54COLUMNS.csv"
    with open(csv_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=COLUMN_SCHEMA)
        writer.writeheader()
        writer.writerows(csv_rows)
    print(f"✓ CSV saved: {csv_file} ({len(csv_rows)} rows, {len(COLUMN_SCHEMA)} columns)")
    
    # Write JSON results
    json_file = f"{output_prefix}_results.json"
    paths = {
        "output_csv": csv_file,
        "output_json": json_file,
        "output_report": f"{output_prefix}_EXECUTIVE_REPORT.txt",
    }
    source_registry_summary = _update_source_registry_from_csv_rows(csv_rows, output_prefix, paths)
    for r in results:
        r["source_registry_path"] = source_registry_summary.get("registry_path", "")
    with open(json_file, 'w') as f:
        json.dump({"results": results, "source_registry": source_registry_summary}, f, indent=2)
    print(f"✓ JSON saved: {json_file}")
    print(f"✓ Source registry updated: {source_registry_summary.get('registry_path', registry_path)} ({source_registry_summary.get('updated_sources', 0)} sources)")

    # Persist normalized opportunity snapshots and attach scan-to-scan diffs
    snapshot_path = _change_snapshot_path_for_output(output_prefix)
    change_summary = {"snapshot_path": str(snapshot_path), "ok": False, "action_worthy_changes": 0}
    change_rows = []
    if pr_change_detection is not None:
        try:
            change_rows = pr_change_detection.apply_change_detection(
                csv_rows,
                snapshot_path,
                run_id=Path(output_prefix).name,
            )
            change_by_url = {row.get("conf_page_url") or row.get("base_url"): row for row in change_rows}
            for r in results:
                meta = change_by_url.get(r.get("url")) or {}
                r["change_detection"] = {
                    "row_identity": meta.get("row_identity", ""),
                    "change_label": meta.get("change_label", ""),
                    "change_labels": meta.get("change_labels", []),
                    "change_diffs": meta.get("change_diffs", []),
                    "change_checked_at": meta.get("change_checked_at", ""),
                    "previous_snapshot_at": meta.get("previous_snapshot_at", ""),
                    "action_worthy": pr_change_detection.is_action_worthy(meta),
                }
            change_summary.update({
                "ok": True,
                "rows_checked": len(change_rows),
                "action_worthy_changes": sum(1 for row in change_rows if pr_change_detection.is_action_worthy(row)),
                "labels": sorted({label for row in change_rows for label in (row.get("change_labels") or [])}),
            })
            print(f"✓ Change snapshots updated: {snapshot_path} ({change_summary['action_worthy_changes']} action-worthy changes)")
        except Exception as e:
            change_summary["error"] = str(e)
            print(f"⚠ Change detection skipped: {e}")
    else:
        change_summary["error"] = "change_detection module unavailable"
        print("⚠ Change detection skipped: change_detection module unavailable")

    # Rewrite JSON results with change metadata included
    with open(json_file, 'w') as f:
        json.dump({"results": results, "source_registry": source_registry_summary, "change_detection": change_summary}, f, indent=2)

    # Generate report
    report = generate_report(results)
    report_file = f"{output_prefix}_EXECUTIVE_REPORT.txt"
    with open(report_file, 'w') as f:
        f.write(report)
    print(f"✓ Report saved: {report_file}")
    
    # Summary
    success_count = sum(1 for r in results if r['status'] == 'success')
    print("\n" + "="*70)
    print("BATCH COMPLETE")
    print("="*70)
    print(f"Total:      {len(results)}")
    print(f"Success:    {success_count}")
    print(f"Failed:     {len(results) - success_count}")
    print(f"Files:      3 generated")
    print("="*70)
    
    return csv_file, report_file


def generate_report(results: list) -> str:
    """Generate executive intelligence report."""
    
    # Categorize by tier
    tier1, tier2, tier3, tier4 = [], [], [], []
    
    for r in results:
        if r['status'] == 'success':
            dates = r['data'].get('conference_dates', '')
            tier = determine_tier(dates)
            if tier == '1':
                tier1.append(r)
            elif tier == '2':
                tier2.append(r)
            elif tier == '3':
                tier3.append(r)
            else:
                tier4.append(r)
        else:
            tier4.append(r)
    
    date_str = datetime.now().strftime("%B %d, %Y")
    
    report = f"""CONFERENCE INTELLIGENCE REPORT
{len(results)} Targets Analyzed | {date_str} | Date-Validated Triage

═══════════════════════════════════════════════════════════════════
EXECUTIVE SUMMARY
═══════════════════════════════════════════════════════════════════

TIER 1 (2026 Confirmed):     {len(tier1)} conferences
TIER 2 (Likely 2026):        {len(tier2)} conferences  
TIER 3 (Likely Past):        {len(tier3)} conferences
TIER 4 (Uncertain):          {len(tier4)} conferences

"""
    
    if tier1:
        report += "═══════════════════════════════════════════════════════════════════\n"
        report += "TIER 1: 2026 CONFIRMED\n"
        report += "═══════════════════════════════════════════════════════════════════\n\n"
        for r in tier1:
            d = r['data']
            if pr_deadline_intelligence is not None:
                d = pr_deadline_intelligence.enrich_row(d)
            report += f"{d.get('conference_name', 'N/A')} (Row {r['row']})\n"
            report += f"  Dates: {d.get('conference_dates', 'N/A')} | {d.get('conference_location', 'N/A')}\n"
            report += f"  Website: {r['url']}\n"
            report += f"  CFP URL: {d.get('cfp_link', 'Not found')}\n"
            report += f"  Contact URL: {r['url']}\n"
            report += f"  Contact: {d.get('contact_name', 'N/A')} / {d.get('contact_email', 'N/A')}\n"
            report += f"  CFP Status: {d.get('cfp_status', 'Unknown')}\n"
            report += f"  Deadline: {d.get('cfp_deadline', 'N/A')} | Normalized: {d.get('cfp_deadline_normalized', 'unknown')} | Urgency: {d.get('deadline_urgency', 'unknown')} | Action: {d.get('action_state', 'unknown')}\n\n"
    
    if tier2:
        report += "═══════════════════════════════════════════════════════════════════\n"
        report += "TIER 2: LIKELY 2026\n"
        report += "═══════════════════════════════════════════════════════════════════\n\n"
        for r in tier2:
            d = r['data']
            if pr_deadline_intelligence is not None:
                d = pr_deadline_intelligence.enrich_row(d)
            report += f"{d.get('conference_name', 'N/A')} (Row {r['row']})\n"
            report += f"  Dates: {d.get('conference_dates', 'N/A')} | {d.get('conference_location', 'N/A')}\n"
            report += f"  Website: {r['url']}\n"
            report += f"  2026 Status: Not announced\n\n"
    
    report += "═══════════════════════════════════════════════════════════════════\n"
    report += "KEY CONTACTS AND DATES\n"
    report += "═══════════════════════════════════════════════════════════════════\n\n"
    
    for i, r in enumerate(tier1 + tier2, 1):
        d = r['data']
        if pr_deadline_intelligence is not None:
            d = pr_deadline_intelligence.enrich_row(d)
        report += f"{i}. {d.get('conference_name', 'N/A')} - {d.get('conference_dates', 'N/A')} (Row {r['row']})\n"
        report += f"   Website: {r['url']}\n"
        if d.get('contact_name') and d.get('contact_name') != 'N/A':
            report += f"   Contact: {d.get('contact_name')} / {d.get('contact_email', 'N/A')}\n"
        if d.get('cfp_link') and d.get('cfp_link') != 'N/A':
            report += f"   CFP URL: {d.get('cfp_link')}\n"
        report += f"   CFP Status: {d.get('cfp_status', 'Unknown')}\n"
        report += f"   Deadline: {d.get('cfp_deadline', 'N/A')} | Normalized: {d.get('cfp_deadline_normalized', 'unknown')} | Urgency: {d.get('deadline_urgency', 'unknown')} | Action: {d.get('action_state', 'unknown')}\n\n"
    
    action_changes = [
        r for r in results
        if r.get('change_detection', {}).get('action_worthy')
    ]
    report += "═══════════════════════════════════════════════════════════════════\n"
    report += "ACTION-WORTHY SCAN CHANGES\n"
    report += "═══════════════════════════════════════════════════════════════════\n\n"
    if action_changes:
        for r in action_changes:
            d = r.get('data') or {}
            cd = r.get('change_detection') or {}
            report += f"{d.get('conference_name') or r.get('name') or 'N/A'} (Row {r.get('row')})\n"
            report += f"  Change: {', '.join(cd.get('change_labels') or [cd.get('change_label', '')])}\n"
            report += f"  Website: {r.get('url')}\n"
            for diff in cd.get('change_diffs') or []:
                report += f"  - {diff.get('field')}: {diff.get('previous')} → {diff.get('current')} @ {diff.get('changed_at')}\n"
            report += "\n"
    else:
        report += "No action-worthy scan changes; rows are new baselines or no_material_change.\n\n"

    return report


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='PR Firm Texas - Batch Conference Processor')
    parser.add_argument('--input', '-i', required=True, help='Input CSV file path')
    parser.add_argument('--output', '-o', required=True, help='Output file prefix')
    
    args = parser.parse_args()
    
    asyncio.run(process_batch(args.input, args.output))
