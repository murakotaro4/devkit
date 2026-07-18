#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import stat
import sys
from pathlib import Path, PurePosixPath


MANIFEST_NAME = ".devkit-sync-manifest.json"
MANIFEST_VERSION = 1
MANAGED_ROOTS = {"skills", "templates", "scripts", "statusline"}
sys.dont_write_bytecode = True


def dump_result(
    changed: bool,
    actions: list[str],
    *,
    reason: str | None = None,
) -> None:
    payload: dict[str, object] = {
        "changed": changed,
        "skipped": not changed,
        "actions": actions,
    }
    if reason is not None:
        payload["reason"] = reason
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def _is_regular_file(path: Path) -> bool:
    try:
        mode = path.lstat().st_mode
    except OSError:
        return False
    return stat.S_ISREG(mode)


def _read_manifest(path: Path) -> dict[str, str] | None:
    if not _is_regular_file(path):
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or payload.get("version") != MANIFEST_VERSION:
        return None
    files = payload.get("files")
    if not isinstance(files, dict):
        return None
    if not all(
        isinstance(key, str)
        and isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
        and "\\" not in key
        and not PurePosixPath(key).is_absolute()
        and PurePosixPath(key).as_posix() == key
        and ".." not in PurePosixPath(key).parts
        and len(PurePosixPath(key).parts) >= 2
        and PurePosixPath(key).parts[0] in MANAGED_ROOTS
        for key, value in files.items()
    ):
        return None
    return dict(files)


def _path_kind(target: Path, destination: Path) -> str:
    relative = destination.relative_to(target)
    current = target
    for part in relative.parts[:-1]:
        current = current / part
        try:
            mode = current.lstat().st_mode
        except FileNotFoundError:
            continue
        except OSError:
            return "irregular"
        if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
            return "irregular"
    try:
        mode = destination.lstat().st_mode
    except FileNotFoundError:
        return "missing"
    except OSError:
        return "irregular"
    if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
        return "irregular"
    return "regular"


def _sha256_file(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _manifest_bytes(files: dict[str, str]) -> bytes:
    payload = {"version": MANIFEST_VERSION, "files": dict(sorted(files.items()))}
    return (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _remove_empty_managed_dirs(target: Path, start: Path) -> None:
    managed_roots = {target / name for name in MANAGED_ROOTS}
    current = start
    while current != target and any(current == root or root in current.parents for root in managed_roots):
        try:
            current.rmdir()
        except OSError:
            break
        current = current.parent


def prune_legacy_cursor_sync(
    target: Path,
    dry_run: bool,
) -> tuple[bool, list[str], str | None]:
    target = target.expanduser()
    if not target.exists() and not target.is_symlink():
        return False, [], "cursor target directory does not exist"
    if target.is_symlink() or not target.is_dir():
        return False, [f"skip_irregular:{target}"], "cursor target is not a regular directory"

    manifest_path = target / MANIFEST_NAME
    if not manifest_path.exists() and not manifest_path.is_symlink():
        return False, [], "legacy Cursor sync manifest does not exist"
    previous = _read_manifest(manifest_path)
    if previous is None:
        raise SystemExit(
            f"invalid Cursor sync manifest: {manifest_path}; "
            "delete the manifest to disable legacy prune"
        )

    actions: list[str] = []
    prunes: list[str] = []
    remaining: dict[str, str] = {}
    for relpath, expected_hash in sorted(previous.items()):
        destination = target / relpath
        kind = _path_kind(target, destination)
        if kind == "missing":
            continue
        if kind == "irregular":
            actions.append(f"skip_irregular:{relpath}")
            remaining[relpath] = expected_hash
            continue
        actual_hash = _sha256_file(destination)
        if actual_hash is None:
            actions.append(f"skip_irregular:{relpath}")
            remaining[relpath] = expected_hash
            continue
        if actual_hash != expected_hash:
            actions.append(f"skip_prune_modified:{relpath}")
            remaining[relpath] = expected_hash
            continue
        actions.append(f"prune:{relpath}")
        prunes.append(relpath)

    if remaining:
        desired_manifest = _manifest_bytes(remaining)
        manifest_changed = remaining != previous
        if manifest_changed:
            actions.append(f"write_manifest:{MANIFEST_NAME}")
    else:
        manifest_changed = True
        actions.append(f"prune_manifest:{MANIFEST_NAME}")

    changed = bool(prunes or manifest_changed)
    if dry_run or not changed:
        return changed, actions, None

    for relpath in prunes:
        destination = target / relpath
        destination.unlink()
        _remove_empty_managed_dirs(target, destination.parent)

    if remaining:
        manifest_path.write_bytes(desired_manifest)
    else:
        manifest_path.unlink()
    return True, actions, None


def main() -> int:
    parser = argparse.ArgumentParser(description="Prune legacy DevKit Cursor skill sync assets.")
    parser.add_argument("--check", action="store_true", help="Report planned changes without writing files")
    parser.add_argument("--format", choices=["json"], default="json", help="Output format")
    parser.add_argument("--target", type=Path, default=Path.home() / ".cursor")
    args = parser.parse_args()

    changed, actions, reason = prune_legacy_cursor_sync(args.target, args.check)
    dump_result(changed, actions, reason=reason)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
