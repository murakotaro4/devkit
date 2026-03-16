"""PostToolUse hook (post_task_tracker.py, post_ask_user.py) のテスト."""

from __future__ import annotations

import json

from conftest import SESSION_ID, get_decision, load_state, parse_hook_output


# ── ヘルパー ──────────────────────────────────────────────────


def _start_dig(hook_runner):
    """user_prompt_submit.py で /dig セッションを開始する。"""
    payload = {"session_id": SESSION_ID, "prompt": "/dig test topic"}
    hook_runner("user_prompt_submit.py", payload)


def _post_task_tracker(hook_runner, tool_name: str, command: str = "", tool_response: str = "", **extra):
    """post_task_tracker.py を呼ぶ。"""
    payload = {
        "session_id": SESSION_ID,
        "tool_name": tool_name,
        "tool_input": {"command": command, "tool_response": tool_response, **extra.get("tool_input_extra", {})},
        "tool_response": tool_response,
    }
    if "metadata" in extra:
        payload["tool_input"]["metadata"] = extra["metadata"]
    if "status" in extra:
        payload["tool_input"]["status"] = extra["status"]
    return hook_runner("post_task_tracker.py", payload)


def _post_ask_user(hook_runner):
    """post_ask_user.py を呼ぶ。"""
    payload = {"session_id": SESSION_ID}
    return hook_runner("post_ask_user.py", payload)


# ── 1. REVIEW_COUNTS critical=0 high=0 → phase4_approved=True ──────


def test_review_pass_sets_phase4_approved(hook_runner, isolated_home):
    _start_dig(hook_runner)

    review_output = (
        "REVIEW_RESULT_MARKER=REVIEW_COUNTS\n"
        "REVIEW_COUNTS critical=0 high=0"
    )
    _post_task_tracker(
        hook_runner,
        tool_name="Bash",
        command="codex exec review",
        tool_response=review_output,
    )

    state = load_state(isolated_home, SESSION_ID)
    assert state["dig"]["phase4_approved"] is True
    assert state["dig"]["plan_review_attempts"] == 1


# ── 2. REVIEW_COUNTS critical=1 → phase4_approved=False, plan_review_attempts=1 ──


def test_review_fail_increments_attempts(hook_runner, isolated_home):
    _start_dig(hook_runner)

    review_output = (
        "REVIEW_RESULT_MARKER=REVIEW_COUNTS\n"
        "REVIEW_COUNTS critical=1 high=0"
    )
    _post_task_tracker(
        hook_runner,
        tool_name="Bash",
        command="codex exec review",
        tool_response=review_output,
    )

    state = load_state(isolated_home, SESSION_ID)
    assert state["dig"]["phase4_approved"] is False
    assert state["dig"]["plan_review_attempts"] == 1


# ── 3. 3回失敗 → review_blocked=True ──────────────────────────


def test_review_blocked_after_3_failures(hook_runner, isolated_home):
    _start_dig(hook_runner)

    review_output = (
        "REVIEW_RESULT_MARKER=REVIEW_COUNTS\n"
        "REVIEW_COUNTS critical=1 high=0"
    )
    for _ in range(3):
        _post_task_tracker(
            hook_runner,
            tool_name="Bash",
            command="codex exec review",
            tool_response=review_output,
        )

    state = load_state(isolated_home, SESSION_ID)
    assert state["dig"]["review_blocked"] is True
    assert state["dig"]["plan_review_attempts"] == 3


# ── 4. REVIEW_RESULT_MARKER あるが REVIEW_COUNTS なし → review_blocked=True ──


def test_review_counts_unparseable_blocks(hook_runner, isolated_home):
    _start_dig(hook_runner)

    review_output = "REVIEW_RESULT_MARKER=REVIEW_COUNTS\nno counts here"
    _post_task_tracker(
        hook_runner,
        tool_name="Bash",
        command="codex exec review",
        tool_response=review_output,
    )

    state = load_state(isolated_home, SESSION_ID)
    assert state["dig"]["review_blocked"] is True


# ── 5. phase4_approved=True 後の REVIEW_COUNTS → 無視 ──────────


def test_review_after_phase4_approved_ignored(hook_runner, isolated_home):
    _start_dig(hook_runner)

    # まず通過させる
    pass_output = (
        "REVIEW_RESULT_MARKER=REVIEW_COUNTS\n"
        "REVIEW_COUNTS critical=0 high=0"
    )
    _post_task_tracker(
        hook_runner,
        tool_name="Bash",
        command="codex exec review",
        tool_response=pass_output,
    )

    state = load_state(isolated_home, SESSION_ID)
    assert state["dig"]["phase4_approved"] is True
    attempts_before = state["dig"]["plan_review_attempts"]

    # 2回目（Phase 6 のレビュー結果を想定）→ 無視される
    fail_output = (
        "REVIEW_RESULT_MARKER=REVIEW_COUNTS\n"
        "REVIEW_COUNTS critical=2 high=3"
    )
    _post_task_tracker(
        hook_runner,
        tool_name="Bash",
        command="codex exec review",
        tool_response=fail_output,
    )

    state = load_state(isolated_home, SESSION_ID)
    assert state["dig"]["phase4_approved"] is True
    assert state["dig"]["plan_review_attempts"] == attempts_before


# ── 6. AskUserQuestion → requirements_confirmed=True, ask_user_count=1 ──


def test_ask_user_sets_requirements_confirmed(hook_runner, isolated_home):
    _start_dig(hook_runner)

    _post_ask_user(hook_runner)

    state = load_state(isolated_home, SESSION_ID)
    assert state["dig"]["requirements_confirmed"] is True
    assert state["dig"]["ask_user_count"] == 1
