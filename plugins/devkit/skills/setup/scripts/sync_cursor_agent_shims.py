#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import stat
import sys
import tempfile
from pathlib import Path


SHIM_NAMES = ("cursor-agent", "agent")
EXECUTABLE_BITS = stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH


def dump_result(changed: bool, actions: list[str], *, skipped: bool | None = None) -> None:
    print(
        json.dumps(
            {
                "changed": changed,
                "skipped": not changed if skipped is None else skipped,
                "actions": actions,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


def shim_content(name: str) -> bytes:
    return f'#!/bin/sh\nexec "$(dirname "$0")/{name}.cmd" "$@"\n'.encode("utf-8")


def _is_executable(path: Path) -> bool:
    if os.name == "nt":
        # Windows の stat/chmod は POSIX 実行 bit を表現できない。Git Bash からは
        # shebang 付き通常ファイルを実行できるため、内容一致を実行可能として扱う。
        return True
    return path.stat().st_mode & EXECUTABLE_BITS == EXECUTABLE_BITS


def _atomic_write(path: Path, content: bytes) -> None:
    fd, temporary_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.devkit-tmp.")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary_name, 0o755)
        os.replace(temporary_name, path)
    finally:
        try:
            os.unlink(temporary_name)
        except OSError:
            pass


def sync(install_dir: Path, dry_run: bool) -> tuple[bool, list[str], bool, bool]:
    actions: list[str] = []
    cursor_cmd = install_dir / "cursor-agent.cmd"
    if not cursor_cmd.is_file():
        return False, [f"skip_not_installed:{cursor_cmd}"], True, False

    changed = False
    errors = False
    for name in SHIM_NAMES:
        command = install_dir / f"{name}.cmd"
        shim = install_dir / name
        if name != "cursor-agent" and not command.is_file():
            actions.append(f"skip_missing_command:{command}")
            continue
        try:
            if shim.is_symlink() or (shim.exists() and not shim.is_file()):
                actions.append(f"error_irregular_path:{shim}")
                errors = True
                continue

            desired = shim_content(name)
            content_matches = shim.is_file() and shim.read_bytes() == desired
            executable_matches = shim.is_file() and _is_executable(shim)
            if content_matches and executable_matches:
                continue

            if not content_matches:
                actions.append(f"write_shim:{shim}")
            if not executable_matches:
                actions.append(f"chmod_755:{shim}")
            if dry_run:
                changed = True
                continue
            if not content_matches:
                _atomic_write(shim, desired)
            else:
                shim.chmod(0o755)
            changed = True
        except OSError as exc:
            actions.append(f"error_sync:{shim}:{exc}")
            errors = True

    return changed, actions, not changed and not errors, errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Synchronize cursor-agent Git Bash shims on Windows.")
    parser.add_argument("--platform", default=sys.platform, help="Platform identifier (win32 is supported)")
    parser.add_argument("--install-dir", help="cursor-agent installation directory")
    parser.add_argument("--check", action="store_true", help="Report planned changes without writing files")
    parser.add_argument("--format", choices=["json"], default="json", help="Output format")
    args = parser.parse_args()

    if args.platform != "win32":
        dump_result(False, [f"skip_unsupported_platform:{args.platform}"], skipped=True)
        return 0
    if args.install_dir is None:
        local_app_data = os.environ.get("LOCALAPPDATA")
        if not local_app_data:
            dump_result(False, ["skip_localappdata_unset"], skipped=True)
            return 0
        install_dir = Path(local_app_data) / "cursor-agent"
    else:
        install_dir = Path(args.install_dir)

    actions: list[str] = []
    try:
        changed, actions, skipped, errors = sync(install_dir, args.check)
    except OSError as exc:
        actions.append(f"error:{exc}")
        dump_result(False, actions, skipped=False)
        print(str(exc), file=sys.stderr)
        return 1
    dump_result(changed, actions, skipped=skipped)
    if errors:
        print("one or more cursor-agent shims could not be synchronized", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
