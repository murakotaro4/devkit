#!/usr/bin/env python3
"""Extract structured requirements from a session transcript."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Iterable

REFRESH_KEYWORDS = (
    "refresh",
    "improve",
    "改善",
    "既存",
    "反映",
    "optimize",
)
CREATE_KEYWORDS = (
    "create",
    "new skill",
    "新規",
    "作成",
    "build",
    "生成",
)
ASK_QUESTION_KEYWORDS = (
    "askuserquestion",
    "ask user",
    "質問",
    "深掘り",
    "確認",
)
REQUIREMENT_KEYWORDS = (
    "must",
    "need",
    "should",
    "want",
    "required",
    "必要",
    "したい",
    "してほしい",
    "欲しい",
    "べき",
)
CONSTRAINT_KEYWORDS = (
    "only",
    "do not",
    "must not",
    "stop",
    "fallback",
    "提案のみ",
    "停止",
    "再質問",
    "しない",
    "禁止",
)


def read_text(input_file: str | None) -> tuple[str, str]:
    if input_file:
        path = Path(input_file)
        return path.read_text(encoding="utf-8"), str(path)

    if sys.stdin.isatty():
        raise SystemExit("error: provide --input-file or pipe session text via stdin")

    return sys.stdin.read(), "stdin"


def normalize_lines(text: str) -> list[str]:
    raw_lines = re.split(r"[\r\n]+", text)
    lines: list[str] = []
    for raw in raw_lines:
        normalized = re.sub(r"\s+", " ", raw).strip(" \t-")
        if normalized:
            lines.append(normalized)
    return lines


def contains_any(line: str, keywords: Iterable[str]) -> bool:
    lower = line.lower()
    return any(keyword in lower for keyword in keywords)


def unique_keep_order(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            ordered.append(value)
    return ordered


def collect_matching(
    lines: list[str], keywords: Iterable[str], limit: int
) -> list[str]:
    selected = [line for line in lines if contains_any(line, keywords)]
    return unique_keep_order(selected)[:limit]


def score_matches(lines: list[str], keywords: Iterable[str]) -> int:
    return sum(1 for line in lines if contains_any(line, keywords))


def infer_mode_hint(refresh_score: int, create_score: int) -> str:
    if refresh_score > create_score:
        return "refresh"
    if create_score > refresh_score:
        return "create"
    return "undecided"


def build_summary(lines: list[str], source: str, limit: int) -> dict[str, object]:
    refresh_score = score_matches(lines, REFRESH_KEYWORDS)
    create_score = score_matches(lines, CREATE_KEYWORDS)

    requirements = collect_matching(lines, REQUIREMENT_KEYWORDS, limit)
    if not requirements:
        requirements = lines[:limit]

    constraints = collect_matching(lines, CONSTRAINT_KEYWORDS, limit)
    key_phrases = unique_keep_order((requirements + constraints))[:limit]

    return {
        "source": source,
        "mode_hint": infer_mode_hint(refresh_score, create_score),
        "mode_scores": {
            "refresh": refresh_score,
            "create": create_score,
        },
        "needs_askuserquestion": score_matches(lines, ASK_QUESTION_KEYWORDS) > 0,
        "requirements": requirements,
        "constraints": constraints,
        "key_phrases": key_phrases,
    }


def render_markdown(data: dict[str, object]) -> str:
    mode_scores = data["mode_scores"]
    requirements = data["requirements"]
    constraints = data["constraints"]
    key_phrases = data["key_phrases"]

    def format_list(values: list[str]) -> str:
        if not values:
            return "- なし"
        return "\n".join(f"- {value}" for value in values)

    return "\n".join(
        [
            f"source: {data['source']}",
            f"mode_hint: {data['mode_hint']}",
            f"mode_scores: refresh={mode_scores['refresh']} create={mode_scores['create']}",
            f"needs_askuserquestion: {str(data['needs_askuserquestion']).lower()}",
            "",
            "## requirements",
            format_list(requirements),
            "",
            "## constraints",
            format_list(constraints),
            "",
            "## key_phrases",
            format_list(key_phrases),
        ]
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract structured items from session text"
    )
    parser.add_argument("--input-file", help="Optional path to session text file")
    parser.add_argument(
        "--format",
        choices=("json", "markdown"),
        default="json",
        help="Output format",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=12,
        help="Maximum number of items per list",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    text, source = read_text(args.input_file)
    lines = normalize_lines(text)
    if not lines:
        raise SystemExit("error: session text is empty")

    summary = build_summary(lines, source, max(args.limit, 1))
    if args.format == "json":
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return
    print(render_markdown(summary))


if __name__ == "__main__":
    main()
