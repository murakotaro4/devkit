#!/usr/bin/env python3
from __future__ import annotations

import json
import sys


SCRIPT_DIR = __import__("pathlib").Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from workflow_state import ensure_dig_state, read_json, sanitize_session_id, state_file_for, write_json


def main() -> int:
    try:
        input_text = sys.stdin.read() if not sys.stdin.isatty() else ""
    except Exception:
        return 0

    if not input_text:
        return 0

    try:
        parsed = json.loads(input_text)
    except json.JSONDecodeError:
        return 0

    if not isinstance(parsed, dict):
        return 0

    session_id = sanitize_session_id(str(parsed.get("session_id", "")))
    state_path = state_file_for(session_id)
    state = read_json(state_path)
    if not state:
        return 0

    dig = ensure_dig_state(state)
    warning = ""
    if dig.get("active") and dig.get("phase4_approved") and not dig.get("phase5_tasks_registered"):
        warning = "[devkit-dig] ⚠️ /dig セッションが終了しましたが、Phase 5 Tasks は未登録のままです。"

    dig.update(
        {
            "active": False,
            "topic": "",
            "session_started_at": 0.0,
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

    if not warning:
        return 0

    payload = {
        "hookSpecificOutput": {
            "hookEventName": "Stop",
            "additionalContext": warning,
        }
    }
    print(json.dumps(payload, ensure_ascii=False), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
