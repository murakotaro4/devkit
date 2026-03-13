#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from workflow_state import ensure_claude_dir, normalize_phase_token, read_json, sanitize_session_id, state_file_for, write_json


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

    tool_input = parsed.get("tool_input") if isinstance(parsed, dict) else {}
    if not isinstance(tool_input, dict) or tool_input.get("status") != "completed":
        return 0

    metadata = tool_input.get("metadata", {})
    phases: list[str] = []
    if isinstance(metadata, dict):
        if isinstance(metadata.get("phases"), list):
            for token in metadata["phases"]:
                normalized = normalize_phase_token(token if isinstance(token, str) else None)
                if normalized:
                    phases.append(normalized)
        elif isinstance(metadata.get("phase"), str):
            normalized = normalize_phase_token(metadata["phase"])
            if normalized:
                phases.append(normalized)

    if not phases:
        return 0

    ensure_claude_dir()
    session_id = sanitize_session_id(str(parsed.get("session_id", "")))
    state_path = state_file_for(session_id)
    state = read_json(state_path) or {}
    raw_existing = state.get("phases_passed")
    existing: list[str] = []
    if isinstance(raw_existing, list):
        for token in raw_existing:
            normalized = normalize_phase_token(token if isinstance(token, str) else None)
            if normalized:
                existing.append(normalized)

    merged = existing[:]
    for phase in phases:
        if phase not in merged:
            merged.append(phase)

    latest_phase = phases[-1]
    state["workflow_version"] = 2
    state["current_phase_token"] = latest_phase
    state["phases_passed"] = merged
    write_json(state_path, state)

    payload = {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": (
                f"[devkit-workflow] Phase completed: {', '.join(phases)}. "
                f"current_phase_token: {latest_phase}. phases_passed: [{', '.join(merged)}]"
            ),
        }
    }
    print(json.dumps(payload, ensure_ascii=False), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
