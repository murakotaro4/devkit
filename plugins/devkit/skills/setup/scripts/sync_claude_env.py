#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import stat
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


MANAGED_ENV = {
    "CLAUDE_CODE_AUTO_COMPACT_WINDOW": "1000000",
    "CLAUDE_AUTOCOMPACT_PCT_OVERRIDE": "50",
}


def dump_result(changed: bool, actions: list[str]) -> None:
    print(
        json.dumps(
            {"changed": changed, "skipped": not changed, "actions": actions},
            ensure_ascii=False,
            sort_keys=True,
        )
    )


def _load_settings(path: Path) -> tuple[dict[str, object], bytes | None, int]:
    if path.is_symlink():
        raise ValueError(f"refusing to replace symlink: {path}")
    if path.exists() and not path.is_file():
        raise ValueError(f"refusing to replace non-file: {path}")
    if not path.exists():
        return {}, None, 0o644

    original = path.read_bytes()
    try:
        settings = json.loads(original.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid JSON in settings file: {path}") from exc
    if not isinstance(settings, dict):
        raise ValueError("settings JSON top level must be an object")
    env = settings.get("env", {})
    if not isinstance(env, dict):
        raise ValueError("settings JSON env must be an object")
    return settings, original, stat.S_IMODE(path.stat().st_mode)


def _backup(path: Path, original: bytes) -> Path:
    backup_dir = path.parent / "devkit-env-backup"
    backup_dir.mkdir(parents=True, exist_ok=True)
    for _attempt in range(100):
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        backup = backup_dir / f"settings.json.{timestamp}.bak"
        try:
            fd = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            continue
        break
    else:
        raise OSError("could not allocate a collision-free settings backup path")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(original)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        try:
            backup.unlink()
        except OSError:
            pass
        raise
    return backup


def _atomic_write(path: Path, content: bytes, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.devkit-tmp.")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary_name, mode)
        os.replace(temporary_name, path)
    finally:
        try:
            os.unlink(temporary_name)
        except OSError:
            pass


def sync(settings_file: Path, dry_run: bool) -> tuple[bool, list[str]]:
    settings, original, mode = _load_settings(settings_file)
    env = dict(settings.get("env", {}))
    changed_keys = [key for key, value in MANAGED_ENV.items() if env.get(key) != value]
    if not changed_keys:
        return False, []

    env.update(MANAGED_ENV)
    desired = dict(settings)
    desired["env"] = env
    content = (json.dumps(desired, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    actions = [f"set_env:{key}" for key in changed_keys]
    if dry_run:
        if original is not None:
            actions.insert(0, f"backup:{settings_file}")
        actions.append(f"write:{settings_file}")
        return True, actions

    if original is not None:
        backup = _backup(settings_file, original)
        actions.insert(0, f"backup:{backup}")
    _atomic_write(settings_file, content, mode)
    actions.append(f"write:{settings_file}")
    return True, actions


def main() -> int:
    parser = argparse.ArgumentParser(description="Synchronize Claude Code compaction environment settings.")
    parser.add_argument(
        "--settings-file",
        default=str(Path.home() / ".claude/settings.json"),
        help="Claude Code settings.json path",
    )
    parser.add_argument("--check", action="store_true", help="Report planned changes without writing files")
    parser.add_argument("--format", choices=["json"], default="json", help="Output format")
    args = parser.parse_args()

    actions: list[str] = []
    try:
        changed, actions = sync(Path(args.settings_file), args.check)
    except (OSError, ValueError) as exc:
        actions.append(f"error:{exc}")
        dump_result(False, actions)
        print(str(exc), file=sys.stderr)
        return 1
    dump_result(changed, actions)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
