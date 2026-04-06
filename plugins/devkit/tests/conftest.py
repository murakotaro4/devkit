from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
WORKFLOW_DIR = REPO_ROOT / "plugins" / "devkit" / "scripts" / "workflow"


@pytest.fixture
def isolated_home(tmp_path, monkeypatch):
    """HOME を tmp_path に隔離。workflow state と task files をクリーンに保つ。"""
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".claude").mkdir(parents=True, exist_ok=True)
    return tmp_path


@pytest.fixture
def hook_env(isolated_home):
    """hook 実行用の環境変数 dict を返す。"""
    env = os.environ.copy()
    env["HOME"] = str(isolated_home)
    return env


def _run_hook(script_name: str, payload: dict, env: dict) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(WORKFLOW_DIR / script_name)],
        input=json.dumps(payload, ensure_ascii=False),
        cwd=str(REPO_ROOT),
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


@pytest.fixture
def hook_runner(hook_env):
    """hook スクリプトを subprocess で実行するヘルパー。"""

    def run(script_name: str, payload: dict) -> subprocess.CompletedProcess[str]:
        return _run_hook(script_name, payload, hook_env)

    return run


def parse_hook_output(result: subprocess.CompletedProcess[str]) -> dict:
    """hook の stdout JSON をパースして返す。空なら空 dict。"""
    if not result.stdout:
        return {}
    return json.loads(result.stdout)


def get_decision(result: subprocess.CompletedProcess[str]) -> str:
    """hook 出力から permissionDecision を取得。"""
    payload = parse_hook_output(result)
    return payload.get("hookSpecificOutput", {}).get("permissionDecision", "")


def load_state(home: Path, session_id: str) -> dict:
    """workflow state ファイルを読む。"""
    path = home / ".claude" / f"devkit-workflow-{session_id}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def write_task(home: Path, session_id: str, task_id: str, subject: str) -> None:
    """タスクファイルを書き込む。"""
    task_dir = home / ".claude" / "tasks" / session_id
    task_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "id": task_id,
        "subject": subject,
        "description": "",
        "activeForm": "",
        "status": "pending",
        "blocks": [],
        "blockedBy": [],
        "metadata": {"phase": "implementation_completed"},
    }
    (task_dir / f"{task_id}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


SESSION_ID = "pytest-dig-test"
