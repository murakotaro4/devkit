#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[2]
SECRETS_BASELINE = SCRIPT_DIR.parent / ".secrets.baseline"
WORKTREE_SNAPSHOT_PREFIX = ".devkit-worktree"


def script(path: str) -> str:
    return str(SCRIPT_DIR / path)


def git_files(*args: str) -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z", *args],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
    )
    return [
        raw.decode("utf-8")
        for raw in result.stdout.split(b"\0")
        if raw
    ]


def git_paths_from_diff(*args: str) -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--name-only", "-z", *args],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
    )
    return [
        raw.decode("utf-8")
        for raw in result.stdout.split(b"\0")
        if raw
    ]


def materialize_secret_scan_snapshot(snapshot: Path) -> list[str]:
    cached = git_files("--cached")
    worktree_modified = git_paths_from_diff()
    untracked = git_files("--others", "--exclude-standard")
    scan_files: set[str] = set()

    for rel in cached:
        destination = snapshot / rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            ["git", "show", f":{rel}"],
            cwd=REPO_ROOT,
            check=False,
            capture_output=True,
        )
        if result.returncode != 0:
            continue
        destination.write_bytes(result.stdout)
        if destination.is_file():
            scan_files.add(rel)

    for rel in worktree_modified:
        source = REPO_ROOT / rel
        if not source.is_file():
            continue
        destination = snapshot / WORKTREE_SNAPSHOT_PREFIX / rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        scan_files.add(f"{WORKTREE_SNAPSHOT_PREFIX}/{rel}")

    for rel in untracked:
        source = REPO_ROOT / rel
        if not source.is_file():
            continue
        destination = snapshot / rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        scan_files.add(rel)

    return sorted(scan_files)


def repo_path_from_secret_snapshot_path(path: str) -> str:
    prefix = f"{WORKTREE_SNAPSHOT_PREFIX}/"
    if path.startswith(prefix):
        return path[len(prefix):]
    return path


def secret_entry_key(path: str, entry: dict[str, object]) -> tuple[object, ...]:
    return (
        repo_path_from_secret_snapshot_path(path),
        entry.get("line_number"),
        entry.get("type"),
        entry.get("hashed_secret"),
    )


def collect_secret_keys(payload: dict[str, object]) -> set[tuple[object, ...]]:
    results = payload.get("results", {})
    if not isinstance(results, dict):
        return set()

    keys: set[tuple[object, ...]] = set()
    for path, entries in results.items():
        if not isinstance(path, str) or not isinstance(entries, list):
            continue
        for entry in entries:
            if isinstance(entry, dict):
                keys.add(secret_entry_key(path, entry))
    return keys


def run_detect_secrets_check() -> int:
    if not SECRETS_BASELINE.exists():
        print(f"missing detect-secrets baseline: {SECRETS_BASELINE}", file=sys.stderr)
        return 2

    with TemporaryDirectory(prefix="devkit-secrets-") as temp_dir_name:
        temp_dir = Path(temp_dir_name)
        snapshot = temp_dir / "snapshot"
        snapshot.mkdir()
        files = materialize_secret_scan_snapshot(snapshot)
        temp_baseline = temp_dir / ".secrets.baseline"
        shutil.copyfile(SECRETS_BASELINE, temp_baseline)
        cmd = [
            sys.executable,
            "-m",
            "detect_secrets",
            "scan",
            "--baseline",
            str(temp_baseline),
            *files,
        ]
        result = subprocess.run(cmd, cwd=snapshot)
        if result.returncode != 0:
            return result.returncode

        baseline = json.loads(SECRETS_BASELINE.read_text(encoding="utf-8"))
        current = json.loads(temp_baseline.read_text(encoding="utf-8"))
        baseline_keys = collect_secret_keys(baseline)
        current_keys = collect_secret_keys(current)
        new_keys = sorted(current_keys - baseline_keys)
        if new_keys:
            print(
                json.dumps(
                    {
                        "ok": False,
                        "reason": "detect-secrets found findings not present in plugins/devkit/.secrets.baseline",
                        "newFindings": new_keys,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                file=sys.stderr,
            )
            return 2
    return 0


CHECKS_FAST: list[list[str]] = [
    [sys.executable, script("check_utf8_bom.py")],
    [sys.executable, script("check_skill_surface.py"), "--phase=B"],
    [sys.executable, script("check_legacy_migration.py"), "--mode=repo"],
    [sys.executable, script("devkit_harness.py"), "verify-secrets"],
    [sys.executable, "-m", "pytest", str(SCRIPT_DIR.parent / "tests"), "-x", "-q"],
]

CHECKS_FULL: list[list[str]] = CHECKS_FAST + [
    [sys.executable, script("check_plugin_version_bump.py")],
]


def run_steps(steps: list[list[str]]) -> int:
    for cmd in steps:
        result = subprocess.run(cmd, cwd=REPO_ROOT)
        if result.returncode != 0:
            return result.returncode
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run DevKit verification harness.")
    parser.add_argument("command", choices=["verify-fast", "verify-full", "verify-secrets"])
    args = parser.parse_args()

    if args.command == "verify-secrets":
        return run_detect_secrets_check()
    if args.command == "verify-fast":
        return run_steps(CHECKS_FAST)
    return run_steps(CHECKS_FULL)


if __name__ == "__main__":
    raise SystemExit(main())
