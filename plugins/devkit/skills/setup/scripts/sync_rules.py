#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


START_MARKER = "<!-- devkit:rules:start -->"
END_MARKER = "<!-- devkit:rules:end -->"
METADATA_VERSION = "1"


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def sha256_text(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def run_git_root(target: Path) -> Path:
    result = subprocess.run(
        ["git", "-C", str(target), "rev-parse", "--show-toplevel"],
        check=True,
        capture_output=True,
        text=True,
    )
    return Path(result.stdout.strip()).resolve()


def ensure_supported_target(repo_root: Path) -> None:
    if (repo_root / "plugins/devkit/.claude-plugin/plugin.json").exists():
        raise SystemExit("refusing to sync rules into the DevKit repository itself")


def desired_block(template_text: str) -> str:
    body = template_text.strip("\n")
    return f"{START_MARKER}\n{body}\n{END_MARKER}\n"


def replace_or_append_agents(existing: str | None, block: str) -> tuple[str, str]:
    if existing is None:
        return block, "create_agents"

    start_count = existing.count(START_MARKER)
    end_count = existing.count(END_MARKER)
    if start_count != end_count or start_count > 1:
        raise SystemExit("AGENTS.md must contain zero or one devkit rules marker pair")

    start = existing.find(START_MARKER)
    end = existing.find(END_MARKER)
    if start != -1 and end < start:
        raise SystemExit("AGENTS.md has malformed devkit rules markers")

    if start != -1:
        end += len(END_MARKER)
        after = existing[end:]
        if after.startswith("\n"):
            after = after[1:]
        return f"{existing[:start]}{block}{after}", "update_agents_block"

    prefix = existing
    if prefix and not prefix.endswith("\n"):
        prefix += "\n"
    if prefix.strip():
        prefix += "\n"
    return f"{prefix}{block}", "append_agents_block"


def ensure_claude_reference(existing: str | None) -> tuple[str, bool]:
    if existing is None:
        return "# CLAUDE.md\n\n@./AGENTS.md\n", True

    if any(line.strip() == "@./AGENTS.md" for line in existing.splitlines()):
        output_lines: list[str] = []
        seen_reference = False
        changed = False
        for line in existing.splitlines():
            if line.strip() == "@./AGENTS.md":
                if seen_reference:
                    changed = True
                    continue
                if line != "@./AGENTS.md":
                    changed = True
                output_lines.append("@./AGENTS.md")
                seen_reference = True
                continue
            output_lines.append(line)

        normalized = "\n".join(output_lines)
        if existing.endswith("\n") or changed:
            normalized += "\n"
        return normalized, changed or normalized != existing

    updated = existing
    if updated and not updated.endswith("\n"):
        updated += "\n"
    if updated.strip():
        updated += "\n"
    updated += "@./AGENTS.md\n"
    return updated, True


def read_metadata(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        data = json.loads(read_text(path))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def build_metadata(template_hash: str) -> dict[str, str]:
    return {
        "version": METADATA_VERSION,
        "synced_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "template_sha256": template_hash,
    }


def dump_result(changed: bool, actions: list[str]) -> None:
    payload = {
        "changed": changed,
        "skipped": not changed,
        "actions": actions,
    }
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def sync_rules(target: Path, template: Path, dry_run: bool) -> int:
    repo_root = run_git_root(target.resolve())
    ensure_supported_target(repo_root)
    template_text = read_text(template.resolve())
    template_hash = sha256_text(template_text)
    block = desired_block(template_text)

    agents_path = repo_root / "AGENTS.md"
    claude_path = repo_root / "CLAUDE.md"
    metadata_path = repo_root / ".claude/devkit-rules.json"
    backup_path = repo_root / ".claude/devkit-rules-backup/AGENTS.md.bak"

    existing_agents = read_text(agents_path) if agents_path.exists() else None
    desired_agents, agents_action = replace_or_append_agents(existing_agents, block)
    existing_claude = read_text(claude_path) if claude_path.exists() else None
    desired_claude, claude_changed = ensure_claude_reference(existing_claude)
    metadata = read_metadata(metadata_path)

    actions: list[str] = []
    agents_changed = existing_agents != desired_agents
    metadata_current = (
        metadata is not None
        and metadata.get("version") == METADATA_VERSION
        and isinstance(metadata.get("synced_at"), str)
        and bool(metadata.get("synced_at"))
        and metadata.get("template_sha256") == template_hash
    )

    if agents_changed:
        if existing_agents is not None:
            actions.append("backup_agents")
        actions.append(agents_action)
    if claude_changed:
        actions.append("create_claude" if existing_claude is None else "update_claude")
    if agents_changed or claude_changed or not metadata_current:
        actions.append("write_metadata")

    changed = bool(actions)
    if dry_run or not changed:
        dump_result(changed, actions)
        return 0

    if agents_changed and existing_agents is not None:
        write_text(backup_path, existing_agents)
    if agents_changed:
        write_text(agents_path, desired_agents)
    if claude_changed:
        write_text(claude_path, desired_claude)
    write_text(metadata_path, json.dumps(build_metadata(template_hash), ensure_ascii=False, indent=2) + "\n")

    dump_result(True, actions)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Synchronize DevKit rule markers into AGENTS.md and CLAUDE.md.")
    parser.add_argument("--target", required=True, help="Target git repository path")
    parser.add_argument("--template", required=True, help="Rules template path")
    parser.add_argument("--dry-run", action="store_true", help="Report planned changes without writing files")
    parser.add_argument("--format", choices=["json"], default="json", help="Output format")
    args = parser.parse_args()

    return sync_rules(Path(args.target), Path(args.template), args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
