#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path


ROOT = Path.cwd()


def must_read(rel: str) -> str:
    abs_path = ROOT / rel
    if not abs_path.exists():
        raise FileNotFoundError(f"Missing file: {rel}")
    return abs_path.read_text(encoding="utf-8")


def main() -> int:
    dig = must_read("plugins/devkit/skills/dig/SKILL.md")
    core = must_read("plugins/devkit/skills/dig-core/SKILL.md")
    claude = must_read("plugins/devkit/skills/dig-claude/SKILL.md")
    cursor = must_read("plugins/devkit/skills/dig-cursor/SKILL.md")
    codex = must_read("plugins/devkit/skills/dig-codex/SKILL.md")
    opencode = must_read("plugins/devkit/skills/dig-opencode/SKILL.md")
    workflow = must_read("plugins/devkit/shared/workflow.md")
    agents = must_read("AGENTS.md")
    readme = must_read("README.md")
    hooks = must_read("plugins/devkit/.claude-plugin/hooks.json")

    problems: list[str] = []

    for token in ["dig-core", "dig-claude", "dig-cursor", "dig-codex", "dig-opencode"]:
        if token not in dig:
            problems.append(f"dig orchestrator missing reference: {token}")

    for token in [
        "../dig-core/SKILL.md",
        "../dig-claude/SKILL.md",
        "../dig-cursor/SKILL.md",
        "../dig-codex/SKILL.md",
        "../dig-opencode/SKILL.md",
    ]:
        if token not in dig:
            problems.append(f"dig orchestrator missing internal file path: {token}")

    if "runtime=<claude|codex|opencode|cursor>" not in dig:
        problems.append("dig orchestrator missing runtime contract")
    if "Claude `/dig` -> `claude`" not in dig:
        problems.append("dig orchestrator missing Claude default: /dig -> claude")
    if "Codex `$dig` -> `codex`" not in dig:
        problems.append("dig orchestrator missing Codex default: $dig -> codex")
    if "Cursor `/dig` -> `cursor`" not in dig:
        problems.append("dig orchestrator missing Cursor default: /dig -> cursor")
    if "/devkit:dig" in dig:
        problems.append("dig orchestrator still references removed command: /devkit:dig")
    if "/prompts:devkit-dig" in dig:
        problems.append("dig orchestrator still references removed command: /prompts:devkit-dig")

    for content in [claude, cursor, codex, opencode]:
        if "dig-core" not in content:
            problems.append("adapter does not reference dig-core contract")

    if "DIG_CURSOR_REVIEW_BLOCKED" not in cursor:
        problems.append("dig-cursor missing review blocked stop code")
    if "DIG_CURSOR_PLAN_REVIEW_UNAVAILABLE" not in cursor:
        problems.append("dig-cursor missing plan review unavailable stop code")
    if "RERUN_COMMAND: /dig runtime=cursor <topic>" not in cursor:
        problems.append("dig-cursor missing rerun command")

    if "DIG_CODEX_PLAN_REQUIRED" not in codex:
        problems.append("dig-codex missing required stop code")
    if "DIG_CODEX_PLAN_REVIEW_UNAVAILABLE" not in codex:
        problems.append("dig-codex missing review unavailable stop code")
    if "DIG_CODEX_PLAN_REVIEW_BLOCKED" not in codex:
        problems.append("dig-codex missing review blocked stop code")
    if "REVIEW_PRIMARY_CMD" not in codex:
        problems.append("dig-codex missing REVIEW_PRIMARY_CMD marker")
    if "REVIEW_FALLBACK_CMD" not in codex:
        problems.append("dig-codex missing REVIEW_FALLBACK_CMD marker")
    if "/prompts:devkit-dig" in codex:
        problems.append("dig-codex still references removed command: /prompts:devkit-dig")
    if "RERUN_COMMAND: $dig <topic>" not in codex:
        problems.append("dig-codex missing rerun command for $dig")

    if "DIG_OPENCODE_PLAN_AGENT_REQUIRED" not in opencode:
        problems.append("dig-opencode missing plan agent stop code")
    if "DIG_OPENCODE_BUILD_REQUIRED" not in opencode:
        problems.append("dig-opencode missing build stop code")

    if "REVIEW_RESULT_MARKER=REVIEW_COUNTS" not in core:
        problems.append("dig-core missing REVIEW_RESULT_MARKER")
    if "STOP_OUTPUT_FIELDS: ERROR_CODE,RERUN_COMMAND,DIAGNOSTIC_COMMAND" not in core:
        problems.append("dig-core missing stop output marker")
    for token in ["Phase 1", "Phase 4", "Phase 5", "Phase 7"]:
        if token not in claude:
            problems.append(f"dig-claude missing 7-phase token: {token}")
    for token in ["[Task 1]", "Phase 4 通過後", "agent-parallel を常に第一候補"]:
        if token not in claude:
            problems.append(f"dig-claude missing task lifecycle token: {token}")
    for token in ["Phase 1", "Phase 4", "Phase 5", "[Task 1]"]:
        if token not in core:
            problems.append(f"dig-core missing 7-phase/task token: {token}")
    for token in ["UserPromptSubmit", "PreToolUse", "PostToolUse", "Stop", '"matcher": "Agent"', '"matcher": "Edit"', '"matcher": "Bash"']:
        if token not in hooks:
            problems.append(f"hooks.json missing dig hook contract token: {token}")

    if "gpt-5.3-codex-spark" not in workflow:
        problems.append("workflow missing spark review command")
    if "gpt-5.4" not in workflow:
        problems.append("workflow missing gpt-5.4 fallback review model")
    if "gpt-5.4" not in agents:
        problems.append("AGENTS.md missing gpt-5.4 fallback review model")
    if "gpt-5.4" not in readme:
        problems.append("README missing gpt-5.4 fallback review model")
    if 'model_reasoning_effort="medium"' not in workflow:
        problems.append("workflow missing medium effort fallback")
    if "codex -a never exec review" not in workflow:
        problems.append("workflow missing approval-never review command")
    if "codex -a never exec review" not in codex:
        problems.append("dig-codex missing approval-never review command")
    if "gpt-5.4" not in codex:
        problems.append("dig-codex missing gpt-5.4 fallback review model")

    if "/devkit:dig" in readme:
        problems.append("README still references removed command: /devkit:dig")
    if "/prompts:devkit-dig" in readme:
        problems.append("README still references removed command: /prompts:devkit-dig")
    if "DIG_CODEX_PLAN_REVIEW_UNAVAILABLE" not in readme:
        problems.append("README missing unavailable stop code")
    if "DIG_CODEX_PLAN_REVIEW_BLOCKED" not in readme:
        problems.append("README missing blocked stop code")
    if "codex -a never exec review" not in readme:
        problems.append("README missing approval-never review command")

    # ── 新契約チェック ──
    for adapter_name, content in [("claude", claude), ("cursor", cursor), ("codex", codex), ("opencode", opencode)]:
        if '> **Role**:' not in content:
            problems.append(f"dig-{adapter_name} missing role description (> **Role**:)")
        if "Plan Mode" not in content:
            problems.append(f"dig-{adapter_name} missing Plan Mode mapping")

    if "## エージェントアーキテクチャ" not in core:
        problems.append("dig-core missing agent architecture section")
    if "ラウンド数に上限を設けない" not in core:
        problems.append("dig-core missing unlimited round policy in Phase 1")
    if "Path A" not in core or "Path B" not in core:
        problems.append("dig-core missing review path definitions (Path A / Path B)")
    if "Codex Exec 相談ルール" not in agents:
        problems.append("AGENTS.md missing codex exec consultation rule")

    if problems:
        print(json.dumps({"ok": False, "problems": problems}, ensure_ascii=False, indent=2))
        return 2

    print(json.dumps({"ok": True}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
