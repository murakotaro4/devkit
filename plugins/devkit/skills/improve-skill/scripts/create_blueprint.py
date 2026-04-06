#!/usr/bin/env python3
"""Create a skill blueprint checklist from session signals."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

VERB_PREFIXES = (
    "improve",
    "refresh",
    "create",
    "build",
    "update",
    "generate",
    "draft",
    "review",
)


def load_session_payload(session_json: str | None) -> dict[str, Any]:
    try:
        if session_json:
            payload = json.loads(Path(session_json).read_text(encoding="utf-8"))
            return normalize_session_payload(payload)

        if sys.stdin.isatty():
            raise SystemExit("error: provide --session-json or pipe JSON via stdin")
        payload = json.loads(sys.stdin.read())
        return normalize_session_payload(payload)
    except FileNotFoundError as exc:
        raise SystemExit(f"error: session JSON file not found: {exc.filename}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"error: invalid session JSON: {exc.msg}") from exc


def normalize_text_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def normalize_session_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise SystemExit("error: session payload must be a JSON object")

    normalized = dict(payload)
    normalized["requirements"] = normalize_text_list(payload.get("requirements", []))
    normalized["constraints"] = normalize_text_list(payload.get("constraints", []))
    normalized["mode_hint"] = (
        str(payload.get("mode_hint", "undecided")).strip() or "undecided"
    )
    return normalized


def slugify(text: str) -> str:
    normalized = text.strip().lower()
    normalized = re.sub(r"[^a-z0-9]+", "-", normalized)
    normalized = re.sub(r"-{2,}", "-", normalized).strip("-")
    return normalized


def infer_name(session: dict[str, Any], explicit_name: str | None) -> str:
    if explicit_name:
        candidate = slugify(explicit_name)
    else:
        combined = " ".join(
            session.get("requirements", []) + session.get("constraints", [])
        )
        words = re.findall(r"[a-zA-Z][a-zA-Z0-9-]{2,}", combined)
        if words:
            candidate = slugify("-".join(words[:3]))
        else:
            mode_hint = session.get("mode_hint", "undecided")
            if mode_hint == "refresh":
                candidate = "refresh-skill"
            elif mode_hint == "create":
                candidate = "create-skill"
            else:
                candidate = "improve-skill"

    if not candidate:
        candidate = "improve-skill"

    first = candidate.split("-", 1)[0]
    if first not in VERB_PREFIXES:
        candidate = f"create-{candidate}"

    return candidate[:64].rstrip("-")


def build_description(session: dict[str, Any], skill_name: str) -> str:
    reqs = session.get("requirements", [])
    top_req = reqs[0] if reqs else "現在セッションの要件"
    return (
        f"現在セッションの要件を基に {skill_name} を作成する。"
        f"AskUserQuestionToolで深掘りし、{top_req} を満たす構成を提案する。"
    )


def build_result(
    session: dict[str, Any],
    skill_name: str,
    base_path: str,
) -> dict[str, Any]:
    skill_path = str(Path(base_path) / skill_name)

    mandatory = [
        {
            "target": f"{skill_path}/SKILL.md",
            "reason": "スキル本体がないと配布・呼び出しができない",
            "expected": "name/description と refresh/create の判断手順を定義する",
        },
        {
            "target": f"{skill_path}/SKILL.md",
            "reason": "質問駆動ルールがないと意図確定に失敗する",
            "expected": "AskUserQuestionTool の必須手順を明記する",
        },
        {
            "target": f"{skill_path}/SKILL.md",
            "reason": "出力契約が曖昧だと提案品質がぶれる",
            "expected": "固定見出しのチェックリスト出力形式を定義する",
        },
    ]

    recommended = [
        {
            "target": f"{skill_path}/references/question-flow.md",
            "reason": "分岐ロジックを本文から分離すると保守しやすい",
            "expected": "refresh/create それぞれの質問テンプレを記述する",
        },
        {
            "target": f"{skill_path}/scripts/session_extract.py",
            "reason": "セッション要件抽出を自動化すると再現性が上がる",
            "expected": "stdin またはファイル入力から要件をJSON化できる",
        },
    ]

    confirm = []
    for req in session.get("requirements", [])[:5]:
        confirm.append(
            {
                "target": skill_path,
                "reason": f"要件: {req}",
                "expected": "上記要件を frontmatter description か本文フローに反映する",
            }
        )
    if not confirm:
        confirm.append(
            {
                "target": skill_path,
                "reason": "明示要件が不足している",
                "expected": "モード・対象・完了条件を再質問して補完する",
            }
        )

    completion = [
        "SKILL.md に trigger と workflow が両方記述されている",
        "チェックリスト出力の固定見出しが含まれている",
        "現在セッションのみを根拠にする制約が明記されている",
    ]

    return {
        "mode": "create",
        "skill_name": skill_name,
        "skill_path": skill_path,
        "description_draft": build_description(session, skill_name),
        "mandatory": mandatory,
        "recommended": recommended,
        "confirm": confirm,
        "completion": completion,
    }


def render_markdown(result: dict[str, Any]) -> str:
    def render_items(items: list[dict[str, str]]) -> str:
        if not items:
            return "- なし"
        lines = []
        for item in items:
            lines.append(
                f"- [ ] 対象: `{item['target']}` | 理由: {item['reason']} | 期待状態: {item['expected']}"
            )
        return "\n".join(lines)

    completion_lines = "\n".join(f"- [ ] {entry}" for entry in result["completion"])
    return "\n".join(
        [
            f"mode: {result['mode']}",
            f"skill_name: {result['skill_name']}",
            f"skill_path: {result['skill_path']}",
            "",
            "description_draft:",
            result["description_draft"],
            "",
            "## 必須修正",
            render_items(result["mandatory"]),
            "",
            "## 推奨修正",
            render_items(result["recommended"]),
            "",
            "## 確認事項",
            render_items(result["confirm"]),
            "",
            "## 完了条件",
            completion_lines,
        ]
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create skill blueprint checklist from session JSON"
    )
    parser.add_argument(
        "--session-json", help="Path to session JSON produced by session_extract.py"
    )
    parser.add_argument("--name", help="Optional explicit skill name")
    parser.add_argument(
        "--base-path",
        default="plugins/devkit/skills",
        help="Base path where the new skill would be created",
    )
    parser.add_argument(
        "--format",
        choices=("markdown", "json"),
        default="markdown",
        help="Output format",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    session = load_session_payload(args.session_json)
    skill_name = infer_name(session, args.name)
    result = build_result(session, skill_name, args.base_path)

    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    print(render_markdown(result))


if __name__ == "__main__":
    main()
