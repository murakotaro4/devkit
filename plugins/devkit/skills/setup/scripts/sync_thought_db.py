#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


START_MARKER = "<!-- devkit:thought-db:start -->"
END_MARKER = "<!-- devkit:thought-db:end -->"


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def desired_block(template_text: str) -> str:
    body = template_text.strip("\n")
    return f"{START_MARKER}\n{body}\n{END_MARKER}\n"


def replace_or_append(existing: str | None, block: str, label: str) -> tuple[str, str]:
    if existing is None:
        return block, f"create_{label}"

    start_count = existing.count(START_MARKER)
    end_count = existing.count(END_MARKER)
    if start_count != end_count or start_count > 1:
        raise SystemExit(f"{label} must contain zero or one devkit thought-db marker pair")

    start = existing.find(START_MARKER)
    end = existing.find(END_MARKER)
    if start != -1 and end < start:
        raise SystemExit(f"{label} has malformed devkit thought-db markers")

    if start != -1:
        end += len(END_MARKER)
        after = existing[end:]
        if after.startswith("\n"):
            after = after[1:]
        return f"{existing[:start]}{block}{after}", f"update_{label}_block"

    prefix = existing
    if prefix and not prefix.endswith("\n"):
        prefix += "\n"
    if prefix.strip():
        prefix += "\n"
    return f"{prefix}{block}", f"append_{label}_block"


def dump_result(payload: dict[str, object]) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def sync(thought_db: Path, targets: dict[str, Path], template: Path, dry_run: bool) -> int:
    if not thought_db.is_dir():
        dump_result(
            {
                "changed": False,
                "skipped": True,
                "reason": f"thought-db not found: {thought_db}",
                "actions": [],
            }
        )
        return 0

    block = desired_block(read_text(template.resolve()))
    actions: list[str] = []
    backups: list[tuple[Path, str]] = []
    writes: list[tuple[Path, str]] = []

    for label, path in targets.items():
        existing = read_text(path) if path.exists() else None
        desired, action = replace_or_append(existing, block, label)
        if existing != desired:
            if existing is not None:
                backup_path = path.parent / "devkit-thought-db-backup" / f"{path.name}.bak"
                actions.append(f"backup_{label}")
                backups.append((backup_path, existing))
            actions.append(action)
            writes.append((path, desired))

    changed = bool(writes)
    if not dry_run:
        for path, content in backups:
            write_text(path, content)
        for path, content in writes:
            write_text(path, content)

    dump_result({"changed": changed, "skipped": not changed, "actions": actions})
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Synchronize the thought-db reference block into user-level agent instruction files."
    )
    parser.add_argument("--thought-db", default=str(Path.home() / "repos/thought-db"), help="thought-db repository path")
    parser.add_argument("--claude-file", default=str(Path.home() / ".claude/CLAUDE.md"), help="Claude user-level instruction file")
    parser.add_argument("--codex-file", default=str(Path.home() / ".codex/AGENTS.md"), help="Codex user-level instruction file")
    parser.add_argument("--template", required=True, help="thought-db reference block template path")
    parser.add_argument("--dry-run", action="store_true", help="Report planned changes without writing files")
    parser.add_argument("--format", choices=["json"], default="json", help="Output format")
    args = parser.parse_args()

    targets = {
        "claude_user": Path(args.claude_file),
        "codex_user": Path(args.codex_file),
    }
    return sync(Path(args.thought_db), targets, Path(args.template), args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
