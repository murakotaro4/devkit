"""dig セッション全体の E2E シミュレーション."""

from __future__ import annotations

import json

from conftest import SESSION_ID, get_decision, load_state, parse_hook_output, write_task


# ── ヘルパー ──────────────────────────────────────────────────


def _start_dig(hook_runner):
    """user_prompt_submit.py で /dig セッションを開始する。"""
    payload = {"session_id": SESSION_ID, "prompt": "/dig test topic"}
    hook_runner("user_prompt_submit.py", payload)


def _post_ask_user(hook_runner):
    """post_ask_user.py を呼ぶ。"""
    return hook_runner("post_ask_user.py", {"session_id": SESSION_ID})


def _pre_tool_gate(hook_runner, tool_name: str, tool_input: dict | None = None):
    """pre_tool_gate.py を呼ぶ。"""
    payload = {
        "session_id": SESSION_ID,
        "tool_name": tool_name,
        "tool_input": tool_input or {},
    }
    return hook_runner("pre_tool_gate.py", payload)


def _post_task_tracker(hook_runner, tool_name: str = "", command: str = "", tool_response: str = "", **extra):
    """post_task_tracker.py を呼ぶ。"""
    payload = {
        "session_id": SESSION_ID,
        "tool_name": tool_name,
        "tool_input": {"command": command, "tool_response": tool_response},
        "tool_response": tool_response,
    }
    if "metadata" in extra:
        payload["tool_input"]["metadata"] = extra["metadata"]
    if "status" in extra:
        payload["tool_input"]["status"] = extra["status"]
    return hook_runner("post_task_tracker.py", payload)


def _stop_dig(hook_runner):
    """stop_dig_session.py を呼ぶ。"""
    return hook_runner("stop_dig_session.py", {"session_id": SESSION_ID})


def _set_phases(isolated_home, phases: list[str], current: str = ""):
    """state ファイルの phases_passed を直接書き換える。"""
    state = load_state(isolated_home, SESSION_ID)
    state["phases_passed"] = phases
    state["current_phase_token"] = current or (phases[-1] if phases else "")
    state_path = isolated_home / ".claude" / f"devkit-workflow-{SESSION_ID}.json"
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


# ── 1. 正常フロー: Phase 1 → Phase 7 ──────────────────────────


def test_happy_path_phase1_to_phase7(hook_runner, isolated_home):
    # /dig 起動
    _start_dig(hook_runner)

    # AskUserQuestion → requirements_confirmed
    _post_ask_user(hook_runner)
    state = load_state(isolated_home, SESSION_ID)
    assert state["dig"]["requirements_confirmed"] is True

    # plan Write → pass (plan ファイルは requirements_confirmed 後なので通過)
    result = _pre_tool_gate(
        hook_runner, "Write", {"file_path": "/tmp/.claude/plans/plan.md"}
    )
    decision = get_decision(result)
    assert decision == "pass"

    # codex exec review → REVIEW_COUNTS → phase4_approved
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

    # [Task 1] write_task → phase5_tasks_registered
    write_task(isolated_home, SESSION_ID, "t1", "[Task 1] implement feature")

    # Edit → pass (phase5_tasks_registered は sync_dig_tasks_from_store で検出)
    result = _pre_tool_gate(hook_runner, "Edit", {"file_path": "/tmp/src/main.py"})
    decision = get_decision(result)
    assert decision == "pass"

    state = load_state(isolated_home, SESSION_ID)
    assert state["dig"]["phase5_tasks_registered"] is True

    # phases_passed に plan_review_completed + implementation_review_completed 設定
    _set_phases(isolated_home, ["plan_review_completed", "implementation_review_completed"])

    # git commit → pass
    result = _pre_tool_gate(hook_runner, "Bash", {"command": "git commit -m 'feat: test'"})
    decision = get_decision(result)
    assert decision == "pass"

    # phases_passed に commit_review_completed 設定
    _set_phases(
        isolated_home,
        ["plan_review_completed", "implementation_review_completed", "commit_review_completed"],
    )

    # git push → pass
    result = _pre_tool_gate(hook_runner, "Bash", {"command": "git push"})
    decision = get_decision(result)
    # pass or block (version bump) — ここでは version check で block される可能性があるが
    # workflow phase gate 自体は通過する
    assert decision in {"pass", "block"}


# ── 2. AskUserQuestion なしで plan Write → ask ──────────────────


def test_skip_phase1_blocked(hook_runner, isolated_home):
    _start_dig(hook_runner)

    # requirements_confirmed=False のまま plan ファイルを Write
    result = _pre_tool_gate(
        hook_runner, "Write", {"file_path": "/tmp/.claude/plans/plan.md"}
    )
    decision = get_decision(result)
    assert decision == "ask"


# ── 3. phase4_approved=False で Edit → ask ─────────────────────


def test_skip_phase4_review_blocked(hook_runner, isolated_home):
    _start_dig(hook_runner)

    # requirements_confirmed にする
    _post_ask_user(hook_runner)

    # phase4_approved=False, phase5_tasks_registered=False で Edit
    result = _pre_tool_gate(hook_runner, "Edit", {"file_path": "/tmp/src/main.py"})
    decision = get_decision(result)
    assert decision == "ask"


# ── 4. 旧キー (phase5_approved=True) がある state で dig 操作 → 正常動作 ──


def test_migration_from_v3_state(hook_runner, isolated_home):
    _start_dig(hook_runner)

    # state を直接書き換えて旧キーを注入
    state = load_state(isolated_home, SESSION_ID)
    state["dig"]["phase5_approved"] = True
    del state["dig"]["phase4_approved"]
    state_path = isolated_home / ".claude" / f"devkit-workflow-{SESSION_ID}.json"
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    # Task を登録して phase5_tasks_registered を有効化
    write_task(isolated_home, SESSION_ID, "t1", "[Task 1] migrate test")

    # Edit → pass (phase5_approved が phase4_approved にマイグレーションされる)
    result = _pre_tool_gate(hook_runner, "Edit", {"file_path": "/tmp/src/main.py"})
    decision = get_decision(result)
    assert decision == "pass"

    # マイグレーション後の state を確認
    state = load_state(isolated_home, SESSION_ID)
    assert state["dig"]["phase4_approved"] is True
    assert "phase5_approved" not in state["dig"]


# ── 5. stop_dig_session で dig state がクリアされる ─────────────


def test_stop_cleans_up(hook_runner, isolated_home):
    _start_dig(hook_runner)
    _post_ask_user(hook_runner)

    state = load_state(isolated_home, SESSION_ID)
    assert state["dig"]["active"] is True

    _stop_dig(hook_runner)

    state = load_state(isolated_home, SESSION_ID)
    assert state["dig"]["active"] is False
    assert state["dig"]["requirements_confirmed"] is False
    assert state["dig"]["phase4_approved"] is False
    assert state["dig"]["ask_user_count"] == 0
