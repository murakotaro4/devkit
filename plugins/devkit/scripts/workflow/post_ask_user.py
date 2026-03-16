#!/usr/bin/env python3
"""PostToolUse handler for AskUserQuestion.

dig セッション中の AskUserQuestion 完了を検知し、requirements_confirmed を設定する。
"""
from __future__ import annotations

import json
import sys


SCRIPT_DIR = __import__("pathlib").Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from workflow_state import (
    append_phase,
    ensure_dig_state,
    read_json,
    sanitize_session_id,
    state_file_for,
    write_json,
)


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
    if not dig.get("active"):
        write_json(state_path, state)
        return 0

    # AskUserQuestion が成功した場合、ask_user_count をインクリメント
    dig["ask_user_count"] = dig.get("ask_user_count", 0) + 1

    if dig["ask_user_count"] >= 1 and not dig.get("requirements_confirmed"):
        dig["requirements_confirmed"] = True
        append_phase(state, "requirements_confirmed")

    write_json(state_path, state)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
