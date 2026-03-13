from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path


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
