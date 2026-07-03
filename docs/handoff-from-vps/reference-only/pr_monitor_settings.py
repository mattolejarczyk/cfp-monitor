"""Environment-backed path settings for the PR Monitor 1 dashboard surface."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


DEFAULT_PROJECT_ROOT = Path("/home/ubuntu/.openclaw/workspace/projects/PR_Firm_Texas")
DEFAULT_DASHBOARD_ROOT = Path("/home/ubuntu/.openclaw/workspace/dashboard")


@dataclass(frozen=True)
class PRMonitorSettings:
    project_root: Path
    dashboard_root: Path
    runtime_root: Path
    source_sets_dir: Path
    db_path: Path
    legacy_runner_path: Path
    batch_processor_path: Path
    crawl_runs_dir: Path
    extract_runs_dir: Path
    discovery_jobs_dir: Path
    provider_lists_dir: Path
    master_lists_dir: Path
    artifacts_dir: Path
    preferences_path: Path
    crawl_engine_metrics_path: Path
    crawl_engine_alerts_path: Path
    source_registry_path: Path


def _path_from_env(name: str, default: Path | str) -> Path:
    return Path(os.environ.get(name, str(default))).expanduser().resolve()


def get_pr_monitor_settings() -> PRMonitorSettings:
    project_root = _path_from_env("PR_MONITOR_PROJECT_ROOT", DEFAULT_PROJECT_ROOT)
    dashboard_root = _path_from_env("PR_MONITOR_DASHBOARD_ROOT", DEFAULT_DASHBOARD_ROOT)
    runtime_root = _path_from_env("PR_MONITOR_RUNTIME_ROOT", project_root / "pr_monitor_1")
    source_sets_dir = _path_from_env("PR_MONITOR_SOURCE_SETS_DIR", project_root / "source_sets_pr_monitor_1")
    db_path = _path_from_env("PR_MONITOR_DB_PATH", project_root / "conference_pipeline.db")
    legacy_runner_path = _path_from_env("PR_MONITOR_LEGACY_RUNNER", project_root / "mvp_conference_db.py")
    batch_processor_path = _path_from_env("PR_MONITOR_BATCH_PROCESSOR", project_root / "batch_processor.py")
    crawl_runs_dir = runtime_root / "crawl_runs"
    extract_runs_dir = runtime_root / "extract_runs"
    discovery_jobs_dir = runtime_root / "discovery_jobs"
    provider_lists_dir = runtime_root / "provider_lists"
    master_lists_dir = runtime_root / "master_lists"
    settings = PRMonitorSettings(
        project_root=project_root,
        dashboard_root=dashboard_root,
        runtime_root=runtime_root,
        source_sets_dir=source_sets_dir,
        db_path=db_path,
        legacy_runner_path=legacy_runner_path,
        batch_processor_path=batch_processor_path,
        crawl_runs_dir=crawl_runs_dir,
        extract_runs_dir=extract_runs_dir,
        discovery_jobs_dir=discovery_jobs_dir,
        provider_lists_dir=provider_lists_dir,
        master_lists_dir=master_lists_dir,
        artifacts_dir=crawl_runs_dir / "artifacts",
        preferences_path=runtime_root / "preferences.json",
        crawl_engine_metrics_path=runtime_root / "crawl_engine_metrics.json",
        crawl_engine_alerts_path=runtime_root / "crawl_engine_alerts.jsonl",
        source_registry_path=_path_from_env("PR_MONITOR_SOURCE_REGISTRY", runtime_root / "source_registry.json"),
    )
    try:
        print(f"[PRMONITOR] db_path={settings.db_path}")
    except Exception:
        pass
    return settings


def ensure_runtime_dirs(settings: PRMonitorSettings | None = None) -> None:
    s = settings or get_pr_monitor_settings()
    for path in (
        s.runtime_root,
        s.source_sets_dir,
        s.crawl_runs_dir,
        s.artifacts_dir,
        s.extract_runs_dir,
        s.discovery_jobs_dir,
        s.provider_lists_dir,
        s.master_lists_dir,
    ):
        path.mkdir(parents=True, exist_ok=True)
