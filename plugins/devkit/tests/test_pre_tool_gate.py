"""pre_tool_gate.py のゲート判定を subprocess で検証する pytest テスト。"""
from __future__ import annotations

import pytest

from conftest import SESSION_ID, get_decision, load_state, parse_hook_output, write_task


# ---------------------------------------------------------------------------
# Helper: dig セッション開始
# ---------------------------------------------------------------------------
def start_dig(hook_runner):
    """user_prompt_submit で dig セッションを開始する。"""
    hook_runner("user_prompt_submit.py", {"session_id": SESSION_ID, "prompt": "/dig test"})


def confirm_requirements(hook_runner):
    """post_ask_user で requirements_confirmed を設定する。"""
    hook_runner("post_ask_user.py", {"session_id": SESSION_ID})


def approve_phase4(hook_runner):
    """post_task_tracker で phase4_approved を設定する (REVIEW_COUNTS critical=0 high=0)。"""
    hook_runner(
        "post_task_tracker.py",
        {
            "session_id": SESSION_ID,
            "tool_name": "Bash",
            "tool_input": {
                "command": "codex exec review",
                "status": "completed",
                "metadata": {},
            },
            "tool_response": "REVIEW_RESULT_MARKER=REVIEW_COUNTS critical=0 high=0",
        },
    )


def register_tasks(isolated_home):
    """write_task でタスクファイルを登録する。"""
    write_task(isolated_home, SESSION_ID, "t1", "[Task 1] sample")


def run_gate(hook_runner, tool_name, tool_input=None):
    """pre_tool_gate.py を実行してゲート判定を取得する。"""
    payload = {"session_id": SESSION_ID, "tool_name": tool_name}
    if tool_input is not None:
        payload["tool_input"] = tool_input
    return hook_runner("pre_tool_gate.py", payload)


# ---------------------------------------------------------------------------
# 1. state なし → pass
# ---------------------------------------------------------------------------
def test_no_workflow_state_pass(hook_runner):
    result = run_gate(hook_runner, "Edit", {"file_path": "/tmp/foo.py"})
    assert get_decision(result) == "pass"


# ---------------------------------------------------------------------------
# 2. dig 非アクティブ → pass
# ---------------------------------------------------------------------------
def test_dig_inactive_pass(hook_runner, isolated_home):
    # state ファイルを作るが dig を開始しない
    import json
    state_path = isolated_home / ".claude" / f"devkit-workflow-{SESSION_ID}.json"
    state_path.write_text(
        json.dumps({"workflow_version": 2, "session_id": SESSION_ID, "phases_passed": []}),
        encoding="utf-8",
    )
    result = run_gate(hook_runner, "Edit", {"file_path": "/tmp/foo.py"})
    assert get_decision(result) == "pass"


# ---------------------------------------------------------------------------
# 3. requirements_confirmed=False で plan Write → ask
# ---------------------------------------------------------------------------
def test_phase1_incomplete_plan_write_ask(hook_runner):
    start_dig(hook_runner)
    result = run_gate(hook_runner, "Write", {"file_path": "/home/user/.claude/plans/plan.md"})
    assert get_decision(result) == "ask"


# ---------------------------------------------------------------------------
# 4. requirements_confirmed=True で plan Write → pass
# ---------------------------------------------------------------------------
def test_phase1_complete_plan_write_pass(hook_runner):
    start_dig(hook_runner)
    confirm_requirements(hook_runner)
    result = run_gate(hook_runner, "Write", {"file_path": "/home/user/.claude/plans/plan.md"})
    assert get_decision(result) == "pass"


# ---------------------------------------------------------------------------
# 5. phase4_approved=False で ExitPlanMode → ask
# ---------------------------------------------------------------------------
def test_exitplanmode_before_phase4_ask(hook_runner):
    start_dig(hook_runner)
    confirm_requirements(hook_runner)
    result = run_gate(hook_runner, "ExitPlanMode")
    assert get_decision(result) == "ask"


# ---------------------------------------------------------------------------
# 6. phase4_approved=True + tasks 未登録で Edit → block
# ---------------------------------------------------------------------------
def test_phase4_approved_no_tasks_block(hook_runner):
    start_dig(hook_runner)
    confirm_requirements(hook_runner)
    approve_phase4(hook_runner)
    result = run_gate(hook_runner, "Edit", {"file_path": "/tmp/foo.py"})
    assert get_decision(result) == "block"


# ---------------------------------------------------------------------------
# 7. phase4_approved=True + tasks 登録で Edit → pass
# ---------------------------------------------------------------------------
def test_phase4_approved_with_tasks_pass(hook_runner, isolated_home):
    start_dig(hook_runner)
    confirm_requirements(hook_runner)
    approve_phase4(hook_runner)
    register_tasks(isolated_home)
    result = run_gate(hook_runner, "Edit", {"file_path": "/tmp/foo.py"})
    assert get_decision(result) == "pass"


# ---------------------------------------------------------------------------
# 8. phase4_approved=False で Edit(非plan) → ask
# ---------------------------------------------------------------------------
def test_phase4_not_approved_impl_tool_ask(hook_runner):
    start_dig(hook_runner)
    confirm_requirements(hook_runner)
    result = run_gate(hook_runner, "Edit", {"file_path": "/tmp/foo.py"})
    assert get_decision(result) == "ask"


# ---------------------------------------------------------------------------
# 9. codex exec readonly → pass（phase4 未通過でも）
# ---------------------------------------------------------------------------
def test_codex_exec_readonly_pass(hook_runner):
    start_dig(hook_runner)
    result = run_gate(
        hook_runner,
        "Bash",
        {"command": "codex exec -m gpt-5.3-codex-spark review"},
    )
    assert get_decision(result) == "pass"


# ---------------------------------------------------------------------------
# 10. codex exec chained with mutating command → ask
# ---------------------------------------------------------------------------
def test_codex_exec_chained_block(hook_runner):
    start_dig(hook_runner)
    result = run_gate(
        hook_runner,
        "Bash",
        {"command": "codex exec -m gpt-5.3-codex-spark review && touch file"},
    )
    decision = get_decision(result)
    assert decision in ("block", "ask")


# ---------------------------------------------------------------------------
# 11. review 未完了で git commit → block
# ---------------------------------------------------------------------------
def test_git_commit_without_review_block(hook_runner, isolated_home):
    start_dig(hook_runner)
    confirm_requirements(hook_runner)
    approve_phase4(hook_runner)
    register_tasks(isolated_home)
    # phase4 通過 + tasks 登録済みだが implementation_review_completed がない
    result = run_gate(hook_runner, "Bash", {"command": "git commit -m 'test'"})
    assert get_decision(result) == "block"


# ---------------------------------------------------------------------------
# 12. commit_review_completed なしで git push → block
# ---------------------------------------------------------------------------
def test_git_push_without_commit_review_block(hook_runner, isolated_home):
    start_dig(hook_runner)
    confirm_requirements(hook_runner)
    approve_phase4(hook_runner)
    register_tasks(isolated_home)
    # plan_review_completed + implementation_review_completed を追加するが
    # commit_review_completed は追加しない
    hook_runner(
        "post_task_tracker.py",
        {
            "session_id": SESSION_ID,
            "tool_input": {
                "status": "completed",
                "metadata": {
                    "phases": [
                        "plan_review_completed",
                        "implementation_review_completed",
                    ]
                },
            },
        },
    )
    result = run_gate(hook_runner, "Bash", {"command": "git push origin main"})
    assert get_decision(result) == "block"
