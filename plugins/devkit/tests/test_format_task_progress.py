"""format_task_progress モジュールの単体テスト."""
from __future__ import annotations

import json

from format_task_progress import format_progress
from workflow_state import state_file_for


# ── 1. 正常ケース: 依存ありタスクの [Task N] 変換 ──


def test_format_progress_resolves_blockers(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))

    session_id = "test-format"
    task_dir = tmp_path / ".claude" / "tasks" / session_id
    task_dir.mkdir(parents=True)

    (task_dir / "001.json").write_text(
        json.dumps({"id": "38", "subject": "[Task 1] dimensions", "status": "completed"}),
        encoding="utf-8",
    )
    (task_dir / "002.json").write_text(
        json.dumps({"id": "39", "subject": "[Task 2] insulation", "status": "pending", "blockedBy": ["38"]}),
        encoding="utf-8",
    )
    (task_dir / "003.json").write_text(
        json.dumps({"id": "40", "subject": "[Task 3] weight", "status": "in_progress", "blockedBy": ["38", "39"]}),
        encoding="utf-8",
    )

    # state_file_for() の実パスに workflow state を作成
    state_path = state_file_for(session_id)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps({"dig": {"session_started_at": 0.0, "active": True}}),
        encoding="utf-8",
    )

    result = format_progress(session_id)
    lines = result.split("\n")

    assert "3 tasks (1 done, 1 in progress, 1 open)" in lines[0]
    assert "✔ [Task 1] dimensions" in lines[1]
    assert "blocked by [Task 1]" in lines[2]
    assert "blocked by [Task 1], [Task 2]" in lines[3]
    # 内部 ID が漏出していないことを確認
    assert "#38" not in result
    assert "#39" not in result


# ── 2. 空ケース: タスク未登録 ──


def test_format_progress_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))

    session_id = "test-empty"
    task_dir = tmp_path / ".claude" / "tasks" / session_id
    task_dir.mkdir(parents=True)

    state_path = state_file_for(session_id)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps({"dig": {"session_started_at": 0.0}}),
        encoding="utf-8",
    )

    result = format_progress(session_id)
    assert result == ""


# ── 3. 部分マッピング: 不明 ID はフォールバック ──


def test_format_progress_unknown_blocker_fallback(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))

    session_id = "test-fallback"
    task_dir = tmp_path / ".claude" / "tasks" / session_id
    task_dir.mkdir(parents=True)

    (task_dir / "001.json").write_text(
        json.dumps({"id": "38", "subject": "[Task 1] dimensions", "status": "completed"}),
        encoding="utf-8",
    )
    (task_dir / "002.json").write_text(
        json.dumps({"id": "39", "subject": "[Task 2] insulation", "status": "pending", "blockedBy": ["38", "999"]}),
        encoding="utf-8",
    )

    state_path = state_file_for(session_id)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps({"dig": {"session_started_at": 0.0}}),
        encoding="utf-8",
    )

    result = format_progress(session_id)
    assert "blocked by [Task 1], #999" in result
