#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[2]


def script(path: str) -> str:
    return str(SCRIPT_DIR / path)


CHECKS_FAST: list[list[str]] = [
    [sys.executable, script("check_utf8_bom.py"), "--mode=repo"],
    [sys.executable, script("check_skill_surface.py"), "--phase=B"],
    [sys.executable, script("check_legacy_migration.py"), "--mode=repo"],
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
    parser.add_argument("command", choices=["verify-fast", "verify-full"])
    args = parser.parse_args()

    if args.command == "verify-fast":
        return run_steps(CHECKS_FAST)
    return run_steps(CHECKS_FULL)


if __name__ == "__main__":
    raise SystemExit(main())
