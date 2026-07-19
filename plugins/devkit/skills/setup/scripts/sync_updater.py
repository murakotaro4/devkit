#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import stat
from pathlib import Path


POSIX_FILES = ("update-ccx.sh", "devkit-lib.sh")
WINDOWS_FILES = (
    "update-ccx.sh",
    "devkit-lib.sh",
    "update-ccx.cmd",
    "devkit-lib.ps1",
    "devkit-setup.ps1",
    "devkit-codex-config.ps1",
    "update-ccx.ps1",
)
LEGACY_CODEX_BIN_FILES = ("update-devkit.sh", "update-devkit.ps1", "update-devkit.cmd")
LEGACY_LOCAL_BIN_FILES = ("update-devkit", "update-devkit.cmd")


def default_source_dir() -> Path:
    skill_dir = Path(__file__).resolve().parent.parent
    return (skill_dir / "../../scripts").resolve()


def shell_shim(target_script: Path) -> bytes:
    return (
        "#!/bin/bash\n"
        "set -euo pipefail\n"
        f'exec "{target_script}" "$@"\n'
    ).encode("utf-8")


def cmd_shim(target_command: Path) -> bytes:
    return (
        "@echo off\r\n"
        "setlocal\r\n"
        f'call "{target_command}" %*\r\n'
        "exit /b %ERRORLEVEL%\r\n"
    ).encode("utf-8")


def dump_result(changed: bool, actions: list[str]) -> None:
    payload = {
        "changed": changed,
        "skipped": not changed,
        "actions": actions,
    }
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def _needs_executable(path: Path) -> bool:
    if path.is_symlink() or not path.exists():
        return True
    executable_bits = stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
    return path.stat().st_mode & executable_bits != executable_bits


def _path_present(path: Path) -> bool:
    return path.exists() or path.is_symlink()


def _prune_file(path: Path) -> None:
    try:
        path.unlink()
    except OSError as exc:
        if _path_present(path):
            raise RuntimeError(f"failed to prune updater remnant: {path}") from exc
    if _path_present(path):
        raise RuntimeError(f"failed to prune updater remnant: {path}")


def sync_updater(
    home: Path,
    source_dir: Path,
    platform: str,
    dry_run: bool,
) -> tuple[bool, list[str]]:
    if platform not in {"posix", "windows"}:
        raise ValueError(f"unsupported platform: {platform}")

    home = home.resolve()
    source_dir = source_dir.resolve()
    codex_bin = home / ".codex/bin"
    local_bin = home / ".local/bin"
    file_names = POSIX_FILES if platform == "posix" else WINDOWS_FILES
    actions: list[str] = []
    desired_files: dict[Path, bytes] = {}

    for file_name in file_names:
        source = source_dir / file_name
        if not source.is_file():
            raise SystemExit(f"missing updater source: {source}")
        destination = codex_bin / file_name
        source_content = source.read_bytes()
        if destination.exists() and not destination.is_file() and not destination.is_symlink():
            raise SystemExit(f"refusing to replace non-file: {destination}")
        if destination.is_symlink():
            actions.append(f"replace_symlink:{destination}")
            destination_content = None
        else:
            destination_content = destination.read_bytes() if destination.is_file() else None
        if destination_content != source_content:
            actions.append(f"copy:{destination}")
        desired_files[destination] = source_content

    executable = codex_bin / "update-ccx.sh"
    if platform == "posix" and _needs_executable(executable):
        actions.append(f"chmod+x:{executable}")

    if platform == "posix":
        shim_path = local_bin / "update-ccx"
        desired_shim = shell_shim(executable)
    else:
        shim_path = local_bin / "update-ccx.cmd"
        desired_shim = cmd_shim(codex_bin / "update-ccx.cmd")
    if shim_path.exists() and not shim_path.is_file() and not shim_path.is_symlink():
        raise SystemExit(f"refusing to replace non-file: {shim_path}")
    if shim_path.is_symlink():
        actions.append(f"replace_symlink:{shim_path}")
        existing_shim = None
    else:
        existing_shim = shim_path.read_bytes() if shim_path.is_file() else None
    if existing_shim != desired_shim:
        actions.append(f"write_shim:{shim_path}")

    legacy_paths = [*(codex_bin / name for name in LEGACY_CODEX_BIN_FILES)]
    legacy_paths.extend(local_bin / name for name in LEGACY_LOCAL_BIN_FILES)
    for legacy_path in legacy_paths:
        if _path_present(legacy_path):
            if legacy_path.is_dir() and not legacy_path.is_symlink():
                raise SystemExit(f"refusing to prune directory: {legacy_path}")
            actions.append(f"prune:{legacy_path}")

    changed = bool(actions)
    if dry_run or not changed:
        return changed, actions

    codex_bin.mkdir(parents=True, exist_ok=True)
    local_bin.mkdir(parents=True, exist_ok=True)
    for destination, source_content in desired_files.items():
        if destination.is_symlink():
            destination.unlink()
        if (destination.read_bytes() if destination.is_file() else None) != source_content:
            destination.write_bytes(source_content)

    if platform == "posix" and _needs_executable(executable):
        executable.chmod(executable.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    if shim_path.is_symlink():
        shim_path.unlink()
    if (shim_path.read_bytes() if shim_path.is_file() else None) != desired_shim:
        shim_path.write_bytes(desired_shim)
    if platform == "posix":
        shim_path.chmod(shim_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    for legacy_path in legacy_paths:
        if _path_present(legacy_path):
            _prune_file(legacy_path)

    return True, actions


def main() -> int:
    parser = argparse.ArgumentParser(description="Synchronize the installed DevKit updater.")
    parser.add_argument("--check", action="store_true", help="Report planned changes without writing files")
    parser.add_argument("--format", choices=["json"], default="json", help="Output format")
    args = parser.parse_args()

    platform = "windows" if os.name == "nt" else "posix"
    changed, actions = sync_updater(Path.home(), default_source_dir(), platform, args.check)
    dump_result(changed, actions)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
