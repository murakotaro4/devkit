#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import sys


SCRIPT_DIR = __import__("pathlib").Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(SCRIPT_DIR.parent))

from check_plugin_version_bump import run_check
from workflow_state import read_json, sanitize_session_id, state_file_for, sync_dig_tasks_from_store, write_json


READ_ONLY_BASH_PATTERNS = [
    r"^\s*rg\b",
    r"^\s*grep\b",
    r"^\s*find\b",
    r"^\s*ls\b",
    r"^\s*pwd\b",
    r"^\s*cat\b",
    r"^\s*head\b",
    r"^\s*tail\b",
    r"^\s*wc\b",
    r"^\s*env\b",
    r"^\s*which\b",
    r"^\s*command\s+-v\b",
    r"^\s*git\s+(status|diff|log|show|rev-parse|branch)\b",
    r"^\s*python3?\s+-m\s+py_compile\b",
]
PURE_CODEX_EXEC_PATTERN = re.compile(r'^\s*codex\s+exec\b[^;&|`<>]*\s*$')


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


def is_mutating_bash(command: str) -> bool:
    if PURE_CODEX_EXEC_PATTERN.match(command):
        return False
    return not any(re.search(pattern, command) for pattern in READ_ONLY_BASH_PATTERNS)


def tool_name(parsed: dict[str, object]) -> str:
    for key in ("tool_name", "toolName", "matcher"):
        value = parsed.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def _is_plan_file(tool_input: dict[str, object]) -> bool:
    file_path = str(tool_input.get("file_path", ""))
    return "/.claude/plans/" in file_path and file_path.endswith(".md")


def is_dig_implementation_tool(name: str, tool_input: dict[str, object]) -> bool:
    if name in {"Edit", "Write", "MultiEdit", "Agent"}:
        return True
    if name == "Bash":
        command = str(tool_input.get("command", ""))
        return bool(command) and is_mutating_bash(command)
    return False


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

    if not isinstance(parsed, dict):
        emit_decision("pass", "invalid payload")
        return 0

    session_id = sanitize_session_id(str(parsed.get("session_id", "")))
    name = tool_name(parsed)
    tool_input = parsed.get("tool_input")
    tool_input = tool_input if isinstance(tool_input, dict) else {}
    command = str(tool_input.get("command", ""))

    is_git_commit = name == "Bash" and re.search(r"\bgit\b.*\bcommit(?:\s|$|[;&|])", command) is not None
    is_git_push = name == "Bash" and re.search(r"\bgit\b.*\bpush(?:\s|$|[;&|])", command) is not None

    state_path = state_file_for(session_id)
    state = read_json(state_path)
    if not state:
        if is_git_commit or is_git_push:
            action = "commit" if is_git_commit else "push"
            emit_decision(
                "ask",
                f"git {action} detected without workflow state",
                f"[devkit-workflow] ⚠️ git {action} が検出されました。ワークフロー状態が確認できません。レビューゲート（Phase 5/7）を完了していますか？",
            )
            return 0
        emit_decision("pass", "no workflow state")
        return 0

    dig = sync_dig_tasks_from_store(state, session_id)
    write_json(state_path, state)

    if dig.get("active") and name in {"Write", "Edit", "MultiEdit"} and not dig.get("requirements_confirmed"):
        if _is_plan_file(tool_input):
            emit_decision(
                "ask",
                "Plan file write before Phase 2 requirements confirmed",
                "[devkit-dig] ⚠️ Phase 2 の要件ヒアリングが完了していません。"
                "AskUserQuestion で最低 1 ラウンドの質問を行ってから "
                "Phase 4 に進んでください。"
                "Phase 2 を完了済みの場合はユーザー承認で続行できます。",
            )
            return 0

    if dig.get("active") and name == "ExitPlanMode" and not dig.get("phase5_approved"):
        emit_decision(
            "ask",
            "ExitPlanMode called before Phase 5 plan review",
            "[devkit-dig] ⚠️ Phase 5 の計画レビューが完了していません。"
            "ExitPlanMode を呼ぶ前に codex exec で計画レビューを実行し、"
            "REVIEW_COUNTS critical=0 high=0 を確認してください。"
            "codex exec が利用不能な場合はユーザー承認で続行できます。",
        )
        return 0

    if dig.get("active") and dig.get("phase5_approved") and not dig.get("phase6_tasks_registered") and is_dig_implementation_tool(name, tool_input):
        emit_decision(
            "block",
            "dig implementation started before Phase 6 task registration",
            "[devkit-dig] ⛔ Phase 5 は通過していますが、Phase 6 の Tasks が未登録です。"
            "先に [Task 1] 以降のタスクを TaskCreate で登録してから実装に入ってください。",
        )
        return 0

    if dig.get("active") and not dig.get("phase5_approved") and not dig.get("phase6_tasks_registered"):
        if is_dig_implementation_tool(name, tool_input) and not (name in {"Write", "Edit", "MultiEdit"} and _is_plan_file(tool_input)):
            emit_decision(
                "ask",
                "Implementation tool before Phase 5/6 completion",
                "[devkit-dig] ⚠️ Phase 5 計画レビューと Phase 6 TaskCreate が未完了です。"
                "調査目的の場合はユーザー承認で続行できます。",
            )
            return 0

    phases_passed = [token for token in state.get("phases_passed", []) if isinstance(token, str)] if isinstance(state.get("phases_passed"), list) else []
    has_review = "plan_review_completed" in phases_passed and "implementation_review_completed" in phases_passed
    if is_git_commit and not has_review:
        emit_decision(
            "block",
            "git commit detected without review phase marker",
            "[devkit-workflow] ⛔ Phase 5 と Phase 7 のレビューが完了していません。plan_review_completed と implementation_review_completed が必要です",
        )
        return 0

    if is_git_push and "commit_review_completed" not in phases_passed:
        emit_decision(
            "block",
            "git push detected without commit review marker",
            "[devkit-workflow] ⛔ Phase 8 のコミットレビューが完了していません。commit_review_completed が必要です",
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
