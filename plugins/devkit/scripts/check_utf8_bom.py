#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
TARGET_PATTERNS = ("*.json", "*.md", "*.yaml", "*.yml")
UTF8_BOM = b"\xef\xbb\xbf"


def git_paths(*args: str) -> list[str]:
    result = subprocess.run(list(args), cwd=REPO_ROOT, check=True, capture_output=True)
    return [path.decode("utf-8") for path in result.stdout.split(b"\0") if path]


def repo_files() -> list[str]:
    return git_paths("git", "ls-files", "-z", "--", *TARGET_PATTERNS)


def index_has_utf8_bom(path: str) -> bool:
    result = subprocess.run(
        ["git", "show", f":{path}"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
    )
    return result.stdout.startswith(UTF8_BOM)


def repo_has_utf8_bom(path: str) -> bool:
    worktree_path = REPO_ROOT / path
    return index_has_utf8_bom(path) or (
        worktree_path.is_file() and worktree_path.read_bytes().startswith(UTF8_BOM)
    )


def main() -> int:
    found = False
    for path in repo_files():
        if repo_has_utf8_bom(path):
            print(f"ERROR: {path} contains UTF-8 BOM (in repo file)", file=sys.stderr)
            found = True

    if not found:
        return 0

    print("", file=sys.stderr)
    print(r"Fix: sed -i '1s/^\xEF\xBB\xBF//' <file>", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
