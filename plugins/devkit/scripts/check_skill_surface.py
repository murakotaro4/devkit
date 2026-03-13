#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path


ROOT = Path.cwd()


def read_json(rel: str) -> object:
    raw = (ROOT / rel).read_text(encoding="utf-8").lstrip("\ufeff")
    return json.loads(raw)


def extract_block(content: str, start_token: str, end_token: str = "\nfunction ") -> str:
    start = content.find(start_token)
    if start == -1:
        return ""
    after_start = content[start:]
    next_function = after_start.find(end_token)
    if next_function == -1:
        return after_start
    return after_start[:next_function]


def run_bash(script: str) -> None:
    subprocess.run(
        ["bash", "-lc", script],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        env=os.environ.copy(),
    )


def run_runtime_smoke_checks() -> None:
    runtime_sync_sh = ROOT / "plugins/devkit/scripts/devkit-runtime-sync.sh"
    script_dir = runtime_sync_sh.parent

    with tempfile.TemporaryDirectory(prefix="devkit-checkout-") as checkout_home:
        run_bash(
            "\n".join(
                [
                    "set -euo pipefail",
                    f"export HOME={json.dumps(checkout_home)}",
                    f"SCRIPT_DIR={json.dumps(str(script_dir))}",
                    f"source {json.dumps(str(runtime_sync_sh))}",
                    'ROOT=$(ensure_devkit_repo_root)',
                    f'test "$ROOT" = {json.dumps(str(ROOT))}',
                    'test ! -e "$HOME/cursor/devkit"',
                ]
            )
        )

    with tempfile.TemporaryDirectory(prefix="devkit-worktree-") as worktree_home:
        run_bash(
            "\n".join(
                [
                    "set -euo pipefail",
                    f"export HOME={json.dumps(worktree_home)}",
                    'WORKTREE_ROOT="$HOME/worktree-devkit"',
                    'mkdir -p "$WORKTREE_ROOT/plugins"',
                    f"ln -s {json.dumps(str(ROOT / 'plugins/devkit'))} \"$WORKTREE_ROOT/plugins/devkit\"",
                    'printf "gitdir: /tmp/devkit-fake-worktree\\n" > "$WORKTREE_ROOT/.git"',
                    'export SCRIPT_DIR="$WORKTREE_ROOT/plugins/devkit/scripts"',
                    f"source {json.dumps(str(runtime_sync_sh))}",
                    'ROOT="$(devkit_script_checkout_root)"',
                    'test "$ROOT" = "$WORKTREE_ROOT"',
                ]
            )
        )

    with tempfile.TemporaryDirectory(prefix="devkit-false-positive-") as false_positive_home:
        run_bash(
            "\n".join(
                [
                    "set -euo pipefail",
                    f"export HOME={json.dumps(false_positive_home)}",
                    'git init "$HOME" >/dev/null 2>&1',
                    'mkdir -p "$HOME/.codex/bin"',
                    'export SCRIPT_DIR="$HOME/.codex/bin"',
                    f"source {json.dumps(str(runtime_sync_sh))}",
                    "! devkit_script_checkout_root",
                ]
            )
        )

    with tempfile.TemporaryDirectory(prefix="devkit-explicit-root-") as explicit_root_home:
        run_bash(
            "\n".join(
                [
                    "set -euo pipefail",
                    f"export HOME={json.dumps(explicit_root_home)}",
                    'ALT_ROOT="$HOME/alt-devkit"',
                    'mkdir -p "$ALT_ROOT/plugins"',
                    f"ln -s {json.dumps(str(ROOT / 'plugins/devkit'))} \"$ALT_ROOT/plugins/devkit\"",
                    'export DEVKIT_SOURCE_ROOT="$ALT_ROOT"',
                    f"SCRIPT_DIR={json.dumps(str(script_dir))}",
                    f"source {json.dumps(str(runtime_sync_sh))}",
                    'ROOT=$(ensure_devkit_repo_root)',
                    'test "$ROOT" = "$ALT_ROOT"',
                ]
            )
        )

    with tempfile.TemporaryDirectory(prefix="devkit-cleanup-") as cleanup_home:
        run_bash(
            "\n".join(
                [
                    "set -euo pipefail",
                    f"export HOME={json.dumps(cleanup_home)}",
                    f"export DEVKIT_SOURCE_ROOT={json.dumps(str(ROOT))}",
                    f"SCRIPT_DIR={json.dumps(str(script_dir))}",
                    'mkdir -p "$HOME/.codex/skills" "$HOME/.agents"',
                    f"ln -s {json.dumps(str(ROOT / 'plugins/devkit/skills/dig'))} \"$HOME/.codex/skills/dig\"",
                    f"ln -s {json.dumps(str(ROOT / 'plugins/devkit/skills/dig-core'))} \"$HOME/.codex/skills/dig-core\"",
                    'mkdir -p "$HOME/.codex/skills/custom-keep"',
                    f"source {json.dumps(str(runtime_sync_sh))}",
                    'sync_devkit_codex_runtime "$HOME"',
                    'test -L "$HOME/.agents/skills/dig"',
                    'test ! -e "$HOME/.codex/skills/dig"',
                    'test ! -e "$HOME/.codex/skills/dig-core"',
                    'test -d "$HOME/.codex/skills/custom-keep"',
                    f'test "$(head -n 1 "$HOME/.codex/devkit/source-root.txt")" = {json.dumps(str(ROOT))}',
                    'grep -F "$HOME/.codex/bin/update-devkit.sh" "$HOME/.local/bin/update-devkit"',
                ]
            )
        )

    with tempfile.TemporaryDirectory(prefix="devkit-opencode-cleanup-") as opencode_cleanup_home:
        run_bash(
            "\n".join(
                [
                    "set -euo pipefail",
                    f"export HOME={json.dumps(opencode_cleanup_home)}",
                    f"export DEVKIT_SOURCE_ROOT={json.dumps(str(ROOT))}",
                    f"SCRIPT_DIR={json.dumps(str(script_dir))}",
                    'mkdir -p "$HOME/.config/opencode/skills" "$HOME/.config/opencode/devkit/source/plugins/devkit/skills" "$HOME/.claude/plugins/marketplaces/murakotaro4/plugins/devkit/skills"',
                    'mkdir -p "$HOME/.config/opencode/devkit/source/plugins/devkit/skills/dig" "$HOME/.config/opencode/devkit/source/plugins/devkit/skills/dig-core"',
                    'mkdir -p "$HOME/.claude/plugins/marketplaces/murakotaro4/plugins/devkit/skills/dig-opencode"',
                    'ln -s "$HOME/.config/opencode/devkit/source/plugins/devkit/skills/dig" "$HOME/.config/opencode/skills/dig"',
                    'ln -s "$HOME/.config/opencode/devkit/source/plugins/devkit/skills/dig-core" "$HOME/.config/opencode/skills/dig-core"',
                    'ln -s "$HOME/.claude/plugins/marketplaces/murakotaro4/plugins/devkit/skills/dig-opencode" "$HOME/.config/opencode/skills/dig-opencode"',
                    'mkdir -p "$HOME/.config/opencode/skills/custom-keep"',
                    f"source {json.dumps(str(runtime_sync_sh))}",
                    'sync_devkit_opencode_runtime "$HOME"',
                    f'test "$(readlink "$HOME/.config/opencode/skills/dig")" = {json.dumps(str(ROOT / "plugins/devkit/skills/dig"))}',
                    'test ! -e "$HOME/.config/opencode/skills/dig-core"',
                    'test ! -e "$HOME/.config/opencode/skills/dig-opencode"',
                    'test -d "$HOME/.config/opencode/skills/custom-keep"',
                    f'test "$(head -n 1 "$HOME/.config/opencode/devkit/source-root.txt")" = {json.dumps(str(ROOT))}',
                ]
            )
        )

    with tempfile.TemporaryDirectory(prefix="devkit-clone-fail-") as clone_failure_home, tempfile.TemporaryDirectory(
        prefix="devkit-detached-script-"
    ) as detached_script_dir:
        detached_runtime_sync = Path(detached_script_dir) / "devkit-runtime-sync.sh"
        shutil.copyfile(runtime_sync_sh, detached_runtime_sync)
        run_bash(
            "\n".join(
                [
                    "set -euo pipefail",
                    f"export HOME={json.dumps(clone_failure_home)}",
                    "export DEVKIT_REPO_URL='/definitely/missing/devkit.git'",
                    f"SCRIPT_DIR={json.dumps(detached_script_dir)}",
                    f"source {json.dumps(str(detached_runtime_sync))}",
                    "! ensure_devkit_repo_root",
                    'test ! -e "$HOME/cursor/devkit"',
                    'test ! -e "$HOME/.codex/devkit/source-root.txt"',
                ]
            )
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", default="B")
    args = parser.parse_args()

    required = [
        "plugins/devkit/skills/dig/SKILL.md",
        "plugins/devkit/skills/dig-core/SKILL.md",
        "plugins/devkit/skills/dig-claude/SKILL.md",
        "plugins/devkit/skills/dig-codex/SKILL.md",
        "plugins/devkit/skills/dig-opencode/SKILL.md",
        "plugins/devkit/scripts/devkit-runtime-sync.sh",
        "plugins/devkit/scripts/devkit-runtime-sync.ps1",
        "plugins/devkit/templates/opencode/commands/dig.md",
        "plugins/devkit/.claude-plugin/plugin.json",
        "plugins/devkit/.claude-plugin/marketplace.json",
        "README.md",
    ]
    removed = [
        "plugins/devkit/skills/agent-orch-core",
        "plugins/devkit/skills/agent-orch-openai",
        "plugins/devkit/skills/agent-orch-anthropic",
        "plugins/devkit/skills/agent-orch-google",
        "plugins/devkit/skills/codex",
    ]
    problems: list[str] = []

    for rel in required:
        if not (ROOT / rel).exists():
            problems.append(f"missing required: {rel}")

    for rel in [
        "plugins/devkit/skills/dig/SKILL.md",
        "plugins/devkit/skills/dig-core/SKILL.md",
        "plugins/devkit/skills/dig-claude/SKILL.md",
        "plugins/devkit/skills/dig-codex/SKILL.md",
        "plugins/devkit/skills/dig-opencode/SKILL.md",
    ]:
        abs_path = ROOT / rel
        if not abs_path.exists():
            continue
        buf = abs_path.read_bytes()
        if len(buf) >= 3 and buf[:3] == b"\xef\xbb\xbf":
            problems.append(f"BOM not allowed in dig skill frontmatter: {rel}")

    if args.phase == "B":
        for rel in removed:
            if (ROOT / rel).exists():
                problems.append(f"must be removed in phase B: {rel}")

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    import re

    readme = re.sub(r"##\s+Migration Notice[\s\S]*?(?=\n##\s+|$)", "", readme, flags=re.M)
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    workflow = (ROOT / "plugins/devkit/shared/workflow.md").read_text(encoding="utf-8")
    dig = (ROOT / "plugins/devkit/skills/dig/SKILL.md").read_text(encoding="utf-8")

    if re.search(r"/devkit:codex(?!-)\b", readme) or "/devkit:agent-orch-" in readme:
        problems.append("README still references removed slash commands")
    if "/devkit:dig" in readme:
        problems.append("README still references removed command: /devkit:dig")
    if "/prompts:devkit-dig" in readme:
        problems.append("README still references removed command: /prompts:devkit-dig")
    if "/devkit:dig" in dig:
        problems.append("dig skill still references removed command: /devkit:dig")
    if "/prompts:devkit-dig" in dig:
        problems.append("dig skill still references removed command: /prompts:devkit-dig")
    for token in ["DIG_CODEX_PLAN_REVIEW_UNAVAILABLE", "DIG_CODEX_PLAN_REVIEW_BLOCKED"]:
        if token not in readme:
            problems.append(f"README missing dig-codex stop code: {token}")
        if token not in workflow:
            problems.append(f"workflow missing dig-codex stop code: {token}")
    if "gpt-5.3-codex-spark" not in workflow:
        problems.append("workflow missing spark review model")
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

    dig_codex = (ROOT / "plugins/devkit/skills/dig-codex/SKILL.md").read_text(encoding="utf-8")
    if "gpt-5.4" not in dig_codex:
        problems.append("dig-codex missing gpt-5.4 fallback review model")

    runtime_sync_sh = (ROOT / "plugins/devkit/scripts/devkit-runtime-sync.sh").read_text(encoding="utf-8")
    runtime_sync_ps1 = (ROOT / "plugins/devkit/scripts/devkit-runtime-sync.ps1").read_text(encoding="utf-8")
    shell_manifest = extract_block(
        runtime_sync_sh, "devkit_skill_manifest() {", "\ndevkit_retired_skill_entries() {"
    )
    ps_manifest = extract_block(runtime_sync_ps1, "function Get-DevKitSkillManifest {")
    shell_retired = extract_block(
        runtime_sync_sh, "devkit_retired_skill_entries() {", "\ndevkit_repo_url() {"
    )
    ps_retired = extract_block(runtime_sync_ps1, "function Get-DevKitRetiredSkillEntries {")

    for manifest_name, manifest in [
        ("devkit-runtime-sync.sh", shell_manifest),
        ("devkit-runtime-sync.ps1", ps_manifest),
    ]:
        if "dig" not in manifest:
            problems.append(f"{manifest_name} missing public dig entry")
        for token in ["dig-core", "dig-claude", "dig-codex", "dig-opencode"]:
            if f'"{token}"' in manifest or f"{token} \\" in manifest or f"    {token}" in manifest:
                problems.append(f"{manifest_name} still syncs internal dig adapter: {token}")

    if "source-root.txt" not in runtime_sync_sh or "source-root.txt" not in runtime_sync_ps1:
        problems.append("runtime sync scripts missing persisted source root support")
    if "DEVKIT_SOURCE_ROOT" not in runtime_sync_sh or "DEVKIT_SOURCE_ROOT" not in runtime_sync_ps1:
        problems.append("runtime sync scripts missing DEVKIT_SOURCE_ROOT override")
    if "prune_legacy_opencode_managed_entries" not in runtime_sync_sh or "Remove-DevKitLegacyOpenCodeManagedEntries" not in runtime_sync_ps1:
        problems.append("runtime sync scripts missing OpenCode legacy cleanup")
    for retired_name, retired_block in [
        ("devkit-runtime-sync.sh", shell_retired),
        ("devkit-runtime-sync.ps1", ps_retired),
    ]:
        if "mermaid-show" not in retired_block:
            problems.append(f"{retired_name} missing retired skill cleanup entry: mermaid-show")
        for token in ["dig-core", "dig-claude", "dig-codex", "dig-opencode"]:
            if token not in retired_block:
                problems.append(f"{retired_name} missing retired adapter cleanup entry: {token}")

    if shutil.which("pwsh"):
        try:
            subprocess.run(
                [
                    "pwsh",
                    "-NoProfile",
                    "-Command",
                    (
                        f". '{ROOT / 'plugins/devkit/scripts/devkit-runtime-sync.ps1'}'; "
                        "if ((Get-DevKitSkillManifest) -contains 'mermaid-show') { exit 2 }; "
                        "if (-not ((Get-DevKitRetiredSkillEntries) -contains 'mermaid-show')) { exit 3 }"
                    ),
                ],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as exc:
            detail = exc.stderr.strip() or exc.stdout.strip() or str(exc)
            problems.append(f"PowerShell manifest smoke failed: {detail}")

    js_files = sorted(
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / "plugins/devkit").rglob("*")
        if path.is_file() and path.suffix in {".js", ".mjs"}
    )
    if js_files:
        problems.append(f"JavaScript files must be removed from plugins/devkit: {', '.join(js_files)}")

    try:
        run_runtime_smoke_checks()
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.strip() or exc.stdout.strip() or str(exc)
        problems.append(f"runtime sync smoke failed: {detail}")

    plugin = read_json("plugins/devkit/.claude-plugin/plugin.json")
    if not isinstance(plugin, dict) or not isinstance(plugin.get("version"), str):
        problems.append("plugin.json version missing")
    if isinstance(plugin, dict) and "agent-orch" in str(plugin.get("description", "")).lower():
        problems.append("plugin description still references agent-orch")

    market = read_json("plugins/devkit/.claude-plugin/marketplace.json")
    desc = ""
    if isinstance(market, dict):
        plugins = market.get("plugins") or []
        if plugins and isinstance(plugins[0], dict):
            desc = str(plugins[0].get("description", ""))
    if "agent-orch" in desc.lower():
        problems.append("marketplace description still references agent-orch")

    if problems:
        print(json.dumps({"phase": args.phase, "problems": problems}, ensure_ascii=False, indent=2))
        return 2

    print(json.dumps({"phase": args.phase, "ok": True}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
