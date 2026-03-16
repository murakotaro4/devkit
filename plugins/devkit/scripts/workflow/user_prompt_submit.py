#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import sys


SCRIPT_DIR = __import__("pathlib").Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from workflow_state import ensure_claude_dir, ensure_dig_state, now_timestamp, read_json, sanitize_session_id, state_file_for, write_json


def emit(message: str) -> None:
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": message,
        }
    }
    print(json.dumps(payload, ensure_ascii=False), end="")


def main() -> int:
    try:
        input_text = sys.stdin.read() if not sys.stdin.isatty() else ""
    except Exception:
        input_text = ""

    if not input_text:
        return 0

    try:
        parsed = json.loads(input_text)
    except json.JSONDecodeError:
        return 0

    session_id = sanitize_session_id(str(parsed.get("session_id", ""))) if isinstance(parsed, dict) else ""
    prompt = ""
    if isinstance(parsed, dict):
        prompt = str(parsed.get("prompt", "") or parsed.get("user_prompt", "") or "")

    if not re.match(r"^\s*/dig\b", prompt):
        return 0

    ensure_claude_dir()
    state_path = state_file_for(session_id)
    state = read_json(state_path) or {"workflow_version": 2, "session_id": session_id, "phases_passed": []}
    dig = ensure_dig_state(state)
    dig.update(
        {
            "active": True,
            "topic": prompt.strip(),
            "session_started_at": now_timestamp(),
            "requirements_confirmed": False,
            "ask_user_count": 0,
            "phase4_approved": False,
            "phase5_tasks_registered": False,
            "task_ids": [],
            "task_subjects": [],
            "plan_review_attempts": 0,
            "review_blocked": False,
        }
    )
    write_json(state_path, state)
    emit(
        "[devkit-dig] /dig session detected. Enforce the 7-phase flow. "
        "Do not create Tasks before Phase 4 passes. At Phase 5 start, register [Task 1], [Task 2]... before implementation."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
