#!/usr/bin/env python3
"""
AI Digital Agents Dashboard
Full operational dashboard with Airtable and Gmail integrations
"""

import os
import json
import asyncio
import sqlite3
import requests
import csv
import base64
import subprocess
import time
import logging
import traceback

logger = logging.getLogger(__name__)
import stripe
from datetime import datetime, timedelta, timezone
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from pathlib import Path
from typing import Dict, Any, Optional, List
from uuid import uuid4
from zoneinfo import ZoneInfo
import hashlib
import threading
import re
import secrets
from html import escape
from urllib.parse import urlsplit, urlunsplit, unquote, parse_qs

# Import the user state classifier
from user_state_classifier import (
    UserState, InterventionType, 
    compute_user_state, get_intervention_type,
    enrich_companion_context
)

# Access logger for /api/* endpoints
api_access_log = logging.getLogger("api_access")
api_access_log.setLevel(logging.INFO)
logger = logging.getLogger("dashboard")
logger.setLevel(logging.INFO)

from fastapi import FastAPI, Request, Form, HTTPException, Query, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, Response, FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from pr_monitor_settings import get_pr_monitor_settings

# Import integrations
from integrations.airtable import fetch_airtable_data
from integrations.gmail import fetch_gmail_summary
from integrations.metrics import calculate_performance_metrics, generate_notifications
from integrations.strategic_metrics import calculate_all_strategic_metrics

# Load environment variables
load_dotenv()
# Load optional secure root-level credentials only when this process can read them.
# Worker/smoke-test users may not have access to ubuntu-owned 0600 files.
for _cred_path in (
    '/home/ubuntu/.openclaw/.stripe_credentials',
    '/home/ubuntu/.openclaw/.anthropic_credentials',
):
    if os.path.isfile(_cred_path) and os.access(_cred_path, os.R_OK):
        load_dotenv(_cred_path, override=False)

# Configuration
ENABLE_IP_RESTRICTION = os.getenv("ENABLE_IP_RESTRICTION", "false").lower() == "true"
ALLOWED_IPS = [ip.strip() for ip in os.getenv("ALLOWED_IPS", "127.0.0.1,::1").split(",")]
DASHBOARD_PASSWORD = os.getenv("DASHBOARD_PASSWORD", "demo123")
PORT = int(os.getenv("PORT", "8080"))
APP_HOST = os.getenv("APP_HOST", "127.0.0.1")

app = FastAPI(title="AI Digital Agents Dashboard")


# PR Monitor async job state (process-local)
PR_MONITOR_JOBS: Dict[str, Dict[str, Any]] = {}
PR_MONITOR_JOBS_LOCK = threading.Lock()

# PR Monitor local desktop browser fallback artifacts.
# Stores runner uploads as a separate evidence layer; never writes to customer source docs.
PR_MONITOR_PROJECT_ROOT = Path("/home/ubuntu/.openclaw/workspace/projects/PR_Firm_Texas/pr_monitor_1")
PR_MONITOR_LOCAL_BROWSER_ROOT = PR_MONITOR_PROJECT_ROOT / "local_browser_fallback"
PR_MONITOR_LOCAL_BROWSER_UPLOAD_TOKENS = PR_MONITOR_LOCAL_BROWSER_ROOT / "upload_tokens"
PR_MONITOR_LOCAL_BROWSER_UPLOADS = PR_MONITOR_LOCAL_BROWSER_ROOT / "uploads"


def _pr_job_set(job_id: str, patch: Dict[str, Any]) -> None:
    with PR_MONITOR_JOBS_LOCK:
        cur = PR_MONITOR_JOBS.get(job_id, {})
        cur.update(patch)
        PR_MONITOR_JOBS[job_id] = cur


def _pr_job_get(job_id: str) -> Optional[Dict[str, Any]]:
    with PR_MONITOR_JOBS_LOCK:
        row = PR_MONITOR_JOBS.get(job_id)
        if not row:
            return None
        return dict(row)


def _reject_json_for_form_endpoint(request: Request) -> None:
    content_type = (request.headers.get("content-type") or "").split(";", 1)[0].strip().lower()
    if content_type == "application/json":
        raise HTTPException(
            status_code=415,
            detail="This endpoint expects form data; use application/x-www-form-urlencoded or multipart/form-data fields per the PR Monitor 1 endpoint contract.",
        )

CARD_SHARE_BASE_URL = os.getenv("CARD_SHARE_BASE_URL", "https://discovermysuperpower.com")
CARD_ASSESSMENT_CTA_URL = os.getenv("CARD_ASSESSMENT_CTA_URL", "https://discovermysuperpower.com")


def _slugify_alnum(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (value or "").lower())


def _build_card_slug(name: str) -> str:
    parts = [p for p in re.split(r"\s+", (name or "").strip()) if p]
    if parts:
        first = _slugify_alnum(parts[0])
        last = _slugify_alnum(parts[-1]) if len(parts) > 1 else ""
    else:
        first, last = "", ""
    base = f"{first}{last}" or "anon"
    ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    return f"{base}{ts}"


def _store_card_slug_meta(slug: str, name: str) -> None:
    payload = {}
    if card_slug_meta_file.exists():
        try:
            payload = json.loads(card_slug_meta_file.read_text(encoding="utf-8"))
        except Exception:
            payload = {}
    payload[slug] = {
        "name": (name or "").strip(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    card_slug_meta_file.write_text(json.dumps(payload), encoding="utf-8")


def _get_card_slug_name(slug: str) -> str:
    if not card_slug_meta_file.exists():
        return ""
    try:
        payload = json.loads(card_slug_meta_file.read_text(encoding="utf-8"))
        return str((payload.get(slug) or {}).get("name") or "").strip()
    except Exception:
        return ""


# Create directories
templates_dir = Path(__file__).parent / "templates"
templates_dir.mkdir(exist_ok=True)
static_dir = Path(__file__).parent / "static"
static_dir.mkdir(exist_ok=True)
cards_static_dir = static_dir / "cards"
cards_static_dir.mkdir(parents=True, exist_ok=True)
card_slug_meta_file = Path(__file__).parent / "data" / "card_slug_meta.json"
card_slug_meta_file.parent.mkdir(parents=True, exist_ok=True)
integrations_dir = Path(__file__).parent / "integrations"
integrations_dir.mkdir(exist_ok=True)
assessments_dir = Path(__file__).parent / "data" / "assessments"
assessments_dir.mkdir(parents=True, exist_ok=True)
quick_signal_assessments_dir = Path(__file__).parent / "data" / "quick_signal_assessments"
quick_signal_assessments_dir.mkdir(parents=True, exist_ok=True)
identity_links_dir = Path(__file__).parent / "data" / "identity_links"
identity_links_dir.mkdir(parents=True, exist_ok=True)
quick_signal_link_file = identity_links_dir / "quick_signal_paid_links.jsonl"
caption_presets_dir = Path("/home/ubuntu/.openclaw/workspace/projects/ugc-video-pipeline/contracts/caption-presets")
caption_presets_dir.mkdir(parents=True, exist_ok=True)

# ========== Patterns DB (assessment + Loops sync) ==========
PATTERNS_DB_PATH = Path(os.environ.get("PATTERNS_DB_PATH", str(Path(__file__).parent / "patterns_paradigm.db")))

ARCHETYPE_MAP = {
    "architect": "Architect",
    "visionary": "Visionary",
    "navigator": "Navigator",
    "conductor": "Conductor",
    "catalyst": "Catalyst",
    "kinetic": "Kinetic",
    "sage": "Sage",
    "artisan": "Artisan",
}

COMPANION_BUNDLE_MARKER = "buy.stripe.com/dRmfZi8Wf8UW1kx2CC9R602"
COMPANION_MONTHLY_PRICE_ID = os.environ.get("COMPANION_MONTHLY_PRICE_ID", "")  # placeholder until set
COMPANION_CT_TZ = "America/Chicago"
COMPANION_SONNET_MODEL = "claude-sonnet-4-20250514"
COMPANION_HAIKU_MODEL = "claude-haiku-4-5-20251001"
COMPANION_FRAMEWORK_LOCK_BLOCK = (
    "Framework lock (mandatory): use CHANNELED Map -> Your Systems -> Action Plan in that order. "
    "Map identifies the wiring signal/pattern. Systems selects the method to run now. Action Plan commits one concrete next output. "
    "If user is stuck/overwhelmed/drifting, respond with exactly: 1) Map signal, 2) System to run now, 3) Next action under 20 minutes."
)

COMPANION_ARCHETYPE_INTEGRITY_BLOCK = (
    "Archetype integrity (mandatory): only reference the user's primary and secondary archetypes when naming wiring. "
    "Do not introduce tertiary archetypes or generic archetype substitutions."
)


# Weekly-plan schema lock: keep v1 day-level shape unless an intentional pivot is approved.
# v1 day keys: day, focus, action, wiring_note, reflection_prompt
COMPANION_WEEKLY_PLAN_SCHEMA_VERSION = "v1"
COMPANION_RENEWAL_EVENT_NAME = "companion_renewal_reminder"
COMPANION_RENEWAL_LOOKAHEAD_DAYS = 5
COMPANION_RENEWAL_INTERVAL_SECONDS = 60 * 60 * 24
COMPANION_COLD_START_MIN_FIELDS = 3

ARCHETYPE_DEFAULTS = {
    "Architect": {
        "secondary": "Navigator",
        "channeled_top": ["Compensate", "Align", "Develop"],
        "friction": ["Analysis loop — optimizing instead of shipping", "Alignment dependency — output drops without the right environment"],
    },
    "Navigator": {
        "secondary": "Architect",
        "channeled_top": ["Align", "Compensate", "Develop"],
        "friction": ["Direction drift — too many active targets", "Decision fatigue when priorities are not explicit"],
    },
    "Visionary": {
        "secondary": "Conductor",
        "channeled_top": ["Develop", "Align", "Compensate"],
        "friction": ["Idea surge without sequencing", "Execution drops when structure is unclear"],
    },
    "Conductor": {
        "secondary": "Visionary",
        "channeled_top": ["Align", "Develop", "Compensate"],
        "friction": ["Coordination overhead replaces output", "Momentum slows when ownership is diffuse"],
    },
    "Catalyst": {
        "secondary": "Kinetic",
        "channeled_top": ["Develop", "Compensate", "Align"],
        "friction": ["Starts fast but context-switches quickly", "Underscopes follow-through when constraints are vague"],
    },
    "Kinetic": {
        "secondary": "Catalyst",
        "channeled_top": ["Compensate", "Develop", "Align"],
        "friction": ["Speed outruns prioritization", "Consistency drops without clear daily targets"],
    },
    "Sage": {
        "secondary": "Architect",
        "channeled_top": ["Align", "Compensate", "Develop"],
        "friction": ["Reflection can delay decisive action", "Over-contextualizing before shipping"],
    },
    "Artisan": {
        "secondary": "Visionary",
        "channeled_top": ["Develop", "Align", "Compensate"],
        "friction": ["Quality tuning delays release", "Output dips when standards are undefined"],
    },
}


def _now_z() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _norm_archetype(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    key = str(value).strip().lower()
    return ARCHETYPE_MAP.get(key)


def _parse_badge_archetypes(badge_label: Optional[str]) -> list[str]:
    if not badge_label:
        return []
    cleaned = badge_label.replace("|", "/")
    out = []
    for part in cleaned.split("/"):
        arc = _norm_archetype(part)
        if arc and arc not in out:
            out.append(arc)
    return out


def resolve_archetypes(payload: Dict[str, Any]) -> Dict[str, Any]:
    confirmed_primary = _norm_archetype(payload.get("confirmed_primary"))
    badge_label = (payload.get("badge_label") or "").strip() or None

    reveal = payload.get("reveal_archetypes") or []
    reveal_archetypes = []
    if isinstance(reveal, list):
        for item in reveal:
            if isinstance(item, dict):
                arc = _norm_archetype(item.get("archetype"))
            else:
                arc = _norm_archetype(item)
            if arc and arc not in reveal_archetypes:
                reveal_archetypes.append(arc)

    badge_archetypes = _parse_badge_archetypes(badge_label)

    if confirmed_primary:
        secondary = None
        for cand in reveal_archetypes + badge_archetypes:
            if cand != confirmed_primary:
                secondary = cand
                break
        return {
            "primary_archetype": confirmed_primary,
            "secondary_archetype": secondary,
            "archetype_pair_label": badge_label,
            "confirmed_primary": confirmed_primary,
            "error": None,
        }

    if reveal_archetypes:
        primary = reveal_archetypes[0]
        secondary = reveal_archetypes[1] if len(reveal_archetypes) > 1 else None
        return {
            "primary_archetype": primary,
            "secondary_archetype": secondary,
            "archetype_pair_label": badge_label,
            "confirmed_primary": None,
            "error": None,
        }

    if badge_archetypes:
        primary = badge_archetypes[0]
        secondary = badge_archetypes[1] if len(badge_archetypes) > 1 else None
        return {
            "primary_archetype": primary,
            "secondary_archetype": secondary,
            "archetype_pair_label": badge_label,
            "confirmed_primary": None,
            "error": None,
        }

    return {
        "primary_archetype": None,
        "secondary_archetype": None,
        "archetype_pair_label": badge_label,
        "confirmed_primary": None,
        "error": "archetype_resolution_failed",
    }


def _patterns_conn():
    conn = sqlite3.connect(str(PATTERNS_DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_patterns_assessments_db():
    conn = _patterns_conn()
    try:
        conn.executescript('''
            CREATE TABLE IF NOT EXISTS assessments (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
                updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
                email TEXT NOT NULL,
                name TEXT,
                primary_archetype TEXT,
                secondary_archetype TEXT,
                archetype_pair_label TEXT,
                context TEXT,
                source_version TEXT,
                confirmed_primary TEXT,
                raw_payload_json TEXT NOT NULL,
                loops_status TEXT NOT NULL DEFAULT 'pending',
                loops_contact_id TEXT,
                last_error TEXT,
                retry_at TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_assessments_email_created ON assessments(email, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_assessments_primary_archetype ON assessments(primary_archetype, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_assessments_loops_status ON assessments(loops_status, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_assessments_retry_at ON assessments(retry_at);

            CREATE TABLE IF NOT EXISTS assessment_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                assessment_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                event_data_json TEXT,
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
                FOREIGN KEY (assessment_id) REFERENCES assessments(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_assessment_events_assessment_id ON assessment_events(assessment_id, created_at DESC);
        ''')
        conn.commit()
    finally:
        conn.close()


def init_companion_tables():
    conn = _patterns_conn()
    try:
        conn.executescript('''
            CREATE TABLE IF NOT EXISTS companion_access (
                email TEXT PRIMARY KEY,
                bundle_lifetime INTEGER NOT NULL DEFAULT 0,
                subscription_price_id TEXT,
                subscription_status TEXT,
                subscription_current_period_end TEXT,
                source TEXT,
                updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
                stripe_customer_id TEXT,
                stripe_subscription_id TEXT,
                discount_code TEXT,
                discount_amount INTEGER,
                access_type TEXT,
                granted_at TEXT,
                expires_at TEXT,
                active INTEGER NOT NULL DEFAULT 0,
                assessment_email TEXT,
                notification_morning INTEGER NOT NULL DEFAULT 1,
                notification_midday INTEGER NOT NULL DEFAULT 1,
                notification_evening INTEGER NOT NULL DEFAULT 1,
                morning_checkin_time TEXT DEFAULT '07:00',
                midday_checkin_time TEXT DEFAULT '12:00',
                evening_checkin_time TEXT DEFAULT '20:00',
                quiet_hours_start TEXT DEFAULT '22:00',
                quiet_hours_end TEXT DEFAULT '07:00',
                onboarding_completed INTEGER NOT NULL DEFAULT 0,
                intake_completed INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS companion_weekly_plans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL,
                week_key TEXT NOT NULL,
                timezone TEXT NOT NULL DEFAULT 'America/Chicago',
                status TEXT NOT NULL,
                model TEXT,
                prompt_hash TEXT,
                plan_json TEXT,
                error TEXT,
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
                updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
                UNIQUE(email, week_key)
            );
            CREATE INDEX IF NOT EXISTS idx_companion_weekly_plans_email_week ON companion_weekly_plans(email, week_key);

            CREATE TABLE IF NOT EXISTS companion_weekly_continuity (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL,
                week_key TEXT NOT NULL,
                summary_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
                UNIQUE(email, week_key)
            );
            CREATE INDEX IF NOT EXISTS idx_companion_weekly_continuity_email_week ON companion_weekly_continuity(email, week_key);

            CREATE TABLE IF NOT EXISTS magic_tokens (
                token TEXT PRIMARY KEY,
                email TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
                used_at TEXT,
                expires_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_magic_tokens_email ON magic_tokens(email);
            CREATE INDEX IF NOT EXISTS idx_magic_tokens_expires_at ON magic_tokens(expires_at);

            CREATE TABLE IF NOT EXISTS daily_completions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL,
                task_date TEXT NOT NULL,
                task_index INTEGER NOT NULL,
                task_title TEXT,
                task_description TEXT,
                completed INTEGER NOT NULL DEFAULT 0,
                note TEXT,
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
                updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
                UNIQUE(email, task_date, task_index)
            );
            CREATE INDEX IF NOT EXISTS idx_daily_completions_email_date ON daily_completions(email, task_date);

            CREATE TABLE IF NOT EXISTS companion_program_day_state (
                email TEXT PRIMARY KEY,
                current_day INTEGER NOT NULL DEFAULT 1,
                current_day_date TEXT,
                last_advanced_at TEXT,
                last_progression_date_ct TEXT,
                updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
            );

            CREATE TABLE IF NOT EXISTS companion_task_chats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL,
                task_date TEXT NOT NULL,
                task_index INTEGER NOT NULL,
                role TEXT NOT NULL,
                message TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
            );
            CREATE INDEX IF NOT EXISTS idx_companion_task_chats_lookup ON companion_task_chats(email, task_date, task_index, id);

            CREATE TABLE IF NOT EXISTS daily_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL,
                snapshot_date TEXT NOT NULL,
                day_number INTEGER,
                tasks_assigned TEXT,
                tasks_completed TEXT,
                task_notes TEXT,
                task_chat_history TEXT,
                evening_reflection_response TEXT,
                tomorrow_preview TEXT,
                free_note TEXT,
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
                updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
                UNIQUE(email, snapshot_date)
            );
            CREATE INDEX IF NOT EXISTS idx_daily_snapshots_email_day ON daily_snapshots(email, day_number DESC);
            CREATE INDEX IF NOT EXISTS idx_daily_snapshots_email_date ON daily_snapshots(email, snapshot_date DESC);

            CREATE TABLE IF NOT EXISTS companion_intake (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT,
                focus_area TEXT,
                tiles_active TEXT,
                tiles_priority TEXT,
                context_summary TEXT,
                friction_patterns TEXT,
                coaching_style_intensity TEXT,
                coaching_style_approach TEXT,
                spiritual_language_preference TEXT,
                scripture_integration_level TEXT,
                faith_boundaries TEXT,
                faith_boundaries_other TEXT,
                created_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
            );
            CREATE INDEX IF NOT EXISTS idx_companion_intake_email_id ON companion_intake(email, id DESC);

            CREATE TABLE IF NOT EXISTS companion_8q_link_state (
                email TEXT PRIMARY KEY,
                status TEXT NOT NULL DEFAULT 'unknown',
                free_8q_email TEXT,
                linked_at TEXT,
                last_prompt_date_ct TEXT,
                next_prompt_date_ct TEXT,
                updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
            );
            CREATE INDEX IF NOT EXISTS idx_companion_8q_link_state_status ON companion_8q_link_state(status, updated_at DESC);

            CREATE TABLE IF NOT EXISTS paid_canonical_8q (
                paid_email TEXT PRIMARY KEY,
                person_key TEXT NOT NULL,
                source_8q_email TEXT NOT NULL,
                source_8q_file TEXT,
                source_8q_saved_at TEXT,
                linked_at TEXT,
                promoted_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
                quick_signal_payload_json TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
            );
            CREATE INDEX IF NOT EXISTS idx_paid_canonical_8q_source_email ON paid_canonical_8q(source_8q_email, promoted_at DESC);

            CREATE TABLE IF NOT EXISTS paid_canonical_8q_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                paid_email TEXT NOT NULL,
                source_8q_email TEXT NOT NULL,
                source_8q_file TEXT,
                source_8q_saved_at TEXT,
                linked_at TEXT,
                promoted_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
                quick_signal_payload_json TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_paid_canonical_8q_history_paid_email ON paid_canonical_8q_history(paid_email, promoted_at DESC);

            CREATE TABLE IF NOT EXISTS companion_alert_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL,
                alert_key TEXT NOT NULL,
                alert_date_ct TEXT NOT NULL,
                details_json TEXT,
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
                UNIQUE(email, alert_key, alert_date_ct)
            );
            CREATE INDEX IF NOT EXISTS idx_companion_alert_log_email_key_date ON companion_alert_log(email, alert_key, alert_date_ct DESC);
            
            CREATE TABLE IF NOT EXISTS user_state_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL,
                date_ct TEXT NOT NULL, 
                user_state TEXT NOT NULL,
                intervention_type TEXT NOT NULL,
                metrics_json TEXT,
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
            );
            CREATE INDEX IF NOT EXISTS idx_user_state_history_email_date ON user_state_history(email, date_ct DESC);

            CREATE TABLE IF NOT EXISTS assessment_recovery_codes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL,
                code TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                used_at TEXT,
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
            );
            CREATE INDEX IF NOT EXISTS idx_assessment_recovery_codes_email_created ON assessment_recovery_codes(email, created_at DESC);

            CREATE TABLE IF NOT EXISTS assessment_recovery_tokens (
                token TEXT PRIMARY KEY,
                email TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                used_at TEXT,
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
            );
            CREATE INDEX IF NOT EXISTS idx_assessment_recovery_tokens_email_created ON assessment_recovery_tokens(email, created_at DESC);

            CREATE TABLE IF NOT EXISTS onboarding_conversation_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL,
                stage TEXT NOT NULL DEFAULT 'A',
                status TEXT NOT NULL DEFAULT 'in_progress',
                input_mode_last TEXT,
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
                updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
            );
            CREATE INDEX IF NOT EXISTS idx_onboarding_conv_sessions_email ON onboarding_conversation_sessions(email, id DESC);

            CREATE TABLE IF NOT EXISTS onboarding_slot_values (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL,
                email TEXT NOT NULL,
                slot_key TEXT NOT NULL,
                slot_value_json TEXT,
                confidence REAL,
                source TEXT,
                confirmed INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
                updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
            );
            CREATE INDEX IF NOT EXISTS idx_onboarding_slot_values_lookup ON onboarding_slot_values(email, session_id, slot_key);

            CREATE TABLE IF NOT EXISTS onboarding_followup_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL,
                email TEXT NOT NULL,
                slot_key TEXT NOT NULL,
                question_text TEXT NOT NULL,
                reason TEXT NOT NULL,
                asked_at TEXT,
                answered_at TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_onboarding_followup_queue_lookup ON onboarding_followup_queue(email, session_id, answered_at);
        ''')

        # Forward-compatible migration for existing databases
        cols = {row[1] for row in conn.execute("PRAGMA table_info(companion_access)").fetchall()}
        if "stripe_customer_id" not in cols:
            conn.execute("ALTER TABLE companion_access ADD COLUMN stripe_customer_id TEXT")
        if "stripe_subscription_id" not in cols:
            conn.execute("ALTER TABLE companion_access ADD COLUMN stripe_subscription_id TEXT")
        if "discount_code" not in cols:
            conn.execute("ALTER TABLE companion_access ADD COLUMN discount_code TEXT")
        if "discount_amount" not in cols:
            conn.execute("ALTER TABLE companion_access ADD COLUMN discount_amount INTEGER")
        if "access_type" not in cols:
            conn.execute("ALTER TABLE companion_access ADD COLUMN access_type TEXT")
        if "granted_at" not in cols:
            conn.execute("ALTER TABLE companion_access ADD COLUMN granted_at TEXT")
        if "expires_at" not in cols:
            conn.execute("ALTER TABLE companion_access ADD COLUMN expires_at TEXT")
        if "active" not in cols:
            conn.execute("ALTER TABLE companion_access ADD COLUMN active INTEGER NOT NULL DEFAULT 0")
        if "assessment_email" not in cols:
            conn.execute("ALTER TABLE companion_access ADD COLUMN assessment_email TEXT")
        if "notification_morning" not in cols:
            conn.execute("ALTER TABLE companion_access ADD COLUMN notification_morning INTEGER NOT NULL DEFAULT 1")
        if "notification_midday" not in cols:
            conn.execute("ALTER TABLE companion_access ADD COLUMN notification_midday INTEGER NOT NULL DEFAULT 1")
        if "notification_evening" not in cols:
            conn.execute("ALTER TABLE companion_access ADD COLUMN notification_evening INTEGER NOT NULL DEFAULT 1")
        if "morning_checkin_time" not in cols:
            conn.execute("ALTER TABLE companion_access ADD COLUMN morning_checkin_time TEXT DEFAULT '07:00'")
        if "midday_checkin_time" not in cols:
            conn.execute("ALTER TABLE companion_access ADD COLUMN midday_checkin_time TEXT DEFAULT '12:00'")
        if "evening_checkin_time" not in cols:
            conn.execute("ALTER TABLE companion_access ADD COLUMN evening_checkin_time TEXT DEFAULT '20:00'")
        if "quiet_hours_start" not in cols:
            conn.execute("ALTER TABLE companion_access ADD COLUMN quiet_hours_start TEXT DEFAULT '22:00'")
        if "quiet_hours_end" not in cols:
            conn.execute("ALTER TABLE companion_access ADD COLUMN quiet_hours_end TEXT DEFAULT '07:00'")
        if "onboarding_completed" not in cols:
            conn.execute("ALTER TABLE companion_access ADD COLUMN onboarding_completed INTEGER DEFAULT 0")
        if "intake_completed" not in cols:
            conn.execute("ALTER TABLE companion_access ADD COLUMN intake_completed INTEGER DEFAULT 0")
        if "day_cutoff_time" not in cols:
            conn.execute("ALTER TABLE companion_access ADD COLUMN day_cutoff_time TEXT DEFAULT '00:00'")
        if "onboarding_version" not in cols:
            conn.execute("ALTER TABLE companion_access ADD COLUMN onboarding_version TEXT")
        if "context_confidence_tier" not in cols:
            conn.execute("ALTER TABLE companion_access ADD COLUMN context_confidence_tier INTEGER DEFAULT 1")
        if "spiritual_language_preference" not in cols:
            conn.execute("ALTER TABLE companion_access ADD COLUMN spiritual_language_preference TEXT")
        if "scripture_integration_level" not in cols:
            conn.execute("ALTER TABLE companion_access ADD COLUMN scripture_integration_level TEXT")
        if "faith_boundaries" not in cols:
            conn.execute("ALTER TABLE companion_access ADD COLUMN faith_boundaries TEXT")

        weekly_cols = {row[1] for row in conn.execute("PRAGMA table_info(companion_weekly_plans)").fetchall()}
        if "week_start" not in weekly_cols:
            conn.execute("ALTER TABLE companion_weekly_plans ADD COLUMN week_start TEXT")
        if "archetype" not in weekly_cols:
            conn.execute("ALTER TABLE companion_weekly_plans ADD COLUMN archetype TEXT")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_companion_weekly_plans_email_weekstart ON companion_weekly_plans(email, week_start)")

        conn.commit()
    finally:
        conn.close()






def _cold_start_intake_gate(intake_row) -> Dict[str, Any]:
    if not intake_row:
        return {"pass": False, "score": 0, "missing": ["focus_area", "context_summary", "friction_patterns"]}
    focus = str(intake_row["focus_area"] or "").strip()
    context = str(intake_row["context_summary"] or "").strip()
    friction = str(intake_row["friction_patterns"] or "").strip()
    style_i = str(intake_row["coaching_style_intensity"] or "").strip()
    style_a = str(intake_row["coaching_style_approach"] or "").strip()

    present = {
        "focus_area": bool(focus),
        "context_summary": bool(context),
        "friction_patterns": bool(friction),
        "coaching_style_intensity": bool(style_i),
        "coaching_style_approach": bool(style_a),
    }
    score = sum(1 for v in present.values() if v)
    missing = [k for k,v in present.items() if not v]
    return {"pass": score >= COMPANION_COLD_START_MIN_FIELDS, "score": score, "missing": missing}

def _build_prior_week_continuity(conn, email: str, ct_now: datetime) -> Dict[str, Any]:
    start_7 = (ct_now - timedelta(days=13)).strftime("%Y-%m-%d")
    end_7 = (ct_now - timedelta(days=7)).strftime("%Y-%m-%d")
    rows = conn.execute(
        """
        SELECT task_title, completed, note
        FROM daily_completions
        WHERE lower(email)=lower(?) AND task_date >= ? AND task_date <= ?
        ORDER BY task_date ASC, task_index ASC
        """,
        (email, start_7, end_7),
    ).fetchall()
    total = len(rows)
    completed = sum(1 for r in rows if int(r["completed"] or 0) == 1)
    skipped = [str(r["task_title"] or "(untitled)") for r in rows if int(r["completed"] or 0) != 1]
    notes = [str(r["note"] or "").strip() for r in rows if str(r["note"] or "").strip()]
    completion_rate = round((completed / total), 3) if total else 0.0
    continuity = {
        "period": {"start": start_7, "end": end_7},
        "total_tasks": total,
        "completed_tasks": completed,
        "completion_rate": completion_rate,
        "skipped_task_titles": skipped[:15],
        "note_themes": notes[:15],
    }
    return continuity

def _companion_week_key(now_utc: Optional[datetime] = None) -> str:
    now_utc = now_utc or datetime.now(timezone.utc)
    ct = now_utc.astimezone(ZoneInfo(COMPANION_CT_TZ))
    monday = ct - timedelta(days=ct.weekday())
    return monday.strftime("%Y-W%W")


def _plan_today_tasks(plan_obj: Any, ct_now: datetime) -> List[Dict[str, str]]:
    if not isinstance(plan_obj, dict):
        return []

    tasks = plan_obj.get("tasks")
    if isinstance(tasks, list):
        normalized = []
        for t in tasks[:3]:
            if not isinstance(t, dict):
                continue
            title = str(t.get("title") or t.get("task_title") or "").strip()
            description = str(t.get("description") or t.get("task_description") or "").strip()
            normalized.append({"title": title, "description": description})
        return normalized

    days = plan_obj.get("days")
    if isinstance(days, list):
        today_name = ct_now.strftime("%A").lower()
        for d in days:
            if not isinstance(d, dict):
                continue
            if str(d.get("day") or "").strip().lower() != today_name:
                continue

            day_tasks = d.get("tasks")
            if isinstance(day_tasks, list) and day_tasks:
                normalized = []
                for t in day_tasks[:3]:
                    if not isinstance(t, dict):
                        continue
                    title = str(t.get("title") or t.get("task_title") or "").strip()
                    description = str(t.get("description") or t.get("task_description") or "").strip()
                    normalized.append({"title": title, "description": description})
                if normalized:
                    return normalized

            title = str(d.get("focus") or "").strip()
            description = str(d.get("action") or "").strip()
            return [
                {"title": title, "description": description},
                {"title": "Focus 2", "description": str(d.get("action2") or d.get("action") or "").strip()},
                {"title": "Focus 3", "description": str(d.get("wiring_note") or "").strip()},
            ]

    return []


def _upsert_companion_access(email: str, bundle_lifetime: Optional[int] = None, subscription_price_id: Optional[str] = None,
                            subscription_status: Optional[str] = None, subscription_period_end: Optional[str] = None,
                            source: str = "system"):
    conn = _patterns_conn()
    try:
        existing = conn.execute("SELECT * FROM companion_access WHERE email = ?", (email.lower().strip(),)).fetchone()
        if existing is None:
            conn.execute(
                """INSERT INTO companion_access (email, bundle_lifetime, subscription_price_id, subscription_status, subscription_current_period_end, source, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    email.lower().strip(),
                    int(bundle_lifetime or 0),
                    subscription_price_id,
                    subscription_status,
                    subscription_period_end,
                    source,
                    _now_z(),
                ),
            )
        else:
            conn.execute(
                """UPDATE companion_access
                   SET bundle_lifetime = ?,
                       subscription_price_id = ?,
                       subscription_status = ?,
                       subscription_current_period_end = ?,
                       source = ?,
                       updated_at = ?
                   WHERE email = ?""",
                (
                    int(bundle_lifetime if bundle_lifetime is not None else existing["bundle_lifetime"]),
                    subscription_price_id if subscription_price_id is not None else existing["subscription_price_id"],
                    subscription_status if subscription_status is not None else existing["subscription_status"],
                    subscription_period_end if subscription_period_end is not None else existing["subscription_current_period_end"],
                    source,
                    _now_z(),
                    email.lower().strip(),
                ),
            )
        conn.commit()
    finally:
        conn.close()


def _get_companion_access(email: str) -> Optional[sqlite3.Row]:
    conn = _patterns_conn()
    try:
        return conn.execute("SELECT * FROM companion_access WHERE email = ?", (email.lower().strip(),)).fetchone()
    finally:
        conn.close()


def _companion_access_decision(email: str) -> tuple[bool, str, Optional[sqlite3.Row]]:
    row = _get_companion_access(email)
    if not row:
        return False, "no_purchase_record", None

    # New gate: active=1 AND expires_at > now (hard-block immediate on expiry/failure)
    active = int(row["active"] or 0) if "active" in row.keys() else 0
    expires_at = (row["expires_at"] or "").strip() if "expires_at" in row.keys() else ""
    if active != 1:
        return False, "inactive", row
    if not expires_at:
        return False, "missing_expiry", row
    if expires_at <= _now_z():
        return False, "expired", row

    return True, "active_not_expired", row


def generate_magic_link(email: str) -> str:
    normalized_email = (email or "").strip().lower()
    if not normalized_email:
        raise ValueError("email is required")

    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    expires_at = (now + timedelta(hours=72)).strftime('%Y-%m-%dT%H:%M:%SZ')
    now_z = now.strftime('%Y-%m-%dT%H:%M:%SZ')

    conn = _patterns_conn()
    try:
        conn.execute(
            """
            INSERT INTO magic_tokens (token, email, created_at, used_at, expires_at)
            VALUES (?, ?, ?, NULL, ?)
            """,
            (token, normalized_email, now_z, expires_at),
        )
        conn.commit()
    finally:
        conn.close()

    return f"https://channeled.org/access?token={token}"


def _infer_channeled_top(raw: Dict[str, Any], archetype: str) -> list[str]:
    candidates = []
    for key in ("channeled_top", "top_channeled_elements", "channeled_elements", "channeled_map_results", "channeled_map"):
        value = raw.get(key)
        if isinstance(value, list):
            for item in value:
                if isinstance(item, str):
                    candidates.append(item)
                elif isinstance(item, dict):
                    name = item.get("name") or item.get("element") or item.get("label")
                    if name:
                        candidates.append(str(name))
        elif isinstance(value, dict):
            sorted_items = sorted(value.items(), key=lambda kv: kv[1], reverse=True)
            candidates.extend([str(k) for k, _ in sorted_items])
    cleaned = []
    for c in candidates:
        label = str(c).strip().title()
        if label and label not in cleaned:
            cleaned.append(label)
    defaults = ARCHETYPE_DEFAULTS.get(archetype, ARCHETYPE_DEFAULTS["Architect"])["channeled_top"]
    return (cleaned[:3] if cleaned else defaults)[:3]


def _infer_friction(raw: Dict[str, Any], archetype: str) -> tuple[str, str]:
    points = raw.get("friction_points") or raw.get("friction") or raw.get("frictions")
    extracted = []
    if isinstance(points, list):
        for item in points:
            if isinstance(item, str) and item.strip():
                extracted.append(item.strip())
            elif isinstance(item, dict):
                txt = item.get("text") or item.get("label") or item.get("description")
                if txt:
                    extracted.append(str(txt).strip())
    defaults = ARCHETYPE_DEFAULTS.get(archetype, ARCHETYPE_DEFAULTS["Architect"])["friction"]
    f1 = extracted[0] if len(extracted) > 0 else defaults[0]
    f2 = extracted[1] if len(extracted) > 1 else defaults[1]
    return f1, f2


def _extract_archetypes_from_8q_payload(payload: Dict[str, Any]) -> tuple[Optional[str], Optional[str], Optional[str]]:
    if not isinstance(payload, dict):
        return None, None, None

    result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
    primary = (
        payload.get("primary_archetype")
        or payload.get("primary")
        or result.get("primary_archetype")
        or result.get("primary")
        or payload.get("archetype")
    )
    secondary = (
        payload.get("secondary_archetype")
        or payload.get("secondary")
        or result.get("secondary_archetype")
        or result.get("secondary")
    )
    context = payload.get("context") or result.get("context")

    p = _norm_archetype(str(primary)) if primary else None
    s = _norm_archetype(str(secondary)) if secondary else None
    c = str(context).strip().lower() if context else None
    if c not in {"personal", "work"}:
        c = None
    return p, s, c


def _resolve_user_context(email: str) -> Dict[str, Any]:
    """Canonical context resolver for Companion personalization precedence.

    Precedence: latest 24Q (paid email) -> latest 24Q (linked assessment_email)
    -> paid_canonical_8q (promoted free data) -> defaults.
    """
    q_email = str(email or "").strip().lower()
    default_name = (q_email.split("@")[0] if "@" in q_email else "Member").title()

    conn = _patterns_conn()
    try:
        access_row = conn.execute(
            "SELECT assessment_email FROM companion_access WHERE lower(email)=lower(?) LIMIT 1",
            (q_email,),
        ).fetchone()
        assessment_email = str(access_row["assessment_email"] or "").strip().lower() if access_row and "assessment_email" in access_row.keys() else ""

        user_row = conn.execute(
            "SELECT name FROM users WHERE lower(email)=lower(?) LIMIT 1",
            (q_email,),
        ).fetchone()

        assessment = conn.execute(
            """
            SELECT email, name, primary_archetype, secondary_archetype, context, raw_payload_json, created_at
            FROM assessments
            WHERE lower(email)=lower(?)
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (q_email,),
        ).fetchone()
        source = "assessment_paid_email" if assessment else None

        if not assessment and assessment_email:
            assessment = conn.execute(
                """
                SELECT email, name, primary_archetype, secondary_archetype, context, raw_payload_json, created_at
                FROM assessments
                WHERE lower(email)=lower(?)
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (assessment_email,),
            ).fetchone()
            if assessment:
                source = "assessment_linked_email"

        canonical_8q = conn.execute(
            """
            SELECT source_8q_email, quick_signal_payload_json, promoted_at
            FROM paid_canonical_8q
            WHERE lower(paid_email)=lower(?)
            LIMIT 1
            """,
            (q_email,),
        ).fetchone()
    finally:
        conn.close()

    raw = {}
    if assessment and assessment["raw_payload_json"]:
        try:
            raw = json.loads(assessment["raw_payload_json"] or "{}")
        except Exception:
            raw = {}

    archetype = None
    secondary = None
    context = None
    channeled_top = None
    friction_1 = None
    friction_2 = None
    source_email = None

    if assessment:
        archetype = assessment["primary_archetype"] or _norm_archetype((raw.get("primary_archetype") or raw.get("archetype") or "Architect"))
        defaults = ARCHETYPE_DEFAULTS.get(archetype or "Architect", ARCHETYPE_DEFAULTS["Architect"])
        secondary = assessment["secondary_archetype"] or raw.get("secondary_archetype") or defaults["secondary"]
        context = assessment["context"] or raw.get("context") or "personal"
        channeled_top = _infer_channeled_top(raw, archetype or "Architect")
        friction_1, friction_2 = _infer_friction(raw, archetype or "Architect")
        source_email = str(assessment["email"] or "").strip().lower()

    if not archetype and canonical_8q and canonical_8q["quick_signal_payload_json"]:
        try:
            q_payload = json.loads(canonical_8q["quick_signal_payload_json"] or "{}")
        except Exception:
            q_payload = {}
        p8, s8, c8 = _extract_archetypes_from_8q_payload(q_payload)
        if p8:
            archetype = p8
            defaults = ARCHETYPE_DEFAULTS.get(archetype, ARCHETYPE_DEFAULTS["Architect"])
            secondary = s8 or defaults["secondary"]
            context = c8 or "personal"
            channeled_top = defaults["channeled_top"]
            friction_1, friction_2 = defaults["friction"]
            source = source or "paid_canonical_8q"
            source_email = str(canonical_8q["source_8q_email"] or "").strip().lower()

    if not archetype:
        archetype = "Architect"
        defaults = ARCHETYPE_DEFAULTS[archetype]
        secondary = defaults["secondary"]
        context = "personal"
        channeled_top = defaults["channeled_top"]
        friction_1, friction_2 = defaults["friction"]
        source = source or "default"

    src = source or "default"
    return {
        "email": q_email,
        "name": (assessment["name"] if assessment and assessment["name"] else None) or (raw.get("name") if isinstance(raw, dict) else None) or (user_row["name"] if user_row and user_row["name"] else None) or default_name,
        "archetype": archetype,
        "secondary": secondary,
        "context": context,
        "channeled_top": channeled_top,
        "friction_1": friction_1,
        "friction_2": friction_2,
        "source": src,
        "source_email": source_email,
        "assessment_email": assessment_email or None,
        "using_24q_foundation": src in {"assessment_paid_email", "assessment_linked_email"},
    }


def _profile_for_email(email: str) -> Dict[str, Any]:
    resolved = _resolve_user_context(email)
    return {
        "name": resolved["name"],
        "archetype": resolved["archetype"],
        "secondary": resolved["secondary"],
        "context": resolved["context"],
        "channeled_top": resolved["channeled_top"],
        "friction_1": resolved["friction_1"],
        "friction_2": resolved["friction_2"],
    }


def _call_companion_llm(system_prompt: str, user_prompt: str, model: str, max_tokens: int = 600, 
                    context: Optional[Dict[str, Any]] = None) -> str:
    """
    Call Anthropic Claude API with enhanced state-aware prompting.
    
    Args:
        system_prompt: The system prompt to use
        user_prompt: The user prompt to send
        model: The Anthropic model to use
        max_tokens: Maximum tokens to generate
        context: Optional context with user_state and intervention_type
    
    Returns:
        The LLM response text
    """
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    retries = 3
    
    # Apply state-based prompt enhancement if context is provided
    enhanced_system_prompt = system_prompt
    if context and "user_state" in context and "intervention_type" in context:
        user_state = context["user_state"]
        intervention_type = context["intervention_type"]
        
        # Add state-aware guidance to system prompt
        state_guidance = _get_state_based_prompt_guidance(user_state, intervention_type)
        enhanced_system_prompt = f"{system_prompt}\n\n{state_guidance}"
        
        # Log the state-enhanced prompt usage
        logging.info(f"Using state-enhanced prompt: {user_state} → {intervention_type}")
    
    for attempt in range(1, retries + 1):
        try:
            if not anthropic_key:
                raise RuntimeError("No LLM key configured (ANTHROPIC_API_KEY)")

            resp = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": anthropic_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": model,
                    "max_tokens": max_tokens,
                    "system": enhanced_system_prompt,
                    "messages": [{"role": "user", "content": user_prompt}],
                },
                timeout=45,
            )
            resp.raise_for_status()
            data = resp.json()
            parts = data.get("content") or []
            if parts and isinstance(parts[0], dict) and parts[0].get("text"):
                return parts[0]["text"].strip()
            raise RuntimeError("Anthropic response missing text content")
        except Exception:
            if attempt >= retries:
                raise
            time.sleep(60)
    return ""

def _get_state_based_prompt_guidance(user_state: UserState, intervention_type: InterventionType) -> str:
    """
    Get state-specific prompt guidance for enhancing LLM prompts.
    
    Args:
        user_state: The user's current state
        intervention_type: The appropriate intervention type
    
    Returns:
        State-specific prompt guidance
    """
    guidance = {
        UserState.MOMENTUM: {
            "prompt": (
                "The user is in MOMENTUM state. They are completing tasks consistently and engaging positively. "
                "Use AMPLIFY intervention strategy: Recognize specific achievements, connect them to the user's archetype strengths, "
                "and suggest ways to build on this momentum. Keep energy high and forward-looking."
            )
        },
        UserState.FRICTION: {
            "prompt": (
                "The user is in FRICTION state. They're completing some tasks but encountering obstacles. "
                "Use UNBLOCK intervention strategy: Identify the specific friction point (often linked to their archetype pattern), "
                "acknowledge it without judgment, and offer 1-2 targeted techniques to address it."
            )
        },
        UserState.OVERWHELM: {
            "prompt": (
                "The user is in OVERWHELM state. They're struggling with completion despite being engaged. "
                "Use SIMPLIFY intervention strategy: Reduce cognitive load by breaking things down, limit options, "
                "offer a concrete next step that feels achievable, and use calming, supportive language."
            )
        },
        UserState.AVOIDANCE: {
            "prompt": (
                "The user is in AVOIDANCE state. They have low engagement and completion rates. "
                "Use RECONNECT intervention strategy: Lower the barrier to re-entry, offer a micro-win, "
                "use non-judgmental language, and focus on the concrete next step without reference to past misses."
            )
        },
        UserState.REENTRY: {
            "prompt": (
                "The user is in REENTRY state. They've returned after a period of absence. "
                "Use REBUILD intervention strategy: Welcome them back without focusing on the gap, "
                "offer a fresh start, provide a simple win to rebuild confidence, and reconnect them to their 'why'."
            )
        },
        UserState.UNKNOWN: {
            "prompt": (
                "The user's state is UNKNOWN due to limited data. "
                "Use a balanced approach that offers clear structure with specific actions "
                "while maintaining a warm, encouraging tone. Focus on concrete next steps."
            )
        }
    }
    
    return guidance.get(user_state, guidance[UserState.UNKNOWN])["prompt"]


def _generate_weekly_plan(profile: Dict[str, Any], model: str = COMPANION_SONNET_MODEL) -> Dict[str, Any]:
    system = "You are CHANNELED companion planner. Return strict JSON only."
    user_prompt = (
        f"Create a weekly plan for {profile['name']} ({profile['archetype']}/{profile['secondary']}, {profile['context']}). "
        f"Top elements: {', '.join(profile['channeled_top'])}. Frictions: {profile['friction_1']} | {profile['friction_2']}. "
        "Return JSON with keys: morning_actions (array of 3 concise actions), midday_prompt (string), evening_questions (array of 2 questions), wiring_note (string)."
    )
    text = _call_companion_llm(system, user_prompt, model=model, max_tokens=800)
    try:
        start = text.find("{")
        end = text.rfind("}")
        parsed = json.loads(text[start:end+1] if start != -1 and end != -1 else text)
    except Exception:
        parsed = {
            "morning_actions": [
                "Define the single deliverable you will ship before noon.",
                "Execute one focused 60-minute build block with no context switching.",
                "Publish or hand off the deliverable before opening new tasks.",
            ],
            "midday_prompt": "Are you executing the named deliverable or drifting into optimization?",
            "evening_questions": [
                "What did you ship today?",
                "What will you name as tomorrow's concrete deliverable?",
            ],
            "wiring_note": "Protect specificity: named outputs beat broad categories for your wiring.",
        }
    return {
        "morning_actions": (parsed.get("morning_actions") or [])[:3] or ARCHETYPE_DEFAULTS.get(profile["archetype"], ARCHETYPE_DEFAULTS["Architect"])["channeled_top"],
        "midday_prompt": parsed.get("midday_prompt") or "Stay with the concrete output, not the planning loop.",
        "evening_questions": (parsed.get("evening_questions") or ["What shipped today?", "What is tomorrow's first concrete output?"])[:2],
        "wiring_note": parsed.get("wiring_note") or "Protect specificity and ship before you optimize.",
    }


def add_assessment_event(conn, assessment_id: str, event_type: str, event_data: Optional[Dict[str, Any]] = None):
    conn.execute(
        "INSERT INTO assessment_events (assessment_id, event_type, event_data_json) VALUES (?, ?, ?)",
        (assessment_id, event_type, json.dumps(event_data or {})),
    )


def _failed_attempt_count(conn, assessment_id: str) -> int:
    row = conn.execute(
        "SELECT COUNT(*) AS c FROM assessment_events WHERE assessment_id = ? AND event_type = 'loops_failed'",
        (assessment_id,),
    ).fetchone()
    return int(row["c"] if row else 0)


def compute_retry_at(attempt_count: int) -> Optional[str]:
    if attempt_count <= 0:
        return None
    minutes = [5, 30, 120, 720]
    idx = min(attempt_count - 1, len(minutes) - 1)
    return (datetime.utcnow() + timedelta(minutes=minutes[idx])).isoformat() + "Z"


def loops_send_event(*, event_name: str, email: str, properties: Dict[str, Any], timeout_seconds: int = 10) -> Dict[str, Any]:
    loops_api_key = (os.getenv("LOOPS_API_KEY") or "").strip()
    loops_enabled = (os.getenv("LOOPS_ENABLED") or "true").lower() == "true"
    if not loops_enabled:
        return {"ok": False, "error": "loops_disabled"}
    if not loops_api_key:
        return {"ok": False, "error": "loops_not_configured"}

    headers = {
        "Authorization": f"Bearer {loops_api_key}",
        "Content-Type": "application/json",
    }

    try:
        resp = requests.post(
            "https://app.loops.so/api/v1/events/send",
            headers=headers,
            json={
                "eventName": event_name,
                "email": email,
                "properties": properties,
            },
            timeout=timeout_seconds,
        )
    except Exception as e:
        return {"ok": False, "error": f"loops_event_exception:{e}"}

    if resp.status_code >= 300:
        return {"ok": False, "error": f"loops_event_http_{resp.status_code}:{resp.text[:500]}"}

    return {"ok": True, "error": None}


def loops_send_transactional_email(to_email: str, magic_link: str = None, subject: str = None, html: str = None, timeout_seconds: int = 10, attachments: List[Dict[str, str]] = None) -> Dict[str, Any]:
    loops_api_key = (os.getenv("LOOPS_API_KEY") or "").strip()
    loops_enabled = (os.getenv("LOOPS_ENABLED") or "true").lower() == "true"
    if not loops_enabled:
        return {"ok": False, "error": "loops_disabled"}
    if not loops_api_key:
        return {"ok": False, "error": "loops_not_configured"}

    headers = {
        "Authorization": f"Bearer {loops_api_key}",
        "Content-Type": "application/json",
    }

    # Build the payload based on the parameters provided
    payload = {
        "transactionalId": "cmo4sf46s09og0i0im5fy7rbw",
        "email": to_email,
        "dataVariables": {},
    }
    
    # Add magic link if provided
    if magic_link:
        payload["dataVariables"]["magicLink"] = magic_link
        
    # Add subject if provided
    if subject:
        payload["subject"] = subject
        
    # Add html content if provided
    if html:
        payload["html"] = html
        
    # Add attachments if provided
    if attachments:
        payload["attachments"] = attachments

    try:
        resp = requests.post(
            "https://app.loops.so/api/v1/transactional",
            headers=headers,
            json=payload,
            timeout=timeout_seconds,
        )
    except Exception as e:
        return {"ok": False, "error": f"loops_transactional_exception:{e}"}

    body_preview = (resp.text or "")[:500]
    if resp.status_code >= 300:
        return {"ok": False, "error": f"loops_transactional_http_{resp.status_code}:{body_preview}"}

    return {"ok": True, "error": None, "status_code": resp.status_code, "body": body_preview}


def onesignal_send_push(title: str, message: str, url: Optional[str] = None, external_user_id: Optional[str] = None, timeout_seconds: int = 10) -> Dict[str, Any]:
    app_id = (os.getenv("ONESIGNAL_APP_ID") or "").strip()
    rest_key = (os.getenv("ONESIGNAL_REST_API_KEY") or "").strip()

    if not app_id or not rest_key:
        return {"ok": False, "error": "onesignal_not_configured"}

    headers = {
        "Authorization": f"Basic {rest_key}",
        "Content-Type": "application/json",
    }

    payload: Dict[str, Any] = {
        "app_id": app_id,
        "headings": {"en": str(title or "").strip() or "Notification"},
        "contents": {"en": str(message or "").strip() or ""},
    }

    if url:
        payload["url"] = url

    if external_user_id:
        payload["include_external_user_ids"] = [str(external_user_id).strip().lower()]
        payload["channel_for_external_user_ids"] = "push"
    else:
        payload["included_segments"] = ["All"]

    try:
        resp = requests.post(
            "https://onesignal.com/api/v1/notifications",
            headers=headers,
            json=payload,
            timeout=timeout_seconds,
        )
    except Exception as e:
        return {"ok": False, "error": f"onesignal_exception:{e}"}

    body_preview = (resp.text or "")[:2000]
    if resp.status_code >= 300:
        return {"ok": False, "status_code": resp.status_code, "error": f"onesignal_http_{resp.status_code}", "body": body_preview}

    return {"ok": True, "status_code": resp.status_code, "body": body_preview}


def _send_morning_nudge() -> Dict[str, Any]:
    job_name = "morning_nudge"
    logger.info("ONESIGNAL_PUSH_FIRING job=%s", job_name)
    print(f"ONESIGNAL_PUSH_FIRING job={job_name}")
    res = onesignal_send_push(
        title="Good morning.",
        message="Your focus items for today are ready.",
        url="https://channeled.org/companion",
        external_user_id=None,
        timeout_seconds=int(os.getenv("ONESIGNAL_TIMEOUT_SECONDS", "10")),
    )
    status = "success" if res.get("ok") else "fail"
    logger.info("ONESIGNAL_PUSH_RESULT job=%s status=%s response=%s", job_name, status, res)
    print(f"ONESIGNAL_PUSH_RESULT job={job_name} status={status} response={res}")
    return res


def _send_midday_nudge() -> Dict[str, Any]:
    job_name = "midday_nudge"
    logger.info("ONESIGNAL_PUSH_FIRING job=%s", job_name)
    print(f"ONESIGNAL_PUSH_FIRING job={job_name}")
    res = onesignal_send_push(
        title="Midday check-in.",
        message="How's your focus going today?",
        url="https://channeled.org/companion",
        external_user_id=None,
        timeout_seconds=int(os.getenv("ONESIGNAL_TIMEOUT_SECONDS", "10")),
    )
    status = "success" if res.get("ok") else "fail"
    logger.info("ONESIGNAL_PUSH_RESULT job=%s status=%s response=%s", job_name, status, res)
    print(f"ONESIGNAL_PUSH_RESULT job={job_name} status={status} response={res}")
    return res


def _send_evening_nudge() -> Dict[str, Any]:
    job_name = "evening_nudge"
    logger.info("ONESIGNAL_PUSH_FIRING job=%s", job_name)
    print(f"ONESIGNAL_PUSH_FIRING job={job_name}")
    res = onesignal_send_push(
        title="Evening reflection.",
        message="2 minutes to close the loop on today.",
        url="https://channeled.org/companion",
        external_user_id=None,
        timeout_seconds=int(os.getenv("ONESIGNAL_TIMEOUT_SECONDS", "10")),
    )
    status = "success" if res.get("ok") else "fail"
    logger.info("ONESIGNAL_PUSH_RESULT job=%s status=%s response=%s", job_name, status, res)
    print(f"ONESIGNAL_PUSH_RESULT job={job_name} status={status} response={res}")
    return res




def _recompute_week_continuity_for_week_key(conn, email: str, week_key: str) -> Dict[str, Any]:
    try:
        week_start_dt = datetime.strptime(f"{week_key}-1", "%Y-W%W-%w")
    except Exception:
        return {"period": {"start": "", "end": ""}, "total_tasks": 0, "completed_tasks": 0, "completion_rate": 0.0, "skipped_task_titles": [], "note_themes": []}

    start_s = week_start_dt.strftime("%Y-%m-%d")
    end_s = (week_start_dt + timedelta(days=6)).strftime("%Y-%m-%d")

    rows = conn.execute(
        """
        SELECT task_title, completed, note
        FROM daily_completions
        WHERE lower(email)=lower(?) AND task_date >= ? AND task_date <= ?
        ORDER BY task_date ASC, task_index ASC
        """,
        (email, start_s, end_s),
    ).fetchall()
    total = len(rows)
    completed = sum(1 for r in rows if int(r["completed"] or 0) == 1)
    skipped = [str(r["task_title"] or "(untitled)") for r in rows if int(r["completed"] or 0) != 1]
    notes = [str(r["note"] or "").strip() for r in rows if str(r["note"] or "").strip()]
    completion_rate = round((completed / total), 3) if total else 0.0
    return {
        "period": {"start": start_s, "end": end_s},
        "total_tasks": total,
        "completed_tasks": completed,
        "completion_rate": completion_rate,
        "skipped_task_titles": skipped[:15],
        "note_themes": notes[:15],
    }


def run_companion_weekly_continuity_reconcile() -> Dict[str, Any]:
    conn = _patterns_conn()
    corrected = 0
    scanned = 0
    errors = []
    try:
        rows = conn.execute(
            "SELECT DISTINCT email, week_key, summary_json FROM companion_weekly_continuity ORDER BY email, week_key"
        ).fetchall()
        alert_date_ct = datetime.now(ZoneInfo(COMPANION_CT_TZ)).strftime("%Y-%m-%d")
        for r in rows:
            scanned += 1
            email = str(r["email"] or "").strip().lower()
            week_key = str(r["week_key"] or "").strip()
            stored_raw = str(r["summary_json"] or "{}")
            try:
                stored = json.loads(stored_raw) if stored_raw else {}
            except Exception:
                stored = {}
            recomputed = _recompute_week_continuity_for_week_key(conn, email, week_key)
            if stored != recomputed:
                conn.execute(
                    "UPDATE companion_weekly_continuity SET summary_json = ?, created_at = ? WHERE lower(email)=lower(?) AND week_key = ?",
                    (json.dumps(recomputed), _now_z(), email, week_key),
                )
                diff = {
                    "stored": stored,
                    "recomputed": recomputed,
                }
                details = {
                    "reason": "nightly_continuity_reconcile_correction",
                    "week_key": week_key,
                    "diff": diff,
                }
                try:
                    conn.execute(
                        "INSERT INTO companion_alert_log (email, alert_key, alert_date_ct, details_json, created_at) VALUES (?, ?, ?, ?, ?)",
                        (email, f"continuity_corrected_{week_key}", alert_date_ct, json.dumps(details), _now_z()),
                    )
                except Exception:
                    pass
                corrected += 1
        conn.commit()
    except Exception as e:
        errors.append(str(e))
        conn.rollback()
    finally:
        conn.close()

    if corrected or errors:
        logger.info("continuity reconcile scanned=%s corrected=%s errors=%s", scanned, corrected, len(errors))
    return {"scanned": scanned, "corrected": corrected, "errors": errors}


def run_weekly_plan_generation() -> Dict[str, Any]:
    """Generate weekly plans for all active users who don't yet have a plan for the upcoming week.
    Runs Sunday evening to prepare plans for the week starting Monday.
    Only generates for users with: companion access, 24Q foundation linked, intake complete, recent activity."""
    conn = _patterns_conn()
    generated = 0
    skipped = 0
    errors = []
    try:
        now_ct = datetime.now(ZoneInfo(COMPANION_CT_TZ))
        # Next week's Monday
        days_to_next_monday = (7 - now_ct.weekday()) % 7
        if days_to_next_monday == 0:
            days_to_next_monday = 7  # If today is Monday, target next Monday
        next_monday = now_ct + timedelta(days=days_to_next_monday)
        next_week_start = next_monday.strftime("%Y-%m-%d")
        next_week_key = next_monday.strftime("%Y-W%W")

        # Find all users with companion access
        rows = conn.execute(
            "SELECT DISTINCT email FROM companion_access WHERE active = 1"
        ).fetchall()

        for r in rows:
            email = str(r["email"] or "").strip().lower()
            if not email:
                continue

            # Check if plan already exists for next week
            existing = conn.execute(
                "SELECT 1 FROM companion_weekly_plans WHERE lower(email)=lower(?) AND week_start = ? AND status = 'generated'",
                (email, next_week_start),
            ).fetchone()
            if existing:
                skipped += 1
                continue

            # Check 24Q foundation
            resolved = _resolve_user_context(email)
            if not bool(resolved.get("using_24q_foundation")):
                skipped += 1
                logger.info("weekly_plan_gen skip_no_24q email=%s", email)
                continue

            # Check intake gate
            intake_row = conn.execute(
                "SELECT * FROM companion_intake WHERE lower(email)=lower(?) ORDER BY id DESC LIMIT 1",
                (email,),
            ).fetchone()
            gate = _cold_start_intake_gate(intake_row)
            if not gate["pass"]:
                skipped += 1
                logger.info("weekly_plan_gen skip_intake email=%s score=%d", email, gate["score"])
                continue

            # Build profile and generate
            try:
                primary = resolved.get("archetype") or "Architect"
                secondary = resolved.get("secondary") or "Artisan"
                context = resolved.get("context") or "personal"
                display_name = resolved.get("name") or (email.split("@")[0].title() if "@" in email else "Member")

                profile = {
                    "name": display_name,
                    "archetype": primary,
                    "secondary": secondary,
                    "context": context,
                    "channeled_top": ARCHETYPE_DEFAULTS.get(primary, ARCHETYPE_DEFAULTS["Architect"])["channeled_top"],
                    "friction_1": "",
                    "friction_2": "",
                }

                # Get prior week continuity
                prior_week_continuity = _build_prior_week_continuity(conn, email, now_ct)

                # Build full prompt (same as companion_weekly_plan endpoint)
                intake_focus_area = str(intake_row["focus_area"] or "").strip() if intake_row else ""
                intake_context_summary = str(intake_row["context_summary"] or "").strip() if intake_row else ""

                json_structure_hint = (
                    "Return ONLY valid JSON with this structure: theme (string), days (array of 7 objects). "
                    "Each day: day (string), focus (string), action (string), wiring_note (string), reflection_prompt (string), tasks (array of 3 objects with title and description). "
                    "No preamble, no markdown, only the JSON object."
                )
                system_prompt = (
                    "You are the CHANNELED Implementation Companion. Generate a focused 7-day action plan for the user. "
                    + COMPANION_FRAMEWORK_LOCK_BLOCK + " "
                    + COMPANION_ARCHETYPE_INTEGRITY_BLOCK + " "
                    + "Profile anchors: primary archetype=" + primary + "; secondary archetype=" + secondary + "; context=" + context + ". "
                    + "Intake anchors (use when provided): focus_area=" + (intake_focus_area or 'none') + "; context_summary=" + (intake_context_summary or 'none') + "; "
                    + "Priority rules (follow in order): "
                    + "1) The intake context is the primary driver of plan content. "
                    + "2) The archetype informs style and framing, not subject matter. "
                    + "3) Tasks must be completable in under 20 minutes with a single concrete output. "
                    + "4) Each task must pass the specificity test. "
                    + "5) The user's secondary archetype is " + secondary + " — never reference any other archetype. "
                    + json_structure_hint
                )

                anthropic_key = (os.environ.get("ANTHROPIC_API_KEY") or "").strip()
                if anthropic_key:
                    resp = requests.post(
                        "https://api.anthropic.com/v1/messages",
                        headers={
                            "x-api-key": anthropic_key,
                            "anthropic-version": "2023-06-01",
                            "content-type": "application/json",
                        },
                        json={
                            "model": "claude-sonnet-4-20250514",
                            "max_tokens": 1500,
                            "system": system_prompt,
                            "messages": [{"role": "user", "content": "Name: " + display_name + "\nPrimary: " + primary + "\nSecondary: " + secondary + "\nContext: " + context + "\nFocus: " + intake_focus_area + "\nPrior week: " + json.dumps(prior_week_continuity)}],
                        },
                        timeout=60,
                    )
                    resp.raise_for_status()
                    raw_text = ((resp.json().get("content") or [{}])[0].get("text") or "").strip()
                else:
                    raw_text = _call_companion_llm(system_prompt, f"Name: {display_name} Primary: {primary} Secondary: {secondary}", model="claude-sonnet-4-20250514", max_tokens=1500)

                start = raw_text.find("{")
                end = raw_text.rfind("}")
                plan_obj = json.loads(raw_text[start:end+1] if start != -1 and end != -1 else raw_text)

                if not isinstance(plan_obj, dict) or "days" not in plan_obj:
                    raise ValueError("Invalid plan JSON shape")

                # Normalize days (same logic as companion_weekly_plan endpoint)
                normalized_days = []
                for d in plan_obj.get("days", []):
                    if not isinstance(d, dict):
                        continue
                    reflection_prompts = [
                        "What's your one sentence for done?",
                        "What was the deliverable you named?",
                        "What system — and use it or improve it?",
                    ]
                    tasks_raw = d.get("tasks") if isinstance(d.get("tasks"), list) else []
                    tasks = []
                    for t in tasks_raw[:3]:
                        if not isinstance(t, dict):
                            continue
                        t_title = str(t.get("title") or "").strip()
                        t_desc = str(t.get("description") or "").strip()
                        if t_title or t_desc:
                            tasks.append({"title": t_title, "description": t_desc})
                    if not tasks:
                        tasks = [
                            {"title": str(d.get("focus") or "").strip(), "description": str(d.get("action") or "").strip()},
                            {"title": "Focus 2", "description": str(d.get("action") or "").strip()},
                            {"title": "Focus 3", "description": str(d.get("wiring_note") or "").strip()},
                        ]
                    normalized_days.append({
                        "day": str(d.get("day") or "").strip(),
                        "focus": str(d.get("focus") or "").strip(),
                        "action": str(d.get("action") or "").strip(),
                        "wiring_note": str(d.get("wiring_note") or "").strip(),
                        "reflection_prompt": str(d.get("reflection_prompt") or "").strip(),
                        "reflection_prompts": reflection_prompts,
                        "tasks": tasks,
                    })
                plan_obj["days"] = normalized_days

                conn.execute(
                    """
                    INSERT INTO companion_weekly_plans (email, week_key, week_start, timezone, status, model, archetype, plan_json, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(email, week_key) DO UPDATE SET
                        week_start=excluded.week_start,
                        status=excluded.status,
                        model=excluded.model,
                        archetype=excluded.archetype,
                        plan_json=excluded.plan_json,
                        updated_at=excluded.updated_at
                    """,
                    (
                        email, next_week_key, next_week_start, COMPANION_CT_TZ,
                        "generated", "claude-sonnet-4-20250514", primary,
                        json.dumps(plan_obj), _now_z(), _now_z(),
                    ),
                )
                conn.commit()
                generated += 1
                logger.info("weekly_plan_gen success email=%s week=%s", email, next_week_start)

            except Exception as e:
                errors.append(f"{email}: {str(e)}")
                logger.exception("weekly_plan_gen error email=%s", email)
                try:
                    conn.execute(
                        "INSERT INTO companion_weekly_plans (email, week_key, week_start, timezone, status, model, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (email, next_week_key, next_week_start, COMPANION_CT_TZ, "failed", "claude-sonnet-4-20250514", _now_z(), _now_z()),
                    )
                    conn.commit()
                except Exception:
                    pass

    except Exception as e:
        errors.append(str(e))
        conn.rollback()
        logger.exception("weekly_plan_generation top-level error: %s", e)
    finally:
        conn.close()

    logger.info("weekly_plan_generation week=%s generated=%s skipped=%s errors=%s",
                next_week_start, generated, skipped, len(errors))
    return {"week_start": next_week_start, "generated": generated, "skipped": skipped, "errors": errors}


def run_daily_program_day_advancement() -> Dict[str, Any]:
    """Advance program_day by 1 for all active users whose last progression was before today (CT).
    Skips users who have been inactive for more than 7 days (no daily_completions in last 7 days).
    Only advances if a weekly_plan exists for the current week."""
    conn = _patterns_conn()
    advanced = 0
    skipped_no_plan = 0
    skipped_inactive = 0
    scanned = 0
    errors = []
    try:
        now_ct = datetime.now(ZoneInfo(COMPANION_CT_TZ))
        today_ct_str = now_ct.strftime("%Y-%m-%d")
        # Current week Monday (week_start format: YYYY-MM-DD of the Monday that starts the week)
        days_to_monday = now_ct.weekday()  # Monday=0
        current_week_start = (now_ct - timedelta(days=days_to_monday)).strftime("%Y-%m-%d")
        week_7_days_ago = (now_ct - timedelta(days=7)).strftime("%Y-%m-%d")

        rows = conn.execute(
            "SELECT email, current_day, last_progression_date_ct FROM companion_program_day_state"
        ).fetchall()

        for r in rows:
            scanned += 1
            email = str(r["email"] or "").strip().lower()
            current_day = int(r["current_day"] or 1)
            last_prog = str(r["last_progression_date_ct"] or "").strip()

            # Skip if already advanced today
            if last_prog >= today_ct_str:
                continue

            # Check for recent activity (any completion in last 7 days)
            activity = conn.execute(
                "SELECT COUNT(*) as c FROM daily_completions WHERE lower(email)=lower(?) AND task_date >= ?",
                (email, week_7_days_ago),
            ).fetchone()
            if not activity or int(activity["c"] or 0) == 0:
                skipped_inactive += 1
                logger.info("program_day_advance skip_inactive email=%s last_prog=%s", email, last_prog)
                continue

            # Check that a weekly plan exists for the current week (match on week_start for consistency)
            plan = conn.execute(
                "SELECT 1 FROM companion_weekly_plans WHERE lower(email)=lower(?) AND week_start = ? AND status = 'generated'",
                (email, current_week_start),
            ).fetchone()
            if not plan:
                skipped_no_plan += 1
                logger.info("program_day_advance skip_no_plan email=%s week_start=%s", email, current_week_start)
                # Log alert so we know a plan is missing
                try:
                    details = json.dumps({
                        "reason": "missing_weekly_plan",
                        "week_start": current_week_start,
                        "current_day": current_day,
                        "action": "skipped_advancement",
                    })
                    conn.execute(
                        "INSERT INTO companion_alert_log (email, alert_key, alert_date_ct, details_json, created_at) VALUES (?, ?, ?, ?, ?)",
                        (email, f"no_plan_skip_advance_{current_week_start}", today_ct_str, details, _now_z()),
                    )
                except Exception:
                    pass
                continue

            # Advance by 1 day
            new_day = current_day + 1
            conn.execute(
                """UPDATE companion_program_day_state
                   SET current_day = ?, current_day_date = ?, last_advanced_at = ?, updated_at = ?, last_progression_date_ct = ?
                   WHERE lower(email) = lower(?)""",
                (new_day, today_ct_str, _now_z(), _now_z(), today_ct_str, email),
            )
            advanced += 1
            logger.info("program_day_advanced email=%s day=%s->%s", email, current_day, new_day)

        conn.commit()
    except Exception as e:
        errors.append(str(e))
        conn.rollback()
        logger.exception("daily_program_day_advancement error: %s", e)
    finally:
        conn.close()

    logger.info("daily_program_day_advancement scanned=%s advanced=%s skipped_no_plan=%s skipped_inactive=%s errors=%s",
                scanned, advanced, skipped_no_plan, skipped_inactive, len(errors))
    return {"scanned": scanned, "advanced": advanced, "skipped_no_plan": skipped_no_plan,
            "skipped_inactive": skipped_inactive, "errors": errors}


def start_onesignal_push_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone=ZoneInfo("America/Chicago"))

    scheduler.add_job(
        _send_morning_nudge,
        trigger=CronTrigger(hour=7, minute=0, timezone=ZoneInfo("America/Chicago")),
        id="onesignal_morning_nudge",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )
    scheduler.add_job(
        _send_midday_nudge,
        trigger=CronTrigger(hour=12, minute=0, timezone=ZoneInfo("America/Chicago")),
        id="onesignal_midday_nudge",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )
    scheduler.add_job(
        _send_evening_nudge,
        trigger=CronTrigger(hour=20, minute=0, timezone=ZoneInfo("America/Chicago")),
        id="onesignal_evening_nudge",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )
    scheduler.add_job(
        run_companion_weekly_continuity_reconcile,
        trigger=CronTrigger(hour=2, minute=15, timezone=ZoneInfo("America/Chicago")),
        id="companion_weekly_continuity_reconcile_nightly",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )
    scheduler.add_job(
        run_daily_program_day_advancement,
        trigger=CronTrigger(hour=5, minute=0, timezone=ZoneInfo("America/Chicago")),
        id="daily_program_day_advancement",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )
    scheduler.add_job(
        run_weekly_plan_generation,
        trigger=CronTrigger(hour=22, minute=0, day_of_week="sun", timezone=ZoneInfo("America/Chicago")),
        id="weekly_plan_generation_sunday",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )
    # Weekly plan generation starts disabled — enable after backfill and validation
    scheduler.get_job("weekly_plan_generation_sunday").pause()

    scheduler.start()

    for job in scheduler.get_jobs():
        msg = f"ONESIGNAL_SCHEDULED_JOB id={job.id} next_run={job.next_run_time} trigger={job.trigger}"
        logger.info(msg)
        print(msg)

    return scheduler


def loops_upsert_and_trigger(*, email: str, name: Optional[str], primary_archetype: Optional[str],
                             secondary_archetype: Optional[str], context: Optional[str],
                             source_version: Optional[str], assessment_id: str,
                             confirmed_primary: Optional[str], archetype_pair_label: Optional[str],
                             assessment_completed_at: str) -> Dict[str, Any]:
    loops_api_key = (os.getenv("LOOPS_API_KEY") or "").strip()
    loops_event_name = (os.getenv("LOOPS_EVENT_NAME") or "").strip()
    loops_enabled = (os.getenv("LOOPS_ENABLED") or "true").lower() == "true"
    timeout_seconds = int(os.getenv("LOOPS_TIMEOUT_SECONDS", "10"))

    if not loops_enabled:
        return {"ok": False, "contact_id": None, "error": "loops_disabled", "retryable": False}
    if not loops_api_key or not loops_event_name:
        return {"ok": False, "contact_id": None, "error": "loops_not_configured", "retryable": False}

    headers = {
        "Authorization": f"Bearer {loops_api_key}",
        "Content-Type": "application/json",
    }

    properties = {
        "primaryArchetype": primary_archetype,
        "secondaryArchetype": secondary_archetype,
        "context": context,
        "sourceVersion": source_version,
        "confirmedPrimary": confirmed_primary,
        "archetypePairLabel": archetype_pair_label,
        "assessmentId": assessment_id,
        "assessmentCompletedAt": assessment_completed_at,
    }

    try:
        upsert_resp = requests.post(
            "https://app.loops.so/api/v1/contacts/update",
            headers=headers,
            json={
                "email": email,
                "firstName": name,
                "subscribed": True,
                **properties,
            },
            timeout=timeout_seconds,
        )
    except Exception as e:
        return {"ok": False, "contact_id": None, "error": f"loops_upsert_exception:{e}", "retryable": True}

    contact_id = None
    try:
        upsert_json = upsert_resp.json()
        contact_id = upsert_json.get("id") or upsert_json.get("contactId")
    except Exception:
        upsert_json = {"raw": upsert_resp.text[:1000]}

    if upsert_resp.status_code >= 300:
        return {
            "ok": False,
            "contact_id": contact_id,
            "error": f"loops_upsert_http_{upsert_resp.status_code}:{json.dumps(upsert_json)[:500]}",
            "retryable": True,
        }

    try:
        event_resp = requests.post(
            "https://app.loops.so/api/v1/events/send",
            headers=headers,
            json={
                "eventName": loops_event_name,
                "email": email,
                "properties": {
                    "assessmentId": assessment_id,
                    "primaryArchetype": primary_archetype,
                    "secondaryArchetype": secondary_archetype,
                    "context": context,
                    "sourceVersion": source_version,
                },
            },
            timeout=timeout_seconds,
        )
    except Exception as e:
        return {"ok": False, "contact_id": contact_id, "error": f"loops_event_exception:{e}", "retryable": True}

    if event_resp.status_code >= 300:
        body = event_resp.text[:500]
        return {
            "ok": False,
            "contact_id": contact_id,
            "error": f"loops_event_http_{event_resp.status_code}:{body}",
            "retryable": True,
        }

    return {"ok": True, "contact_id": contact_id, "error": None, "retryable": False}


def run_companion_renewal_checks() -> Dict[str, Any]:
    conn = _patterns_conn()
    sent = 0
    expired = 0
    errors = []
    try:
        now_z = _now_z()
        window_end = (datetime.now(timezone.utc) + timedelta(days=COMPANION_RENEWAL_LOOKAHEAD_DAYS)).strftime('%Y-%m-%dT%H:%M:%SZ')

        due_rows = conn.execute(
            """
            SELECT ca.email,
                   COALESCE(
                     (SELECT a.primary_archetype
                        FROM assessments a
                       WHERE lower(a.email)=lower(ca.email)
                    ORDER BY a.created_at DESC
                       LIMIT 1),
                     'Unknown'
                   ) AS primary_archetype
              FROM companion_access ca
             WHERE ca.active = 1
               AND ca.access_type = 'bundle_month1'
               AND ca.expires_at >= ?
               AND ca.expires_at <= ?
            """,
            (now_z, window_end),
        ).fetchall()

        for row in due_rows:
            res = loops_send_event(
                event_name=COMPANION_RENEWAL_EVENT_NAME,
                email=(row["email"] or "").strip().lower(),
                properties={
                    "primaryArchetype": (row["primary_archetype"] or "Unknown"),
                },
                timeout_seconds=int(os.getenv("LOOPS_TIMEOUT_SECONDS", "10")),
            )
            if res.get("ok"):
                sent += 1
            else:
                errors.append({"email": row["email"], "error": res.get("error")})

        expired_res = conn.execute(
            """
            UPDATE companion_access
               SET active = 0,
                   source = 'expiry_cleanup',
                   updated_at = ?
             WHERE active = 1
               AND expires_at < ?
            """,
            (_now_z(), now_z),
        )
        expired = int(expired_res.rowcount or 0)
        conn.commit()
    finally:
        conn.close()

    if sent or expired or errors:
        logger.info("companion renewal check sent=%s expired=%s errors=%s", sent, expired, len(errors))

    return {"sent": sent, "expired": expired, "errors": errors}


def _companion_renewal_scheduler_loop():
    logger.info("companion renewal scheduler started interval_seconds=%s", COMPANION_RENEWAL_INTERVAL_SECONDS)
    while True:
        try:
            run_companion_renewal_checks()
        except Exception as e:
            logger.exception("companion renewal scheduler error: %s", e)
        time.sleep(COMPANION_RENEWAL_INTERVAL_SECONDS)


def start_companion_renewal_scheduler():
    thread = threading.Thread(target=_companion_renewal_scheduler_loop, name="companion-renewal-scheduler", daemon=True)
    thread.start()
    return thread


# ========== SQLite Database Setup ==========
DB_PATH = Path(__file__).parent / "mc_data.db"

def init_db():
    """Initialize SQLite database with required tables"""
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    
    # User data table - stores dashboard state
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_data (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            data_json TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Activity log table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS activity_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            description TEXT NOT NULL,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()

# Initialize database and schedulers on startup
init_db()
init_patterns_assessments_db()
init_companion_tables()
if os.getenv("DASHBOARD_DISABLE_SCHEDULERS", "false").lower() not in {"1", "true", "yes"}:
    start_companion_renewal_scheduler()
    onesignal_push_scheduler = start_onesignal_push_scheduler()
else:
    onesignal_push_scheduler = None

# ========== CORS Configuration ==========
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins - adjust for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

@app.get("/card/{slug}", response_class=HTMLResponse)
async def card_share_page(slug: str):
    safe_slug = _slugify_alnum(slug)
    if not safe_slug:
        raise HTTPException(status_code=404, detail="Card not found")

    card_file = cards_static_dir / f"{safe_slug}.png"
    if not card_file.exists():
        raise HTTPException(status_code=404, detail="Card not found")

    share_image_url = f"{CARD_SHARE_BASE_URL}/static/cards/{safe_slug}_share.png"
    card_url = f"{CARD_SHARE_BASE_URL}/static/cards/{safe_slug}.png"
    page_url = f"{CARD_SHARE_BASE_URL}/card/{safe_slug}"
    person_name = _get_card_slug_name(safe_slug)
    title = f"{person_name}'s Superpower Profile" if person_name else "My Superpower Profile"
    description = "Unlock your edge. Discover your cognitive superpower at discovermysuperpower.com"

    html = f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>{escape(title)}</title>
  <meta property=\"og:title\" content=\"{escape(title)}\" />
  <meta property=\"og:description\" content=\"{escape(description)}\" />
  <meta property=\"og:image\" content=\"{escape(share_image_url)}\" />
  <meta property=\"og:image:width\" content=\"1200\" />
  <meta property=\"og:image:height\" content=\"630\" />
  <meta property=\"og:url\" content=\"{escape(page_url)}\" />
  <meta property=\"og:type\" content=\"website\" />
  <meta property=\"fb:app_id\" content=\"\" />
  <meta name=\"twitter:card\" content=\"summary_large_image\" />
  <meta name=\"twitter:title\" content=\"{escape(title)}\" />
  <meta name=\"twitter:description\" content=\"Unlock your edge. Discover your cognitive superpower at discovermysuperpower.com\" />
  <meta name=\"twitter:image\" content=\"https://discovermysuperpower.com/static/cards/{safe_slug}_share.png\" />
  <style>
    html, body {{
      margin: 0;
      padding: 0;
      background: #0d0f1a;
      color: #e2e8f0;
      font-family: Inter, Arial, sans-serif;
      height: 100%;
    }}
    .container {{
      display: flex;
      flex-direction: column;
      justify-content: center;
      align-items: center;
      min-height: 100vh;
      padding: 16px;
      box-sizing: border-box;
      text-align: center;
    }}
    .cta-button {{
      display: inline-block;
      padding: 14px 24px;
      margin-top: 32px;
      margin-bottom: 0;
      border-radius: 12px;
      background: #2563eb;
      color: #fff;
      text-decoration: none;
      font-size: 18px;
      font-variant: small-caps;
      letter-spacing: 0.05em;
      border: none;
      cursor: pointer;
      transition: background-color 0.3s;
    }}
    .cta-button:hover {{
      background: #1d4ed8;
    }}
    .card-image {{
      max-width: 90%;
      max-height: 75vh;
      height: auto;
      object-fit: contain;
      border-radius: 16px;
      box-shadow: 0 12px 40px rgba(0, 0, 0, 0.45);
    }}
  </style>
</head>
<body>
  <div class="container">
    <img src="{escape(card_url)}" alt="Superpower profile card" class="card-image" />
    <a href="{escape(CARD_ASSESSMENT_CTA_URL)}" class="cta-button">Discover My Superpower</a>
  </div>
</body>
</html>"""
    return HTMLResponse(content=html)

# Mount UGC video output directory
ugc_output_dir = Path("/home/ubuntu/.openclaw/workspace/projects/ugc-video-pipeline/output")
if ugc_output_dir.exists():
    app.mount("/ugc-videos", StaticFiles(directory=str(ugc_output_dir)), name="ugc-videos")

# User auth system (Patterns Paradigm — swap out by removing these 2 lines)
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "projects" / "patterns-paradigm" / "backend"))
from app.core.extensions.user_auth import setup_user_auth, get_optional_user
setup_user_auth(app)

# Hero card generator (Patterns Paradigm)
from app.core.extensions.card_generator import setup_card_routes, generate_hero_card_with_meta
setup_card_routes(app)

# Session management
authenticated_sessions = set()

# IP Restriction Middleware
class IPRestrictionMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if ENABLE_IP_RESTRICTION:
            client_ip = request.client.host
            if client_ip not in ALLOWED_IPS:
                return HTMLResponse(
                    content="<h1>Access Denied</h1><p>Your IP is not authorized.</p>",
                    status_code=403
                )
        return await call_next(request)

app.add_middleware(IPRestrictionMiddleware)

# No-cache middleware for Patterns Library pages/assets
class NoCachePatternsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        path = request.url.path
        if path == "/patterns-library" or path.startswith("/static/patterns/"):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response

app.add_middleware(NoCachePatternsMiddleware)

# ============== ROUTES ==============

@app.post("/stripe/webhook")
async def stripe_webhook(request: Request):
    payload = await request.body()  # raw body required for signature verification
    print(f"RAW WEBHOOK RECEIVED headers={request.headers.get('stripe-signature','')[:50]}", flush=True)
    sig_header = request.headers.get("Stripe-Signature")
    webhook_secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
    dms_webhook_secret = os.environ.get("STRIPE_WEBHOOK_SECRET_DMS", "")
    logger = logging.getLogger("companion")

    event = None
    verification_errors = []

    if webhook_secret:
        print(f"SIG VERIFY result: secret_len={len(webhook_secret)} sig_present={bool(sig_header)}", flush=True)
        try:
            event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
        except Exception as e:
            verification_errors.append(f"primary secret failed: {e}")

    if event is None and dms_webhook_secret:
        try:
            event = stripe.Webhook.construct_event(payload, sig_header, dms_webhook_secret)
        except Exception as e:
            verification_errors.append(f"dms secret failed: {e}")

    if event is None:
        logger.error("Stripe webhook signature verification failed. %s", " | ".join(verification_errors) or "no webhook secrets configured")
        return Response(status_code=400)

    event_type = event.type
    data_obj = event.data.object

    def _unix_to_z(ts):
        try:
            return datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        except Exception:
            return None

    customer_details = getattr(data_obj, "customer_details", None)
    customer_details_email = getattr(customer_details, "email", None) if customer_details is not None else None
    customer_details_name = (getattr(customer_details, "name", None) or "").strip() if customer_details is not None else ""
    customer_email = (getattr(data_obj, "customer_email", None) or customer_details_email or "").lower().strip()
    logger.info("Stripe webhook event=%s email=%s", event_type, customer_email or "unknown")

    if event_type == "checkout.session.completed":
        email = customer_email
        stripe_customer_id = (getattr(data_obj, "customer", None) or "").strip()
        stripe_subscription_id = (getattr(data_obj, "subscription", None) or "").strip()

        discount_code = None
        discount_amount = None
        try:
            total_details = getattr(data_obj, "total_details", None)
            if total_details is not None:
                amt = getattr(total_details, "amount_discount", None)
                if amt is not None:
                    discount_amount = int(amt)
            discounts_obj = getattr(data_obj, "discounts", None)
            discounts = getattr(discounts_obj, "data", None) or []
            if discounts:
                first_discount = discounts[0]
                promotion_code_obj = getattr(first_discount, "promotion_code", None)
                if promotion_code_obj is not None:
                    discount_code = (getattr(promotion_code_obj, "code", None) or "").strip() or None
                if not discount_code:
                    coupon_obj = getattr(first_discount, "coupon", None)
                    discount_code = (getattr(coupon_obj, "id", None) or "").strip() or None
        except Exception as e:
            logger.warning("Failed parsing Stripe discount metadata for %s: %s", email or "unknown", e)

        if email and stripe_subscription_id:
            now_z = _now_z()
            expires_at = (datetime.now(timezone.utc) + timedelta(days=30)).strftime('%Y-%m-%dT%H:%M:%SZ')
            conn = _patterns_conn()
            try:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO companion_access
                    (email, stripe_customer_id, stripe_subscription_id, discount_code, discount_amount, access_type, granted_at, expires_at, active, source, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (email, stripe_customer_id or None, stripe_subscription_id, discount_code, discount_amount, "bundle_month1", now_z, expires_at, 1, "stripe_webhook", now_z),
                )
                conn.commit()
            finally:
                conn.close()

            try:
                magic_link = generate_magic_link(email)
                logger.info("Generated companion magic link for %s: %s", email, magic_link)

                first_name = ""
                if customer_details_name:
                    first_name = customer_details_name.split()[0].strip()
                greeting = f"Hi {escape(first_name)}," if first_name else "Hi there,"

                html_body = f"""
                <div style=\"font-family: Arial, sans-serif; line-height:1.6; color:#111;\"> 
                  <p>{greeting}</p>
                  <p>This is your private access link to the Channeled Companion.</p>
                  <p>
                    <a href=\"{magic_link}\" style=\"display:inline-block;padding:14px 22px;background:#1a3a5c;color:#fff;text-decoration:none;border-radius:8px;font-weight:600;\">Open your Channeled Companion</a>
                  </p>
                  <p style=\"word-break:break-all;\"><a href=\"{magic_link}\">{magic_link}</a></p>
                  <p>This link expires in 72 hours. If you need a new one, just reply to this email.</p>
                  <p>— discovermysuperpower.com</p>
                </div>
                """.strip()

                # Prepare PDF attachments
                iphone_pdf_path = "/home/ubuntu/.openclaw/workspace/dashboard/static/patterns/install_guides/Channeled_PWA_Install_Guide_iPhone.pdf"
                android_pdf_path = "/home/ubuntu/.openclaw/workspace/dashboard/static/patterns/install_guides/Channeled_PWA_Install_Guide_Android.pdf"
                
                attachments = []
                
                # Function to read PDF and encode as base64
                def encode_pdf_as_base64(file_path):
                    import base64
                    if os.path.exists(file_path):
                        with open(file_path, "rb") as file:
                            return base64.b64encode(file.read()).decode("ascii")
                    return None
                
                # Add iPhone PDF attachment
                iphone_pdf_data = encode_pdf_as_base64(iphone_pdf_path)
                if iphone_pdf_data:
                    attachments.append({
                        "filename": "Channeled_PWA_Install_Guide_iPhone.pdf",
                        "contentType": "application/pdf",
                        "data": iphone_pdf_data
                    })
                
                # Add Android PDF attachment
                android_pdf_data = encode_pdf_as_base64(android_pdf_path)
                if android_pdf_data:
                    attachments.append({
                        "filename": "Channeled_PWA_Install_Guide_Android.pdf",
                        "contentType": "application/pdf",
                        "data": android_pdf_data
                    })
                
                loops_send = loops_send_transactional_email(
                    to_email=email,
                    subject="You're in — here's your access link",
                    html=html_body,
                    timeout_seconds=int(os.getenv("LOOPS_TIMEOUT_SECONDS", "10")),
                    attachments=attachments
                )
                if loops_send.get("ok"):
                    logger.info("Loops transactional send success email=%s status=%s", email, loops_send.get("status_code"))
                else:
                    logger.error("Loops transactional send failed email=%s error=%s", email, loops_send.get("error"))

                # Fire Loops event for downstream automation
                try:
                    primary_archetype = "Unknown"
                    conn = _patterns_conn()
                    try:
                        row = conn.execute(
                            """
                            SELECT primary_archetype
                            FROM assessments
                            WHERE lower(email)=lower(?)
                            ORDER BY created_at DESC
                            LIMIT 1
                            """,
                            (email,),
                        ).fetchone()
                        if row and row[0]:
                            primary_archetype = str(row[0]).strip()
                    finally:
                        conn.close()

                    loops_event = loops_send_event(
                        event_name="companion_access_granted",
                        email=email,
                        properties={
                            "firstName": first_name,
                            "primaryArchetype": primary_archetype,
                        },
                        timeout_seconds=int(os.getenv("LOOPS_TIMEOUT_SECONDS", "10")),
                    )
                    if loops_event.get("ok"):
                        logger.info("Loops event sent event=companion_access_granted email=%s", email)
                    else:
                        logger.error("Loops event failed event=companion_access_granted email=%s error=%s", email, loops_event.get("error"))
                except Exception as event_err:
                    logger.exception("Failed sending Loops event companion_access_granted for %s: %s", email, event_err)
            except Exception as e:
                logger.exception("Failed generating/sending magic link for %s: %s", email, e)

    elif event_type == "invoice.paid":
        billing_reason = (getattr(data_obj, "billing_reason", None) or "").strip()
        if billing_reason != "subscription_create":
            stripe_customer_id = (getattr(data_obj, "customer", None) or "").strip()
            subscription_id = (getattr(data_obj, "subscription", None) or "").strip()
            lines_obj = getattr(data_obj, "lines", None)
            lines = getattr(lines_obj, "data", None) or []
            period_end = None
            if lines:
                line0 = lines[0]
                period = getattr(line0, "period", None)
                period_end = _unix_to_z(getattr(period, "end", None))
            if stripe_customer_id and period_end:
                now_z = _now_z()
                conn = _patterns_conn()
                try:
                    conn.execute(
                        """
                        UPDATE companion_access
                        SET access_type = ?,
                            stripe_subscription_id = COALESCE(?, stripe_subscription_id),
                            expires_at = ?,
                            active = 1,
                            source = ?,
                            updated_at = ?
                        WHERE stripe_customer_id = ?
                        """,
                        ("subscription", subscription_id or None, period_end, "stripe_webhook", now_z, stripe_customer_id),
                    )
                    conn.commit()
                finally:
                    conn.close()

    elif event_type == "customer.subscription.deleted":
        stripe_customer_id = (getattr(data_obj, "customer", None) or "").strip()
        if stripe_customer_id:
            conn = _patterns_conn()
            try:
                conn.execute(
                    "UPDATE companion_access SET active = 0, source = ?, updated_at = ? WHERE stripe_customer_id = ?",
                    ("stripe_webhook", _now_z(), stripe_customer_id),
                )
                conn.commit()
            finally:
                conn.close()

    else:
        logger.info("Stripe webhook unhandled event=%s (acknowledged)", event_type)

    return Response(status_code=200)

# Clean URL routes for sales pages (aliases to static files)
@app.get("/upgrade", response_class=HTMLResponse)
async def upgrade():
    return FileResponse(str(static_dir / "patterns" / "full_assessment.html"))

@app.get("/faith", response_class=HTMLResponse)
async def faith():
    return FileResponse(str(static_dir / "patterns" / "full_assessment_christian.html"))

@app.get("/confirm", response_class=HTMLResponse)
async def confirm():
    return FileResponse(str(static_dir / "patterns" / "purchase_confirmed.html"))


@app.get("/purchase_confirmed.html", response_class=HTMLResponse)
async def purchase_confirmed_page():
    return FileResponse(str(static_dir / "patterns" / "purchase_confirmed.html"))


@app.get("/pr-monitor", response_class=HTMLResponse)
async def pr_monitor_page():
    return FileResponse(str(static_dir / "pr_monitor.html"))


@app.get("/pr-monitor-review", response_class=HTMLResponse)
async def pr_monitor_review_page():
    return FileResponse(str(static_dir / "pr_monitor_review.html"))


@app.post("/api/pr-monitor/sources/save")
async def pr_monitor_sources_save(
    source_set_name: str = Form(""),
    urls_text: str = Form(""),
):
    name = (source_set_name or "").strip() or "Unnamed source set"
    raw_urls = [u.strip() for u in (urls_text or "").splitlines() if u.strip()]
    urls = [u for u in raw_urls if u.lower().startswith(("http://", "https://"))]
    unique_urls = list(dict.fromkeys(urls))
    if not unique_urls:
        raise HTTPException(status_code=400, detail="No valid URLs to save.")

    out_dir = Path("/home/ubuntu/.openclaw/workspace/projects/PR_Firm_Texas/source_sets")
    out_dir.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", name).strip("_") or "source_set"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = out_dir / f"{slug}_{stamp}.txt"
    out_path.write_text("\n".join(unique_urls) + "\n", encoding="utf-8")

    return {"ok": True, "source_set_name": name, "saved_urls": len(unique_urls), "path": str(out_path)}


@app.post("/api/pr-monitor/sources/upload-csv")
async def pr_monitor_sources_upload_csv(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only .csv files are supported.")

    content = (await file.read()).decode("utf-8", errors="replace")
    if not content.strip():
        raise HTTPException(status_code=400, detail="CSV is empty.")

    # Try delimiter sniffing first (comma/semicolon/tab), fallback to comma reader
    try:
        dialect = csv.Sniffer().sniff(content[:4096], delimiters=",;\t")
        reader = csv.reader(content.splitlines(), dialect)
    except Exception:
        reader = csv.reader(content.splitlines())

    rows = list(reader)
    if not rows:
        raise HTTPException(status_code=400, detail="CSV is empty.")

    # Treat first row as header only if it does not contain any URL-like value
    first_row_has_url = any(((c or "").strip().strip('"\'').lower().startswith(("http://", "https://"))) for c in rows[0])
    data_rows = rows if first_row_has_url else rows[1:]
    urls = []
    for r in data_rows:
        if not r:
            continue
        # Scan every cell in the row (handles: col1 format, comma-list single row, mixed layouts)
        for cell in r:
            c = (cell or "").strip().strip('"\'')
            if c.lower().startswith(("http://", "https://")):
                urls.append(c)

    unique_urls = list(dict.fromkeys(urls))
    if not unique_urls:
        raise HTTPException(status_code=400, detail="No valid URLs found in CSV. Expected at least one http(s) URL.")

    return {"ok": True, "url_count": len(unique_urls), "urls": unique_urls}


@app.post("/api/pr-monitor/run")
async def pr_monitor_run(
    mode: str = Form("smart_hybrid"),
    min_confidence: float = Form(0.85),
    urls_text: str = Form(""),
    allow_default_csv: str = Form("false"),
    skip_same_day: str = Form("true"),
):
    if mode not in {"full_ai", "smart_hybrid"}:
        raise HTTPException(status_code=400, detail="Invalid mode")

    raw_urls = [u.strip() for u in (urls_text or "").splitlines() if u.strip()]
    urls = [u for u in raw_urls if u.lower().startswith(("http://", "https://"))]

    script = str(get_pr_monitor_settings().legacy_runner_path)
    cmd = ["python3", script, "--mode", mode, "--min-confidence", str(min_confidence)]
    if str(skip_same_day).lower() == "true":
        cmd.append("--skip-same-day")

    import_csv_path = None
    if urls:
        import tempfile
        from urllib.parse import urlparse
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix="_pr_monitor_input.csv", delete=False, encoding="utf-8", newline="")
        fieldnames = [
            'conf_page_url','conf_name','conf_name_found','conf_dates','conf_dates_found','conf_location','conf_location_found',
            'conf_description','conf_description_found','conf_page_cost','conf_page_paths_tried','contact_page_url','contact_name',
            'contact_name_found','contact_email','contact_email_found','contact_phone','contact_phone_found','contact_org',
            'contact_org_found','contact_page_cost','contact_paths_tried','cfp_page_url','cfp_status','cfp_status_found',
            'cfp_deadline','cfp_deadline_found','cfp_opens','cfp_opens_found','cfp_sub_requirements','cfp_sub_requirements_found',
            'cfp_page_cost','sub_page_url','sub_link','sub_link_found','sub_portal_name','sub_portal_name_found','sub_instructions',
            'sub_instructions_found','sub_page_cost','sub_paths_tried','conference_name','base_url','domain','crawl_date','total_cost',
            'fields_with_value','fields_with_placeholder','fields_unavailable','completeness_pct','budget_exceeded','notable_info',
            'crawl_notes','metrics','market','customer'
        ]
        writer = csv.DictWriter(tmp, fieldnames=fieldnames)
        writer.writeheader()
        for u in urls:
            parsed = urlparse(u)
            writer.writerow({
                "conf_page_url": u,
                "base_url": u,
                "domain": parsed.netloc.lower(),
                "conference_name": "",
                "market": "hydrogen",
                "customer": "default_customer",
            })
        tmp.close()
        import_csv_path = tmp.name
        cmd.extend(["--import-csv", import_csv_path])
    else:
        if str(allow_default_csv).lower() != "true":
            raise HTTPException(status_code=400, detail="No valid URLs provided. Paste URLs or explicitly enable default CSV run.")

    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        return JSONResponse(status_code=500, content={"ok": False, "error": proc.stderr or proc.stdout})

    return {
        "ok": True,
        "output": proc.stdout.strip(),
        "source": "manual_urls" if urls else "default_csv",
        "input_url_count": len(urls),
        "import_csv": import_csv_path,
    }


@app.get("/api/pr-monitor/local-browser/job/{run_id}")
async def pr_monitor_local_browser_job(run_id: str):
    """Generate a recovery job file for local browser fallback.

    Returns a JSON job manifest with blocked/partial URLs from the given quality run.
    The user downloads this file and places it in their local runner folder.
    """
    safe_run_id = re.sub(r"[^A-Za-z0-9_.-]", "_", run_id or "")[:120]
    if not safe_run_id:
        raise HTTPException(status_code=400, detail="Invalid run_id")

    # Look up blocked/partial URLs from the quality report for this run
    quality_reports_dir = PR_MONITOR_PROJECT_ROOT / "quality_reports"
    report_path = quality_reports_dir / f"{safe_run_id}.json"

    # Also check scheduled variants
    if not report_path.exists():
        # Try to find any matching report
        for p in quality_reports_dir.glob(f"*{safe_run_id}*.json"):
            report_path = p
            break

    if not report_path.exists():
        raise HTTPException(status_code=404, detail=f"Quality run not found: {safe_run_id}")

    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to read quality report")

    # Extract blocked and partial URLs from records
    records = report.get("records", [])
    blocked_urls = []
    for rec in records:
        status = rec.get("status", "")
        if status in ("BLOCKED", "PARTIAL"):
            url = rec.get("rec", {}) or {}
            blocked_urls.append({
                "row_number": rec.get("row_number"),
                "name": rec.get("name", ""),
                "url": rec.get("url", ""),
                "original_status": status,
                "original_http_status": rec.get("http_status"),
                "original_failure_mode": rec.get("status_reason", ""),
            })

    if not blocked_urls:
        raise HTTPException(status_code=404, detail="No blocked or partial URLs found in this run")

    # Build job manifest (same format the local runner expects)
    # Generate a new upload token for this recovery job
    recovery_token = secrets.token_urlsafe(24)
    token_path = PR_MONITOR_LOCAL_BROWSER_UPLOAD_TOKENS / f"{safe_run_id}.json"
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(json.dumps({
        "run_id": safe_run_id,
        "upload_code": recovery_token,
        "created_from": "local_browser_job_endpoint",
        "customer_sheet_write_policy": "READ_ONLY_NO_CUSTOMER_SHEET_WRITES",
    }, indent=2))
    os.chmod(token_path, 0o644)

    job_manifest = {
        "job_type": "pr_monitor_local_browser_fallback",
        "source": "vps_quality_crawl",
        "source_run_id": safe_run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "customer_sheet_write_policy": "READ_ONLY_NO_CUSTOMER_SHEET_WRITES",
        "upload": {
            "enabled": True,
            "url": "https://channeled.org/api/pr-monitor/local-browser/upload",
            "run_id": safe_run_id,
            "upload_code": recovery_token,
        },
        "urls": blocked_urls,
    }

    # Return as a downloadable JSON file
    from fastapi.responses import Response
    return Response(
        content=json.dumps(job_manifest, indent=2),
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="recovery_job_{safe_run_id}.json"'
        }
    )


@app.post("/api/pr-monitor/local-browser/upload")
async def pr_monitor_local_browser_upload(
    run_id: str = Form(...),
    upload_code: str = Form(...),
    file: UploadFile = File(...),
):
    """Receive local desktop browser fallback result bundles.

    This is a fallback evidence layer only. It stores uploaded ZIPs under
    pr_monitor_1/local_browser_fallback/uploads and does not write to customer
    source docs or Nicolia Google Sheets.
    """
    safe_run_id = re.sub(r"[^A-Za-z0-9_.-]", "_", run_id or "")[:120]
    if not safe_run_id:
        raise HTTPException(status_code=400, detail="Invalid run_id")

    token_path = PR_MONITOR_LOCAL_BROWSER_UPLOAD_TOKENS / f"{safe_run_id}.json"
    if not token_path.exists():
        raise HTTPException(status_code=403, detail="Upload is not enabled for this run")
    try:
        token_data = json.loads(token_path.read_text())
    except Exception:
        raise HTTPException(status_code=500, detail="Upload token configuration is unreadable")
    expected_code = token_data.get("upload_code") or ""
    if not expected_code or not secrets.compare_digest(str(upload_code), str(expected_code)):
        raise HTTPException(status_code=403, detail="Invalid upload code")

    original_name = file.filename or "local_browser_results.zip"
    if not original_name.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Only .zip result bundles are accepted")

    upload_dir = PR_MONITOR_LOCAL_BROWSER_UPLOADS / safe_run_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest_name = f"{stamp}_{re.sub(r'[^A-Za-z0-9_.-]', '_', original_name)[:160]}"
    dest_path = upload_dir / dest_name

    max_bytes = 75 * 1024 * 1024
    total = 0
    digest = hashlib.sha256()
    with dest_path.open("wb") as out:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                try:
                    dest_path.unlink()
                except FileNotFoundError:
                    pass
                raise HTTPException(status_code=413, detail="Upload too large; limit is 75MB")
            digest.update(chunk)
            out.write(chunk)
    os.chmod(dest_path, 0o644)

    metadata = {
        "run_id": safe_run_id,
        "received_at": datetime.now(timezone.utc).isoformat(),
        "filename": dest_name,
        "bytes": total,
        "sha256": digest.hexdigest(),
        "customer_sheet_write_policy": "READ_ONLY_NO_CUSTOMER_SHEET_WRITES",
        "stored_path": str(dest_path),
    }
    meta_path = upload_dir / f"{dest_name}.metadata.json"
    meta_path.write_text(json.dumps(metadata, indent=2))
    os.chmod(meta_path, 0o644)
    # After successful upload, also extract summary.json from the zip for quick recovery lookups
    try:
        import zipfile
        with zipfile.ZipFile(str(dest_path), 'r') as z:
            summary_member = None
            for name in z.namelist():
                if name == 'summary.json' or name.endswith('/summary.json'):
                    summary_member = name
                    break
            if summary_member:
                summary_data = json.loads(z.read(summary_member))
                summary_path = upload_dir / f"{dest_name}_summary.json"
                summary_path.write_text(json.dumps(summary_data, indent=2))
                os.chmod(summary_path, 0o644)
    except Exception:
        pass  # Non-critical: recovery endpoint will just report no data

    return JSONResponse({"ok": True, "upload": metadata})


@app.get("/api/pr-monitor/local-browser/recovery/{run_id}")
async def pr_monitor_local_browser_recovery(run_id: str):
    """Return local browser fallback recovery data for a given quality run."""
    safe_run_id = re.sub(r"[^A-Za-z0-9_.-]", "_", run_id or "")[:120]
    if not safe_run_id:
        raise HTTPException(status_code=400, detail="Invalid run_id")

    uploads_dir = PR_MONITOR_LOCAL_BROWSER_UPLOADS / safe_run_id
    if not uploads_dir.exists():
        return JSONResponse({
            "run_id": safe_run_id,
            "available": False,
            "message": "No local browser recovery data for this run. Run the local Windows runner to attempt recovery.",
            "recovery_map": [],
        })

    # Merge all uploaded summaries for this run. A later transient browser/network
    # error should not hide an earlier successful local recovery for the same URL.
    summary_files = sorted(uploads_dir.glob("*_summary.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not summary_files:
        summary_files = sorted(uploads_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)

    best_by_url = {}
    first_order = []
    for sf in summary_files:
        try:
            data = json.loads(sf.read_text(encoding="utf-8"))
            recovery_map = data.get("recovery_map")
            if recovery_map is None and isinstance(data.get("results"), list):
                recovery_map = []
                for row in data.get("results", []):
                    original = row.get("original_status", "UNKNOWN")
                    local = row.get("local_status", "UNKNOWN")
                    recovery_map.append({
                        "url": row.get("url"),
                        "name": row.get("name"),
                        "original_vps_status": original,
                        "local_browser_status": local,
                        "recovered": original in ("BLOCKED", "PARTIAL") and local in ("PASS", "PARTIAL"),
                        "fallback_method": "local_browser" if local in ("PASS", "PARTIAL") else "none",
                    })
            if recovery_map is None:
                continue
            for row in recovery_map:
                url = row.get("url") or row.get("name")
                if not url:
                    continue
                if url not in best_by_url:
                    best_by_url[url] = row
                    first_order.append(url)
                    continue
                current = best_by_url[url]
                if row.get("recovered") and not current.get("recovered"):
                    best_by_url[url] = row
        except Exception:
            continue

    if best_by_url:
        recovery_map = [best_by_url[url] for url in first_order]
        recovery_summary = {
            "total_urls": len(recovery_map),
            "recovered_by_local": sum(1 for row in recovery_map if row.get("recovered")),
            "still_blocked": sum(1 for row in recovery_map if not row.get("recovered")),
        }
        return JSONResponse({
            "run_id": safe_run_id,
            "available": True,
            "recovery_summary": recovery_summary,
            "recovery_map": recovery_map,
        })

    return JSONResponse({
        "run_id": safe_run_id,
        "available": False,
        "message": "Upload directory exists but no recovery summary found.",
        "recovery_map": [],
    })


@app.get("/api/pr-monitor/latest")
async def pr_monitor_latest():
    db = str(get_pr_monitor_settings().db_path)
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            """
            SELECT run_id, mode, started_at, completed_at, rows_scanned, rows_inserted, rows_updated,
                   rows_flagged, ai_calls, total_ai_cost, avg_confidence
            FROM pipeline_runs
            WHERE status='completed'
            ORDER BY started_at DESC
            LIMIT 1
            """
        ).fetchone()
        if not row:
            return {"ok": True, "run": None}
        run = dict(row)
        skipped = conn.execute(
            "SELECT COUNT(*) FROM run_row_audit WHERE run_id=? AND skip_reason='same_day_already_processed'",
            (run["run_id"],),
        ).fetchone()[0]
        run["rows_skipped_same_day"] = skipped
        return {"ok": True, "run": run}
    finally:
        conn.close()


@app.get("/api/pr-monitor/runs")
async def pr_monitor_runs(limit: int = 20):
    db = str(get_pr_monitor_settings().db_path)
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    try:
        row_limit = max(1, min(int(limit or 20), 200))
        rows = conn.execute(
            """
            SELECT run_id, mode, started_at, completed_at, rows_scanned, rows_inserted, rows_updated,
                   rows_flagged, ai_calls, total_ai_cost, avg_confidence
            FROM pipeline_runs
            WHERE status='completed'
            ORDER BY started_at DESC
            LIMIT ?
            """,
            (row_limit,),
        ).fetchall()
        runs = []
        for r in rows:
            d = dict(r)
            d["rows_skipped_same_day"] = conn.execute(
                "SELECT COUNT(*) FROM run_row_audit WHERE run_id=? AND skip_reason='same_day_already_processed'",
                (d["run_id"],),
            ).fetchone()[0]
            d["rows_with_results"] = conn.execute(
                """
                SELECT COUNT(*)
                FROM run_row_audit a
                LEFT JOIN conference_events e ON e.event_key = a.event_key AND e.run_id = a.run_id
                WHERE a.run_id = ?
                  AND (
                    coalesce(trim(a.cfp_status),'')<>'' OR coalesce(trim(a.cfp_deadline),'')<>'' OR coalesce(trim(a.conf_dates),'')<>''
                    OR coalesce(trim(e.cfp_status),'')<>'' OR coalesce(trim(e.cfp_deadline),'')<>'' OR coalesce(trim(e.conf_dates),'')<>''
                  )
                """,
                (d["run_id"],),
            ).fetchone()[0]
            d["rows_null_results"] = max(0, int(d.get("rows_scanned") or 0) - int(d["rows_with_results"]))
            runs.append(d)
        return {"ok": True, "runs": runs}
    finally:
        conn.close()


@app.get("/api/pr-monitor/run/{run_id}/rows")
async def pr_monitor_run_rows(
    run_id: str,
    qa_status: str = "",
    ai_called: str = "",
    changed_only: str = "false",
    has_cfp_or_dates: str = "false",
    domain_contains: str = "",
    market: str = "",
    customer: str = "",
    limit: int = 500,
):
    db = str(get_pr_monitor_settings().db_path)
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    try:
        where = ["a.run_id = ?"]
        params = [run_id]

        if qa_status:
            where.append("coalesce(a.qa_status,'') = ?")
            params.append(qa_status)
        if ai_called in {"0", "1"}:
            where.append("a.ai_called = ?")
            params.append(int(ai_called))
        if str(changed_only).lower() == "true":
            where.append("coalesce(a.changed_fields,'') <> '' AND coalesce(a.changed_fields,'') <> 'no_material_change'")
        if str(has_cfp_or_dates).lower() == "true":
            where.append("(coalesce(trim(a.cfp_status),'')<>'' OR coalesce(trim(a.cfp_deadline),'')<>'' OR coalesce(trim(a.conf_dates),'')<>'' OR coalesce(trim(e.cfp_status),'')<>'' OR coalesce(trim(e.cfp_deadline),'')<>'' OR coalesce(trim(e.conf_dates),'')<>'')")
        if domain_contains:
            where.append("lower(coalesce(a.domain,'')) LIKE ?")
            params.append(f"%{domain_contains.lower()}%")
        if market:
            where.append("lower(coalesce(e.market,'')) = ?")
            params.append(market.lower())
        if customer:
            where.append("lower(coalesce(e.customer,'')) = ?")
            params.append(customer.lower())

        row_limit = max(1, min(int(limit or 500), 2000))
        audit_cols = {r[1] for r in conn.execute("PRAGMA table_info(run_row_audit)").fetchall()}
        event_cols = {r[1] for r in conn.execute("PRAGMA table_info(conference_events)").fetchall()}
        change_diffs_expr = "a.change_diffs" if "change_diffs" in audit_cols else "NULL"
        change_checked_at_expr = "a.change_checked_at" if "change_checked_at" in audit_cols else "NULL"
        geo_city_expr = "e.geo_city" if "geo_city" in event_cols else "NULL"
        geo_state_expr = "e.geo_state" if "geo_state" in event_cols else "NULL"
        geo_country_expr = "e.geo_country" if "geo_country" in event_cols else "NULL"
        geo_confidence_status_expr = "e.geo_confidence_status" if "geo_confidence_status" in event_cols else "NULL"
        cfp_deadline_normalized_expr = "coalesce(a.cfp_deadline_normalized, e.cfp_deadline_normalized)" if "cfp_deadline_normalized" in audit_cols and "cfp_deadline_normalized" in event_cols else "NULL"
        deadline_urgency_expr = "coalesce(a.deadline_urgency, e.deadline_urgency)" if "deadline_urgency" in audit_cols and "deadline_urgency" in event_cols else "NULL"
        action_state_expr = "coalesce(a.action_state, e.action_state)" if "action_state" in audit_cols and "action_state" in event_cols else "NULL"
        q = f"""
        SELECT a.run_id, a.created_at, a.event_key, a.domain, a.conf_page_url, a.conference_name,
               a.qa_status, a.extract_confidence, a.ai_called, a.changed_fields,
               {change_diffs_expr} as change_diffs, {change_checked_at_expr} as change_checked_at, a.skip_reason,
               coalesce(a.cfp_status, e.cfp_status) as cfp_status,
               coalesce(a.cfp_deadline, e.cfp_deadline) as cfp_deadline,
               {cfp_deadline_normalized_expr} as cfp_deadline_normalized,
               {deadline_urgency_expr} as deadline_urgency,
               {action_state_expr} as action_state,
               coalesce(a.conf_dates, e.conf_dates) as conf_dates,
               e.conf_location,
               {geo_city_expr} as geo_city,
               {geo_state_expr} as geo_state,
               {geo_country_expr} as geo_country,
               {geo_confidence_status_expr} as geo_confidence_status,
               e.market,
               e.customer,
               e.run_id as event_run_id
        FROM run_row_audit a
        LEFT JOIN conference_events e ON e.event_key = a.event_key AND e.run_id = a.run_id
        WHERE {' AND '.join(where)}
        ORDER BY a.created_at DESC, a.domain ASC
        LIMIT {row_limit}
        """
        rows = [dict(r) for r in conn.execute(q, params).fetchall()]
        for row in rows:
            if isinstance(row.get("change_diffs"), str) and row.get("change_diffs"):
                try:
                    row["change_diffs"] = json.loads(row["change_diffs"])
                except Exception:
                    pass

        if event_cols and {"geo_city", "geo_state", "geo_country", "geo_confidence_status"} <= event_cols:
            try:
                geo_lookup: Dict[tuple, Dict[str, Any]] = {}
                for r in conn.execute(
                    """
                    SELECT domain, conf_page_url, geo_city, geo_state, geo_country, geo_confidence_status
                    FROM conference_events
                    WHERE (domain, conf_page_url, updated_at) IN (
                        SELECT domain, conf_page_url, MAX(updated_at)
                        FROM conference_events
                        GROUP BY domain, conf_page_url
                    )
                    """
                ):
                    geo_lookup[(r["domain"], r["conf_page_url"])] = dict(r)

                for row in rows:
                    if not row.get("geo_city"):
                        key = (row.get("domain") or "", row.get("conf_page_url") or "")
                        match = geo_lookup.get(key)
                        if match and match.get("geo_city"):
                            row["geo_city"] = match["geo_city"]
                            row["geo_state"] = match["geo_state"]
                            row["geo_country"] = match["geo_country"]
                            row["geo_confidence_status"] = match["geo_confidence_status"]
            except Exception as exc:
                logger.warning("geo fallback enrichment failed: %s", exc, exc_info=True)

        rows = _enrich_pr_monitor_rows_with_source_history(rows)
        return {"ok": True, "run_id": run_id, "count": len(rows), "rows": rows}
    finally:
        conn.close()


@app.get("/api/pr-monitor/portfolio/latest")
async def pr_monitor_portfolio_latest(
    market: str = "hydrogen",
    customer: str = "default_customer",
    has_cfp_or_dates: str = "true",
    limit: int = 500,
):
    db = str(get_pr_monitor_settings().db_path)
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    try:
        row_limit = max(1, min(int(limit or 500), 2000))
        where = ["1=1"]
        params = []
        if market:
            where.append("lower(coalesce(market,'')) = ?")
            params.append(market.lower())
        if customer:
            where.append("lower(coalesce(customer,'')) = ?")
            params.append(customer.lower())
        if str(has_cfp_or_dates).lower() == "true":
            where.append("(coalesce(trim(cfp_status),'')<>'' OR coalesce(trim(cfp_deadline),'')<>'' OR coalesce(trim(conf_dates),'')<>'')")

        q = f"""
        SELECT * FROM conference_events e
        WHERE {' AND '.join(where)}
          AND updated_at = (
            SELECT MAX(updated_at) FROM conference_events e2 WHERE e2.event_key = e.event_key
          )
        ORDER BY updated_at DESC
        LIMIT {row_limit}
        """
        rows = [dict(r) for r in conn.execute(q, params).fetchall()]
        for row in rows:
            if isinstance(row.get("change_diffs"), str) and row.get("change_diffs"):
                try:
                    row["change_diffs"] = json.loads(row["change_diffs"])
                except Exception:
                    pass
        rows = _enrich_pr_monitor_rows_with_source_history(rows)
        return {"ok": True, "count": len(rows), "rows": rows}
    finally:
        conn.close()


@app.get("/api/pr-monitor/portfolio/export-csv")
async def pr_monitor_portfolio_export_csv(
    market: str = "hydrogen",
    customer: str = "default_customer",
    has_cfp_or_dates: str = "true",
    upcoming_only: str = "false",
    limit: int = 5000,
):
    import io
    import re
    from datetime import datetime, timezone

    def _parse_conf_start_date(value: str):
        s = (value or "").strip()
        if not s:
            return None

        m = re.search(r"\b(20\d{2})-(\d{1,2})-(\d{1,2})\b", s)
        if m:
            try:
                return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), tzinfo=timezone.utc).date()
            except Exception:
                pass

        m = re.search(r"\b(\d{1,2})/(\d{1,2})/(20\d{2})\b", s)
        if m:
            try:
                return datetime(int(m.group(3)), int(m.group(1)), int(m.group(2)), tzinfo=timezone.utc).date()
            except Exception:
                pass

        m = re.search(r"\b([A-Za-z]{3,9})\.?\s+(\d{1,2})(?:\s*[-–]\s*\d{1,2})?(?:,)?\s*(20\d{2})\b", s, flags=re.I)
        if m:
            mon = m.group(1).lower()
            months = {
                "january":1,"jan":1,"february":2,"feb":2,"march":3,"mar":3,"april":4,"apr":4,"may":5,
                "june":6,"jun":6,"july":7,"jul":7,"august":8,"aug":8,"september":9,"sep":9,"sept":9,
                "october":10,"oct":10,"november":11,"nov":11,"december":12,"dec":12
            }
            if mon in months:
                try:
                    return datetime(int(m.group(3)), months[mon], int(m.group(2)), tzinfo=timezone.utc).date()
                except Exception:
                    pass
        return None

    db = str(get_pr_monitor_settings().db_path)
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    try:
        row_limit = max(1, min(int(limit or 5000), 20000))
        where = ["1=1"]
        params = []
        if market:
            where.append("lower(coalesce(market,'')) = ?")
            params.append(market.lower())
        if customer:
            where.append("lower(coalesce(customer,'')) = ?")
            params.append(customer.lower())
        if str(has_cfp_or_dates).lower() == "true":
            where.append("(coalesce(trim(cfp_status),'')<>'' OR coalesce(trim(cfp_deadline),'')<>'' OR coalesce(trim(conf_dates),'')<>'')")

        q = f"""
        SELECT * FROM conference_events e
        WHERE {' AND '.join(where)}
          AND updated_at = (
            SELECT MAX(updated_at) FROM conference_events e2 WHERE e2.event_key = e.event_key
          )
        ORDER BY updated_at DESC
        LIMIT {row_limit}
        """
        rows = [dict(r) for r in conn.execute(q, params).fetchall()]

        if str(upcoming_only).lower() == "true":
            today = datetime.now(timezone.utc).date()
            rows = [r for r in rows if (_parse_conf_start_date(r.get("conf_dates")) is not None and _parse_conf_start_date(r.get("conf_dates")) >= today)]

        def _normalize_text(v):
            if not isinstance(v, str):
                return v
            # Fix common mojibake artifacts seen in conference date ranges and punctuation
            replacements = {
                "â€“": "–",  # en dash
                "â€”": "—",  # em dash
                "â€™": "’",
                "â€œ": "“",
                "â€": "”",
                "Â ": " ",
                "Â": "",
            }
            out = v
            for bad, good in replacements.items():
                out = out.replace(bad, good)
            return out

        cleaned_rows = []
        for r in rows:
            cleaned_rows.append({k: _normalize_text(v) for k, v in r.items()})

        output = io.StringIO()
        if cleaned_rows:
            fieldnames = list(cleaned_rows[0].keys())
            writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(cleaned_rows)
        else:
            writer = csv.writer(output)
            writer.writerow(["no_data"])

        # UTF-8 BOM helps Excel detect encoding correctly
        csv_bytes = ("\ufeff" + output.getvalue()).encode("utf-8")
        filename = f"pr_monitor_{(market or 'all').strip() or 'all'}_latest.csv"
        headers = {
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Type": "text/csv; charset=utf-8",
        }
        return Response(content=csv_bytes, media_type="text/csv", headers=headers)
    finally:
        conn.close()






@app.get("/api/pr-monitor/queue")
async def pr_monitor_queue(
    open_cfp: Optional[str] = "",
    deadline_bucket: str = "",
    change_status: str = "",
    failure_or_manual_review: Optional[str] = "",
    client_fit_status: str = "",
    source: str = "",
    limit: int = 500,
):
    """Return normalized opportunity rows grouped by action state and urgency."""
    db = str(get_pr_monitor_settings().db_path)
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    try:
        row_limit = max(1, min(int(limit or 500), 2000))
        where = ["1=1"]
        params: List[Any] = []

        if str(open_cfp or "").strip().lower() in {"true", "1", "yes"}:
            where.append(
                "(coalesce(trim(a.cfp_status),'')<>'' OR coalesce(trim(e.cfp_status),'')<>'')"
            )

        raw_deadline_bucket = (deadline_bucket or "").strip()
        if raw_deadline_bucket:
            where.append("coalesce(a.cfp_deadline_normalized, e.cfp_deadline_normalized, '') <> ''")

        change_status_norm = (change_status or "").strip().lower()
        if change_status_norm in {"new", "changed", "unchanged"}:
            if change_status_norm == "new":
                where.append("(coalesce(trim(a.changed_fields),'')='new')")
            elif change_status_norm == "changed":
                where.append("coalesce(trim(a.changed_fields),'') <> '' AND coalesce(trim(a.changed_fields),'') NOT IN ('new','no_material_change','')")
            else:
                where.append("(coalesce(trim(a.changed_fields),'')='' OR coalesce(trim(a.changed_fields),'')='no_material_change')")

        if str(failure_or_manual_review or "").strip().lower() in {"true", "1", "yes"}:
            where.append(
                "(coalesce(trim(a.qa_status),'') <> '' OR coalesce(trim(a.skip_reason),'') <> '')"
            )

        if (client_fit_status or "").strip():
            where.append("coalesce(trim(a.qa_status),'') = ?")
            params.append((client_fit_status or "").strip())

        if (source or "").strip():
            where.append("coalesce(trim(a.source),'') = ?")
            params.append((source or "").strip())

        audit_cols = {r[1] for r in conn.execute("PRAGMA table_info(run_row_audit)").fetchall()}
        event_cols = {r[1] for r in conn.execute("PRAGMA table_info(conference_events)").fetchall()}
        change_diffs_expr = "a.change_diffs" if "change_diffs" in audit_cols else "NULL"
        cfp_deadline_normalized_expr = (
            "coalesce(a.cfp_deadline_normalized, e.cfp_deadline_normalized)"
            if "cfp_deadline_normalized" in audit_cols and "cfp_deadline_normalized" in event_cols
            else "NULL"
        )
        deadline_urgency_expr = (
            "coalesce(a.deadline_urgency, e.deadline_urgency)"
            if "deadline_urgency" in audit_cols and "deadline_urgency" in event_cols
            else "NULL"
        )
        action_state_expr = (
            "coalesce(a.action_state, e.action_state)"
            if "action_state" in audit_cols and "action_state" in event_cols
            else "NULL"
        )

        geo_city_expr = "e.geo_city" if "geo_city" in event_cols else "NULL"
        geo_state_expr = "e.geo_state" if "geo_state" in event_cols else "NULL"
        geo_country_expr = "e.geo_country" if "geo_country" in event_cols else "NULL"
        geo_confidence_expr = "e.geo_confidence_status" if "geo_confidence_status" in event_cols else "NULL"

        q = (
            "SELECT a.run_id, a.created_at, a.event_key, a.domain, a.conf_page_url, a.conference_name,"
            "       a.qa_status, a.extract_confidence, a.ai_called, a.changed_fields,"
            "       " + change_diffs_expr + " as change_diffs, a.change_checked_at, a.skip_reason,"
            "       coalesce(a.cfp_status, e.cfp_status) as cfp_status,"
            "       coalesce(a.cfp_deadline, e.cfp_deadline) as cfp_deadline,"
            "       " + cfp_deadline_normalized_expr + " as cfp_deadline_normalized,"
            "       " + deadline_urgency_expr + " as deadline_urgency,"
            "       " + action_state_expr + " as action_state,"
            "       coalesce(a.conf_dates, e.conf_dates) as conf_dates,"
            "       e.conf_location,"
            "       " + geo_city_expr + " as geo_city,"
            "       " + geo_state_expr + " as geo_state,"
            "       " + geo_country_expr + " as geo_country,"
            "       " + geo_confidence_expr + " as geo_confidence_status"
            "  FROM run_row_audit a"
            "  LEFT JOIN conference_events e ON e.event_key = a.event_key AND e.run_id = a.run_id"
            " WHERE " + " AND ".join(where) +
            " ORDER BY a.created_at DESC, a.domain ASC"
            " LIMIT " + str(row_limit)
        )
        rows = [dict(r) for r in conn.execute(q, params).fetchall()]
        for row in rows:
            raw = row.get("change_diffs")
            if isinstance(raw, str) and raw:
                try:
                    row["change_diffs"] = json.loads(raw)
                except Exception:
                    pass

        # Geo fallback enrichment: when LEFT JOIN on event_key+run_id misses,
        # look up conference_events by (domain, conf_page_url) across all runs.
        if event_cols and {"geo_city", "geo_state", "geo_country", "geo_confidence_status"} <= event_cols:
            try:
                geo_lookup: Dict[tuple, Dict[str, Any]] = {}
                for r in conn.execute(
                    """
                    SELECT domain, conf_page_url, geo_city, geo_state, geo_country, geo_confidence_status
                    FROM conference_events
                    WHERE (domain, conf_page_url, updated_at) IN (
                        SELECT domain, conf_page_url, MAX(updated_at)
                        FROM conference_events
                        GROUP BY domain, conf_page_url
                    )
                    """
                ):
                    geo_lookup[(r["domain"], r["conf_page_url"])] = dict(r)

                for row in rows:
                    if not row.get("geo_city"):
                        key = (row.get("domain") or "", row.get("conf_page_url") or "")
                        match = geo_lookup.get(key)
                        if match and match.get("geo_city"):
                            row["geo_city"] = match["geo_city"]
                            row["geo_state"] = match["geo_state"]
                            row["geo_country"] = match["geo_country"]
                            row["geo_confidence_status"] = match["geo_confidence_status"]
            except Exception as exc:
                logger.warning("queue geo fallback enrichment failed: %s", exc, exc_info=True)

        rows = _enrich_pr_monitor_rows_with_source_history(rows)
        buckets: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            cfp_deadline = (row.get("cfp_deadline_normalized") or "").strip()
            raw_deadline_urgency = (row.get("deadline_urgency") or "").strip().lower()
            if not raw_deadline_urgency:
                raw_deadline_urgency = "unscheduled"
            action_state = (row.get("action_state") or "").strip().lower() or "needs_review"
            changed_fields = (row.get("changed_fields") or "").strip().lower()
            if action_state == "needs_review" and changed_fields:
                action_state = changed_fields
            key = f"{action_state}|{raw_deadline_urgency}"
            bucket = buckets.get(key)
            if not bucket:
                bucket = {
                    "state": action_state,
                    "urgency": raw_deadline_urgency,
                    "count": 0,
                    "rows": [],
                }
                buckets[key] = bucket
            bucket["count"] += 1
            bucket["rows"].append(row)
        groups = list(buckets.values())
        return {"ok": True, "count": len(rows), "groups": groups}
    finally:
        conn.close()

@app.get("/api/pr-monitor-review/portfolio/latest")
async def pr_monitor_review_portfolio_latest(
    market: str = "hydrogen",
    customer: str = "default_customer",
    limit: int = 500,
):
    db = str(get_pr_monitor_settings().db_path)
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    try:
        row_limit = max(1, min(int(limit or 500), 2000))
        q = f"""
        SELECT
          e.*,
          r.review_status,
          r.override_cfp_status,
          r.override_cfp_deadline,
          r.override_conf_dates,
          r.review_notes,
          r.reviewed_by,
          r.reviewed_at,
          coalesce(r.submission_status, 'not_submitted') as submission_status,
          CASE WHEN coalesce(trim(r.override_cfp_status),'')<>'' THEN 1 ELSE 0 END as has_override_cfp_status,
          CASE WHEN coalesce(trim(r.override_cfp_deadline),'')<>'' THEN 1 ELSE 0 END as has_override_cfp_deadline,
          CASE WHEN coalesce(trim(r.override_conf_dates),'')<>'' THEN 1 ELSE 0 END as has_override_conf_dates
        FROM conference_events e
        LEFT JOIN conference_event_reviews r
          ON r.event_key = e.event_key
         AND lower(coalesce(r.market,'')) = lower(coalesce(e.market,''))
         AND lower(coalesce(r.customer,'')) = lower(coalesce(e.customer,''))
        WHERE lower(coalesce(e.market,'')) = ?
          AND lower(coalesce(e.customer,'')) = ?
          AND e.updated_at = (
            SELECT MAX(updated_at) FROM conference_events e2 WHERE e2.event_key = e.event_key
          )
        ORDER BY e.updated_at DESC
        LIMIT {row_limit}
        """
        rows = [dict(r) for r in conn.execute(q, (market.lower(), customer.lower())).fetchall()]
        rows = _enrich_pr_monitor_rows_with_source_history(rows)
        return {"ok": True, "count": len(rows), "rows": rows}
    finally:
        conn.close()


@app.post("/api/pr-monitor-review/review/upsert")
async def pr_monitor_review_upsert(payload: dict):
    from datetime import datetime, timezone

    event_key = str(payload.get("event_key") or "").strip()
    if not event_key:
        raise HTTPException(status_code=400, detail="event_key is required")

    market = str(payload.get("market") or "").strip()
    customer = str(payload.get("customer") or "").strip()
    review_status = str(payload.get("review_status") or "needs_review").strip() or "needs_review"
    override_cfp_status = payload.get("override_cfp_status")
    override_cfp_deadline = payload.get("override_cfp_deadline")
    override_conf_dates = payload.get("override_conf_dates")
    review_notes = payload.get("review_notes")
    reviewed_by = payload.get("reviewed_by")
    reviewed_at = payload.get("reviewed_at") or datetime.now(timezone.utc).isoformat()
    submission_status = str(payload.get("submission_status") or "not_submitted").strip() or "not_submitted"

    db = str(get_pr_monitor_settings().db_path)
    conn = sqlite3.connect(db)
    try:
        conn.execute(
            """
            INSERT INTO conference_event_reviews (
              event_key, market, customer, review_status,
              override_cfp_status, override_cfp_deadline, override_conf_dates,
              review_notes, reviewed_by, reviewed_at, submission_status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
            ON CONFLICT(event_key, market, customer) DO UPDATE SET
              review_status=excluded.review_status,
              override_cfp_status=excluded.override_cfp_status,
              override_cfp_deadline=excluded.override_cfp_deadline,
              override_conf_dates=excluded.override_conf_dates,
              review_notes=excluded.review_notes,
              reviewed_by=excluded.reviewed_by,
              reviewed_at=excluded.reviewed_at,
              submission_status=excluded.submission_status,
              updated_at=datetime('now')
            """,
            (
                event_key, market, customer, review_status,
                override_cfp_status, override_cfp_deadline, override_conf_dates,
                review_notes, reviewed_by, reviewed_at, submission_status,
            ),
        )
        conn.commit()
        return {"ok": True, "event_key": event_key}
    finally:
        conn.close()


@app.get("/api/pr-monitor-review/portfolio/export-csv")
async def pr_monitor_review_portfolio_export_csv(
    market: str = "hydrogen",
    customer: str = "default_customer",
    limit: int = 5000,
):
    import io

    db = str(get_pr_monitor_settings().db_path)
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    try:
        row_limit = max(1, min(int(limit or 5000), 20000))
        q = f"""
        SELECT
          e.*,
          coalesce(r.review_status, 'needs_review') as review_status,
          r.review_notes,
          r.reviewed_by,
          r.reviewed_at,
          coalesce(r.submission_status, 'not_submitted') as submission_status,
          r.override_cfp_status,
          r.override_cfp_deadline,
          r.override_conf_dates,
          CASE WHEN coalesce(trim(r.override_cfp_status),'')<>'' THEN r.override_cfp_status ELSE e.cfp_status END as effective_cfp_status,
          CASE WHEN coalesce(trim(r.override_cfp_deadline),'')<>'' THEN r.override_cfp_deadline ELSE e.cfp_deadline END as effective_cfp_deadline,
          CASE WHEN coalesce(trim(r.override_conf_dates),'')<>'' THEN r.override_conf_dates ELSE e.conf_dates END as effective_conf_dates
        FROM conference_events e
        LEFT JOIN conference_event_reviews r
          ON r.event_key = e.event_key
         AND lower(coalesce(r.market,'')) = lower(coalesce(e.market,''))
         AND lower(coalesce(r.customer,'')) = lower(coalesce(e.customer,''))
        WHERE lower(coalesce(e.market,'')) = ?
          AND lower(coalesce(e.customer,'')) = ?
          AND e.updated_at = (
            SELECT MAX(updated_at) FROM conference_events e2 WHERE e2.event_key = e.event_key
          )
        ORDER BY e.updated_at DESC
        LIMIT {row_limit}
        """
        rows = [dict(r) for r in conn.execute(q, (market.lower(), customer.lower())).fetchall()]

        output = io.StringIO()
        if rows:
            fieldnames = list(rows[0].keys())
            writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
        else:
            writer = csv.writer(output)
            writer.writerow(["no_data"])

        csv_bytes = ("\ufeff" + output.getvalue()).encode("utf-8")
        filename = f"pr_monitor_review_{(market or 'all').strip() or 'all'}_latest.csv"
        headers = {
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Type": "text/csv; charset=utf-8",
        }
        return Response(content=csv_bytes, media_type="text/csv", headers=headers)
    finally:
        conn.close()


@app.get("/api/companion/pilot-users")
async def companion_pilot_users(code: str = "FAMILY100", limit: int = 200):
    code_norm = (code or "").strip().upper()
    row_limit = max(1, min(int(limit or 200), 1000))
    conn = _patterns_conn()
    try:
        rows = conn.execute(
            """
            SELECT
                email,
                discount_code,
                discount_amount,
                stripe_customer_id,
                stripe_subscription_id,
                granted_at,
                updated_at,
                active
            FROM companion_access
            WHERE upper(coalesce(discount_code, '')) = ?
            ORDER BY coalesce(updated_at, granted_at) DESC
            LIMIT ?
            """,
            (code_norm, row_limit),
        ).fetchall()
    finally:
        conn.close()

    return {
        "ok": True,
        "code": code_norm,
        "count": len(rows),
        "users": [dict(r) for r in rows],
    }

@app.get("/channeled_results.html", response_class=HTMLResponse)
async def channeled_results_page():
    return FileResponse(str(static_dir / "patterns" / "channeled_results.html"))


@app.get("/channeled_assessment_24_questions.html", response_class=HTMLResponse)
async def channeled_assessment_24_questions_page():
    return FileResponse(str(static_dir / "patterns" / "channeled_assessment_24_questions.html"))


@app.get("/channeled_homepage.html", response_class=HTMLResponse)
async def channeled_homepage_page():
    return FileResponse(str(static_dir / "patterns" / "channeled_homepage.html"))

@app.get("/manifest.json")
async def app_manifest():
    return FileResponse(str(static_dir / "patterns" / "manifest.json"), media_type="application/manifest+json")

@app.get("/OneSignalSDKWorker.js")
async def onesignal_worker():
    return FileResponse(str(static_dir / "OneSignalSDKWorker.js"), media_type="application/javascript")

@app.get("/OneSignalSDKUpdaterWorker.js")
async def onesignal_updater_worker():
    return FileResponse(str(static_dir / "OneSignalSDKUpdaterWorker.js"), media_type="application/javascript")

@app.get("/api/companion/onesignal-config")
async def companion_onesignal_config():
    app_id = (os.getenv("ONESIGNAL_APP_ID") or "").strip()
    return {"ok": True, "app_id": app_id}

@app.post("/api/admin/test-push")
async def admin_test_push(request: Request):
    admin_secret = (os.getenv("ADMIN_SECRET") or "").strip()
    auth = (request.headers.get("authorization") or "").strip()
    expected = f"Bearer {admin_secret}" if admin_secret else ""

    if (not admin_secret) or (auth != expected):
        raise HTTPException(status_code=401, detail="unauthorized")

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="invalid_json")

    email = str((body or {}).get("email") or "").strip().lower()
    title = str((body or {}).get("title") or "Test").strip() or "Test"
    message = str((body or {}).get("message") or "Channeled push is working").strip() or "Channeled push is working"
    url = str((body or {}).get("url") or "https://channeled.org/companion").strip() or "https://channeled.org/companion"

    if not email:
        raise HTTPException(status_code=422, detail="email_required")

    result = onesignal_send_push(
        title=title,
        message=message,
        url=url,
        external_user_id=email,
        timeout_seconds=int(os.getenv("ONESIGNAL_TIMEOUT_SECONDS", "10")),
    )
    return result

@app.get("/api/admin/trigger-evening-nudge")
async def admin_trigger_evening_nudge(request: Request):
    admin_secret = (os.getenv("ADMIN_SECRET") or "").strip()
    auth = (request.headers.get("authorization") or "").strip()
    expected = f"Bearer {admin_secret}" if admin_secret else ""

    if (not admin_secret) or (auth != expected):
        raise HTTPException(status_code=401, detail="unauthorized")

    result = _send_evening_nudge()
    return result

@app.get("/access")
async def magic_access(token: str = Query("")):
    token = (token or "").strip()
    if not token:
        raise HTTPException(status_code=400, detail="token_required")

    conn = _patterns_conn()
    try:
        row = conn.execute(
            "SELECT token, email, used_at, expires_at FROM magic_tokens WHERE token = ?",
            (token,),
        ).fetchone()

        now_z = _now_z()
        if not row:
            raise HTTPException(status_code=401, detail="invalid_token")
        if row["used_at"]:
            raise HTTPException(status_code=401, detail="token_already_used")
        if (row["expires_at"] or "") <= now_z:
            raise HTTPException(status_code=401, detail="token_expired")

        conn.execute(
            "UPDATE magic_tokens SET used_at = ? WHERE token = ?",
            (now_z, token),
        )
        conn.commit()
        email = (row["email"] or "").strip().lower()
    finally:
        conn.close()

    response = RedirectResponse(url="/channeled_results.html", status_code=302)
    response.set_cookie(
        key="companion_session_email",
        value=email,
        max_age=60 * 60 * 24 * 7,
        httponly=True,
        secure=True,
        samesite="lax",
        domain="channeled.org",
        path="/",
    )
    return response


@app.get("/api/companion/access")
async def companion_access(request: Request):
    user = get_optional_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    has_access, reason, _ = _companion_access_decision(user["email"])
    return {"ok": True, "email": user["email"], "has_access": has_access, "reason": reason}


@app.post("/api/companion/notification-preferences")
async def companion_notification_preferences(request: Request):
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="invalid_json")

    email = str((body or {}).get("email") or "").strip().lower()
    if not email:
        raise HTTPException(status_code=422, detail="email_required")

    morning = bool((body or {}).get("morning", True))
    midday = bool((body or {}).get("midday", True))
    evening = bool((body or {}).get("evening", True))

    conn = _patterns_conn()
    try:
        conn.execute(
            """
            UPDATE companion_access
               SET notification_morning = ?,
                   notification_midday = ?,
                   notification_evening = ?,
                   updated_at = ?
             WHERE lower(email) = ?
                OR lower(COALESCE(assessment_email, '')) = ?
            """,
            (1 if morning else 0, 1 if midday else 0, 1 if evening else 0, _now_z(), email, email),
        )
        conn.commit()
    finally:
        conn.close()

    return {"ok": True, "email": email, "morning": morning, "midday": midday, "evening": evening}


@app.post("/api/companion/day-cutoff")
async def companion_day_cutoff(request: Request):
    email = _session_email_or_401(request)
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="invalid_json")
    cutoff = str((body or {}).get("day_cutoff_time") or "00:00").strip()
    if not re.match(r"^\d{2}:\d{2}$", cutoff):
        raise HTTPException(status_code=422, detail="invalid_day_cutoff_time")
    hh, mm = [int(x) for x in cutoff.split(":")]
    if hh < 0 or hh > 23 or mm < 0 or mm > 59:
        raise HTTPException(status_code=422, detail="invalid_day_cutoff_time")
    conn = _patterns_conn()
    try:
        conn.execute("UPDATE companion_access SET day_cutoff_time=?, updated_at=? WHERE lower(email)=lower(?)", (cutoff, _now_z(), email))
        conn.commit()
    finally:
        conn.close()
    return {"ok": True, "email": email, "day_cutoff_time": cutoff}


def _session_email_or_401(request: Request) -> str:
    email = (request.cookies.get("companion_session_email") or "").strip().lower()
    if not email:
        raise HTTPException(status_code=401, detail="No companion session")
    return email


def _logical_program_date_ct(conn: sqlite3.Connection, email: str) -> str:
    now_ct = datetime.now(ZoneInfo(COMPANION_CT_TZ))
    row = conn.execute("SELECT day_cutoff_time FROM companion_access WHERE lower(email)=lower(?) LIMIT 1", (email,)).fetchone()
    cutoff = str((row["day_cutoff_time"] if row else "00:00") or "00:00").strip()
    try:
      hh, mm = cutoff.split(":")
      cutoff_minutes = int(hh) * 60 + int(mm)
    except Exception:
      cutoff_minutes = 0
    now_minutes = now_ct.hour * 60 + now_ct.minute
    day = now_ct.date() if now_minutes >= cutoff_minutes else (now_ct.date() - timedelta(days=1))
    return day.strftime("%Y-%m-%d")


def _get_or_init_program_day(conn: sqlite3.Connection, email: str) -> int:
    try:
        pcols = {r[1] for r in conn.execute("PRAGMA table_info(companion_program_day_state)").fetchall()}
        if "last_progression_date_ct" not in pcols:
            conn.execute("ALTER TABLE companion_program_day_state ADD COLUMN last_progression_date_ct TEXT")
    except Exception:
        pass
    row = conn.execute("SELECT current_day FROM companion_program_day_state WHERE lower(email)=lower(?)", (email,)).fetchone()
    if row and int(row["current_day"] or 0) > 0:
        return int(row["current_day"])
    now_z = _now_z()
    conn.execute(
        "INSERT OR IGNORE INTO companion_program_day_state (email, current_day, current_day_date, last_advanced_at, last_progression_date_ct, updated_at) VALUES (?, 1, ?, ?, ?, ?)",
        (email, _logical_program_date_ct(conn, email), now_z, None, now_z),
    )
    return 1


def _stage_a_required_slots() -> List[str]:
    return [
        "goal_30d_primary",
        "goal_90d_direction",
        "purpose_why_now",
        "core_drivers_top3",
        "blockers_top2",
        "non_negotiable_boundary",
        "weekly_win_definition",
        "spiritual_language_preference",
    ]


def _stage_a_status(conn: sqlite3.Connection, email: str) -> Dict[str, Any]:
    srow = conn.execute(
        "SELECT id FROM onboarding_conversation_sessions WHERE lower(email)=lower(?) ORDER BY id DESC LIMIT 1",
        (email,),
    ).fetchone()
    required = _stage_a_required_slots()
    if not srow:
        return {"required_complete": False, "missing_slots": required, "confidence_tier": 1}
    slots = conn.execute(
        "SELECT slot_key, confirmed FROM onboarding_slot_values WHERE session_id=? AND lower(email)=lower(?)",
        (srow["id"], email),
    ).fetchall()
    have = {str(r["slot_key"]): int(r["confirmed"] or 0) for r in slots}
    missing = [k for k in required if have.get(k, 0) != 1]
    complete = len(missing) == 0
    return {"required_complete": complete, "missing_slots": missing, "confidence_tier": 2 if complete else 1, "session_id": srow["id"]}


def _snapshot_day_number(conn: sqlite3.Connection, email: str, snapshot_date: str) -> int:
    granted = conn.execute(
        "SELECT granted_at, updated_at FROM companion_access WHERE lower(email)=lower(?) OR lower(COALESCE(assessment_email,''))=lower(?) ORDER BY updated_at DESC LIMIT 1",
        (email, email),
    ).fetchone()
    base_raw = None
    if granted:
        base_raw = granted["granted_at"] or granted["updated_at"]
    try:
        base = datetime.fromisoformat(str(base_raw).replace("Z", "+00:00")).astimezone(ZoneInfo(COMPANION_CT_TZ)).date() if base_raw else datetime.now(ZoneInfo(COMPANION_CT_TZ)).date()
    except Exception:
        base = datetime.now(ZoneInfo(COMPANION_CT_TZ)).date()
    snap = datetime.strptime(snapshot_date, "%Y-%m-%d").date()
    return max(1, (snap - base).days + 1)


def _collect_day_payload(conn: sqlite3.Connection, email: str, snapshot_date: str):
    rows = conn.execute(
        "SELECT task_index, task_title, task_description, completed, note FROM daily_completions WHERE lower(email)=lower(?) AND task_date=? ORDER BY task_index ASC",
        (email, snapshot_date),
    ).fetchall()
    tasks_assigned, tasks_completed, task_notes = [], [], []
    for r in rows:
        task = {
            "task_index": int(r["task_index"]),
            "task_title": r["task_title"] or "",
            "task_description": r["task_description"] or "",
        }
        tasks_assigned.append(task)
        if int(r["completed"] or 0) == 1:
            tasks_completed.append(task)
        if (r["note"] or "").strip():
            task_notes.append({"task_index": int(r["task_index"]), "note": r["note"]})

    chat_rows = conn.execute(
        "SELECT task_index, role, message, created_at FROM companion_task_chats WHERE lower(email)=lower(?) AND task_date=? ORDER BY id ASC",
        (email, snapshot_date),
    ).fetchall()
    chat = [
        {
            "task_index": int(r["task_index"]),
            "role": r["role"],
            "message": r["message"],
            "created_at": r["created_at"],
        }
        for r in chat_rows
    ]
    return tasks_assigned, tasks_completed, task_notes, chat


def _ensure_daily_tasks_for_date(conn: sqlite3.Connection, email: str, task_date: str) -> int:
    """Idempotently seed daily_completions for a given local date (sequential day)."""
    program_day = _get_or_init_program_day(conn, email)
    seq_key = f"PD{program_day:03d}|"
    existing_count_row = conn.execute(
        "SELECT COUNT(*) AS c FROM daily_completions WHERE lower(email)=lower(?) AND task_date=?",
        (email, task_date),
    ).fetchone()
    if int(existing_count_row["c"] if existing_count_row else 0) > 0:
        return 0

    dt = datetime.strptime(task_date, "%Y-%m-%d").replace(tzinfo=ZoneInfo(COMPANION_CT_TZ))
    week_start = (dt - timedelta(days=dt.weekday())).strftime("%Y-%m-%d")

    plan_row = conn.execute(
        "SELECT plan_json FROM companion_weekly_plans WHERE lower(email)=lower(?) AND week_start=? ORDER BY id DESC LIMIT 1",
        (email, week_start),
    ).fetchone()

    plan_obj = {}
    if plan_row and plan_row["plan_json"]:
        try:
            plan_obj = json.loads(plan_row["plan_json"])
        except Exception:
            plan_obj = {}

    day_name = dt.strftime("%A")
    day_focus = ""
    for d in (plan_obj.get("days") or []):
        if isinstance(d, dict) and str(d.get("day") or "").strip().lower() == day_name.lower():
            day_focus = str(d.get("focus") or "").strip()
            break

    tasks = _plan_today_tasks(plan_obj, dt)
    if not tasks:
        return 0

    # Anti-repeat guardrail: check last 7 days of descriptions for this user
    lookback_start = (dt.date() - timedelta(days=7)).isoformat()
    recent_rows = conn.execute(
        """
        SELECT task_description FROM daily_completions
        WHERE lower(email)=lower(?) AND task_date>=? AND task_date<?
        """,
        (email, lookback_start, task_date),
    ).fetchall()
    recent_desc = set((str(r["task_description"] or "").strip().lower() for r in recent_rows if str(r["task_description"] or "").strip()))

    # Domain-aware alternates for diversification
    alternates = [
        "Define your one non-negotiable win for today in plain language, then complete the first step now.",
        "Schedule one focused block and remove one distraction before you begin.",
        "Choose one thing to finish today and write what 'done' looks like in one sentence.",
        "Identify one bottleneck slowing you down and remove or bypass it today.",
        "Complete one meaningful action in your priority area before checking other tasks.",
        "At day end, write two lines: what moved forward and what to adjust tomorrow.",
    ]

    diversified = []
    alt_i = 0
    for i in range(3):
        t = tasks[i] if i < len(tasks) and isinstance(tasks[i], dict) else {}
        title = str(t.get("title") or f"Focus {i+1}").strip() or f"Focus {i+1}"
        desc = str(t.get("description") or "").strip()
        if day_focus and day_focus.lower() not in desc.lower():
            desc = f"{desc} ({day_focus})" if desc else day_focus
        # Replace exact repeats from recent window with next alternate not used recently
        if desc.strip().lower() in recent_desc:
            while alt_i < len(alternates) and alternates[alt_i].strip().lower() in recent_desc:
                alt_i += 1
            if alt_i < len(alternates):
                desc = alternates[alt_i]
                alt_i += 1
            else:
                desc = f"{desc} — variation for {dt.strftime('%A')}"
        diversified.append((f"Day {program_day} · {title}", f"{seq_key}{desc}"))

    now_z = _now_z()
    seeded = 0
    for i, (title, desc) in enumerate(diversified, start=1):
        conn.execute(
            """
            INSERT INTO daily_completions (email, task_date, task_index, task_title, task_description, completed, note, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, 0, ?, ?, ?)
            ON CONFLICT(email, task_date, task_index) DO NOTHING
            """,
            (email, task_date, i, title, desc, "", now_z, now_z),
        )
        seeded += 1
    return seeded


def _upsert_daily_snapshot(conn: sqlite3.Connection, email: str, snapshot_date: str, evening_reflection_response: Optional[str] = None, tomorrow_preview: Optional[str] = None, free_note: Optional[str] = None):
    tasks_assigned, tasks_completed, task_notes, chat = _collect_day_payload(conn, email, snapshot_date)
    day_number = _snapshot_day_number(conn, email, snapshot_date)
    existing = conn.execute(
        "SELECT evening_reflection_response, tomorrow_preview, free_note, created_at FROM daily_snapshots WHERE lower(email)=lower(?) AND snapshot_date=?",
        (email, snapshot_date),
    ).fetchone()
    now_z = _now_z()
    conn.execute(
        """
        INSERT INTO daily_snapshots (
            email, snapshot_date, day_number, tasks_assigned, tasks_completed, task_notes, task_chat_history,
            evening_reflection_response, tomorrow_preview, free_note, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(email, snapshot_date) DO UPDATE SET
            day_number=excluded.day_number,
            tasks_assigned=excluded.tasks_assigned,
            tasks_completed=excluded.tasks_completed,
            task_notes=excluded.task_notes,
            task_chat_history=excluded.task_chat_history,
            evening_reflection_response=COALESCE(excluded.evening_reflection_response, daily_snapshots.evening_reflection_response),
            tomorrow_preview=COALESCE(excluded.tomorrow_preview, daily_snapshots.tomorrow_preview),
            free_note=COALESCE(excluded.free_note, daily_snapshots.free_note),
            updated_at=excluded.updated_at
        """,
        (
            email,
            snapshot_date,
            day_number,
            json.dumps(tasks_assigned),
            json.dumps(tasks_completed),
            json.dumps(task_notes),
            json.dumps(chat),
            evening_reflection_response,
            tomorrow_preview,
            free_note,
            (existing["created_at"] if existing and existing["created_at"] else now_z),
            now_z,
        ),
    )


@app.post("/api/companion/complete-task")
async def companion_complete_task(request: Request):
    session_email = _session_email_or_401(request)
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="invalid_json")

    email = str((body or {}).get("email") or session_email).strip().lower()
    if email != session_email:
        raise HTTPException(status_code=403, detail="email_mismatch")

    task_date = str((body or {}).get("task_date") or "").strip()
    task_index = int((body or {}).get("task_index") or 0)
    task_title = str((body or {}).get("task_title") or "").strip()
    task_description = str((body or {}).get("task_description") or "").strip()
    completed = 1 if bool((body or {}).get("completed", False)) else 0
    note_raw = (body or {}).get("note")
    note = None if note_raw is None else str(note_raw).strip()

    if not task_date or not re.match(r"^\d{4}-\d{2}-\d{2}$", task_date):
        raise HTTPException(status_code=422, detail="invalid_task_date")
    if task_index not in (1, 2, 3):
        raise HTTPException(status_code=422, detail="invalid_task_index")

    now_z = _now_z()
    conn = _patterns_conn()
    try:
        conn.execute(
            """
            INSERT INTO daily_completions (email, task_date, task_index, task_title, task_description, completed, note, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(email, task_date, task_index) DO UPDATE SET
                task_title=excluded.task_title,
                task_description=excluded.task_description,
                completed=excluded.completed,
                note=excluded.note,
                updated_at=excluded.updated_at
            """,
            (email, task_date, task_index, task_title, task_description, completed, note, now_z, now_z),
        )
        _upsert_daily_snapshot(conn, email, task_date)
        if completed == 1:
            _get_or_init_program_day(conn, email)
            state = conn.execute("SELECT current_day, current_day_date, last_progression_date_ct FROM companion_program_day_state WHERE lower(email)=lower(?)", (email,)).fetchone()
            if state:
                ct_today = _logical_program_date_ct(conn, email)
                current_day_date = str(state["current_day_date"] or "")
                last_prog = str(state["last_progression_date_ct"] or "")
                if current_day_date != task_date:
                    conn.execute("UPDATE companion_program_day_state SET current_day_date=?, updated_at=? WHERE lower(email)=lower(?)", (task_date, _now_z(), email))
                elif last_prog != ct_today:
                    conn.execute("UPDATE companion_program_day_state SET current_day=current_day+1, current_day_date=?, last_advanced_at=?, last_progression_date_ct=?, updated_at=? WHERE lower(email)=lower(?)", (ct_today, _now_z(), ct_today, _now_z(), email))
        conn.commit()
    finally:
        conn.close()

    return {"ok": True, "email": email, "task_date": task_date, "task_index": task_index, "completed": bool(completed), "note": note}


@app.get("/api/companion/daily-completions")
async def companion_daily_completions(request: Request, date: str = Query("")):
    email = _session_email_or_401(request)
    if not date or not re.match(r"^\d{4}-\d{2}-\d{2}$", date):
        raise HTTPException(status_code=422, detail="invalid_date")

    conn = _patterns_conn()
    try:
        _ensure_daily_tasks_for_date(conn, email, date)
        conn.commit()
        rows = conn.execute(
            """
            SELECT task_index, task_title, task_description, completed, note, task_date
            FROM daily_completions
            WHERE lower(email)=lower(?) AND task_date=?
            ORDER BY task_index ASC
            """,
            (email, date),
        ).fetchall()
    finally:
        conn.close()

    return {
        "ok": True,
        "date": date,
        "email": email,
        "rows": [
            {
                "task_index": int(r["task_index"]),
                "task_title": r["task_title"],
                "task_description": r["task_description"],
                "completed": bool(r["completed"]),
                "note": r["note"],
            }
            for r in rows
        ],
    }


@app.post("/api/companion/init-day")
async def companion_init_day(request: Request):
    email = _session_email_or_401(request)
    ct_now = datetime.now(ZoneInfo(COMPANION_CT_TZ))
    today_str = ct_now.strftime("%Y-%m-%d")
    week_start_dt = ct_now - timedelta(days=ct_now.weekday())
    week_start = week_start_dt.strftime("%Y-%m-%d")

    conn = _patterns_conn()
    try:
        inserted = _ensure_daily_tasks_for_date(conn, email, today_str)
        _upsert_daily_snapshot(conn, email, today_str)
        conn.commit()
    finally:
        conn.close()

    return {"ok": True, "initialized": bool(inserted), "task_date": today_str}


@app.post("/api/companion/skip-day")
async def companion_skip_day(request: Request):
    email = _session_email_or_401(request)
    conn = _patterns_conn()
    try:
        current_day = _get_or_init_program_day(conn, email)
        now_ct = _logical_program_date_ct(conn, email)
        state = conn.execute("SELECT last_progression_date_ct FROM companion_program_day_state WHERE lower(email)=lower(?)", (email,)).fetchone()
        last_prog = str(state["last_progression_date_ct"] or "") if state else ""
        if last_prog == now_ct:
            return {"ok": False, "email": email, "blocked": True, "message": "Next day unlocks tomorrow.", "current_day": current_day}
        conn.execute(
            "UPDATE companion_program_day_state SET current_day=?, current_day_date=?, last_advanced_at=?, last_progression_date_ct=?, updated_at=? WHERE lower(email)=lower(?)",
            (current_day + 1, now_ct, _now_z(), now_ct, _now_z(), email),
        )
        conn.commit()
    finally:
        conn.close()
    return {"ok": True, "email": email, "skipped_to_day": current_day + 1}


@app.post("/api/onboarding/conversation/start")
async def onboarding_conversation_start(request: Request):
    email = _session_email_or_401(request)
    conn = _patterns_conn()
    try:
        now_z = _now_z()
        conn.execute(
            "INSERT INTO onboarding_conversation_sessions (email, stage, status, created_at, updated_at) VALUES (?, 'A', 'in_progress', ?, ?)",
            (email, now_z, now_z),
        )
        sid = conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
        conn.commit()
    finally:
        conn.close()
    return {
        "ok": True,
        "session_id": sid,
        "stage": "A",
        "first_prompt": "What are you trying to accomplish or change most right now?"
    }


@app.post("/api/onboarding/conversation/respond")
async def onboarding_conversation_respond(request: Request):
    email = _session_email_or_401(request)
    body = await request.json()
    session_id = int((body or {}).get("session_id") or 0)
    response_text = str((body or {}).get("response_text") or "").strip()
    input_mode = str((body or {}).get("input_mode") or "text").strip().lower()
    if not session_id or not response_text:
        raise HTTPException(status_code=422, detail="session_id_and_response_required")

    # Stage A extraction mapping logic (broad prompt response -> structured slots)
    extracted = []
    low = response_text.lower()

    def add_slot(slot_key: str, value: dict, confidence: float):
        extracted.append({
            "slot_key": slot_key,
            "slot_value_json": json.dumps(value),
            "confidence": confidence,
        })

    # 1) Goals / outcomes
    if len(response_text) >= 12:
        add_slot("goal_30d_primary", {"text": response_text}, 0.78)
    if any(k in low for k in ["90 day", "90-day", "quarter", "3 month", "3-month"]):
        add_slot("goal_90d_direction", {"text": response_text}, 0.72)

    # 2) Purpose / why now
    if any(k in low for k in ["because", "so that", "for my", "important", "matters", "purpose"]):
        add_slot("purpose_why_now", {"text": response_text}, 0.68)

    # 3) Core drivers hints
    driver_hits = [k for k in ["faith", "family", "health", "work", "business", "financial", "money", "service", "impact"] if k in low]
    if driver_hits:
        add_slot("core_drivers_top3", {"detected": driver_hits[:3], "text": response_text}, 0.66)

    # 4) Blockers
    if any(k in low for k in ["hard", "stuck", "blocked", "overwhelmed", "busy", "tired", "distracted", "confused"]):
        add_slot("blockers_top2", {"signal": "friction_present", "text": response_text}, 0.74)

    # 5) Boundaries / non-negotiables
    if any(k in low for k in ["won't", "will not", "non-negotiable", "must not", "boundary", "never"]):
        add_slot("non_negotiable_boundary", {"text": response_text}, 0.7)

    # 6) Weekly win / measurable success
    if any(k in low for k in ["this week", "weekly", "win", "measure", "metric", "by friday"]):
        add_slot("weekly_win_definition", {"text": response_text}, 0.69)

    # 7) Faith-lens preference
    if any(k in low for k in ["scripture", "christian", "jesus", "bible", "faith-based", "faith based"]):
        pref = "faith_forward"
        if any(k in low for k in ["neutral", "practical first", "light scripture"]):
            pref = "neutral_with_scripture"
        if any(k in low for k in ["no scripture", "non spiritual", "avoid spiritual"]):
            pref = "avoid_spiritual"
        add_slot("spiritual_language_preference", {"preference": pref, "text": response_text}, 0.76)

    # 8) Scripture depth (optional stage-B signal if explicitly provided early)
    if any(k in low for k in ["heavy scripture", "more scripture", "light scripture", "moderate scripture"]):
        level = "moderate"
        if "heavy" in low or "more scripture" in low:
            level = "strong"
        if "light" in low:
            level = "light"
        add_slot("scripture_integration_level", {"level": level, "text": response_text}, 0.7)

    conn = _patterns_conn()
    try:
        now_z = _now_z()
        conn.execute("UPDATE onboarding_conversation_sessions SET input_mode_last=?, updated_at=? WHERE id=? AND lower(email)=lower(?)", (input_mode, now_z, session_id, email))
        for e in extracted:
            existing = conn.execute(
                "SELECT id FROM onboarding_slot_values WHERE session_id=? AND lower(email)=lower(?) AND slot_key=? ORDER BY id DESC LIMIT 1",
                (session_id, email, e["slot_key"]),
            ).fetchone()
            if existing:
                conn.execute(
                    """
                    UPDATE onboarding_slot_values
                       SET slot_value_json=?, confidence=?, source='broad_prompt', confirmed=0, updated_at=?
                     WHERE id=?
                    """,
                    (e["slot_value_json"], e["confidence"], now_z, existing["id"]),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO onboarding_slot_values (session_id, email, slot_key, slot_value_json, confidence, source, confirmed, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, 'broad_prompt', 0, ?, ?)
                    """,
                    (session_id, email, e["slot_key"], e["slot_value_json"], e["confidence"], now_z, now_z),
                )
        conn.commit()
    finally:
        conn.close()

    summary = {
        "goal_30d_primary": "Captured" if any(e["slot_key"] == "goal_30d_primary" for e in extracted) else "Not yet clear",
        "blockers_signal": "Captured" if any(e["slot_key"] == "blockers_top2" for e in extracted) else "Not yet clear"
    }

    recap_lines = []
    for e in extracted:
        try:
            obj = json.loads(e["slot_value_json"])
        except Exception:
            obj = {}
        label = str(e["slot_key"]).replace('_', ' ')
        text_val = ''
        if isinstance(obj, dict):
            text_val = str(obj.get('text') or obj.get('preference') or obj.get('level') or obj.get('detected') or '').strip()
        recap_lines.append(f"- {label}: {text_val or 'captured'}")

    recap_text = "Here’s what I heard:\n" + ("\n".join(recap_lines) if recap_lines else "- I captured your response.") + "\n\nDid I get that right?"

    return {
        "ok": True,
        "session_id": session_id,
        "extracted_count": len(extracted),
        "summary": summary,
        "recap_text": recap_text,
        "confirmation_prompt": "Here’s what I heard. Did I get that right?"
    }


@app.post("/api/onboarding/conversation/confirm")
async def onboarding_conversation_confirm(request: Request):
    email = _session_email_or_401(request)
    body = await request.json()
    session_id = int((body or {}).get("session_id") or 0)
    confirmed = bool((body or {}).get("confirmed"))
    corrections = (body or {}).get("corrections") or {}
    if not session_id:
        raise HTTPException(status_code=422, detail="session_id_required")

    conn = _patterns_conn()
    try:
        now_z = _now_z()

        # Apply explicit corrections first (canonicalization)
        if isinstance(corrections, dict) and corrections:
            for slot_key, value in corrections.items():
                value_json = json.dumps(value if isinstance(value, (dict, list)) else {"text": str(value)})
                existing = conn.execute(
                    "SELECT id FROM onboarding_slot_values WHERE session_id=? AND lower(email)=lower(?) AND slot_key=? ORDER BY id DESC LIMIT 1",
                    (session_id, email, str(slot_key)),
                ).fetchone()
                if existing:
                    conn.execute(
                        """
                        UPDATE onboarding_slot_values
                           SET slot_value_json=?, source='manual_correction', confirmed=1, updated_at=?
                         WHERE id=?
                        """,
                        (value_json, now_z, existing["id"]),
                    )
                else:
                    conn.execute(
                        """
                        INSERT INTO onboarding_slot_values (session_id, email, slot_key, slot_value_json, confidence, source, confirmed, created_at, updated_at)
                        VALUES (?, ?, ?, ?, 1.0, 'manual_correction', 1, ?, ?)
                        """,
                        (session_id, email, str(slot_key), value_json, now_z, now_z),
                    )

        if confirmed:
            # Confirm all current inferred slots not explicitly corrected
            conn.execute(
                """
                UPDATE onboarding_slot_values
                   SET confirmed=1, updated_at=?
                 WHERE session_id=? AND lower(email)=lower(?)
                """,
                (now_z, session_id, email),
            )

            # Task 5 handoff: persist confirmed Stage A slot values into core companion fields
            rows = conn.execute(
                "SELECT slot_key, slot_value_json FROM onboarding_slot_values WHERE session_id=? AND lower(email)=lower(?) AND confirmed=1",
                (session_id, email),
            ).fetchall()
            slot_map = {str(r["slot_key"]): str(r["slot_value_json"] or "") for r in rows}

            def _slot_text(key: str) -> str:
                raw = slot_map.get(key, "")
                if not raw:
                    return ""
                try:
                    obj = json.loads(raw)
                    if isinstance(obj, dict):
                        if isinstance(obj.get("text"), str):
                            return obj.get("text", "").strip()
                        return json.dumps(obj)
                    return str(obj)
                except Exception:
                    return str(raw)

            context_summary = _slot_text("goal_30d_primary")
            friction_patterns = _slot_text("blockers_top2")
            focus_area = _slot_text("goal_90d_direction") or _slot_text("core_drivers_top3")
            spiritual_pref = ""
            scripture_level = ""
            faith_bounds = _slot_text("faith_boundaries")
            if slot_map.get("spiritual_language_preference"):
                try:
                    p = json.loads(slot_map.get("spiritual_language_preference") or "{}")
                    spiritual_pref = str((p.get("preference") if isinstance(p, dict) else "") or "").strip()
                except Exception:
                    spiritual_pref = ""
            if slot_map.get("scripture_integration_level"):
                try:
                    lv = json.loads(slot_map.get("scripture_integration_level") or "{}")
                    scripture_level = str((lv.get("level") if isinstance(lv, dict) else "") or "").strip()
                except Exception:
                    scripture_level = ""

            existing_intake = conn.execute(
                "SELECT id FROM companion_intake WHERE lower(email)=lower(?) ORDER BY id DESC LIMIT 1",
                (email,),
            ).fetchone()

            if existing_intake:
                conn.execute(
                    """
                    UPDATE companion_intake
                       SET focus_area = COALESCE(NULLIF(?, ''), focus_area),
                           context_summary = COALESCE(NULLIF(?, ''), context_summary),
                           friction_patterns = COALESCE(NULLIF(?, ''), friction_patterns)
                     WHERE id = ?
                    """,
                    (focus_area, context_summary, friction_patterns, existing_intake["id"]),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO companion_intake (email, focus_area, context_summary, friction_patterns, coaching_style_intensity, coaching_style_approach, created_at)
                    VALUES (?, ?, ?, ?, '', '', ?)
                    """,
                    (email, focus_area, context_summary, friction_patterns, now_z),
                )

            # Persist stage metadata + confidence and version to companion_access
            conn.execute(
                """
                UPDATE companion_access
                   SET onboarding_version='conversation-first-v1',
                       context_confidence_tier=2,
                       intake_completed=1,
                       spiritual_language_preference=COALESCE(NULLIF(?, ''), spiritual_language_preference),
                       scripture_integration_level=COALESCE(NULLIF(?, ''), scripture_integration_level),
                       faith_boundaries=COALESCE(NULLIF(?, ''), faith_boundaries),
                       updated_at=?
                 WHERE lower(email)=lower(?)
                """,
                (spiritual_pref, scripture_level, faith_bounds, now_z, email),
            )

            conn.execute(
                "UPDATE onboarding_conversation_sessions SET status='confirmed', updated_at=? WHERE id=? AND lower(email)=lower(?)",
                (now_z, session_id, email),
            )
        else:
            conn.execute(
                "UPDATE onboarding_conversation_sessions SET status='awaiting_confirmation', updated_at=? WHERE id=? AND lower(email)=lower(?)",
                (now_z, session_id, email),
            )

        conn.commit()
    finally:
        conn.close()

    return {"ok": True, "session_id": session_id, "confirmed": confirmed, "corrections_applied": len(corrections) if isinstance(corrections, dict) else 0}


@app.get("/api/onboarding/conversation/status")
async def onboarding_conversation_status(request: Request):
    email = _session_email_or_401(request)
    conn = _patterns_conn()
    try:
        srow = conn.execute("SELECT id, stage, status, created_at, updated_at FROM onboarding_conversation_sessions WHERE lower(email)=lower(?) ORDER BY id DESC LIMIT 1", (email,)).fetchone()
        st = _stage_a_status(conn, email)
        if not srow:
            return {"ok": True, "stage": "A", "required_complete": st["required_complete"], "missing_slots": st["missing_slots"], "confidence_tier": st["confidence_tier"]}
        return {"ok": True, "session_id": srow["id"], "stage": srow["stage"], "status": srow["status"], "required_complete": st["required_complete"], "missing_slots": st["missing_slots"], "confidence_tier": st["confidence_tier"]}
    finally:
        conn.close()


@app.get("/api/companion/snapshots")
async def companion_snapshots(request: Request):
    email = _session_email_or_401(request)
    conn = _patterns_conn()
    try:
        rows = conn.execute(
            """
            SELECT id, email, snapshot_date, day_number, tasks_assigned, tasks_completed, task_notes,
                   task_chat_history, evening_reflection_response, tomorrow_preview, free_note, created_at, updated_at
            FROM daily_snapshots
            WHERE lower(email)=lower(?)
            ORDER BY day_number DESC, snapshot_date DESC
            """,
            (email,),
        ).fetchall()
    finally:
        conn.close()

    def _j(v):
        if not v:
            return []
        try:
            return json.loads(v)
        except Exception:
            return []

    return {
        "ok": True,
        "email": email,
        "rows": [
            {
                "id": r["id"],
                "snapshot_date": r["snapshot_date"],
                "day_number": r["day_number"],
                "tasks_assigned": _j(r["tasks_assigned"]),
                "tasks_completed": _j(r["tasks_completed"]),
                "task_notes": _j(r["task_notes"]),
                "task_chat_history": _j(r["task_chat_history"]),
                "evening_reflection_response": r["evening_reflection_response"],
                "tomorrow_preview": r["tomorrow_preview"],
                "free_note": r["free_note"],
                "created_at": r["created_at"],
                "updated_at": r["updated_at"],
            }
            for r in rows
        ],
    }


@app.post("/api/companion/task-explain")
async def companion_task_explain(request: Request):
    email = _session_email_or_401(request)
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="invalid_json")

    task_title = str((body or {}).get("task_title") or "").strip()
    task_description = str((body or {}).get("task_description") or "").strip()
    profile = (body or {}).get("profile") or {}
    primary = str(profile.get("primary") or profile.get("archetype") or "Architect")
    secondary = str(profile.get("secondary") or "Navigator")

    # Get database connection to compute user state
    conn = sqlite3.connect(str(DB_PATH))
    context = {
        "email": email,
        "task_title": task_title,
        "task_description": task_description,
        "archetype": primary,
        "secondary": secondary
    }
    
    # Enrich context with user state classification
    context = enrich_companion_context(conn, context)
    
    # Add implementation-intention structure to the response
    system_prompt = (
        f"You are a coaching companion for a {primary} / {secondary} archetype. "
        "Explain why the following task matters specifically for their wiring, in 3-4 sentences, conversational and direct. No fluff. "
        "Write at a 12th grade reading level. Use clear direct language. No coaching jargon or abstract frameworks without plain explanation. "
        "\n\nAfter your explanation, provide a clear Implementation-Intention structure with these parts clearly labeled:\n"
        "1. IF-THEN PLAN: Create an implementation intention in if-then format that specifies when and where they'll complete this task\n"
        "2. TIMEBOX: Suggest a specific time duration (15-60 minutes)\n"
        "3. TRIGGER CUE: Give them an environmental or contextual trigger to start\n"
        "4. DONE DEFINITION: Define exactly what 'done' looks like for this task in one sentence\n\n"
        "Never end your response with a question. "
        f"{COMPANION_FRAMEWORK_LOCK_BLOCK} "
        f"{COMPANION_ARCHETYPE_INTEGRITY_BLOCK}"
    )
    user_prompt = f"Task title: {task_title}\nTask description: {task_description}"
    text = _call_companion_llm(system_prompt, user_prompt, model="claude-sonnet-4-20250514", 
                             max_tokens=500, context=context)

    # Add metadata about user state and intervention type
    response = {
        "ok": True, 
        "email": email, 
        "text": text.strip(),
        "user_state": context.get("user_state", UserState.UNKNOWN),
        "intervention_type": context.get("intervention_type", InterventionType.UNBLOCK)
    }
    
    return response


@app.post("/api/companion/task-chat")
async def companion_task_chat(request: Request):
    email = _session_email_or_401(request)
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="invalid_json")

    task_index = int((body or {}).get("task_index") or 0)
    task_date = str((body or {}).get("task_date") or "").strip() or datetime.now(ZoneInfo("America/Chicago")).strftime("%Y-%m-%d")
    task_title = str((body or {}).get("task_title") or "").strip()
    task_description = str((body or {}).get("task_description") or "").strip()
    user_message = str((body or {}).get("message") or "").strip()
    profile = (body or {}).get("profile") or {}
    primary = str(profile.get("primary") or profile.get("archetype") or "Architect")
    secondary = str(profile.get("secondary") or "Navigator")

    if task_index not in (1, 2, 3):
        raise HTTPException(status_code=422, detail="invalid_task_index")
    if not user_message:
        raise HTTPException(status_code=422, detail="message_required")

    conn = _patterns_conn()
    now_z = _now_z()
    try:
        conn.execute(
            "INSERT INTO companion_task_chats (email, task_date, task_index, role, message, created_at) VALUES (?, ?, ?, 'user', ?, ?)",
            (email, task_date, task_index, user_message, now_z),
        )

        history_rows = conn.execute(
            """
            SELECT role, message FROM companion_task_chats
            WHERE lower(email)=lower(?) AND task_date=? AND task_index=?
            ORDER BY id DESC LIMIT 4
            """,
            (email, task_date, task_index),
        ).fetchall()
        history_rows = list(reversed(history_rows))

        history_text = "\n".join([f"{r['role']}: {r['message']}" for r in history_rows])
        system_prompt = (
            f"You are a coaching companion for a {primary} / {secondary} archetype. Keep responses under 100 words, specific, practical, and direct. "
            "Write at a 12th grade reading level. Use clear direct language. No coaching jargon or abstract frameworks without plain explanation. Never end your response with a question. "
            f"{COMPANION_FRAMEWORK_LOCK_BLOCK} "
            f"{COMPANION_ARCHETYPE_INTEGRITY_BLOCK}"
            "Responses must be complete and self-contained. Do not invite further conversation. Do not include phrases like 'does that help', 'let me know', 'feel free to ask', or similar closers."
        )
        user_prompt = (
            f"Task: {task_title}\nDescription: {task_description}\n"
            f"Recent chat:\n{history_text}\n\nRespond to the latest user message helpfully."
        )
        assistant_text = _call_companion_llm(system_prompt, user_prompt, model="claude-sonnet-4-20250514", max_tokens=220).strip()
        assistant_text = re.sub(r"\s*(does that help\??|let me know if you want more\.?|let me know\.?|feel free to ask\.?|if you want,.*)$", "", assistant_text, flags=re.IGNORECASE)
        assistant_text = assistant_text.rstrip()
        if assistant_text.endswith("?"):
            assistant_text = assistant_text.rstrip("?").rstrip() + "."

        conn.execute(
            "INSERT INTO companion_task_chats (email, task_date, task_index, role, message, created_at) VALUES (?, ?, ?, 'assistant', ?, ?)",
            (email, task_date, task_index, assistant_text, _now_z()),
        )
        _upsert_daily_snapshot(conn, email, task_date)
        conn.commit()
    finally:
        conn.close()

    return {"ok": True, "text": assistant_text}


@app.post("/api/companion/evening-reflection")
async def companion_evening_reflection(request: Request):
    email = _session_email_or_401(request)
    gate_conn = _patterns_conn()
    try:
        st = _stage_a_status(gate_conn, email)
    finally:
        gate_conn.close()
    if not st.get("required_complete"):
        return JSONResponse(content={
            "ok": True,
            "limited": True,
            "reason": "stage_a_incomplete",
            "missing_slots": st.get("missing_slots", []),
            "reflection_response": "Complete your onboarding context to unlock fully personalized reflection and next-day planning.",
            "tomorrow_preview": "Complete onboarding context first — then your tailored tomorrow plan will be generated.",
            "tomorrow_plan": {
                "theme": "Build Foundation",
                "tasks": [
                    {"title": "Complete onboarding", "description": "Finish your onboarding context questions."},
                    {"title": "Set one clear goal", "description": "Write one 30-day outcome in plain language."},
                    {"title": "Name one blocker", "description": "Identify one blocker and one action to reduce it."}
                ]
            }
        })
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="invalid_json")

    tasks = (body or {}).get("tasks") or []
    free_text = str((body or {}).get("free_text") or "").strip()
    profile = (body or {}).get("profile") or {}
    primary = str(profile.get("primary") or profile.get("archetype") or "Architect")
    secondary = str(profile.get("secondary") or "Navigator")
    context = str(profile.get("context") or "personal")

    ct_now = datetime.now(ZoneInfo(COMPANION_CT_TZ))
    today_str = ct_now.strftime("%Y-%m-%d")
    tomorrow_dt = ct_now + timedelta(days=1)
    tomorrow_str = tomorrow_dt.strftime("%Y-%m-%d")

    conn = _patterns_conn()
    try:
        for t in tasks:
            idx = int(t.get("task_index") or 0)
            if idx not in (1, 2, 3):
                continue
            conn.execute(
                """
                INSERT INTO daily_completions (email, task_date, task_index, task_title, task_description, completed, note, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(email, task_date, task_index) DO UPDATE SET
                    task_title=excluded.task_title,
                    task_description=excluded.task_description,
                    completed=excluded.completed,
                    note=excluded.note,
                    updated_at=excluded.updated_at
                """,
                (
                    email,
                    today_str,
                    idx,
                    str(t.get("task_title") or "").strip(),
                    str(t.get("task_description") or "").strip(),
                    1 if bool(t.get("completed")) else 0,
                    str(t.get("note") or "").strip() or None,
                    _now_z(),
                    _now_z(),
                ),
            )

        completed_list = [t for t in tasks if bool(t.get("completed"))]
        completed_summary = ", ".join([str(t.get("task_title") or f"Task {t.get('task_index')}") for t in completed_list]) or "none completed"

        # Compute user state and appropriate intervention
        user_context = {
            "email": email,
            "archetype": primary,
            "secondary": secondary
        }
        user_context = enrich_companion_context(conn, user_context)
        
        # Include state and intervention in system prompt
        system_prompt = (
            "You are a coaching companion. Return ONLY valid JSON with keys: tomorrow_plan (object), reflection_response (string), tomorrow_preview (string). "
            "Tomorrow plan must include theme and exactly 3 tasks with title + description. Reflection response must be under 100 words, specific, include one archetype-specific insight, and mention completed tasks concretely. "
            "Write at a 12th grade reading level. Use clear direct language. No coaching jargon or abstract frameworks without plain explanation. Never end your response with a question. "
            "Each task must follow the Implementation-Intention format with these components: specific action, trigger cue, timebox duration, and done definition. "
            f"{COMPANION_FRAMEWORK_LOCK_BLOCK} "
            f"{COMPANION_ARCHETYPE_INTEGRITY_BLOCK}"
        )
        user_prompt = (
            f"Profile: {primary} / {secondary} ({context})\n"
            f"User State: {user_context.get('user_state', 'unknown')}\n"
            f"Intervention Type: {user_context.get('intervention_type', 'unblock')}\n"
            f"Today's completed tasks: {completed_summary}\n"
            f"All task data: {json.dumps(tasks)}\n"
            f"Free text: {free_text}\n"
            f"Generate tomorrow's plan for date {tomorrow_str}, plus a concise reflection and one-sentence tomorrow preview in format: 'Tomorrow: [theme] — 3 tasks waiting in the morning.'"
        )

        # Add retry logic with exponential backoff
        max_attempts = 3
        backoff_seconds = 1
        parsed = {}
        
        for attempt in range(max_attempts):
            try:
                raw_text = _call_companion_llm(system_prompt, user_prompt, model="claude-sonnet-4-20250514", max_tokens=1200, context=user_context)
                start = raw_text.find("{")
                end = raw_text.rfind("}")
                if start == -1 or end == -1:
                    raise ValueError(f"Invalid JSON structure in LLM response (attempt {attempt+1})")
                
                parsed = json.loads(raw_text[start:end+1])
                
                # Validate required fields exist
                if not isinstance(parsed, dict):
                    raise ValueError(f"Response not a dictionary object (attempt {attempt+1})")
                if not isinstance(parsed.get("tomorrow_plan"), dict):
                    raise ValueError(f"Missing valid tomorrow_plan (attempt {attempt+1})")
                if not parsed.get("reflection_response"):
                    raise ValueError(f"Missing reflection_response (attempt {attempt+1})")
                
                # If we get here, parsing succeeded
                break
                
            except Exception as e:
                logger.error(f"Reflection generation failed (attempt {attempt+1}): {str(e)}")
                
                # On final failure, send urgent email alert
                if attempt == max_attempts - 1:
                    try:
                        # Create fallback response with basic structure
                        parsed = {
                            "reflection_response": f"You completed {len(completed_list)} out of 3 tasks today. Keep building momentum with small wins tomorrow.",
                            "tomorrow_preview": f"Tomorrow: Building momentum — 3 tasks waiting in the morning.",
                            "tomorrow_plan": {
                                "theme": "Building momentum",
                                "tasks": [
                                    {"title": "Focus 1", "description": "Choose one high-impact task and complete it before noon."},
                                    {"title": "Focus 2", "description": "Take a 20-minute break mid-day to clear your mind and reset."},
                                    {"title": "Focus 3", "description": "Review your progress at the end of the day and celebrate small wins."}
                                ]
                            }
                        }
                        
                        # Send alert email about the failure
                        import smtplib
                        from email.mime.text import MIMEText
                        from email.mime.multipart import MIMEMultipart
                        
                        try:
                            credentials_path = "/home/ubuntu/.openclaw/.gmail_credentials"
                            creds = {}
                            with open(credentials_path, "r") as f:
                                for line in f:
                                    if "=" in line:
                                        key, value = line.strip().split("=", 1)
                                        creds[key.strip()] = value.strip()
                            
                            msg = MIMEMultipart()
                            msg["Subject"] = f"[URGENT] Reflection Generation Failure for {email}"
                            msg["From"] = creds.get("GMAIL_USER") or "solomonpaulmatthews@gmail.com"
                            msg["To"] = "mattolejarczyk70@gmail.com"
                            
                            body = f"""
URGENT: Reflection Generation Failed

User: {email}
Date: {today_str}
Attempts: {max_attempts}
Last error: {str(e)}

Action taken: Created a fallback reflection to prevent user-facing error.
Completed tasks: {completed_summary}

This may indicate an issue with the Claude API or invalid input. Please investigate.
"""
                            msg.attach(MIMEText(body, "plain"))
                            
                            with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
                                server.login(creds.get("GMAIL_USER") or "solomonpaulmatthews@gmail.com", 
                                             creds.get("GMAIL_APP_PASSWORD") or creds.get("APP_PASSWORD") or "")
                                server.send_message(msg)
                            
                            logger.info(f"Sent alert email for reflection generation failure: {email}")
                        except Exception as email_err:
                            logger.error(f"Failed to send alert email: {str(email_err)}")
                    except Exception as alert_err:
                        logger.error(f"Failed to process alert for reflection failure: {str(alert_err)}")
                
                # If not the last attempt, backoff and try again
                if attempt < max_attempts - 1:
                    time.sleep(backoff_seconds)
                    backoff_seconds *= 2

        tomorrow_plan = parsed.get("tomorrow_plan") if isinstance(parsed, dict) else {}
        if not isinstance(tomorrow_plan, dict):
            tomorrow_plan = {}

        tomorrow_week_key = tomorrow_dt.strftime("%Y-%m-%d")
        conn.execute(
            """
            INSERT INTO companion_weekly_continuity (email, week_key, summary_json, created_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(email, week_key) DO UPDATE SET
                summary_json=excluded.summary_json,
                created_at=excluded.created_at
            """,
            (email, week_key, json.dumps(prior_week_continuity), _now_z()),
        )

        conn.execute(
            """
            INSERT INTO companion_weekly_plans (email, week_key, week_start, timezone, status, model, archetype, plan_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(email, week_key) DO UPDATE SET
                week_start=excluded.week_start,
                timezone=excluded.timezone,
                status=excluded.status,
                model=excluded.model,
                archetype=excluded.archetype,
                plan_json=excluded.plan_json,
                updated_at=excluded.updated_at
            """,
            (email, tomorrow_week_key, tomorrow_str, COMPANION_CT_TZ, "generated", "claude-sonnet-4-20250514", primary, json.dumps(tomorrow_plan), _now_z(), _now_z()),
        )
        _upsert_daily_snapshot(
            conn,
            email,
            today_str,
            evening_reflection_response=str(parsed.get("reflection_response") or "").strip() or None,
            tomorrow_preview=str(parsed.get("tomorrow_preview") or "").strip() or None,
            free_note=free_text or None,
        )
        conn.commit()
    finally:
        conn.close()

    return {
        "ok": True,
        "reflection_response": str(parsed.get("reflection_response") or "").strip(),
        "tomorrow_preview": str(parsed.get("tomorrow_preview") or "").strip(),
        "tomorrow_plan": tomorrow_plan,
        "tomorrow_date": tomorrow_str,
    }

@app.post("/api/companion/request-access")
async def companion_request_access(request: Request):
    # Security posture: always return {"ok": true} to avoid revealing account existence.
    try:
        body = await request.json()
    except Exception:
        body = {}

    email = str((body or {}).get("email") or "").strip().lower()
    if not email:
        return {"ok": True}

    try:
        has_access, _, _ = _companion_access_decision(email)
        if has_access:
            magic_link = generate_magic_link(email)
            loops_send_transactional_email(
                to_email=email,
                magic_link=magic_link,
                timeout_seconds=int(os.getenv("LOOPS_TIMEOUT_SECONDS", "10")),
            )
    except Exception as e:
        print(f"Companion request-access error (masked response): {e}")

    return {"ok": True}


@app.get("/api/companion/user-context")
async def companion_user_context(request: Request):
    email = (request.cookies.get("companion_session_email") or "").strip().lower()
    if not email:
        raise HTTPException(status_code=401, detail="No companion session")

    has_access, reason, _ = _companion_access_decision(email)
    if not has_access:
        raise HTTPException(status_code=403, detail={"code": "no_access", "reason": reason})

    resolved = _resolve_user_context(email)
    return {
        "ok": True,
        "email": resolved["email"],
        "name": resolved["name"],
        "primary": resolved["archetype"],
        "secondary": resolved["secondary"],
        "context": resolved["context"],
        "channeled_top": resolved["channeled_top"],
        "friction": [resolved["friction_1"], resolved["friction_2"]],
        "resolver_source": resolved["source"],
        "resolver_source_email": resolved["source_email"],
        "assessment_email": resolved["assessment_email"],
        "using_24q_foundation": bool(resolved.get("using_24q_foundation")),
    }


@app.get("/api/companion/profile")
async def companion_profile(request: Request):
    email = (request.cookies.get("companion_session_email") or "").strip().lower()
    if not email:
        raise HTTPException(status_code=401, detail="No companion session")
    has_access, reason, access_row = _companion_access_decision(email)
    resolved = _resolve_user_context(email)

    conn = _patterns_conn()
    try:
        ct_today = datetime.now(ZoneInfo(COMPANION_CT_TZ)).date()
        week_start = ct_today - timedelta(days=ct_today.weekday())
        week_end = week_start + timedelta(days=6)

        actions_completed_week = int(
            conn.execute(
                """
                SELECT COUNT(*) AS c
                FROM daily_completions
                WHERE lower(email)=lower(?)
                  AND completed=1
                  AND task_date >= ?
                  AND task_date <= ?
                """,
                (email, week_start.isoformat(), week_end.isoformat()),
            ).fetchone()["c"]
            or 0
        )

        streak_days = 0
        snapshot_rows = conn.execute(
            """
            SELECT snapshot_date, evening_reflection_response
            FROM daily_snapshots
            WHERE lower(email)=lower(?)
            ORDER BY snapshot_date DESC
            """,
            (email,),
        ).fetchall()
        snapshots_by_date = {
            str(r["snapshot_date"]): str(r["evening_reflection_response"] or "").strip()
            for r in snapshot_rows
        }

        # If today's snapshot exists but has no completed reflection yet,
        # skip today and begin streak counting from yesterday.
        cursor_day = ct_today
        today_key = ct_today.isoformat()
        if today_key in snapshots_by_date and not snapshots_by_date.get(today_key):
            cursor_day = ct_today - timedelta(days=1)

        while True:
            key = cursor_day.isoformat()
            if key not in snapshots_by_date:
                break

            reflection = snapshots_by_date.get(key, "")
            if not reflection:
                break

            streak_days += 1
            cursor_day = cursor_day - timedelta(days=1)
    finally:
        conn.close()

    primary = resolved.get("archetype")
    secondary = resolved.get("secondary")
    context = resolved.get("context")
    display_name = resolved.get("name") or (email.split("@")[0].title() if "@" in email else "Member")
    channeled = {
        "top": resolved.get("channeled_top") or [],
        "source": resolved.get("source") or "default",
    }

    if not bool(resolved.get("using_24q_foundation")):
        _companion_raise_24q_foundation_alert(email, route="/api/companion/profile", resolved=resolved)

    granted_at = (access_row["granted_at"] if access_row and "granted_at" in access_row.keys() else None)
    onboarding_completed = int(access_row["onboarding_completed"] or 0) if access_row and "onboarding_completed" in access_row.keys() else 0
    intake_completed = int(access_row["intake_completed"] or 0) if access_row and "intake_completed" in access_row.keys() else 0
    companion_week = 1
    if granted_at:
        try:
            granted_dt = datetime.fromisoformat(str(granted_at).replace("Z", "+00:00"))
            now_dt = datetime.now(timezone.utc)
            days_since = max(0, (now_dt - granted_dt).days)
            companion_week = max(1, (days_since // 7) + 1)
        except Exception:
            companion_week = 1

    gate_conn = _patterns_conn()
    try:
        st = _stage_a_status(gate_conn, email)
    finally:
        gate_conn.close()
    return {
        "ok": True,
        "email": email,
        "has_access": has_access,
        "reason": reason,
        "name": display_name,
        "primary": primary,
        "primary_archetype": primary,
        "secondary": secondary,
        "context": context,
        "channeled": channeled,
        "friction": [resolved.get("friction_1"), resolved.get("friction_2")],
        "granted_at": granted_at,
        "companion_week": companion_week,
        "actions_completed_week": actions_completed_week,
        "streak_days": streak_days,
        "onboarding_completed": bool(onboarding_completed),
        "intake_completed": bool(intake_completed),
        "onboarding_stageA_required_complete": bool(st.get("required_complete")),
        "onboarding_stageA_missing_slots": st.get("missing_slots", []),
        "context_confidence_tier": int(st.get("confidence_tier", 1)),
        "morning_checkin_time": (access_row["morning_checkin_time"] if access_row and "morning_checkin_time" in access_row.keys() else "07:00"),
        "midday_checkin_time": (access_row["midday_checkin_time"] if access_row and "midday_checkin_time" in access_row.keys() else "12:00"),
        "evening_checkin_time": (access_row["evening_checkin_time"] if access_row and "evening_checkin_time" in access_row.keys() else "20:00"),
        "quiet_hours_start": (access_row["quiet_hours_start"] if access_row and "quiet_hours_start" in access_row.keys() else "22:00"),
        "quiet_hours_end": (access_row["quiet_hours_end"] if access_row and "quiet_hours_end" in access_row.keys() else "07:00"),
        "day_cutoff_time": (access_row["day_cutoff_time"] if access_row and "day_cutoff_time" in access_row.keys() else "00:00"),
        "spiritual_language_preference": (access_row["spiritual_language_preference"] if access_row and "spiritual_language_preference" in access_row.keys() else ""),
        "scripture_integration_level": (access_row["scripture_integration_level"] if access_row and "scripture_integration_level" in access_row.keys() else ""),
        "faith_boundaries": (access_row["faith_boundaries"] if access_row and "faith_boundaries" in access_row.keys() else ""),
        "using_24q_foundation": bool(resolved.get("using_24q_foundation")),
        "resolver_source": resolved.get("source"),
    }


@app.get("/api/companion/8q-link/status")
async def companion_8q_link_status(request: Request):
    """Companion-only daily follow-up to connect free 8Q data to paid account."""
    _ensure_companion_8q_schema()
    email = (request.cookies.get("companion_session_email") or "").strip().lower()
    if not email:
        raise HTTPException(status_code=401, detail="No companion session")

    has_access, reason, _ = _companion_access_decision(email)
    if not has_access:
        raise HTTPException(status_code=403, detail={"code": "no_access", "reason": reason})

    # Resolution order: direct paid email -> linked free email
    direct = _quick_signal_latest_for_email(email)
    if direct:
        linked_at = _now_z()
        _companion_set_8q_state(email, status="linked", free_8q_email=email, linked_at=linked_at)
        promotion = _promote_8q_to_paid_canonical(email, email, linked_at=linked_at)
        return {"ok": True, "needs_prompt": False, "status": "linked", "matched_by": "paid_email", "quick_signal": direct, "promotion": promotion}

    linked_free = _latest_linked_free_email_for_paid_email(email)
    if linked_free:
        linked = _quick_signal_latest_for_email(linked_free)
        if linked:
            linked_at = _now_z()
            _companion_set_8q_state(email, status="linked", free_8q_email=linked_free, linked_at=linked_at)
            promotion = _promote_8q_to_paid_canonical(email, linked_free, linked_at=linked_at)
            return {"ok": True, "needs_prompt": False, "status": "linked", "matched_by": "linked_email", "quick_signal": linked, "promotion": promotion}

    st = _companion_get_8q_state(email)
    today_ct = _ct_today_str()
    last_prompt = str(st["last_prompt_date_ct"] or "") if st else ""
    next_prompt = str(st["next_prompt_date_ct"] or "") if st and "next_prompt_date_ct" in st.keys() else ""
    status = str(st["status"] or "unknown") if st else "unknown"

    # If next_prompt_date_ct is set, only prompt on/after that date; otherwise keep legacy once-daily behavior.
    needs_prompt = (today_ct >= next_prompt) if next_prompt else (last_prompt != today_ct)
    return {
        "ok": True,
        "needs_prompt": needs_prompt,
        "status": status,
        "last_prompt_date_ct": last_prompt or None,
        "followup_question": "Did you take the free 8Q assessment? If yes, what email did you use?",
        "hint": "If you have not taken it yet, choose 'I haven't taken it'. We'll remind you daily in Companion until 8Q data is linked.",
    }


@app.post("/api/companion/8q-link/respond")
async def companion_8q_link_respond(request: Request):
    _ensure_companion_8q_schema()
    email = (request.cookies.get("companion_session_email") or "").strip().lower()
    if not email:
        raise HTTPException(status_code=401, detail="No companion session")

    try:
        body = await request.json()
    except Exception:
        body = {}

    action = str((body or {}).get("action") or "").strip().lower()
    today_ct = _ct_today_str()

    if action == "remind_in_days":
        days = int((body or {}).get("days") or 0)
        if days not in {1, 5, 10}:
            return JSONResponse(content={"ok": False, "error": "days_must_be_1_5_or_10"}, status_code=400)
        next_prompt_date_ct = (datetime.now(timezone.utc).astimezone(ZoneInfo(COMPANION_CT_TZ)) + timedelta(days=days)).strftime("%Y-%m-%d")
        conn = _patterns_conn()
        try:
            conn.execute(
                """
                INSERT INTO companion_8q_link_state (email, status, last_prompt_date_ct, next_prompt_date_ct, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(email) DO UPDATE SET
                  status=excluded.status,
                  last_prompt_date_ct=excluded.last_prompt_date_ct,
                  next_prompt_date_ct=excluded.next_prompt_date_ct,
                  updated_at=excluded.updated_at
                """,
                (_normalize_email(email), "needs_8q_assessment", today_ct, next_prompt_date_ct, _now_z()),
            )
            conn.commit()
        finally:
            conn.close()
        return {"ok": True, "status": "needs_8q_assessment", "needs_prompt": False, "next_prompt_date_ct": next_prompt_date_ct}

    if action == "not_taken":
        _companion_set_8q_state(email, status="needs_8q_assessment", last_prompt_date_ct=today_ct)
        return {"ok": True, "status": "needs_8q_assessment", "needs_prompt": False}

    free_8q_email = _normalize_email((body or {}).get("free_8q_email"))
    if not free_8q_email:
        return JSONResponse(content={"ok": False, "error": "free_8q_email_required"}, status_code=400)

    # Persist canonical paid->free link
    rec = {
        "linked_at": _now_z(),
        "paid_email": email,
        "free_8q_email": free_8q_email,
        "source": "companion_followup",
    }
    with quick_signal_link_file.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")

    match = _quick_signal_latest_for_email(free_8q_email)
    if match:
        _companion_set_8q_state(email, status="linked", free_8q_email=free_8q_email, linked_at=rec["linked_at"], last_prompt_date_ct=today_ct)
        promotion = _promote_8q_to_paid_canonical(email, free_8q_email, linked_at=rec["linked_at"])
        return {"ok": True, "status": "linked", "matched": True, "quick_signal": match, "promotion": promotion}

    _companion_set_8q_state(email, status="needs_8q_assessment", free_8q_email=free_8q_email, last_prompt_date_ct=today_ct)
    return {
        "ok": True,
        "status": "needs_8q_assessment",
        "matched": False,
        "needs_prompt": False,
        "next_step": "No 8Q found for that email yet. Complete free 8Q, then we'll auto-link on next check.",
    }


@app.post("/api/companion/complete-onboarding")
async def companion_complete_onboarding(request: Request):
    email = (request.cookies.get("companion_session_email") or "").strip().lower()
    if not email:
        raise HTTPException(status_code=401, detail="No companion session")

    conn = _patterns_conn()
    try:
        conn.execute(
            "UPDATE companion_access SET onboarding_completed = 1, updated_at = ? WHERE lower(email)=lower(?)",
            (_now_z(), email),
        )
        conn.commit()
    finally:
        conn.close()

    return {"ok": True}


@app.post("/api/companion/intake-chat")
async def companion_intake_chat(request: Request):
    email = (request.cookies.get("companion_session_email") or "").strip().lower()
    if not email:
        raise HTTPException(status_code=401, detail="No companion session")

    try:
        body = await request.json()
    except Exception:
        body = {}

    focus_area = str((body or {}).get("focus_area") or "").strip()
    context_summary = str((body or {}).get("context_summary") or "").strip()
    messages = (body or {}).get("messages") if isinstance((body or {}).get("messages"), list) else []
    mode = str((body or {}).get("mode") or "question").strip().lower()

    user_msgs = [m for m in messages if isinstance(m, dict) and str(m.get("role") or "").lower() == "user" and str(m.get("content") or "").strip()]
    turn = len(user_msgs)

    if mode == "summary" or turn >= 4:
        system_prompt = (
            "You are the CHANNELED intake coach. Produce one concise paragraph summarizing the user's current context, "
            "constraints, and leverage point in practical language. No bullets, no markdown."
        )
        convo = "\n".join([f"{str(m.get('role') or '').upper()}: {str(m.get('content') or '').strip()}" for m in messages if isinstance(m, dict)])
        user_prompt = (
            f"Focus area: {focus_area or 'unspecified'}\n"
            f"Current context note: {context_summary or 'none'}\n"
            f"Conversation:\n{convo}\n\n"
            "Write the summary paragraph now."
        )
        summary = _call_companion_llm(system_prompt, user_prompt, model="claude-sonnet-4-20250514", max_tokens=260).strip()
        return {"ok": True, "done": True, "summary": summary}

    system_prompt = (
        "You are the CHANNELED intake coach. Ask one focused follow-up question that helps clarify execution context. "
        "Do not ask broad open-ended or trailing questions. Keep it under 16 words."
    )
    convo = "\n".join([f"{str(m.get('role') or '').upper()}: {str(m.get('content') or '').strip()}" for m in messages if isinstance(m, dict)])
    user_prompt = (
        f"Focus area: {focus_area or 'unspecified'}\n"
        f"Current context note: {context_summary or 'none'}\n"
        f"Question count already asked: {turn}\n"
        f"Conversation so far:\n{convo}\n\n"
        "Ask the next single focused question."
    )
    next_q = _call_companion_llm(system_prompt, user_prompt, model="claude-sonnet-4-20250514", max_tokens=80).strip()
    return {"ok": True, "done": False, "question": next_q}


@app.post("/api/companion/complete-intake")
async def companion_complete_intake(request: Request):
    email = (request.cookies.get("companion_session_email") or "").strip().lower()
    if not email:
        raise HTTPException(status_code=401, detail="No companion session")

    try:
        body = await request.json()
    except Exception:
        body = {}

    focus_area = str((body or {}).get("focus_area") or "").strip()
    tiles_active = (body or {}).get("tiles_active") if isinstance((body or {}).get("tiles_active"), list) else []
    tiles_priority = (body or {}).get("tiles_priority") if isinstance((body or {}).get("tiles_priority"), list) else []
    context_summary = str((body or {}).get("context_summary") or "").strip()
    friction_patterns = (body or {}).get("friction_patterns") if isinstance((body or {}).get("friction_patterns"), list) else []
    coaching_style_intensity = str((body or {}).get("coaching_style_intensity") or "").strip().lower()
    coaching_style_approach = str((body or {}).get("coaching_style_approach") or "").strip().lower()
    checkin_window = str((body or {}).get("checkin_window") or "").strip().lower()
    quiet_hours_preference = str((body or {}).get("quiet_hours_preference") or "").strip().lower()
    morning_checkin_time = str((body or {}).get("morning_checkin_time") or "07:00").strip()
    midday_checkin_time = str((body or {}).get("midday_checkin_time") or "12:00").strip()
    evening_checkin_time = str((body or {}).get("evening_checkin_time") or "20:00").strip()
    quiet_hours_start = str((body or {}).get("quiet_hours_start") or "22:00").strip()
    quiet_hours_end = str((body or {}).get("quiet_hours_end") or "07:00").strip()
    reentry_preference = str((body or {}).get("reentry_preference") or "").strip().lower()
    fast_win_preference = str((body or {}).get("fast_win_preference") or "").strip().lower()
    spiritual_language_preference = str((body or {}).get("spiritual_language_preference") or "").strip().lower()
    scripture_integration_level = str((body or {}).get("scripture_integration_level") or "").strip().lower()
    faith_boundaries = str((body or {}).get("faith_boundaries") or "").strip()
    faith_boundaries_other = str((body or {}).get("faith_boundaries_other") or "").strip()
    faith_lens_preference = str((body or {}).get("faith_lens_preference") or "").strip().lower()
    scripture_reference_preference = str((body or {}).get("scripture_reference_preference") or "").strip().lower()

    if not faith_lens_preference or not scripture_reference_preference:
        _pref_map = {
            "faith_forward": ("yes", "helpful"),
            "neutral_with_scripture": ("yes", "ask"),
            "avoid_spiritual": ("no", "avoid"),
        }
        mapped_faith, mapped_scripture = _pref_map.get(spiritual_language_preference, ("no", "avoid"))
        faith_lens_preference = faith_lens_preference or mapped_faith
        scripture_reference_preference = scripture_reference_preference or mapped_scripture

    logger.info(
        "companion_complete_intake email=%s spiritual=%s scripture_level=%s faith_boundaries_present=%s faith_boundaries_other_present=%s faith_lens=%s scripture_ref=%s",
        email,
        spiritual_language_preference,
        scripture_integration_level,
        bool(faith_boundaries),
        bool(faith_boundaries_other),
        faith_lens_preference,
        scripture_reference_preference,
    )

    if coaching_style_intensity not in {"push", "meet", "read_the_room"}:
        raise HTTPException(status_code=422, detail="coaching_style_intensity must be push, meet, or read_the_room")
    if coaching_style_approach not in {"direct", "think_through", "plan_plus_steps"}:
        raise HTTPException(status_code=422, detail="coaching_style_approach must be direct, think_through, or plan_plus_steps")

    faith_capture_ok = False
    conn = _patterns_conn()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS companion_intake (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT,
                focus_area TEXT,
                tiles_active TEXT,
                tiles_priority TEXT,
                context_summary TEXT,
                friction_patterns TEXT,
                coaching_style_intensity TEXT,
                coaching_style_approach TEXT,
                checkin_window TEXT,
                quiet_hours_preference TEXT,
                morning_checkin_time TEXT,
                midday_checkin_time TEXT,
                evening_checkin_time TEXT,
                quiet_hours_start TEXT,
                quiet_hours_end TEXT,
                reentry_preference TEXT,
                fast_win_preference TEXT,
                created_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
            )
            """
        )

        # Backward-compatible migration for existing companion_intake tables
        cols = {r[1] for r in conn.execute("PRAGMA table_info(companion_intake)").fetchall()}
        if "checkin_window" not in cols:
            conn.execute("ALTER TABLE companion_intake ADD COLUMN checkin_window TEXT")
        if "quiet_hours_preference" not in cols:
            conn.execute("ALTER TABLE companion_intake ADD COLUMN quiet_hours_preference TEXT")
        if "morning_checkin_time" not in cols:
            conn.execute("ALTER TABLE companion_intake ADD COLUMN morning_checkin_time TEXT")
        if "midday_checkin_time" not in cols:
            conn.execute("ALTER TABLE companion_intake ADD COLUMN midday_checkin_time TEXT")
        if "evening_checkin_time" not in cols:
            conn.execute("ALTER TABLE companion_intake ADD COLUMN evening_checkin_time TEXT")
        if "quiet_hours_start" not in cols:
            conn.execute("ALTER TABLE companion_intake ADD COLUMN quiet_hours_start TEXT")
        if "quiet_hours_end" not in cols:
            conn.execute("ALTER TABLE companion_intake ADD COLUMN quiet_hours_end TEXT")
        if "reentry_preference" not in cols:
            conn.execute("ALTER TABLE companion_intake ADD COLUMN reentry_preference TEXT")
        if "fast_win_preference" not in cols:
            conn.execute("ALTER TABLE companion_intake ADD COLUMN fast_win_preference TEXT")
        if "spiritual_language_preference" not in cols:
            conn.execute("ALTER TABLE companion_intake ADD COLUMN spiritual_language_preference TEXT")
        if "scripture_integration_level" not in cols:
            conn.execute("ALTER TABLE companion_intake ADD COLUMN scripture_integration_level TEXT")
        if "faith_boundaries" not in cols:
            conn.execute("ALTER TABLE companion_intake ADD COLUMN faith_boundaries TEXT")
        if "faith_boundaries_other" not in cols:
            conn.execute("ALTER TABLE companion_intake ADD COLUMN faith_boundaries_other TEXT")
        if "faith_lens_preference" not in cols:
            conn.execute("ALTER TABLE companion_intake ADD COLUMN faith_lens_preference TEXT")
        if "scripture_reference_preference" not in cols:
            conn.execute("ALTER TABLE companion_intake ADD COLUMN scripture_reference_preference TEXT")

        conn.execute(
            """
            INSERT INTO companion_intake (
                email, focus_area, tiles_active, tiles_priority, context_summary,
                friction_patterns, coaching_style_intensity, coaching_style_approach,
                checkin_window, quiet_hours_preference, morning_checkin_time, midday_checkin_time,
                evening_checkin_time, quiet_hours_start, quiet_hours_end, reentry_preference, fast_win_preference,
                spiritual_language_preference, scripture_integration_level, faith_boundaries, faith_boundaries_other,
                faith_lens_preference, scripture_reference_preference
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                email,
                focus_area,
                json.dumps(tiles_active),
                json.dumps(tiles_priority),
                context_summary,
                json.dumps(friction_patterns),
                coaching_style_intensity,
                coaching_style_approach,
                checkin_window,
                quiet_hours_preference,
                morning_checkin_time,
                midday_checkin_time,
                evening_checkin_time,
                quiet_hours_start,
                quiet_hours_end,
                reentry_preference,
                fast_win_preference,
                spiritual_language_preference,
                scripture_integration_level,
                faith_boundaries,
                faith_boundaries_other,
                faith_lens_preference,
                scripture_reference_preference,
            ),
        )

        now_z = _now_z()
        conn.execute(
            """
            UPDATE companion_access
               SET intake_completed = 1,
                   morning_checkin_time = ?,
                   midday_checkin_time = ?,
                   evening_checkin_time = ?,
                   quiet_hours_start = ?,
                   quiet_hours_end = ?,
                   spiritual_language_preference = COALESCE(NULLIF(?, ''), spiritual_language_preference),
                   scripture_integration_level = COALESCE(NULLIF(?, ''), scripture_integration_level),
                   faith_boundaries = COALESCE(NULLIF(?, ''), faith_boundaries),
                   updated_at = ?
             WHERE lower(email)=lower(?)
            """,
            (morning_checkin_time, midday_checkin_time, evening_checkin_time, quiet_hours_start, quiet_hours_end, spiritual_language_preference, scripture_integration_level, faith_boundaries, now_z, email),
        )

        ct_now = datetime.now(timezone.utc).astimezone(ZoneInfo(COMPANION_CT_TZ))
        week_start = (ct_now - timedelta(days=ct_now.weekday())).strftime("%Y-%m-%d")
        conn.execute(
            "DELETE FROM companion_weekly_plans WHERE lower(email)=lower(?) AND week_start = ?",
            (email, week_start),
        )
        conn.commit()

        verify_row = conn.execute(
            "SELECT spiritual_language_preference, scripture_integration_level, faith_boundaries, faith_boundaries_other, faith_lens_preference, scripture_reference_preference FROM companion_intake WHERE lower(email)=lower(?) ORDER BY id DESC LIMIT 1",
            (email,),
        ).fetchone()
        faith_capture_ok = bool(verify_row and (verify_row[0] or verify_row[4] or verify_row[5]))
        if spiritual_language_preference in {"faith_forward", "neutral_with_scripture"} and not faith_capture_ok:
            logger.warning("Faith preference capture appears empty after intake write for %s", email)
    finally:
        conn.close()

    return {"ok": True, "faith_capture_ok": faith_capture_ok}


@app.post("/api/companion/weekly-plan")
async def companion_weekly_plan(request: Request):
    email = (request.cookies.get("companion_session_email") or "").strip().lower()
    if not email:
        raise HTTPException(status_code=401, detail="No companion session")

    has_access, reason, _ = _companion_access_decision(email)
    if not has_access:
        raise HTTPException(status_code=403, detail={"code": "no_access", "reason": reason})

    body = {}
    try:
        body = await request.json()
    except Exception:
        body = {}
    force_regenerate = bool((body or {}).get("force_regenerate"))

    conn = _patterns_conn()
    try:
        st = _stage_a_status(conn, email)
        if not st.get("required_complete") and not force_regenerate:
            return JSONResponse(content={
                "ok": True,
                "limited": True,
                "reason": "stage_a_incomplete",
                "missing_slots": st.get("missing_slots", []),
                "message": "Complete onboarding context to unlock full personalized recommendations.",
                "today_tasks": [
                    {"title": "Define Today’s Finish Line", "description": "Write one sentence describing what done looks like today."},
                    {"title": "Protect One Focus Block", "description": "Set one 60-90 minute focus block and complete one meaningful action."},
                    {"title": "Name One Constraint", "description": "Write your top blocker and choose one step to reduce it today."}
                ]
            })

        resolved = _resolve_user_context(email)
        intake_row = conn.execute(
            "SELECT * FROM companion_intake WHERE lower(email)=lower(?) ORDER BY id DESC LIMIT 1",
            (email,),
        ).fetchone()

        now_utc = datetime.now(timezone.utc)
        ct_now = now_utc.astimezone(ZoneInfo(COMPANION_CT_TZ))
        week_start_dt = ct_now - timedelta(days=ct_now.weekday())
        week_start = week_start_dt.strftime("%Y-%m-%d")
        week_key = week_start_dt.strftime("%Y-W%W")

        existing = conn.execute(
            "SELECT plan_json, week_start FROM companion_weekly_plans WHERE lower(email)=lower(?) AND week_start = ? ORDER BY id DESC LIMIT 1",
            (email, week_start),
        ).fetchone()
        if (not force_regenerate) and existing and existing["plan_json"]:
            try:
                existing_plan = json.loads(existing["plan_json"])
                has_tasks = isinstance(existing_plan.get("tasks"), list)
                has_days = isinstance(existing_plan.get("days"), list)
                existing_week_start = str(existing["week_start"] or "").strip()
                today_str = ct_now.strftime("%Y-%m-%d")

                # Daily-format tomorrow-plan is valid only when anchored to today's date.
                if has_tasks and (not has_days) and existing_week_start != today_str:
                    raise ValueError("stale_daily_plan")

                fixed_reflection_prompts = [
                    "What's your one sentence for done?",
                    "What was the deliverable you named?",
                    "What system — and use it or improve it?",
                ]
                if isinstance(existing_plan.get("days"), list):
                    for d in existing_plan.get("days", []):
                        if isinstance(d, dict):
                            d["reflection_prompts"] = fixed_reflection_prompts

                existing_plan["today_tasks"] = _plan_today_tasks(existing_plan, ct_now)
                return JSONResponse(content=existing_plan)
            except Exception:
                pass

        primary = resolved.get("archetype") or "Architect"
        secondary = resolved.get("secondary") or "Artisan"
        context = resolved.get("context") or "personal"
        display_name = resolved.get("name") or (email.split("@")[0].title() if "@" in email else "Member")

        if not bool(resolved.get("using_24q_foundation")):
            # Auto-recovery attempt: if exactly one assessment matches companion_access.email, relink and continue.
            fallback_rows = conn.execute(
                "SELECT id, email, created_at FROM assessments WHERE lower(email)=lower(?) ORDER BY COALESCE(is_primary,0) DESC, datetime(created_at) DESC",
                (email,),
            ).fetchall()
            if len(fallback_rows) >= 1:
                # Deterministic resolver: use most recent assessment when multiple matches exist
                relink_email = str(fallback_rows[0]["email"] or "").strip().lower()
                if relink_email:
                    conn.execute(
                        "UPDATE companion_access SET assessment_email = ?, updated_at = ? WHERE lower(email)=lower(?)",
                        (relink_email, _now_z(), email),
                    )
                    ct_now_str = datetime.now(ZoneInfo(COMPANION_CT_TZ)).strftime("%Y-%m-%d")
                    details = {
                        "reason": "auto_link_from_assessments_latest_match_on_companion_email",
                        "route": "/api/companion/weekly-plan",
                        "companion_email": email,
                        "assessment_email": relink_email,
                        "assessment_id": int(fallback_rows[0]["id"] or 0),
                    }
                    try:
                        conn.execute(
                            "INSERT INTO companion_alert_log (email, alert_key, alert_date_ct, details_json, created_at) VALUES (?, ?, ?, ?, ?)",
                            (email, "auto_link_24q", ct_now_str, json.dumps(details), _now_z()),
                        )
                    except Exception:
                        pass
                    conn.commit()
                    resolved = _resolve_user_context(email)

            if not bool(resolved.get("using_24q_foundation")):
                _companion_raise_24q_foundation_alert(email, route="/api/companion/weekly-plan", resolved=resolved)
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "missing_24q_foundation",
                        "message": "Companion weekly plan requires linked 24Q CHANNELED assessment data.",
                        "resolver_source": resolved.get("source"),
                    },
                )

        seven_days_ago = (ct_now - timedelta(days=6)).strftime("%Y-%m-%d")
        completion_rows = conn.execute(
            """
            SELECT task_title, task_description, completed, note
            FROM daily_completions
            WHERE lower(email)=lower(?) AND task_date >= ? AND task_date <= ?
            ORDER BY task_date ASC, task_index ASC
            """,
            (email, seven_days_ago, ct_now.strftime("%Y-%m-%d")),
        ).fetchall()

        total_tasks = max(21, len(completion_rows))
        completed_count = sum(1 for r in completion_rows if int(r["completed"] or 0) == 1)
        skipped_titles = [str(r["task_title"] or "(untitled)") for r in completion_rows if int(r["completed"] or 0) != 1]
        note_themes = [str(r["note"] or "").strip() for r in completion_rows if str(r["note"] or "").strip()]
        prior_week_continuity = _build_prior_week_continuity(conn, email, ct_now)

        intake_focus_area = str(intake_row["focus_area"] or "").strip() if intake_row else ""
        intake_context_summary = str(intake_row["context_summary"] or "").strip() if intake_row else ""

        existing_plan_count = conn.execute(
            "SELECT COUNT(1) AS c FROM companion_weekly_plans WHERE lower(email)=lower(?)",
            (email,),
        ).fetchone()["c"]
        cold_start = int(existing_plan_count or 0) == 0
        gate = _cold_start_intake_gate(intake_row)
        if cold_start and not gate["pass"]:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "cold_start_intake_incomplete",
                    "message": "Companion needs a bit more intake context before generating your first weekly plan.",
                    "intake_score": gate["score"],
                    "required_min": COMPANION_COLD_START_MIN_FIELDS,
                    "missing_fields": gate["missing"],
                },
            )
        intake_friction_patterns = []
        if intake_row and intake_row["friction_patterns"]:
            try:
                loaded = json.loads(intake_row["friction_patterns"])
                if isinstance(loaded, list):
                    intake_friction_patterns = [str(x).strip() for x in loaded if str(x).strip()]
            except Exception:
                intake_friction_patterns = []
        intake_coaching_intensity = str(intake_row["coaching_style_intensity"] or "").strip() if intake_row else ""
        intake_coaching_approach = str(intake_row["coaching_style_approach"] or "").strip() if intake_row else ""

        system_prompt = (
            f"You are the CHANNELED Implementation Companion. Generate a focused 7-day action plan for the user. "
            f"{COMPANION_FRAMEWORK_LOCK_BLOCK} "
            f"{COMPANION_ARCHETYPE_INTEGRITY_BLOCK} "
            f"Profile anchors: primary archetype={primary}; secondary archetype={secondary}; context={context}. "
            f"Intake anchors (use when provided): focus_area={intake_focus_area or 'none'}; context_summary={intake_context_summary or 'none'}; "
            f"friction_patterns={', '.join(intake_friction_patterns) if intake_friction_patterns else 'none'}; "
            f"coaching_style_intensity={intake_coaching_intensity or 'none'}; coaching_style_approach={intake_coaching_approach or 'none'}. "
            "Priority rules (follow in order): "
            "1) The intake context is the primary driver of plan content. The focus_area and context_summary from intake determine what the 7-day plan is about. If context is 'need mental clarity around issue at home', every day's tasks must directly address that situation. Do not default to generic productivity or systems-building tasks. "
            "2) The archetype informs style and framing, not subject matter. An Architect working on mental clarity gets structured, sequential, decision-oriented tasks, but tasks must remain about mental clarity (not productivity systems). "
            "3) Friction patterns determine task design. If friction includes Can't finish / Lose focus / Run out of steam, every task must be completable in under 20 minutes, have a single concrete output, and require no decision-making to start. "
            "4) Coaching style shapes tone. think_through means tasks include a brief 'why this matters' framing. read_the_room means tasks are never demanding; they are invitations, not commands. "
            "5) Tasks must pass the specificity test. Each task must be unambiguous. 'Work on your project' fails. 'Write one sentence describing the decision you've been avoiding' passes. "
            f"6) The user's secondary archetype is {secondary} — never reference any other archetype in wiring notes. Every wiring note must name only {primary} and/or {secondary} by name. "
            "Return ONLY valid JSON with this exact structure: {\"theme\": \"one sentence weekly theme\", \"days\": [{\"day\": \"Monday\", \"focus\": \"one sentence\", \"action\": \"one specific action\", \"wiring_note\": \"one sentence connecting this to their archetype\", \"reflection_prompt\": \"required\", \"tasks\": [{\"title\": \"...\", \"description\": \"...\"}, {\"title\": \"...\", \"description\": \"...\"}, {\"title\": \"...\", \"description\": \"...\"}]}]} for all 7 days. "
            "Each day object MUST include a \"reflection_prompt\" field: a single question of maximum 8 words that assumes the action was attempted and asks for the specific output or decision it was designed to produce (e.g. \"What sentence did you write?\" not \"Did you complete this?\"). This field is required — do not omit it. "
            "Use prior performance context: completed tasks count, skipped task themes, and note themes supplied in the user message. Adjust this week's focus accordingly — if tasks were skipped repeatedly, simplify or reframe them; if completion was high, increase challenge slightly. "
            "No preamble, no markdown, only the JSON object. Use prior-week continuity context from user message to avoid reset-based planning and carry forward stall/completion patterns."
        )
        user_prompt = (
            f"This person's primary focus is: {intake_focus_area or 'none'}. Their context is: '{intake_context_summary or 'none'}'. Every task this week must directly serve this focus and context. Do not generate tasks about unrelated areas even if they seem relevant to the archetype.\n"
            f"Name: {display_name}\n"
            f"Primary archetype: {primary}\n"
            f"Secondary archetype: {secondary}\n"
            f"Context: {context}\n"
            f"Completion summary: completed {completed_count} of {total_tasks}.\n"
            f"Cold start: {cold_start}. Intake gate score: {gate['score']}/{COMPANION_COLD_START_MIN_FIELDS}.\n"
            f"Skipped tasks: {', '.join(skipped_titles[:10]) if skipped_titles else 'none'}\n"
            f"Notes themes: {' | '.join(note_themes[:8]) if note_themes else 'none'}\n"
            f"Prior week continuity JSON: {json.dumps(prior_week_continuity)}\n"
            "Generate a Monday-Sunday plan."
        )

        anthropic_key = (os.environ.get("ANTHROPIC_API_KEY") or "").strip()
        print(f"[weekly-plan] prompt archetypes primary={primary} secondary={secondary} context={context}")
        if anthropic_key:
            resp = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": anthropic_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-sonnet-4-20250514",
                    "max_tokens": 1500,
                    "system": system_prompt,
                    "messages": [{"role": "user", "content": user_prompt}],
                },
                timeout=60,
            )
            resp.raise_for_status()
            raw_text = ((resp.json().get("content") or [{}])[0].get("text") or "").strip()
        else:
            raw_text = _call_companion_llm(system_prompt, user_prompt, model="claude-sonnet-4-20250514", max_tokens=1500)

        start = raw_text.find("{")
        end = raw_text.rfind("}")
        plan_obj = json.loads(raw_text[start:end+1] if start != -1 and end != -1 else raw_text)

        if not isinstance(plan_obj, dict) or "days" not in plan_obj:
            raise ValueError("Invalid plan JSON shape")

        if not isinstance(plan_obj.get("days"), list):
            plan_obj["days"] = []

        normalized_days = []
        for d in plan_obj.get("days", []):
            if not isinstance(d, dict):
                continue
            action_text = str(d.get("action") or "").strip()
            rp = str(d.get("reflection_prompt") or "").strip()

            # Back-compat guardrail: if a model drifts to nested tasks, map the first task
            # back into the locked v1 day-level shape instead of changing API structure.
            if (not action_text or not rp) and isinstance(d.get("tasks"), list) and d.get("tasks"):
                first_task = d.get("tasks")[0] if isinstance(d.get("tasks")[0], dict) else {}
                if not action_text:
                    action_text = str(first_task.get("action") or "").strip()
                if not rp:
                    rp = str(first_task.get("reflection_prompt") or "").strip()

            if rp:
                words = rp.split()
                if len(words) > 8:
                    rp = " ".join(words[:8]).rstrip("?.!,:;") + "?"

            reflection_prompts = [
                "What's your one sentence for done?",
                "What was the deliverable you named?",
                "What system — and use it or improve it?",
            ]

            tasks_raw = d.get("tasks") if isinstance(d.get("tasks"), list) else []
            tasks = []
            for t in tasks_raw[:3]:
                if not isinstance(t, dict):
                    continue
                t_title = str(t.get("title") or "").strip()
                t_desc = str(t.get("description") or "").strip()
                if t_title or t_desc:
                    tasks.append({"title": t_title, "description": t_desc})
            if not tasks:
                tasks = [
                    {"title": str(d.get("focus") or "").strip(), "description": action_text},
                    {"title": "Focus 2", "description": str(d.get("action2") or d.get("action") or "").strip()},
                    {"title": "Focus 3", "description": str(d.get("wiring_note") or "").strip()},
                ]

            day_obj = {
                "day": str(d.get("day") or "").strip(),
                "focus": str(d.get("focus") or "").strip(),
                "action": action_text,
                "wiring_note": str(d.get("wiring_note") or "").strip(),
                "reflection_prompt": rp,
                "reflection_prompts": reflection_prompts,
                "tasks": tasks,
            }
            day_obj["reflection_prompt"] = day_obj.get("reflection_prompt", "")
            day_obj["reflection_prompts"] = [
                "What's your one sentence for done?",
                "What was the deliverable you named?",
                "What system — and use it or improve it?",
            ]
            normalized_days.append(day_obj)
        plan_obj["days"] = normalized_days
        plan_obj["today_tasks"] = _plan_today_tasks(plan_obj, ct_now)

        conn.execute(
            """
            INSERT INTO companion_weekly_continuity (email, week_key, summary_json, created_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(email, week_key) DO UPDATE SET
                summary_json=excluded.summary_json,
                created_at=excluded.created_at
            """,
            (email, week_key, json.dumps(prior_week_continuity), _now_z()),
        )

        conn.execute(
            """
            INSERT INTO companion_weekly_plans (email, week_key, week_start, timezone, status, model, archetype, plan_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(email, week_key) DO UPDATE SET
                week_start=excluded.week_start,
                timezone=excluded.timezone,
                status=excluded.status,
                model=excluded.model,
                archetype=excluded.archetype,
                plan_json=excluded.plan_json,
                updated_at=excluded.updated_at
            """,
            (
                email,
                week_key,
                week_start,
                COMPANION_CT_TZ,
                "generated",
                "claude-sonnet-4-20250514",
                primary,
                json.dumps(plan_obj),
                _now_z(),
                _now_z(),
            ),
        )
        conn.commit()
        return JSONResponse(content=plan_obj)
    finally:
        conn.close()


@app.get("/api/companion/weekly-plan/current")
async def companion_weekly_plan_current(request: Request):
    user = get_optional_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    has_access, reason, _row = _companion_access_decision(user["email"])
    if not has_access:
        raise HTTPException(status_code=402, detail={"code": "companion_access_inactive", "message": "Your Companion access is currently inactive. Renew to continue.", "reason": reason})

    has_access, reason, _row = _companion_access_decision(user["email"])
    if not has_access:
        raise HTTPException(status_code=402, detail={"code": "companion_access_inactive", "message": "Your Companion access is currently inactive. Renew to continue.", "reason": reason})

    week_key = _companion_week_key()
    conn = _patterns_conn()
    try:
        row = conn.execute(
            "SELECT * FROM companion_weekly_plans WHERE email = ? AND week_key = ? ORDER BY id DESC LIMIT 1",
            (user["email"].lower().strip(), week_key),
        ).fetchone()
    finally:
        conn.close()

    if not row:
        return {"ok": True, "week_key": week_key, "exists": False}

    plan = {}
    if row["plan_json"]:
        try:
            plan = json.loads(row["plan_json"])
        except Exception:
            plan = {}

    return {
        "ok": True,
        "exists": True,
        "week_key": week_key,
        "status": row["status"],
        "plan": plan,
        "error": row["error"],
    }


@app.post("/api/companion/weekly-plan/generate-for-me")
async def companion_generate_weekly_plan_for_me(request: Request):
    user = get_optional_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    week_key = _companion_week_key()
    email = user["email"].lower().strip()
    gate_conn = _patterns_conn()
    try:
        st = _stage_a_status(gate_conn, email)
    finally:
        gate_conn.close()
    if not st.get("required_complete"):
        return JSONResponse(content={
            "ok": False,
            "limited": True,
            "reason": "stage_a_incomplete",
            "missing_slots": st.get("missing_slots", [])
        }, status_code=409)

    conn = _patterns_conn()
    try:
        existing = conn.execute(
            "SELECT * FROM companion_weekly_plans WHERE email = ? AND week_key = ? LIMIT 1",
            (email, week_key),
        ).fetchone()
        if existing:
            plan = json.loads(existing["plan_json"]) if existing["plan_json"] else {}
            return {"ok": True, "preserved": True, "week_key": week_key, "status": existing["status"], "plan": plan}

        profile = _profile_for_email(email)
        prompt_hash = hashlib.sha256(json.dumps(profile, sort_keys=True).encode()).hexdigest()

        conn.execute(
            "INSERT INTO companion_weekly_plans (email, week_key, timezone, status, model, prompt_hash, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (email, week_key, COMPANION_CT_TZ, "generating", COMPANION_SONNET_MODEL, prompt_hash, _now_z(), _now_z()),
        )
        conn.commit()

        last_error = None
        plan = None
        for attempt in range(1, 4):
            try:
                plan = _generate_weekly_plan(profile, model=COMPANION_SONNET_MODEL)
                break
            except Exception as e:
                last_error = str(e)
                if attempt < 3:
                    time.sleep(60)

        if plan is None:
            conn.execute(
                "UPDATE companion_weekly_plans SET status = ?, error = ?, updated_at = ? WHERE email = ? AND week_key = ?",
                ("failed", last_error or "generation_failed", _now_z(), email, week_key),
            )
            conn.commit()
            return {"ok": False, "week_key": week_key, "status": "failed", "error": last_error or "generation_failed"}

        conn.execute(
            "UPDATE companion_weekly_plans SET status = ?, plan_json = ?, error = NULL, updated_at = ? WHERE email = ? AND week_key = ?",
            ("ready", json.dumps(plan), _now_z(), email, week_key),
        )
        conn.commit()
        return {"ok": True, "week_key": week_key, "status": "ready", "plan": plan}
    finally:
        conn.close()


@app.get("/api/companion/admin/24q-foundation-report")
async def companion_admin_24q_foundation_report(request: Request, limit: int = Query(500, ge=1, le=5000), include_inactive: bool = Query(False)):
    """Operational report: identify companion users not currently resolved to 24Q foundation."""
    conn = _patterns_conn()
    try:
        where_clause = "" if include_inactive else "WHERE active = 1"
        rows = conn.execute(
            f"SELECT email, active, assessment_email, updated_at FROM companion_access {where_clause} ORDER BY updated_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    finally:
        conn.close()

    scanned = []
    non_24q = []
    for r in rows:
        email = str(r["email"] or "").strip().lower()
        if not email:
            continue
        resolved = _resolve_user_context(email)
        rec = {
            "email": email,
            "active": int(r["active"] or 0),
            "assessment_email": str(r["assessment_email"] or "").strip().lower() or None,
            "resolver_source": resolved.get("source"),
            "resolver_source_email": resolved.get("source_email"),
            "using_24q_foundation": bool(resolved.get("using_24q_foundation")),
        }
        scanned.append(rec)
        if not rec["using_24q_foundation"]:
            non_24q.append(rec)

    return {
        "ok": True,
        "summary": {
            "scanned": len(scanned),
            "using_24q_foundation": len(scanned) - len(non_24q),
            "not_using_24q_foundation": len(non_24q),
            "include_inactive": include_inactive,
            "limit": limit,
        },
        "non_24q_users": non_24q,
        "scanned_users": scanned,
    }


async def run_companion_reconciliation_summary(send_email: bool = True, include_integration_tests: bool = True) -> Dict[str, Any]:
    conn = _patterns_conn()
    try:
        access_rows = conn.execute(
            "SELECT email, active, assessment_email FROM companion_access ORDER BY updated_at DESC LIMIT 5000"
        ).fetchall()

        scanned = []
        non_24q = []
        for r in access_rows:
            email = str(r["email"] or "").strip().lower()
            if not email:
                continue
            resolved = _resolve_user_context(email)
            rec = {
                "email": email,
                "active": int(r["active"] or 0),
                "assessment_email": str(r["assessment_email"] or "").strip().lower() or None,
                "resolver_source": resolved.get("source"),
                "resolver_source_email": resolved.get("source_email"),
                "using_24q_foundation": bool(resolved.get("using_24q_foundation")),
            }
            scanned.append(rec)
            if not rec["using_24q_foundation"]:
                non_24q.append(rec)

        unresolved_rows = conn.execute(
            """
            SELECT email, status, free_8q_email, linked_at, last_prompt_date_ct, updated_at
            FROM companion_8q_link_state
            WHERE lower(status) != 'linked'
            ORDER BY updated_at DESC
            LIMIT 500
            """
        ).fetchall()

        now_utc = datetime.now(timezone.utc)
        day_start = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
        week_start = day_start - timedelta(days=day_start.weekday())
        month_start = day_start.replace(day=1)
        next_day = day_start + timedelta(days=1)

        day_s = day_start.strftime('%Y-%m-%dT%H:%M:%SZ')
        week_s = week_start.strftime('%Y-%m-%dT%H:%M:%SZ')
        month_s = month_start.strftime('%Y-%m-%dT%H:%M:%SZ')
        next_day_s = next_day.strftime('%Y-%m-%dT%H:%M:%SZ')

        def _count(sql: str, params=()):
            row = conn.execute(sql, params).fetchone()
            return int((row[0] if row else 0) or 0)

        test_access_predicate = "(lower(email) LIKE '%@example.com' OR lower(COALESCE(source,'')) LIKE '%test%')"
        paid_access_predicate = f"NOT {test_access_predicate}"

        test_assessment_predicate = (
            "(lower(email) LIKE '%@example.com' "
            "OR lower(COALESCE(source_version,'')) LIKE '%test%' "
            "OR lower(COALESCE(source_version,'')) LIKE '%qa%' "
            "OR lower(COALESCE(source_version,'')) LIKE 'diag-%')"
        )
        paid_assessment_predicate = f"NOT {test_assessment_predicate}"

        growth_metrics = {
            "total": _count("SELECT COUNT(1) FROM companion_access WHERE active=1 AND access_type='bundle_month1'"),
            "today": _count(
                """
                SELECT COUNT(1) FROM companion_access
                WHERE active=1 AND access_type='bundle_month1'
                  AND COALESCE(granted_at, updated_at) >= ?
                  AND COALESCE(granted_at, updated_at) < ?
                """,
                (day_s, next_day_s),
            ),
            "week": _count(
                """
                SELECT COUNT(1) FROM companion_access
                WHERE active=1 AND access_type='bundle_month1'
                  AND COALESCE(granted_at, updated_at) >= ?
                """,
                (week_s,),
            ),
            "month": _count(
                """
                SELECT COUNT(1) FROM companion_access
                WHERE active=1 AND access_type='bundle_month1'
                  AND COALESCE(granted_at, updated_at) >= ?
                """,
                (month_s,),
            ),
        }

        growth_paid_metrics = {
            "total": _count(
                f"SELECT COUNT(1) FROM companion_access WHERE active=1 AND access_type='bundle_month1' AND ({paid_access_predicate})"
            ),
            "today": _count(
                f"""
                SELECT COUNT(1) FROM companion_access
                WHERE active=1 AND access_type='bundle_month1'
                  AND ({paid_access_predicate})
                  AND COALESCE(granted_at, updated_at) >= ?
                  AND COALESCE(granted_at, updated_at) < ?
                """,
                (day_s, next_day_s),
            ),
        }

        growth_test_metrics = {
            "total": _count(
                f"SELECT COUNT(1) FROM companion_access WHERE active=1 AND access_type='bundle_month1' AND ({test_access_predicate})"
            ),
            "today": _count(
                f"""
                SELECT COUNT(1) FROM companion_access
                WHERE active=1 AND access_type='bundle_month1'
                  AND ({test_access_predicate})
                  AND COALESCE(granted_at, updated_at) >= ?
                  AND COALESCE(granted_at, updated_at) < ?
                """,
                (day_s, next_day_s),
            ),
        }

        completions_metrics = {
            "total": _count("SELECT COUNT(1) FROM assessments"),
            "today": _count("SELECT COUNT(1) FROM assessments WHERE created_at >= ? AND created_at < ?", (day_s, next_day_s)),
            "week": _count("SELECT COUNT(1) FROM assessments WHERE created_at >= ?", (week_s,)),
            "month": _count("SELECT COUNT(1) FROM assessments WHERE created_at >= ?", (month_s,)),
        }

        completions_paid_metrics = {
            "total": _count(f"SELECT COUNT(1) FROM assessments WHERE ({paid_assessment_predicate})"),
            "today": _count(
                f"SELECT COUNT(1) FROM assessments WHERE ({paid_assessment_predicate}) AND created_at >= ? AND created_at < ?",
                (day_s, next_day_s),
            ),
        }

        completions_test_metrics = {
            "total": _count(f"SELECT COUNT(1) FROM assessments WHERE ({test_assessment_predicate})"),
            "today": _count(
                f"SELECT COUNT(1) FROM assessments WHERE ({test_assessment_predicate}) AND created_at >= ? AND created_at < ?",
                (day_s, next_day_s),
            ),
        }
    finally:
        conn.close()

    unresolved = [
        {
            "email": str(r["email"] or "").strip().lower(),
            "status": str(r["status"] or "").strip(),
            "free_8q_email": str(r["free_8q_email"] or "").strip().lower() or None,
            "last_prompt_date_ct": str(r["last_prompt_date_ct"] or "").strip() or None,
            "updated_at": str(r["updated_at"] or "").strip() or None,
        }
        for r in unresolved_rows
    ]

    purge = await quick_signal_purge_report(older_than_days=30)
    blocked = int((purge.get("summary") or {}).get("blocked_linked_not_promoted") or 0)

    tests_result = {
        "enabled": bool(include_integration_tests),
        "ok": None,
        "exit_code": None,
        "output_tail": None,
    }
    if include_integration_tests:
        try:
            attempts = []
            for idx in range(2):
                proc = subprocess.run(
                    ["python3", "/home/ubuntu/.openclaw/workspace/dashboard/scripts/test_critical_paths.py"],
                    capture_output=True,
                    text=True,
                    timeout=180,
                )
                combined = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
                attempts.append((proc.returncode, combined))
                if proc.returncode == 0:
                    break
                time.sleep(2)

            rc, out = attempts[-1]
            tests_result["ok"] = (rc == 0)
            tests_result["exit_code"] = rc
            tests_result["output_tail"] = "\n".join((out or "").splitlines()[-20:]) if out else ""
        except Exception as e:
            tests_result["ok"] = False
            tests_result["exit_code"] = -1
            tests_result["output_tail"] = f"integration_test_exception: {e}"

    quality = {
        "foundation_status": "PASS" if len(non_24q) == 0 else "WARN",
        "links_status": "PASS" if len(unresolved) == 0 else "WARN",
        "purge_status": "PASS" if blocked == 0 else "WARN",
        "checks_status": (
            "NOT RUN" if tests_result.get("enabled") is False else ("PASS" if tests_result.get("ok") else "FAIL")
        ),
    }

    summary = {
        "generated_at": _now_z(),
        "growth": growth_metrics,
        "growth_paid": growth_paid_metrics,
        "growth_test": growth_test_metrics,
        "completions": completions_metrics,
        "completions_paid": completions_paid_metrics,
        "completions_test": completions_test_metrics,
        "quality": quality,
        "non_24q_foundation_count": len(non_24q),
        "non_24q_foundation_users": non_24q[:100],
        "unresolved_8q_link_count": len(unresolved),
        "unresolved_8q_links": unresolved[:100],
        "purge_blocked_linked_not_promoted_30d": blocked,
        "integration_tests": tests_result,
    }

    if send_email:
        it = summary.get("integration_tests") or {}
        growth = summary.get("growth") or {}
        growth_paid = summary.get("growth_paid") or {}
        growth_test = summary.get("growth_test") or {}
        comps = summary.get("completions") or {}
        comps_paid = summary.get("completions_paid") or {}
        comps_test = summary.get("completions_test") or {}
        q = summary.get("quality") or {}

        lines = [
            "PATTERNS DAILY EOD REPORT",
            f"Generated: {summary['generated_at']}",
            "",
            "Growth (Paid Companion)",
            f"- Total: {growth.get('total', 0)}",
            f"- Today: {growth.get('today', 0)}",
            f"- Week: {growth.get('week', 0)}",
            f"- Month: {growth.get('month', 0)}",
            "",
            "Completions (24Q)",
            f"- Total: {comps.get('total', 0)}",
            f"- Today: {comps.get('today', 0)}",
            f"- Week: {comps.get('week', 0)}",
            f"- Month: {comps.get('month', 0)}",
            "",
            "System Quality",
            f"- Foundation Compliance: {max(growth.get('total', 0) - summary['non_24q_foundation_count'], 0)} / {growth.get('total', 0)} ({q.get('foundation_status')})",
            f"- Unresolved Links: {summary['unresolved_8q_link_count']} ({q.get('links_status')})",
            f"- Purge Blocks (30d): {summary['purge_blocked_linked_not_promoted_30d']} ({q.get('purge_status')})",
            f"- Critical Checks: {q.get('checks_status')} ({'3/3' if it.get('ok') else ('0/3' if it.get('enabled') else 'n/a')})",
            "",
            "Needs Attention",
            f"- Missing Foundation: {summary['non_24q_foundation_count']}",
            f"- Link Cleanup: {summary['unresolved_8q_link_count']}",
            "",
            "Details — Missing Foundation",
        ]
        for u in summary["non_24q_foundation_users"][:20]:
            lines.append(f"- {u.get('email')} | source={u.get('resolver_source')} | linked={u.get('assessment_email') or 'none'}")

        lines.append("")
        lines.append("Details — Unresolved Links")
        for u in summary["unresolved_8q_links"][:20]:
            lines.append(f"- {u.get('email')} | state={u.get('status')} | free_email={u.get('free_8q_email') or 'none'}")

        if it.get("output_tail") and it.get("ok") is False:
            lines.append("")
            lines.append("Critical Checks — Failure Details")
            lines.append(str(it.get("output_tail")))

        lines.extend([
            "",
            "Test vs Paid Split (Pilot Clarity)",
            "- Keep this section separate from primary totals.",
            f"- Companion Access (Paid): total={growth_paid.get('total', 0)} | today={growth_paid.get('today', 0)}",
            f"- Companion Access (Test): total={growth_test.get('total', 0)} | today={growth_test.get('today', 0)}",
            f"- 24Q Completions (Paid): total={comps_paid.get('total', 0)} | today={comps_paid.get('today', 0)}",
            f"- 24Q Completions (Test): total={comps_test.get('total', 0)} | today={comps_test.get('today', 0)}",
        ])

        lines.extend([
            "",
            "Legend:",
            "- PASS = healthy",
            "- WARN = attention needed",
            "- FAIL = action required now",
        ])

        _send_matt_critical_alert(
            subject="[Nightly] Patterns Daily EOD Report",
            body="\n".join(lines),
        )

    return summary


@app.post("/api/companion/admin/reconciliation-summary")
async def companion_admin_reconciliation_summary(send_email: bool = Query(True), include_integration_tests: bool = Query(True)):
    """Build nightly reconciliation summary (incl. optional integration tests) and optionally email Matt."""
    summary = await run_companion_reconciliation_summary(send_email=send_email, include_integration_tests=include_integration_tests)
    return {"ok": True, "summary": summary}


@app.post("/api/companion/insight")
async def companion_insight(request: Request):
    # Accept either app-auth user OR companion magic-link session
    user = get_optional_user(request)
    session_email = (request.cookies.get("companion_session_email") or "").strip().lower()
    email = (user.get("email") if user else session_email).strip().lower() if (user or session_email) else ""
    if not email:
        raise HTTPException(status_code=401, detail="Not authenticated")

    gate_conn = _patterns_conn()
    try:
        st = _stage_a_status(gate_conn, email)
    finally:
        gate_conn.close()
    if not st.get("required_complete"):
        return JSONResponse(content={
            "ok": False,
            "limited": True,
            "reason": "stage_a_incomplete",
            "missing_slots": st.get("missing_slots", []),
            "text": "Complete onboarding context to unlock personalized insights."
        }, status_code=409)

    body = await request.json()
    interaction_type = (body.get("interaction_type") or "").strip().lower()
    inputs = body.get("inputs") or {}
    profile = body.get("profile") or _profile_for_email(email)
    
    # Compute user state and appropriate intervention
    conn = sqlite3.connect(str(DB_PATH))
    user_context = {
        "email": email,
        "archetype": profile.get('archetype','Architect'),
        "secondary": profile.get('secondary','Navigator')
    }
    try:
        user_context = enrich_companion_context(conn, user_context)
    finally:
        conn.close()
    
    # Add user state information to the response
    user_state = user_context.get("user_state", UserState.UNKNOWN)
    intervention_type = user_context.get("intervention_type", InterventionType.UNBLOCK)

    system = (
        f"You are the CHANNELED Implementation Companion for {profile.get('name','Member')}. "
        f"Profile: {profile.get('archetype','Architect')} / {profile.get('secondary','Navigator')} ({profile.get('context','personal')}). "
        f"Top elements: {', '.join(profile.get('channeled_top', []))}. "
        f"Frictions: {profile.get('friction_1','')} | {profile.get('friction_2','')}. "
        f"Current user state: {user_state}. Intervention approach: {intervention_type}. "
        "Respond in 1-3 sentences, specific, direct, no platitudes. "
        f"{COMPANION_FRAMEWORK_LOCK_BLOCK} "
        f"{COMPANION_ARCHETYPE_INTEGRITY_BLOCK}"
    )

    if interaction_type == "midday":
        coaching_intensity = ""
        pref_conn = _patterns_conn()
        try:
            pref_row = pref_conn.execute(
                "SELECT coaching_style_intensity FROM companion_intake WHERE lower(email)=lower(?) ORDER BY id DESC LIMIT 1",
                (email,),
            ).fetchone()
            coaching_intensity = str(pref_row[0]).strip().lower() if pref_row and pref_row[0] else ""
        finally:
            pref_conn.close()

        tone_rule = ""
        if coaching_intensity == "read_the_room":
            tone_rule = "Use supportive-direct tone: keep urgency, but avoid harsh/commanding phrasing."
        elif coaching_intensity == "push":
            tone_rule = "Use assertive execution tone with clear urgency."

        prompt = (
            f"Mid-day check-in status: {inputs.get('status','not provided')}. "
            f"Actions completed: {inputs.get('actions_completed',0)} of {inputs.get('actions_total',3)}. "
            f"User state: {user_state}. "
            f"{tone_rule} "
            "Generate ONE unified 'Today Focus' block (not two sections). "
            "Format exactly as: line 1='Today Focus: <single concrete outcome for today>'; "
            "line 2='1) <choose action tied directly to line 1>'; "
            "line 3='2) <execute action with a concrete time window today>'; "
            "line 4='3) <report measurable proof/result>'. "
            "All 3 steps must directly operationalize line 1 and reuse its key nouns. "
            "No generic template language, no extra headings, max 4 short lines."
        )
    elif interaction_type == "evening":
        prompt = (
            f"Evening reflection: completed={inputs.get('completed','not answered')}; "
            f"obstacle={inputs.get('obstacle','not answered')}; note={inputs.get('note','')}. "
            f"User state: {user_state}. "
            "Generate a 2-3 sentence insight: pattern + what it means + what to carry into tomorrow."
        )
    else:
        raise HTTPException(status_code=422, detail="interaction_type must be midday or evening")

    # Use context-aware LLM call
    text = _call_companion_llm(system, prompt, model=COMPANION_HAIKU_MODEL, max_tokens=240, context=user_context)
    
    # Add metadata to the response
    return {
        "ok": True, 
        "text": text, 
        "user_state": user_state,
        "intervention_type": intervention_type
    }




@app.get("/api/companion/access-status")
async def companion_access_status(request: Request):
    user = get_optional_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    has_access, reason, row = _companion_access_decision(user["email"])
    out = {
        "ok": True,
        "has_access": bool(has_access),
        "reason": reason,
        "email": user["email"],
    }
    if row:
        out.update({
            "active": int(row["active"] or 0) if "active" in row.keys() else 0,
            "expires_at": str(row["expires_at"] or "") if "expires_at" in row.keys() else "",
            "access_type": str(row["access_type"] or "") if "access_type" in row.keys() else "",
        })
    return out

@app.get("/assessment")
async def channeled_assessment_page():
    return FileResponse(str(static_dir / "patterns" / "channeled_assessment.html"))


@app.get("/intake")
async def channeled_intake_page(request: Request):
    email = (request.cookies.get("companion_session_email") or "").strip().lower()
    if not email:
        return RedirectResponse(url="/login?reason=companion_inactive", status_code=302)

    has_access, reason, access_row = _companion_access_decision(email)
    if not has_access:
        return RedirectResponse(url="/login?reason=companion_inactive", status_code=302)

    intake_completed = int(access_row["intake_completed"] or 0) if access_row and "intake_completed" in access_row.keys() else 0
    if intake_completed == 1:
        return RedirectResponse(url="/companion", status_code=302)

    return FileResponse(str(static_dir / "patterns" / "channeled_intake.html"))


@app.get("/companion")
async def channeled_companion_page(request: Request):
    email = (request.cookies.get("companion_session_email") or "").strip().lower()
    if not email:
        return RedirectResponse(url="/login?reason=companion_inactive", status_code=302)

    has_access, reason, access_row = _companion_access_decision(email)
    if not has_access:
        return RedirectResponse(url="/login?reason=companion_inactive", status_code=302)

    intake_completed = int(access_row["intake_completed"] or 0) if access_row and "intake_completed" in access_row.keys() else 0
    if intake_completed != 1:
        return RedirectResponse(url="/channeled_results.html", status_code=302)

    return FileResponse(str(static_dir / "patterns" / "channeled_companion.html"))


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    host = (request.headers.get("host") or "").split(":")[0].lower()
    if host in {"channeled.org", "www.channeled.org"}:
        homepage_path = static_dir / "patterns" / "chaneled_homepage.html"
        if not homepage_path.exists():
            homepage_path = static_dir / "patterns" / "channeled_homepage.html"
        return FileResponse(str(homepage_path))

    session_id = request.client.host
    if session_id in authenticated_sessions:
        return RedirectResponse(url="/dashboard")
    return RedirectResponse(url="/login")

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: str = None):
    host = (request.headers.get("host") or "").split(":")[0].lower()
    if host in {"channeled.org", "www.channeled.org"}:
        return FileResponse(str(static_dir / "patterns" / "channeled_login.html"))

    from jinja2 import Template
    template = Template(LOGIN_HTML)
    return HTMLResponse(content=template.render(error=error))

@app.post("/login")
async def login(request: Request, password: str = Form(...)):
    if password == DASHBOARD_PASSWORD:
        session_id = request.client.host
        authenticated_sessions.add(session_id)
        return RedirectResponse(url="/dashboard", status_code=302)
    return RedirectResponse(url="/login?error=Invalid+password", status_code=302)

@app.get("/logout")
async def logout(request: Request):
    session_id = request.client.host
    authenticated_sessions.discard(session_id)
    return RedirectResponse(url="/login")

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, notice: str = None, detail: str = None):
    session_id = request.client.host
    if session_id not in authenticated_sessions:
        return RedirectResponse(url="/login")
    
    from jinja2 import Template
    template = Template(DASHBOARD_HTML)
    
    from datetime import datetime
    from zoneinfo import ZoneInfo
    
    server_time = datetime.now()
    central_time = server_time.astimezone(ZoneInfo("America/Chicago"))
    
    # Format times for display - use lstrip/replace for compatibility
    srv_time_str = server_time.strftime('%m/%d/%Y, %I:%M:%S %p')
    srv_time_str = srv_time_str.lstrip('0').replace('/0', '/').replace(' 0', ' ')
    ct_time_str = central_time.strftime('%H:%M:%S')
    last_updated_str = f"{srv_time_str} ({ct_time_str} CT)"
    
    # Load saved segmentation weights so UI reflects persisted values after refresh
    hook_pct, proof_pct, cta_pct = 22, 48, 30
    profile_path = Path("/home/ubuntu/.openclaw/workspace/projects/ugc-video-pipeline/contracts/segmentation.profile.json")
    try:
        if profile_path.exists():
            profile = json.loads(profile_path.read_text())
            segs = profile.get("segments", [])
            if len(segs) >= 3:
                hook_pct = round(float(segs[0].get("weight", 0.22)) * 100)
                proof_pct = round(float(segs[1].get("weight", 0.48)) * 100)
                cta_pct = round(float(segs[2].get("weight", 0.30)) * 100)
    except Exception:
        pass

    notice_map = {
        "cuts-saved": "Cuts saved",
        "pipeline-ok": "Pipeline success",
        "pipeline-fail": "Pipeline failed",
    }
    notice_text = notice_map.get((notice or "").strip(), (notice or "idle"))

    html_content = template.render(
        client_ip=request.client.host,
        server_time=server_time.strftime("%Y-%m-%d %H:%M:%S %Z"),
        last_updated=last_updated_str,
        notice=notice_text,
        detail=detail or "",
        hook_pct=hook_pct,
        proof_pct=proof_pct,
        cta_pct=cta_pct,
    )
    
    return HTMLResponse(content=html_content)

@app.post("/upload-song")
async def upload_song(request: Request, song_file: UploadFile = File(...)):
    session_id = request.client.host
    if session_id not in authenticated_sessions:
        return RedirectResponse(url="/login?reason=companion_inactive", status_code=302)

    project_root = Path("/home/ubuntu/.openclaw/workspace/projects/ugc-video-pipeline")
    target_dir = project_root / "audio" / "music_owned"
    target_dir.mkdir(parents=True, exist_ok=True)

    filename = Path(song_file.filename or "uploaded-track.wav").name
    target_path = target_dir / filename

    contents = await song_file.read()
    if not contents:
        return RedirectResponse(url="/dashboard?upload=empty", status_code=302)

    target_path.write_bytes(contents)
    return RedirectResponse(url=f"/dashboard?upload=ok&file={filename}", status_code=302)


@app.post("/upload-song-chunk")
async def upload_song_chunk(
    request: Request,
    upload_id: str = Form(...),
    filename: str = Form(...),
    chunk_index: int = Form(...),
    total_chunks: int = Form(...),
    data_b64: str = Form(...),
):
    session_id = request.client.host
    if session_id not in authenticated_sessions:
        raise HTTPException(status_code=401, detail="Not authenticated")

    project_root = Path("/home/ubuntu/.openclaw/workspace/projects/ugc-video-pipeline")
    temp_dir = project_root / ".tmp_uploads"
    temp_dir.mkdir(parents=True, exist_ok=True)

    safe_name = Path(filename).name
    part_path = temp_dir / f"{upload_id}.part"

    try:
        chunk_bytes = base64.b64decode(data_b64)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid chunk encoding")

    if chunk_index == 0 and part_path.exists():
        part_path.unlink()

    with part_path.open("ab") as f:
        f.write(chunk_bytes)

    done = chunk_index >= (total_chunks - 1)
    if done:
        target_dir = project_root / "audio" / "music_owned"
        target_dir.mkdir(parents=True, exist_ok=True)
        final_path = target_dir / safe_name
        part_path.replace(final_path)
        return JSONResponse({"ok": True, "done": True, "file": safe_name, "path": str(final_path)})

    return JSONResponse({"ok": True, "done": False, "chunk": chunk_index})


@app.post("/upload-clip-chunk")
async def upload_clip_chunk(
    request: Request,
    upload_id: str = Form(...),
    filename: str = Form(...),
    chunk_index: int = Form(...),
    total_chunks: int = Form(...),
    data_b64: str = Form(...),
):
    session_id = request.client.host
    if session_id not in authenticated_sessions:
        raise HTTPException(status_code=401, detail="Not authenticated")

    project_root = Path("/home/ubuntu/.openclaw/workspace/projects/ugc-video-pipeline")
    temp_dir = project_root / ".tmp_uploads"
    temp_dir.mkdir(parents=True, exist_ok=True)

    safe_name = Path(filename).name
    part_path = temp_dir / f"clip-{upload_id}.part"

    try:
        chunk_bytes = base64.b64decode(data_b64)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid chunk encoding")

    if chunk_index == 0 and part_path.exists():
        part_path.unlink()

    with part_path.open("ab") as f:
        f.write(chunk_bytes)

    done = chunk_index >= (total_chunks - 1)
    if done:
        target_dir = project_root / "ingestion" / "mirror"
        target_dir.mkdir(parents=True, exist_ok=True)
        final_path = target_dir / safe_name
        part_path.replace(final_path)
        return JSONResponse({"ok": True, "done": True, "file": safe_name, "path": str(final_path)})

    return JSONResponse({"ok": True, "done": False, "chunk": chunk_index})


@app.post("/set-segmentation-weights")
async def set_segmentation_weights(
    request: Request,
    hook: float = Form(...),
    proof: float = Form(...),
    cta: float = Form(...),
):
    session_id = request.client.host
    if session_id not in authenticated_sessions:
        raise HTTPException(status_code=401, detail="Not authenticated")

    vals = [max(0.05, float(hook)), max(0.05, float(proof)), max(0.05, float(cta))]
    s = sum(vals)
    weights = [v / s for v in vals]

    profile_path = Path("/home/ubuntu/.openclaw/workspace/projects/ugc-video-pipeline/contracts/segmentation.profile.json")
    profile = json.loads(profile_path.read_text()) if profile_path.exists() else {"segments": []}

    segs = profile.get("segments", [])
    if len(segs) < 3:
        segs = [
            {"id": "seg1", "label": "hook", "minSec": 2.0, "maxSec": 5.0, "captionHint": "Hook"},
            {"id": "seg2", "label": "proof", "minSec": 4.0, "maxSec": 10.0, "captionHint": "Proof"},
            {"id": "seg3", "label": "cta", "minSec": 2.0, "maxSec": 6.0, "captionHint": "CTA"},
        ]

    segs[0]["weight"] = round(weights[0], 4)
    segs[1]["weight"] = round(weights[1], 4)
    segs[2]["weight"] = round(weights[2], 4)
    profile["segments"] = segs
    profile_path.write_text(json.dumps(profile, indent=2))

    return JSONResponse({"ok": True, "weights": {"hook": segs[0]["weight"], "proof": segs[1]["weight"], "cta": segs[2]["weight"]}})


@app.post("/set-segmentation-weights-form")
async def set_segmentation_weights_form(
    request: Request,
    hook: float = Form(...),
    proof: float = Form(...),
    cta: float = Form(...),
):
    session_id = request.client.host
    if session_id not in authenticated_sessions:
        return RedirectResponse(url="/login?reason=companion_inactive", status_code=302)

    vals = [max(0.05, float(hook)), max(0.05, float(proof)), max(0.05, float(cta))]
    s = sum(vals)
    weights = [v / s for v in vals]

    profile_path = Path("/home/ubuntu/.openclaw/workspace/projects/ugc-video-pipeline/contracts/segmentation.profile.json")
    profile = json.loads(profile_path.read_text()) if profile_path.exists() else {"segments": []}
    segs = profile.get("segments", [])
    if len(segs) < 3:
        segs = [
            {"id": "seg1", "label": "hook", "minSec": 2.0, "maxSec": 5.0, "captionHint": "Hook"},
            {"id": "seg2", "label": "proof", "minSec": 4.0, "maxSec": 10.0, "captionHint": "Proof"},
            {"id": "seg3", "label": "cta", "minSec": 2.0, "maxSec": 6.0, "captionHint": "CTA"},
        ]
    segs[0]["weight"] = round(weights[0], 4)
    segs[1]["weight"] = round(weights[1], 4)
    segs[2]["weight"] = round(weights[2], 4)
    profile["segments"] = segs
    profile_path.write_text(json.dumps(profile, indent=2))

    msg = f"saved-{round(segs[0]['weight']*100)}/{round(segs[1]['weight']*100)}/{round(segs[2]['weight']*100)}"
    return RedirectResponse(url=f"/dashboard?notice=cuts-saved&detail={msg}", status_code=302)


@app.post("/run-ugc-pipeline")
async def run_ugc_pipeline(request: Request):
    session_id = request.client.host
    if session_id not in authenticated_sessions:
        raise HTTPException(status_code=401, detail="Not authenticated")

    project_root = Path("/home/ubuntu/.openclaw/workspace/projects/ugc-video-pipeline")
    cmd = ["bash", "-lc", "./scripts/run_pipeline.sh"]
    proc = subprocess.run(cmd, cwd=str(project_root), capture_output=True, text=True, timeout=180)

    output = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
    lines = [ln for ln in output.splitlines() if ln.strip()]
    tail = "\n".join(lines[-20:])

    return JSONResponse({
        "ok": proc.returncode == 0,
        "returnCode": proc.returncode,
        "summary": "Pipeline complete + validated" if proc.returncode == 0 else "Pipeline failed",
        "tail": tail,
    })


@app.post("/run-ugc-pipeline-form")
async def run_ugc_pipeline_form(request: Request):
    session_id = request.client.host
    if session_id not in authenticated_sessions:
        return RedirectResponse(url="/login?reason=companion_inactive", status_code=302)

    project_root = Path("/home/ubuntu/.openclaw/workspace/projects/ugc-video-pipeline")
    cmd = ["bash", "-lc", "./scripts/run_pipeline.sh"]
    proc = subprocess.run(cmd, cwd=str(project_root), capture_output=True, text=True, timeout=180)
    output = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
    lines = [ln for ln in output.splitlines() if ln.strip()]
    tail = " | ".join(lines[-2:]) if lines else "no-output"

    notice = "pipeline-ok" if proc.returncode == 0 else "pipeline-fail"
    return RedirectResponse(url=f"/dashboard?notice={notice}&detail={tail[:160]}", status_code=302)

@app.get("/patterns-library", response_class=HTMLResponse)
async def patterns_library(request: Request):
    # No authentication required - public access

    # Read the patterns library HTML file
    template_path = Path(__file__).parent / "templates" / "patterns_library.html"
    if template_path.exists():
        html_content = template_path.read_text()
        return HTMLResponse(content=html_content)
    else:
        return HTMLResponse(content="<h1>Patterns Library not found</h1>", status_code=404)

@app.get("/workspace-structure", response_class=HTMLResponse)
async def workspace_structure(request: Request):
    # No authentication required - public access

    # Read the workspace structure HTML file
    template_path = Path(__file__).parent / "workspace_structure.html"
    if template_path.exists():
        html_content = template_path.read_text()
        return HTMLResponse(content=html_content)
    else:
        return HTMLResponse(content="<h1>Workspace Structure not found</h1>", status_code=404)

@app.get("/mission_control", response_class=HTMLResponse)
async def mission_control(request: Request):
    # No authentication required - public access
    
    # Read the mission control HTML file
    template_path = Path(__file__).parent / "templates" / "mission_control.html"
    if template_path.exists():
        html_content = template_path.read_text()
        return HTMLResponse(content=html_content)
    else:
        return HTMLResponse(content="<h1>Mission Control not found</h1>", status_code=404)

@app.get("/patterns_paradigm_architecture.html", response_class=HTMLResponse)
async def patterns_paradigm_architecture(request: Request):
    # No authentication required - public access
    template_path = Path(__file__).parent / "templates" / "patterns_paradigm_architecture.html"
    if template_path.exists():
        html_content = template_path.read_text()
        return HTMLResponse(content=html_content)
    else:
        return HTMLResponse(content="<h1>File not found</h1>", status_code=404)

@app.get("/patterns_paradigm_schema.html", response_class=HTMLResponse)
async def patterns_paradigm_schema(request: Request):
    # No authentication required - public access
    template_path = Path(__file__).parent / "templates" / "patterns_paradigm_schema.html"
    if template_path.exists():
        html_content = template_path.read_text()
        return HTMLResponse(content=html_content)
    else:
        return HTMLResponse(content="<h1>File not found</h1>", status_code=404)

@app.get("/video-gallery", response_class=HTMLResponse)
async def video_gallery(request: Request):
    """UGC Video Gallery - preview and download rendered shorts"""
    from datetime import datetime
    
    videos = []
    ugc_output_dir = Path("/home/ubuntu/.openclaw/workspace/projects/ugc-video-pipeline/output")
    
    if ugc_output_dir.exists():
        for video_file in sorted(ugc_output_dir.glob("*.mp4"), key=lambda x: x.stat().st_mtime, reverse=True):
            if video_file.name == "google_oauth_demo.mp4":  # Skip demo video
                continue
            stat = video_file.stat()
            size_mb = round(stat.st_size / (1024 * 1024), 1)
            created = datetime.fromtimestamp(stat.st_mtime).strftime("%b %d, %I:%M %p")
            videos.append({
                "name": video_file.stem,
                "url": f"/ugc-videos/{video_file.name}",
                "size_mb": size_mb,
                "created": created
            })
    
    template_path = Path(__file__).parent / "templates" / "video_gallery.html"
    if template_path.exists():
        from jinja2 import Template
        template = Template(template_path.read_text())
        html_content = template.render(videos=videos)
        return HTMLResponse(content=html_content)
    else:
        return HTMLResponse(content="<h1>Gallery template not found</h1>", status_code=404)

@app.get("/caption-designer", response_class=HTMLResponse)
async def caption_designer(request: Request):
    session_id = request.client.host
    if session_id not in authenticated_sessions:
        return RedirectResponse(url="/login")

    template_path = Path(__file__).parent / "templates" / "caption_designer.html"
    if not template_path.exists():
        return HTMLResponse(content="<h1>Caption designer template not found</h1>", status_code=404)
    return HTMLResponse(content=template_path.read_text(encoding="utf-8"))


@app.get("/api/caption-preset/{name}")
async def api_get_caption_preset(name: str, request: Request):
    session_id = request.client.host
    if session_id not in authenticated_sessions:
        raise HTTPException(status_code=401, detail="Not authenticated")

    safe_name = Path(name).name
    preset_path = caption_presets_dir / f"{safe_name}.json"
    if not preset_path.exists():
        raise HTTPException(status_code=404, detail="Preset not found")
    return JSONResponse(content=json.loads(preset_path.read_text(encoding="utf-8")))


@app.get("/api/caption-presets")
async def api_list_caption_presets(request: Request):
    session_id = request.client.host
    if session_id not in authenticated_sessions:
        raise HTTPException(status_code=401, detail="Not authenticated")

    presets = sorted([p.stem for p in caption_presets_dir.glob("*.json")])
    return JSONResponse(content={"presets": presets})


@app.post("/api/caption-preset/save")
async def api_save_caption_preset(request: Request):
    session_id = request.client.host
    if session_id not in authenticated_sessions:
        raise HTTPException(status_code=401, detail="Not authenticated")

    body = await request.json()
    name = Path((body.get("name") or "").strip()).name
    if not name:
        return JSONResponse(content={"ok": False, "error": "Preset name required"}, status_code=400)

    body["name"] = name
    preset_path = caption_presets_dir / f"{name}.json"
    preset_path.write_text(json.dumps(body, indent=2), encoding="utf-8")
    return JSONResponse(content={"ok": True, "path": str(preset_path)})


@app.get("/api/render-jobs")
async def api_list_render_jobs(request: Request):
    session_id = request.client.host
    if session_id not in authenticated_sessions:
        raise HTTPException(status_code=401, detail="Not authenticated")

    jobs_dir = Path("/home/ubuntu/.openclaw/workspace/projects/ugc-video-pipeline/contracts/shorts_jobs")
    jobs = sorted([p.name for p in jobs_dir.glob("*.render.job.json")])
    return JSONResponse(content={"jobs": jobs})


@app.get("/api/render-job/{job_file}")
async def api_get_render_job(job_file: str, request: Request):
    session_id = request.client.host
    if session_id not in authenticated_sessions:
        raise HTTPException(status_code=401, detail="Not authenticated")

    safe_job = Path((job_file or "").strip()).name
    if not safe_job:
        return JSONResponse(content={"ok": False, "error": "jobFile required"}, status_code=400)

    jobs_dir = Path("/home/ubuntu/.openclaw/workspace/projects/ugc-video-pipeline/contracts/shorts_jobs")
    job_path = jobs_dir / safe_job
    if not job_path.exists():
        return JSONResponse(content={"ok": False, "error": "Render job not found"}, status_code=404)

    job = json.loads(job_path.read_text(encoding="utf-8"))
    clips = []
    for idx, clip in enumerate(job.get("clipTimeline") or []):
        clips.append({
            "index": idx,
            "clipId": str(clip.get("clipId") or f"clip-{idx+1}"),
            "startSec": float(clip.get("startSec", 0) or 0),
            "endSec": float(clip.get("endSec", 0) or 0),
            "caption": str(clip.get("caption") or ""),
        })

    caption_timeline = []
    for idx, item in enumerate(job.get("captionTimeline") or []):
        if not isinstance(item, dict):
            continue
        caption_timeline.append({
            "id": str(item.get("id") or f"cap-{idx+1}"),
            "text": str(item.get("text") or ""),
            "startSec": float(item.get("startSec", 0) or 0),
            "durationSec": float(item.get("durationSec", 0) or 0),
            "style": item.get("style") or {},
        })

    return JSONResponse(content={
        "ok": True,
        "jobFile": safe_job,
        "durationSec": float(job.get("durationSec", 0) or 0),
        "clips": clips,
        "captionTimeline": caption_timeline,
    })


@app.post("/api/render-job/caption-timeline")
async def api_save_render_job_caption_timeline(request: Request):
    session_id = request.client.host
    if session_id not in authenticated_sessions:
        raise HTTPException(status_code=401, detail="Not authenticated")

    body = await request.json()
    job_file = Path((body.get("jobFile") or "").strip()).name
    timeline_items = body.get("captionTimeline") or []

    if not job_file:
        return JSONResponse(content={"ok": False, "error": "jobFile required"}, status_code=400)
    if not isinstance(timeline_items, list):
        return JSONResponse(content={"ok": False, "error": "captionTimeline list required"}, status_code=400)

    jobs_dir = Path("/home/ubuntu/.openclaw/workspace/projects/ugc-video-pipeline/contracts/shorts_jobs")
    job_path = jobs_dir / job_file
    if not job_path.exists():
        return JSONResponse(content={"ok": False, "error": "Render job not found"}, status_code=404)

    normalized = []
    for idx, item in enumerate(timeline_items):
        if not isinstance(item, dict):
            continue
        start_sec = float(item.get("startSec", 0) or 0)
        duration_sec = float(item.get("durationSec", 0) or 0)
        if start_sec < 0:
            return JSONResponse(content={"ok": False, "error": f"captionTimeline[{idx}].startSec must be >= 0"}, status_code=400)
        if duration_sec <= 0:
            return JSONResponse(content={"ok": False, "error": f"captionTimeline[{idx}].durationSec must be > 0"}, status_code=400)
        normalized.append({
            "id": str(item.get("id") or f"cap-{idx+1}"),
            "text": str(item.get("text") or ""),
            "startSec": start_sec,
            "durationSec": duration_sec,
            "style": item.get("style") or {},
        })

    job = json.loads(job_path.read_text(encoding="utf-8"))
    total_duration = float(job.get("durationSec", 0) or 0)
    if total_duration <= 0:
        total_duration = 0.0
        for c in job.get("clipTimeline") or []:
            total_duration = max(total_duration, float(c.get("endSec", 0) or 0))

    if total_duration > 0 and normalized:
        max_end = max((float(i.get("startSec", 0)) + float(i.get("durationSec", 0)) for i in normalized), default=0)
        if max_end - total_duration > 1e-6:
            return JSONResponse(
                content={"ok": False, "error": f"captionTimeline exceeds job duration ({max_end:.2f}s > {total_duration:.2f}s)"},
                status_code=400,
            )
    job["captionTimeline"] = normalized
    job_path.write_text(json.dumps(job, indent=2), encoding="utf-8")

    return JSONResponse(content={
        "ok": True,
        "jobFile": job_file,
        "captionTimelineCount": len(normalized),
    })


@app.post("/api/render-job/captions")
async def api_save_render_job_captions(request: Request):
    session_id = request.client.host
    if session_id not in authenticated_sessions:
        raise HTTPException(status_code=401, detail="Not authenticated")

    body = await request.json()
    job_file = Path((body.get("jobFile") or "").strip()).name
    clip_captions = body.get("clips") or []

    if not job_file:
        return JSONResponse(content={"ok": False, "error": "jobFile required"}, status_code=400)
    if not isinstance(clip_captions, list):
        return JSONResponse(content={"ok": False, "error": "clips list required"}, status_code=400)

    jobs_dir = Path("/home/ubuntu/.openclaw/workspace/projects/ugc-video-pipeline/contracts/shorts_jobs")
    job_path = jobs_dir / job_file
    if not job_path.exists():
        return JSONResponse(content={"ok": False, "error": "Render job not found"}, status_code=404)

    job = json.loads(job_path.read_text(encoding="utf-8"))
    timeline = job.get("clipTimeline") or []
    clip_id_to_caption = {
        str(item.get("clipId") or ""): str(item.get("caption") or "")
        for item in clip_captions if isinstance(item, dict)
    }

    updated = 0
    for i, clip in enumerate(timeline):
        cid = str(clip.get("clipId") or "")
        if cid in clip_id_to_caption:
            clip["caption"] = clip_id_to_caption[cid]
            updated += 1

    job_path.write_text(json.dumps(job, indent=2), encoding="utf-8")
    return JSONResponse(content={"ok": True, "jobFile": job_file, "clipsUpdated": updated})


@app.post("/api/caption-preset/apply")
async def api_apply_caption_preset_to_job(request: Request):
    session_id = request.client.host
    if session_id not in authenticated_sessions:
        raise HTTPException(status_code=401, detail="Not authenticated")

    body = await request.json()
    preset_name = Path((body.get("presetName") or "").strip()).name
    job_file = Path((body.get("jobFile") or "").strip()).name
    apply_text = bool(body.get("applyText", False))
    caption_text = str(body.get("captionText") or "").strip()
    hook_text = str(body.get("hookText") or "")
    manual_words = str(body.get("manualWords") or "")
    manual_line_breaks = bool(body.get("manualLineBreaks", False))

    if not preset_name:
        return JSONResponse(content={"ok": False, "error": "presetName required"}, status_code=400)
    if not job_file:
        return JSONResponse(content={"ok": False, "error": "jobFile required"}, status_code=400)

    preset_path = caption_presets_dir / f"{preset_name}.json"
    jobs_dir = Path("/home/ubuntu/.openclaw/workspace/projects/ugc-video-pipeline/contracts/shorts_jobs")
    job_path = jobs_dir / job_file

    if not preset_path.exists():
        return JSONResponse(content={"ok": False, "error": "Preset not found"}, status_code=404)
    if not job_path.exists():
        return JSONResponse(content={"ok": False, "error": "Render job not found"}, status_code=404)

    preset = json.loads(preset_path.read_text(encoding="utf-8"))
    style = (preset.get("style") or {}) if isinstance(preset, dict) else {}
    if not style:
        return JSONResponse(content={"ok": False, "error": "Preset has no style"}, status_code=400)

    job = json.loads(job_path.read_text(encoding="utf-8"))
    clips = job.get("clipTimeline") or []
    updated = 0
    text_updates = 0
    for clip in clips:
        clip["captionStyle"] = {
            "x": int(style.get("x", 40)),
            "y": int(style.get("y", 332)),
            "fontSize": int(style.get("fontSize", 34)),
            "fontWeight": str(style.get("fontWeight", "700")),
            "color": str(style.get("color", "#ffffff")),
            "outline": bool(style.get("outline", True)),
            "motion": str(style.get("motion", "static")),
            "typeSpeed": int(style.get("typeSpeed", 20)),
            "fadeDuration": float(style.get("fadeDuration", 0.6)),
        }
        clip["captionFormat"] = {
            "hookText": hook_text,
            "manualWords": manual_words,
            "manualLineBreaks": manual_line_breaks,
        }
        if apply_text and caption_text:
            clip["caption"] = caption_text
            text_updates += 1
        updated += 1

    job_path.write_text(json.dumps(job, indent=2), encoding="utf-8")
    return JSONResponse(content={
        "ok": True,
        "jobFile": job_file,
        "presetName": preset_name,
        "clipsUpdated": updated,
        "textUpdates": text_updates,
        "jobPath": str(job_path),
    })


@app.post("/api/render-job")
async def api_render_job(request: Request):
    session_id = request.client.host
    if session_id not in authenticated_sessions:
        raise HTTPException(status_code=401, detail="Not authenticated")

    body = await request.json()
    job_file = Path((body.get("jobFile") or "").strip()).name
    if not job_file:
        return JSONResponse(content={"ok": False, "error": "jobFile required"}, status_code=400)

    project_root = Path("/home/ubuntu/.openclaw/workspace/projects/ugc-video-pipeline")
    job_path = project_root / "contracts" / "shorts_jobs" / job_file
    if not job_path.exists():
        return JSONResponse(content={"ok": False, "error": "Render job not found"}, status_code=404)

    try:
        job = json.loads(job_path.read_text(encoding="utf-8"))
        hook_id = str(job.get("hookId") or Path(job_file).stem.replace(".render.job", ""))
        output_file = f"{hook_id}.mp4"

        cmd = [
            "python3",
            "scripts/render_job.py",
            f"contracts/shorts_jobs/{job_file}",
            f"output/{output_file}",
        ]
        result = subprocess.run(
            cmd,
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=600,
        )

        if result.returncode != 0:
            return JSONResponse(content={
                "ok": False,
                "error": "Render failed",
                "stderr": (result.stderr or "")[-1200:],
            }, status_code=500)

        video_url = f"/ugc-videos/{output_file}"
        return JSONResponse(content={
            "ok": True,
            "jobFile": job_file,
            "outputFile": output_file,
            "videoUrl": video_url,
            "stdout": (result.stdout or "")[-1200:],
        })
    except subprocess.TimeoutExpired:
        return JSONResponse(content={"ok": False, "error": "Render timed out"}, status_code=504)
    except Exception as e:
        return JSONResponse(content={"ok": False, "error": str(e)}, status_code=500)


@app.get("/patterns_paradigm_build_plan.html", response_class=HTMLResponse)
async def patterns_paradigm_build_plan(request: Request):
    # No authentication required - public access
    template_path = Path(__file__).parent / "templates" / "patterns_paradigm_build_plan.html"
    if template_path.exists():
        html_content = template_path.read_text()
        return HTMLResponse(content=html_content)
    else:
        return HTMLResponse(content="<h1>File not found</h1>", status_code=404)

@app.get("/patterns_paradigm_journey.html", response_class=HTMLResponse)
async def patterns_paradigm_journey(request: Request):
    # No authentication required - public access
    template_path = Path(__file__).parent / "templates" / "patterns_paradigm_journey.html"
    if template_path.exists():
        html_content = template_path.read_text()
        return HTMLResponse(content=html_content)
    else:
        return HTMLResponse(content="<h1>File not found</h1>", status_code=404)

@app.get("/patterns_paradigm_revelation.html", response_class=HTMLResponse)
async def patterns_paradigm_revelation(request: Request):
    # No authentication required - public access
    template_path = Path(__file__).parent / "templates" / "patterns_paradigm_revelation.html"
    if template_path.exists():
        html_content = template_path.read_text()
        return HTMLResponse(content=html_content)
    else:
        return HTMLResponse(content="<h1>File not found</h1>", status_code=404)

@app.get("/patterns_paradigm_assessment_mvp.html", response_class=HTMLResponse)
async def patterns_paradigm_assessment_mvp(request: Request):
    # No authentication required - public access
    template_path = Path(__file__).parent / "templates" / "patterns_paradigm_assessment_mvp.html"
    if template_path.exists():
        html_content = template_path.read_text()
        return HTMLResponse(content=html_content)
    else:
        return HTMLResponse(content="<h1>File not found</h1>", status_code=404)

@app.get("/patterns_paradigm_assessment.html", response_class=HTMLResponse)
async def patterns_paradigm_assessment(request: Request):
    """Full 40-question CHANNELED assessment with weighted scoring"""
    # No authentication required - public access
    template_path = Path(__file__).parent / "templates" / "patterns_paradigm_assessment.html"
    if template_path.exists():
        html_content = template_path.read_text()
        return HTMLResponse(content=html_content)
    else:
        return HTMLResponse(content="<h1>File not found</h1>", status_code=404)

@app.get("/patterns_assessment_review.html", response_class=HTMLResponse)
async def patterns_assessment_review(request: Request):
    """Admin review page for latest CHANNELED assessment"""
    # No authentication required - public access
    template_path = Path(__file__).parent / "templates" / "patterns_assessment_review.html"
    if template_path.exists():
        html_content = template_path.read_text()
        return HTMLResponse(content=html_content)
    else:
        return HTMLResponse(content="<h1>File not found</h1>", status_code=404)

@app.get("/mission_control_foundation.html", response_class=HTMLResponse)
async def mission_control_foundation(request: Request):
    # No authentication required - public access
    template_path = Path(__file__).parent / "templates" / "mission_control_foundation.html"
    if template_path.exists():
        html_content = template_path.read_text()
        return HTMLResponse(
            content=html_content,
            headers={
                "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
                "Pragma": "no-cache",
                "Expires": "0",
            },
        )
    else:
        return HTMLResponse(content="<h1>File not found</h1>", status_code=404)

# ============== API ENDPOINTS ==============

@app.get("/api/patterns/assessment/latest")
async def latest_patterns_assessment():
    """Return latest saved CHANNELED assessment (if any)"""
    files = sorted(assessments_dir.glob("assessment_*.json"))
    if not files:
        return JSONResponse(content={"ok": True, "latest": None})
    latest = files[-1]
    return JSONResponse(content={"ok": True, "latest": json.loads(latest.read_text(encoding="utf-8")), "file": str(latest)})


@app.post("/api/patterns/assessment/recovery/request")
async def request_assessment_recovery(payload: Dict[str, Any]):
    q_email = _normalize_email(payload.get("email"))
    # security posture: always return ok to avoid account enumeration
    if not q_email:
        return {"ok": True}

    code = f"{secrets.randbelow(1000000):06d}"
    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat().replace("+00:00", "Z")

    conn = _patterns_conn()
    try:
        conn.execute(
            "INSERT INTO assessment_recovery_codes (email, code, expires_at, used_at, created_at) VALUES (?, ?, ?, NULL, ?)",
            (q_email, code, expires_at, _now_z()),
        )
        conn.commit()
    finally:
        conn.close()

    _send_email_via_local_script(
        q_email,
        "Your CHANNELED Assessment Recovery Code",
        (
            "Use this one-time code to recover your assessment results:\n\n"
            f"Code: {code}\n"
            "Expires in 15 minutes.\n\n"
            "If you did not request this, you can ignore this email."
        ),
    )
    return {"ok": True}


@app.post("/api/patterns/assessment/recovery/verify")
async def verify_assessment_recovery(payload: Dict[str, Any]):
    q_email = _normalize_email(payload.get("email"))
    code = str(payload.get("code") or "").strip()
    if not q_email or not code:
        return JSONResponse(content={"ok": False, "error": "email_and_code_required"}, status_code=400)

    conn = _patterns_conn()
    try:
        row = conn.execute(
            """
            SELECT id, code, expires_at, used_at
            FROM assessment_recovery_codes
            WHERE lower(email)=lower(?)
            ORDER BY id DESC
            LIMIT 1
            """,
            (q_email,),
        ).fetchone()

        if not row:
            return JSONResponse(content={"ok": False, "error": "invalid_code"}, status_code=401)

        if row["used_at"]:
            return JSONResponse(content={"ok": False, "error": "code_already_used"}, status_code=401)

        exp = datetime.fromisoformat(str(row["expires_at"]).replace("Z", "+00:00"))
        if datetime.now(timezone.utc) > exp:
            return JSONResponse(content={"ok": False, "error": "code_expired"}, status_code=401)

        if str(row["code"] or "") != code:
            return JSONResponse(content={"ok": False, "error": "invalid_code"}, status_code=401)

        token = str(uuid4())
        token_exp = (datetime.now(timezone.utc) + timedelta(minutes=20)).isoformat().replace("+00:00", "Z")

        conn.execute("UPDATE assessment_recovery_codes SET used_at=? WHERE id=?", (_now_z(), row["id"]))
        conn.execute(
            "INSERT INTO assessment_recovery_tokens (token, email, expires_at, used_at, created_at) VALUES (?, ?, ?, NULL, ?)",
            (token, q_email, token_exp, _now_z()),
        )
        conn.commit()
    finally:
        conn.close()

    return {"ok": True, "recovery_token": token, "expires_at": token_exp}


@app.get("/api/patterns/assessment/load")
async def load_patterns_assessment(request: Request, email: str = Query(""), assessment_id: str = Query(""), recovery_token: str = Query("")):
    """Load persisted 24Q assessment record by assessment_id or email (latest match).

    If no email provided, attempts companion-session cookie + linked assessment_email.
    """
    q_email = str(email or "").strip().lower()
    q_assessment_id = str(assessment_id or "").strip()
    q_recovery_token = str(recovery_token or "").strip()

    companion_email = str(request.cookies.get("companion_session_email") or "").strip().lower()
    trusted_session = False
    if not q_email and companion_email:
        # Paid Companion email is authoritative for this flow.
        # Do not auto-switch to linked assessment_email.
        q_email = companion_email
        trusted_session = True

    if companion_email and q_email and companion_email == q_email:
        trusted_session = True

    token_valid_for_email = False
    if q_email and q_recovery_token:
        conn = _patterns_conn()
        try:
            trow = conn.execute(
                "SELECT token, email, expires_at, used_at FROM assessment_recovery_tokens WHERE token=? LIMIT 1",
                (q_recovery_token,),
            ).fetchone()
            if trow and not trow["used_at"] and _normalize_email(trow["email"]) == q_email:
                exp = datetime.fromisoformat(str(trow["expires_at"]).replace("Z", "+00:00"))
                token_valid_for_email = datetime.now(timezone.utc) <= exp
        finally:
            conn.close()

    if q_email and (not trusted_session) and (not token_valid_for_email) and (not q_assessment_id):
        return JSONResponse(content={"ok": False, "error": "recovery_verification_required"}, status_code=401)

    # Preferred source: SQLite assessments table (authoritative for current app state)
    db_match = None
    conn = _patterns_conn()
    try:
        if q_assessment_id:
            db_match = conn.execute(
                "SELECT * FROM assessments WHERE id = ? ORDER BY COALESCE(updated_at, created_at) DESC LIMIT 1",
                (q_assessment_id,),
            ).fetchone()
        elif q_email and (trusted_session or token_valid_for_email):
            db_match = conn.execute(
                "SELECT * FROM assessments WHERE lower(email)=lower(?) ORDER BY COALESCE(is_primary,0) DESC, COALESCE(updated_at, created_at) DESC LIMIT 1",
                (q_email,),
            ).fetchone()
    finally:
        conn.close()

    if db_match:
        if q_email and token_valid_for_email and q_recovery_token:
            conn = _patterns_conn()
            try:
                conn.execute("UPDATE assessment_recovery_tokens SET used_at=? WHERE token=?", (_now_z(), q_recovery_token))
                conn.commit()
            finally:
                conn.close()

        row = dict(db_match)
        parsed_payload = {}
        try:
            parsed_payload = json.loads(str(row.get("raw_payload_json") or "{}"))
        except Exception:
            parsed_payload = {}

        # Normalize DB-backed record to shape expected by frontend.
        # Support both legacy v1 payloads and 24Q CHANNELED payloads.
        payload_results = parsed_payload.get("results") if isinstance(parsed_payload.get("results"), dict) else {}
        assembled_results = parsed_payload.get("assembled_results") if isinstance(parsed_payload.get("assembled_results"), dict) else {}

        if payload_results:
            # 24Q/native path
            primary = str(
                row.get("primary_archetype")
                or payload_results.get("primary")
                or assembled_results.get("primary")
                or ""
            ).strip()
            secondary = str(
                row.get("secondary_archetype")
                or payload_results.get("secondary")
                or assembled_results.get("secondary")
                or ""
            ).strip()
            normalized_scores = payload_results.get("scores") if isinstance(payload_results.get("scores"), dict) else {}
            dimension_scores = payload_results.get("dimensionScores") if isinstance(payload_results.get("dimensionScores"), dict) else {}
            normalized_raw_answers = parsed_payload.get("raw_answers") if isinstance(parsed_payload.get("raw_answers"), dict) else {}
        else:
            # Legacy v1 fallback path
            primary = str(row.get("primary_archetype") or parsed_payload.get("reveal_archetypes", {}).get("primary") or "").strip()
            secondary = str(row.get("secondary_archetype") or parsed_payload.get("reveal_archetypes", {}).get("secondary") or "").strip()
            v1_payload = parsed_payload.get("v1") if isinstance(parsed_payload.get("v1"), dict) else {}
            normalized_scores = v1_payload.get("normalized") if isinstance(v1_payload.get("normalized"), dict) else {}
            by_dimension = v1_payload.get("by_dimension") if isinstance(v1_payload.get("by_dimension"), dict) else {}
            dimension_scores = {}
            for dk, dv in by_dimension.items():
                if isinstance(dv, dict) and ("score" in dv):
                    try:
                        dimension_scores[dk] = float(dv.get("score") or 0)
                    except Exception:
                        pass
            normalized_raw_answers = parsed_payload.get("raw_answers") if isinstance(parsed_payload.get("raw_answers"), dict) else {}

        normalized_results = {
            "primary": primary,
            "secondary": secondary,
            "scores": normalized_scores,
            "dimensionScores": dimension_scores,
        }
        normalized_record = {
            "assessment_id": row.get("id"),
            "email": row.get("email"),
            "saved_at": row.get("updated_at") or row.get("created_at"),
            "payload": {
                "assessment_id": row.get("id"),
                "email": row.get("email"),
                "results": normalized_results,
                "raw_answers": normalized_raw_answers,
                "assembled_results": assembled_results,
            },
        }

        return JSONResponse(content={
            "ok": True,
            "found": True,
            "record": normalized_record,
            "results": normalized_results,
            "raw_answers": normalized_raw_answers,
            "source": "sqlite:assessments",
        })

    # Legacy fallback: filesystem assessment JSONs
    files = sorted(assessments_dir.glob("assessment_*.json"), reverse=True)
    for f in files:
        try:
            record = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue

        rid = str(record.get("assessment_id") or record.get("payload", {}).get("assessment_id") or "").strip()
        remail = str(record.get("email") or record.get("payload", {}).get("email") or "").strip().lower()

        id_match = bool(q_assessment_id and rid and rid == q_assessment_id)
        email_match = bool(q_email and remail and remail == q_email)
        allowed_email_match = bool(email_match and (trusted_session or token_valid_for_email))

        if id_match or allowed_email_match:
            if allowed_email_match and token_valid_for_email and q_recovery_token:
                conn = _patterns_conn()
                try:
                    conn.execute("UPDATE assessment_recovery_tokens SET used_at=? WHERE token=?", (_now_z(), q_recovery_token))
                    conn.commit()
                finally:
                    conn.close()
            payload = record.get("payload") if isinstance(record.get("payload"), dict) else {}
            return JSONResponse(content={
                "ok": True,
                "found": True,
                "record": record,
                "results": payload.get("results") if isinstance(payload.get("results"), dict) else payload,
                "raw_answers": payload.get("raw_answers") if isinstance(payload.get("raw_answers"), dict) else {},
                "file": str(f),
                "source": "filesystem:assessment_json",
            })

    return JSONResponse(content={"ok": True, "found": False, "record": None})

def _infer_profile_key(payload: dict) -> str:
    """Infer archetype profile key from assessment payload dimension scores."""
    dims = payload.get("dimensionScores") or payload.get("dimension_scores") or []
    if not dims:
        return "system_architect"

    # Backward/forward compatibility:
    # - legacy shape: [{"id":"C1","score":0.8}, ...]
    # - 24Q shape: {"processing_style":1.0, ...}
    if isinstance(dims, dict):
        dims = [{"id": str(k), "score": float(v)} for k, v in dims.items()]
    elif isinstance(dims, list):
        dims = [d for d in dims if isinstance(d, dict)]
    else:
        return "system_architect"

    if not dims:
        return "system_architect"

    sorted_dims = sorted(dims, key=lambda d: d.get("score", 0), reverse=True)
    top_id = (sorted_dims[0].get("id", "")).replace("1", "").replace("2", "")
    mapping = {
        "L": "multiplier",
        "E": "purpose_driver",
        "D": "self_aware_architect",
        "C": "system_architect",
        "H": "deep_diver",
        "N": "connected_catalyst",
        "A": "system_architect",
    }
    # N2 (Normalize/Reframe) check
    if sorted_dims[0].get("id", "") == "N2":
        return "resilient_reframer"
    # E1 (Exercise/Energy) check
    if sorted_dims[0].get("id", "") == "E1":
        return "energized_executor"
    return mapping.get(top_id, "system_architect")


# ============== PROFILE PAGES ==============

PROFILE_PAGES = {
    "system_architect": "profiles/profile_system_architect.html",
    "deep_diver": "profiles/profile_deep_diver.html",
    "connected_catalyst": "profiles/profile_connected_catalyst.html",
    "resilient_reframer": "profiles/profile_resilient_reframer.html",
    "energized_executor": "profiles/profile_energized_executor.html",
    "multiplier": "profiles/profile_multiplier.html",
    "purpose_driver": "profiles/profile_purpose_driver.html",
    "self_aware_architect": "profiles/profile_self_aware_architect.html",
}

@app.get("/profiles/{profile_key}", response_class=HTMLResponse)
async def profile_page(profile_key: str):
    """Serve archetype profile pages"""
    template_file = PROFILE_PAGES.get(profile_key)
    if not template_file:
        return HTMLResponse(content="<h1>Profile not found</h1>", status_code=404)
    template_path = templates_dir / template_file
    if template_path.exists():
        return HTMLResponse(content=template_path.read_text(encoding="utf-8"))
    return HTMLResponse(content="<h1>Profile template not found</h1>", status_code=404)


@app.get("/patterns_paradigm_premium.html", response_class=HTMLResponse)
async def patterns_paradigm_premium(request: Request):
    """Premium tier placeholder page"""
    template_path = templates_dir / "patterns_paradigm_premium.html"
    if template_path.exists():
        return HTMLResponse(content=template_path.read_text(encoding="utf-8"))
    return HTMLResponse(content="<h1>Premium page not found</h1>", status_code=404)


@app.get("/patterns_assessment_admin.html", response_class=HTMLResponse)
async def patterns_assessment_admin(request: Request):
    """Admin page: full assessment history with table, detail, and CSV export"""
    template_path = templates_dir / "patterns_assessment_admin.html"
    if template_path.exists():
        return HTMLResponse(content=template_path.read_text(encoding="utf-8"))
    return HTMLResponse(content="<h1>Admin page not found</h1>", status_code=404)


# ============== NEW ASSESSMENT API ENDPOINTS ==============

@app.get("/api/patterns/assessments")
async def list_assessments():
    """List all saved assessments, most recent first"""
    files = sorted(assessments_dir.glob("assessment_*.json"), reverse=True)
    assessments = []
    for f in files:
        try:
            record = json.loads(f.read_text(encoding="utf-8"))
            payload = record.get("payload", {})
            # Enrich with profile key if not already present
            if "profileKey" not in payload and "profile_key" not in payload:
                payload["profileKey"] = _infer_profile_key(payload)
                record["payload"] = payload
            assessments.append({
                "file": f.name,
                "saved_at": record.get("saved_at", ""),
                "payload": payload,
            })
        except Exception:
            continue
    return JSONResponse(content={"ok": True, "count": len(assessments), "assessments": assessments})


@app.get("/api/patterns/assessments/export")
async def export_assessments_csv():
    """Export all assessments as CSV"""
    import csv
    import io
    files = sorted(assessments_dir.glob("assessment_*.json"), reverse=True)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Date", "Profile Key", "Profile Name", "Overall Score", "Tier",
        "Strongest Dimension", "Strongest Score", "Weakest Dimension", "Weakest Score",
        "Dimension Scores", "Recommendations Count", "File"
    ])
    for f in files:
        try:
            record = json.loads(f.read_text(encoding="utf-8"))
            payload = record.get("payload", {})
            profile_key = payload.get("profileKey") or payload.get("profile_key") or _infer_profile_key(payload)
            profile_names = {
                "system_architect": "The System Architect",
                "deep_diver": "The Deep Diver",
                "connected_catalyst": "The Connected Catalyst",
                "resilient_reframer": "The Resilient Reframer",
                "energized_executor": "The Energized Executor",
                "multiplier": "The Multiplier",
                "purpose_driver": "The Purpose Driver",
                "self_aware_architect": "The Self-Aware Architect",
            }
            dims = payload.get("dimensionScores") or payload.get("dimension_scores") or []
            dim_str = "; ".join(f"{d.get('name', d.get('id', '?'))}: {d.get('score', 0):.1f}" for d in dims)
            recs = payload.get("recommendations", [])
            strongest = payload.get("strongest", {})
            weakest = payload.get("weakest", {})
            writer.writerow([
                record.get("saved_at", ""),
                profile_key,
                profile_names.get(profile_key, profile_key),
                payload.get("overallScore") or payload.get("overall_score", ""),
                payload.get("tier", ""),
                strongest.get("name", ""),
                strongest.get("score", ""),
                weakest.get("name", ""),
                weakest.get("score", ""),
                dim_str,
                len(recs),
                f.name,
            ])
        except Exception:
            continue
    from fastapi.responses import Response
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=assessments_export.csv"},
    )


# Keep existing endpoints working (override to include profile key)
@app.post("/api/patterns/assessment/save")
async def save_patterns_assessment(request: Request, payload: Dict[str, Any]):
    """Persist CHANNELED 24Q submission.

    Writes both filesystem snapshot (backward compatibility) and SQLite assessments row
    (authoritative load path for login/reload flows).
    """
    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    saved_at = datetime.utcnow().isoformat() + "Z"

    # Enrich payload with profile key
    profile_key = _infer_profile_key(payload)
    payload["profileKey"] = profile_key
    payload["profileUrl"] = f"/profiles/{profile_key}"

    # Resolve identity/email with backend fallback from trusted session cookie.
    email_raw = str(payload.get("email") or "").strip().lower()
    if not email_raw:
        cookie_email = str(request.cookies.get("companion_session_email") or "").strip().lower()
        if cookie_email:
            email_raw = cookie_email

    assessment_id = str(payload.get("assessment_id") or payload.get("assessmentId") or uuid4())
    payload["assessment_id"] = assessment_id
    if email_raw:
        payload["email"] = email_raw

    user_key = f"email:{email_raw}" if email_raw else f"assessment:{assessment_id}"

    # Keep JSON snapshot for backward compatibility / audit trail.
    record = {
        "saved_at": saved_at,
        "assessment_id": assessment_id,
        "user_key": user_key,
        "email": email_raw or None,
        "payload": payload,
    }
    safe_email = ""
    if email_raw:
        safe_email = "_" + "".join(c if c.isalnum() else "_" for c in email_raw)[:120]
    out_path = assessments_dir / f"assessment_{ts}{safe_email}.json"
    out_path.write_text(json.dumps(record, indent=2), encoding="utf-8")

    # Dual-write to DB so results load remains consistent after login/magic link.
    primary = str((payload.get("results") or {}).get("primary") or "").strip() or None
    secondary = str((payload.get("results") or {}).get("secondary") or "").strip() or None
    source_version = str(payload.get("version") or "channeled_24q_v1").strip() or "channeled_24q_v1"
    context = str(payload.get("source") or "channeled_assessment_24_questions").strip() or None

    conn = _patterns_conn()
    try:
        conn.execute(
            """
            INSERT INTO assessments (
                id, created_at, updated_at, email, name,
                primary_archetype, secondary_archetype, archetype_pair_label,
                context, source_version, confirmed_primary,
                raw_payload_json, loops_status, loops_contact_id, last_error, retry_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                updated_at=excluded.updated_at,
                email=COALESCE(excluded.email, assessments.email),
                primary_archetype=COALESCE(excluded.primary_archetype, assessments.primary_archetype),
                secondary_archetype=COALESCE(excluded.secondary_archetype, assessments.secondary_archetype),
                context=COALESCE(excluded.context, assessments.context),
                source_version=COALESCE(excluded.source_version, assessments.source_version),
                raw_payload_json=excluded.raw_payload_json
            """,
            (
                assessment_id,
                saved_at,
                saved_at,
                email_raw or None,
                None,
                primary,
                secondary,
                None,
                context,
                source_version,
                None,
                json.dumps(payload),
                "n/a",
                None,
                None,
                None,
            ),
        )

        # Keep purchase/login email linked to assessment email when available.
        if email_raw:
            conn.execute(
                "UPDATE companion_access SET assessment_email=?, updated_at=? WHERE lower(email)=lower(?)",
                (email_raw, saved_at, email_raw),
            )

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return JSONResponse(content={
        "ok": True,
        "file": str(out_path),
        "profileKey": profile_key,
        "profileUrl": f"/profiles/{profile_key}",
        "assessment_id": assessment_id,
        "user_key": user_key,
        "email": email_raw or None,
        "source": "dual_write:file+sqlite",
    })


@app.post("/api/patterns/quick-signal/save")
async def save_quick_signal_assessment(payload: Dict[str, Any]):
    """Persist 8Q quick-signal submission, store structured DB record, and sync to Loops."""
    saved_at = _now_z()
    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")

    email = (payload.get("email") or "").strip().lower()
    if not email:
        return JSONResponse(content={"ok": False, "error": "email_required"}, status_code=400)

    name = (payload.get("name") or "").strip() or None
    context = (payload.get("context") or "").strip() or None
    source_version = (payload.get("version") or "").strip() or None

    resolved = resolve_archetypes(payload)
    primary = resolved.get("primary_archetype")
    secondary = resolved.get("secondary_archetype")
    archetype_pair_label = resolved.get("archetype_pair_label")
    confirmed_primary = resolved.get("confirmed_primary")
    resolution_error = resolved.get("error")

    assessment_id = str(uuid4())
    loops_status = "pending"
    last_error = None
    retry_at = None
    loops_contact_id = None

    if resolution_error:
        loops_status = "skipped"
        last_error = resolution_error

    # Always retain JSON snapshot for backward compatibility
    safe_email = "".join(c if c.isalnum() else "_" for c in email)[:120]
    out_path = quick_signal_assessments_dir / f"quick_signal_{ts}_{safe_email}.json"
    record = {
        "saved_at": saved_at,
        "email": email,
        "assessment_id": assessment_id,
        "payload": payload,
    }
    out_path.write_text(json.dumps(record, indent=2), encoding="utf-8")

    # DB source-of-truth write first (never lose submission)
    conn = _patterns_conn()
    try:
        conn.execute(
            """
            INSERT INTO assessments (
                id, created_at, updated_at, email, name,
                primary_archetype, secondary_archetype, archetype_pair_label,
                context, source_version, confirmed_primary,
                raw_payload_json, loops_status, loops_contact_id, last_error, retry_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                assessment_id,
                saved_at,
                saved_at,
                email,
                name,
                primary,
                secondary,
                archetype_pair_label,
                context,
                source_version,
                confirmed_primary,
                json.dumps(payload),
                loops_status,
                loops_contact_id,
                last_error,
                retry_at,
            ),
        )
        add_assessment_event(conn, assessment_id, "created", {
            "loops_status": loops_status,
            "primary_archetype": primary,
            "secondary_archetype": secondary,
            "resolution_error": resolution_error,
        })

        # If archetype cannot be resolved, skip Loops but keep durable record
        if loops_status == "skipped":
            conn.commit()
            return JSONResponse(content={
                "ok": True,
                "assessment_id": assessment_id,
                "file": str(out_path),
                "saved_at": saved_at,
                "email": email,
                "primary_archetype": primary,
                "secondary_archetype": secondary,
                "loops_status": "skipped",
                "last_error": "archetype_resolution_failed",
            })

        add_assessment_event(conn, assessment_id, "loops_attempt", {"attempt": 1})
        loops_result = loops_upsert_and_trigger(
            email=email,
            name=name,
            primary_archetype=primary,
            secondary_archetype=secondary,
            context=context,
            source_version=source_version,
            assessment_id=assessment_id,
            confirmed_primary=confirmed_primary,
            archetype_pair_label=archetype_pair_label,
            assessment_completed_at=saved_at,
        )

        if loops_result.get("ok"):
            loops_status = "sent"
            loops_contact_id = loops_result.get("contact_id")
            last_error = None
            retry_at = None
            add_assessment_event(conn, assessment_id, "loops_sent", {
                "contact_id": loops_contact_id,
            })
        else:
            loops_status = "failed"
            loops_contact_id = loops_result.get("contact_id")
            last_error = loops_result.get("error") or "loops_send_failed"
            attempts = _failed_attempt_count(conn, assessment_id) + 1
            retry_at = compute_retry_at(attempts) if loops_result.get("retryable", True) else None
            add_assessment_event(conn, assessment_id, "loops_failed", {
                "error": last_error,
                "contact_id": loops_contact_id,
                "retryable": loops_result.get("retryable", True),
            })
            if retry_at:
                add_assessment_event(conn, assessment_id, "retry_scheduled", {"retry_at": retry_at})

        conn.execute(
            """
            UPDATE assessments
               SET updated_at = ?, loops_status = ?, loops_contact_id = ?, last_error = ?, retry_at = ?
             WHERE id = ?
            """,
            (_now_z(), loops_status, loops_contact_id, last_error, retry_at, assessment_id),
        )
        conn.commit()

    finally:
        conn.close()

    return JSONResponse(content={
        "ok": True,
        "assessment_id": assessment_id,
        "file": str(out_path),
        "saved_at": saved_at,
        "email": email,
        "primary_archetype": primary,
        "secondary_archetype": secondary,
        "loops_status": loops_status,
        "loops_contact_id": loops_contact_id,
        "last_error": last_error,
        "retry_at": retry_at,
    })


def _normalize_email(value: Optional[str]) -> str:
    return (value or "").strip().lower()


def _quick_signal_latest_for_email(email: str) -> Optional[Dict[str, Any]]:
    q = _normalize_email(email)
    if not q:
        return None

    files = sorted(quick_signal_assessments_dir.glob("quick_signal_*.json"), reverse=True)
    for f in files:
        try:
            record = json.loads(f.read_text(encoding="utf-8"))
            rec_email = _normalize_email(record.get("email") or record.get("payload", {}).get("email"))
            if rec_email != q:
                continue
            return {
                "file": f.name,
                "saved_at": record.get("saved_at", ""),
                "email": rec_email,
                "payload": record.get("payload", {}),
            }
        except Exception:
            continue
    return None


def _latest_linked_free_email_for_paid_email(paid_email: str) -> Optional[str]:
    if not quick_signal_link_file.exists():
        return None

    q = _normalize_email(paid_email)
    if not q:
        return None

    latest_ts = ""
    latest_free = None
    try:
        for line in quick_signal_link_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if _normalize_email(rec.get("paid_email")) != q:
                continue
            ts = str(rec.get("linked_at") or "")
            if ts >= latest_ts:
                latest_ts = ts
                latest_free = _normalize_email(rec.get("free_8q_email"))
    except Exception:
        return None

    return latest_free or None


def _ct_today_str() -> str:
    return datetime.now(timezone.utc).astimezone(ZoneInfo(COMPANION_CT_TZ)).date().isoformat()


def _send_email_via_local_script(to_email: str, subject: str, body: str) -> bool:
    cmd = [
        "python3",
        str(Path(__file__).resolve().parent.parent / "send_email.py"),
        "--to", to_email,
        "--subject", subject,
        "--body", body,
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=25)
        if r.returncode != 0:
            print(f"[send-email] failed rc={r.returncode} stderr={r.stderr[:300]}")
            return False
        return True
    except Exception as e:
        print(f"[send-email] exception: {e}")
        return False


def _send_matt_critical_alert(subject: str, body: str) -> bool:
    to_email = os.getenv("MATT_ALERT_EMAIL", "mattolejarczyk70@gmail.com").strip()
    return _send_email_via_local_script(to_email, subject, body)


def _companion_alert_once_per_day(email: str, alert_key: str, details: Dict[str, Any]) -> bool:
    """Returns True when alert should be sent (and logs reservation), False if already sent today."""
    today_ct = _ct_today_str()
    conn = _patterns_conn()
    try:
        try:
            conn.execute(
                "INSERT INTO companion_alert_log (email, alert_key, alert_date_ct, details_json, created_at) VALUES (?, ?, ?, ?, ?)",
                (_normalize_email(email), str(alert_key), today_ct, json.dumps(details or {}), _now_z()),
            )
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False
    finally:
        conn.close()


def _is_test_email(email: Optional[str]) -> bool:
    e = _normalize_email(email)
    if not e:
        return False
    return e.endswith("@example.com") or ".test@" in e or e.startswith("test+")


def _companion_raise_24q_foundation_alert(email: str, route: str, resolved: Dict[str, Any]):
    # Never alert Matt for synthetic test identities.
    if _is_test_email(email):
        return

    source = str((resolved or {}).get("source") or "unknown")
    details = {
        "route": route,
        "resolver_source": source,
        "resolver_source_email": (resolved or {}).get("source_email"),
        "assessment_email": (resolved or {}).get("assessment_email"),
    }
    alert_key = f"24q-foundation-missing:{route}"
    should_send = _companion_alert_once_per_day(email, alert_key, details)
    if not should_send:
        return

    subject = f"[CRITICAL] Companion 24Q foundation missing for {email}"
    body = (
        "Critical Companion policy alert:\n\n"
        f"Email: {email}\n"
        f"Route: {route}\n"
        f"Resolver source used: {source}\n"
        f"Resolver source email: {details.get('resolver_source_email') or 'n/a'}\n"
        f"Linked assessment_email: {details.get('assessment_email') or 'n/a'}\n\n"
        "Policy: Weekly plans/content must be grounded in 24Q CHANNELED assessment data.\n"
        "Action needed: investigate identity link or missing 24Q assessment for this paid user."
    )
    _send_matt_critical_alert(subject, body)


def _companion_set_8q_state(email: str, status: str, free_8q_email: Optional[str] = None,
                            linked_at: Optional[str] = None, last_prompt_date_ct: Optional[str] = None):
    conn = _patterns_conn()
    try:
        conn.execute(
            """
            INSERT INTO companion_8q_link_state (email, status, free_8q_email, linked_at, last_prompt_date_ct, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(email) DO UPDATE SET
              status=excluded.status,
              free_8q_email=COALESCE(excluded.free_8q_email, companion_8q_link_state.free_8q_email),
              linked_at=COALESCE(excluded.linked_at, companion_8q_link_state.linked_at),
              last_prompt_date_ct=COALESCE(excluded.last_prompt_date_ct, companion_8q_link_state.last_prompt_date_ct),
              updated_at=excluded.updated_at
            """,
            (_normalize_email(email), status, _normalize_email(free_8q_email) or None, linked_at, last_prompt_date_ct, _now_z()),
        )
        conn.commit()
    finally:
        conn.close()


def _ensure_companion_8q_schema():
    conn = _patterns_conn()
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(companion_8q_link_state)").fetchall()}
        if "next_prompt_date_ct" not in cols:
            conn.execute("ALTER TABLE companion_8q_link_state ADD COLUMN next_prompt_date_ct TEXT")
            conn.commit()
    finally:
        conn.close()


def _companion_get_8q_state(email: str) -> Optional[sqlite3.Row]:
    conn = _patterns_conn()
    try:
        return conn.execute("SELECT * FROM companion_8q_link_state WHERE lower(email)=lower(?) LIMIT 1", (_normalize_email(email),)).fetchone()
    finally:
        conn.close()


def _promote_8q_to_paid_canonical(paid_email: str, source_8q_email: str, linked_at: Optional[str] = None) -> Dict[str, Any]:
    paid = _normalize_email(paid_email)
    source = _normalize_email(source_8q_email)
    if not paid or not source:
        return {"ok": False, "error": "paid_email_and_source_8q_email_required"}

    latest = _quick_signal_latest_for_email(source)
    if not latest:
        return {"ok": False, "error": "source_8q_not_found"}

    promoted_at = _now_z()
    person_key = f"email:{paid}"

    conn = _patterns_conn()
    try:
        conn.execute(
            """
            INSERT INTO paid_canonical_8q (
                paid_email, person_key, source_8q_email, source_8q_file, source_8q_saved_at,
                linked_at, promoted_at, quick_signal_payload_json, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(paid_email) DO UPDATE SET
                person_key=excluded.person_key,
                source_8q_email=excluded.source_8q_email,
                source_8q_file=excluded.source_8q_file,
                source_8q_saved_at=excluded.source_8q_saved_at,
                linked_at=excluded.linked_at,
                promoted_at=excluded.promoted_at,
                quick_signal_payload_json=excluded.quick_signal_payload_json,
                updated_at=excluded.updated_at
            """,
            (
                paid,
                person_key,
                source,
                latest.get("file"),
                latest.get("saved_at"),
                linked_at,
                promoted_at,
                json.dumps(latest.get("payload") or {}),
                promoted_at,
            ),
        )

        conn.execute(
            """
            INSERT INTO paid_canonical_8q_history (
                paid_email, source_8q_email, source_8q_file, source_8q_saved_at, linked_at, promoted_at, quick_signal_payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                paid,
                source,
                latest.get("file"),
                latest.get("saved_at"),
                linked_at,
                promoted_at,
                json.dumps(latest.get("payload") or {}),
            ),
        )
        conn.commit()
    finally:
        conn.close()

    return {
        "ok": True,
        "paid_email": paid,
        "source_8q_email": source,
        "promoted_at": promoted_at,
        "source_8q_file": latest.get("file"),
        "source_8q_saved_at": latest.get("saved_at"),
    }


@app.get("/api/patterns/quick-signal/by-email")
async def quick_signal_by_email(email: str = Query(...), limit: int = Query(5, ge=1, le=100)):
    """Recall quick-signal submissions by email (latest first)."""
    q = (email or "").strip().lower()
    files = sorted(quick_signal_assessments_dir.glob("quick_signal_*.json"), reverse=True)
    matches = []
    for f in files:
        try:
            record = json.loads(f.read_text(encoding="utf-8"))
            if (record.get("email") or "").strip().lower() != q:
                continue
            matches.append({
                "file": f.name,
                "saved_at": record.get("saved_at", ""),
                "email": record.get("email", ""),
                "payload": record.get("payload", {}),
            })
            if len(matches) >= limit:
                break
        except Exception:
            continue
    return JSONResponse(content={"ok": True, "email": q, "count": len(matches), "assessments": matches})


@app.post("/api/patterns/quick-signal/link")
async def link_quick_signal_identity(payload: Dict[str, Any]):
    """Link paid email to a (potentially different) free 8Q email for profile unification."""
    paid_email = _normalize_email(payload.get("paid_email") or payload.get("email"))
    free_email = _normalize_email(payload.get("free_8q_email") or payload.get("quick_signal_email"))

    if not paid_email or not free_email:
        return JSONResponse(content={"ok": False, "error": "paid_email_and_free_8q_email_required"}, status_code=400)

    rec = {
        "linked_at": _now_z(),
        "paid_email": paid_email,
        "free_8q_email": free_email,
        "source": payload.get("source") or "manual",
    }

    with quick_signal_link_file.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")

    free_latest = _quick_signal_latest_for_email(free_email)
    promotion = _promote_8q_to_paid_canonical(paid_email, free_email, linked_at=rec["linked_at"]) if free_latest else {"ok": False, "error": "source_8q_not_found"}

    return JSONResponse(content={
        "ok": True,
        "paid_email": paid_email,
        "free_8q_email": free_email,
        "linked_at": rec["linked_at"],
        "free_8q_found": bool(free_latest),
        "free_8q_latest": free_latest,
        "promotion": promotion,
    })


@app.get("/api/patterns/quick-signal/purge/report")
async def quick_signal_purge_report(older_than_days: int = Query(30, ge=1, le=3650)):
    """Dry-run report for purge safety: never purge linked-but-not-promoted 8Q records."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=int(older_than_days))

    promoted_sources = set()
    conn = _patterns_conn()
    try:
        for r in conn.execute("SELECT DISTINCT lower(source_8q_email) AS e FROM paid_canonical_8q WHERE source_8q_email IS NOT NULL"):
            if r[0]:
                promoted_sources.add(str(r[0]).strip().lower())
    finally:
        conn.close()

    linked_sources = set()
    if quick_signal_link_file.exists():
        try:
            for line in quick_signal_link_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                e = _normalize_email(rec.get("free_8q_email"))
                if e:
                    linked_sources.add(e)
        except Exception:
            pass

    files = sorted(quick_signal_assessments_dir.glob("quick_signal_*.json"))
    scanned = 0
    candidates = 0
    purgeable = 0
    blocked_linked_not_promoted = 0
    rows = []

    for f in files:
        scanned += 1
        try:
            rec = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue

        saved_at = str(rec.get("saved_at") or "")
        email = _normalize_email(rec.get("email") or rec.get("payload", {}).get("email"))
        if not saved_at:
            continue
        try:
            dt = datetime.fromisoformat(saved_at.replace("Z", "+00:00"))
        except Exception:
            continue

        if dt > cutoff:
            continue

        candidates += 1
        is_linked = email in linked_sources if email else False
        is_promoted = email in promoted_sources if email else False

        blocked = bool(is_linked and not is_promoted)
        if blocked:
            blocked_linked_not_promoted += 1
        else:
            purgeable += 1

        rows.append({
            "file": f.name,
            "email": email or None,
            "saved_at": saved_at,
            "linked": is_linked,
            "promoted": is_promoted,
            "blocked_reason": "linked_not_promoted" if blocked else None,
            "purgeable": not blocked,
        })

    return {
        "ok": True,
        "summary": {
            "older_than_days": older_than_days,
            "scanned": scanned,
            "candidates": candidates,
            "purgeable": purgeable,
            "blocked_linked_not_promoted": blocked_linked_not_promoted,
        },
        "rows": rows,
    }


@app.post("/api/patterns/quick-signal/purge")
async def quick_signal_purge(older_than_days: int = Query(30, ge=1, le=3650), dry_run: bool = Query(True)):
    report = await quick_signal_purge_report(older_than_days=older_than_days)
    if dry_run:
        return {"ok": True, "dry_run": True, **report}

    deleted = []
    errors = []
    for row in report.get("rows", []):
        if not row.get("purgeable"):
            continue
        fp = quick_signal_assessments_dir / str(row.get("file") or "")
        try:
            if fp.exists():
                fp.unlink()
                deleted.append(fp.name)
        except Exception as e:
            errors.append({"file": fp.name, "error": str(e)})

    return {
        "ok": True,
        "dry_run": False,
        "summary": {
            **report.get("summary", {}),
            "deleted": len(deleted),
            "errors": len(errors),
        },
        "deleted_files": deleted,
        "errors": errors,
    }


@app.get("/api/patterns/person/8q-context")
async def get_person_8q_context(paid_email: str = Query(...), free_8q_email: Optional[str] = Query(None)):
    """Resolve which 8Q run to attach to a paid profile and whether follow-up prompt is needed."""
    paid = _normalize_email(paid_email)
    if not paid:
        return JSONResponse(content={"ok": False, "error": "paid_email_required"}, status_code=400)

    # 1) direct match on paid email
    direct = _quick_signal_latest_for_email(paid)
    if direct:
        return JSONResponse(content={
            "ok": True,
            "paid_email": paid,
            "matched": True,
            "matched_by": "paid_email",
            "needs_followup": False,
            "quick_signal": direct,
        })

    # 2) explicit free-email from UI follow-up
    explicit_free = _normalize_email(free_8q_email)
    if explicit_free:
        free_match = _quick_signal_latest_for_email(explicit_free)
        if free_match:
            return JSONResponse(content={
                "ok": True,
                "paid_email": paid,
                "matched": True,
                "matched_by": "provided_free_8q_email",
                "needs_followup": False,
                "quick_signal": free_match,
                "proposed_link": {"paid_email": paid, "free_8q_email": explicit_free},
            })

    # 3) persisted link table fallback
    linked_free = _latest_linked_free_email_for_paid_email(paid)
    if linked_free:
        linked_match = _quick_signal_latest_for_email(linked_free)
        if linked_match:
            return JSONResponse(content={
                "ok": True,
                "paid_email": paid,
                "matched": True,
                "matched_by": "linked_free_8q_email",
                "needs_followup": False,
                "linked_free_8q_email": linked_free,
                "quick_signal": linked_match,
            })

    # 4) no match yet -> trigger your follow-up question in product
    return JSONResponse(content={
        "ok": True,
        "paid_email": paid,
        "matched": False,
        "needs_followup": True,
        "followup_question": "Did you take the free 8Q assessment? If yes, what email did you use?",
    })


# ============== NEW API ENDPOINTS ==============

@app.get("/api/status")
async def api_status():
    """Return server status"""
    return JSONResponse(content={
        "status": "online",
        "timestamp": datetime.now().isoformat(),
        "version": "1.0"
    })

@app.get("/api/agent-models")
async def api_agent_models():
    """Return live sub-agent model mapping from OpenClaw config"""
    config_path = Path(__file__).resolve().parents[2] / "openclaw.json"

    if not config_path.exists():
        return JSONResponse(
            content={"error": "openclaw.json not found", "agentModels": {}},
            status_code=404,
            headers={
                "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
                "Pragma": "no-cache",
                "Expires": "0",
            },
        )

    try:
        cfg = json.loads(config_path.read_text())
        agents = cfg.get("agents", {}).get("list", [])
        agent_models = {}

        for agent in agents:
            agent_id = agent.get("id")
            if not agent_id or agent_id == "main":
                continue
            model = (agent.get("subagents") or {}).get("model")
            if model:
                agent_models[agent_id] = model

        return JSONResponse(
            content={
                "updatedAt": datetime.now().isoformat(),
                "agentModels": agent_models,
            },
            headers={
                "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
                "Pragma": "no-cache",
                "Expires": "0",
            },
        )
    except Exception as e:
        return JSONResponse(
            content={"error": str(e), "agentModels": {}},
            status_code=500,
            headers={
                "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
                "Pragma": "no-cache",
                "Expires": "0",
            },
        )

# ========== Simple Rate Limiter for /api/* ==========
_rate_limit_store: Dict[str, list] = {}
RATE_LIMIT_WINDOW = 60  # seconds
RATE_LIMIT_MAX_REQUESTS = 30

def _check_rate_limit(ip: str) -> bool:
    """Returns True if request is allowed, False if rate limited."""
    now = time.time()
    if ip not in _rate_limit_store:
        _rate_limit_store[ip] = []
    _rate_limit_store[ip] = [t for t in _rate_limit_store[ip] if now - t < RATE_LIMIT_WINDOW]
    if len(_rate_limit_store[ip]) >= RATE_LIMIT_MAX_REQUESTS:
        return False
    _rate_limit_store[ip].append(now)
    return True

# ========== Live Agents API ==========
@app.get("/api/agents")
async def api_agents(request: Request):
    """Return live agent data from OpenClaw config — non-sensitive fields only."""
    client_ip = request.client.host if request.client else "unknown"
    api_access_log.info(f"/api/agents called from {client_ip} at {datetime.now().isoformat()}")

    if not _check_rate_limit(client_ip):
        return JSONResponse(
            content={"agents": [], "error": "rate_limited"},
            status_code=429,
            headers={
                "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
                "Retry-After": "60",
            },
        )

    config_path = Path(__file__).resolve().parents[2] / "openclaw.json"

    if not config_path.exists():
        return JSONResponse(
            content={"agents": [], "updatedAt": datetime.now().isoformat()},
            status_code=200,
            headers={
                "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
                "Pragma": "no-cache",
                "Expires": "0",
            },
        )

    try:
        cfg = json.loads(config_path.read_text())
        agents = cfg.get("agents", {}).get("list", [])

        result = []
        for agent in agents:
            agent_id = agent.get("id")
            if not agent_id or agent_id == "main":
                continue

            model = agent.get("model", "")
            if not model:
                default_model = cfg.get("agents", {}).get("defaults", {}).get("model", {})
                if isinstance(default_model, dict):
                    model = default_model.get("primary", "")

            skills = agent.get("skills", [])

            result.append({
                "id": agent_id,
                "name": agent_id,
                "model": model,
                "skillCount": len(skills),
                "skills": skills,
                "default": agent.get("default", False),
            })

        return JSONResponse(
            content={
                "updatedAt": datetime.now().isoformat(),
                "agents": result,
            },
            headers={
                "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
                "Pragma": "no-cache",
                "Expires": "0",
            },
        )
    except Exception:
        api_access_log.exception("Error reading openclaw.json for /api/agents")
        return JSONResponse(
            content={"agents": [], "error": "config_read_error", "updatedAt": datetime.now().isoformat()},
            status_code=200,
            headers={
                "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
                "Pragma": "no-cache",
                "Expires": "0",
            },
        )

@app.get("/api/weather")
async def api_weather(city: str = "Millersville"):
    """Proxy weather data from wttr.in"""
    try:
        response = requests.get(f"https://wttr.in/{city}?format=j1", timeout=10.0)
        if response.status_code == 200:
            data = response.json()
            current = data.get("current_condition", [{}])[0]
            return JSONResponse(content={
                "temp": f"{current.get('temp_F', '--')}°F",
                "condition": current.get('weatherDesc', [{}])[0].get('value', 'Unknown'),
                "feels_like": f"{current.get('FeelsLikeF', '--')}°F",
                "city": city
            })
    except Exception as e:
        # Fallback to Jackson, MO if Millersville fails
        if city != "Jackson":
            return await api_weather(city="Jackson")
        return JSONResponse(content={
            "temp": "--°F",
            "condition": "Unavailable",
            "feels_like": "--°F",
            "city": city,
            "error": str(e)
        })

@app.get("/api/data")
async def api_get_data():
    """Get user data from database"""
    try:
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()
        cursor.execute("SELECT data_json, updated_at FROM user_data WHERE id = 1")
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return JSONResponse(content={
                "data": json.loads(row[0]),
                "updated_at": row[1]
            })
        return JSONResponse(content={"data": None})
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)

@app.post("/api/data")
async def api_save_data(request: Request):
    """Save user data to database"""
    try:
        body = await request.json()
        data_json = json.dumps(body)
        
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO user_data (id, data_json, updated_at) 
            VALUES (1, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(id) DO UPDATE SET 
                data_json = excluded.data_json,
                updated_at = CURRENT_TIMESTAMP
        ''', (data_json,))
        conn.commit()
        conn.close()
        
        return JSONResponse(content={
            "status": "saved",
            "timestamp": datetime.now().isoformat()
        })
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)

@app.get("/api/activity")
async def api_get_activity(limit: int = 50):
    """Get recent activity log entries"""
    try:
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, description, timestamp 
            FROM activity_log 
            ORDER BY timestamp DESC 
            LIMIT ?
        ''', (limit,))
        rows = cursor.fetchall()
        conn.close()
        
        activities = [
            {"id": row[0], "description": row[1], "timestamp": row[2]}
            for row in rows
        ]
        return JSONResponse(content=activities)
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)

@app.post("/api/activity")
async def api_log_activity(request: Request):
    """Log a new activity"""
    try:
        body = await request.json()
        description = body.get("description", "")
        
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO activity_log (description, timestamp) 
            VALUES (?, CURRENT_TIMESTAMP)
        ''', (description,))
        conn.commit()
        conn.close()
        
        return JSONResponse(content={"status": "logged"})
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)

@app.get("/api/airtable/metrics")
async def api_airtable_metrics(
    request: Request,
    date_range: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    campaign: Optional[str] = Query(None)
):
    session_id = request.client.host
    if session_id not in authenticated_sessions:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    filters = {}
    if date_range:
        filters['date_range'] = date_range
    if status:
        filters['status'] = status
    if source:
        filters['source'] = source
    if campaign:
        filters['campaign'] = campaign
    
    data = await fetch_airtable_data(filters if filters else None)
    return JSONResponse(content=data)

@app.get("/api/gmail/summary")
async def api_gmail_summary(request: Request):
    session_id = request.client.host
    if session_id not in authenticated_sessions:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    data = fetch_gmail_summary()
    return JSONResponse(content=data)

@app.get("/api/daily-report")
async def api_daily_report(request: Request):
    """Return the daily ProjectTracker report"""
    session_id = request.client.host
    if session_id not in authenticated_sessions:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    report_path = Path(__file__).parent / "daily_report.txt"
    if report_path.exists():
        content = report_path.read_text()
    else:
        content = "📊 Daily report not yet generated.\n\nRun: python3 scripts/project_tracker_check.py"
    
    return JSONResponse(content={"report": content})

@app.get("/api/performance")
async def api_performance(
    request: Request,
    date_range: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    campaign: Optional[str] = Query(None)
):
    session_id = request.client.host
    if session_id not in authenticated_sessions:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    filters = {}
    if date_range:
        filters['date_range'] = date_range
    if status:
        filters['status'] = status
    if source:
        filters['source'] = source
    if campaign:
        filters['campaign'] = campaign
    
    airtable_data = await fetch_airtable_data(filters if filters else None)
    metrics = calculate_performance_metrics(airtable_data)
    return JSONResponse(content=metrics)

@app.get("/api/notifications")
async def api_notifications(
    request: Request,
    date_range: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    campaign: Optional[str] = Query(None)
):
    session_id = request.client.host
    if session_id not in authenticated_sessions:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    filters = {}
    if date_range:
        filters['date_range'] = date_range
    if status:
        filters['status'] = status
    if source:
        filters['source'] = source
    if campaign:
        filters['campaign'] = campaign
    
    airtable_data = await fetch_airtable_data(filters if filters else None)
    gmail_data = fetch_gmail_summary()
    notifications = generate_notifications(airtable_data, gmail_data)
    return JSONResponse(content={"notifications": notifications})

@app.get("/api/refresh")
async def api_refresh(
    request: Request,
    date_range: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    campaign: Optional[str] = Query(None)
):
    """Refresh all data with optional filters"""
    session_id = request.client.host
    if session_id not in authenticated_sessions:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    filters = {}
    if date_range:
        filters['date_range'] = date_range
    if status:
        filters['status'] = status
    if source:
        filters['source'] = source
    if campaign:
        filters['campaign'] = campaign
    
    airtable_data = await fetch_airtable_data(filters if filters else None)
    gmail_data = fetch_gmail_summary()
    metrics = calculate_performance_metrics(airtable_data)
    notifications = generate_notifications(airtable_data, gmail_data)
    
    return JSONResponse(content={
        "airtable": airtable_data,
        "gmail": gmail_data,
        "performance": metrics,
        "notifications": notifications,
        "timestamp": datetime.now().isoformat()
    })

@app.get("/api/filters/options")
async def api_filter_options(request: Request):
    """Get available filter options"""
    session_id = request.client.host
    if session_id not in authenticated_sessions:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    # Fetch base data to get available options
    base_data = await fetch_airtable_data()
    
    return JSONResponse(content={
        "date_ranges": [
            {"value": "all", "label": "All Time"},
            {"value": "today", "label": "Today"},
            {"value": "week", "label": "This Week"},
            {"value": "month", "label": "This Month"}
        ],
        "statuses": [
            {"value": "all", "label": "All Statuses"},
            {"value": "New", "label": "New"},
            {"value": "Hot", "label": "Hot"},
            {"value": "Closed", "label": "Closed"},
            {"value": "Needs Follow-Up", "label": "Needs Follow-Up"}
        ],
        "sources": [{"value": "all", "label": "All Sources"}] + 
                   [{"value": s, "label": s} for s in base_data.get("available_sources", [])],
        "campaigns": [{"value": "all", "label": "All Campaigns"}] + 
                    [{"value": c, "label": c} for c in base_data.get("available_campaigns", [])]
    })

@app.get("/api/strategic-metrics")
async def api_strategic_metrics(
    request: Request,
    date_range: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    campaign: Optional[str] = Query(None)
):
    """Get strategic business metrics for AI Voice Partner"""
    session_id = request.client.host
    if session_id not in authenticated_sessions:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    filters = {}
    if date_range:
        filters['date_range'] = date_range
    if status:
        filters['status'] = status
    if source:
        filters['source'] = source
    if campaign:
        filters['campaign'] = campaign
    
    airtable_data = await fetch_airtable_data(filters if filters else None)
    gmail_data = fetch_gmail_summary()
    strategic = calculate_all_strategic_metrics(airtable_data, gmail_data)
    
    return JSONResponse(content=strategic)

# ============== HTML TEMPLATES ==============

LOGIN_HTML = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Dashboard Login - AI Digital Agents</title>
    <link rel="stylesheet" href="/static/style.css">
</head>
<body class="login-page">
    <div class="login-container">
        <div class="login-box">
            <div class="login-logo">🔍</div>
            <h1>AI Digital Agents</h1>
            <p class="login-subtitle">Campaign Dashboard</p>
            
            {% if error %}
            <div class="login-error">
                <span class="error-icon">⚠️</span>
                {{ error }}
            </div>
            {% endif %}
            
            <form method="post" action="/login" class="login-form">
                <div class="input-group">
                    <input type="password" name="password" placeholder="Enter password" required autocomplete="off">
                </div>
                <button type="submit" class="btn btn-login">Sign In</button>
            </form>
            
            <p class="login-hint">Contact admin if you need access</p>
        </div>
    </div>
</body>
</html>'''

# DASHBOARD_HTML - Restructured Layout 2024-02-24
DASHBOARD_HTML = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI Digital Agents Dashboard</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <link rel="stylesheet" href="/static/style_v3.css">
</head>
<body>
    <div class="container">
        <header class="header">
            <div class="header-content">
                <h1>🔍 AI Digital Agents Dashboard</h1>
                <div class="header-actions">
                    <!-- Navigation Bookmarks -->
                    <a href="#operating-system" class="icon-btn nav-bookmark" title="Operating System Info">
                        <span class="nav-icon">⚙️</span>
                    </a>
                    <a href="#blockers-section" class="icon-btn nav-bookmark" title="Blockers Analysis">
                        <span class="nav-icon">🚧</span>
                    </a>
                    <a href="/patterns-library" class="btn" style="background: #3b82f6; color: white; padding: 8px 16px; border-radius: 6px; text-decoration: none; font-size: 0.85rem; margin-right: 10px;">🧠 Patterns Library</a>
                    <a href="/shorts-queue" class="btn" style="background: #e1306c; color: white; padding: 8px 16px; border-radius: 6px; text-decoration: none; font-size: 0.85rem; margin-right: 10px;">🎬 Shorts Queue</a>
                    <a href="/video-gallery" class="btn" style="background: #8b5cf6; color: white; padding: 8px 16px; border-radius: 6px; text-decoration: none; font-size: 0.85rem; margin-right: 10px;">🎥 Video Gallery</a>
                    <a href="/caption-designer" class="btn" style="background: #14b8a6; color: white; padding: 8px 16px; border-radius: 6px; text-decoration: none; font-size: 0.85rem; margin-right: 10px;">✍️ Caption Designer</a>
                    <div style="display:flex; align-items:center; gap:6px; margin-right:10px;">
                        <input id="song-upload-input" type="file" accept="audio/*" style="font-size:0.75rem; color:white; max-width:180px;" />
                        <button onclick="uploadSongChunked()" class="btn" style="background:#16a34a; color:white; padding:8px 10px; border-radius:6px; border:none; font-size:0.8rem; cursor:pointer;">⬆ Upload Song</button>
                        <span id="song-upload-status" style="font-size:0.72rem; color:rgba(255,255,255,0.8);"></span>
                    </div>
                    <div style="display:flex; align-items:center; gap:6px; margin-right:10px;">
                        <input id="clip-upload-input" type="file" accept="video/*" style="font-size:0.75rem; color:white; max-width:180px;" />
                        <button onclick="uploadClipChunked()" class="btn" style="background:#2563eb; color:white; padding:8px 10px; border-radius:6px; border:none; font-size:0.8rem; cursor:pointer;">⬆ Upload Clip</button>
                        <span id="clip-upload-status" style="font-size:0.72rem; color:rgba(255,255,255,0.8);"></span>
                    </div>
                    <form action="/set-segmentation-weights-form" method="post" style="display:flex; align-items:center; gap:4px; margin-right:10px; color:white; font-size:0.72rem;">
                        <span>Cuts</span>
                        <input name="hook" type="number" value="{{ hook_pct }}" min="5" max="90" step="1" style="width:50px; padding:4px; border-radius:4px; border:1px solid #334155; background:#0f172a; color:white;" title="Hook %" />
                        <input name="proof" type="number" value="{{ proof_pct }}" min="5" max="90" step="1" style="width:50px; padding:4px; border-radius:4px; border:1px solid #334155; background:#0f172a; color:white;" title="Proof %" />
                        <input name="cta" type="number" value="{{ cta_pct }}" min="5" max="90" step="1" style="width:50px; padding:4px; border-radius:4px; border:1px solid #334155; background:#0f172a; color:white;" title="CTA %" />
                        <button type="submit" class="btn" style="background:#7c3aed; color:white; padding:8px 10px; border-radius:6px; border:none; font-size:0.78rem; cursor:pointer;">Save Cuts</button>
                    </form>
                    <form action="/run-ugc-pipeline-form" method="post" style="display:flex; align-items:center; margin-right:10px;">
                        <button type="submit" class="btn" style="background:#f59e0b; color:#0b1220; padding:8px 10px; border-radius:6px; border:none; font-size:0.78rem; cursor:pointer; font-weight:700;">Run Pipeline Now</button>
                    </form>
                    <div style="font-size:0.68rem; color:#cbd5e1; margin-right:10px; max-width:520px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">
                        Status: {{ notice if notice else 'idle' }}{% if detail %} — {{ detail }}{% endif %}
                    </div>
                    <span id="connection-status" class="status-dot online" title="All systems connected"></span>
                    <a href="/logout" class="btn btn-logout">Logout</a>
                </div>
            </div>
        </header>

        <!-- Filter Bar -->
        <div class="filter-bar">
            <div class="filter-group">
                <span class="filter-label">📅 Date:</span>
                <div class="filter-options">
                    <button class="btn-filter active" data-filter="date" data-value="all">All</button>
                    <button class="btn-filter" data-filter="date" data-value="today">Today</button>
                    <button class="btn-filter" data-filter="date" data-value="week">Week</button>
                    <button class="btn-filter" data-filter="date" data-value="month">Month</button>
                </div>
            </div>
            <div class="filter-group">
                <span class="filter-label">📊 Status:</span>
                <select id="status-filter" class="filter-select">
                    <option value="all">All Statuses</option>
                    <option value="New">New</option>
                    <option value="Hot">Hot</option>
                    <option value="Closed">Closed</option>
                    <option value="Needs Follow-Up">Needs Follow-Up</option>
                </select>
            </div>
            <div class="filter-group">
                <span class="filter-label">📡 Source:</span>
                <select id="source-filter" class="filter-select">
                    <option value="all">All Sources</option>
                    <option value="Facebook">Facebook</option>
                    <option value="LinkedIn">LinkedIn</option>
                    <option value="Email">Email</option>
                    <option value="X">X</option>
                    <option value="Referral">Referral</option>
                    <option value="Website">Website</option>
                </select>
            </div>
            <div class="filter-group">
                <span class="filter-label">🎯 Campaign:</span>
                <select id="campaign-filter" class="filter-select">
                    <option value="all">All Campaigns</option>
                </select>
            </div>
            <button class="btn btn-text filter-reset" onclick="resetFilters()">Reset</button>
        </div>

        <!-- THIS WEEK'S TOP PRIORITIES - A1 & Top 3 -->
        <section class="card priorities-section" style="background: linear-gradient(135deg, rgba(10, 22, 40, 0.95) 0%, rgba(30, 58, 95, 0.95) 100%); border: 2px solid #2D5BFF; margin-bottom: 20px;">
            <div class="card-header" style="background: rgba(45, 91, 255, 0.15); border-bottom: 2px solid #2D5BFF;">
                <h2 style="color: #00D4FF; font-size: 1.2rem; margin: 0;">🎯 This Week's Top Priorities</h2>
                <span style="color: rgba(255, 255, 255, 0.7); font-size: 0.85rem;">March 2-8, 2026 — Multi-Track Focus Week</span>
            </div>
            <div class="card-body" style="padding: 16px;">
                <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px;">
                    <!-- A1 - UGC VIDEO PIPELINE -->
                    <div style="background: rgba(45, 91, 255, 0.08); border: 2px solid #2D5BFF; border-radius: 8px; padding: 16px;">
                        <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 12px; flex-wrap: wrap;">
                            <span style="background: #00D4FF; color: #0A1628; padding: 4px 12px; border-radius: 12px; font-size: 0.85rem; font-weight: 700;">A1</span>
                            <h3 style="font-size: 1.1rem; color: #00D4FF; margin: 0; flex: 1;">UGC Video Pipeline</h3>
                            <span style="width: 10px; height: 10px; border-radius: 50%; background: #27AE60; box-shadow: 0 0 8px #27AE60;"></span>
                        </div>
                        <p style="color: rgba(255, 255, 255, 0.7); margin-bottom: 12px; font-size: 0.85rem; line-height: 1.4;"><strong>Status:</strong> In active build — compliance gates running</p>
                        <ul style="list-style: none; padding: 0; margin: 0 0 12px 0;">
                            <li style="color: rgba(255, 255, 255, 0.7); padding: 3px 0; font-size: 0.8rem;">› Live Google ingestion cutover</li>
                            <li style="color: rgba(255, 255, 255, 0.7); padding: 3px 0; font-size: 0.8rem;">› Auto-generate ownership paperwork</li>
                            <li style="color: rgba(255, 255, 255, 0.7); padding: 3px 0; font-size: 0.8rem;">› Validate risk gates end-to-end</li>
                            <li style="color: rgba(255, 255, 255, 0.7); padding: 3px 0; font-size: 0.8rem;">› Ship first Remotion render</li>
                        </ul>
                        <span style="display: block; color: #00D4FF; font-size: 0.75rem; font-weight: 600; margin-top: 12px; padding-top: 12px; border-top: 1px solid rgba(255, 255, 255, 0.1);">🎬 Immediate execution priority</span>
                    </div>
                    
                    <!-- A2 - PATTERNS PARADIGM -->
                    <div style="background: rgba(255, 255, 255, 0.05); border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 8px; padding: 16px;">
                        <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 12px; flex-wrap: wrap;">
                            <span style="background: #2D5BFF; color: white; padding: 4px 10px; border-radius: 12px; font-size: 0.75rem; font-weight: 700;">A2</span>
                            <h3 style="font-size: 1rem; color: white; margin: 0; flex: 1;">Patterns Paradigm</h3>
                            <span style="width: 10px; height: 10px; border-radius: 50%; background: #27AE60; box-shadow: 0 0 8px #27AE60;"></span>
                        </div>
                        <p style="color: rgba(255, 255, 255, 0.7); margin-bottom: 12px; font-size: 0.8rem; line-height: 1.4;"><strong>Status:</strong> Continue Building — Assessment Platform</p>
                        <ul style="list-style: none; padding: 0; margin: 0 0 12px 0;">
                            <li style="color: rgba(255, 255, 255, 0.7); padding: 3px 0; font-size: 0.8rem;">› BRD decision (custom vs hybrid)</li>
                            <li style="color: rgba(255, 255, 255, 0.7); padding: 3px 0; font-size: 0.8rem;">› AI Implementation Tier dev</li>
                            <li style="color: rgba(255, 255, 255, 0.7); padding: 3px 0; font-size: 0.8rem;">› Beta recruiting (5 by Mar 21)</li>
                            <li style="color: rgba(255, 255, 255, 0.7); padding: 3px 0; font-size: 0.8rem;">› Weekly check-ins start now</li>
                        </ul>
                        <span style="display: block; color: #00D4FF; font-size: 0.75rem; font-weight: 600; margin-top: 12px; padding-top: 12px; border-top: 1px solid rgba(255, 255, 255, 0.1);">📊 Long-term product foundation</span>
                    </div>
                    
                    <!-- A3 - PR FIRM -->
                    <div style="background: rgba(255, 255, 255, 0.05); border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 8px; padding: 16px;">
                        <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 12px; flex-wrap: wrap;">
                            <span style="background: #2D5BFF; color: white; padding: 4px 10px; border-radius: 12px; font-size: 0.75rem; font-weight: 700;">A3</span>
                            <h3 style="font-size: 1rem; color: white; margin: 0; flex: 1;">PR Firm (Texas)</h3>
                            <span style="width: 10px; height: 10px; border-radius: 50%; background: #F5A623; box-shadow: 0 0 8px #F5A623;"></span>
                        </div>
                        <p style="color: rgba(255, 255, 255, 0.7); margin-bottom: 12px; font-size: 0.8rem; line-height: 1.4;"><strong>Status:</strong> IMMEDIATE REVENUE — Real prospect</p>
                        <ul style="list-style: none; padding: 0; margin: 0 0 12px 0;">
                            <li style="color: rgba(255, 255, 255, 0.7); padding: 3px 0; font-size: 0.8rem;">› Scope specific workflows</li>
                            <li style="color: rgba(255, 255, 255, 0.7); padding: 3px 0; font-size: 0.8rem;">› Prepare tailored demo</li>
                            <li style="color: rgba(255, 255, 255, 0.7); padding: 3px 0; font-size: 0.8rem;">› Draft proposal ($500-20K)</li>
                            <li style="color: rgba(255, 255, 255, 0.7); padding: 3px 0; font-size: 0.8rem;">› Move to signed engagement</li>
                        </ul>
                        <span style="display: block; color: #00D4FF; font-size: 0.75rem; font-weight: 600; margin-top: 12px; padding-top: 12px; border-top: 1px solid rgba(255, 255, 255, 0.1);">💰 This week revenue opportunity</span>
                    </div>

                    <!-- A4 - UPGRADE SOLOMON -->
                    <div style="background: rgba(255, 255, 255, 0.05); border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 8px; padding: 16px;">
                        <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 12px; flex-wrap: wrap;">
                            <span style="background: #2D5BFF; color: white; padding: 4px 10px; border-radius: 12px; font-size: 0.75rem; font-weight: 700;">A4</span>
                            <h3 style="font-size: 1rem; color: white; margin: 0; flex: 1;">Upgrade Solomon</h3>
                            <span style="width: 10px; height: 10px; border-radius: 50%; background: #27AE60; box-shadow: 0 0 8px #27AE60;"></span>
                        </div>
                        <p style="color: rgba(255, 255, 255, 0.7); margin-bottom: 12px; font-size: 0.8rem; line-height: 1.4;"><strong>Status:</strong> Ongoing capability expansion</p>
                        <ul style="list-style: none; padding: 0; margin: 0 0 12px 0;">
                            <li style="color: rgba(255, 255, 255, 0.7); padding: 3px 0; font-size: 0.8rem;">› Audit capability gaps</li>
                            <li style="color: rgba(255, 255, 255, 0.7); padding: 3px 0; font-size: 0.8rem;">› Implement 3-5 upgrades</li>
                            <li style="color: rgba(255, 255, 255, 0.7); padding: 3px 0; font-size: 0.8rem;">› Test against live projects</li>
                            <li style="color: rgba(255, 255, 255, 0.7); padding: 3px 0; font-size: 0.8rem;">› Improve research + PM workflows</li>
                        </ul>
                        <span style="display: block; color: #00D4FF; font-size: 0.75rem; font-weight: 600; margin-top: 12px; padding-top: 12px; border-top: 1px solid rgba(255, 255, 255, 0.1);">🧠 Improves execution velocity</span>
                    </div>
                </div>
            </div>
        </section>

        <!-- KEY METRICS ROW - Leading (Left) + Lagging (Right) -->
        <div class="metrics-row">
            <!-- LEADING INDICATORS (First 4) -->
            <div class="metric-card leading">
                <div class="metric-icon">💬</div>
                <div class="metric-info">
                    <div id="dm-count" class="metric-value loading">--</div>
                    <div class="metric-label">FB DMs</div>
                    <div class="metric-sublabel">/10</div>
                </div>
            </div>
            <div class="metric-card leading">
                <div class="metric-icon">📝</div>
                <div class="metric-info">
                    <div id="posts-count" class="metric-value loading">--</div>
                    <div class="metric-label">Posts</div>
                    <div class="metric-sublabel">/10</div>
                </div>
            </div>
            <div class="metric-card leading">
                <div class="metric-icon">📧</div>
                <div class="metric-info">
                    <div id="emails-sent" class="metric-value loading">--</div>
                    <div class="metric-label">Emails</div>
                    <div class="metric-sublabel">TBD</div>
                </div>
            </div>
            <div class="metric-card leading">
                <div class="metric-icon">🗣️</div>
                <div class="metric-info">
                    <div id="conversations-unique" class="metric-value loading">--</div>
                    <div class="metric-label">Conversations</div>
                    <div id="conversations-total" class="metric-sublabel">--</div>
                </div>
            </div>
            
            <!-- LAGGING INDICATORS (Last 5) -->
            <div class="metric-card lagging">
                <div class="metric-icon">💵</div>
                <div class="metric-info">
                    <div id="mrr-value" class="metric-value loading">$--</div>
                    <div class="metric-label">MRR</div>
                    <div id="mrr-trend" class="metric-sublabel"></div>
                </div>
            </div>
            <div class="metric-card lagging">
                <div class="metric-icon">🎯</div>
                <div class="metric-info">
                    <div id="goal-percent" class="metric-value loading">--%</div>
                    <div class="metric-label">to $100K</div>
                    <div id="goal-remaining" class="metric-sublabel"></div>
                </div>
            </div>
            <div class="metric-card lagging">
                <div class="metric-icon">👥</div>
                <div class="metric-info">
                    <div id="active-clients" class="metric-value loading">--</div>
                    <div class="metric-label">Clients</div>
                    <div id="clients-to-target" class="metric-sublabel"></div>
                </div>
            </div>
            <div class="metric-card lagging">
                <div class="metric-icon">🔥</div>
                <div class="metric-info">
                    <div id="hot-leads-count" class="metric-value loading">--</div>
                    <div class="metric-label">Hot Leads</div>
                    <div class="metric-action">Action</div>
                </div>
            </div>
            <div class="metric-card lagging">
                <div class="metric-icon">🏆</div>
                <div class="metric-info">
                    <div id="win-rate" class="metric-value loading">--%</div>
                    <div class="metric-label">Win Rate</div>
                    <div id="pipeline-value" class="metric-sublabel"></div>
                </div>
            </div>
        </div>

        <!-- Smart Alerts Section -->
        <div id="smart-alerts" class="smart-alerts-container">
            <div class="smart-alerts-header">
                <h3>⚡ Action Required <span id="alerts-count" class="badge badge-critical">0</span></h3>
                <button onclick="dismissAllAlerts()" class="btn-text">Dismiss All</button>
            </div>
            <div id="alerts-list" class="alerts-list"></div>
        </div>

        <!-- Main Content Grid -->
        <div class="dashboard-grid">
            <!-- Campaign Stats -->
            <div class="card card-large">
                <div class="card-header">
                    <h2>📈 Campaign Performance</h2>
                    <div class="status-badges">
                        <span id="leads-status" class="badge badge-success">Live Data</span>
                    </div>
                </div>
                <div class="card-body">
                    <div class="stats-grid">
                        <div class="stat-item">
                            <span id="new-leads" class="stat-value loading">--</span>
                            <span class="stat-label">New Today</span>
                        </div>
                        <div class="stat-item">
                            <span id="posts-week" class="stat-value loading">--</span>
                            <span class="stat-label">Posts This Week</span>
                        </div>
                        <div class="stat-item">
                            <span id="total-posts" class="stat-value loading">--</span>
                            <span class="stat-label">Total Posts</span>
                        </div>
                        <div class="stat-item">
                            <span id="avg-response-rate" class="stat-value loading">--%</span>
                            <span class="stat-label">Avg Response</span>
                        </div>
                    </div>
                    <div class="chart-container">
                        <canvas id="statusChart"></canvas>
                    </div>
                </div>
            </div>

            <!-- Email Summary -->
            <div class="card">
                <div class="card-header">
                    <h2>📧 Email Summary</h2>
                    <div class="status-badges">
                        <span id="gmail-status" class="badge badge-success">Connected</span>
                    </div>
                </div>
                <div class="card-body">
                    <div class="email-metric">
                        <span id="unread-count" class="email-count loading">--</span>
                        <span class="email-label">Unread Messages</span>
                    </div>
                    <div id="recent-emails" class="email-list"></div>
                    <a href="https://mail.google.com" target="_blank" class="btn btn-primary btn-full">Open Gmail</a>
                </div>
            </div>

            <!-- Conversion Funnel -->
            <div class="card card-large">
                <div class="card-header">
                    <h2>🔄 Conversion Funnel</h2>
                </div>
                <div class="card-body">
                    <div class="funnel-container">
                        <div class="funnel-chart-container">
                            <canvas id="funnelChart"></canvas>
                        </div>
                        <div class="funnel-stats">
                            <div class="funnel-stage">
                                <div class="stage-bar" style="width: 100%">
                                    <span id="funnel-outreach" class="stage-value">--</span>
                                    <span class="stage-label">Outreach Sent</span>
                                </div>
                            </div>
                            <div class="funnel-stage">
                                <div class="stage-bar" style="width: 80%">
                                    <span id="funnel-responses" class="stage-value">--</span>
                                    <span class="stage-label">Responses</span>
                                </div>
                                <span id="rate-response" class="stage-rate">--%</span>
                            </div>
                            <div class="funnel-stage">
                                <div class="stage-bar" style="width: 60%">
                                    <span id="funnel-meetings" class="stage-value">--</span>
                                    <span class="stage-label">Meetings</span>
                                </div>
                                <span id="rate-meeting" class="stage-rate">--%</span>
                            </div>
                            <div class="funnel-stage">
                                <div class="stage-bar" style="width: 40%">
                                    <span id="funnel-closes" class="stage-value">--</span>
                                    <span class="stage-label">Closed Deals</span>
                                </div>
                                <span id="rate-close" class="stage-rate">--%</span>
                            </div>
                        </div>
                    </div>
                    <div class="conversion-summary">
                        <div class="conversion-item">
                            <span class="conversion-label">Overall Conversion</span>
                            <span id="overall-conversion" class="conversion-value">--%</span>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Hot Leads -->
            <div class="card">
                <div class="card-header">
                    <h2>🔥 Hot Leads</h2>
                    <a href="https://airtable.com" target="_blank" class="btn-text">View All</a>
                </div>
                <div class="card-body">
                    <div id="hot-leads-list" class="leads-list"></div>
                </div>
            </div>
        </div>

        <!-- TOP ROW: 4 Equal Sections - Full Width -->
        <div class="dashboard-content">
            <div class="four-section-row">
                <!-- Outreach Volume -->
                <div class="card">
                    <div class="card-header">
                        <h2>📤 Outreach</h2>
                    </div>
                    <div class="card-body" style="padding: 12px;">
                        <div class="outreach-metrics" style="display: flex; justify-content: space-between; margin-bottom: 8px;">
                            <div class="outreach-item" style="text-align: center;">
                                <span id="outreach-daily" class="outreach-value loading" style="font-size: 1.2rem;">--</span>
                                <span class="outreach-label" style="font-size: 0.75rem;">Daily</span>
                            </div>
                            <div class="outreach-item" style="text-align: center;">
                                <span id="outreach-weekly" class="outreach-value loading" style="font-size: 1.2rem;">--</span>
                                <span class="outreach-label" style="font-size: 0.75rem;">Weekly</span>
                            </div>
                            <div class="outreach-item" style="text-align: center;">
                                <span id="outreach-total" class="outreach-value loading" style="font-size: 1.2rem;">--</span>
                                <span class="outreach-label" style="font-size: 0.75rem;">Total</span>
                            </div>
                        </div>
                        <div class="chart-container small" style="height: 140px;">
                            <canvas id="outreachChart"></canvas>
                        </div>
                    </div>
                </div>

                <!-- Quick Links -->
                <div class="card">
                    <div class="card-header">
                        <h2>🔗 Links</h2>
                    </div>
                    <div class="card-body" style="padding: 12px;">
                        <div class="links-grid" style="display: grid; grid-template-columns: 1fr 1fr; gap: 6px;">
                            <a href="https://airtable.com" target="_blank" class="link-card" style="padding: 6px; font-size: 0.85rem;">
                                <span class="link-icon" style="font-size: 0.9rem;">📊</span>
                                <span class="link-text">Airtable</span>
                            </a>
                            <a href="https://facebook.com" target="_blank" class="link-card" style="padding: 6px; font-size: 0.85rem;">
                                <span class="link-icon" style="font-size: 0.9rem;">📱</span>
                                <span class="link-text">Facebook</span>
                            </a>
                            <a href="https://mail.google.com" target="_blank" class="link-card" style="padding: 6px; font-size: 0.85rem;">
                                <span class="link-icon" style="font-size: 0.9rem;">📧</span>
                                <span class="link-text">Gmail</span>
                            </a>
                            <a href="https://linkedin.com" target="_blank" class="link-card" style="padding: 6px; font-size: 0.85rem;">
                                <span class="link-icon" style="font-size: 0.9rem;">💼</span>
                                <span class="link-text">LinkedIn</span>
                            </a>
                            <a href="https://instagram.com" target="_blank" class="link-card" style="padding: 6px; font-size: 0.85rem;">
                                <span class="link-icon" style="font-size: 0.9rem;">📸</span>
                                <span class="link-text">Instagram</span>
                            </a>
                            <a href="https://x.com" target="_blank" class="link-card" style="padding: 6px; font-size: 0.85rem;">
                                <span class="link-icon" style="font-size: 0.9rem;">𝕏</span>
                                <span class="link-text">X/Twitter</span>
                            </a>
                        </div>
                    </div>
                </div>

                <!-- DECISIONS NEEDED -->
                <div class="card">
                    <div class="card-header">
                        <h2>❓ Decisions</h2>
                    </div>
                    <div class="card-body" style="padding: 12px;">
                        <div class="decisions-list" style="display: flex; flex-direction: column; gap: 8px;">
                            <div class="decision-item" style="display: flex; flex-direction: column; gap: 2px; padding: 6px; background: rgba(255,255,255,0.03); border-radius: 4px;">
                                <div style="display: flex; align-items: center; gap: 6px;">
                                    <span class="decision-priority high" style="font-size: 0.6rem; padding: 1px 4px;">HIGH</span>
                                    <span class="decision-task" style="font-size: 0.75rem; color: #fff;">Install rtrvr.ai</span>
                                </div>
                                <span class="decision-context" style="font-size: 0.75rem; color: rgba(255,255,255,0.5);">Blocks A3-A5</span>
                            </div>
                            <div class="decision-item" style="display: flex; flex-direction: column; gap: 2px; padding: 6px; background: rgba(255,255,255,0.03); border-radius: 4px;">
                                <div style="display: flex; align-items: center; gap: 6px;">
                                    <span class="decision-priority medium" style="font-size: 0.6rem; padding: 1px 4px;">MED</span>
                                    <span class="decision-task" style="font-size: 0.75rem; color: #fff;">Facebook login</span>
                                </div>
                                <span class="decision-context" style="font-size: 0.75rem; color: rgba(255,255,255,0.5);">Blocks B2 completion</span>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- DAILY SCHEDULE -->
                <div class="card">
                    <div class="card-header">
                        <h2>🕐 Schedule</h2>
                    </div>
                    <div class="card-body" style="padding: 12px;">
                        <div style="display: flex; flex-direction: column; gap: 3px;">
                            <div style="display: flex; justify-content: space-between; padding: 3px 6px; background: rgba(255,255,255,0.03); border-radius: 3px; font-size: 0.85rem;">
                                <span style="color: rgba(255,255,255,0.5);">06-08</span>
                                <span style="color: #fff;">Morning</span>
                            </div>
                            <div style="display: flex; justify-content: space-between; padding: 3px 6px; background: rgba(39,174,96,0.15); border-radius: 3px; font-size: 0.85rem; border-left: 2px solid #27AE60;">
                                <span style="color: #27AE60;">08-10</span>
                                <span style="color: #fff;">Deep Work</span>
                            </div>
                            <div style="display: flex; justify-content: space-between; padding: 3px 6px; background: rgba(255,255,255,0.03); border-radius: 3px; font-size: 0.85rem;">
                                <span style="color: rgba(255,255,255,0.5);">10-12</span>
                                <span style="color: #fff;">Execution</span>
                            </div>
                            <div style="display: flex; justify-content: space-between; padding: 3px 6px; background: rgba(255,255,255,0.03); border-radius: 3px; font-size: 0.85rem;">
                                <span style="color: rgba(255,255,255,0.5);">12-13</span>
                                <span style="color: rgba(255,255,255,0.7);">Lunch</span>
                            </div>
                            <div style="display: flex; justify-content: space-between; padding: 3px 6px; background: rgba(255,255,255,0.03); border-radius: 3px; font-size: 0.85rem;">
                                <span style="color: rgba(255,255,255,0.5);">13-15</span>
                                <span style="color: #fff;">Client</span>
                            </div>
                            <div style="display: flex; justify-content: space-between; padding: 3px 6px; background: rgba(255,255,255,0.03); border-radius: 3px; font-size: 0.85rem;">
                                <span style="color: rgba(255,255,255,0.5);">15-17</span>
                                <span style="color: #fff;">Admin</span>
                            </div>
                            <div style="display: flex; justify-content: space-between; padding: 3px 6px; background: rgba(245,166,35,0.1); border-radius: 3px; font-size: 0.85rem;">
                                <span style="color: #F5A623;">17-20</span>
                                <span style="color: #fff;">Flex</span>
                            </div>
                            <div style="display: flex; justify-content: space-between; padding: 3px 6px; background: rgba(231,76,60,0.05); border-radius: 3px; font-size: 0.85rem;">
                                <span style="color: rgba(255,255,255,0.4);">20+</span>
                                <span style="color: rgba(255,255,255,0.6);">Shutdown</span>
                            </div>
                        </div>
                    </div>
                </div>
            </div>


        </div>

        <!-- OPERATING SYSTEM INFORMATION SECTION -->
        <section id="operating-system" class="os-info-section">
            <div class="os-section-header">
                <h2>⚙️ Operating System Information</h2>
                <span class="os-subtitle">Business operations metrics, blockers, and system documentation</span>
            </div>
            
            <!-- OPERATING STATUS SECTION -->
            <section class="card operating-status-section">
                <div class="card-header">
                    <h2>📋 Operating Status</h2>
                    <span class="status-subtitle">A/B/C Priority System | Work: A1→A2→A3→B1→B2 | KEY: ⏳ In Progress = doing NOW | ⏳ Pending = next in queue</span>
                </div>
                <div class="card-body">
                    <div class="status-grid" style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px;">
                        <!-- TODAY'S TASKS: Merged A + B -->
                        <div class="status-column status-today">
                            <div class="status-column-header">
                                <span class="status-icon">📋</span>
                                <h3>TODAY'S TASKS</h3>
                                <span class="status-meta">A1-A3 complete, A4-A6 active, B1-B7 backlog</span>
                            </div>
                            <div class="status-table">
                                <div class="status-table-header">
                                    <span class="col-dot"></span>
                                    <span class="col-task">Task</span>
                                    <span class="col-project">Project</span>
                                    <span class="col-context">Context</span>
                                </div>
                                <!-- A-PRIORITY: ACTIVE TASKS -->
                                <div class="status-table-row">
                                    <span class="status-dot checkmark"></span>
                                    <span class="col-task">A1: Install rtrvr.ai Chrome extension</span>
                                    <span class="col-project">LinkedIn Automation Personal</span>
                                    <span class="col-context">✅ DONE — Extension installed and working</span>
                                </div>
                                <div class="status-table-row">
                                    <span class="status-dot checkmark"></span>
                                    <span class="col-task">A2: Extra free tier Gemini keys</span>
                                    <span class="col-project">Personal Productivity</span>
                                    <span class="col-context">✅ DONE — Additional API keys configured</span>
                                </div>
                                <div class="status-table-row">
                                    <span class="status-dot checkmark"></span>
                                    <span class="col-task">A3: Test Facebook profile extraction</span>
                                    <span class="col-project">Lead Enrichment SaaS</span>
                                    <span class="col-context">✅ DONE — Success! Facebook extraction working</span>
                                </div>


                                <div class="status-table-row">
                                    <span class="status-dot green"></span>
                                    <span class="col-task">A5: Implement RTRVR Business Model</span>
                                    <span class="col-project">RTRVR Automation Services</span>
                                    <span class="col-context">🎯 ACTIVE — Feasibility-first revenue model, PR firm lighthouse client</span>
                                </div>





                                <div class="status-table-row">
                                    <span class="status-dot checkmark"></span>
                                    <span class="col-task">A4: Crawler Subagent Setup</span>
                                    <span class="col-project">Operational Capabilities</span>
                                    <span class="col-context">✅ DONE — Bulk web crawler with structured extraction (crawl4ai)</span>
                                </div>

                            </div>
                        </div>
                        <!-- C-PRIORITY: Backlog (UNCHANGED) -->
                        <div class="status-column status-cpriority">
                            <div class="status-column-header">
                                <span class="status-icon">🟢</span>
                                <h3>C-PRIORITY</h3>
                            </div>
                            <div class="status-table">
                                <div class="status-table-header">
                                    <span class="col-dot"></span>
                                    <span class="col-task">Task</span>
                                    <span class="col-project">Project</span>
                                    <span class="col-context">Context</span>
                                </div>
                                <!-- C-PRIORITY: ACTIVE BACKLOG -->
                                <div class="status-table-row">
                                    <span class="status-icon-box empty"></span>
                                    <span class="col-task">C1: Design LinkedIn scaling architecture</span>
                                    <span class="col-project">Lead Enrichment SaaS</span>
                                    <span class="col-context">For customer volume</span>
                                </div>
                                <div class="status-table-row">
                                    <span class="status-icon-box empty"></span>
                                    <span class="col-task">C2: Finalize customer pricing model</span>
                                    <span class="col-project">Lead Enrichment SaaS</span>
                                    <span class="col-context">Target: $0.10-0.15/lead</span>
                                </div>
                                <div class="status-table-row">
                                    <span class="status-icon-box empty"></span>
                                    <span class="col-task">C3: Choose brand name</span>
                                    <span class="col-project">Lead Enrichment SaaS</span>
                                    <span class="col-context">VERO? CASCADE? Final decision</span>
                                </div>
                                <div class="status-table-row">
                                    <span class="status-dot checkmark"></span>
                                    <span class="col-task">C7: Research competitor analysis (Clearbit, ZoomInfo, Lusha)</span>
                                    <span class="col-project">Lead Enrichment SaaS</span>
                                    <span class="col-context">✅ Research applied to pricing model — see project doc</span>
                                </div>
                                <div class="status-table-row">
                                    <span class="status-dot checkmark"></span>
                                    <span class="col-task">C8: The Patterns Paradigm (Book/Speaking)</span>
                                    <span class="col-project">Digital Products</span>
                                    <span class="col-context">✅ Research complete — DECISION NEEDED — see project doc</span>
                                </div>
                                <div class="status-table-row">
                                    <span class="status-icon-box empty"></span>
                                    <span class="col-task">C14: Test Ollama Local LLM Workaround</span>
                                    <span class="col-project">Personal Productivity</span>
                                    <span class="col-context">Bypass Anthropic API using local models — see task doc</span>
                                </div>
                                <div class="status-table-row">
                                    <span class="status-icon-box empty"></span>
                                    <span class="col-task">C15: Test LinkedIn profile extraction</span>
                                    <span class="col-project">LinkedIn Automation SaaS</span>
                                    <span class="col-context">⏳ PAUSED — Free tier credits depleted</span>
                                </div>
                                <div class="status-table-row">
                                    <span class="status-icon-box empty"></span>
                                    <span class="col-task">C16: Test on 2-3 additional leads</span>
                                    <span class="col-project">Lead Enrichment SaaS</span>
                                    <span class="col-context">⏳ READY — awaiting extraction completion</span>
                                </div>
                                <div class="status-table-row">
                                    <span class="status-icon-box empty"></span>
                                    <span class="col-task">C17: Validate extraction output quality</span>
                                    <span class="col-project">LinkedIn Automation SaaS</span>
                                    <span class="col-context">Review fields, completeness, errors</span>
                                </div>
                                <div class="status-table-row">
                                    <span class="status-icon-box empty"></span>
                                    <span class="col-task">C18: Document validation workflows</span>
                                    <span class="col-project">Lead Enrichment SaaS</span>
                                    <span class="col-context">Create reusable process docs</span>
                                </div>
                                <div class="status-table-row">
                                    <span class="status-icon-box empty"></span>
                                    <span class="col-task">C19: Draft Builder Vetting Process</span>
                                    <span class="col-project">Architect Network</span>
                                    <span class="col-context">Application → Portfolio → References → Test Project → Agreement</span>
                                </div>
                                <div class="status-table-row">
                                    <span class="status-icon-box empty"></span>
                                    <span class="col-task">C20: Create LinkedIn "EXPERIENCE" Post</span>
                                    <span class="col-project">Architect Network</span>
                                    <span class="col-context">Recruitment post for AI builders with capacity</span>
                                </div>
                                <div class="status-table-row">
                                    <span class="status-icon-box empty"></span>
                                    <span class="col-task">C21: Set Up Engagement Tracking System</span>
                                    <span class="col-project">Architect Network</span>
                                    <span class="col-context">Preferred provider scoring (reposts, comments, speed)</span>
                                </div>
                                <div class="status-table-row">
                                    <span class="status-icon-box empty"></span>
                                    <span class="col-task">C22: Build Proven Builds Database</span>
                                    <span class="col-project">Architect Network</span>
                                    <span class="col-context">Airtable catalog of vetted solutions Matt can sell</span>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </section>
            
            <div class="os-grid">
                <!-- Blockers Analysis -->
                <div class="card card-large" id="blockers-section">
                    <div class="card-header">
                        <h3>🚧 Blockers Analysis</h3>
                        <button onclick="refreshBlockers()" class="btn-text">↻ Refresh</button>
                    </div>
                    <div class="card-body">
                        <div id="blockers-list" class="blockers-list">
                            <div class="blocker-item" data-blocker="decision-bottleneck">
                                <div class="blocker-info">
                                    <span class="blocker-icon">⏳</span>
                                    <div class="blocker-details">
                                        <span class="blocker-name">Decision Bottleneck</span>
                                        <span class="blocker-desc">Protocol fixed — only business decisions escalate to Matt now</span>
                                    </div>
                                </div>
                                <div class="blocker-meta">
                                    <span class="blocker-status status-improving">IMPROVING</span>
                                    <div class="blocker-progress-mini">
                                        <div class="progress-bar-mini">
                                            <div class="progress-fill-mini" style="width: 75%"></div>
                                        </div>
                                        <span class="progress-label-mini">75%</span>
                                    </div>
                                </div>
                            </div>

                            <div class="blocker-item" data-blocker="build-vs-execute">
                                <div class="blocker-info">
                                    <span class="blocker-icon">🔧</span>
                                    <div class="blocker-details">
                                        <span class="blocker-name">Build vs Execute Tension</span>
                                        <span class="blocker-desc">Facebook automation PROVEN — now executing instead of researching</span>
                                    </div>
                                </div>
                                <div class="blocker-meta">
                                    <span class="blocker-status status-improving">IMPROVING</span>
                                    <div class="blocker-progress-mini">
                                        <div class="progress-bar-mini">
                                            <div class="progress-fill-mini" style="width: 65%"></div>
                                        </div>
                                        <span class="progress-label-mini">65%</span>
                                    </div>
                                </div>
                            </div>

                            <div class="blocker-item" data-blocker="manual-dependency">
                                <div class="blocker-info">
                                    <span class="blocker-icon">⭐</span>
                                    <div class="blocker-details">
                                        <span class="blocker-name">Manual Dependency — BIGGEST WIN</span>
                                        <span class="blocker-desc">Facebook automated via Playwright — LinkedIn next. GOLIATH WOUNDED</span>
                                    </div>
                                </div>
                                <div class="blocker-meta">
                                    <span class="blocker-status status-improving">MAJOR PROGRESS</span>
                                    <div class="blocker-progress-mini">
                                        <div class="progress-bar-mini">
                                            <div class="progress-fill-mini" style="width: 70%"></div>
                                        </div>
                                        <span class="progress-label-mini">70%</span>
                                    </div>
                                </div>
                            </div>

                            <div class="blocker-item" data-blocker="data-chasm">
                                <div class="blocker-info">
                                    <span class="blocker-icon">📊</span>
                                    <div class="blocker-details">
                                        <span class="blocker-name">Data Chasm</span>
                                        <span class="blocker-desc">Validation workflow bridges gap completely — data now actionable</span>
                                    </div>
                                </div>
                                <div class="blocker-meta">
                                    <span class="blocker-status status-improving">NEARLY RESOLVED</span>
                                    <div class="blocker-progress-mini">
                                        <div class="progress-bar-mini">
                                            <div class="progress-fill-mini" style="width: 80%"></div>
                                        </div>
                                        <span class="progress-label-mini">80%</span>
                                    </div>
                                </div>
                            </div>

                            <div class="blocker-item" data-blocker="undefined-mvp">
                                <div class="blocker-info">
                                    <span class="blocker-icon">🎯</span>
                                    <div class="blocker-details">
                                        <span class="blocker-name">Undefined MVP</span>
                                        <span class="blocker-desc">Now clear: automated phone/email + semi-auto social + human judgment</span>
                                    </div>
                                </div>
                                <div class="blocker-meta">
                                    <span class="blocker-status status-improving">WELL DEFINED</span>
                                    <div class="blocker-progress-mini">
                                        <div class="progress-bar-mini">
                                            <div class="progress-fill-mini" style="width: 85%"></div>
                                        </div>
                                        <span class="progress-label-mini">85%</span>
                                    </div>
                                </div>
                            </div>
                        </div>
                        <div class="blocker-summary">
                            <div class="summary-item">
                                <span class="summary-label">Active Blockers:</span>
                                <span class="summary-value" id="active-blockers-count">0</span>
                            </div>
                            <div class="summary-item">
                                <span class="summary-label">Improving:</span>
                                <span class="summary-value" id="improving-blockers-count">5</span>
                            </div>
                            <div class="summary-item">
                                <span class="summary-label">Avg Progress:</span>
                                <span class="summary-value" id="avg-blocker-progress">75%</span>
                            </div>
                        </div>
                    </div>
                </div>
                
                <!-- Field Documentation -->
                <div class="card" id="field-docs-section">
                    <div class="card-header">
                        <h3>📖 Field Documentation</h3>
                    </div>
                    <div class="card-body">
                        <table class="help-table-compact">
                            <thead>
                                <tr><th>Field</th><th>Source</th></tr>
                            </thead>
                            <tbody>
                                <tr><td><strong>FB DMs</strong></td><td>Manual tracking</td></tr>
                                <tr><td><strong>Posts</strong></td><td>Airtable - Posts</td></tr>
                                <tr><td><strong>Emails</strong></td><td>Gmail API</td></tr>
                                <tr><td><strong>Conversations</strong></td><td>Calculated</td></tr>
                                <tr><td><strong>MRR</strong></td><td>Airtable - Closed</td></tr>
                                <tr><td><strong>Goal %</strong></td><td>Calculated</td></tr>
                                <tr><td><strong>Clients</strong></td><td>Airtable - Closed</td></tr>
                                <tr><td><strong>Hot Leads</strong></td><td>Airtable - Status</td></tr>
                                <tr><td><strong>Win Rate</strong></td><td>Calculated</td></tr>
                            </tbody>
                        </table>
                    </div>
                </div>
                
                <!-- Notifications -->
                <div class="card" id="notifications-section">
                    <div class="card-header">
                        <h3>🔔 Notifications</h3>
                        <button onclick="dismissAllNotifications()" class="btn-text">Clear All</button>
                    </div>
                    <div class="card-body">
                        <div id="notifications-list-os" class="notifications-list-os">
                            <div class="notification-item-os empty">
                                <span class="notification-icon-os">📭</span>
                                <span class="notification-text-os">No new notifications</span>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </section>


        <!-- OFFICIAL PROJECTS SECTION -->
        <section class="projects-card">
            <div class="projects-header">
                <h2>🎯 Official Projects</h2>
                <span class="projects-subtitle">Active initiatives and strategic context</span>
            </div>
            <div class="projects-body">
                
                <!-- PRODUCT/BUSINESS PROJECTS -->
                <div class="project-category">
                    <h3 class="category-header"><span class="cat-icon">💼</span> Product/Business Projects</h3>
                    <table class="proj-table">
                        <thead>
                            <tr><th class="col-proj-name">Project Name</th><th class="col-proj-desc">Description</th><th>Type</th><th>Status</th><th>Goal</th><th>Current Focus</th></tr>
                        </thead>
                        <tbody>
                            <tr class="proj-primary">
                                <td class="col-proj-name">AI Voice Partner</td>
                                <td class="col-proj-desc">AI phone answering for HVAC/trades — $100K revenue driver</td>
                                <td><span class="proj-badge svc">Service</span></td>
                                <td><span class="status-ind active"></span>Active</td>
                                <td class="mono">100K_revenue</td>
                                <td>HVAC launch, authority content, free audit</td>
                            </tr>
                            <tr>
                                <td class="col-proj-name">Lead Enrichment SaaS</td>
                                <td class="col-proj-desc">Lead data enrichment — validates, enriches, scores</td>
                                <td><span class="proj-badge saas">SaaS</span></td>
                                <td><span class="status-ind dev"></span>Dev</td>
                                <td class="mono">100K_revenue</td>
                                <td>LinkedIn extraction, $0.10-0.15/lead target</td>
                            </tr>
                            <tr>
                                <td class="col-proj-name">LinkedIn Automation Personal</td>
                                <td class="col-proj-desc">Personal LinkedIn — network building</td>
                                <td><span class="proj-badge tool">Tool</span></td>
                                <td><span class="status-ind active"></span>Active</td>
                                <td class="mono">authority</td>
                                <td>rtrvr.ai setup, prospect list</td>
                            </tr>
                            <tr class="proj-muted">
                                <td class="col-proj-name">LinkedIn Automation SaaS</td>
                                <td class="col-proj-desc">Cloud LinkedIn for customers (Phase 2)</td>
                                <td><span class="proj-badge feat">Feature</span></td>
                                <td><span class="status-ind planned"></span>Planned</td>
                                <td class="mono">100K_revenue</td>
                                <td>After personal version works</td>
                            </tr>
                        </tbody>
                    </table>
                </div>

                <!-- OPERATIONAL PROJECTS -->
                <div class="project-category">
                    <h3 class="category-header"><span class="cat-icon">⚙️</span> Operational Projects</h3>
                    <table class="proj-table">
                        <thead>
                            <tr><th class="col-proj-name">Project Name</th><th class="col-proj-desc">Description</th><th>Type</th><th>Status</th><th>Goal</th><th>Current Focus</th></tr>
                        </thead>
                        <tbody>
                            <tr>
                                <td class="col-proj-name">Email Agent</td>
                                <td class="col-proj-desc">Solomon's email management — inbox, CRM automation</td>
                                <td><span class="proj-badge sys">System</span></td>
                                <td><span class="status-ind active"></span>Active</td>
                                <td class="mono">operational</td>
                                <td>CRM sync, 9 contacts, 7 follow-ups sent</td>
                            </tr>
                            <tr>
                                <td class="col-proj-name">Content Engine</td>
                                <td class="col-proj-desc">Authority content — feeds personal + AI Voice</td>
                                <td><span class="proj-badge sys">System</span></td>
                                <td><span class="status-ind active"></span>Active</td>
                                <td class="mono">authority</td>
                                <td>3 posts, free audit offer, FB invites</td>
                            </tr>
                        </tbody>
                    </table>
                </div>

                <!-- COMPANY/BRAND ENTITIES -->
                <div class="project-category">
                    <h3 class="category-header"><span class="cat-icon">🏢</span> Company/Brand Entities</h3>
                    <table class="proj-table">
                        <thead>
                            <tr><th class="col-proj-name">Entity Name</th><th class="col-proj-desc">Description</th><th>Type</th><th>Status</th><th>Goal</th><th>Role</th></tr>
                        </thead>
                        <tbody>
                            <tr class="proj-muted">
                                <td class="col-proj-name">AI Digital Agents</td>
                                <td class="col-proj-desc">Umbrella company — owns all AI business</td>
                                <td><span class="proj-badge ent">Parent</span></td>
                                <td><span class="status-ind active"></span>Active</td>
                                <td class="mono">operational</td>
                                <td>Container for growth</td>
                            </tr>
                            <tr class="proj-muted">
                                <td class="col-proj-name">AI Voice Partner</td>
                                <td class="col-proj-desc">Operating brand customers see</td>
                                <td><span class="proj-badge ent">Brand</span></td>
                                <td><span class="status-ind active"></span>Active</td>
                                <td class="mono">100K_revenue</td>
                                <td>Customer relationship</td>
                            </tr>
                        </tbody>
                    </table>
                </div>

                <!-- ORG CHART -->
                <div class="org-chart-section">
                    <h3 class="category-header"><span class="cat-icon">🔗</span> Project Relationships</h3>
                    <div class="org-hierarchy">
                        <!-- Level 1: Parent -->
                        <div class="org-level level-1">
                            <div class="org-box parent-box">AI Digital Agents</div>
                        </div>
                        
                        <!-- Level 2: Connector Lines -->
                        <div class="org-connectors">
                            <div class="v-line"></div>
                            <div class="h-line"></div>
                        </div>
                        
                        <!-- Level 3: Children -->
                        <div class="org-level level-3">
                            <div class="org-branch">
                                <div class="v-line-short"></div>
                                <div class="org-box child-box">AI Voice Partner</div>
                                <div class="org-subs">
                                    <span>Content Engine</span>
                                    <span>Email Agent</span>
                                    <span>LinkedIn_Personal</span>
                                </div>
                            </div>
                            
                            <div class="org-branch">
                                <div class="v-line-short"></div>
                                <div class="org-box child-box">Lead Enrichment SaaS</div>
                                <div class="org-subs">
                                    <span>LinkedIn_SaaS (Phase 2)</span>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </section>

        <style>
            .projects-card { background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1); border-radius: 8px; margin: 16px 0; }
            .projects-header { padding: 16px; border-bottom: 1px solid rgba(255,255,255,0.1); }
            .projects-header h2 { margin: 0; font-size: 1.1rem; color: #fff; }
            .projects-subtitle { font-size: 0.85rem; color: rgba(255,255,255,0.6); }
            .projects-body { padding: 16px; }
            .project-category { margin-bottom: 20px; }
            .category-header { display: flex; align-items: center; gap: 8px; font-size: 0.95rem; color: #00D4FF; margin-bottom: 10px; padding-bottom: 8px; border-bottom: 1px solid rgba(255,255,255,0.1); }
            .cat-icon { font-size: 1.1rem; }
            .proj-table { width: 100%; border-collapse: collapse; font-size: 0.8rem; }
            .proj-table th { text-align: left; padding: 8px; background: rgba(255,255,255,0.05); color: rgba(255,255,255,0.7); font-weight: 600; }
            .proj-table td { padding: 8px; border-bottom: 1px solid rgba(255,255,255,0.05); vertical-align: top; }
            .proj-table tr:hover { background: rgba(255,255,255,0.03); }
            .proj-table td strong { display: block; color: #fff; margin-bottom: 2px; }
            .proj-table td small { display: block; color: rgba(255,255,255,0.5); font-size: 0.85rem; }
            .proj-primary { background: rgba(39,174,96,0.1); border-left: 3px solid #27AE60; }
            .proj-muted { opacity: 0.8; background: rgba(255,255,255,0.02); }
            .proj-badge { display: inline-block; font-size: 0.6rem; padding: 2px 6px; border-radius: 3px; font-weight: 600; text-transform: uppercase; }
            .proj-badge.svc { background: rgba(45,91,255,0.2); color: #2D5BFF; }
            .proj-badge.saas { background: rgba(0,212,255,0.2); color: #00D4FF; }
            .proj-badge.tool { background: rgba(155,89,182,0.2); color: #BB8FCE; }
            .proj-badge.feat { background: rgba(245,166,35,0.2); color: #F5A623; }
            .proj-badge.sys { background: rgba(39,174,96,0.2); color: #27AE60; }
            .proj-badge.ent { background: rgba(255,255,255,0.1); color: rgba(255,255,255,0.7); }
            .status-ind { display: inline-block; width: 6px; height: 6px; border-radius: 50%; margin-right: 5px; }
            .status-ind.active { background: #27AE60; box-shadow: 0 0 4px #27AE60; }
            .status-ind.dev { background: #F5A623; }
            .status-ind.planned { background: rgba(255,255,255,0.4); }
            .mono { font-family: monospace; font-size: 0.85rem; color: #00D4FF; }
            .col-proj-name { font-weight: 500; color: #fff; min-width: 180px; }
            .col-proj-desc { color: rgba(255,255,255,0.7); font-size: 0.8rem; min-width: 220px; }
            .org-chart-section { margin-top: 20px; padding-top: 16px; border-top: 1px solid rgba(255,255,255,0.1); }
            .org-hierarchy { display: flex; flex-direction: column; align-items: center; padding: 20px; }
            .org-level { display: flex; justify-content: center; }
            .org-box { border-radius: 6px; font-weight: 600; text-align: center; }
            .parent-box { background: #2D5BFF; color: white; padding: 12px 28px; font-size: 1.3rem; }
            .org-connectors { position: relative; width: 280px; height: 30px; margin: 0 auto; }
            .v-line { position: absolute; left: 50%; top: 0; width: 2px; height: 15px; background: rgba(255,255,255,0.4); transform: translateX(-50%); }
            .h-line { position: absolute; left: 50%; top: 15px; width: 200px; height: 2px; background: rgba(255,255,255,0.4); transform: translateX(-50%); }
            .level-3 { display: flex; gap: 40px; justify-content: center; }
            .org-branch { display: flex; flex-direction: column; align-items: center; text-align: center; }
            .v-line-short { width: 2px; height: 15px; background: rgba(255,255,255,0.4); margin-bottom: 0; }
            .child-box { background: #1E3A5F; color: white; padding: 10px 20px; border: 1px solid rgba(255,255,255,0.2); margin-top: 0; }
            .org-subs { display: flex; flex-wrap: wrap; gap: 6px; justify-content: center; margin-top: 10px; max-width: 200px; }
            .org-subs span { font-size: 0.85rem; background: rgba(255,255,255,0.1); color: rgba(255,255,255,0.8); padding: 4px 10px; border-radius: 4px; border: 1px solid rgba(255,255,255,0.1); }
            @media (max-width: 768px) { .proj-table { font-size: 0.85rem; } .proj-table th, .proj-table td { padding: 6px; } .org-children { gap: 12px; } }
        </style>

        <!-- NEW TODAY'S TASKS - Enhanced Full Width -->
        <section class="card new-tasks-section" style="margin-top: 24px; background: rgba(255,255,255,0.03); width: 100%;">
            <div class="card-header" style="border-bottom: 2px solid rgba(0,212,255,0.3);">
                <h2>📋 TODAY'S TASKS (Enhanced)</h2>
                <span class="status-subtitle">Task | Project | Goal | Tags | Intent | Blocks | Blocked By | Status (24 tasks)</span>
            </div>
            <div class="card-body" style="padding: 0; max-height: 600px; overflow-y: auto;">
                <table class="new-tasks-table" style="width: 100%; border-collapse: collapse; font-size: 0.9rem;">
                    <thead style="position: sticky; top: 0; z-index: 10;">
                        <tr style="background: rgba(0,212,255,0.1);">
                            <th style="padding: 10px 8px; text-align: left; color: #00D4FF; font-weight: 600; border-bottom: 2px solid rgba(0,212,255,0.3); width: 18%;">Task</th>
                            <th style="padding: 10px 8px; text-align: left; color: #00D4FF; font-weight: 600; border-bottom: 2px solid rgba(0,212,255,0.3); width: 12%;">Project</th>
                            <th style="padding: 10px 8px; text-align: left; color: #00D4FF; font-weight: 600; border-bottom: 2px solid rgba(0,212,255,0.3); width: 8%;">Goal</th>
                            <th style="padding: 10px 8px; text-align: left; color: #00D4FF; font-weight: 600; border-bottom: 2px solid rgba(0,212,255,0.3); width: 10%;">Tags</th>
                            <th style="padding: 10px 8px; text-align: left; color: #00D4FF; font-weight: 600; border-bottom: 2px solid rgba(0,212,255,0.3); width: 20%;">Intent</th>
                            <th style="padding: 10px 8px; text-align: left; color: #00D4FF; font-weight: 600; border-bottom: 2px solid rgba(0,212,255,0.3); width: 12%;">Blocks</th>
                            <th style="padding: 10px 8px; text-align: left; color: #00D4FF; font-weight: 600; border-bottom: 2px solid rgba(0,212,255,0.3); width: 12%;">Blocked By</th>
                            <th style="padding: 10px 8px; text-align: center; color: #00D4FF; font-weight: 600; border-bottom: 2px solid rgba(0,212,255,0.3); width: 8%;">Status</th>
                        </tr>
                    </thead>
                    <tbody>
                        <!-- A-PRIORITY: Must Do Tomorrow -->
                        <tr>
                            <td style="padding: 8px; color: #27AE60; font-weight: 500;">A1: Install rtrvr.ai</td>
                            <td style="padding: 8px; color: rgba(255,255,255,0.7);">LinkedIn Personal</td>
                            <td style="padding: 8px; color: #00D4FF; font-family: monospace; font-size: 0.85rem;">authority</td>
                            <td style="padding: 8px;">
                                <span style="background: rgba(45,91,255,0.2); color: #2D5BFF; padding: 2px 6px; border-radius: 3px; font-size: 0.75rem; margin-right: 4px;">linkedin</span>
                                <span style="background: rgba(39,174,96,0.2); color: #27AE60; padding: 2px 6px; border-radius: 3px; font-size: 0.75rem; margin-right: 4px;">setup</span>
                                <span style="background: rgba(231,76,60,0.2); color: #E74C3C; padding: 2px 6px; border-radius: 3px; font-size: 0.75rem;">blocks</span>
                            </td>
                            <td style="padding: 8px; color: rgba(255,255,255,0.6); font-size: 0.85rem;">Install Chrome extension for LinkedIn automation</td>
                            <td style="padding: 8px; color: rgba(255,255,255,0.5); font-size: 0.85rem;">LinkedIn extraction workflow</td>
                            <td style="padding: 8px; color: rgba(255,255,255,0.5); font-size: 0.85rem;">Extension installed</td>
                            <td style="padding: 8px; text-align: center;"><span style="background: rgba(39,174,96,0.3); color: #27AE60; padding: 2px 8px; border-radius: 3px; font-size: 0.75rem; font-weight: 600;">✅ Done</span></td>
                        </tr>
                        <tr>
                            <td style="padding: 8px; color: #27AE60; font-weight: 500;">A2: Extra free tier Gemini keys</td>
                            <td style="padding: 8px; color: rgba(255,255,255,0.7);">Personal Productivity</td>
                            <td style="padding: 8px; color: #00D4FF; font-family: monospace; font-size: 0.85rem;">operational</td>
                            <td style="padding: 8px;">
                                <span style="background: rgba(155,89,182,0.2); color: #BB8FCE; padding: 2px 6px; border-radius: 3px; font-size: 0.75rem; margin-right: 4px;">api-keys</span>
                                <span style="background: rgba(39,174,96,0.2); color: #27AE60; padding: 2px 6px; border-radius: 3px; font-size: 0.75rem; margin-right: 4px;">gemini</span>
                                <span style="background: rgba(39,174,96,0.2); color: #27AE60; padding: 2px 6px; border-radius: 3px; font-size: 0.75rem;">setup</span>
                            </td>
                            <td style="padding: 8px; color: rgba(255,255,255,0.6); font-size: 0.85rem;">Additional API keys for extended usage</td>
                            <td style="padding: 8px; color: rgba(255,255,255,0.5); font-size: 0.85rem;">—</td>
                            <td style="padding: 8px; color: rgba(255,255,255,0.5); font-size: 0.85rem;">—</td>
                            <td style="padding: 8px; text-align: center;"><span style="background: rgba(39,174,96,0.3); color: #27AE60; padding: 2px 8px; border-radius: 3px; font-size: 0.75rem; font-weight: 600;">✅ Done</span></td>
                        </tr>
                        <tr style="background: rgba(39,174,96,0.08);">
                            <td style="padding: 8px; color: #27AE60; font-weight: 500;">A3: Test Facebook profile extraction</td>
                            <td style="padding: 8px; color: rgba(255,255,255,0.7);">Lead Enrichment SaaS</td>
                            <td style="padding: 8px; color: #00D4FF; font-family: monospace; font-size: 0.85rem;">100K</td>
                            <td style="padding: 8px;">
                                <span style="background: rgba(231,76,60,0.2); color: #E74C3C; padding: 2px 6px; border-radius: 3px; font-size: 0.75rem; margin-right: 4px;">facebook</span>
                                <span style="background: rgba(39,174,96,0.2); color: #27AE60; padding: 2px 6px; border-radius: 3px; font-size: 0.75rem; margin-right: 4px;">validation</span>
                                <span style="background: rgba(245,166,35,0.2); color: #F5A623; padding: 2px 6px; border-radius: 3px; font-size: 0.75rem;">success</span>
                            </td>
                            <td style="padding: 8px; color: rgba(255,255,255,0.6); font-size: 0.85rem;">Facebook extraction test — SUCCESS</td>
                            <td style="padding: 8px; color: rgba(255,255,255,0.5); font-size: 0.85rem;">Lead gen workflow</td>
                            <td style="padding: 8px; color: rgba(255,255,255,0.5); font-size: 0.85rem;">—</td>
                            <td style="padding: 8px; text-align: center;"><span style="background: rgba(39,174,96,0.3); color: #27AE60; padding: 2px 8px; border-radius: 3px; font-size: 0.75rem; font-weight: 600;">✅ Done</span></td>
                        </tr>
                        <tr>
                            <td style="padding: 8px; color: #fff; font-weight: 500;">A4: Test LinkedIn profile extraction</td>
                            <td style="padding: 8px; color: rgba(255,255,255,0.7);">LinkedIn SaaS</td>
                            <td style="padding: 8px; color: #00D4FF; font-family: monospace; font-size: 0.85rem;">100K</td>
                            <td style="padding: 8px;">
                                <span style="background: rgba(45,91,255,0.2); color: #2D5BFF; padding: 2px 6px; border-radius: 3px; font-size: 0.75rem; margin-right: 4px;">linkedin</span>
                                <span style="background: rgba(245,166,35,0.2); color: #F5A623; padding: 2px 6px; border-radius: 3px; font-size: 0.75rem; margin-right: 4px;">paused</span>
                                <span style="background: rgba(245,166,35,0.2); color: #F5A623; padding: 2px 6px; border-radius: 3px; font-size: 0.75rem;">revenue_critical</span>
                            </td>
                            <td style="padding: 8px; color: rgba(255,255,255,0.6); font-size: 0.85rem;">Validate data quality & accuracy</td>
                            <td style="padding: 8px; color: rgba(255,255,255,0.5); font-size: 0.85rem;">A5 lead testing</td>
                            <td style="padding: 8px; color: rgba(255,255,255,0.5); font-size: 0.85rem;">Free tier credits depleted</td>
                            <td style="padding: 8px; text-align: center;"><span style="background: rgba(45,91,255,0.3); color: #2D5BFF; padding: 2px 8px; border-radius: 3px; font-size: 0.75rem; font-weight: 600;">Backlog</span></td>
                        </tr>
                        <tr style="background: rgba(231,76,60,0.05);">
                            <td style="padding: 8px; color: #fff; font-weight: 500;">A5: Test on 2-3 leads</td>
                            <td style="padding: 8px; color: rgba(255,255,255,0.7);">Lead Enrichment</td>
                            <td style="padding: 8px; color: #00D4FF; font-family: monospace; font-size: 0.85rem;">100K</td>
                            <td style="padding: 8px;">
                                <span style="background: rgba(245,166,35,0.2); color: #F5A623; padding: 2px 6px; border-radius: 3px; font-size: 0.75rem; margin-right: 4px;">unblocked</span>
                                <span style="background: rgba(231,76,60,0.2); color: #E74C3C; padding: 2px 6px; border-radius: 3px; font-size: 0.75rem; margin-right: 4px;">revenue_critical</span>
                                <span style="background: rgba(245,166,35,0.2); color: #F5A623; padding: 2px 6px; border-radius: 3px; font-size: 0.75rem;">enrichment</span>
                            </td>
                            <td style="padding: 8px; color: rgba(255,255,255,0.6); font-size: 0.85rem;">Test extraction on 2-3 real leads</td>
                            <td style="padding: 8px; color: rgba(255,255,255,0.5); font-size: 0.85rem;">Process documentation</td>
                            <td style="padding: 8px; color: rgba(255,255,255,0.5); font-size: 0.85rem;">Awaiting A4 completion</td>
                            <td style="padding: 8px; text-align: center;"><span style="background: rgba(45,91,255,0.3); color: #2D5BFF; padding: 2px 8px; border-radius: 3px; font-size: 0.75rem; font-weight: 600;">Backlog</span></td>
                        </tr>
                        <tr>
                            <td style="padding: 8px; color: #fff; font-weight: 500;">B1: Validate output quality</td>
                            <td style="padding: 8px; color: rgba(255,255,255,0.7);">LinkedIn SaaS</td>
                            <td style="padding: 8px; color: #00D4FF; font-family: monospace; font-size: 0.85rem;">100K</td>
                            <td style="padding: 8px;">
                                <span style="background: rgba(45,91,255,0.2); color: #2D5BFF; padding: 2px 6px; border-radius: 3px; font-size: 0.75rem; margin-right: 4px;">linkedin</span>
                                <span style="background: rgba(39,174,96,0.2); color: #27AE60; padding: 2px 6px; border-radius: 3px; font-size: 0.75rem; margin-right: 4px;">validation</span>
                                <span style="background: rgba(245,166,35,0.2); color: #F5A623; padding: 2px 6px; border-radius: 3px; font-size: 0.75rem;">enrichment</span>
                            </td>
                            <td style="padding: 8px; color: rgba(255,255,255,0.6); font-size: 0.85rem;">Review fields, completeness, errors</td>
                            <td style="padding: 8px; color: rgba(255,255,255,0.5); font-size: 0.85rem;">Architecture decisions</td>
                            <td style="padding: 8px; color: rgba(255,255,255,0.5); font-size: 0.85rem;">Initial extraction tests needed</td>
                            <td style="padding: 8px; text-align: center;"><span style="background: rgba(45,91,255,0.3); color: #2D5BFF; padding: 2px 8px; border-radius: 3px; font-size: 0.75rem; font-weight: 600;">Backlog</span></td>
                        </tr>
                        <tr>
                            <td style="padding: 8px; color: #fff; font-weight: 500;">B2: Document workflows</td>
                            <td style="padding: 8px; color: rgba(255,255,255,0.7);">Lead Enrichment</td>
                            <td style="padding: 8px; color: #00D4FF; font-family: monospace; font-size: 0.85rem;">operational</td>
                            <td style="padding: 8px;">
                                <span style="background: rgba(155,89,182,0.2); color: #BB8FCE; padding: 2px 6px; border-radius: 3px; font-size: 0.75rem; margin-right: 4px;">docs</span>
                                <span style="background: rgba(245,166,35,0.2); color: #F5A623; padding: 2px 6px; border-radius: 3px; font-size: 0.75rem; margin-right: 4px;">enrichment</span>
                                <span style="background: rgba(155,89,182,0.2); color: #BB8FCE; padding: 2px 6px; border-radius: 3px; font-size: 0.75rem;">operational</span>
                            </td>
                            <td style="padding: 8px; color: rgba(255,255,255,0.6); font-size: 0.85rem;">Create reusable process docs</td>
                            <td style="padding: 8px; color: rgba(255,255,255,0.5); font-size: 0.85rem;">Pricing model input</td>
                            <td style="padding: 8px; color: rgba(255,255,255,0.5); font-size: 0.85rem;">Working test extractions first</td>
                            <td style="padding: 8px; text-align: center;"><span style="background: rgba(45,91,255,0.3); color: #2D5BFF; padding: 2px 8px; border-radius: 3px; font-size: 0.75rem; font-weight: 600;">Backlog</span></td>
                        </tr>
                        <tr>
                            <td style="padding: 8px; color: #fff; font-weight: 500;">B3: Builder Vetting Process</td>
                            <td style="padding: 8px; color: rgba(255,255,255,0.7);">Architect Network</td>
                            <td style="padding: 8px; color: #00D4FF; font-family: monospace; font-size: 0.85rem;">operational</td>
                            <td style="padding: 8px;">
                                <span style="background: rgba(155,89,182,0.2); color: #BB8FCE; padding: 2px 6px; border-radius: 3px; font-size: 0.75rem; margin-right: 4px;">process</span>
                                <span style="background: rgba(45,91,255,0.2); color: #2D5BFF; padding: 2px 6px; border-radius: 3px; font-size: 0.75rem; margin-right: 4px;">architect</span>
                                <span style="background: rgba(155,89,182,0.2); color: #BB8FCE; padding: 2px 6px; border-radius: 3px; font-size: 0.75rem;">operational</span>
                            </td>
                            <td style="padding: 8px; color: rgba(255,255,255,0.6); font-size: 0.85rem;">Application → Test Project → Agreement</td>
                            <td style="padding: 8px; color: rgba(255,255,255,0.5); font-size: 0.85rem;">Recruitment post</td>
                            <td style="padding: 8px; color: rgba(255,255,255,0.5); font-size: 0.85rem;">—</td>
                            <td style="padding: 8px; text-align: center;"><span style="background: rgba(45,91,255,0.3); color: #2D5BFF; padding: 2px 8px; border-radius: 3px; font-size: 0.75rem; font-weight: 600;">Backlog</span></td>
                        </tr>
                        <tr>
                            <td style="padding: 8px; color: #fff; font-weight: 500;">B4: LinkedIn EXPERIENCE Post</td>
                            <td style="padding: 8px; color: rgba(255,255,255,0.7);">Architect Network</td>
                            <td style="padding: 8px; color: #00D4FF; font-family: monospace; font-size: 0.85rem;">authority</td>
                            <td style="padding: 8px;">
                                <span style="background: rgba(45,91,255,0.2); color: #2D5BFF; padding: 2px 6px; border-radius: 3px; font-size: 0.75rem; margin-right: 4px;">recruit</span>
                                <span style="background: rgba(45,91,255,0.2); color: #2D5BFF; padding: 2px 6px; border-radius: 3px; font-size: 0.75rem; margin-right: 4px;">linkedin</span>
                                <span style="background: rgba(45,91,255,0.2); color: #2D5BFF; padding: 2px 6px; border-radius: 3px; font-size: 0.75rem;">architect</span>
                            </td>
                            <td style="padding: 8px; color: rgba(255,255,255,0.6); font-size: 0.85rem;">Recruitment post for AI builders</td>
                            <td style="padding: 8px; color: rgba(255,255,255,0.5); font-size: 0.85rem;">Tracking system</td>
                            <td style="padding: 8px; color: rgba(255,255,255,0.5); font-size: 0.85rem;">Vetting process needed first</td>
                            <td style="padding: 8px; text-align: center;"><span style="background: rgba(45,91,255,0.3); color: #2D5BFF; padding: 2px 8px; border-radius: 3px; font-size: 0.75rem; font-weight: 600;">Backlog</span></td>
                        </tr>
                        <tr>
                            <td style="padding: 8px; color: #fff; font-weight: 500;">B5: Engagement Tracking</td>
                            <td style="padding: 8px; color: rgba(255,255,255,0.7);">Architect Network</td>
                            <td style="padding: 8px; color: #00D4FF; font-family: monospace; font-size: 0.85rem;">operational</td>
                            <td style="padding: 8px;">
                                <span style="background: rgba(39,174,96,0.2); color: #27AE60; padding: 2px 6px; border-radius: 3px; font-size: 0.75rem; margin-right: 4px;">tracking</span>
                                <span style="background: rgba(45,91,255,0.2); color: #2D5BFF; padding: 2px 6px; border-radius: 3px; font-size: 0.75rem; margin-right: 4px;">architect</span>
                                <span style="background: rgba(245,166,35,0.2); color: #F5A623; padding: 2px 6px; border-radius: 3px; font-size: 0.75rem;">framework</span>
                            </td>
                            <td style="padding: 8px; color: rgba(255,255,255,0.6); font-size: 0.85rem;">Preferred provider scoring system</td>
                            <td style="padding: 8px; color: rgba(255,255,255,0.5); font-size: 0.85rem;">Solutions catalog</td>
                            <td style="padding: 8px; color: rgba(255,255,255,0.5); font-size: 0.85rem;">Need recruitment started first</td>
                            <td style="padding: 8px; text-align: center;"><span style="background: rgba(45,91,255,0.3); color: #2D5BFF; padding: 2px 8px; border-radius: 3px; font-size: 0.75rem; font-weight: 600;">Backlog</span></td>
                        </tr>
                        <tr>
                            <td style="padding: 8px; color: #fff; font-weight: 500;">B6: Crawler Subagent Setup</td>
                            <td style="padding: 8px; color: rgba(255,255,255,0.7);">Operational Capabilities</td>
                            <td style="padding: 8px; color: #00D4FF; font-family: monospace; font-size: 0.85rem;">operational</td>
                            <td style="padding: 8px;">
                                <span style="background: rgba(39,174,96,0.2); color: #27AE60; padding: 2px 6px; border-radius: 3px; font-size: 0.75rem; margin-right: 4px;">crawl4ai</span>
                                <span style="background: rgba(39,174,96,0.2); color: #27AE60; padding: 2px 6px; border-radius: 3px; font-size: 0.75rem; margin-right: 4px;">sub-agent</span>
                                <span style="background: rgba(245,166,35,0.2); color: #F5A623; padding: 2px 6px; border-radius: 3px; font-size: 0.75rem;">automation</span>
                            </td>
                            <td style="padding: 8px; color: rgba(255,255,255,0.6); font-size: 0.85rem;">Bulk web crawler with structured extraction</td>
                            <td style="padding: 8px; color: rgba(255,255,255,0.5); font-size: 0.85rem;">Lead research, competitive intel</td>
                            <td style="padding: 8px; color: rgba(255,255,255,0.5); font-size: 0.85rem;">crawl4ai already installed (818MB)</td>
                            <td style="padding: 8px; text-align: center;"><span style="background: rgba(39,174,96,0.3); color: #27AE60; padding: 2px 8px; border-radius: 3px; font-size: 0.75rem; font-weight: 600;">✅ Done</span></td>
                        </tr>
                        <tr>
                            <td style="padding: 8px; color: #fff; font-weight: 500;">B7: Proven Builds Database</td>
                            <td style="padding: 8px; color: rgba(255,255,255,0.7);">Architect Network</td>
                            <td style="padding: 8px; color: #00D4FF; font-family: monospace; font-size: 0.85rem;">100K</td>
                            <td style="padding: 8px;">
                                <span style="background: rgba(155,89,182,0.2); color: #BB8FCE; padding: 2px 6px; border-radius: 3px; font-size: 0.75rem; margin-right: 4px;">catalog</span>
                                <span style="background: rgba(45,91,255,0.2); color: #2D5BFF; padding: 2px 6px; border-radius: 3px; font-size: 0.75rem; margin-right: 4px;">architect</span>
                                <span style="background: rgba(245,166,35,0.2); color: #F5A623; padding: 2px 6px; border-radius: 3px; font-size: 0.75rem;">100K</span>
                            </td>
                            <td style="padding: 8px; color: rgba(255,255,255,0.6); font-size: 0.85rem;">Airtable catalog of vetted solutions</td>
                            <td style="padding: 8px; color: rgba(255,255,255,0.5); font-size: 0.85rem;">—</td>
                            <td style="padding: 8px; color: rgba(255,255,255,0.5); font-size: 0.85rem;">Tracking system needed first</td>
                            <td style="padding: 8px; text-align: center;"><span style="background: rgba(45,91,255,0.3); color: #2D5BFF; padding: 2px 8px; border-radius: 3px; font-size: 0.75rem; font-weight: 600;">Backlog</span></td>
                        </tr>
                        <tr>
                            <td style="padding: 8px; color: #fff; font-weight: 500;">B7: LinkedIn Scaling Arch</td>
                            <td style="padding: 8px; color: rgba(255,255,255,0.7);">Lead Enrichment</td>
                            <td style="padding: 8px; color: #00D4FF; font-family: monospace; font-size: 0.85rem;">operational</td>
                            <td style="padding: 8px;">
                                <span style="background: rgba(155,89,182,0.2); color: #BB8FCE; padding: 2px 6px; border-radius: 3px; font-size: 0.75rem; margin-right: 4px;">architecture</span>
                                <span style="background: rgba(45,91,255,0.2); color: #2D5BFF; padding: 2px 6px; border-radius: 3px; font-size: 0.75rem; margin-right: 4px;">linkedin</span>
                                <span style="background: rgba(245,166,35,0.2); color: #F5A623; padding: 2px 6px; border-radius: 3px; font-size: 0.75rem;">enrichment</span>
                            </td>
                            <td style="padding: 8px; color: rgba(255,255,255,0.6); font-size: 0.85rem;">Design architecture for customer volume</td>
                            <td style="padding: 8px; color: rgba(255,255,255,0.5); font-size: 0.85rem;">Pricing model</td>
                            <td style="padding: 8px; color: rgba(255,255,255,0.5); font-size: 0.85rem;">Need extraction validation first</td>
                            <td style="padding: 8px; text-align: center;"><span style="background: rgba(45,91,255,0.3); color: #2D5BFF; padding: 2px 8px; border-radius: 3px; font-size: 0.75rem; font-weight: 600;">Backlog</span></td>
                        </tr>
                        <tr>
                            <td style="padding: 8px; color: #fff; font-weight: 500;">B8: Finalize Pricing</td>
                            <td style="padding: 8px; color: rgba(255,255,255,0.7);">Lead Enrichment</td>
                            <td style="padding: 8px; color: #00D4FF; font-family: monospace; font-size: 0.85rem;">100K</td>
                            <td style="padding: 8px;">
                                <span style="background: rgba(245,166,35,0.2); color: #F5A623; padding: 2px 6px; border-radius: 3px; font-size: 0.75rem; margin-right: 4px;">pricing</span>
                                <span style="background: rgba(245,166,35,0.2); color: #F5A623; padding: 2px 6px; border-radius: 3px; font-size: 0.75rem; margin-right: 4px;">100K</span>
                                <span style="background: rgba(245,166,35,0.2); color: #F5A623; padding: 2px 6px; border-radius: 3px; font-size: 0.75rem;">revenue_critical</span>
                            </td>
                            <td style="padding: 8px; color: rgba(255,255,255,0.6); font-size: 0.85rem;">Target: $0.10-0.15/lead</td>
                            <td style="padding: 8px; color: rgba(255,255,255,0.5); font-size: 0.85rem;">—</td>
                            <td style="padding: 8px; color: rgba(255,255,255,0.5); font-size: 0.85rem;">Need architecture & documentation first</td>
                            <td style="padding: 8px; text-align: center;"><span style="background: rgba(45,91,255,0.3); color: #2D5BFF; padding: 2px 8px; border-radius: 3px; font-size: 0.75rem; font-weight: 600;">Backlog</span></td>
                        </tr>
                        <tr>
                            <td style="padding: 8px; color: #fff; font-weight: 500;">B9: Choose Brand Name</td>
                            <td style="padding: 8px; color: rgba(255,255,255,0.7);">Lead Enrichment</td>
                            <td style="padding: 8px; color: #00D4FF; font-family: monospace; font-size: 0.85rem;">authority</td>
                            <td style="padding: 8px;">
                                <span style="background: rgba(45,91,255,0.2); color: #2D5BFF; padding: 2px 6px; border-radius: 3px; font-size: 0.75rem; margin-right: 4px;">branding</span>
                                <span style="background: rgba(245,166,35,0.2); color: #F5A623; padding: 2px 6px; border-radius: 3px; font-size: 0.75rem; margin-right: 4px;">enrichment</span>
                                <span style="background: rgba(39,174,96,0.2); color: #27AE60; padding: 2px 6px; border-radius: 3px; font-size: 0.75rem;">authority</span>
                            </td>
                            <td style="padding: 8px; color: rgba(255,255,255,0.6); font-size: 0.85rem;">VERO? CASCADE? Final decision</td>
                            <td style="padding: 8px; color: rgba(255,255,255,0.5); font-size: 0.85rem;">—</td>
                            <td style="padding: 8px; color: rgba(255,255,255,0.5); font-size: 0.85rem;">—</td>
                            <td style="padding: 8px; text-align: center;"><span style="background: rgba(45,91,255,0.3); color: #2D5BFF; padding: 2px 8px; border-radius: 3px; font-size: 0.75rem; font-weight: 600;">Backlog</span></td>
                        </tr>
                    </tbody>
                </table>
            </div>
        </section>

        <!-- Footer -->
        <footer class="footer">
            <div class="footer-content">
                <button onclick="refreshData()" class="btn btn-refresh" id="refresh-btn">
                    🔄 Refresh Data
                </button>
                <span id="last-updated" class="last-updated">Last updated: {{ last_updated }}</span>
                <span id="client-info" class="client-info">Server: {{ server_time }} | IP: {{ client_ip }}</span>
            </div>
        </footer>
    </div>

    <!-- Toast Container -->
    <div id="toast-container" class="toast-container"></div>

    <script src="/static/dashboard.js"></script>
    <script>
      async function uploadChunked(inputId, statusId, endpoint) {
        const input = document.getElementById(inputId);
        const status = document.getElementById(statusId);
        if (!input || !input.files || input.files.length === 0) {
          if (status) status.textContent = 'Choose a file first';
          return;
        }

        const file = input.files[0];
        const chunkSize = 512 * 1024; // 512KB raw per request
        const totalChunks = Math.ceil(file.size / chunkSize);
        const uploadId = `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;

        if (status) status.textContent = `Uploading ${file.name}...`;

        for (let i = 0; i < totalChunks; i++) {
          const start = i * chunkSize;
          const end = Math.min(start + chunkSize, file.size);
          const chunk = file.slice(start, end);
          const buf = await chunk.arrayBuffer();
          const bytes = new Uint8Array(buf);

          let binary = '';
          const step = 0x8000;
          for (let j = 0; j < bytes.length; j += step) {
            binary += String.fromCharCode.apply(null, bytes.subarray(j, j + step));
          }
          const dataB64 = btoa(binary);

          const form = new FormData();
          form.append('upload_id', uploadId);
          form.append('filename', file.name);
          form.append('chunk_index', String(i));
          form.append('total_chunks', String(totalChunks));
          form.append('data_b64', dataB64);

          const res = await fetch(endpoint, { method: 'POST', body: form });
          if (!res.ok) {
            const txt = await res.text();
            throw new Error(`Chunk ${i + 1}/${totalChunks} failed: ${txt}`);
          }

          const pct = Math.round(((i + 1) / totalChunks) * 100);
          if (status) status.textContent = `Uploading ${file.name}... ${pct}%`;
        }

        if (status) status.textContent = `Upload complete: ${file.name}`;
      }

      async function uploadSongChunked() {
        return uploadChunked('song-upload-input', 'song-upload-status', '/upload-song-chunk');
      }

      async function uploadClipChunked() {
        return uploadChunked('clip-upload-input', 'clip-upload-status', '/upload-clip-chunk');
      }

      function setCutsStatus(kind, msg) {
        const s = document.getElementById('cuts-status');
        if (!s) return;
        s.textContent = msg;
        const styles = {
          idle: ['#93c5fd', 'rgba(59,130,246,0.15)', 'rgba(59,130,246,0.35)'],
          working: ['#fde68a', 'rgba(245,158,11,0.18)', 'rgba(245,158,11,0.35)'],
          ok: ['#86efac', 'rgba(34,197,94,0.18)', 'rgba(34,197,94,0.35)'],
          err: ['#fca5a5', 'rgba(239,68,68,0.18)', 'rgba(239,68,68,0.35)']
        };
        const c = styles[kind] || styles.idle;
        s.style.color = c[0];
        s.style.background = c[1];
        s.style.border = `1px solid ${c[2]}`;
      }

      function stampMeta(field, value) {
        const m = document.getElementById('cuts-meta');
        if (!m) return;
        const now = new Date().toLocaleTimeString();
        if (field === 'saved') {
          m.textContent = `Last saved: ${now} (${value}) | Last run: ${m.dataset.lastRun || '—'}`;
          m.dataset.lastSaved = `${now} (${value})`;
        } else {
          m.textContent = `Last saved: ${m.dataset.lastSaved || '—'} | Last run: ${now} (${value})`;
          m.dataset.lastRun = `${now} (${value})`;
        }
      }

      function setTail(text) {
        const t = document.getElementById('pipeline-tail');
        if (t) t.textContent = `Run output: ${text || '—'}`;
      }

      async function saveSegWeights() {
        const hook = Number(document.getElementById('w-hook')?.value || 22);
        const proof = Number(document.getElementById('w-proof')?.value || 48);
        const cta = Number(document.getElementById('w-cta')?.value || 30);
        const saveBtn = document.getElementById('save-cuts-btn');
        if (saveBtn) saveBtn.disabled = true;
        setCutsStatus('working', 'Saving...');

        const form = new FormData();
        form.append('hook', String(hook));
        form.append('proof', String(proof));
        form.append('cta', String(cta));

        const res = await fetch('/set-segmentation-weights', { method: 'POST', body: form });
        if (!res.ok) {
          const txt = await res.text();
          setCutsStatus('err', 'Save failed');
          setTail(txt.slice(0, 220));
          if (saveBtn) saveBtn.disabled = false;
          return;
        }
        const data = await res.json();
        const msg = `${Math.round(data.weights.hook*100)}/${Math.round(data.weights.proof*100)}/${Math.round(data.weights.cta*100)}`;
        setCutsStatus('ok', `Saved ${msg}`);
        stampMeta('saved', msg);
        setTail('Weights saved successfully');
        if (saveBtn) saveBtn.disabled = false;
      }

      function applySegPreset() {
        const preset = document.getElementById('cuts-preset')?.value || 'custom';
        const hp = document.getElementById('w-hook-panel');
        const pp = document.getElementById('w-proof-panel');
        const cp = document.getElementById('w-cta-panel');
        const map = {
          balanced: [25, 45, 30],
          aggressive: [20, 40, 40],
          education: [20, 60, 20],
          scrollstop: [35, 45, 20],
        };
        if (preset !== 'custom' && map[preset] && hp && pp && cp) {
          hp.value = String(map[preset][0]);
          pp.value = String(map[preset][1]);
          cp.value = String(map[preset][2]);
          setCutsStatus('idle', `Preset ${map[preset][0]}/${map[preset][1]}/${map[preset][2]} applied`);
          setTail('Preset applied. Click Save Cuts');
        } else {
          setCutsStatus('idle', 'Custom mode');
        }
      }

      async function saveSegWeightsPanel() {
        const hook = document.getElementById('w-hook-panel')?.value || '22';
        const proof = document.getElementById('w-proof-panel')?.value || '48';
        const cta = document.getElementById('w-cta-panel')?.value || '30';
        const a = document.getElementById('w-hook');
        const b = document.getElementById('w-proof');
        const c = document.getElementById('w-cta');
        if (a) a.value = hook;
        if (b) b.value = proof;
        if (c) c.value = cta;
        return saveSegWeights();
      }

      async function runPipelineNow() {
        const runBtn = document.getElementById('run-pipeline-btn');
        if (runBtn) runBtn.disabled = true;
        setCutsStatus('working', 'Running pipeline...');
        setTail('Pipeline started');

        const res = await fetch('/run-ugc-pipeline', { method: 'POST' });
        if (!res.ok) {
          const txt = await res.text();
          setCutsStatus('err', 'Run failed');
          setTail(txt.slice(0, 220));
          stampMeta('run', 'failed');
          if (runBtn) runBtn.disabled = false;
          return;
        }
        const data = await res.json();
        if (data.ok) {
          setCutsStatus('ok', 'Pipeline success');
          stampMeta('run', 'success');
        } else {
          setCutsStatus('err', 'Pipeline failed');
          stampMeta('run', 'failed');
        }
        const shortTail = (data.tail || '').split('\n').slice(-3).join(' | ');
        setTail(shortTail || data.summary || 'No output');
        if (runBtn) runBtn.disabled = false;
      }
    </script>
</body>
</html>'''

if __name__ == "__main__" and False:  # disabled duplicate
    pass

# ============== SHORTS/REELS QUEUE ==============

# Import shorts pipeline modules by explicit file path (avoid stdlib queue.py conflict)
import importlib.util as _importlib_util

_SHORTS_DIR = Path("/home/ubuntu/.openclaw/workspace/projects/ugc-video-pipeline/shorts")

def _load_shorts_module(name: str, file_name: str):
    spec = _importlib_util.spec_from_file_location(name, _SHORTS_DIR / file_name)
    module = _importlib_util.module_from_spec(spec)
    assert spec and spec.loader
    try:
        spec.loader.exec_module(module)
        return module
    except Exception as exc:
        print(f"Warning: failed to load shorts module {file_name}: {exc}")
        def _shorts_unavailable(*args, **kwargs):
            raise HTTPException(status_code=503, detail=f"Shorts module unavailable: {file_name}")
        if file_name == "queue.py":
            return type("ShortsQueueUnavailable", (), {
                "init_db": staticmethod(lambda *args, **kwargs: None),
                "get_queue": staticmethod(_shorts_unavailable),
                "get_stats": staticmethod(lambda *args, **kwargs: {"error": f"Shorts module unavailable: {file_name}"}),
                "get_item": staticmethod(_shorts_unavailable),
                "approve": staticmethod(_shorts_unavailable),
                "reject": staticmethod(_shorts_unavailable),
                "mark_posted": staticmethod(_shorts_unavailable),
                "update_status": staticmethod(_shorts_unavailable),
                "add_batch": staticmethod(_shorts_unavailable),
                "add_to_queue": staticmethod(_shorts_unavailable),
            })()
        if file_name == "batch_processor.py":
            return type("ShortsBatchUnavailable", (), {
                "load_hooks_from_file": staticmethod(_shorts_unavailable),
                "process_batch": staticmethod(_shorts_unavailable),
                "hooks_to_render_jobs": staticmethod(_shorts_unavailable),
                "export_all_ready": staticmethod(_shorts_unavailable),
            })()
        return type("ShortsExportUnavailable", (), {"export_package": staticmethod(_shorts_unavailable)})()

_shorts_queue_mod = _load_shorts_module("shorts_queue_mod", "queue.py")
_shorts_batch_mod = _load_shorts_module("shorts_batch_mod", "batch_processor.py")
_shorts_export_mod = _load_shorts_module("shorts_export_mod", "export_package.py")

_shorts_init_db = _shorts_queue_mod.init_db
_shorts_get_queue = _shorts_queue_mod.get_queue
_shorts_stats = _shorts_queue_mod.get_stats
_shorts_get_item = _shorts_queue_mod.get_item
_shorts_approve = _shorts_queue_mod.approve
_shorts_reject = _shorts_queue_mod.reject
_shorts_mark_posted = _shorts_queue_mod.mark_posted
_shorts_update_status = _shorts_queue_mod.update_status
_shorts_add_batch = _shorts_queue_mod.add_batch
_shorts_add_to_queue = _shorts_queue_mod.add_to_queue

load_hooks_from_file = _shorts_batch_mod.load_hooks_from_file
_shorts_process_batch = _shorts_batch_mod.process_batch
hooks_to_render_jobs = _shorts_batch_mod.hooks_to_render_jobs
_shorts_export_all = _shorts_batch_mod.export_all_ready

_shorts_export_pkg = _shorts_export_mod.export_package

# Init shorts DB on startup
_shorts_init_db()

@app.get("/shorts-queue", response_class=HTMLResponse)
async def shorts_queue_page(request: Request):
    """Dashboard page for Shorts/Reels publishing queue."""
    session_id = request.client.host
    if session_id not in authenticated_sessions:
        return RedirectResponse(url="/login")
    template_path = templates_dir / "shorts_queue.html"
    if template_path.exists():
        return HTMLResponse(content=template_path.read_text(encoding="utf-8"))
    return HTMLResponse(content="<h1>Shorts Queue page not found</h1>", status_code=404)

@app.get("/api/shorts/stats")
async def api_shorts_stats(request: Request):
    """Get shorts queue statistics."""
    session_id = request.client.host
    if session_id not in authenticated_sessions:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return JSONResponse(content=_shorts_stats())

@app.get("/api/shorts/queue")
async def api_shorts_queue(request: Request, status: Optional[str] = None):
    """List queue items, optionally filtered by status."""
    session_id = request.client.host
    if session_id not in authenticated_sessions:
        raise HTTPException(status_code=401, detail="Not authenticated")
    items = _shorts_get_queue(status)
    # Parse JSON fields for frontend
    for item in items:
        try:
            item["hashtags"] = json.loads(item.get("hashtags", "[]"))
        except:
            item["hashtags"] = []
        try:
            item["platforms"] = json.loads(item.get("platforms", "[]"))
        except:
            item["platforms"] = []
    return JSONResponse(content={"ok": True, "items": items, "count": len(items)})

@app.get("/api/shorts/item/{hook_id}")
async def api_shorts_get_item(request: Request, hook_id: str):
    """Get single queue item."""
    session_id = request.client.host
    if session_id not in authenticated_sessions:
        raise HTTPException(status_code=401, detail="Not authenticated")
    item = _shorts_get_item(hook_id)
    if not item:
        raise HTTPException(status_code=404, detail="Not found")
    try:
        item["hashtags"] = json.loads(item.get("hashtags", "[]"))
        item["platforms"] = json.loads(item.get("platforms", "[]"))
    except:
        pass
    return JSONResponse(content={"ok": True, "item": item})

@app.post("/api/shorts/add")
async def api_shorts_add(request: Request):
    """Add a new hook to the queue."""
    session_id = request.client.host
    if session_id not in authenticated_sessions:
        raise HTTPException(status_code=401, detail="Not authenticated")
    body = await request.json()
    result = _shorts_add_to_queue(
        hook_id=body.get("id", f"hook-{datetime.now().strftime('%H%M%S')}"),
        hook_text=body.get("hook", ""),
        script_text=body.get("script", ""),
        caption=body.get("caption", ""),
        hashtags=body.get("hashtags", []),
        platforms=body.get("platforms", ["tiktok", "instagram"]),
        target_duration_sec=body.get("target_duration_sec", 15),
    )
    return JSONResponse(content=result)

@app.post("/api/shorts/add-batch")
async def api_shorts_add_batch(request: Request):
    """Add multiple hooks from hooks.json to queue."""
    session_id = request.client.host
    if session_id not in authenticated_sessions:
        raise HTTPException(status_code=401, detail="Not authenticated")
    hooks = load_hooks_from_file()
    if not hooks:
        return JSONResponse(content={"ok": False, "error": "No hooks in hooks.json"}, status_code=400)
    result = _shorts_add_batch(hooks)
    return JSONResponse(content={"ok": True, **result})

@app.post("/api/shorts/process")
async def api_shorts_process(request: Request):
    """Process hooks into render jobs."""
    session_id = request.client.host
    if session_id not in authenticated_sessions:
        raise HTTPException(status_code=401, detail="Not authenticated")
    hooks = load_hooks_from_file()
    result = _shorts_process_batch(hooks)
    return JSONResponse(content=result)

@app.post("/api/shorts/approve/{hook_id}")
async def api_shorts_approve(request: Request, hook_id: str):
    """Human approval gate - approve rendered item."""
    session_id = request.client.host
    if session_id not in authenticated_sessions:
        raise HTTPException(status_code=401, detail="Not authenticated")
    body = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
    approved_by = body.get("approved_by", "matt")
    # Export package first
    item = _shorts_get_item(hook_id)
    if item:
        _shorts_export_pkg(hook_id, item)
    result = _shorts_approve(hook_id, approved_by)
    return JSONResponse(content=result)

@app.post("/api/shorts/reject/{hook_id}")
async def api_shorts_reject(request: Request, hook_id: str):
    """Reject rendered item, send back to failed/draft."""
    session_id = request.client.host
    if session_id not in authenticated_sessions:
        raise HTTPException(status_code=401, detail="Not authenticated")
    body = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
    reason = body.get("reason", "")
    result = _shorts_reject(hook_id, reason)
    return JSONResponse(content=result)

@app.post("/api/shorts/mark-posted/{hook_id}")
async def api_shorts_mark_posted(request: Request, hook_id: str):
    """Mark item as posted after manual posting."""
    session_id = request.client.host
    if session_id not in authenticated_sessions:
        raise HTTPException(status_code=401, detail="Not authenticated")
    body = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
    platform = body.get("platform", "")
    result = _shorts_mark_posted(hook_id, platform)
    return JSONResponse(content=result)

@app.post("/api/shorts/export/{hook_id}")
async def api_shorts_export(request: Request, hook_id: str):
    """Export ready-to-publish package for an item."""
    session_id = request.client.host
    if session_id not in authenticated_sessions:
        raise HTTPException(status_code=401, detail="Not authenticated")
    item = _shorts_get_item(hook_id)
    if not item:
        raise HTTPException(status_code=404, detail="Not found")
    result = _shorts_export_pkg(hook_id, item)
    return JSONResponse(content=result)

@app.post("/api/shorts/export-all")
async def api_shorts_export_all(request: Request):
    """Export packages for all ready-to-post items."""
    session_id = request.client.host
    if session_id not in authenticated_sessions:
        raise HTTPException(status_code=401, detail="Not authenticated")
    results = _shorts_export_all()
    return JSONResponse(content={"ok": True, "exported": len(results), "results": results})

@app.get("/api/shorts/hooks-file")
async def api_shorts_hooks_file(request: Request):
    """Get hooks from hooks.json file."""
    session_id = request.client.host
    if session_id not in authenticated_sessions:
        raise HTTPException(status_code=401, detail="Not authenticated")
    hooks = load_hooks_from_file()
    return JSONResponse(content={"ok": True, "hooks": hooks, "count": len(hooks)})


@app.post("/api/generate-card-v2")
async def generate_card_v2(
    name: str = Form(...),
    profile_name: str = Form(...),
    scores_json: str = Form(...),
    body: str = Form(default=""),
    gender: str = Form("male"),
    favorite_color: str = Form("blue"),
    ethnicity: str = Form("fair"),
    hair_color: str = Form("na"),
    top_name_style: str = Form("v2"),
    top_name_font_weight: str = Form("semibold"),
    photo: UploadFile = File(None),
):
    """Force final framed + text/name overlay output via in-process generator."""
    try:
        print(f"[TRACE-8080] /api/generate-card-v2 receive body={repr(body)} len={len(body) if isinstance(body, str) else 'N/A'}")
        try:
            scores = json.loads(scores_json)
        except Exception:
            scores = []

        photo_bytes = await photo.read() if photo else None

        card_bytes, gen_source, gen_reason, face_swap_status = generate_hero_card_with_meta(
            name=name,
            profile_name=profile_name,
            scores=scores,
            photo_bytes=photo_bytes,
            gender=gender,
            favorite_color=favorite_color,
            ethnicity=ethnicity,
            hair_color=hair_color,
            top_name_style=top_name_style,
            top_name_font_weight=top_name_font_weight,
            body_text=body,
        )

        slug = _build_card_slug(name)
        card_path = cards_static_dir / f"{slug}.png"
        card_path.write_bytes(card_bytes)
        _store_card_slug_meta(slug, name)
        card_url = f"{CARD_SHARE_BASE_URL}/static/cards/{slug}.png"
        share_url = f"{CARD_SHARE_BASE_URL}/card/{slug}"

        return Response(
            content=card_bytes,
            media_type="image/png",
            headers={
                "X-Generation-Source": gen_source,
                "X-Generation-Reason": gen_reason,
                "X-Face-Swap-Status": face_swap_status,
                "X-Card-Route": "generate-card-v2",
                "X-Card-Slug": slug,
                "X-Card-Url": card_url,
                "X-Card-Share-Url": share_url,
            },
        )
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/generate-card")
async def generate_card_proxy(
    request: Request,
    name: str = Form(...),
    profile_name: str = Form(...),
    scores_json: str = Form(...),
    gender: str = Form("male"),
    favorite_color: str = Form("blue"),
    ethnicity: str = Form("fair"),
    hair_color: str = Form("na"),
    top_name_style: str = Form("v2"),
    top_name_font_weight: str = Form("semibold"),
    photo: UploadFile = File(None),
):
    """Proxy request to patterns backend for card generation"""
    try:
        # Forward request to patterns backend
        import requests
        import io
        
        # Locked to patterns backend on 8081 (864x1216 no-frame generation + final frame overlay)
        url = "http://127.0.0.1:8081/api/generate-card"
        data = {
            "name": name,
            "profile_name": profile_name,
            "scores_json": scores_json,
            "gender": gender,
            "favorite_color": favorite_color,
            "ethnicity": ethnicity,
            "hair_color": hair_color,
            "top_name_style": top_name_style,
            "top_name_font_weight": top_name_font_weight,
        }
        
        files = {}
        if photo:
            files["photo"] = (photo.filename, await photo.read())
        
        response = requests.post(url, data=data, files=files, timeout=120)
        
        if response.status_code == 200:
            slug = _build_card_slug(name)
            card_path = cards_static_dir / f"{slug}.png"
            card_path.write_bytes(response.content)
            _store_card_slug_meta(slug, name)
            card_url = f"{CARD_SHARE_BASE_URL}/static/cards/{slug}.png"
            share_url = f"{CARD_SHARE_BASE_URL}/card/{slug}"

            return Response(
                content=response.content,
                media_type="image/png",
                headers={
                    "X-Generation-Source": response.headers.get("X-Generation-Source", "unknown"),
                    "X-Generation-Reason": response.headers.get("X-Generation-Reason", "unknown"),
                    "X-Face-Swap-Status": response.headers.get("X-Face-Swap-Status", "no_photo"),
                    "X-Card-Slug": slug,
                    "X-Card-Url": card_url,
                    "X-Card-Share-Url": share_url,
                }
            )
        else:
            return JSONResponse({"error": "Backend failed"}, status_code=500)
            
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
@app.get("/pr-monitor-1", response_class=HTMLResponse)
async def pr_monitor_1_review_page():
    return FileResponse(str(static_dir / "pr_monitor_1.html"))

@app.get("/pr-monitor-dashboard", response_class=HTMLResponse)
async def pr_monitor_dashboard():
    return FileResponse(str(static_dir / "pr_monitor_dashboard.html"))

@app.get("/pr-monitor-project", response_class=HTMLResponse)
async def pr_monitor_project():
    return FileResponse(str(static_dir / "pr_monitor_project.html"))

@app.get("/pr-monitor-alerts", response_class=HTMLResponse)
async def pr_monitor_alerts():
    return FileResponse(str(static_dir / "pr_monitor_alerts.html"))


@app.post("/api/pr-monitor-1/sources/save")
async def pr_monitor_1_sources_save(
    request: Request,
    source_set_name: str = Form(""),
    urls_text: str = Form(""),
):
    _reject_json_for_form_endpoint(request)
    name = (source_set_name or "").strip() or "Unnamed source set"
    raw_urls = [u.strip() for u in (urls_text or "").splitlines() if u.strip()]
    urls = [u for u in raw_urls if u.lower().startswith(("http://", "https://"))]
    unique_urls = list(dict.fromkeys(urls))
    if not unique_urls:
        raise HTTPException(status_code=400, detail="No valid URLs to save.")

    out_dir = get_pr_monitor_settings().source_sets_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", name).strip("_") or "source_set"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = out_dir / f"{slug}_{stamp}.txt"
    out_path.write_text("\n".join(unique_urls) + "\n", encoding="utf-8")

    return {"ok": True, "source_set_name": name, "saved_urls": len(unique_urls), "path": str(out_path)}


@app.post("/api/pr-monitor-1/sources/upload-csv")
async def pr_monitor_1_sources_upload_csv(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only .csv files are supported.")

    content = (await file.read()).decode("utf-8", errors="replace")
    if not content.strip():
        raise HTTPException(status_code=400, detail="CSV is empty.")

    # Try delimiter sniffing first (comma/semicolon/tab), fallback to comma reader
    try:
        dialect = csv.Sniffer().sniff(content[:4096], delimiters=",;\t")
        reader = csv.reader(content.splitlines(), dialect)
    except Exception:
        reader = csv.reader(content.splitlines())

    rows = list(reader)
    if not rows:
        raise HTTPException(status_code=400, detail="CSV is empty.")

    # Treat first row as header only if it does not contain any URL-like value
    first_row_has_url = any(((c or "").strip().strip('"\'').lower().startswith(("http://", "https://"))) for c in rows[0])
    data_rows = rows if first_row_has_url else rows[1:]
    urls = []
    for r in data_rows:
        if not r:
            continue
        # Scan every cell in the row (handles: col1 format, comma-list single row, mixed layouts)
        for cell in r:
            c = (cell or "").strip().strip('"\'')
            if c.lower().startswith(("http://", "https://")):
                urls.append(c)

    unique_urls = list(dict.fromkeys(urls))
    if not unique_urls:
        raise HTTPException(status_code=400, detail="No valid URLs found in CSV. Expected at least one http(s) URL.")

    return {"ok": True, "url_count": len(unique_urls), "urls": unique_urls}


US_STATES_ALPHA = [
    {"code": "AL", "name": "Alabama"}, {"code": "AK", "name": "Alaska"}, {"code": "AZ", "name": "Arizona"},
    {"code": "AR", "name": "Arkansas"}, {"code": "CA", "name": "California"}, {"code": "CO", "name": "Colorado"},
    {"code": "CT", "name": "Connecticut"}, {"code": "DE", "name": "Delaware"}, {"code": "FL", "name": "Florida"},
    {"code": "GA", "name": "Georgia"}, {"code": "HI", "name": "Hawaii"}, {"code": "ID", "name": "Idaho"},
    {"code": "IL", "name": "Illinois"}, {"code": "IN", "name": "Indiana"}, {"code": "IA", "name": "Iowa"},
    {"code": "KS", "name": "Kansas"}, {"code": "KY", "name": "Kentucky"}, {"code": "LA", "name": "Louisiana"},
    {"code": "ME", "name": "Maine"}, {"code": "MD", "name": "Maryland"}, {"code": "MA", "name": "Massachusetts"},
    {"code": "MI", "name": "Michigan"}, {"code": "MN", "name": "Minnesota"}, {"code": "MS", "name": "Mississippi"},
    {"code": "MO", "name": "Missouri"}, {"code": "MT", "name": "Montana"}, {"code": "NE", "name": "Nebraska"},
    {"code": "NV", "name": "Nevada"}, {"code": "NH", "name": "New Hampshire"}, {"code": "NJ", "name": "New Jersey"},
    {"code": "NM", "name": "New Mexico"}, {"code": "NY", "name": "New York"}, {"code": "NC", "name": "North Carolina"},
    {"code": "ND", "name": "North Dakota"}, {"code": "OH", "name": "Ohio"}, {"code": "OK", "name": "Oklahoma"},
    {"code": "OR", "name": "Oregon"}, {"code": "PA", "name": "Pennsylvania"}, {"code": "RI", "name": "Rhode Island"},
    {"code": "SC", "name": "South Carolina"}, {"code": "SD", "name": "South Dakota"}, {"code": "TN", "name": "Tennessee"},
    {"code": "TX", "name": "Texas"}, {"code": "UT", "name": "Utah"}, {"code": "VT", "name": "Vermont"},
    {"code": "VA", "name": "Virginia"}, {"code": "WA", "name": "Washington"}, {"code": "WV", "name": "West Virginia"},
    {"code": "WI", "name": "Wisconsin"}, {"code": "WY", "name": "Wyoming"},
]

US_STATE_NAME_BY_CODE = {s["code"].upper(): s["name"] for s in US_STATES_ALPHA}


def _geo_fallback_city_search(country: str, state: str, q: str, limit: int):
    cc = (country or "").strip().upper()
    st = (state or "").strip().upper()
    query = (q or "").strip()
    if not cc:
        return []

    # Nominatim fallback (used only when GeoNames is unavailable/fails)
    # Kept lightweight to avoid hard failures in UI when primary provider is down.
    state_name = US_STATE_NAME_BY_CODE.get(st, st) if cc == "US" else st
    parts = []
    if query:
        parts.append(query)
    if state_name:
        parts.append(state_name)
    parts.append(cc)
    search_q = ", ".join([p for p in parts if p])
    if not search_q:
        return []

    params = {
        "q": search_q,
        "format": "jsonv2",
        "addressdetails": 1,
        "limit": max(1, min(int(limit or 20), 50)),
    }
    headers = {"User-Agent": "openclaw-pr-monitor-1/1.0"}
    r = requests.get("https://nominatim.openstreetmap.org/search", params=params, headers=headers, timeout=12)
    r.raise_for_status()
    rows = r.json() or []
    out = []
    seen = set()
    for row in rows:
        addr = (row or {}).get("address") or {}
        city = (
            addr.get("city")
            or addr.get("town")
            or addr.get("village")
            or addr.get("municipality")
            or ""
        ).strip()
        country_code = str(addr.get("country_code") or "").upper()
        state_text = (addr.get("state_code") or addr.get("state") or "").strip()
        if not city:
            display = str((row or {}).get("display_name") or "")
            city = display.split(",")[0].strip() if display else ""
        if not city or (country_code and country_code != cc):
            continue
        if cc == "US" and st and state_text:
            st_norm = state_text.upper()
            if st_norm not in {st, US_STATE_NAME_BY_CODE.get(st, "").upper()}:
                continue
        key = (city.lower(), state_text.upper(), cc)
        if key in seen:
            continue
        seen.add(key)
        out.append({"name": city, "state": st or state_text, "country": cc})
    return out


@app.get("/api/pr-monitor-1/geo/countries")
async def pr_monitor_1_geo_countries():
    fallback = [
        {"code": "US", "name": "United States"},
        {"code": "CA", "name": "Canada"},
        {"code": "AU", "name": "Australia"},
        {"code": "GB", "name": "United Kingdom"},
        {"code": "DE", "name": "Germany"},
        {"code": "IN", "name": "India"},
    ]
    try:
        r = requests.get(
            "https://restcountries.com/v3.1/all?fields=name,cca2",
            timeout=12,
        )
        r.raise_for_status()
        rows = r.json() or []
        out = []
        for row in rows:
            code = str((row or {}).get("cca2") or "").upper()
            name = str((((row or {}).get("name") or {}).get("common")) or "").strip()
            if code and name:
                out.append({"code": code, "name": name})
        dedup = {}
        for c in out:
            dedup[c["code"]] = c
        countries = sorted(dedup.values(), key=lambda x: x["name"].lower())
    except Exception:
        countries = fallback
    return {"ok": True, "countries": countries, "default_country": "US"}


@app.get("/api/pr-monitor-1/geo/states")
async def pr_monitor_1_geo_states(country: str = Query("US")):
    cc = (country or "US").strip().upper()
    if cc == "US":
        return {"ok": True, "states": US_STATES_ALPHA}
    if cc == "CA":
        ca = [
            {"code": "AB", "name": "Alberta"}, {"code": "BC", "name": "British Columbia"},
            {"code": "MB", "name": "Manitoba"}, {"code": "NB", "name": "New Brunswick"},
            {"code": "NL", "name": "Newfoundland and Labrador"}, {"code": "NS", "name": "Nova Scotia"},
            {"code": "ON", "name": "Ontario"}, {"code": "PE", "name": "Prince Edward Island"},
            {"code": "QC", "name": "Quebec"}, {"code": "SK", "name": "Saskatchewan"},
        ]
        return {"ok": True, "states": ca}
    if cc == "AU":
        au = [
            {"code": "ACT", "name": "Australian Capital Territory"}, {"code": "NSW", "name": "New South Wales"},
            {"code": "NT", "name": "Northern Territory"}, {"code": "QLD", "name": "Queensland"},
            {"code": "SA", "name": "South Australia"}, {"code": "TAS", "name": "Tasmania"},
            {"code": "VIC", "name": "Victoria"}, {"code": "WA", "name": "Western Australia"},
        ]
        return {"ok": True, "states": au}
    return {"ok": True, "states": []}


@app.get("/api/pr-monitor-1/geo/cities")
async def pr_monitor_1_geo_cities(
    country: str = Query(...),
    state: str = Query(""),
    q: str = Query(""),
    limit: int = Query(20),
    min_population: int = Query(0),
):
    username = os.getenv("GEONAMES_USERNAME", "demo").strip() or "demo"
    params = {
        "username": username,
        "country": (country or "").strip().upper(),
        "featureClass": "P",
        "maxRows": max(1, min(int(limit or 20), 50)),
        "orderby": "population",
    }
    state_val = (state or "").strip()
    if state_val:
        params["adminCode1"] = state_val
    query = (q or "").strip()
    if query:
        params["name_startsWith"] = query
    try:
        r = requests.get("https://api.geonames.org/searchJSON", params=params, timeout=12)
        r.raise_for_status()
        data = r.json() or {}
        rows = data.get("geonames") or []
        seen = set()
        out = []
        min_pop = max(0, int(min_population or 0))
        state_req = state_val.upper() if state_val else ""
        for row in rows:
            city = str((row or {}).get("name") or "").strip()
            admin = str((row or {}).get("adminCode1") or "").strip()
            country_code = str((row or {}).get("countryCode") or "").strip().upper()
            population = int((row or {}).get("population") or 0)
            if not city:
                continue
            if state_req and admin.upper() != state_req:
                continue
            if population < min_pop:
                continue
            key = (city.lower(), admin.upper(), country_code)
            if key in seen:
                continue
            seen.add(key)
            out.append({"name": city, "state": admin, "country": country_code, "population": population})
        return {"ok": True, "cities": out}
    except Exception as e:
        try:
            out = _geo_fallback_city_search(
                country=params["country"],
                state=state_val,
                q=query,
                limit=params["maxRows"],
            )
            return {"ok": True, "cities": out, "provider": "nominatim_fallback", "warning": str(e)}
        except Exception as e2:
            return {"ok": False, "cities": [], "error": f"{e}; fallback_failed={e2}"}


@app.get("/api/pr-monitor-1/geo/validate-city")
async def pr_monitor_1_geo_validate_city(
    country: str = Query(...),
    state: str = Query(""),
    city: str = Query(...),
):
    city_val = (city or "").strip()
    if not city_val:
        raise HTTPException(status_code=400, detail="city is required")
    username = os.getenv("GEONAMES_USERNAME", "demo").strip() or "demo"
    params = {
        "username": username,
        "country": (country or "").strip().upper(),
        "featureClass": "P",
        "name_equals": city_val,
        "maxRows": 20,
    }
    state_val = (state or "").strip()
    if state_val:
        params["adminCode1"] = state_val
    def _is_city_match(rows):
        normalized = city_val.lower()
        for row in rows:
            row_city = str((row or {}).get("name") or "").strip().lower()
            row_state = str((row or {}).get("state") or (row or {}).get("adminCode1") or "").strip().upper()
            row_country = str((row or {}).get("country") or (row or {}).get("countryCode") or "").strip().upper()
            if row_city == normalized and row_country == params["country"]:
                if not state_val or row_state in {state_val.upper(), US_STATE_NAME_BY_CODE.get(state_val.upper(), "").upper()}:
                    return True
        return False

    try:
        r = requests.get("https://api.geonames.org/searchJSON", params=params, timeout=12)
        r.raise_for_status()
        data = r.json() or {}
        rows = data.get("geonames") or []
        rows_norm = [
            {
                "name": str((row or {}).get("name") or "").strip(),
                "state": str((row or {}).get("adminCode1") or "").strip(),
                "country": str((row or {}).get("countryCode") or "").strip().upper(),
            }
            for row in rows
        ]
        return {"ok": True, "valid": _is_city_match(rows_norm), "provider": "geonames"}
    except Exception as e:
        try:
            rows = _geo_fallback_city_search(
                country=params["country"],
                state=state_val,
                q=city_val,
                limit=20,
            )
            return {"ok": True, "valid": _is_city_match(rows), "provider": "nominatim_fallback", "warning": str(e)}
        except Exception as e2:
            return {"ok": False, "valid": False, "error": f"{e}; fallback_failed={e2}"}


@app.get("/api/pr-monitor-1/preferences")
async def pr_monitor_1_get_preferences():
    pref_dir = get_pr_monitor_settings().runtime_root
    pref_dir.mkdir(parents=True, exist_ok=True)
    pref_path = pref_dir / "preferences.json"
    default = {
        "market": "",
        "record_type": "both",
        "conference_country_scope": "US",
        "conference_countries": [],
        "conference_region_scope": "US",
        "conference_us_states": [],
        "conference_geo_preference": "",
        "award_geo_preference": "",
    }
    if not pref_path.exists():
        return {"ok": True, "preferences": default}
    try:
        data = json.loads(pref_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            data = default
    except Exception:
        data = default
    for k, v in default.items():
        data.setdefault(k, v)
    return {"ok": True, "preferences": data}


@app.post("/api/pr-monitor-1/preferences")
async def pr_monitor_1_save_preferences(payload: dict):
    pref_dir = get_pr_monitor_settings().runtime_root
    pref_dir.mkdir(parents=True, exist_ok=True)
    pref_path = pref_dir / "preferences.json"
    data = {
        "market": str(payload.get("market") or "").strip(),
        "record_type": str(payload.get("record_type") or "both").strip() or "both",
        "conference_country_scope": str(payload.get("conference_country_scope") or "US").strip().upper() or "US",
        "conference_countries": payload.get("conference_countries") if isinstance(payload.get("conference_countries"), list) else [],
        "conference_region_scope": str(payload.get("conference_region_scope") or "US").strip().upper() or "US",
        "conference_us_states": payload.get("conference_us_states") if isinstance(payload.get("conference_us_states"), list) else [],
        "conference_geo_preference": str(payload.get("conference_geo_preference") or "").strip(),
        "award_geo_preference": str(payload.get("award_geo_preference") or "").strip(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    pref_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return {"ok": True, "path": str(pref_path), "preferences": data}


@app.post("/api/pr-monitor-1/prompt-pack")
async def pr_monitor_1_prompt_pack(payload: dict):
    market = str(payload.get("market_focus") or payload.get("market") or "").strip()
    record_type = str(payload.get("record_type") or "both").strip() or "both"
    conf_country_scope = str(payload.get("conference_country_scope") or "").strip().upper()
    conf_countries_raw = payload.get("conference_countries") or []
    conf_region_scope = str(payload.get("conference_region_scope") or "").strip().upper()
    conf_states_raw = payload.get("conference_us_states") or []
    award_geo = str(payload.get("award_geo_preference") or "").strip()
    # Keep date_window for backward compatibility in payload/storage, but do not
    # constrain discovery prompts with it.
    date_window = str(payload.get("date_window") or "").strip() or "next 12 months"
    priority_mode = str(payload.get("priority_mode") or "").strip() or "balanced"
    include_unknown_geo = payload.get("include_unknown_geo")
    if include_unknown_geo is None:
        include_unknown_geo = True
    include_unknown_geo = bool(include_unknown_geo)

    # Backward-compat mapping from legacy conference geo preference string.
    legacy_conf_geo = str(payload.get("conference_geo_preference") or "").strip()
    if not conf_country_scope and conf_region_scope:
        conf_country_scope = conf_region_scope if conf_region_scope in {"US", "INTERNATIONAL"} else "US"

    if not conf_country_scope:
        if legacy_conf_geo:
            legacy_lower = legacy_conf_geo.lower()
            if "country: united states" in legacy_lower or "country: us" in legacy_lower:
                conf_country_scope = "US"
                # Best-effort parse state from "state: X | ..."
                state_part = ""
                if "state:" in legacy_lower:
                    try:
                        state_part = legacy_conf_geo.split("state:", 1)[1].split("|", 1)[0].strip()
                    except Exception:
                        state_part = ""
                conf_states_raw = [state_part] if state_part else []
            else:
                conf_country_scope = "INTERNATIONAL"
                conf_states_raw = []
        else:
            conf_country_scope = "US"

    if isinstance(conf_states_raw, str):
        conf_states = [s.strip() for s in conf_states_raw.split(",") if s.strip()]
    elif isinstance(conf_states_raw, list):
        conf_states = [str(s).strip() for s in conf_states_raw if str(s).strip()]
    else:
        conf_states = []

    # Normalize state list to uppercase abbreviations only when already abbreviation-like.
    conf_states = [s.upper() if len(s) <= 3 else s for s in conf_states]
    conf_states = list(dict.fromkeys(conf_states))
    us_state_codes = {
        "AL","AK","AZ","AR","CA","CO","CT","DE","FL","GA","HI","ID","IL","IN","IA","KS","KY","LA","ME","MD",
        "MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ","NM","NY","NC","ND","OH","OK","OR","PA","RI","SC",
        "SD","TN","TX","UT","VT","VA","WA","WV","WI","WY",
    }
    contiguous_us_state_codes = us_state_codes - {"AK", "HI"}
    conf_states_upper = {s.upper() for s in conf_states}
    us_all_states_selected = conf_states_upper == us_state_codes
    us_contiguous_states_selected = conf_states_upper == contiguous_us_state_codes

    if isinstance(conf_countries_raw, str):
        conf_countries = [s.strip().upper() for s in conf_countries_raw.split(",") if s.strip()]
    elif isinstance(conf_countries_raw, list):
        conf_countries = [str(s).strip().upper() for s in conf_countries_raw if str(s).strip()]
    else:
        conf_countries = []
    conf_countries = list(dict.fromkeys(conf_countries))

    if not market:
        raise HTTPException(status_code=400, detail="market_focus is required")
    if conf_country_scope not in {"US", "INTERNATIONAL", "SPECIFIC_COUNTRIES"}:
        raise HTTPException(status_code=400, detail="conference_country_scope must be US, INTERNATIONAL, or SPECIFIC_COUNTRIES")
    if conf_country_scope != "US" and conf_states:
        raise HTTPException(status_code=400, detail="conference_us_states is only valid when conference_country_scope=US")
    if conf_country_scope == "INTERNATIONAL" and conf_countries:
        raise HTTPException(status_code=400, detail="conference_countries is not allowed when conference_country_scope=INTERNATIONAL")
    if conf_country_scope == "US" and conf_countries:
        raise HTTPException(status_code=400, detail="conference_countries is not allowed when conference_country_scope=US")
    if conf_country_scope == "SPECIFIC_COUNTRIES" and not conf_countries:
        raise HTTPException(status_code=400, detail="conference_countries is required when conference_country_scope=SPECIFIC_COUNTRIES")
    if conf_country_scope == "SPECIFIC_COUNTRIES" and "US" in conf_countries:
        raise HTTPException(status_code=400, detail="US is not allowed when conference_country_scope=SPECIFIC_COUNTRIES")
    if len(award_geo) < 3:
        raise HTTPException(status_code=400, detail="award_geo_preference must be at least 3 characters")

    if conf_country_scope == "US":
        if us_all_states_selected:
            conference_targeting_clause = "Conference targeting scope: US only. Include all US states."
        elif us_contiguous_states_selected:
            conference_targeting_clause = "Conference targeting scope: US only. Include contiguous United States (exclude AK, HI)."
        elif conf_states:
            conference_targeting_clause = f"Conference targeting scope: US only. Restrict to these states: {', '.join(conf_states)}."
        else:
            conference_targeting_clause = "Conference targeting scope: US only. No state filter selected, so include all US states."
    elif conf_country_scope == "SPECIFIC_COUNTRIES":
        conference_targeting_clause = f"Conference targeting scope: Specific countries only. Restrict to these countries: {', '.join(conf_countries)}. Exclude US."
    else:
        conference_targeting_clause = "Conference targeting scope: INTERNATIONAL (global). Include both non-US and US conferences."

    # Keep legacy field populated for transitional consumers and history readability.
    if conf_country_scope == "US":
        if us_all_states_selected or not conf_states:
            legacy_states = "ALL"
        elif us_contiguous_states_selected:
            legacy_states = "CONTIGUOUS_US"
        else:
            legacy_states = ", ".join(conf_states)
        conf_geo_legacy = f"region_scope: US | states: {legacy_states}"
    elif conf_country_scope == "SPECIFIC_COUNTRIES":
        conf_geo_legacy = f"region_scope: SPECIFIC_COUNTRIES | countries: {', '.join(conf_countries)}"
    else:
        conf_geo_legacy = "region_scope: INTERNATIONAL"

    prompts = {
        "conference_discovery": (
            f"Identify high-relevance conference sources for market: {market}. "
            f"{conference_targeting_clause} "
            "Return canonical URLs only where possible. Include rationale, geo evidence snippet, and confidence note for each accepted source. "
            "Reject weak directory duplicates when a canonical source exists."
        ),
        "award_discovery": (
            f"Identify high-relevance award opportunities for market: {market}. "
            f"Prioritize geography by: {award_geo}. "
            f"Priority mode: {priority_mode}. "
            "Return application/source URLs and deadlines when available. Include rationale, geo evidence snippet, and confidence note for each accepted source. "
            "Reject weak directory duplicates when a canonical source exists."
        ),
        "url_validation": (
            "Validate each candidate URL for relevance, canonical quality, and freshness. "
            "Mark APPROVE, HOLD, or REJECT with explicit reason."
        ),
        "geo_enrichment": (
            "Extract or verify geo_city, geo_state, geo_country from page content or trusted linked pages. "
            "Set geo_confidence_status as GEO_CONFIRMED, GEO_PARTIAL, or GEO_UNKNOWN. "
            "Parse and output the effective geo hierarchy rank as city > state > domestic > international > unknown."
        ),
        "output_standardization": (
            "Return records in standardized schema with deterministic fields and explicit status tags. "
            "Include decision_status and decision_reason. "
            "Unknown geo rows must remain visible and tagged; never silently drop them."
        ),
    }

    prompt_pack_id = f"pp_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    schema_version = "step1_prompt_pack_v1"
    prompt_pack = {
        "prompt_pack_id": prompt_pack_id,
        "schema_version": schema_version,
        "market_focus": market,
        "record_type": record_type,
        "conference_country_scope": conf_country_scope,
        "conference_countries": conf_countries,
        "conference_region_scope": conf_country_scope if conf_country_scope in {"US", "INTERNATIONAL"} else "INTERNATIONAL",
        "conference_us_states": conf_states,
        "conference_geo_preference": conf_geo_legacy,
        "award_geo_preference": award_geo,
        "date_window": date_window,
        "priority_mode": priority_mode,
        "include_unknown_geo": include_unknown_geo,
        "prompts": prompts,
        "defaults_applied": ["priority_mode", "include_unknown_geo"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    out_dir = get_pr_monitor_settings().runtime_root
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = out_dir / f"prompt_pack_{stamp}.json"
    out_path.write_text(json.dumps(prompt_pack, indent=2), encoding="utf-8")

    pref_path = out_dir / "preferences.json"
    pref_path.write_text(
        json.dumps(
            {
                "market": market,
                "record_type": record_type,
                "conference_country_scope": conf_country_scope,
                "conference_countries": conf_countries,
                "conference_region_scope": conf_country_scope if conf_country_scope in {"US", "INTERNATIONAL"} else "INTERNATIONAL",
                "conference_us_states": conf_states,
                "conference_geo_preference": conf_geo_legacy,
                "award_geo_preference": award_geo,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    # Backward-compatible top-level keys retained for current UI consumers.
    return {
        "ok": True,
        "path": str(out_path),
        "prompt_pack": prompt_pack,
        "prompt_pack_id": prompt_pack_id,
        "schema_version": schema_version,
        "prompts": prompts,
        "defaults_applied": prompt_pack["defaults_applied"],
    }


@app.post("/api/pr-monitor-1/run")
async def pr_monitor_1_run(
    mode: str = Form("smart_hybrid"),
    min_confidence: float = Form(0.85),
    urls_text: str = Form(""),
    allow_default_csv: str = Form("false"),
    skip_same_day: str = Form("true"),
):
    if mode not in {"full_ai", "smart_hybrid"}:
        raise HTTPException(status_code=400, detail="Invalid mode")

    raw_urls = [u.strip() for u in (urls_text or "").splitlines() if u.strip()]
    urls = [u for u in raw_urls if u.lower().startswith(("http://", "https://"))]

    script = str(get_pr_monitor_settings().legacy_runner_path)
    cmd = ["python3", script, "--db", str(get_pr_monitor_settings().db_path), "--mode", mode, "--min-confidence", str(min_confidence)]
    if str(skip_same_day).lower() == "true":
        cmd.append("--skip-same-day")

    import_csv_path = None
    if urls:
        import tempfile
        from urllib.parse import urlparse
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix="_pr_monitor_1_input.csv", delete=False, encoding="utf-8", newline="")
        fieldnames = [
            'conf_page_url','conf_name','conf_name_found','conf_dates','conf_dates_found','conf_location','conf_location_found',
            'conf_description','conf_description_found','conf_page_cost','conf_page_paths_tried','contact_page_url','contact_name',
            'contact_name_found','contact_email','contact_email_found','contact_phone','contact_phone_found','contact_org',
            'contact_org_found','contact_page_cost','contact_paths_tried','cfp_page_url','cfp_status','cfp_status_found',
            'cfp_deadline','cfp_deadline_found','cfp_opens','cfp_opens_found','cfp_sub_requirements','cfp_sub_requirements_found',
            'cfp_page_cost','sub_page_url','sub_link','sub_link_found','sub_portal_name','sub_portal_name_found','sub_instructions',
            'sub_instructions_found','sub_page_cost','sub_paths_tried','conference_name','base_url','domain','crawl_date','total_cost',
            'fields_with_value','fields_with_placeholder','fields_unavailable','completeness_pct','budget_exceeded','notable_info',
            'crawl_notes','metrics','market','customer'
        ]
        writer = csv.DictWriter(tmp, fieldnames=fieldnames)
        writer.writeheader()
        for u in urls:
            parsed = urlparse(u)
            writer.writerow({
                "conf_page_url": u,
                "base_url": u,
                "domain": parsed.netloc.lower(),
                "conference_name": "",
                "market": "hydrogen",
                "customer": "default_customer",
            })
        tmp.close()
        import_csv_path = tmp.name
        cmd.extend(["--import-csv", import_csv_path])
    else:
        if str(allow_default_csv).lower() != "true":
            raise HTTPException(status_code=400, detail="No valid URLs provided. Paste URLs or explicitly enable default CSV run.")

    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        return JSONResponse(status_code=500, content={"ok": False, "error": proc.stderr or proc.stdout})

    return {
        "ok": True,
        "output": proc.stdout.strip(),
        "source": "manual_urls" if urls else "default_csv",
        "input_url_count": len(urls),
        "import_csv": import_csv_path,
    }


def _parse_http_urls(urls_text: str) -> List[str]:
    raw_urls = [u.strip() for u in (urls_text or "").splitlines() if u.strip()]
    deduped = []
    seen = set()
    for u in raw_urls:
        if not u.lower().startswith(("http://", "https://")):
            continue
        c = _canonicalize_url(u)
        if c and c not in seen:
            seen.add(c)
            deduped.append(c)
    return deduped


def _load_latest_master_urls() -> List[str]:
    p = get_pr_monitor_settings().master_lists_dir / "master_list_latest.txt"
    if not p.exists():
        return []
    try:
        return _parse_http_urls(p.read_text(encoding="utf-8"))
    except Exception:
        return []


def _resolve_pr_monitor_1_crawl_urls(
    custom_urls: str = "",
    urls: str = "",
    urls_text: str = "",
    use_master_list: str = "true",
) -> List[str]:
    """Resolve Step 3 crawl URL inputs in documented priority order."""
    parsed_urls: List[str] = []

    if (custom_urls or "").strip():
        try:
            maybe_list = json.loads(custom_urls)
            if isinstance(maybe_list, list):
                parsed_urls = _parse_http_urls("\n".join(str(x) for x in maybe_list))
            else:
                parsed_urls = _parse_http_urls(str(maybe_list))
        except Exception:
            parsed_urls = _parse_http_urls(custom_urls)

    if not parsed_urls and (urls or "").strip():
        parsed_urls = _parse_http_urls(urls)

    if not parsed_urls and (urls_text or "").strip():
        parsed_urls = _parse_http_urls(urls_text)

    if not parsed_urls and str(use_master_list).lower() == "true":
        parsed_urls = _load_latest_master_urls()

    return parsed_urls


def _run_pr_monitor_pipeline(mode: str, min_confidence: float, urls: List[str], allow_default_csv: bool, skip_same_day: bool) -> Dict[str, Any]:
    script = str(get_pr_monitor_settings().legacy_runner_path)
    cmd = [
        "python3",
        script,
        "--db",
        str(get_pr_monitor_settings().db_path),
        "--mode",
        mode,
        "--min-confidence",
        str(min_confidence),
    ]
    if skip_same_day:
        cmd.append("--skip-same-day")

    import_csv_path = None
    if urls:
        import tempfile
        from urllib.parse import urlparse
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix="_pr_monitor_1_input.csv", delete=False, encoding="utf-8", newline="")
        fieldnames = [
            'conf_page_url','conf_name','conf_name_found','conf_dates','conf_dates_found','conf_location','conf_location_found',
            'conf_description','conf_description_found','conf_page_cost','conf_page_paths_tried','contact_page_url','contact_name',
            'contact_name_found','contact_email','contact_email_found','contact_phone','contact_phone_found','contact_org',
            'contact_org_found','contact_page_cost','contact_paths_tried','cfp_page_url','cfp_status','cfp_status_found',
            'cfp_deadline','cfp_deadline_found','cfp_opens','cfp_opens_found','cfp_sub_requirements','cfp_sub_requirements_found',
            'cfp_page_cost','sub_page_url','sub_link','sub_link_found','sub_portal_name','sub_portal_name_found','sub_instructions',
            'sub_instructions_found','sub_page_cost','sub_paths_tried','conference_name','base_url','domain','crawl_date','total_cost',
            'fields_with_value','fields_with_placeholder','fields_unavailable','completeness_pct','budget_exceeded','notable_info',
            'crawl_notes','metrics','market','customer'
        ]
        writer = csv.DictWriter(tmp, fieldnames=fieldnames)
        writer.writeheader()
        for u in urls:
            parsed = urlparse(u)
            writer.writerow({
                "conf_page_url": u,
                "base_url": u,
                "domain": parsed.netloc.lower(),
                "conference_name": "",
                "market": "hydrogen",
                "customer": "default_customer",
            })
        tmp.close()
        import_csv_path = tmp.name
        cmd.extend(["--import-csv", import_csv_path])
    else:
        if not allow_default_csv:
            raise HTTPException(status_code=400, detail="No valid URLs provided. Paste URLs, run Step 3 crawl first, or explicitly enable default CSV run.")

    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        return {"ok": False, "error": proc.stderr or proc.stdout}

    return {
        "ok": True,
        "output": proc.stdout.strip(),
        "source": "manual_urls" if urls else "default_csv",
        "input_url_count": len(urls),
        "import_csv": import_csv_path,
    }


async def _crawl_with_crawl4ai(urls: List[str], crawl_id: str, crawl_dir: Path) -> Dict[str, Any]:
    """
    Crawl URLs with Crawl4AI and persist reusable artifacts.
    Falls back to HTTP reachability-only rows if Crawl4AI is unavailable.
    """
    artifacts_dir = crawl_dir / "artifacts" / crawl_id
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    rows: List[Dict[str, Any]] = []
    reachable = 0
    crawl4ai_enabled = False
    crawl4ai_error = ""

    try:
        from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, CacheMode  # type: ignore
        crawl4ai_enabled = True
        config = CrawlerRunConfig(cache_mode=CacheMode.BYPASS, page_timeout=60000)

        async with AsyncWebCrawler() as crawler:
            for idx, u in enumerate(urls, start=1):
                artifact_path = artifacts_dir / f"{idx:04d}.json"
                err = ""
                status = None
                final_url = u
                markdown = ""
                cleaned_html = ""
                raw_html = ""
                try:
                    result = await crawler.arun(u, config=config)
                    status = getattr(result, "status_code", None)
                    final_url = str(getattr(result, "url", None) or u)
                    markdown = str(getattr(result, "markdown", "") or "")
                    cleaned_html = str(getattr(result, "cleaned_html", "") or "")
                    raw_html = str(getattr(result, "html", "") or "")
                    if status is None and (markdown or cleaned_html or raw_html):
                        status = 200
                    if status is not None and int(status) < 400:
                        reachable += 1
                except Exception as e:
                    err = str(e)

                artifact_payload = {
                    "source_url": u,
                    "final_url": final_url,
                    "http_status": status,
                    "markdown": markdown,
                    "cleaned_html": cleaned_html,
                    "html": raw_html,
                    "error": err,
                    "crawled_at": datetime.now(timezone.utc).isoformat(),
                }
                artifact_path.write_text(json.dumps(artifact_payload, ensure_ascii=False), encoding="utf-8")

                rows.append({
                    "url": u,
                    "canonical_url": _canonicalize_url(u),
                    "final_url": _canonicalize_url(final_url),
                    "http_status": status,
                    "reachable": bool(status is not None and int(status) < 400),
                    "error": err,
                    "artifact_json": str(artifact_path),
                    "artifact_markdown_len": len(markdown),
                    "artifact_html_len": len(raw_html or cleaned_html),
                    "crawled_at": artifact_payload["crawled_at"],
                })
    except Exception as e:
        crawl4ai_error = str(e)

    if not crawl4ai_enabled:
        headers = {"User-Agent": "openclaw-pr-monitor-1-crawl/1.0"}
        for idx, u in enumerate(urls, start=1):
            artifact_path = artifacts_dir / f"{idx:04d}.json"
            status = None
            final_url = u
            err = ""
            body = ""
            try:
                r = requests.get(u, headers=headers, timeout=20, allow_redirects=True)
                status = int(r.status_code)
                final_url = str(r.url or u)
                body = r.text or ""
                if status < 400:
                    reachable += 1
            except Exception as ex:
                err = str(ex)

            artifact_payload = {
                "source_url": u,
                "final_url": final_url,
                "http_status": status,
                "markdown": "",
                "cleaned_html": "",
                "html": body,
                "error": err,
                "crawled_at": datetime.now(timezone.utc).isoformat(),
                "fallback_mode": "requests_get_only",
            }
            artifact_path.write_text(json.dumps(artifact_payload, ensure_ascii=False), encoding="utf-8")

            rows.append({
                "url": u,
                "canonical_url": _canonicalize_url(u),
                "final_url": _canonicalize_url(final_url),
                "http_status": status,
                "reachable": bool(status is not None and status < 400),
                "error": err,
                "artifact_json": str(artifact_path),
                "artifact_markdown_len": 0,
                "artifact_html_len": len(body),
                "crawled_at": artifact_payload["crawled_at"],
            })

    return {
        "rows": rows,
        "reachable_count": reachable,
        "crawl4ai_enabled": crawl4ai_enabled,
        "crawl4ai_error": crawl4ai_error,
        "artifacts_dir": str(artifacts_dir),
    }


def _load_pr_monitor_source_registry_module():
    import importlib.util
    module_path = get_pr_monitor_settings().project_root / "source_registry.py"
    spec = importlib.util.spec_from_file_location("pr_monitor_source_registry", module_path)
    if not spec or not spec.loader:
        raise RuntimeError(f"Could not load source registry module at {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _source_registry_path() -> Path:
    return get_pr_monitor_settings().source_registry_path


def _prefer_source_registry_paths(urls: List[str]) -> List[str]:
    """Prefer remembered CFP/submission/contact paths before broad source URLs."""
    try:
        sr = _load_pr_monitor_source_registry_module()
        return list(sr.preferred_urls_for_sources(urls, _source_registry_path()))
    except Exception:
        return urls


def _update_source_registry_from_crawl(crawl_id: str, rows: List[Dict[str, Any]], manifest_path: Path, artifacts_dir: str) -> Dict[str, Any]:
    try:
        sr = _load_pr_monitor_source_registry_module()
        return sr.update_registry_from_crawl_rows(
            registry_path=_source_registry_path(),
            rows=rows,
            crawl_id=crawl_id,
            manifest_path=str(manifest_path),
            artifacts_dir=artifacts_dir,
        )
    except Exception as e:
        return {"registry_path": str(_source_registry_path()), "error": str(e), "updated_sources": 0}


def _load_pr_monitor_deadline_intelligence_module():
    import importlib.util
    module_path = get_pr_monitor_settings().project_root / "deadline_intelligence.py"
    if not module_path.exists():
        fallback_path = Path(__file__).resolve().parent.parent / "projects" / "PR_Firm_Texas" / "deadline_intelligence.py"
        if fallback_path.exists():
            module_path = fallback_path
    spec = importlib.util.spec_from_file_location("pr_monitor_deadline_intelligence", str(module_path))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load deadline intelligence module at {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _enrich_pr_monitor_rows_with_deadline_intelligence(rows: List[Dict[str, Any]], today_for_deadline: Optional[str] = None) -> List[Dict[str, Any]]:
    try:
        di = _load_pr_monitor_deadline_intelligence_module()
        return list(di.enrich_rows(rows, today=today_for_deadline))
    except Exception:
        return rows


def _read_csv_rows(path_value: str, today_for_deadline: Optional[str] = None) -> List[Dict[str, Any]]:
    if not path_value:
        return []
    p = Path(path_value)
    if not p.exists():
        return []
    with p.open("r", encoding="utf-8-sig", newline="") as f:
        rows = [dict(r) for r in csv.DictReader(f)]
    return _enrich_pr_monitor_rows_with_deadline_intelligence(rows, today_for_deadline=today_for_deadline)


def _update_source_registry_from_extract(extract_id: str, result: Dict[str, Any]) -> Dict[str, Any]:
    try:
        sr = _load_pr_monitor_source_registry_module()
        paths = result.get("paths") or {}
        rows = _read_csv_rows(str(paths.get("output_csv") or ""))
        return sr.update_registry_from_extraction_rows(
            registry_path=_source_registry_path(),
            rows=rows,
            extract_id=extract_id,
            artifact_refs=paths,
        )
    except Exception as e:
        return {"registry_path": str(_source_registry_path()), "error": str(e), "updated_sources": 0}


def _enrich_pr_monitor_rows_with_source_history(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    try:
        sr = _load_pr_monitor_source_registry_module()
        return list(sr.enrich_rows_with_source_history(rows, _source_registry_path()))
    except Exception:
        return rows


def _run_batch_processor_extract(urls: List[str], extract_id: str, extract_dir: Path) -> Dict[str, Any]:
    """
    Run canonical extractor (batch_processor.py) using URL CSV input.
    """
    if not urls:
        return {"ok": False, "error": "No URLs provided for extraction."}

    input_csv = extract_dir / f"{extract_id}_input.csv"
    with input_csv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["CONFERENCE URL", "CONFERENCE"])
        writer.writeheader()
        for idx, u in enumerate(urls, start=1):
            writer.writerow({"CONFERENCE URL": u, "CONFERENCE": f"Conference {idx}"})

    output_prefix = str(extract_dir / extract_id)
    cmd = [
        "python3",
        str(get_pr_monitor_settings().batch_processor_path),
        "--input",
        str(input_csv),
        "--output",
        output_prefix,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        return {"ok": False, "error": proc.stderr or proc.stdout}

    csv_out = f"{output_prefix}_CONFERENCES_54COLUMNS.csv"
    json_out = f"{output_prefix}_results.json"
    report_out = f"{output_prefix}_EXECUTIVE_REPORT.txt"
    return {
        "ok": True,
        "stdout": proc.stdout.strip(),
        "paths": {
            "input_csv": str(input_csv),
            "output_csv": csv_out,
            "output_json": json_out,
            "output_report": report_out,
        },
    }



def _expand_urls_with_discovery(
    urls: List[str],
    source_crawl_id: Optional[str],
    extract_id: str,
    extract_dir: Path,
) -> tuple[List[str], Dict[str, Any]]:
    """Expand extraction URLs through Step 4 v2 internal-link discovery.

    This is intentionally best-effort. If the recovery/evidence package inputs are
    unavailable, production extraction falls back to the original v1 URL list.
    """
    info: Dict[str, Any] = {
        "requested": True,
        "ok": False,
        "fallback_to_v1": False,
        "source_crawl_id": source_crawl_id or "",
    }
    if not source_crawl_id:
        info.update({"fallback_to_v1": True, "error": "source_crawl_id_required"})
        return urls, info

    settings = get_pr_monitor_settings()
    script_path = settings.runtime_root / "extraction_benchmarks" / "multi_page_evidence.py"
    if not script_path.exists():
        info.update({"fallback_to_v1": True, "error": f"multi_page_evidence.py not found: {script_path}"})
        return urls, info

    evidence_dir = extract_dir / f"{extract_id}_v2_evidence"
    cmd = [
        "python3",
        str(script_path),
        "--run-id",
        source_crawl_id,
        "--out-dir",
        str(evidence_dir),
        "--skip-direct-fetch",
        "--use-discovery",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(script_path.parent))
    info.update({
        "command": cmd,
        "evidence_dir": str(evidence_dir),
        "returncode": proc.returncode,
        "stdout": (proc.stdout or "").strip()[-4000:],
        "stderr": (proc.stderr or "").strip()[-4000:],
    })
    if proc.returncode != 0:
        info.update({"fallback_to_v1": True, "error": proc.stderr or proc.stdout or "discovery evidence command failed"})
        return urls, info

    index_path = evidence_dir / "index.json"
    try:
        index = json.loads(index_path.read_text(encoding="utf-8"))
        manifest_path = Path(index.get("local_browser_job_manifest") or "")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        discovered_urls = [
            str(row.get("url") or "").strip()
            for row in (manifest.get("urls") or [])
            if str(row.get("url") or "").strip()
        ]
    except Exception as e:
        info.update({"fallback_to_v1": True, "error": f"discovery_manifest_read_failed: {e}"})
        return urls, info

    expanded = list(dict.fromkeys(_canonicalize_url(u) for u in [*discovered_urls, *urls] if str(u).strip()))
    if not expanded:
        info.update({"fallback_to_v1": True, "error": "discovery_returned_no_urls"})
        return urls, info

    info.update({
        "ok": True,
        "fallback_to_v1": False,
        "original_url_count": len(urls),
        "expanded_url_count": len(expanded),
        "manifest_path": str(manifest_path),
    })
    return expanded, info



def _pr_monitor_1_base_dir() -> Path:
    return get_pr_monitor_settings().runtime_root


def _safe_pr_monitor_1_path(path_value: str) -> Path:
    if not path_value:
        raise HTTPException(status_code=400, detail="path is required")
    base = _pr_monitor_1_base_dir().resolve()
    p = Path(path_value).expanduser().resolve()
    try:
        p.relative_to(base)
    except ValueError:
        raise HTTPException(status_code=403, detail="Path not allowed")
    return p


def _send_crawl_engine_fallback_alert(crawl4ai_error: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Fire immediate Telegram alert on crawl-engine fallback/failure.
    Uses env vars when available:
    - PR_MONITOR_TELEGRAM_BOT_TOKEN (or TELEGRAM_BOT_TOKEN)
    - PR_MONITOR_TELEGRAM_CHAT_ID (or MATT_TELEGRAM_CHAT_ID or TELEGRAM_CHAT_ID)
    """
    token = (
        os.environ.get("PR_MONITOR_TELEGRAM_BOT_TOKEN")
        or os.environ.get("TELEGRAM_BOT_TOKEN")
        or ""
    ).strip()
    chat_id = (
        os.environ.get("PR_MONITOR_TELEGRAM_CHAT_ID")
        or os.environ.get("MATT_TELEGRAM_CHAT_ID")
        or os.environ.get("TELEGRAM_CHAT_ID")
        or ""
    ).strip()

    base = _pr_monitor_1_base_dir()
    base.mkdir(parents=True, exist_ok=True)
    alert_log = base / "crawl_engine_alerts.jsonl"
    now_iso = datetime.now(timezone.utc).isoformat()
    ctx = context or {}
    reason = (crawl4ai_error or "crawl engine import/runtime failure").strip()
    msg = (
        "PR Monitor ALERT: crawl engine fallback triggered.\n"
        f"time_utc={now_iso}\n"
        f"reason={reason}\n"
        f"crawl_id={ctx.get('crawl_id') or 'n/a'}\n"
        f"url_count={ctx.get('url_count') or 'n/a'}"
    )

    sent_ok = False
    send_error = ""
    if token and chat_id:
        try:
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            r = requests.post(url, data={"chat_id": chat_id, "text": msg}, timeout=15)
            sent_ok = bool(r.ok)
            if not sent_ok:
                send_error = f"http_{r.status_code}"
        except Exception as e:
            send_error = str(e)
    else:
        send_error = "telegram_credentials_missing"

    try:
        line = {
            "at": now_iso,
            "sent_ok": sent_ok,
            "send_error": send_error,
            "reason": reason,
            "context": ctx,
        }
        with alert_log.open("a", encoding="utf-8") as f:
            f.write(json.dumps(line) + "\n")
    except Exception:
        pass

    return {
        "sent_ok": sent_ok,
        "send_error": send_error,
        "alert_log": str(alert_log),
    }


def _update_crawl_engine_metrics(
    crawl4ai_enabled: bool,
    crawl4ai_error: str,
    context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    base = _pr_monitor_1_base_dir()
    base.mkdir(parents=True, exist_ok=True)
    metrics_path = base / "crawl_engine_metrics.json"
    now_iso = datetime.now(timezone.utc).isoformat()
    metrics = {
        "total_runs": 0,
        "crawl_engine_runs": 0,
        "fallback_runs": 0,
        "crawl_engine_failure_count": 0,
        "last_run_at": None,
        "last_crawl_engine_failure_at": None,
        "last_crawl_engine_failure_reason": "",
    }
    if metrics_path.exists():
        try:
            loaded = json.loads(metrics_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                metrics.update(loaded)
        except Exception:
            pass

    metrics["total_runs"] = int(metrics.get("total_runs") or 0) + 1
    metrics["last_run_at"] = now_iso
    if crawl4ai_enabled:
        metrics["crawl_engine_runs"] = int(metrics.get("crawl_engine_runs") or 0) + 1
    else:
        metrics["fallback_runs"] = int(metrics.get("fallback_runs") or 0) + 1
        metrics["crawl_engine_failure_count"] = int(metrics.get("crawl_engine_failure_count") or 0) + 1
        metrics["last_crawl_engine_failure_at"] = now_iso
        metrics["last_crawl_engine_failure_reason"] = crawl4ai_error or "crawl engine import/runtime failure"
        alert_info = _send_crawl_engine_fallback_alert(crawl4ai_error=crawl4ai_error, context=context or {})
        metrics["last_alert_sent_ok"] = bool(alert_info.get("sent_ok"))
        metrics["last_alert_send_error"] = str(alert_info.get("send_error") or "")
        metrics["alert_log"] = str(alert_info.get("alert_log") or "")

    metrics_path.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    metrics["metrics_path"] = str(metrics_path)
    return metrics


@app.get("/api/pr-monitor-1/artifact/list")
async def pr_monitor_1_artifact_list(path: str = Query(...)):
    p = _safe_pr_monitor_1_path(path)
    if not p.exists() or not p.is_dir():
        raise HTTPException(status_code=404, detail="Directory not found")
    items = []
    for child in sorted(p.iterdir()):
        items.append({
            "name": child.name,
            "is_dir": child.is_dir(),
            "path": str(child),
            "size": child.stat().st_size if child.is_file() else None,
        })
    return {"ok": True, "path": str(p), "items": items}


@app.get("/api/pr-monitor-1/artifact/open")
async def pr_monitor_1_artifact_open(path: str = Query(...)):
    p = _safe_pr_monitor_1_path(path)
    if not p.exists() or not p.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(str(p), filename=p.name)


@app.get("/api/pr-monitor-1/crawl-engine-metrics")
async def pr_monitor_1_crawl_engine_metrics():
    metrics_path = _pr_monitor_1_base_dir() / "crawl_engine_metrics.json"
    if not metrics_path.exists():
        return {
            "ok": True,
            "metrics": {
                "total_runs": 0,
                "crawl_engine_runs": 0,
                "fallback_runs": 0,
                "crawl_engine_failure_count": 0,
                "last_run_at": None,
                "last_crawl_engine_failure_at": None,
                "last_crawl_engine_failure_reason": "",
                "metrics_path": str(metrics_path),
            },
        }
    try:
        metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
        if not isinstance(metrics, dict):
            metrics = {}
    except Exception:
        metrics = {}
    metrics.setdefault("total_runs", 0)
    metrics.setdefault("crawl_engine_runs", 0)
    metrics.setdefault("fallback_runs", 0)
    metrics.setdefault("crawl_engine_failure_count", 0)
    metrics.setdefault("last_run_at", None)
    metrics.setdefault("last_crawl_engine_failure_at", None)
    metrics.setdefault("last_crawl_engine_failure_reason", "")
    metrics["metrics_path"] = str(metrics_path)
    return {"ok": True, "metrics": metrics}


@app.get("/api/pr-monitor-1/source-registry")
async def pr_monitor_1_source_registry():
    path = _source_registry_path()
    try:
        sr = _load_pr_monitor_source_registry_module()
        registry = sr.load_registry(path)
    except Exception:
        registry = {"schema_version": "source_registry_v1", "sources": {}}
    return {
        "ok": True,
        "path": str(path),
        "source_count": len(registry.get("sources") or {}),
        "registry": registry,
    }


@app.get("/api/pr-monitor-1/source-history")
async def pr_monitor_1_source_history(url: str = Query(...)):
    try:
        sr = _load_pr_monitor_source_registry_module()
        history = sr.source_history_for_url(_source_registry_path(), url)
    except Exception as e:
        history = {"error": str(e)}
    return {"ok": True, "url": url, "history": history}


@app.get("/api/pr-monitor-1/job/{job_id}")
async def pr_monitor_1_job_status(job_id: str):
    row = _pr_job_get(job_id)
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"ok": True, "job": row}


def _run_crawl_job(job_id: str, urls: List[str], use_master_list: str) -> None:
    try:
        _pr_job_set(job_id, {
            "status": "running",
            "message": "Starting crawl",
            "progress": 10,
            "started_at": datetime.now(timezone.utc).isoformat(),
        })

        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        crawl_id = f"crawl_{stamp}"
        crawl_dir = get_pr_monitor_settings().crawl_runs_dir
        crawl_dir.mkdir(parents=True, exist_ok=True)

        _pr_job_set(job_id, {"message": "Running crawl engine", "progress": 45})
        crawl_result = asyncio.run(_crawl_with_crawl4ai(urls=urls, crawl_id=crawl_id, crawl_dir=crawl_dir))
        rows = crawl_result["rows"]
        reachable = int(crawl_result["reachable_count"])
        engine_metrics = _update_crawl_engine_metrics(
            crawl4ai_enabled=bool(crawl_result["crawl4ai_enabled"]),
            crawl4ai_error=str(crawl_result.get("crawl4ai_error") or ""),
            context={"crawl_id": crawl_id, "url_count": len(urls), "job_id": job_id},
        )

        manifest = {
            "ok": True,
            "crawl_id": crawl_id,
            "url_count": len(urls),
            "reachable_count": reachable,
            "crawl4ai_enabled": bool(crawl_result["crawl4ai_enabled"]),
            "crawl4ai_error": crawl_result.get("crawl4ai_error") or "",
            "artifacts_dir": crawl_result["artifacts_dir"],
            "rows": rows,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
        manifest_path = crawl_dir / f"{crawl_id}.json"
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        source_registry_summary = _update_source_registry_from_crawl(
            crawl_id=crawl_id,
            rows=rows,
            manifest_path=manifest_path,
            artifacts_dir=str(crawl_result.get("artifacts_dir") or ""),
        )
        manifest["source_registry"] = source_registry_summary
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

        urls_path = crawl_dir / f"{crawl_id}.txt"
        urls_path.write_text("\n".join(urls) + "\n", encoding="utf-8")
        latest_json = crawl_dir / "latest_crawl.json"
        latest_txt = crawl_dir / "latest_crawl.txt"
        latest_json.write_text(manifest_path.read_text(encoding="utf-8"), encoding="utf-8")
        latest_txt.write_text(urls_path.read_text(encoding="utf-8"), encoding="utf-8")

        _pr_job_set(job_id, {
            "status": "completed",
            "message": "Crawl completed",
            "progress": 100,
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "result": {
                "ok": True,
                "crawl_id": crawl_id,
                "url_count": len(urls),
                "reachable_count": reachable,
                "crawl4ai_enabled": bool(crawl_result["crawl4ai_enabled"]),
                "crawl4ai_error": crawl_result.get("crawl4ai_error") or "",
                "artifacts_dir": crawl_result["artifacts_dir"],
                "paths": {
                    "manifest_json": str(manifest_path),
                    "urls_txt": str(urls_path),
                    "latest_manifest_json": str(latest_json),
                    "latest_urls_txt": str(latest_txt),
                },
                "engine_metrics": engine_metrics,
                "source_registry": source_registry_summary,
            },
        })
    except Exception as e:
        _pr_job_set(job_id, {
            "status": "failed",
            "message": "Crawl failed",
            "progress": 100,
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "error": str(e),
            "traceback": traceback.format_exc(),
        })


def _run_extract_job(
    job_id: str,
    mode: str,
    min_confidence: float,
    urls_text: str,
    skip_same_day: str,
    use_latest_crawl: str,
    use_discovery: str,
) -> None:
    try:
        _pr_job_set(job_id, {
            "status": "running",
            "message": "Preparing extraction input",
            "progress": 10,
            "started_at": datetime.now(timezone.utc).isoformat(),
        })

        urls = _parse_http_urls(urls_text)
        source_crawl_id = None
        if not urls and str(use_latest_crawl).lower() == "true":
            latest_manifest = get_pr_monitor_settings().crawl_runs_dir / "latest_crawl.json"
            if latest_manifest.exists():
                try:
                    payload = json.loads(latest_manifest.read_text(encoding="utf-8"))
                    source_crawl_id = str(payload.get("crawl_id") or "")
                    rows = payload.get("rows") or []
                    for row in rows:
                        candidate = str(row.get("final_url") or row.get("url") or "").strip()
                        if candidate:
                            urls.append(candidate)
                except Exception:
                    pass
        if not urls:
            urls = _load_latest_master_urls()

        urls = list(dict.fromkeys(_canonicalize_url(u) for u in urls if str(u).strip()))
        urls = _prefer_source_registry_paths(urls)
        extract_dir = get_pr_monitor_settings().extract_runs_dir
        extract_dir.mkdir(parents=True, exist_ok=True)
        extract_id = f"extract_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
        discovery_info: Dict[str, Any] = {"requested": bool(str(use_discovery).lower() == "true")}
        if str(use_discovery).lower() == "true":
            _pr_job_set(job_id, {"message": "Expanding URLs with v2 discovery", "progress": 45})
            urls, discovery_info = _expand_urls_with_discovery(
                urls=urls,
                source_crawl_id=source_crawl_id,
                extract_id=extract_id,
                extract_dir=extract_dir,
            )

        _pr_job_set(job_id, {"message": "Running batch extractor", "progress": 60})
        result = _run_batch_processor_extract(urls=urls, extract_id=extract_id, extract_dir=extract_dir)
        if not result.get("ok"):
            raise RuntimeError(result.get("error") or "batch extractor failed")

        source_registry_summary = _update_source_registry_from_extract(extract_id, result)
        trace_path = extract_dir / f"{extract_id}_trace.json"
        trace_payload = {
            "extract_id": extract_id,
            "source_crawl_id": source_crawl_id,
            "used_latest_crawl": bool(str(use_latest_crawl).lower() == "true"),
            "mode": mode,
            "min_confidence": min_confidence,
            "url_count": len(urls),
            "urls": urls,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "batch_output_paths": result.get("paths") or {},
            "source_registry": source_registry_summary,
            "use_discovery": bool(str(use_discovery).lower() == "true"),
            "discovery": discovery_info,
        }
        trace_path.write_text(json.dumps(trace_payload, indent=2), encoding="utf-8")

        _pr_job_set(job_id, {
            "status": "completed",
            "message": "Extraction completed",
            "progress": 100,
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "result": {
                "ok": True,
                "phase": "extract",
                "extract_id": extract_id,
                "source_crawl_id": source_crawl_id,
                "used_latest_crawl": bool(str(use_latest_crawl).lower() == "true"),
                "use_discovery": bool(str(use_discovery).lower() == "true"),
                "discovery": discovery_info,
                "url_count": len(urls),
                "paths": {
                    **(result.get("paths") or {}),
                    "trace_json": str(trace_path),
                    "extract_run_dir": str(extract_dir),
                },
                "source_registry": source_registry_summary,
                "output": result.get("stdout", ""),
            },
        })
    except Exception as e:
        _pr_job_set(job_id, {
            "status": "failed",
            "message": "Extraction failed",
            "progress": 100,
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "error": str(e),
            "traceback": traceback.format_exc(),
        })


@app.post("/api/pr-monitor-1/crawl")
async def pr_monitor_1_crawl(
    request: Request,
    urls_text: str = Form(""),
    urls: str = Form(""),
    custom_urls: str = Form(""),
    use_master_list: str = Form("true"),
    async_mode: str = Form("true"),
):
    _reject_json_for_form_endpoint(request)
    parsed_urls = _resolve_pr_monitor_1_crawl_urls(
        custom_urls=custom_urls,
        urls=urls,
        urls_text=urls_text,
        use_master_list=use_master_list,
    )
    use_master = str(use_master_list).lower() == "true"
    if not parsed_urls:
        raise HTTPException(status_code=400, detail="No URLs to crawl. Provide URLs or generate master list first.")
    original_url_count = len(parsed_urls)
    parsed_urls = _prefer_source_registry_paths(parsed_urls)

    if str(async_mode).lower() == "true":
        job_id = f"crawl_job_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{uuid4().hex[:8]}"
        _pr_job_set(job_id, {
            "job_id": job_id,
            "job_type": "crawl",
            "status": "queued",
            "message": "Queued",
            "progress": 0,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "input": {
                "url_count": len(parsed_urls),
                "original_url_count": original_url_count,
                "source_registry_preferred_paths_added": max(0, len(parsed_urls) - original_url_count),
                "use_master_list": use_master,
                "custom_urls_used": bool(custom_urls.strip()),
                "urls_alias_used": bool(urls.strip()),
            },
        })
        t = threading.Thread(target=_run_crawl_job, args=(job_id, parsed_urls, use_master_list), daemon=True)
        t.start()
        return {"ok": True, "async": True, "job_id": job_id, "status": "queued"}

    # sync fallback
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    crawl_id = f"crawl_{stamp}"
    crawl_dir = get_pr_monitor_settings().crawl_runs_dir
    crawl_dir.mkdir(parents=True, exist_ok=True)
    crawl_result = await _crawl_with_crawl4ai(urls=parsed_urls, crawl_id=crawl_id, crawl_dir=crawl_dir)
    rows = crawl_result["rows"]
    reachable = int(crawl_result["reachable_count"])
    engine_metrics = _update_crawl_engine_metrics(
        crawl4ai_enabled=bool(crawl_result["crawl4ai_enabled"]),
        crawl4ai_error=str(crawl_result.get("crawl4ai_error") or ""),
        context={"crawl_id": crawl_id, "url_count": len(parsed_urls)},
    )
    manifest = {
        "ok": True,
        "crawl_id": crawl_id,
        "url_count": len(parsed_urls),
        "reachable_count": reachable,
        "crawl4ai_enabled": bool(crawl_result["crawl4ai_enabled"]),
        "crawl4ai_error": crawl_result.get("crawl4ai_error") or "",
        "artifacts_dir": crawl_result["artifacts_dir"],
        "rows": rows,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    manifest_path = crawl_dir / f"{crawl_id}.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    source_registry_summary = _update_source_registry_from_crawl(
        crawl_id=crawl_id,
        rows=rows,
        manifest_path=manifest_path,
        artifacts_dir=str(crawl_result.get("artifacts_dir") or ""),
    )
    manifest["source_registry"] = source_registry_summary
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    urls_path = crawl_dir / f"{crawl_id}.txt"
    urls_path.write_text("\n".join(parsed_urls) + "\n", encoding="utf-8")
    latest_json = crawl_dir / "latest_crawl.json"
    latest_txt = crawl_dir / "latest_crawl.txt"
    latest_json.write_text(manifest_path.read_text(encoding="utf-8"), encoding="utf-8")
    latest_txt.write_text(urls_path.read_text(encoding="utf-8"), encoding="utf-8")
    return {
        "ok": True,
        "crawl_id": crawl_id,
        "url_count": len(parsed_urls),
        "reachable_count": reachable,
        "crawl4ai_enabled": bool(crawl_result["crawl4ai_enabled"]),
        "crawl4ai_error": crawl_result.get("crawl4ai_error") or "",
        "artifacts_dir": crawl_result["artifacts_dir"],
        "paths": {
            "manifest_json": str(manifest_path),
            "urls_txt": str(urls_path),
            "latest_manifest_json": str(latest_json),
            "latest_urls_txt": str(latest_txt),
        },
        "engine_metrics": engine_metrics,
        "source_registry": source_registry_summary,
    }


@app.post("/api/pr-monitor-1/extract")
async def pr_monitor_1_extract(
    request: Request,
    mode: str = Form("smart_hybrid"),
    min_confidence: float = Form(0.85),
    urls_text: str = Form(""),
    allow_default_csv: str = Form("false"),
    skip_same_day: str = Form("true"),
    use_latest_crawl: str = Form("true"),
    use_discovery: str = Form("false"),
    async_mode: str = Form("true"),
):
    _reject_json_for_form_endpoint(request)
    if mode not in {"full_ai", "smart_hybrid"}:
        raise HTTPException(status_code=400, detail="Invalid mode")

    if str(async_mode).lower() == "true":
        job_id = f"extract_job_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{uuid4().hex[:8]}"
        _pr_job_set(job_id, {
            "job_id": job_id,
            "job_type": "extract",
            "status": "queued",
            "message": "Queued",
            "progress": 0,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "input": {
                "mode": mode,
                "min_confidence": min_confidence,
                "skip_same_day": str(skip_same_day).lower() == "true",
                "use_latest_crawl": str(use_latest_crawl).lower() == "true",
                "use_discovery": str(use_discovery).lower() == "true",
            },
        })
        t = threading.Thread(
            target=_run_extract_job,
            args=(job_id, mode, min_confidence, urls_text, skip_same_day, use_latest_crawl, use_discovery),
            daemon=True,
        )
        t.start()
        return {"ok": True, "async": True, "job_id": job_id, "status": "queued"}

    # sync fallback
    urls = _parse_http_urls(urls_text)
    source_crawl_id = None
    if not urls and str(use_latest_crawl).lower() == "true":
        latest_manifest = get_pr_monitor_settings().crawl_runs_dir / "latest_crawl.json"
        if latest_manifest.exists():
            try:
                payload = json.loads(latest_manifest.read_text(encoding="utf-8"))
                source_crawl_id = str(payload.get("crawl_id") or "")
                rows = payload.get("rows") or []
                for row in rows:
                    candidate = str(row.get("final_url") or row.get("url") or "").strip()
                    if candidate:
                        urls.append(candidate)
            except Exception:
                pass
    if not urls:
        urls = _load_latest_master_urls()
    urls = list(dict.fromkeys(_canonicalize_url(u) for u in urls if str(u).strip()))
    urls = _prefer_source_registry_paths(urls)
    extract_dir = get_pr_monitor_settings().extract_runs_dir
    extract_dir.mkdir(parents=True, exist_ok=True)
    extract_id = f"extract_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    discovery_info: Dict[str, Any] = {"requested": bool(str(use_discovery).lower() == "true")}
    if str(use_discovery).lower() == "true":
        urls, discovery_info = _expand_urls_with_discovery(
            urls=urls,
            source_crawl_id=source_crawl_id,
            extract_id=extract_id,
            extract_dir=extract_dir,
        )
    result = _run_batch_processor_extract(urls=urls, extract_id=extract_id, extract_dir=extract_dir)
    if not result.get("ok"):
        return JSONResponse(status_code=500, content=result)
    source_registry_summary = _update_source_registry_from_extract(extract_id, result)
    trace_path = extract_dir / f"{extract_id}_trace.json"
    trace_payload = {
        "extract_id": extract_id,
        "source_crawl_id": source_crawl_id,
        "used_latest_crawl": bool(str(use_latest_crawl).lower() == "true"),
        "mode": mode,
        "min_confidence": min_confidence,
        "url_count": len(urls),
        "urls": urls,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "batch_output_paths": result.get("paths") or {},
        "source_registry": source_registry_summary,
        "use_discovery": bool(str(use_discovery).lower() == "true"),
        "discovery": discovery_info,
    }
    trace_path.write_text(json.dumps(trace_payload, indent=2), encoding="utf-8")
    return {
        "ok": True,
        "phase": "extract",
        "extract_id": extract_id,
        "source_crawl_id": source_crawl_id,
        "used_latest_crawl": bool(str(use_latest_crawl).lower() == "true"),
        "use_discovery": bool(str(use_discovery).lower() == "true"),
        "discovery": discovery_info,
        "url_count": len(urls),
        "paths": {
            **(result.get("paths") or {}),
            "trace_json": str(trace_path),
            "extract_run_dir": str(extract_dir),
        },
        "source_registry": source_registry_summary,
        "output": result.get("stdout", ""),
    }


@app.post("/api/pr-monitor-1/enrich")
async def pr_monitor_1_enrich(
    run_id: str = Form(""),
    enrich_types: str = Form("geo"),
    async_mode: str = Form("false"),
):
    """Enrich extracted data (geo, etc.) for a given run.
    
    Args:
        run_id: The run to enrich. If empty, uses latest completed run.
        enrich_types: Comma-separated list of enrichment types (default: "geo").
        async_mode: If true, runs as background job.
    """
    db_path = str(get_pr_monitor_settings().db_path)
    enrich_list = [t.strip() for t in enrich_types.split(",") if t.strip()]

    # Resolve run_id
    if not run_id:
        conn = sqlite3.connect(db_path)
        row = conn.execute(
            "SELECT run_id FROM pipeline_runs WHERE status='completed' ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
        conn.close()
        if not row:
            raise HTTPException(status_code=400, detail="No completed run found")
        run_id = row[0]

    if async_mode == "true":
        job_id = f"enrich_{run_id}_{int(datetime.now(timezone.utc).timestamp())}"
        _set_job(job_id, {"job_id": job_id, "job_type": "enrich", "status": "queued", "message": f"Enrichment queued for {run_id}"})
        _enrich_worker(job_id, db_path, run_id, enrich_list)
        return {"ok": True, "async": True, "job_id": job_id, "status": "queued", "run_id": run_id}

    # Synchronous mode
    result = _run_enrichment(db_path, run_id, enrich_list)
    return {"ok": True, "run_id": run_id, "result": result}


def _run_enrichment(db_path: str, run_id: str, enrich_types: list) -> dict:
    """Run enrichment pipeline for a given run."""
    import subprocess
    import json as _json

    conn = sqlite3.connect(db_path)
    try:
        # Get URLs that need enrichment
        if "geo" in enrich_types:
            rows = conn.execute(
                "SELECT rowid, conf_page_url, conf_location FROM conference_events "
                "WHERE run_id = ? AND conf_location IS NOT NULL AND trim(conf_location) != '' "
                "AND (geo_city IS NULL OR geo_city = '')",
                (run_id,)
            ).fetchall()
        else:
            rows = []

        enriched = 0
        for rowid, url, conf_location in rows:
            city, state, country, confidence = _parse_geo_from_location(conf_location)
            if city:
                conn.execute(
                    "UPDATE conference_events SET geo_city=?, geo_state=?, geo_country=?, geo_confidence_status=? WHERE rowid=?",
                    (city, state, country, confidence, rowid),
                )
                enriched += 1

        conn.commit()

        # Summary
        total_geo = conn.execute(
            "SELECT COUNT(*) FROM conference_events WHERE run_id = ? AND geo_city IS NOT NULL AND geo_city != ''",
            (run_id,)
        ).fetchone()[0]

        return {
            "enriched": enriched,
            "total_with_geo": total_geo,
            "enrich_types": enrich_types,
        }
    finally:
        conn.close()


def _parse_geo_from_location(conf_location: str):
    """Parse geo fields from a conf_location string. Returns (city, state, country, confidence)."""
    import re

    if not conf_location or not conf_location.strip():
        return None, None, None, None

    text = conf_location.strip()

    # Common US state abbreviations
    state_map = {
        'AL': 'Alabama', 'AK': 'Alaska', 'AZ': 'Arizona', 'AR': 'Arkansas',
        'CA': 'California', 'CO': 'Colorado', 'CT': 'Connecticut', 'DE': 'Delaware',
        'FL': 'Florida', 'GA': 'Georgia', 'HI': 'Hawaii', 'ID': 'Idaho',
        'IL': 'Illinois', 'IN': 'Indiana', 'IA': 'Iowa', 'KS': 'Kansas',
        'KY': 'Kentucky', 'LA': 'Louisiana', 'ME': 'Maine', 'MD': 'Maryland',
        'MA': 'Massachusetts', 'MI': 'Michigan', 'MN': 'Minnesota', 'MS': 'Mississippi',
        'MO': 'Missouri', 'MT': 'Montana', 'NE': 'Nebraska', 'NV': 'Nevada',
        'NH': 'New Hampshire', 'NJ': 'New Jersey', 'NM': 'New Mexico', 'NY': 'New York',
        'NC': 'North Carolina', 'ND': 'North Dakota', 'OH': 'Ohio', 'OK': 'Oklahoma',
        'OR': 'Oregon', 'PA': 'Pennsylvania', 'RI': 'Rhode Island', 'SC': 'South Carolina',
        'SD': 'South Dakota', 'TN': 'Tennessee', 'TX': 'Texas', 'UT': 'Utah',
        'VT': 'Vermont', 'VA': 'Virginia', 'WA': 'Washington', 'WV': 'West Virginia',
        'WI': 'Wisconsin', 'WY': 'Wyoming', 'DC': 'District of Columbia',
    }

    country_aliases = {
        'USA': 'United States', 'US': 'United States', 'United States': 'United States',
        'UAE': 'United Arab Emirates', 'UK': 'United Kingdom', 'GB': 'United Kingdom',
        'Germany': 'Germany', 'France': 'France', 'Singapore': 'Singapore',
        'Australia': 'Australia', 'Japan': 'Japan', 'Canada': 'Canada',
        'Israel': 'Israel', 'India': 'India', 'Brazil': 'Brazil',
        'Netherlands': 'Netherlands', 'Switzerland': 'Switzerland',
        'Austria': 'Austria', 'Belgium': 'Belgium', 'Spain': 'Spain',
        'Italy': 'Italy', 'Sweden': 'Sweden', 'Norway': 'Norway',
        'Denmark': 'Denmark', 'Finland': 'Finland', 'Ireland': 'Ireland',
        'Portugal': 'Portugal', 'Greece': 'Greece', 'Poland': 'Poland',
        'Czech Republic': 'Czech Republic', 'Hungary': 'Hungary',
        'Romania': 'Romania', 'Bulgaria': 'Bulgaria', 'Croatia': 'Croatia',
        'Turkey': 'Turkey', 'South Africa': 'South Africa', 'Egypt': 'Egypt',
        'Kenya': 'Kenya', 'Nigeria': 'Nigeria', 'Morocco': 'Morocco',
        'Thailand': 'Thailand', 'Vietnam': 'Vietnam', 'Indonesia': 'Indonesia',
        'Malaysia': 'Malaysia', 'Philippines': 'Philippines',
        'South Korea': 'South Korea', 'Taiwan': 'Taiwan',
        'China': 'China', 'Hong Kong': 'Hong Kong',
        'Mexico': 'Mexico', 'Argentina': 'Argentina', 'Chile': 'Chile',
        'Colombia': 'Colombia', 'Peru': 'Peru',
        'New Zealand': 'New Zealand', 'Dubai': 'United Arab Emirates',
        'Qatar': 'Qatar', 'Saudi Arabia': 'Saudi Arabia',
    }

    city_country = {
        'las vegas': 'United States', 'new york': 'United States',
        'san francisco': 'United States', 'chicago': 'United States',
        'houston': 'United States', 'dallas': 'United States',
        'boston': 'United States', 'seattle': 'United States',
        'los angeles': 'United States', 'washington': 'United States',
        'atlanta': 'United States', 'miami': 'United States',
        'denver': 'United States', 'phoenix': 'United States',
        'philadelphia': 'United States', 'detroit': 'United States',
        'minneapolis': 'United States', 'portland': 'United States',
        'austin': 'United States', 'charlotte': 'United States',
        'kansas city': 'United States', 'st. louis': 'United States',
        'cleveland': 'United States', 'pittsburgh': 'United States',
        'cincinnati': 'United States', 'indianapolis': 'United States',
        'columbus': 'United States', 'milwaukee': 'United States',
        'nashville': 'United States', 'memphis': 'United States',
        'louisville': 'United States', 'richmond': 'United States',
        'tampa': 'United States', 'orlando': 'United States',
        'jacksonville': 'United States', 'baltimore': 'United States',
        'raleigh': 'United States', 'salt lake city': 'United States',
        'san diego': 'United States', 'san jose': 'United States',
        'sacramento': 'United States', 'honolulu': 'United States',
        'anchorage': 'United States', 'albuquerque': 'United States',
        'boise': 'United States', 'des moines': 'United States',
        'omaha': 'United States', 'tucson': 'United States',
        'fresno': 'United States', 'mesa': 'United States',
        'colorado springs': 'United States', 'virginia beach': 'United States',
        'omaha': 'United States', 'oakland': 'United States',
        'tulsa': 'United States', 'wichita': 'United States',
        'arlington': 'United States', 'bakersfield': 'United States',
        'tampa': 'United States', 'london': 'United Kingdom',
        'paris': 'France', 'berlin': 'Germany', 'munich': 'Germany',
        'hamburg': 'Germany', 'frankfurt': 'Germany', 'zurich': 'Switzerland',
        'geneva': 'Switzerland', 'amsterdam': 'Netherlands',
        'brussels': 'Belgium', 'vienna': 'Austria', 'prague': 'Czech Republic',
        'warsaw': 'Poland', 'budapest': 'Hungary', 'bucharest': 'Romania',
        'sofia': 'Bulgaria', 'athens': 'Greece', 'lisbon': 'Portugal',
        'madrid': 'Spain', 'barcelona': 'Spain', 'rome': 'Italy',
        'milan': 'Italy', 'amsterdam': 'Netherlands', 'oslo': 'Norway',
        'stockholm': 'Sweden', 'copenhagen': 'Denmark', 'helsinki': 'Finland',
        'dublin': 'Ireland', 'edinburgh': 'United Kingdom', 'manchester': 'United Kingdom',
        'birmingham': 'United Kingdom', 'glasgow': 'United Kingdom',
        'tokyo': 'Japan', 'osaka': 'Japan', 'singapore': 'Singapore',
        'sydney': 'Australia', 'melbourne': 'Australia', 'brisbane': 'Australia',
        'perth': 'Australia', 'auckland': 'New Zealand',
        'toronto': 'Canada', 'vancouver': 'Canada', 'montreal': 'Canada',
        'calgary': 'Canada', 'ottawa': 'Canada',
        'tel aviv': 'Israel', 'jerusalem': 'Israel',
        'dubai': 'United Arab Emirates', 'abu dhabi': 'United Arab Emirates',
        'mumbai': 'India', 'delhi': 'India', 'bangalore': 'India',
        'hyderabad': 'India', 'chennai': 'India', 'kolkata': 'India',
        'pune': 'India', 'ahmedabad': 'India',
        'beijing': 'China', 'shanghai': 'China', 'shenzhen': 'China',
        'guangzhou': 'China', 'hong kong': 'Hong Kong',
        'taipei': 'Taiwan', 'seoul': 'South Korea', 'busan': 'South Korea',
        'bangkok': 'Thailand', 'ho chi minh city': 'Vietnam',
        'hanoi': 'Vietnam', 'jakarta': 'Indonesia', 'kuala lumpur': 'Malaysia',
        'manila': 'Philippines', 'cairo': 'Egypt', 'johannesburg': 'South Africa',
        'cape town': 'South Africa', 'nairobi': 'Kenya', 'lagos': 'Nigeria',
        'casablanca': 'Morocco', 'mexico city': 'Mexico',
        'sao paulo': 'Brazil', 'rio de janeiro': 'Brazil',
        'buenos aires': 'Argentina', 'santiago': 'Chile',
        'bogota': 'Colombia', 'lima': 'Peru',
    }

    # Try "City, State, Country" or "City, Country" patterns
    parts = [p.strip() for p in text.split(',')]

    city = None
    state = None
    country = None
    confidence = None

    if len(parts) >= 3:
        # e.g. "Las Vegas, NV, USA" or "Austin, Texas, United States"
        city = parts[0].strip()
        mid = parts[1].strip()
        last = parts[2].strip()

        # Check if mid is a state
        if mid in state_map:
            state = state_map[mid]
        elif mid.upper() in state_map:
            state = state_map[mid.upper()]
        elif mid in state_map.values():
            state = mid

        # Check if last is a country
        country = country_aliases.get(last, country_aliases.get(last.upper(), last))
        confidence = 'GEO_CONFIRMED' if state else 'GEO_PARTIAL'

    elif len(parts) == 2:
        # e.g. "Las Vegas, USA" or "Vienna, Austria"
        city = parts[0].strip()
        last = parts[1].strip()

        # Check if last is a state abbreviation
        if last in state_map:
            state = state_map[last]
            country = 'United States'
            confidence = 'GEO_CONFIRMED'
        elif last.upper() in state_map:
            state = state_map[last.upper()]
            country = 'United States'
            confidence = 'GEO_CONFIRMED'
        else:
            country = country_aliases.get(last, country_aliases.get(last.upper(), last))
            confidence = 'GEO_PARTIAL'

    elif len(parts) == 1:
        # Single value — could be a city name
        single = parts[0].strip().lower()
        if single in city_country:
            city = parts[0].strip()
            country = city_country[single]
            confidence = 'GEO_PARTIAL'
        else:
            # Try as country
            country = country_aliases.get(parts[0].strip(), parts[0].strip())
            confidence = 'GEO_UNKNOWN'

    if city or country:
        return city, state, country, confidence or 'GEO_UNKNOWN'

    return None, None, None, None


def _enrich_worker(job_id: str, db_path: str, run_id: str, enrich_types: list):
    """Background worker for enrichment."""
    import threading

    def _run():
        try:
            _set_job(job_id, {"status": "running", "message": "Enriching..."})
            result = _run_enrichment(db_path, run_id, enrich_types)
            _set_job(job_id, {"status": "completed", "result": result, "message": f"Enriched {result.get('enriched', 0)} rows"})
        except Exception as e:
            _set_job(job_id, {"status": "failed", "error": str(e)})

    threading.Thread(target=_run, daemon=True).start()


def _canonicalize_url(url: str) -> str:
    raw = (url or "").strip()
    if not raw:
        return ""
    try:
        p = urlsplit(raw)
        scheme = (p.scheme or "https").lower()
        netloc = (p.netloc or "").lower()
        # Strip www. prefix for deduplication
        if netloc.startswith("www."):
            netloc = netloc[4:]
        path = re.sub(r"/{2,}", "/", p.path or "")
        if path.endswith("/") and path != "/":
            path = path[:-1]
        return urlunsplit((scheme, netloc, path, "", ""))
    except Exception:
        return raw.rstrip("/")


def _multi_model_fixture_results(market: str) -> Dict[str, Dict[str, List[Dict[str, str]]]]:
    mkt = (market or "general").strip()
    # Fixture sets intentionally overlap to exercise dedupe + provenance logic.
    return {
        "perplexity": {
            "conference": [
                {"url": "https://www.blackhat.com/", "title": f"{mkt} conference source - Black Hat"},
                {"url": "https://www.rsaconference.com/", "title": f"{mkt} conference source - RSA Conference"},
                {"url": "https://www.sans.org/cyber-security-training-events/", "title": f"{mkt} conference source - SANS events"},
                {"url": "https://www.gartner.com/en/conferences", "title": f"{mkt} conference source - Gartner conferences"},
            ],
            "award": [
                {"url": "https://cybersecurity-excellence-awards.com/", "title": f"{mkt} awards source - Cybersecurity Excellence Awards"},
                {"url": "https://globeeawards.com/cyber-security-awards/", "title": f"{mkt} awards source - Globee Cyber Security Awards"},
                {"url": "https://www.scawards.com/", "title": f"{mkt} awards source - SC Awards"},
            ],
        },
        "chatgpt": {
            "conference": [
                {"url": "https://www.rsaconference.com/", "title": f"{mkt} conference source - RSA Conference"},
                {"url": "https://www.gartner.com/en/conferences", "title": f"{mkt} conference source - Gartner conferences"},
                {"url": "https://www.infosecurityeurope.com/", "title": f"{mkt} conference source - Infosecurity Europe"},
                {"url": "https://www.securityweek.com/category/events/", "title": f"{mkt} conference source - SecurityWeek events"},
            ],
            "award": [
                {"url": "https://www.scawards.com/", "title": f"{mkt} awards source - SC Awards"},
                {"url": "https://www.csoonline.com/awards/", "title": f"{mkt} awards source - CSO Awards"},
                {"url": "https://cybersecurity-excellence-awards.com/", "title": f"{mkt} awards source - Cybersecurity Excellence Awards"},
            ],
        },
        "gemini": {
            "conference": [
                {"url": "https://www.blackhat.com/", "title": f"{mkt} conference source - Black Hat"},
                {"url": "https://www.infosecurityeurope.com/", "title": f"{mkt} conference source - Infosecurity Europe"},
                {"url": "https://events.nist.gov/", "title": f"{mkt} conference source - NIST events"},
                {"url": "https://www.eventbrite.com/d/online/cybersecurity-conference/", "title": f"{mkt} conference source - Eventbrite cybersecurity conferences"},
            ],
            "award": [
                {"url": "https://globeeawards.com/cyber-security-awards/", "title": f"{mkt} awards source - Globee Cyber Security Awards"},
                {"url": "https://www.csoonline.com/awards/", "title": f"{mkt} awards source - CSO Awards"},
                {"url": "https://www.topinfosecinnovator.com/awards/", "title": f"{mkt} awards source - Top InfoSec Innovator Awards"},
            ],
        },
    }


def _extract_urls_from_duckduckgo_html(html_text: str, limit: int = 12) -> List[str]:
    if not html_text:
        return []
    out: List[str] = []
    # DuckDuckGo html results commonly encode target in /l/?uddg=...
    for m in re.finditer(r'href="([^"]+)"', html_text):
        href = m.group(1)
        url = ""
        if "uddg=" in href:
            try:
                q = parse_qs(urlsplit(href).query)
                uddg = q.get("uddg", [""])[0]
                url = unquote(uddg or "").strip()
            except Exception:
                url = ""
        elif href.startswith("http://") or href.startswith("https://"):
            url = href.strip()
        if not url:
            continue
        c = _canonicalize_url(url)
        if not c:
            continue
        if any(c.startswith(prefix) for prefix in ("https://duckduckgo.com", "http://duckduckgo.com")):
            continue
        if c not in out:
            out.append(c)
        if len(out) >= limit:
            break
    return out


def _live_discovery_results(
    market: str,
    provider: str,
    record_type: str,
    conf_prompt: str,
    award_prompt: str,
) -> Dict[str, List[Dict[str, str]]]:
    # Lightweight live discovery via public web query endpoint per provider lane.
    # Provider name is used as a lane/provenance key while query text is shared.
    mkt = (market or "").strip() or "general"
    rt = (record_type or "both").strip().lower()
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; PRMonitor/1.0; +https://localhost)"
    }

    def run_query(q: str) -> List[str]:
        resp = requests.get(
            "https://duckduckgo.com/html/",
            params={"q": q},
            headers=headers,
            timeout=20,
        )
        resp.raise_for_status()
        return _extract_urls_from_duckduckgo_html(resp.text, limit=12)

    conf_results: List[Dict[str, str]] = []
    award_results: List[Dict[str, str]] = []

    if rt in {"both", "conference"}:
        conf_queries = [
            f"{mkt} conference official site",
            f"{mkt} summit 2026 call for papers",
            conf_prompt[:220] if conf_prompt else "",
        ]
        conf_urls: List[str] = []
        for q in conf_queries:
            q = (q or "").strip()
            if not q:
                continue
            try:
                conf_urls.extend(run_query(q))
            except Exception:
                continue
        for u in list(dict.fromkeys(conf_urls))[:8]:
            conf_results.append({"url": u, "title": f"{mkt} conference source - {provider}"})

    if rt in {"both", "award"}:
        award_queries = [
            f"{mkt} awards official site",
            f"{mkt} awards nominations",
            award_prompt[:220] if award_prompt else "",
        ]
        award_urls: List[str] = []
        for q in award_queries:
            q = (q or "").strip()
            if not q:
                continue
            try:
                award_urls.extend(run_query(q))
            except Exception:
                continue
        for u in list(dict.fromkeys(award_urls))[:8]:
            award_results.append({"url": u, "title": f"{mkt} awards source - {provider}"})

    return {"conference": conf_results, "award": award_results}


@app.post("/api/pr-monitor-1/multi-model-discovery")
async def pr_monitor_1_multi_model_discovery(payload: dict):
    market = str(payload.get("market_focus") or payload.get("market") or "").strip()
    if not market:
        raise HTTPException(status_code=400, detail="market_focus is required")

    dry_run = bool(payload.get("dry_run", False))
    providers_raw = payload.get("providers") or ["perplexity", "chatgpt", "gemini"]
    providers = []
    for p in providers_raw if isinstance(providers_raw, list) else [providers_raw]:
        v = str(p).strip().lower()
        if v in {"perplexity", "chatgpt", "gemini"} and v not in providers:
            providers.append(v)
    if not providers:
        providers = ["perplexity", "chatgpt", "gemini"]

    prompt_pack_result = await pr_monitor_1_prompt_pack(payload)
    prompts = (prompt_pack_result.get("prompts") or {})
    record_type = str(payload.get("record_type") or "both").strip().lower()

    fixture = _multi_model_fixture_results(market)

    async def _run_provider(provider: str):
        await asyncio.sleep(0)  # keep orchestration async/parallel-safe
        provider_error = ""
        if dry_run:
            result = fixture.get(provider, {"conference": [], "award": []})
        else:
            try:
                result = _live_discovery_results(
                    market=market,
                    provider=provider,
                    record_type=record_type,
                    conf_prompt=prompts.get("conference_discovery", ""),
                    award_prompt=prompts.get("award_discovery", ""),
                )
            except Exception as e:
                provider_error = str(e)
                result = {"conference": [], "award": []}
        return {
            "provider": provider,
            "dry_run": dry_run,
            "conference_results": result["conference"],
            "award_results": result["award"],
            "conference_prompt_used": prompts.get("conference_discovery", ""),
            "award_prompt_used": prompts.get("award_discovery", ""),
            "result_count": len(result["conference"]) + len(result["award"]),
            "error": provider_error,
        }

    provider_results = await asyncio.gather(*[_run_provider(p) for p in providers])

    merged: Dict[str, Dict[str, Any]] = {}
    for pr in provider_results:
        provider = pr["provider"]
        for item_type, items in (("conference", pr["conference_results"]), ("award", pr["award_results"])):
            for item in items:
                canonical = _canonicalize_url(item.get("url", ""))
                if not canonical:
                    continue
                row = merged.setdefault(
                    canonical,
                    {
                        "url": canonical,
                        "title": item.get("title", ""),
                        "types": set(),
                        "found_by_models": set(),
                        "evidence_notes": [],
                    },
                )
                row["types"].add(item_type)
                row["found_by_models"].add(provider)
                row["evidence_notes"].append(f"{provider}:{item_type}")
                if not row.get("title") and item.get("title"):
                    row["title"] = item["title"]

    master_list = []
    for _, row in sorted(merged.items(), key=lambda kv: kv[0]):
        found_by = sorted(list(row["found_by_models"]))
        confidence_score = round(min(1.0, 0.34 * len(found_by)), 2)
        master_list.append(
            {
                "url": row["url"],
                "title": row["title"],
                "type": "both" if row["types"] == {"conference", "award"} else next(iter(row["types"])),
                "found_by_models": found_by,
                "confidence_score": confidence_score,
                "dedupe_status": "deduped_multi_source" if len(found_by) > 1 else "single_source",
                "evidence_notes": row["evidence_notes"],
            }
        )

    overlap = {}
    for pr in provider_results:
        pset = set()
        for item in pr["conference_results"] + pr["award_results"]:
            c = _canonicalize_url(item.get("url", ""))
            if c:
                pset.add(c)
        overlap[pr["provider"]] = pset

    pairwise_overlap = {}
    plist = [pr["provider"] for pr in provider_results]
    for i in range(len(plist)):
        for j in range(i + 1, len(plist)):
            a, b = plist[i], plist[j]
            pairwise_overlap[f"{a}__{b}"] = len(overlap.get(a, set()) & overlap.get(b, set()))

    base_dir = get_pr_monitor_settings().runtime_root
    out_dir = base_dir / "discovery_jobs"
    provider_dir = base_dir / "provider_lists"
    master_dir = base_dir / "master_lists"
    source_set_dir = get_pr_monitor_settings().source_sets_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    provider_dir.mkdir(parents=True, exist_ok=True)
    master_dir.mkdir(parents=True, exist_ok=True)
    source_set_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    job_id = f"mmd_{stamp}"
    out_path = out_dir / f"{job_id}.json"
    payload_out = {
        "ok": True,
        "job_id": job_id,
        "dry_run": dry_run,
        "providers": providers,
        "prompt_pack_id": prompt_pack_result.get("prompt_pack_id"),
        "provider_results": provider_results,
        "comparison": {
            "pairwise_overlap_counts": pairwise_overlap,
            "unique_master_urls": len(master_list),
            "providers_count": len(providers),
        },
        "master_list": master_list,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    out_path.write_text(json.dumps(payload_out, indent=2), encoding="utf-8")

    # Persist canonical master list artifacts for downstream extraction.
    master_urls = [row["url"] for row in master_list if str(row.get("url") or "").strip()]
    master_txt_path = master_dir / f"master_list_{job_id}.txt"
    master_txt_path.write_text(("\n".join(master_urls) + "\n") if master_urls else "", encoding="utf-8")

    latest_master_txt_path = master_dir / "master_list_latest.txt"
    latest_master_txt_path.write_text(master_txt_path.read_text(encoding="utf-8"), encoding="utf-8")

    # Save into source_sets folder so it can be used as the current master source set.
    source_set_master_path = source_set_dir / f"master_list_{job_id}.txt"
    source_set_master_path.write_text(master_txt_path.read_text(encoding="utf-8"), encoding="utf-8")
    source_set_master_latest_path = source_set_dir / "master_list_latest.txt"
    source_set_master_latest_path.write_text(master_txt_path.read_text(encoding="utf-8"), encoding="utf-8")

    # Persist each independent model list for performance/outlier analysis.
    provider_artifacts = {}
    for pr in provider_results:
        provider = str(pr.get("provider") or "").strip().lower()
        if not provider:
            continue
        model_urls = []
        for item in (pr.get("conference_results") or []) + (pr.get("award_results") or []):
            canonical = _canonicalize_url(item.get("url", ""))
            if canonical:
                model_urls.append(canonical)
        model_urls = list(dict.fromkeys(model_urls))

        provider_json_path = provider_dir / f"{job_id}_{provider}.json"
        provider_txt_path = provider_dir / f"{job_id}_{provider}.txt"
        provider_payload = {
            "job_id": job_id,
            "provider": provider,
            "url_count": len(model_urls),
            "urls": model_urls,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
        provider_json_path.write_text(json.dumps(provider_payload, indent=2), encoding="utf-8")
        provider_txt_path.write_text(("\n".join(model_urls) + "\n") if model_urls else "", encoding="utf-8")

        provider_artifacts[provider] = {
            "json": str(provider_json_path),
            "txt": str(provider_txt_path),
            "url_count": len(model_urls),
        }

    payload_out["path"] = str(out_path)
    payload_out["artifacts"] = {
        "master_list_job_txt": str(master_txt_path),
        "master_list_latest_txt": str(latest_master_txt_path),
        "source_set_master_job_txt": str(source_set_master_path),
        "source_set_master_latest_txt": str(source_set_master_latest_path),
        "provider_lists": provider_artifacts,
    }
    return payload_out


@app.get("/api/pr-monitor-1/latest")
async def pr_monitor_1_latest():
    db = str(get_pr_monitor_settings().db_path)
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            """
            SELECT run_id, mode, started_at, completed_at, rows_scanned, rows_inserted, rows_updated,
                   rows_flagged, ai_calls, total_ai_cost, avg_confidence
            FROM pipeline_runs
            WHERE status='completed'
            ORDER BY started_at DESC
            LIMIT 1
            """
        ).fetchone()
        if not row:
            return {"ok": True, "run": None}
        run = dict(row)
        skipped = conn.execute(
            "SELECT COUNT(*) FROM run_row_audit WHERE run_id=? AND skip_reason='same_day_already_processed'",
            (run["run_id"],),
        ).fetchone()[0]
        run["rows_skipped_same_day"] = skipped
        return {"ok": True, "run": run}
    finally:
        conn.close()


@app.get("/api/pr-monitor-1/runs")
async def pr_monitor_1_runs(limit: int = 20):
    db = str(get_pr_monitor_settings().db_path)
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    try:
        row_limit = max(1, min(int(limit or 20), 200))
        rows = conn.execute(
            """
            SELECT run_id, mode, started_at, completed_at, rows_scanned, rows_inserted, rows_updated,
                   rows_flagged, ai_calls, total_ai_cost, avg_confidence
            FROM pipeline_runs
            WHERE status='completed'
            ORDER BY started_at DESC
            LIMIT ?
            """,
            (row_limit,),
        ).fetchall()
        runs = []
        for r in rows:
            d = dict(r)
            d["rows_skipped_same_day"] = conn.execute(
                "SELECT COUNT(*) FROM run_row_audit WHERE run_id=? AND skip_reason='same_day_already_processed'",
                (d["run_id"],),
            ).fetchone()[0]
            d["rows_with_results"] = conn.execute(
                """
                SELECT COUNT(*)
                FROM run_row_audit a
                LEFT JOIN conference_events e ON e.event_key = a.event_key AND e.run_id = a.run_id
                WHERE a.run_id = ?
                  AND (
                    coalesce(trim(a.cfp_status),'')<>'' OR coalesce(trim(a.cfp_deadline),'')<>'' OR coalesce(trim(a.conf_dates),'')<>''
                    OR coalesce(trim(e.cfp_status),'')<>'' OR coalesce(trim(e.cfp_deadline),'')<>'' OR coalesce(trim(e.conf_dates),'')<>''
                  )
                """,
                (d["run_id"],),
            ).fetchone()[0]
            d["rows_null_results"] = max(0, int(d.get("rows_scanned") or 0) - int(d["rows_with_results"]))
            runs.append(d)
        return {"ok": True, "runs": runs}
    finally:
        conn.close()


@app.get("/api/pr-monitor-1/run/{run_id}/rows")
async def pr_monitor_1_run_rows(
    run_id: str,
    qa_status: str = "",
    ai_called: str = "",
    changed_only: str = "false",
    has_cfp_or_dates: str = "false",
    deadline_urgency: str = "",
    action_state: str = "",
    domain_contains: str = "",
    limit: int = 500,
):
    db = str(get_pr_monitor_settings().db_path)
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    try:
        where = ["a.run_id = ?"]
        params = [run_id]

        if qa_status:
            where.append("coalesce(a.qa_status,'') = ?")
            params.append(qa_status)
        if ai_called in {"0", "1"}:
            where.append("a.ai_called = ?")
            params.append(int(ai_called))
        if str(changed_only).lower() == "true":
            where.append("coalesce(a.changed_fields,'') <> '' AND coalesce(a.changed_fields,'') <> 'no_material_change'")
        if str(has_cfp_or_dates).lower() == "true":
            where.append("(coalesce(trim(a.cfp_status),'')<>'' OR coalesce(trim(a.cfp_deadline),'')<>'' OR coalesce(trim(a.conf_dates),'')<>'' OR coalesce(trim(e.cfp_status),'')<>'' OR coalesce(trim(e.cfp_deadline),'')<>'' OR coalesce(trim(e.conf_dates),'')<>'')")
        if domain_contains:
            where.append("lower(coalesce(a.domain,'')) LIKE ?")
            params.append(f"%{domain_contains.lower()}%")

        row_limit = max(1, min(int(limit or 500), 2000))
        audit_cols = {r[1] for r in conn.execute("PRAGMA table_info(run_row_audit)").fetchall()}
        event_cols = {r[1] for r in conn.execute("PRAGMA table_info(conference_events)").fetchall()}
        change_diffs_expr = "a.change_diffs" if "change_diffs" in audit_cols else "NULL"
        change_checked_at_expr = "a.change_checked_at" if "change_checked_at" in audit_cols else "NULL"
        geo_city_expr = "e.geo_city" if "geo_city" in event_cols else "NULL"
        geo_state_expr = "e.geo_state" if "geo_state" in event_cols else "NULL"
        geo_country_expr = "e.geo_country" if "geo_country" in event_cols else "NULL"
        geo_confidence_status_expr = "e.geo_confidence_status" if "geo_confidence_status" in event_cols else "NULL"
        cfp_deadline_normalized_expr = "coalesce(a.cfp_deadline_normalized, e.cfp_deadline_normalized)" if "cfp_deadline_normalized" in audit_cols and "cfp_deadline_normalized" in event_cols else "NULL"
        deadline_urgency_expr = "coalesce(a.deadline_urgency, e.deadline_urgency)" if "deadline_urgency" in audit_cols and "deadline_urgency" in event_cols else "NULL"
        action_state_expr = "coalesce(a.action_state, e.action_state)" if "action_state" in audit_cols and "action_state" in event_cols else "NULL"
        q = f"""
        SELECT a.run_id, a.created_at, a.event_key, a.domain, a.conf_page_url, a.conference_name,
               a.qa_status, a.extract_confidence, a.ai_called, a.changed_fields,
               {change_diffs_expr} as change_diffs, {change_checked_at_expr} as change_checked_at, a.skip_reason,
               coalesce(a.cfp_status, e.cfp_status) as cfp_status,
               coalesce(a.cfp_deadline, e.cfp_deadline) as cfp_deadline,
               {cfp_deadline_normalized_expr} as cfp_deadline_normalized,
               {deadline_urgency_expr} as deadline_urgency,
               {action_state_expr} as action_state,
               coalesce(a.conf_dates, e.conf_dates) as conf_dates,
               e.conf_location, e.run_id as event_run_id
        FROM run_row_audit a
        LEFT JOIN conference_events e ON e.event_key = a.event_key AND e.run_id = a.run_id
        WHERE {' AND '.join(where)}
        ORDER BY a.created_at DESC, a.domain ASC
        LIMIT {row_limit}
        """
        rows = [dict(r) for r in conn.execute(q, params).fetchall()]
        if event_cols and {"geo_city", "geo_state", "geo_country", "geo_confidence_status"} <= event_cols and rows:
            try:
                unique_keys = list({(r.get("domain") or "", r.get("conf_page_url") or "") for r in rows})
                geo_map: Dict[tuple, Dict[str, str]] = {}
                if unique_keys:
                    placeholders = ",".join(["(?,?)"] * len(unique_keys))
                    geo_sql = f"""
                        SELECT domain, conf_page_url, geo_city, geo_state, geo_country, geo_confidence_status
                        FROM conference_events
                        WHERE (domain, conf_page_url) IN ({placeholders})
                        AND updated_at = (
                            SELECT MAX(updated_at) FROM conference_events e2
                            WHERE e2.domain = conference_events.domain AND e2.conf_page_url = conference_events.conf_page_url
                        )
                    """
                    geo_params = [v for key in unique_keys for v in key]
                    for r in conn.execute(geo_sql, geo_params):
                        geo_map[(r[0], r[1])] = {
                            "geo_city": r[2],
                            "geo_state": r[3],
                            "geo_country": r[4],
                            "geo_confidence_status": r[5],
                        }
                for row in rows:
                    if not row.get("geo_city"):
                        key = (row.get("domain") or "", row.get("conf_page_url") or "")
                        match = geo_map.get(key)
                        if match and match.get("geo_city"):
                            row["geo_city"] = match["geo_city"]
                            row["geo_state"] = match["geo_state"]
                            row["geo_country"] = match["geo_country"]
                            row["geo_confidence_status"] = match["geo_confidence_status"]
            except Exception as exc:
                logger.warning("geo fallback enrichment failed: %s", exc, exc_info=True)
        for row in rows:
            if isinstance(row.get("change_diffs"), str) and row.get("change_diffs"):
                try:
                    row["change_diffs"] = json.loads(row["change_diffs"])
                except Exception:
                    pass
        rows = _enrich_pr_monitor_rows_with_deadline_intelligence(rows)
        if deadline_urgency:
            rows = [row for row in rows if str(row.get("deadline_urgency") or "") == deadline_urgency]
        if action_state:
            rows = [row for row in rows if str(row.get("action_state") or "") == action_state]
        rows = _enrich_pr_monitor_rows_with_source_history(rows)
        return {"ok": True, "run_id": run_id, "count": len(rows), "rows": rows}
    finally:
        conn.close()


@app.get("/api/pr-monitor-1/portfolio/latest")
async def pr_monitor_1_portfolio_latest(
    market: list[str] = Query(default=[]),
    customer: str = "default_customer",
    has_cfp_or_dates: str = "true",
    deadline_urgency: str = "",
    action_state: str = "",
    limit: int = 500,
):
    db = str(get_pr_monitor_settings().db_path)
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    try:
        row_limit = max(1, min(int(limit or 500), 2000))
        where = ["1=1"]
        params = []
        market_filters = [m.strip().lower() for m in (market or []) if m.strip()]
        if market_filters:
            placeholders = ",".join(["?" for _ in market_filters])
            where.append(f"lower(coalesce(market,'')) IN ({placeholders})")
            params.extend(market_filters)
        if customer:
            where.append("lower(coalesce(customer,'')) = ?")
            params.append(customer.lower())
        if str(has_cfp_or_dates).lower() == "true":
            where.append("(coalesce(trim(cfp_status),'')<>'' OR coalesce(trim(cfp_deadline),'')<>'' OR coalesce(trim(conf_dates),'')<>'')")

        q = f"""
        SELECT * FROM conference_events e
        WHERE {' AND '.join(where)}
          AND updated_at = (
            SELECT MAX(updated_at) FROM conference_events e2 WHERE e2.event_key = e.event_key
          )
        ORDER BY updated_at DESC
        LIMIT {row_limit}
        """
        rows = [dict(r) for r in conn.execute(q, params).fetchall()]
        for row in rows:
            if isinstance(row.get("change_diffs"), str) and row.get("change_diffs"):
                try:
                    row["change_diffs"] = json.loads(row["change_diffs"])
                except Exception:
                    pass
        rows = _enrich_pr_monitor_rows_with_deadline_intelligence(rows)
        if deadline_urgency:
            rows = [row for row in rows if str(row.get("deadline_urgency") or "") == deadline_urgency]
        if action_state:
            rows = [row for row in rows if str(row.get("action_state") or "") == action_state]
        rows = _enrich_pr_monitor_rows_with_source_history(rows)
        return {"ok": True, "count": len(rows), "rows": rows}
    finally:
        conn.close()


@app.get("/api/pr-monitor-1/portfolio/export-csv")
async def pr_monitor_1_portfolio_export_csv(
    market: str = "hydrogen",
    customer: str = "default_customer",
    has_cfp_or_dates: str = "true",
    upcoming_only: str = "false",
    limit: int = 5000,
):
    import io
    import re
    from datetime import datetime, timezone

    def _parse_conf_start_date(value: str):
        s = (value or "").strip()
        if not s:
            return None

        m = re.search(r"\b(20\d{2})-(\d{1,2})-(\d{1,2})\b", s)
        if m:
            try:
                return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), tzinfo=timezone.utc).date()
            except Exception:
                pass

        m = re.search(r"\b(\d{1,2})/(\d{1,2})/(20\d{2})\b", s)
        if m:
            try:
                return datetime(int(m.group(3)), int(m.group(1)), int(m.group(2)), tzinfo=timezone.utc).date()
            except Exception:
                pass

        m = re.search(r"\b([A-Za-z]{3,9})\.?\s+(\d{1,2})(?:\s*[-–]\s*\d{1,2})?(?:,)?\s*(20\d{2})\b", s, flags=re.I)
        if m:
            mon = m.group(1).lower()
            months = {
                "january":1,"jan":1,"february":2,"feb":2,"march":3,"mar":3,"april":4,"apr":4,"may":5,
                "june":6,"jun":6,"july":7,"jul":7,"august":8,"aug":8,"september":9,"sep":9,"sept":9,
                "october":10,"oct":10,"november":11,"nov":11,"december":12,"dec":12
            }
            if mon in months:
                try:
                    return datetime(int(m.group(3)), months[mon], int(m.group(2)), tzinfo=timezone.utc).date()
                except Exception:
                    pass
        return None

    db = str(get_pr_monitor_settings().db_path)
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    try:
        row_limit = max(1, min(int(limit or 5000), 20000))
        where = ["1=1"]
        params = []
        if market:
            where.append("lower(coalesce(market,'')) = ?")
            params.append(market.lower())
        if customer:
            where.append("lower(coalesce(customer,'')) = ?")
            params.append(customer.lower())
        if str(has_cfp_or_dates).lower() == "true":
            where.append("(coalesce(trim(cfp_status),'')<>'' OR coalesce(trim(cfp_deadline),'')<>'' OR coalesce(trim(conf_dates),'')<>'')")

        q = f"""
        SELECT * FROM conference_events e
        WHERE {' AND '.join(where)}
          AND updated_at = (
            SELECT MAX(updated_at) FROM conference_events e2 WHERE e2.event_key = e.event_key
          )
        ORDER BY updated_at DESC
        LIMIT {row_limit}
        """
        rows = [dict(r) for r in conn.execute(q, params).fetchall()]

        if str(upcoming_only).lower() == "true":
            today = datetime.now(timezone.utc).date()
            rows = [r for r in rows if (_parse_conf_start_date(r.get("conf_dates")) is not None and _parse_conf_start_date(r.get("conf_dates")) >= today)]

        def _normalize_text(v):
            if not isinstance(v, str):
                return v
            # Fix common mojibake artifacts seen in conference date ranges and punctuation
            replacements = {
                "â€“": "–",  # en dash
                "â€”": "—",  # em dash
                "â€™": "’",
                "â€œ": "“",
                "â€": "”",
                "Â ": " ",
                "Â": "",
            }
            out = v
            for bad, good in replacements.items():
                out = out.replace(bad, good)
            return out

        cleaned_rows = []
        for r in rows:
            cleaned_rows.append({k: _normalize_text(v) for k, v in r.items()})

        output = io.StringIO()
        if cleaned_rows:
            fieldnames = list(cleaned_rows[0].keys())
            writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(cleaned_rows)
        else:
            writer = csv.writer(output)
            writer.writerow(["no_data"])

        # UTF-8 BOM helps Excel detect encoding correctly
        csv_bytes = ("\ufeff" + output.getvalue()).encode("utf-8")
        filename = f"pr_monitor_1_{(market or 'all').strip() or 'all'}_latest.csv"
        headers = {
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Type": "text/csv; charset=utf-8",
        }
        return Response(content=csv_bytes, media_type="text/csv", headers=headers)
    finally:
        conn.close()


@app.get("/api/pr-monitor-1-review/markets")
async def pr_monitor_1_review_markets():
    """Return list of distinct markets in the conference_events table."""
    db = str(get_pr_monitor_settings().db_path)
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT DISTINCT market, COUNT(*) as cnt FROM conference_events "
            "WHERE market IS NOT NULL AND market != '' "
            "GROUP BY market ORDER BY cnt DESC"
        ).fetchall()
        markets = [{"market": r["market"], "count": r["cnt"]} for r in rows]
        return {"ok": True, "markets": markets}
    finally:
        conn.close()


@app.get("/api/pr-monitor-1-review/portfolio/latest")
async def pr_monitor_1_review_portfolio_latest(
    market: list[str] = Query(default=[]),
    customer: str = "default_customer",
    deadline_urgency: str = "",
    action_state: str = "",
    limit: int = 500,
    debug: bool = False,
):
    db = str(get_pr_monitor_settings().db_path)
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    try:
        row_limit = max(1, min(int(limit or 500), 2000))
        market_filters = [m.strip().lower() for m in (market or []) if m.strip()]
        customer_filter = (customer or "default_customer").strip().lower()

        # Build WHERE clause - support empty market for "all markets"
        where_parts = [
            "e.updated_at = (SELECT MAX(updated_at) FROM conference_events e2 WHERE e2.event_key = e.event_key)"
        ]
        params: list = []
        if market_filters:
            placeholders = ",".join(["?" for _ in market_filters])
            where_parts.append(f"lower(coalesce(e.market,'')) IN ({placeholders})")
            params.extend(market_filters)
        if customer_filter:
            where_parts.append("lower(coalesce(e.customer,'')) = ?")
            params.append(customer_filter)

        where_clause = " AND ".join(where_parts)

        q = f"""
        SELECT
          e.*,
          r.review_status,
          r.override_cfp_status,
          r.override_cfp_deadline,
          r.override_conf_dates,
          r.review_notes,
          r.reviewed_by,
          r.reviewed_at,
          coalesce(r.submission_status, 'not_submitted') as submission_status,
          CASE WHEN coalesce(trim(r.override_cfp_status),'')<>'' THEN 1 ELSE 0 END as has_override_cfp_status,
          CASE WHEN coalesce(trim(r.override_cfp_deadline),'')<>'' THEN 1 ELSE 0 END as has_override_cfp_deadline,
          CASE WHEN coalesce(trim(r.override_conf_dates),'')<>'' THEN 1 ELSE 0 END as has_override_conf_dates
        FROM conference_events e
        LEFT JOIN conference_event_reviews r
          ON r.event_key = e.event_key
         AND lower(coalesce(r.market,'')) = lower(coalesce(e.market,''))
         AND lower(coalesce(r.customer,'')) = lower(coalesce(e.customer,''))
        WHERE {where_clause}
        ORDER BY e.market ASC, e.updated_at DESC
        LIMIT {row_limit}
        """
        rows = [dict(r) for r in conn.execute(q, params).fetchall()]
        rows = _enrich_pr_monitor_rows_with_deadline_intelligence(rows)
        if deadline_urgency:
            rows = [row for row in rows if str(row.get("deadline_urgency") or "") == deadline_urgency]
        if action_state:
            rows = [row for row in rows if str(row.get("action_state") or "") == action_state]
        rows = _enrich_pr_monitor_rows_with_source_history(rows)
        payload: Dict[str, Any] = {"ok": True, "count": len(rows), "rows": rows}
        if debug:
            payload["debug_db_path"] = db
        return payload
    finally:
        conn.close()


@app.post("/api/pr-monitor-1-review/review/upsert")
async def pr_monitor_1_review_upsert(payload: dict):
    from datetime import datetime, timezone

    event_key = str(payload.get("event_key") or "").strip()
    if not event_key:
        raise HTTPException(status_code=400, detail="event_key is required")

    market = str(payload.get("market") or "").strip()
    customer = str(payload.get("customer") or "").strip()
    review_status = str(payload.get("review_status") or "needs_review").strip() or "needs_review"
    override_cfp_status = payload.get("override_cfp_status")
    override_cfp_deadline = payload.get("override_cfp_deadline")
    override_conf_dates = payload.get("override_conf_dates")
    review_notes = payload.get("review_notes")
    reviewed_by = payload.get("reviewed_by")
    reviewed_at = payload.get("reviewed_at") or datetime.now(timezone.utc).isoformat()
    submission_status = str(payload.get("submission_status") or "not_submitted").strip() or "not_submitted"

    db = str(get_pr_monitor_settings().db_path)
    conn = sqlite3.connect(db)
    try:
        conn.execute(
            """
            INSERT INTO conference_event_reviews (
              event_key, market, customer, review_status,
              override_cfp_status, override_cfp_deadline, override_conf_dates,
              review_notes, reviewed_by, reviewed_at, submission_status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
            ON CONFLICT(event_key, market, customer) DO UPDATE SET
              review_status=excluded.review_status,
              override_cfp_status=excluded.override_cfp_status,
              override_cfp_deadline=excluded.override_cfp_deadline,
              override_conf_dates=excluded.override_conf_dates,
              review_notes=excluded.review_notes,
              reviewed_by=excluded.reviewed_by,
              reviewed_at=excluded.reviewed_at,
              submission_status=excluded.submission_status,
              updated_at=datetime('now')
            """,
            (
                event_key, market, customer, review_status,
                override_cfp_status, override_cfp_deadline, override_conf_dates,
                review_notes, reviewed_by, reviewed_at, submission_status,
            ),
        )
        conn.commit()
        return {"ok": True, "event_key": event_key}
    finally:
        conn.close()


@app.get("/api/pr-monitor-1-review/portfolio/export-csv")
async def pr_monitor_1_review_portfolio_export_csv(
    market: list[str] = Query(default=[]),
    customer: str = "default_customer",
    limit: int = 5000,
):
    import io

    db = str(get_pr_monitor_settings().db_path)
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    try:
        row_limit = max(1, min(int(limit or 5000), 20000))
        market_filters = [m.strip().lower() for m in (market or []) if m.strip()]
        customer_filter = (customer or "default_customer").strip().lower()

        where_parts = [
            "e.updated_at = (SELECT MAX(updated_at) FROM conference_events e2 WHERE e2.event_key = e.event_key)"
        ]
        params: list = []
        if market_filters:
            placeholders = ",".join(["?" for _ in market_filters])
            where_parts.append(f"lower(coalesce(e.market,'')) IN ({placeholders})")
            params.extend(market_filters)
        if customer_filter:
            where_parts.append("lower(coalesce(e.customer,'')) = ?")
            params.append(customer_filter)

        where_clause = " AND ".join(where_parts)

        q = f"""
        SELECT
          e.*,
          coalesce(r.review_status, 'needs_review') as review_status,
          r.review_notes,
          r.reviewed_by,
          r.reviewed_at,
          coalesce(r.submission_status, 'not_submitted') as submission_status,
          r.override_cfp_status,
          r.override_cfp_deadline,
          r.override_conf_dates,
          CASE WHEN coalesce(trim(r.override_cfp_status),'')<>'' THEN r.override_cfp_status ELSE e.cfp_status END as effective_cfp_status,
          CASE WHEN coalesce(trim(r.override_cfp_deadline),'')<>'' THEN r.override_cfp_deadline ELSE e.cfp_deadline END as effective_cfp_deadline,
          CASE WHEN coalesce(trim(r.override_conf_dates),'')<>'' THEN r.override_conf_dates ELSE e.conf_dates END as effective_conf_dates
        FROM conference_events e
        LEFT JOIN conference_event_reviews r
          ON r.event_key = e.event_key
         AND lower(coalesce(r.market,'')) = lower(coalesce(e.market,''))
         AND lower(coalesce(r.customer,'')) = lower(coalesce(e.customer,''))
        WHERE {where_clause}
        ORDER BY e.market ASC, e.updated_at DESC
        LIMIT {row_limit}
        """
        rows = [dict(r) for r in conn.execute(q, params).fetchall()]
        output = io.StringIO()
        if rows:
            fieldnames = list(rows[0].keys())
            writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
        else:
            writer = csv.writer(output)
            writer.writerow(["no_data"])

        csv_bytes = ("\ufeff" + output.getvalue()).encode("utf-8")
        filename = f"pr_monitor_1_review_{(market or 'all').strip() or 'all'}_latest.csv"
        headers = {
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Type": "text/csv; charset=utf-8",
        }
        return Response(content=csv_bytes, media_type="text/csv", headers=headers)
    finally:
        conn.close()

if __name__ == "__main__":
    import uvicorn
    print(f"🚀 Starting Dashboard Server on port {PORT}")
    print(f"🔒 IP Restrictions: {'ENABLED' if ENABLE_IP_RESTRICTION else 'DISABLED'}")
    print(f"📝 Allowed IPs: {', '.join(ALLOWED_IPS)}")
    uvicorn.run(app, host=APP_HOST, port=PORT)
