#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from workflow_state import cleanup_old_state_files, ensure_claude_dir, normalize_state, read_json, sanitize_session_id, state_file_for, write_json


def emit(message: str) -> None:
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": message,
        }
    }
    print(json.dumps(payload, ensure_ascii=False), end="")


def main() -> int:
    try:
        input_text = sys.stdin.read() if not sys.stdin.isatty() else ""
    except Exception:
        input_text = ""

    session_id = ""
    agent_type = ""
    if input_text:
        try:
            parsed = json.loads(input_text)
            if isinstance(parsed, dict):
                session_id = str(parsed.get("session_id", ""))
                agent_type = str(parsed.get("agent_type", ""))
        except json.JSONDecodeError:
            pass

    if agent_type == "subagent":
        emit("[devkit-workflow] subagent: skip workflow init")
        return 0

    ensure_claude_dir()
    session_id = sanitize_session_id(session_id)
    state_path = state_file_for(session_id)

    if state_path.exists():
        current = read_json(state_path)
        if current is not None:
            write_json(state_path, normalize_state(current))
        emit("[devkit-workflow] Existing workflow state loaded. agent-team workflow active.")
        return 0

    state = {
        "workflow_version": 2,
        "session_id": session_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "task": "",
        "current_phase_token": "",
        "phases_passed": [],
    }
    write_json(state_path, state)
    cleanup_old_state_files()
    emit("[devkit-workflow] Workflow state initialized. agent-team workflow contract active.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
