"""テスト共通フィクスチャ."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

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


# ---------------------------------------------------------------------------
# symlink サポート probe(全テストファイル共通)
# ---------------------------------------------------------------------------
#
# 各テストファイルが個別に実装していた同型の probe(tempfile.TemporaryDirectory
# 内でディレクトリ symlink を試みて OSError / NotImplementedError なら不可と
# 判定する)をここへ集約する。結果はモジュールレベルでキャッシュし、テストごとの
# 再計測コストを避ける。


def _probe_symlink_support() -> bool:
    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            probe_dir = Path(tmp_dir)
            target = probe_dir / "target"
            target.mkdir()
            (probe_dir / "link").symlink_to(target, target_is_directory=True)
    except (OSError, NotImplementedError):
        return False
    return True


SYMLINK_SUPPORTED = _probe_symlink_support()


def require_symlink_support() -> None:
    """symlink 作成権限がない環境では呼び出し元テストを skip する。"""
    if not SYMLINK_SUPPORTED:
        pytest.skip("[symlink] symlink creation is unavailable in this environment")


# ---------------------------------------------------------------------------
# skip 理由プレフィックス規約の strict 検査
# ---------------------------------------------------------------------------
#
# すべての skip(宣言的 skipif・実行時 pytest.skip の両方)の reason には、
# 機械判定可能なプレフィックス([platform] / [symlink] / [tool:xxx])を付ける
# 規約を敷いている。DEVKIT_STRICT_SKIPS=1 のとき、収集した全 skip の reason が
# DEVKIT_ALLOWED_SKIP_PREFIXES(カンマ区切り)のいずれかで始まることを
# session 終端で強制する。CI はこの環境変数を渡し、原理的に残る skip だけを
# 許容リストに載せることで「直せる skip がこっそり残る」ドリフトを防ぐ。

_SKIP_REPORTS: list[tuple[str, str]] = []


def _extract_skip_reason(report: pytest.TestReport) -> str | None:
    longrepr = report.longrepr
    if isinstance(longrepr, tuple) and len(longrepr) == 3:
        reason = longrepr[2]
        if isinstance(reason, str):
            prefix = "Skipped: "
            if reason.startswith(prefix):
                return reason[len(prefix) :]
            return reason
    return None


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    if not report.skipped:
        return
    # xfail(strict=False)由来の "skipped" 表示は skip 規約の対象外(誤検出防止)。
    if hasattr(report, "wasxfail"):
        return
    reason = _extract_skip_reason(report)
    if reason is None:
        return
    _SKIP_REPORTS.append((report.nodeid, reason))


@pytest.hookimpl(hookwrapper=True)
def pytest_sessionfinish(session: pytest.Session, exitstatus: int):
    yield
    if os.environ.get("DEVKIT_STRICT_SKIPS") != "1":
        return
    allowed_prefixes = [
        prefix
        for prefix in os.environ.get("DEVKIT_ALLOWED_SKIP_PREFIXES", "").split(",")
        if prefix
    ]

    def is_allowed(reason: str) -> bool:
        return any(reason.startswith(prefix) for prefix in allowed_prefixes)

    violations = [(nodeid, reason) for nodeid, reason in _SKIP_REPORTS if not is_allowed(reason)]
    if violations:
        print("DEVKIT_STRICT_SKIPS: disallowed skip(s) detected:", file=sys.stderr)
        for nodeid, reason in violations:
            print(f"  {nodeid}: {reason}", file=sys.stderr)
        session.exitstatus = 1
