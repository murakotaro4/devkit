#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from workflow_state import (
    append_phase,
    ensure_claude_dir,
    ensure_dig_state,
    normalize_phase_token,
    read_json,
    sanitize_session_id,
    state_file_for,
    sync_dig_tasks_from_store,
    write_json,
)


REVIEW_RESULT_MARKER = "REVIEW_RESULT_MARKER=REVIEW_COUNTS"
REVIEW_COUNTS_PATTERN = re.compile(r"REVIEW_COUNTS\s+critical=(\d+)\s+high=(\d+)")


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
    if not isinstance(tool_input, dict):
        return 0

    tool_status = tool_input.get("status")
    if tool_status not in {None, "completed"}:
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

    ensure_claude_dir()
    session_id = sanitize_session_id(str(parsed.get("session_id", "")))
    state_path = state_file_for(session_id)
    state = read_json(state_path) or {}
    dig = sync_dig_tasks_from_store(state, session_id)
    raw_existing = state.get("phases_passed")
    existing: list[str] = []
    if isinstance(raw_existing, list):
        for token in raw_existing:
            normalized = normalize_phase_token(token if isinstance(token, str) else None)
            if normalized:
                existing.append(normalized)

    merged = existing[:]
    latest_phase = state.get("current_phase_token") if isinstance(state.get("current_phase_token"), str) else ""
    for phase in phases:
        if phase not in merged:
            merged.append(phase)
        latest_phase = phase

    state["workflow_version"] = 2
    state["current_phase_token"] = latest_phase
    state["phases_passed"] = merged

    tool = str(parsed.get("tool_name", "") or parsed.get("toolName", "") or "")
    command = str(tool_input.get("command", ""))
    tool_response = str(parsed.get("tool_response", "") or tool_input.get("tool_response", "") or "")
    if tool == "Bash" and dig.get("active"):
        combined = f"{command}\n{tool_response}"
        if REVIEW_RESULT_MARKER in combined and not dig.get("phase5_approved"):
            # Phase 5 plan review のみ対象。phase5_approved 後の REVIEW_COUNTS は
            # Phase 7 (SUBTASK/INTEGRATION) のレビュー結果なので無視する。
            match = REVIEW_COUNTS_PATTERN.search(combined)
            if match:
                dig["plan_review_attempts"] = dig.get("plan_review_attempts", 0) + 1
                critical = int(match.group(1))
                high = int(match.group(2))
                if dig.get("plan_review_attempts", 0) >= 3 and (critical > 0 or high > 0):
                    dig["review_blocked"] = True
                    print(
                        "DIG_CLAUDE_REVIEW_BLOCKED: Plan review failed 3 times. 手動介入が必要です",
                        file=sys.stderr,
                    )
                elif critical == 0 and high == 0 and not dig.get("review_blocked"):
                    dig["phase5_approved"] = True
                    append_phase(state, "plan_review_completed")
            else:
                # REVIEW_RESULT_MARKER は存在するが REVIEW_COUNTS のパースに失敗
                dig["plan_review_attempts"] = dig.get("plan_review_attempts", 0) + 1
                dig["review_blocked"] = True
                print(
                    "DIG_CLAUDE_REVIEW_BLOCKED: REVIEW_COUNTS パース不能。手動介入が必要です",
                    file=sys.stderr,
                )

    ensure_dig_state(state)
    write_json(state_path, state)

    if not phases and not (tool == "Bash" and dig.get("active")):
        return 0

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
