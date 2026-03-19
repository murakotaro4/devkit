from __future__ import annotations

import json
import os
import re
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


TASK_SUBJECT_RE = re.compile(r"^\[Task \d+\]\s+")

LEGACY_PHASE_MAP = {
    "plan_review": "plan_review_completed",
    "impl_review": "implementation_review_completed",
    "commit_review": "commit_review_completed",
    "phase_6": "implementation_completed",
}


def sanitize_session_id(raw: str) -> str:
    if not raw:
        return str(uuid.uuid4())
    sanitized = re.sub(r"[^a-zA-Z0-9-]", "", raw)
    return sanitized or str(uuid.uuid4())


def normalize_phase_token(token: str | None) -> str | None:
    if not token or not isinstance(token, str):
        return None
    return LEGACY_PHASE_MAP.get(token, token)


def claude_dir() -> Path:
    return Path(os.environ.get("HOME", "")) / ".claude"


def tasks_dir_for(session_id: str) -> Path:
    return claude_dir() / "tasks" / sanitize_session_id(session_id)


def state_file_for(session_id: str) -> Path:
    return claude_dir() / f"devkit-workflow-{sanitize_session_id(session_id)}.json"


def ensure_claude_dir() -> Path:
    path = claude_dir()
    path.mkdir(parents=True, exist_ok=True)
    return path


def read_json(path: Path) -> dict[str, object] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def append_phase(state: dict[str, Any], token: str) -> None:
    normalized = normalize_phase_token(token)
    if not normalized:
        return

    raw = state.get("phases_passed")
    phases = [item for item in raw if isinstance(item, str)] if isinstance(raw, list) else []
    if normalized not in phases:
        phases.append(normalized)
    state["current_phase_token"] = normalized
    state["phases_passed"] = phases


def default_dig_state() -> dict[str, Any]:
    return {
        "active": False,
        "topic": "",
        "session_started_at": 0.0,
        "requirements_confirmed": False,
        "ask_user_count": 0,
        "phase4_approved": False,
        "phase5_tasks_registered": False,
        "task_ids": [],
        "task_subjects": [],
        "task_id_map": {},
        "task_blockers": {},
        "plan_review_attempts": 0,
        "review_blocked": False,
    }


def ensure_dig_state(state: dict[str, Any]) -> dict[str, Any]:
    raw = state.get("dig")
    dig = dict(raw) if isinstance(raw, dict) else {}
    # 旧キーから新キーへのマイグレーション（v3→v4 互換）
    # merged.update の前に dig 側で変換しないとフィルタで除外される
    if "phase5_approved" in dig and "phase4_approved" not in dig:
        dig["phase4_approved"] = dig.pop("phase5_approved")
    elif "phase5_approved" in dig:
        dig.pop("phase5_approved")
    if "phase6_tasks_registered" in dig and "phase5_tasks_registered" not in dig:
        dig["phase5_tasks_registered"] = dig.pop("phase6_tasks_registered")
    elif "phase6_tasks_registered" in dig:
        dig.pop("phase6_tasks_registered")
    merged = default_dig_state()
    merged.update({key: value for key, value in dig.items() if key in merged})
    if not isinstance(merged.get("task_ids"), list):
        merged["task_ids"] = []
    if not isinstance(merged.get("task_subjects"), list):
        merged["task_subjects"] = []
    if not isinstance(merged.get("task_id_map"), dict):
        merged["task_id_map"] = {}
    if not isinstance(merged.get("task_blockers"), dict):
        merged["task_blockers"] = {}
    state["dig"] = merged
    return merged


def load_task_entries(session_id: str) -> list[dict[str, Any]]:
    task_dir = tasks_dir_for(session_id)
    if not task_dir.exists():
        return []

    entries: list[dict[str, Any]] = []
    for child in sorted(task_dir.glob("*.json")):
        payload = read_json(child)
        if isinstance(payload, dict):
            try:
                payload["_mtime"] = child.stat().st_mtime
            except OSError:
                payload["_mtime"] = 0.0
            entries.append(payload)
    return entries


def sync_dig_tasks_from_store(state: dict[str, Any], session_id: str) -> dict[str, Any]:
    dig = ensure_dig_state(state)
    entries = load_task_entries(session_id)
    session_started_at = dig.get("session_started_at")
    # 1秒のトレランスを差し引く（ファイルシステム mtime と time.time() の微小なずれを吸収）
    started_after = max(0.0, float(session_started_at) - 1.0) if isinstance(session_started_at, (int, float)) else 0.0

    task_ids: list[str] = []
    task_subjects: list[str] = []
    task_id_map: dict[str, str] = {}
    task_blockers: dict[str, list[str]] = {}
    for entry in entries:
        entry_mtime = entry.get("_mtime")
        if started_after and not isinstance(entry_mtime, (int, float)):
            continue
        if started_after and float(entry_mtime) < started_after:
            continue
        subject = entry.get("subject")
        if not isinstance(subject, str):
            continue
        if TASK_SUBJECT_RE.match(subject):
            sys_id = str(entry.get("id", ""))
            task_subjects.append(subject)
            task_ids.append(sys_id)

            m = re.match(r"^(\[Task \d+\])", subject)
            if m and sys_id:
                task_id_map[sys_id] = m.group(1)

            blocked_by = entry.get("blockedBy", [])
            if isinstance(blocked_by, list) and blocked_by:
                task_blockers[sys_id] = [str(b) for b in blocked_by]

    dig["task_ids"] = [item for item in task_ids if item]
    dig["task_subjects"] = task_subjects
    dig["task_id_map"] = task_id_map
    dig["task_blockers"] = task_blockers
    dig["phase5_tasks_registered"] = bool(task_subjects)
    return dig


def now_timestamp() -> float:
    return time.time()


def normalize_state(state: dict[str, object] | None) -> dict[str, object]:
    phases_passed = []
    if isinstance(state, dict):
        raw_phases = state.get("phases_passed")
        if isinstance(raw_phases, list):
            for token in raw_phases:
                normalized = normalize_phase_token(token if isinstance(token, str) else None)
                if normalized:
                    phases_passed.append(normalized)

    deduped: list[str] = []
    for token in phases_passed:
        if token not in deduped:
            deduped.append(token)

    current = ""
    if isinstance(state, dict):
        current = normalize_phase_token(state.get("current_phase_token") if isinstance(state.get("current_phase_token"), str) else None) or ""
    if not current and deduped:
        current = deduped[-1]

    base = dict(state or {})
    base["workflow_version"] = 2
    base["current_phase_token"] = current
    base["phases_passed"] = deduped
    ensure_dig_state(base)
    return base


def cleanup_old_state_files() -> None:
    path = ensure_claude_dir()
    threshold = datetime.now(timezone.utc) - timedelta(hours=24)
    for child in path.iterdir():
        if not child.name.startswith("devkit-workflow-"):
            continue
        try:
            mtime = datetime.fromtimestamp(child.stat().st_mtime, tz=timezone.utc)
            if mtime < threshold:
                child.unlink()
        except Exception:
            continue
