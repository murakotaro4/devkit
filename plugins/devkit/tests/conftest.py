"""テスト共通フィクスチャ."""

from __future__ import annotations

import os

import pytest


@pytest.fixture(autouse=True)
def _clean_git_env(monkeypatch):
    # git hook(pre-commit / pre-push)経由の実行では GIT_DIR / GIT_INDEX_FILE 等が
    # 親リポジトリを指したまま伝播し、tmp_path に作るテスト用リポジトリへの git 操作が
    # 実リポジトリを参照してしまう(linked worktree では GIT_DIR が絶対パスになり顕在化)。
    # テストの密閉性を保つため GIT_* を除去する。
    for key in list(os.environ):
        if key.startswith("GIT_"):
            monkeypatch.delenv(key, raising=False)
