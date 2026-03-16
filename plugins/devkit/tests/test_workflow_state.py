"""workflow_state モジュールの単体テスト."""

from __future__ import annotations

import json
import time

from workflow_state import (
    append_phase,
    default_dig_state,
    ensure_dig_state,
    normalize_phase_token,
    sync_dig_tasks_from_store,
)


# ── 1. default_dig_state キーセット ──────────────────────────


def test_default_dig_state_keys():
    state = default_dig_state()
    expected_keys = {
        "active",
        "topic",
        "session_started_at",
        "requirements_confirmed",
        "ask_user_count",
        "phase4_approved",
        "phase5_tasks_registered",
        "task_ids",
        "task_subjects",
        "plan_review_attempts",
        "review_blocked",
    }
    assert set(state.keys()) == expected_keys


# ── 2. ensure_dig_state マイグレーション: phase5_approved → phase4_approved ──


def test_ensure_dig_state_migration_phase5_to_phase4():
    state = {"dig": {"phase5_approved": True}}
    dig = ensure_dig_state(state)
    assert dig["phase4_approved"] is True
    assert "phase5_approved" not in dig


# ── 3. ensure_dig_state マイグレーション: phase6_tasks_registered → phase5_tasks_registered ──


def test_ensure_dig_state_migration_phase6_to_phase5():
    state = {"dig": {"phase6_tasks_registered": True}}
    dig = ensure_dig_state(state)
    assert dig["phase5_tasks_registered"] is True
    assert "phase6_tasks_registered" not in dig


# ── 4. 新キーが既にある場合、旧キーは除去されるだけ ──


def test_ensure_dig_state_no_migration_when_new_key_exists():
    state = {
        "dig": {
            "phase5_approved": True,
            "phase4_approved": False,
            "phase6_tasks_registered": True,
            "phase5_tasks_registered": False,
        }
    }
    dig = ensure_dig_state(state)
    # 新キーの値がそのまま維持される
    assert dig["phase4_approved"] is False
    assert dig["phase5_tasks_registered"] is False
    assert "phase5_approved" not in dig
    assert "phase6_tasks_registered" not in dig


# ── 5. dig が dict でない場合もデフォルト状態を返す ──


def test_ensure_dig_state_invalid_input():
    for invalid in ["string", 42, None, [1, 2]]:
        state = {"dig": invalid}
        dig = ensure_dig_state(state)
        assert dig == default_dig_state()


# ── 6. sync_dig_tasks_from_store: [Task 1] パターンにマッチ ──


def test_sync_dig_tasks_from_store_matches_task_pattern(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))

    session_id = "test-session"
    task_dir = tmp_path / ".claude" / "tasks" / session_id
    task_dir.mkdir(parents=True)

    task_file = task_dir / "001.json"
    task_file.write_text(
        json.dumps({"id": "t1", "subject": "[Task 1] implement feature"}),
        encoding="utf-8",
    )

    state = {"dig": {"session_started_at": 0.0}}
    dig = sync_dig_tasks_from_store(state, session_id)

    assert dig["phase5_tasks_registered"] is True
    assert "[Task 1] implement feature" in dig["task_subjects"]
    assert "t1" in dig["task_ids"]


# ── 7. sync_dig_tasks_from_store: session_started_at より古いタスクは無視 ──


def test_sync_dig_tasks_from_store_ignores_stale(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))

    session_id = "test-session-stale"
    task_dir = tmp_path / ".claude" / "tasks" / session_id
    task_dir.mkdir(parents=True)

    task_file = task_dir / "001.json"
    task_file.write_text(
        json.dumps({"id": "old", "subject": "[Task 1] old task"}),
        encoding="utf-8",
    )

    # ファイルの mtime を過去に設定
    import os

    old_time = time.time() - 3600
    os.utime(task_file, (old_time, old_time))

    # session_started_at を現在時刻にして、古いタスクをフィルタアウト
    state = {"dig": {"session_started_at": time.time()}}
    dig = sync_dig_tasks_from_store(state, session_id)

    assert dig["phase5_tasks_registered"] is False
    assert dig["task_subjects"] == []
    assert dig["task_ids"] == []


# ── 8. normalize_phase_token: レガシートークン変換 ──


def test_normalize_phase_token_legacy():
    assert normalize_phase_token("plan_review") == "plan_review_completed"
    assert normalize_phase_token("impl_review") == "implementation_review_completed"
    assert normalize_phase_token("commit_review") == "commit_review_completed"
    assert normalize_phase_token("phase_6") == "implementation_completed"


# ── 9. normalize_phase_token: 新トークンはパススルー ──


def test_normalize_phase_token_passthrough():
    assert normalize_phase_token("plan_review_completed") == "plan_review_completed"
    assert normalize_phase_token("intake_declared") == "intake_declared"
    assert normalize_phase_token(None) is None
    assert normalize_phase_token("") is None


# ── 10. append_phase: 重複追加しない ──


def test_append_phase_dedup():
    state = {"phases_passed": []}
    append_phase(state, "plan_review_completed")
    append_phase(state, "plan_review_completed")

    assert state["phases_passed"] == ["plan_review_completed"]
    assert state["current_phase_token"] == "plan_review_completed"
