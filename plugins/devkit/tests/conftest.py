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


@pytest.fixture(autouse=True)
def _isolate_home_env(monkeypatch, tmp_path_factory):
    # os.environ.copy() でサブプロセスへ環境を継承するテストが、実ユーザーの
    # HOME / USERPROFILE(= 実ホーム)を掴んでしまう経路を塞ぐ。実際に
    # ~/.codex/devkit/source-root.txt が実環境で破壊された事故を踏まえ、
    # テストごとに専用の疑似ホームを明示的に設定する(未設定のまま放置しない)。
    # 個別テストが独自の一時ホームを使う場合はこの後で上書きしてよい。
    fake_home = tmp_path_factory.mktemp("devkit-test-home")
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("USERPROFILE", str(fake_home))
