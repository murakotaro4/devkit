#!/usr/bin/env python3
"""Generate a refresh checklist by mapping session signals to an existing skill."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml


def read_session_payload(session_json: str | None) -> dict[str, Any]:
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
    return normalized


def load_skill(skill_dir: str) -> dict[str, Any]:
    root = Path(skill_dir).resolve()
    skill_md = root / "SKILL.md"
    if not skill_md.exists():
        raise SystemExit(f"error: SKILL.md not found in {root}")

    skill_text = skill_md.read_text(encoding="utf-8")
    frontmatter_match = re.match(r"^---\n(.*?)\n---", skill_text, re.DOTALL)
    frontmatter = frontmatter_match.group(1) if frontmatter_match else ""

    description = ""
    if frontmatter:
        try:
            parsed = yaml.safe_load(frontmatter)
            if isinstance(parsed, dict):
                desc = parsed.get("description")
                if isinstance(desc, str):
                    description = desc.strip()
        except yaml.YAMLError:
            # Frontmatter parse failure should not break checklist generation.
            description = ""

    return {
        "root": root,
        "skill_md": skill_md,
        "text": skill_text,
        "description": description,
        "has_scripts": (root / "scripts").exists(),
        "has_references": (root / "references").exists(),
    }


def includes_any(text: str, keywords: list[str]) -> bool:
    lower = text.lower()
    return any(keyword in lower for keyword in keywords)


def add_item(bucket: list[dict[str, str]], target: str, reason: str, expected: str) -> None:
    bucket.append(
        {
            "target": target,
            "reason": reason,
            "expected": expected,
        }
    )


def build_checklist(skill: dict[str, Any], session: dict[str, Any], priorities: list[str]) -> dict[str, Any]:
    mandatory: list[dict[str, str]] = []
    recommended: list[dict[str, str]] = []
    confirm: list[dict[str, str]] = []

    skill_text = skill["text"]
    skill_md_rel = str(skill["skill_md"])
    description = skill["description"]

    if not description or "[TODO" in description:
        add_item(
            mandatory,
            skill_md_rel,
            "description が未完成だとトリガー精度が落ちる",
            "利用条件が分かる description に更新する",
        )

    if not includes_any(skill_text, ["askuserquestion", "request_user_input"]):
        add_item(
            mandatory,
            skill_md_rel,
            "質問フローがないと mode と対象を確定できない",
            "AskUserQuestionTool を使う手順を追加する",
        )

    if not includes_any(skill_text, ["必須修正", "推奨修正", "完了条件", "チェックリスト"]):
        add_item(
            mandatory,
            skill_md_rel,
            "出力契約が曖昧だと結果品質がぶれる",
            "固定見出しのチェックリスト出力を明示する",
        )

    if "現在セッション" not in skill_text:
        add_item(
            mandatory,
            skill_md_rel,
            "セッション参照範囲の指定が不足している",
            "現在セッションのみ参照するルールを明記する",
        )

    if not includes_any(skill_text.lower(), ["refresh", "create"]):
        add_item(
            mandatory,
            skill_md_rel,
            "モード分岐が欠けると処理方針を決められない",
            "refresh/create の二択フローを追加する",
        )

    if len(skill_text.splitlines()) > 500:
        add_item(
            recommended,
            skill_md_rel,
            "SKILL.md が長いと読み込みコストが高い",
            "詳細を references/ に分割して本文を短くする",
        )

    if not skill["has_references"]:
        add_item(
            recommended,
            str(skill["root"]),
            "チェック観点の再利用性が低い",
            "references/checklist.md などの参照資料を追加する",
        )

    if not skill["has_scripts"]:
        add_item(
            recommended,
            str(skill["root"]),
            "手動要約だけでは再現性が低い",
            "セッション抽出やマッピングの補助スクリプトを追加する",
        )

    session_lines = "\n".join(session.get("requirements", []) + session.get("constraints", []))
    if includes_any(session_lines, ["質問", "askuserquestion"]) and not includes_any(
        skill_text, ["askuserquestion", "request_user_input"]
    ):
        add_item(
            mandatory,
            skill_md_rel,
            "セッション要件に質問駆動が含まれている",
            "深掘り質問フローを実装する",
        )

    if includes_any(session_lines, ["セッション", "反映"]) and "現在セッション" not in skill_text:
        add_item(
            mandatory,
            skill_md_rel,
            "セッション反映要件に対する説明が不足している",
            "セッション要件を改善項目へ写像する工程を明記する",
        )

    for priority in priorities:
        add_item(
            confirm,
            skill_md_rel,
            f"優先観点 '{priority}' の重みを確認する必要がある",
            "採用順（必須修正の優先順位）を明示する",
        )

    completion: list[str] = [
        "必須修正がすべて解消されている",
        "出力が固定見出しのチェックリストになっている",
        "現在セッションのみを根拠にしている",
    ]
    if mandatory:
        completion.append("refresh/create の分岐と質問フローが文章で確認できる")

    return {
        "mode": "refresh",
        "target_skill": str(skill["root"]),
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
            f"target_skill: {result['target_skill']}",
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
    parser = argparse.ArgumentParser(description="Map session requirements to refresh checklist")
    parser.add_argument("--skill", required=True, help="Target skill directory")
    parser.add_argument("--session-json", help="Path to session JSON produced by session_extract.py")
    parser.add_argument(
        "--priorities",
        default="trigger,compact,reuse,safety,validation",
        help="Comma-separated priority labels",
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
    session = read_session_payload(args.session_json)
    skill = load_skill(args.skill)
    priorities = [item.strip() for item in args.priorities.split(",") if item.strip()]
    result = build_checklist(skill, session, priorities)

    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    print(render_markdown(result))


if __name__ == "__main__":
    main()
