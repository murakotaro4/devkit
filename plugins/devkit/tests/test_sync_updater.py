from __future__ import annotations

import importlib.util
import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = ROOT / "plugins/devkit/skills/setup/scripts/sync_updater.py"
DEVKIT_LIB_SH = ROOT / "plugins/devkit/scripts/devkit-lib.sh"
DEVKIT_LIB_PS1 = ROOT / "plugins/devkit/scripts/devkit-lib.ps1"
SPEC = importlib.util.spec_from_file_location("sync_updater", SCRIPT_PATH)
assert SPEC and SPEC.loader
sync_updater = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sync_updater)


def _source_tree(tmp_path: Path) -> Path:
    source = tmp_path / "scripts"
    source.mkdir()
    for name in (*sync_updater.POSIX_FILES, *sync_updater.WINDOWS_FILES):
        (source / name).write_text(f"source:{name}\n", encoding="utf-8")
    return source


def test_posix_sync_is_idempotent_and_uses_expected_targets(tmp_path):
    home = tmp_path / "home"
    source = _source_tree(tmp_path)

    first_changed, first_actions = sync_updater.sync_updater(home, source, "posix", False)

    assert first_changed is True
    assert first_actions
    assert {path.name for path in (home / ".codex/bin").iterdir()} == set(sync_updater.POSIX_FILES)
    assert {path.name for path in (home / ".local/bin").iterdir()} == {"update-ccx"}
    mode = (home / ".codex/bin/update-ccx.sh").stat().st_mode
    assert mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH) == (
        stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
    )

    second = sync_updater.sync_updater(home, source, "posix", False)

    assert second == (False, [])


def test_windows_sync_uses_expected_targets(tmp_path):
    home = tmp_path / "home"
    source = _source_tree(tmp_path)

    changed, actions = sync_updater.sync_updater(home, source, "windows", False)

    assert changed is True
    assert actions
    assert {path.name for path in (home / ".codex/bin").iterdir()} == set(sync_updater.WINDOWS_FILES)
    assert {path.name for path in (home / ".local/bin").iterdir()} == {"update-ccx.cmd"}


def test_shims_match_devkit_lib_implementations(tmp_path):
    home = tmp_path / "home"
    source = _source_tree(tmp_path)
    sync_updater.sync_updater(home, source, "posix", False)

    posix_target = home.resolve() / ".codex/bin/update-ccx.sh"
    assert (home / ".local/bin/update-ccx").read_bytes() == (
        b"#!/bin/bash\n"
        b"set -euo pipefail\n"
        + f'exec "{posix_target}" "$@"\n'.encode()
    )

    windows_home = tmp_path / "windows-home"
    sync_updater.sync_updater(windows_home, source, "windows", False)
    windows_target = windows_home.resolve() / ".codex/bin/update-ccx.cmd"
    assert (windows_home / ".local/bin/update-ccx.cmd").read_bytes() == (
        b"@echo off\r\n"
        b"setlocal\r\n"
        + f'call "{windows_target}" %*\r\n'.encode()
        + b"exit /b %ERRORLEVEL%\r\n"
    )

    shell_implementation = DEVKIT_LIB_SH.read_text(encoding="utf-8").split(
        "install_devkit_shell_shim()", 1
    )[1].split("devkit_legacy_skill_entry_name()", 1)[0]
    for contract_line in ('#!/bin/bash', 'set -euo pipefail', 'exec "$target_script" "\\$@"'):
        assert contract_line in shell_implementation

    cmd_implementation = DEVKIT_LIB_PS1.read_text(encoding="utf-8").split(
        "function Install-DevKitCommandShim", 1
    )[1].split("function Install-DevKitShellShim", 1)[0]
    for contract_line in ("@echo off", "setlocal", 'call `"$TargetCommandPath`" %*', "exit /b %ERRORLEVEL%"):
        assert contract_line in cmd_implementation


def test_sync_replaces_managed_symlinks_without_touching_their_targets(tmp_path):
    home = tmp_path / "home"
    source = _source_tree(tmp_path)
    codex_bin = home / ".codex/bin"
    local_bin = home / ".local/bin"
    codex_bin.mkdir(parents=True)
    local_bin.mkdir(parents=True)
    external_script = tmp_path / "external-script"
    external_shim = tmp_path / "external-shim"
    external_script.write_text("external script\n", encoding="utf-8")
    external_shim.write_text("external shim\n", encoding="utf-8")
    managed_script = codex_bin / "update-ccx.sh"
    managed_shim = local_bin / "update-ccx"
    try:
        managed_script.symlink_to(external_script)
        managed_shim.symlink_to(external_shim)
    except OSError:
        pytest.skip("symlink creation is unavailable in this environment")

    changed, actions = sync_updater.sync_updater(home, source, "posix", False)

    assert changed is True
    assert f"replace_symlink:{managed_script}" in actions
    assert f"replace_symlink:{managed_shim}" in actions
    assert not managed_script.is_symlink()
    assert not managed_shim.is_symlink()
    assert external_script.read_text(encoding="utf-8") == "external script\n"
    assert external_shim.read_text(encoding="utf-8") == "external shim\n"


def test_sync_prunes_all_update_devkit_remnants_and_records_actions(tmp_path):
    home = tmp_path / "home"
    source = _source_tree(tmp_path)
    codex_bin = home / ".codex/bin"
    local_bin = home / ".local/bin"
    codex_bin.mkdir(parents=True)
    local_bin.mkdir(parents=True)
    legacy_paths = [
        *(codex_bin / name for name in sync_updater.LEGACY_CODEX_BIN_FILES),
        *(local_bin / name for name in sync_updater.LEGACY_LOCAL_BIN_FILES),
    ]
    for path in legacy_paths:
        path.write_text("legacy\n", encoding="utf-8")

    changed, actions = sync_updater.sync_updater(home, source, "posix", False)

    assert changed is True
    for path in legacy_paths:
        assert not path.exists()
        assert f"prune:{path.resolve()}" in actions


def test_check_reports_changes_without_writing(tmp_path):
    home = tmp_path / "home"
    legacy = home / ".codex/bin/update-devkit.sh"
    source_root = home / ".codex/devkit/source-root.txt"
    legacy.parent.mkdir(parents=True)
    source_root.parent.mkdir(parents=True)
    legacy.write_text("legacy\n", encoding="utf-8")
    source_root.write_text("keep-this-root\n", encoding="utf-8")
    env = os.environ.copy()
    env["HOME"] = str(home)

    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--check", "--format", "json"],
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(result.stdout)
    assert payload["changed"] is True
    assert payload["skipped"] is False
    assert payload["actions"]
    assert legacy.read_text(encoding="utf-8") == "legacy\n"
    assert source_root.read_text(encoding="utf-8") == "keep-this-root\n"
    assert not (home / ".codex/bin/update-ccx.sh").exists()
    assert not (home / ".local").exists()
