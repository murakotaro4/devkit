#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import stat
import sys
from pathlib import Path, PurePosixPath


EXPECTED_SKILLS = {
    "backlog",
    "catch-up",
    "commit-push",
    "dig-goal",
    "handoff",
    "improve-skill",
    "memory-review",
    "refactor",
    "setup",
}
MANIFEST_NAME = ".devkit-sync-manifest.json"
MANIFEST_VERSION = 1
sys.dont_write_bytecode = True


def _load_updater_file_names() -> tuple[str, ...]:
    module_path = Path(__file__).with_name("sync_updater.py")
    spec = importlib.util.spec_from_file_location("devkit_sync_updater", module_path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"failed to load updater contract: {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return tuple(module.POSIX_FILES) + tuple(module.WINDOWS_FILES)


UPDATER_FILES = _load_updater_file_names()


def default_source_dir() -> Path:
    skill_dir = Path(__file__).resolve().parent.parent
    return (skill_dir / "../..").resolve()


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


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _is_regular_file(path: Path) -> bool:
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        return False
    return stat.S_ISREG(mode)


def _trees_overlap(source: Path, target: Path) -> bool:
    source_resolved = source.resolve()
    target_resolved = target.resolve()
    return (
        source_resolved == target_resolved
        or source_resolved in target_resolved.parents
        or target_resolved in source_resolved.parents
    )


def _collect_tree(source_root: Path, relative_root: Path) -> dict[str, bytes]:
    result: dict[str, bytes] = {}
    root = source_root / relative_root
    if not root.is_dir() or root.is_symlink():
        raise SystemExit(f"missing required source directory: {root}")
    for path in sorted(root.rglob("*")):
        relative_parts = path.relative_to(root).parts
        if "__pycache__" in relative_parts or path.suffix == ".pyc":
            continue
        if path.is_symlink():
            raise SystemExit(f"source contains symlink: {path}")
        if path.is_dir():
            continue
        if not _is_regular_file(path):
            raise SystemExit(f"source contains non-regular file: {path}")
        relpath = (relative_root / path.relative_to(root)).as_posix()
        result[relpath] = path.read_bytes()
    return result


def collect_desired(source: Path) -> dict[str, bytes]:
    source = source.resolve()
    skills_dir = source / "skills"
    if not skills_dir.is_dir() or skills_dir.is_symlink():
        raise SystemExit(f"missing skills source directory: {skills_dir}")

    actual_skills = {path.name for path in skills_dir.iterdir() if path.is_dir()}
    if actual_skills != EXPECTED_SKILLS:
        raise SystemExit(
            "skills surface mismatch: "
            f"expected={sorted(EXPECTED_SKILLS)} actual={sorted(actual_skills)}"
        )

    desired: dict[str, bytes] = {}
    for skill_name in sorted(EXPECTED_SKILLS):
        skill_dir = skills_dir / skill_name
        skill_markdown = skill_dir / "SKILL.md"
        if skill_dir.is_symlink() or not _is_regular_file(skill_markdown):
            raise SystemExit(f"missing regular SKILL.md: {skill_markdown}")
        desired.update(_collect_tree(source, Path("skills") / skill_name))

    for template_name in ("rules", "codex"):
        desired.update(_collect_tree(source, Path("templates") / template_name))

    scripts_dir = source / "scripts"
    for file_name in UPDATER_FILES:
        path = scripts_dir / file_name
        if not _is_regular_file(path):
            raise SystemExit(f"missing updater source: {path}")
        desired[(Path("scripts") / file_name).as_posix()] = path.read_bytes()

    for file_name in ("install.js", "statusline.js"):
        path = source / "statusline" / file_name
        if not _is_regular_file(path):
            raise SystemExit(f"missing statusline source: {path}")
        desired[(Path("statusline") / file_name).as_posix()] = path.read_bytes()

    return desired


def _read_manifest(path: Path) -> dict[str, str] | None:
    if not path.exists() and not path.is_symlink():
        return None
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
    managed_roots = {"skills", "templates", "scripts", "statusline"}
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
        and PurePosixPath(key).parts[0] in managed_roots
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
        if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
            return "irregular"
    try:
        mode = destination.lstat().st_mode
    except FileNotFoundError:
        return "missing"
    if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
        return "irregular"
    return "regular"


def _directory_is_empty_after_prunes(target: Path, directory: Path, prunes: set[str]) -> bool:
    pending = [directory]
    while pending:
        current = pending.pop()
        try:
            children = list(current.iterdir())
        except OSError:
            return False
        for child in children:
            try:
                mode = child.lstat().st_mode
            except OSError:
                return False
            if stat.S_ISLNK(mode):
                return False
            if stat.S_ISDIR(mode):
                pending.append(child)
                continue
            if not stat.S_ISREG(mode) or child.relative_to(target).as_posix() not in prunes:
                return False
    return True


def _path_kind_after_prunes(
    target: Path,
    destination: Path,
    prunes: set[str],
) -> tuple[str, bool]:
    relative = destination.relative_to(target)
    current = target
    removed_parent = False
    for part in relative.parts[:-1]:
        current = current / part
        if removed_parent:
            continue
        try:
            mode = current.lstat().st_mode
        except FileNotFoundError:
            continue
        if stat.S_ISDIR(mode) and not stat.S_ISLNK(mode):
            continue
        if stat.S_ISREG(mode) and current.relative_to(target).as_posix() in prunes:
            removed_parent = True
            continue
        return "irregular", False
    if removed_parent:
        return "missing", False
    try:
        mode = destination.lstat().st_mode
    except FileNotFoundError:
        return "missing", False
    if stat.S_ISREG(mode):
        return "regular", False
    if stat.S_ISDIR(mode) and not stat.S_ISLNK(mode):
        removable = _directory_is_empty_after_prunes(target, destination, prunes)
        return ("missing", True) if removable else ("irregular", False)
    return "irregular", False


def _manifest_bytes(files: dict[str, str]) -> bytes:
    payload = {"version": MANIFEST_VERSION, "files": dict(sorted(files.items()))}
    return (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _remove_empty_managed_dirs(target: Path, start: Path) -> None:
    managed_roots = {target / name for name in ("skills", "templates", "scripts", "statusline")}
    current = start
    while current != target and any(current == root or root in current.parents for root in managed_roots):
        try:
            current.rmdir()
        except OSError:
            break
        current = current.parent


def _remove_empty_tree(directory: Path) -> None:
    if not directory.exists() or directory.is_symlink() or not directory.is_dir():
        return
    directories = [path for path in directory.rglob("*") if path.is_dir() and not path.is_symlink()]
    for path in sorted(directories, key=lambda item: len(item.parts), reverse=True):
        try:
            path.rmdir()
        except OSError:
            pass
    directory.rmdir()


def sync_cursor_skills(
    target: Path,
    source: Path,
    dry_run: bool,
    *,
    source_is_default: bool = False,
) -> tuple[bool, list[str], str | None]:
    target = target.expanduser()
    source = source.expanduser()

    if _trees_overlap(source, target):
        if source_is_default:
            return False, [], "source resolves inside target; running from the synced Cursor copy"
        raise SystemExit(f"source and target must be separate trees: {source.resolve()} {target.resolve()}")

    if not target.exists():
        return False, [], "cursor target directory does not exist"
    if target.is_symlink() or not target.is_dir():
        return False, [f"skip_irregular:{target}"], "cursor target is not a regular directory"
    desired = collect_desired(source)

    manifest_path = target / MANIFEST_NAME
    manifest_present = manifest_path.exists() or manifest_path.is_symlink()
    previous = _read_manifest(manifest_path)
    if manifest_present and previous is None:
        raise SystemExit(
            f"invalid Cursor sync manifest: {manifest_path}; "
            "delete the manifest to retry the safe adoption flow"
        )

    actions: list[str] = []
    writes: dict[str, bytes] = {}
    prunes: list[str] = []
    replacement_dirs: set[Path] = set()
    next_manifest: dict[str, str] = {}

    prune_decisions: dict[str, str] = {}
    if previous is not None:
        for relpath in sorted(set(previous) - set(desired)):
            destination = target / relpath
            kind = _path_kind(target, destination)
            if kind == "missing":
                prune_decisions[relpath] = "missing"
            elif kind == "irregular":
                prune_decisions[relpath] = "skip_irregular"
            elif _sha256(destination.read_bytes()) != previous[relpath]:
                prune_decisions[relpath] = "skip_prune_modified"
            else:
                prune_decisions[relpath] = "prune"
                prunes.append(relpath)
    planned_prunes = set(prunes)

    for relpath, content in sorted(desired.items()):
        destination = target / relpath
        kind, replace_directory = _path_kind_after_prunes(target, destination, planned_prunes)
        desired_hash = _sha256(content)
        if kind == "irregular":
            actions.append(f"skip_irregular:{relpath}")
            if previous is not None and relpath in previous:
                next_manifest[relpath] = previous[relpath]
            continue

        existing = destination.read_bytes() if kind == "regular" else None
        is_managed = previous is not None and relpath in previous
        if not is_managed and existing is not None and existing != content:
            actions.append(f"skip_conflict:{relpath}")
            continue
        if (
            is_managed
            and existing is not None
            and existing != content
            and _sha256(existing) != previous[relpath]
        ):
            actions.append(f"skip_modified:{relpath}")
            next_manifest[relpath] = previous[relpath]
            continue
        if existing != content:
            actions.append(f"copy:{relpath}")
            writes[relpath] = content
            if replace_directory:
                replacement_dirs.add(destination)
        next_manifest[relpath] = desired_hash

    if previous is not None:
        for relpath in sorted(set(previous) - set(desired)):
            decision = prune_decisions[relpath]
            if decision == "missing":
                continue
            if decision == "skip_irregular":
                actions.append(f"skip_irregular:{relpath}")
                next_manifest[relpath] = previous[relpath]
                continue
            if decision == "skip_prune_modified":
                actions.append(f"skip_prune_modified:{relpath}")
                next_manifest[relpath] = previous[relpath]
                continue
            actions.append(f"prune:{relpath}")

    desired_manifest = _manifest_bytes(next_manifest)
    existing_manifest = manifest_path.read_bytes() if previous is not None else None
    manifest_change = existing_manifest != desired_manifest
    if manifest_change:
        actions.append(f"write_manifest:{MANIFEST_NAME}")

    changed = bool(writes or prunes or manifest_change)
    if dry_run or not changed:
        return changed, actions, None

    for relpath in prunes:
        destination = target / relpath
        destination.unlink()
        _remove_empty_managed_dirs(target, destination.parent)

    for directory in sorted(replacement_dirs, key=lambda item: len(item.parts), reverse=True):
        _remove_empty_tree(directory)

    for relpath, content in writes.items():
        destination = target / relpath
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)

    if manifest_change:
        manifest_path.write_bytes(desired_manifest)

    return True, actions, None


def main() -> int:
    parser = argparse.ArgumentParser(description="Synchronize DevKit skills for Cursor.")
    parser.add_argument("--check", action="store_true", help="Report planned changes without writing files")
    parser.add_argument("--format", choices=["json"], default="json", help="Output format")
    parser.add_argument("--target", type=Path, default=Path.home() / ".cursor")
    parser.add_argument("--source", type=Path)
    args = parser.parse_args()

    source_is_default = args.source is None
    source = default_source_dir() if source_is_default else args.source
    changed, actions, reason = sync_cursor_skills(
        args.target,
        source,
        args.check,
        source_is_default=source_is_default,
    )
    dump_result(changed, actions, reason=reason)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
