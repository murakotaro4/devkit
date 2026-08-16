#!/usr/bin/env python3
"""bash 4+ 専用構文の混入を検査する。

macOS の stock /bin/bash は 3.2 であり、update-ccx.sh などの配布 shell と、
テストが `_bash_path()`(PATH の bash)で実行する埋め込み shell fixture は
bash 3.2 で動く必要がある。過去に test fixture の `mapfile` が macOS ローカルで
のみ失敗した(CI の bash 5 では通る)ため、bash 4+ 専用 token を静的に検出する。

対象: git 追跡下の *.sh 全部と plugins/devkit/tests/*.py(埋め込み fixture)。
行内に `bash32-allow` と書けばその行は検査対象外(意図的な使用の waiver)。
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
TARGET_PATTERNS = ("*.sh", "plugins/devkit/tests/*.py")
# この check 自身とそのテストは token を文字列として含むため除外する。
SELF_NAMES = ("check_bash32_compat.py", "test_check_bash32_compat.py")
WAIVER_TOKEN = "bash32-allow"

# (token 名, 正規表現) の一覧。bash 3.2 に存在しない構文だけを登録する。
BASH4_TOKENS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("mapfile", re.compile(r"(?<![\w-])mapfile(?![\w-])")),
    ("readarray", re.compile(r"(?<![\w-])readarray(?![\w-])")),
    (
        "declare/local/typeset -A or -n",
        # -A / -n が結合(-Ar)・後続クラスタ(-r -n)のどこにあっても拾う。
        re.compile(r"\b(?:declare|local|typeset)\s+(?:-[A-Za-z]+\s+)*-[A-Za-z]*[An][A-Za-z]*\b"),
    ),
    ("case fallthrough ;;&", re.compile(r";;&")),
    (
        "case modification ${var^^} / ${var,,}",
        re.compile(r"\$\{[A-Za-z_][A-Za-z0-9_]*(?:\[[^]]*\])?(?:\^{1,2}|,{1,2})[^}]*\}"),
    ),
    (
        "parameter transformation ${var@Q}",
        re.compile(r"\$\{[A-Za-z_][A-Za-z0-9_]*(?:\[[^]]*\])?@[A-Za-z]\}"),
    ),
)


def git_paths(*args: str) -> list[str]:
    result = subprocess.run(list(args), cwd=REPO_ROOT, check=True, capture_output=True)
    return [path.decode("utf-8") for path in result.stdout.split(b"\0") if path]


def target_files() -> list[str]:
    paths = git_paths("git", "ls-files", "-z", "--", *TARGET_PATTERNS)
    return [path for path in paths if Path(path).name not in SELF_NAMES]


def scan_lines(lines: list[str]) -> list[tuple[int, str]]:
    findings: list[tuple[int, str]] = []
    for line_no, line in enumerate(lines, start=1):
        if WAIVER_TOKEN in line:
            continue
        # コメント行(#)は実行されないため対象外。Python 文字列内の
        # 埋め込み shell はクォートで始まるので落とさない。
        if line.lstrip().startswith("#"):
            continue
        for token_name, pattern in BASH4_TOKENS:
            if pattern.search(line):
                findings.append((line_no, token_name))
    return findings


def main() -> int:
    found = False
    for path in target_files():
        file_path = REPO_ROOT / path
        if not file_path.is_file():
            continue
        lines = file_path.read_text(encoding="utf-8").splitlines()
        for line_no, token_name in scan_lines(lines):
            print(
                f"ERROR: {path}:{line_no}: {token_name} requires bash 4+ "
                "(macOS stock /bin/bash is 3.2)",
                file=sys.stderr,
            )
            found = True

    if not found:
        return 0

    print("", file=sys.stderr)
    print(
        f"Fix: rewrite with bash 3.2 compatible constructs, or append '{WAIVER_TOKEN}' "
        "to the line if the usage is intentionally bash 4+ only",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
