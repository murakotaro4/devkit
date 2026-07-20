#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import tarfile
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path.cwd()
LEGACY_PATTERNS = [
    r"(?<![\w-])dig-goal\b",
    r"devkit-dig-goal-wt\b",
    r"devkit-dig-goal-job\b",
    r"/prompts:devkit-dig\b",
    r"/devkit:codex(?!-)\b",
    r"/devkit:agent-orch-(core|openai|anthropic|google)\b",
    r"devkit-codex(?!-)\b",
    r"devkit-agent-orch-core\b",
    r"agent-orch-(core|openai|anthropic|google)\b",
    r"plugins/devkit/skills/codex\b",
    r"plugins/devkit/skills/agent-orch-(core|openai|anthropic|google)\b",
    r"dig-(core|claude|codex|cursor|opencode)\b",
    r"codex-impl\b",
    r"(?:skills/|/devkit:)decomposition\b",
    r"devkit-init\b",
    r"shared/workflow\.md",
    r"auto-retro\b",
    r"discord-rust-server-ops\b",
    r"discord-rust-skill\b",
    r"rust-minimal8\.json\b",
    r"02_projects/streaming/discord-rust-server-ops\b",
    r"REVIEW_GATE_[A-Z]",
    r"team_shape\b",
    r"DIG_[A-Z]+_[A-Z]",
    r"devkit-runtime-sync\b",
    r"devkit-skill-update\b",
    r"sync_devkit_(codex|opencode)_runtime\b",
    r"(?:plugins/devkit/)?skills/(gpt-pro|deep-research|computer-use-chatgpt-pro|codex-search|discord-ops|discord-rust-server-ops|repo-maintainer|repo-maintainer-init)\b",
    r"/devkit:(gpt-pro|deep-research|computer-use-chatgpt-pro|codex-search|discord-ops|discord-rust-server-ops|repo-maintainer|repo-maintainer-init)\b",
    r"opencode-ai\b",
    r"\bOpenCode\b",
    r"\bopencode\b",
    r"\.config/opencode/skills\b",
    r"DevKitSkillsDailyUpdate\b",
    r"(?<![A-Za-z0-9_])AskUserQuestionTool(?![A-Za-z0-9_])",
]
TEXT_EXT = {
    ".md",
    ".txt",
    ".lock",
    ".json",
    ".js",
    ".mjs",
    ".cjs",
    ".yaml",
    ".yml",
    ".ts",
    ".tsx",
    ".jsx",
    ".sh",
    ".ps1",
    ".bat",
    ".cmd",
    ".toml",
    ".ini",
    ".cfg",
    ".py",
}
PRUNE_IMPLEMENTATION_FILES = {
    "plugins/devkit/scripts/devkit-lib.sh",
    "plugins/devkit/scripts/devkit-lib.ps1",
}


def is_binary_buffer(buf: bytes) -> bool:
    return b"\x00" in buf[:8000]


def collect_files(directory: Path) -> list[Path]:
    out: list[Path] = []
    for path in directory.rglob("*"):
        if path.is_dir():
            continue
        rel = path.relative_to(directory).as_posix()
        # 除外対象は scan 対象ツリー内の相対パス構成要素だけで判定する。directory
        # (= ROOT) 自身の絶対パスが ".claude/worktrees/<slug>" のように除外語を
        # 祖先に含む場合、path.parts (絶対パス) で判定すると全ファイルが除外され、
        # scan が常に 0 findings を返す誤検出ゼロの見せかけ(実際は未スキャン)に
        # なるため、必ず rel 側の parts で判定する。
        if any(
            part in {".git", "node_modules", ".claude", ".codex", ".venv", "__pycache__"}
            for part in Path(rel).parts
        ):
            continue
        out.append(path)
    return out


def is_allowed_exception(file_rel: str, line: str, in_migration_notice: bool) -> bool:
    if "migration-allow" in line:
        return True
    if file_rel in PRUNE_IMPLEMENTATION_FILES:
        return True
    name = file_rel.rsplit("/", 1)[-1]
    if name == "CHANGELOG.md":
        return True
    if name == "README.md":
        return in_migration_notice
    return False


def scan_text_file(abs_path: Path, rel_path: str) -> list[dict[str, object]]:
    import re

    content = abs_path.read_text(encoding="utf-8")
    lines = content.splitlines()
    findings: list[dict[str, object]] = []
    in_migration_notice = False

    for index, line in enumerate(lines, start=1):
        if rel_path.rsplit("/", 1)[-1] == "README.md":
            if re.match(r"^##\s+Migration Notice\b", line):
                in_migration_notice = True
            elif re.match(r"^##\s+", line) and in_migration_notice:
                in_migration_notice = False

        for pattern in LEGACY_PATTERNS:
            match = re.search(pattern, line)
            if not match:
                continue
            if is_allowed_exception(rel_path, line, in_migration_notice):
                continue
            findings.append(
                {
                    "path": rel_path,
                    "line": index,
                    "token": match.group(0),
                    "replacement": "Use the new /dig (deep-dive to implementation) and /goal-prompt (goal prompt generation) skills",
                }
            )

    return findings


def scan_dir(directory: Path) -> dict[str, list[dict[str, object]]]:
    findings: list[dict[str, object]] = []
    binaries: list[dict[str, object]] = []

    # checker 自身と、retired エントリとして legacy 名を契約上保持する配布スクリプトは走査対象外。
    skip_names = {
        "check_legacy_migration.py",
        "check_skill_surface.py",
        "check_plugin_version_bump.py",
    }

    for file_path in collect_files(directory):
        rel = file_path.relative_to(directory).as_posix()
        if file_path.name in skip_names:
            continue
        if rel.startswith("plugins/devkit/tests/"):
            continue

        buf = file_path.read_bytes()
        if is_binary_buffer(buf) or file_path.suffix.lower() not in TEXT_EXT:
            binaries.append({"path": rel, "sha256": hashlib.sha256(buf).hexdigest()})
            continue

        try:
            findings.extend(scan_text_file(file_path, rel))
        except UnicodeDecodeError:
            binaries.append({"path": rel, "sha256": hashlib.sha256(buf).hexdigest()})

    return {"findings": findings, "binaries": binaries}


def extract_artifact(artifact: Path, temp_dir: Path) -> None:
    lower = artifact.name.lower()
    if lower.endswith(".zip"):
        with zipfile.ZipFile(artifact) as archive:
            archive.extractall(temp_dir)
        return
    if lower.endswith((".tar", ".tgz", ".tar.gz")):
        with tarfile.open(artifact) as archive:
            archive.extractall(temp_dir)
        return
    raise RuntimeError(f"Unsupported artifact type: {artifact}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", default="repo", choices=["repo", "artifact"])
    parser.add_argument("--artifact", default="")
    args = parser.parse_args()

    if args.mode == "repo":
        result = scan_dir(ROOT)
    else:
        if not args.artifact:
            raise RuntimeError("--artifact is required in artifact mode")
        artifact = (ROOT / args.artifact).resolve()
        if not artifact.exists():
            raise RuntimeError(f"Artifact not found: {artifact}")
        with TemporaryDirectory(prefix="legacy-mig-") as temp_dir_name:
            temp_dir = Path(temp_dir_name)
            extract_artifact(artifact, temp_dir)
            result = scan_dir(temp_dir)

    payload = {
        "mode": args.mode,
        "findings": result["findings"],
        "binaryEntries": result["binaries"],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 2 if result["findings"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
