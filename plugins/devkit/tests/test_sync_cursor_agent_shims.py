from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import require_symlink_support


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "plugins/devkit/skills/setup/scripts/sync_cursor_agent_shims.py"


def _run(
    install_dir: Path | None,
    *args: str,
    platform: str = "win32",
    env: dict[str, str] | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    command = [sys.executable, str(SCRIPT), "--platform", platform]
    if install_dir is not None:
        command.extend(["--install-dir", str(install_dir)])
    command.extend([*args, "--format", "json"])
    return subprocess.run(command, check=check, capture_output=True, text=True, env=env)


def _payload(result: subprocess.CompletedProcess[str]) -> dict[str, object]:
    return json.loads(result.stdout)


def _make_commands(install_dir: Path, *, agent: bool = True) -> None:
    install_dir.mkdir(parents=True)
    (install_dir / "cursor-agent.cmd").write_text("@echo off\r\n", encoding="utf-8")
    if agent:
        (install_dir / "agent.cmd").write_text("@echo off\r\n", encoding="utf-8")


def _expected(name: str) -> bytes:
    return f'#!/bin/sh\nexec "$(dirname "$0")/{name}.cmd" "$@"\n'.encode()


def test_creates_both_shims_and_is_idempotent(tmp_path: Path):
    install_dir = tmp_path / "cursor-agent"
    _make_commands(install_dir)

    first = _payload(_run(install_dir))
    assert first["changed"] is True
    for name in ("cursor-agent", "agent"):
        shim = install_dir / name
        assert shim.read_bytes() == _expected(name)
        if os.name != "nt":
            assert stat.S_IMODE(shim.stat().st_mode) & 0o111 == 0o111

    second = _payload(_run(install_dir))
    assert second == {"actions": [], "changed": False, "skipped": True}


def test_check_does_not_write(tmp_path: Path):
    install_dir = tmp_path / "cursor-agent"
    _make_commands(install_dir)

    payload = _payload(_run(install_dir, "--check"))
    assert payload["changed"] is True
    assert not (install_dir / "cursor-agent").exists()


def test_replaces_wrong_content(tmp_path: Path):
    install_dir = tmp_path / "cursor-agent"
    _make_commands(install_dir)
    shim = install_dir / "cursor-agent"
    shim.write_text("wrong", encoding="utf-8")
    shim.chmod(0o755)

    _run(install_dir)
    assert shim.read_bytes() == _expected("cursor-agent")


def test_repairs_executable_bits_only(tmp_path: Path):
    if os.name == "nt":
        pytest.skip("[platform] POSIX 実行ビットは Windows のファイルシステムでは表現できない")
    install_dir = tmp_path / "cursor-agent"
    _make_commands(install_dir)
    shim = install_dir / "cursor-agent"
    shim.write_bytes(_expected("cursor-agent"))
    shim.chmod(0o644)

    payload = _payload(_run(install_dir))
    assert payload["changed"] is True
    assert any(str(action).startswith("chmod_755:") for action in payload["actions"])
    assert stat.S_IMODE(shim.stat().st_mode) & 0o111 == 0o111


def test_non_windows_skips(tmp_path: Path):
    payload = _payload(_run(tmp_path, platform="linux"))
    assert payload["skipped"] is True
    assert "skip_unsupported_platform:linux" in payload["actions"]


def test_missing_localappdata_skips():
    env = os.environ.copy()
    env.pop("LOCALAPPDATA", None)
    payload = _payload(_run(None, env=env))
    assert payload["skipped"] is True
    assert "skip_localappdata_unset" in payload["actions"]


def test_not_installed_skips(tmp_path: Path):
    payload = _payload(_run(tmp_path / "missing"))
    assert payload["skipped"] is True
    assert any(str(action).startswith("skip_not_installed:") for action in payload["actions"])


def test_missing_agent_command_partially_skips(tmp_path: Path):
    install_dir = tmp_path / "cursor-agent"
    _make_commands(install_dir, agent=False)

    payload = _payload(_run(install_dir))
    assert payload["changed"] is True
    assert (install_dir / "cursor-agent").is_file()
    assert not (install_dir / "agent").exists()
    assert any(str(action).startswith("skip_missing_command:") for action in payload["actions"])


@pytest.mark.parametrize("kind", ["directory", "symlink"])
def test_irregular_shim_is_error_but_other_shim_is_processed(tmp_path: Path, kind: str):
    install_dir = tmp_path / "cursor-agent"
    _make_commands(install_dir)
    irregular = install_dir / "cursor-agent"
    if kind == "directory":
        irregular.mkdir()
    else:
        require_symlink_support()
        target = tmp_path / "target"
        target.write_text("unchanged", encoding="utf-8")
        irregular.symlink_to(target)

    result = _run(install_dir, check=False)
    assert result.returncode != 0
    payload = _payload(result)
    assert any(str(action).startswith("error_irregular_path:") for action in payload["actions"])
    assert (install_dir / "agent").read_bytes() == _expected("agent")


def test_failures_without_successful_writes_report_unchanged(tmp_path: Path):
    install_dir = tmp_path / "cursor-agent"
    _make_commands(install_dir)
    (install_dir / "cursor-agent").mkdir()
    (install_dir / "agent").mkdir()

    result = _run(install_dir, check=False)
    assert result.returncode != 0
    payload = _payload(result)
    assert payload["changed"] is False
    assert payload["skipped"] is False
