"""skip 理由プレフィックス規約の strict 検査(conftest.py の hook)に対するメタテスト.

conftest.py の pytest_runtest_logreport / pytest_sessionfinish hook は、
DEVKIT_STRICT_SKIPS=1 のとき「reason が DEVKIT_ALLOWED_SKIP_PREFIXES のいずれかで
始まらない skip」が 1 件でもあれば session の exitstatus を非 0 に上書きする。

この検査ロジック自体を回帰から守るため、pytest を subprocess として起動し、
合成テストファイル(非許可 skip 1 件 + 許可 skip 1 件)に対して strict hook が
期待どおり動くことを確認する。検査ロジックを複製せず、実物の
plugins/devkit/tests/conftest.py が定義する hook 関数をそのまま実行させるために、
importlib でその実ファイルを読み込んで再公開するだけの conftest.py を合成先へ
書き出す(合成テストは repo の tests/ 配下ではなく tmp_path に置き、repo の
pytest.ini_options / pythonpath の影響を受けない独立したセッションで実行する)。
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
REAL_CONFTEST = ROOT / "plugins" / "devkit" / "tests" / "conftest.py"

SYNTHETIC_CONFTEST_TEMPLATE = '''\
"""tmp_path 合成テスト用 conftest。本物の conftest.py の hook 関数をそのまま再公開する
(検査ロジックの複製ではなく、実ファイルを importlib で読み込んで再利用する)。
"""
import importlib.util

_spec = importlib.util.spec_from_file_location(
    "devkit_real_conftest_under_test", {real_conftest_path!r}
)
_real_conftest = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_real_conftest)

pytest_runtest_logreport = _real_conftest.pytest_runtest_logreport
pytest_sessionfinish = _real_conftest.pytest_sessionfinish
'''

SYNTHETIC_TEST_FILE = '''\
import pytest


def test_disallowed_skip():
    pytest.skip("[tool:bash] gone")


def test_allowed_skip():
    pytest.skip("[platform] n/a")
'''


def _write_synthetic_suite(tmp_path: Path) -> Path:
    (tmp_path / "conftest.py").write_text(
        SYNTHETIC_CONFTEST_TEMPLATE.format(real_conftest_path=str(REAL_CONFTEST)),
        encoding="utf-8",
    )
    test_file = tmp_path / "test_synthetic_skips.py"
    test_file.write_text(SYNTHETIC_TEST_FILE, encoding="utf-8")
    return test_file


def _run_pytest(test_file: Path, tmp_path: Path, extra_env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    # 親プロセス(このメタテスト自身)の DEVKIT_STRICT_SKIPS / DEVKIT_ALLOWED_SKIP_PREFIXES
    # を継承しないよう明示的に取り除いてから、シナリオごとの値だけを与える。
    env.pop("DEVKIT_STRICT_SKIPS", None)
    env.pop("DEVKIT_ALLOWED_SKIP_PREFIXES", None)
    env.update(extra_env)

    return subprocess.run(
        [sys.executable, "-m", "pytest", str(test_file), "-p", "no:cacheprovider", "-q"],
        cwd=str(tmp_path),
        env=env,
        capture_output=True,
        text=True,
    )


def test_strict_skips_guard_fails_when_disallowed_skip_present(tmp_path):
    test_file = _write_synthetic_suite(tmp_path)

    result = _run_pytest(
        test_file,
        tmp_path,
        {"DEVKIT_STRICT_SKIPS": "1", "DEVKIT_ALLOWED_SKIP_PREFIXES": "[platform]"},
    )

    assert result.returncode != 0, result.stdout + result.stderr
    output = result.stdout + result.stderr
    assert "test_disallowed_skip" in output
    assert "[tool:bash] gone" in output


def test_strict_skips_guard_passes_when_all_skips_allowlisted(tmp_path):
    test_file = _write_synthetic_suite(tmp_path)

    result = _run_pytest(
        test_file,
        tmp_path,
        {
            "DEVKIT_STRICT_SKIPS": "1",
            "DEVKIT_ALLOWED_SKIP_PREFIXES": "[platform],[tool:bash]",
        },
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_strict_skips_guard_is_noop_when_strict_flag_unset(tmp_path):
    test_file = _write_synthetic_suite(tmp_path)

    result = _run_pytest(test_file, tmp_path, {})

    assert result.returncode == 0, result.stdout + result.stderr
