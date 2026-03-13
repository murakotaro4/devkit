#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
import argparse


REPO_ROOT = Path(__file__).resolve().parents[3]
TARGET_PATTERNS = ("*.json", "*.md", "*.yaml", "*.yml")
UTF8_BOM = b"\xef\xbb\xbf"


def git_paths(*args: str) -> list[str]:
    result = subprocess.run(list(args), cwd=REPO_ROOT, check=True, capture_output=True)
    return [path.decode("utf-8") for path in result.stdout.split(b"\0") if path]


def staged_files() -> list[str]:
    return git_paths(
        "git",
        "diff",
        "--cached",
        "--name-only",
        "-z",
        "--diff-filter=ACM",
        "--",
        *TARGET_PATTERNS,
    )


def repo_files() -> list[str]:
    return git_paths("git", "ls-files", "-z", "--", *TARGET_PATTERNS)


def staged_has_utf8_bom(path: str) -> bool:
    result = subprocess.run(
        ["git", "show", f":{path}"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
    )
    return result.stdout.startswith(UTF8_BOM)


def repo_has_utf8_bom(path: str) -> bool:
    return (REPO_ROOT / path).read_bytes().startswith(UTF8_BOM)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Reject UTF-8 BOM in staged or tracked files.")
    parser.add_argument("--mode", choices=("staged", "repo"), default="staged")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    files = staged_files() if args.mode == "staged" else repo_files()
    has_utf8_bom = staged_has_utf8_bom if args.mode == "staged" else repo_has_utf8_bom

    found = False
    for path in files:
        if has_utf8_bom(path):
            location = "staged content" if args.mode == "staged" else "repo file"
            print(f"ERROR: {path} contains UTF-8 BOM (in {location})", file=sys.stderr)
            found = True

    if not found:
        return 0

    print("", file=sys.stderr)
    fix_command = r"Fix: sed -i '1s/^\xEF\xBB\xBF//' <file>"
    if args.mode == "staged":
        fix_command += r" && git add <file>"
    print(fix_command, file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
