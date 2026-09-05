#!/usr/bin/env python3
"""配布ドキュメントのサイズを baseline 比で計測するレポート。

gate ではない。サイズの増減では常に終了コード 0 を返す。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[3]

# 基点は cc2cd36（2026-07-25 の圧縮 + 独立レビュー 10 巡の収束点）。
# 圧縮 commit 0b3e7cf ではない。そこは独立レビュー 17 件の安全契約を戻す前の
# 中間状態で、dig 9,964 / repo-loop 7,768 / setup 5,516 と食い違う。
# 再確認: git show cc2cd36:<path>
BASELINE_COMMIT = "cc2cd36"

SIZE_BASELINE: dict[str, int] = {
    "AGENTS.md": 7935,
    "plugins/devkit/skills/backlog/SKILL.md": 2610,
    "plugins/devkit/skills/catch-up/SKILL.md": 2963,
    "plugins/devkit/skills/commit-push/SKILL.md": 3092,
    "plugins/devkit/skills/dig/SKILL.md": 11231,
    "plugins/devkit/skills/dig/references/execution.md": 0,
    "plugins/devkit/skills/dig/references/integration.md": 0,
    "plugins/devkit/skills/dig/references/planning.md": 0,
    "plugins/devkit/skills/goal-prompt/SKILL.md": 1898,
    "plugins/devkit/skills/handoff/SKILL.md": 2226,
    "plugins/devkit/skills/improve-skill/SKILL.md": 3878,
    "plugins/devkit/skills/improve-skill/references/checklist.md": 859,
    "plugins/devkit/skills/improve-skill/references/question-flow.md": 636,
    "plugins/devkit/skills/memory-review/SKILL.md": 4246,
    "plugins/devkit/skills/refactor/SKILL.md": 2451,
    "plugins/devkit/skills/repo-loop/SKILL.md": 8261,
    "plugins/devkit/skills/repo-loop/references/delivery.md": 0,
    "plugins/devkit/skills/repo-loop/references/selection.md": 0,
    "plugins/devkit/skills/setup/SKILL.md": 5926,
    "plugins/devkit/skills/setup/references/environment.md": 0,
    "plugins/devkit/skills/setup/references/sync-matrix.md": 0,
}

YAML_TOTAL_BASELINE = 2886


def _chars(relpath: str) -> int:
    return len((REPO_ROOT / relpath).read_text(encoding="utf-8"))


def _skill_yaml_paths() -> list[Path]:
    skills_dir = REPO_ROOT / "plugins" / "devkit" / "skills"
    return sorted(skills_dir.glob("**/*.yaml"))


def _delta_percent(baseline: int, current: int) -> float:
    if baseline == 0:
        return 0.0 if current == 0 else 100.0
    return round((current - baseline) / baseline * 100, 2)


def _entry(path: str, baseline: int, current: int) -> dict[str, Any]:
    return {
        "path": path,
        "baseline": baseline,
        "current": current,
        "delta": current - baseline,
        "delta_percent": _delta_percent(baseline, current),
    }


def collect_report() -> dict[str, Any]:
    markdown: list[dict[str, Any]] = []
    for path, baseline in SIZE_BASELINE.items():
        target = REPO_ROOT / path
        if not target.is_file():
            raise FileNotFoundError(f"baseline file missing: {path}")
        markdown.append(_entry(path, baseline, _chars(path)))

    markdown.sort(key=lambda item: item["delta_percent"], reverse=True)

    md_baseline = sum(SIZE_BASELINE.values())
    md_current = sum(item["current"] for item in markdown)
    yaml_current = sum(len(path.read_text(encoding="utf-8")) for path in _skill_yaml_paths())

    return {
        "baseline_commit": BASELINE_COMMIT,
        "markdown": markdown,
        "markdown_total": _entry("markdown 合計", md_baseline, md_current),
        "yaml_total": _entry("yaml 合計", YAML_TOTAL_BASELINE, yaml_current),
    }


def _format_text_line(item: dict[str, Any], label: str) -> str:
    pct = item["delta_percent"]
    return f"  {pct:+.1f}%  {item['current']:6,} ({item['baseline']:6,})  {label}"


def render_text(report: dict[str, Any]) -> str:
    lines = [f"doc size vs {BASELINE_COMMIT} (2026-07-25 圧縮+レビュー収束)"]
    for item in report["markdown"]:
        lines.append(_format_text_line(item, item["path"]))
    lines.append(_format_text_line(report["markdown_total"], "markdown 合計"))
    lines.append(_format_text_line(report["yaml_total"], "yaml 合計"))
    return "\n".join(lines)


def render_json(report: dict[str, Any]) -> str:
    payload = {
        "baseline_commit": report["baseline_commit"],
        "markdown": [
            {
                "path": item["path"],
                "baseline": item["baseline"],
                "current": item["current"],
                "delta": item["delta"],
                "delta_percent": item["delta_percent"],
            }
            for item in report["markdown"]
        ],
        "markdown_total": {
            "baseline": report["markdown_total"]["baseline"],
            "current": report["markdown_total"]["current"],
            "delta": report["markdown_total"]["delta"],
            "delta_percent": report["markdown_total"]["delta_percent"],
        },
        "yaml_total": {
            "baseline": report["yaml_total"]["baseline"],
            "current": report["yaml_total"]["current"],
            "delta": report["yaml_total"]["delta"],
            "delta_percent": report["yaml_total"]["delta_percent"],
        },
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Report distributed document sizes vs baseline (not a gate)."
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Output format (default: text)",
    )
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        code = exc.code
        return 0 if code in (None, 0) else int(code)

    try:
        report = collect_report()
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        print(f"doc size report failed: {exc}", file=sys.stderr)
        return 2

    if args.format == "json":
        print(render_json(report))
    else:
        print(render_text(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
