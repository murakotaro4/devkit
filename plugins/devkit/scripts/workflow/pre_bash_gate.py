#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(SCRIPT_DIR.parent))

from check_plugin_version_bump import run_check
from workflow_state import normalize_phase_token, read_json, sanitize_session_id, state_file_for


def emit_decision(decision: str, reason: str, additional_context: str | None = None) -> None:
    payload: dict[str, object] = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": decision,
            "permissionDecisionReason": reason,
        }
    }
    if additional_context:
        payload["hookSpecificOutput"]["additionalContext"] = additional_context
    print(json.dumps(payload, ensure_ascii=False), end="")


def suggest_version_message() -> str | None:
    code, payload = run_check()
    if code == 0:
        return None
    if payload.get("reason") != "plugin version not bumped":
        return None
    return (
        "[devkit-workflow] ⛔ git push がブロックされました。"
        f"plugin.json のバージョンが変更されていません（現在: {payload.get('baseVersion')}）。\n"
        f"必要条件: {payload.get('required')}\n"
        "plugin.json の version を更新してからコミットし直してください。"
    )


def main() -> int:
    try:
        input_text = sys.stdin.read() if not sys.stdin.isatty() else ""
    except Exception:
        emit_decision("pass", "stdin not available")
        return 0

    if not input_text:
        emit_decision("pass", "no input")
        return 0

    try:
        parsed = json.loads(input_text)
    except json.JSONDecodeError:
        emit_decision("pass", "malformed input")
        return 0

    tool_input = parsed.get("tool_input") if isinstance(parsed, dict) else {}
    session_id = sanitize_session_id(str(parsed.get("session_id", ""))) if isinstance(parsed, dict) else ""
    command = tool_input.get("command", "") if isinstance(tool_input, dict) else ""
    if not command:
        emit_decision("pass", "no command")
        return 0

    is_git_commit = re.search(r"\bgit\b.*\bcommit(?:\s|$|[;&|])", command) is not None
    is_git_push = re.search(r"\bgit\b.*\bpush(?:\s|$|[;&|])", command) is not None
    if not is_git_commit and not is_git_push:
        emit_decision("pass", "not a git commit/push")
        return 0

    state = read_json(state_file_for(session_id))
    if not state:
        action = "commit" if is_git_commit else "push"
        emit_decision(
            "ask",
            f"git {action} detected without workflow state",
            f"[devkit-workflow] ⚠️ git {action} が検出されました。ワークフロー状態が確認できません。レビューゲート（Phase 5/7）を完了していますか？",
        )
        return 0

    phases_passed: list[str] = []
    raw_phases = state.get("phases_passed")
    if isinstance(raw_phases, list):
        for token in raw_phases:
            normalized = normalize_phase_token(token if isinstance(token, str) else None)
            if normalized:
                phases_passed.append(normalized)

    has_review = (
        "plan_review_completed" in phases_passed
        and "implementation_review_completed" in phases_passed
    )
    if is_git_commit and not has_review:
        emit_decision(
            "ask",
            "git commit detected without review phase marker",
            "[devkit-workflow] ⚠️ git commit が検出されましたが、レビューゲートの完了マーカーがありません。\nagent team ワークフローの Phase 5 または Phase 7 を完了してからコミットしてください。",
        )
        return 0

    if is_git_push and "commit_review_completed" not in phases_passed:
        emit_decision(
            "ask",
            "git push detected without commit review marker",
            "[devkit-workflow] ⚠️ git push が検出されましたが、コミット前確認（Phase 8 Step 2）の完了マーカーがありません。",
        )
        return 0

    if is_git_push:
        version_message = suggest_version_message()
        if version_message:
            emit_decision("block", "plugin.json version not bumped", version_message)
            return 0

    emit_decision("pass", "workflow checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
