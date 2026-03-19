#!/usr/bin/env python3
"""dig タスク進捗の可読フォーマッタ。

TaskList の内部 ID を [Task N] ラベルに変換して出力する。
PostToolUse hook から自動呼び出し、または dig-claude からの手動呼び出しで使用。
"""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from workflow_state import (
    load_task_entries,
    read_json,
    state_file_for,
    sync_dig_tasks_from_store,
)

STATUS_ICONS = {"completed": "✔", "in_progress": "▶", "pending": "◻", "cancelled": "✖"}


def format_progress(session_id: str) -> str:
    """セッション内タスクの進捗を可読形式で返す。タスクが無ければ空文字列。"""
    state = read_json(state_file_for(session_id))
    dig = sync_dig_tasks_from_store(state if isinstance(state, dict) else {}, session_id)

    id_map: dict[str, str] = dig.get("task_id_map", {})
    # sync_dig_tasks_from_store がフィルタ済みの task_ids を使う（mtime トレランス適用済み）
    valid_ids = set(dig.get("task_ids", []))
    if not valid_ids:
        return ""
    entries = load_task_entries(session_id)

    tasks: list[dict] = []
    for e in entries:
        sys_id = str(e.get("id", ""))
        if sys_id not in valid_ids:
            continue
        tasks.append(e)

    if not tasks:
        return ""

    done = sum(1 for t in tasks if t.get("status") == "completed")
    prog = sum(1 for t in tasks if t.get("status") == "in_progress")
    total = len(tasks)
    lines = [f"{total} tasks ({done} done, {prog} in progress, {total - done - prog} open)"]

    for t in tasks:
        status = t.get("status", "pending")
        icon = STATUS_ICONS.get(status, "◻")
        subj = t.get("subject", "")
        blocked = t.get("blockedBy", [])
        if blocked:
            labels = [id_map.get(str(b), f"#{b}") for b in blocked]
            lines.append(f"{icon} {subj} › blocked by {', '.join(labels)}")
        else:
            suffix = " (in_progress)" if status == "in_progress" else ""
            lines.append(f"{icon} {subj}{suffix}")

    return "\n".join(lines)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: format_task_progress.py <session_id>", file=sys.stderr)
        sys.exit(1)
    print(format_progress(sys.argv[1]))
