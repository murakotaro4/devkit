#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path


ROOT = Path.cwd()


def shell_path(path: Path | str) -> str:
    raw = path.as_posix() if isinstance(path, Path) else str(path).replace("\\", "/")
    if len(raw) >= 3 and raw[1:3] == ":/":
        raw = f"/{raw[0].lower()}/{raw[3:]}"
    return json.dumps(raw)


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


def manifest_entries(manifest: str) -> set[str]:
    entries: set[str] = set()
    for raw_line in manifest.splitlines():
        line = raw_line.strip()
        if not line or line.startswith(("devkit_skill_manifest", "function Get-DevKitSkillManifest", "return @(")):
            continue
        line = line.split("#", 1)[0].strip()
        line = line.removesuffix("\\").strip().removesuffix(",").strip()
        if line.startswith('"') and line.endswith('"'):
            line = line[1:-1]
        if re.fullmatch(r"[A-Za-z0-9_-]+", line):
            entries.add(line)
    return entries


def run_bash(script: str) -> None:
    subprocess.run(
        ["bash", "-lc", script],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        env=os.environ.copy(),
    )


def write_executable(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def run_update_devkit_argument_smoke_checks() -> None:
    if os.name == "nt":
        return

    update_ccx_sh = ROOT / "plugins/devkit/scripts/update-ccx.sh"
    fake_tool = """#!/bin/sh
echo "$(basename "$0") $*" >> "$DEVKIT_TEST_CALL_LOG"
case "$(basename "$0")" in
  brew)
    case "$1" in
      --version) echo "Homebrew 0.0.0" ;;
      --prefix) echo "$DEVKIT_FAKE_BREW_PREFIX" ;;
    esac
    ;;
  fnm)
    echo "fnm 0.0.0"
    ;;
  node)
    echo "v0.0.0"
    ;;
  claude|codex|opencode)
    if [ "$1" = "--version" ]; then
      echo "$(basename "$0") 0.0.0"
    elif [ "$1" = "update" ]; then
      echo "updated"
    fi
    ;;
esac
exit 0
"""

    def run_case(
        label: str,
        args: list[str],
        *,
        expected_log_lines: list[str],
        blocked_cli_prefixes: list[str],
        blocked_log_lines: list[str],
        expect_codex_sync: bool,
        expect_opencode_sync: bool,
        expect_no_cli: bool = False,
    ) -> None:
        with tempfile.TemporaryDirectory(prefix=f"devkit-update-{label}-home-") as home, tempfile.TemporaryDirectory(
            prefix=f"devkit-update-{label}-bin-"
        ) as fake_bin:
            home_path = Path(home)
            source_root = home_path / "source"
            (source_root / "plugins").mkdir(parents=True)
            (source_root / "plugins/devkit").symlink_to(ROOT / "plugins/devkit", target_is_directory=True)

            call_log = home_path / "tool-calls.log"
            fake_bin_path = Path(fake_bin)
            for name in ["brew", "claude", "codex", "curl", "fnm", "node", "npm", "opencode"]:
                write_executable(fake_bin_path / name, fake_tool)

            env = os.environ.copy()
            env.update(
                {
                    "DEVKIT_FAKE_BREW_PREFIX": str(home_path / "fake-homebrew-prefix"),
                    "DEVKIT_SOURCE_ROOT": str(source_root),
                    "DEVKIT_TEST_CALL_LOG": str(call_log),
                    "HOME": home,
                    "PATH": f"{fake_bin}{os.pathsep}{env.get('PATH', '')}",
                }
            )
            result = subprocess.run(
                ["bash", str(update_ccx_sh), *args],
                cwd=ROOT,
                capture_output=True,
                text=True,
                env=env,
                check=True,
            )

            log_text = call_log.read_text(encoding="utf-8") if call_log.exists() else ""
            log_lines = log_text.splitlines()
            if expect_no_cli and log_text.strip():
                raise AssertionError(f"{label} invoked CLI tooling:\n{log_text}")
            for expected in expected_log_lines:
                if expected not in log_lines:
                    raise AssertionError(f"{label} did not run expected command {expected!r}:\n{log_text}")
            for blocked in blocked_cli_prefixes:
                if any(line.startswith(blocked) for line in log_lines):
                    raise AssertionError(f"{label} touched unselected CLI prefix {blocked!r}:\n{log_text}")
            for blocked in blocked_log_lines:
                if blocked in log_lines:
                    raise AssertionError(f"{label} ran blocked command {blocked!r}:\n{log_text}")

            codex_synced = "✓ Codex runtime synced" in result.stdout
            opencode_synced = "✓ OpenCode runtime synced" in result.stdout
            if codex_synced != expect_codex_sync:
                raise AssertionError(f"{label} Codex sync mismatch:\n{result.stdout}\n{result.stderr}")
            if opencode_synced != expect_opencode_sync:
                raise AssertionError(f"{label} OpenCode sync mismatch:\n{result.stdout}\n{result.stderr}")

            codex_skills = {
                "computer-use-chatgpt-pro": home_path / ".agents/skills/computer-use-chatgpt-pro",
                "gpt-pro": home_path / ".agents/skills/gpt-pro",
            }
            opencode_skills = {
                "computer-use-chatgpt-pro": home_path / ".config/opencode/skills/computer-use-chatgpt-pro",
                "gpt-pro": home_path / ".config/opencode/skills/gpt-pro",
            }
            if codex_skills["computer-use-chatgpt-pro"].exists() != expect_codex_sync:
                raise AssertionError(f"{label} Codex skill sync mismatch")
            if codex_skills["gpt-pro"].exists() != expect_codex_sync:
                raise AssertionError(f"{label} Codex gpt-pro sync mismatch")
            if opencode_skills["computer-use-chatgpt-pro"].exists() != expect_opencode_sync:
                raise AssertionError(f"{label} OpenCode skill sync mismatch")
            if opencode_skills["gpt-pro"].exists() != expect_opencode_sync:
                raise AssertionError(f"{label} OpenCode gpt-pro sync mismatch")

    run_case(
        "devkit-only-codex",
        ["--devkit-only", "--runtime", "codex"],
        expected_log_lines=[],
        blocked_cli_prefixes=[],
        blocked_log_lines=[],
        expect_codex_sync=True,
        expect_opencode_sync=False,
        expect_no_cli=True,
    )
    run_case(
        "runtime-codex",
        ["--runtime", "codex"],
        expected_log_lines=["npm update -g @openai/codex"],
        blocked_cli_prefixes=["claude ", "opencode "],
        blocked_log_lines=["claude update", "brew upgrade opencode", "npm update -g opencode-ai"],
        expect_codex_sync=True,
        expect_opencode_sync=False,
    )
    run_case(
        "runtime-opencode",
        ["--runtime", "opencode"],
        expected_log_lines=["npm update -g opencode-ai"],
        blocked_cli_prefixes=["claude ", "codex "],
        blocked_log_lines=["claude update", "brew upgrade codex", "npm update -g @openai/codex"],
        expect_codex_sync=False,
        expect_opencode_sync=True,
    )
    run_case(
        "runtime-all",
        ["--runtime", "all"],
        expected_log_lines=["claude update", "npm update -g @openai/codex", "npm update -g opencode-ai"],
        blocked_cli_prefixes=[],
        blocked_log_lines=[],
        expect_codex_sync=True,
        expect_opencode_sync=True,
    )


def run_runtime_smoke_checks() -> None:
    if os.name == "nt":
        return

    runtime_sync_sh = ROOT / "plugins/devkit/scripts/devkit-runtime-sync.sh"
    script_dir = runtime_sync_sh.parent

    with tempfile.TemporaryDirectory(prefix="devkit-checkout-") as checkout_home:
        run_bash(
            "\n".join(
                [
                    "set -euo pipefail",
                    f"export HOME={json.dumps(checkout_home)}",
                    f"SCRIPT_DIR={shell_path(script_dir)}",
                    f"source {shell_path(runtime_sync_sh)}",
                    'ROOT=$(ensure_devkit_repo_root)',
                    f'test "$ROOT" = {shell_path(ROOT)}',
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
                    f"ln -s {shell_path(ROOT / 'plugins/devkit')} \"$WORKTREE_ROOT/plugins/devkit\"",
                    'printf "gitdir: /tmp/devkit-fake-worktree\\n" > "$WORKTREE_ROOT/.git"',
                    'export SCRIPT_DIR="$WORKTREE_ROOT/plugins/devkit/scripts"',
                    f"source {shell_path(runtime_sync_sh)}",
                    'ROOT="$(devkit_script_checkout_root)"',
                    'EXPECTED_ROOT="$(cd "$WORKTREE_ROOT" && pwd -P)"',
                    'test "$ROOT" = "$EXPECTED_ROOT"',
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
                    f"source {shell_path(runtime_sync_sh)}",
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
                    f"ln -s {shell_path(ROOT / 'plugins/devkit')} \"$ALT_ROOT/plugins/devkit\"",
                    'export DEVKIT_SOURCE_ROOT="$ALT_ROOT"',
                    f"SCRIPT_DIR={shell_path(script_dir)}",
                    f"source {shell_path(runtime_sync_sh)}",
                    'ROOT=$(ensure_devkit_repo_root)',
                    'EXPECTED_ROOT="$(cd "$ALT_ROOT" && pwd -P)"',
                    'test "$ROOT" = "$EXPECTED_ROOT"',
                ]
            )
        )

    with tempfile.TemporaryDirectory(prefix="devkit-cleanup-") as cleanup_home:
        run_bash(
            "\n".join(
                [
                    "set -euo pipefail",
                    f"export HOME={json.dumps(cleanup_home)}",
                    f"export DEVKIT_SOURCE_ROOT={shell_path(ROOT)}",
                    f"SCRIPT_DIR={shell_path(script_dir)}",
                    'mkdir -p "$HOME/.codex/skills" "$HOME/.agents"',
                    'mkdir -p "$HOME/.codex/devkit/source/plugins/devkit/skills/amazon-search"',
                    f"ln -s {shell_path(ROOT / 'plugins/devkit/skills/dig')} \"$HOME/.codex/skills/dig\"",
                    f"ln -s {shell_path(ROOT / 'plugins/devkit/skills/dig-core')} \"$HOME/.codex/skills/dig-core\"",
                    'ln -s "$HOME/.codex/devkit/source/plugins/devkit/skills/amazon-search" "$HOME/.codex/skills/amazon-search"',
                    'mkdir -p "$HOME/.codex/skills/custom-keep"',
                    f"source {shell_path(runtime_sync_sh)}",
                    'sync_devkit_codex_runtime "$HOME"',
                    'test ! -e "$HOME/.agents/skills/dig" -a ! -L "$HOME/.agents/skills/dig"',
                    f'test "$(readlink "$HOME/.agents/skills/gpt-pro")" = {shell_path(ROOT / "plugins/devkit/skills/gpt-pro")}',
                    f'test "$(readlink "$HOME/.agents/skills/computer-use-chatgpt-pro")" = {shell_path(ROOT / "plugins/devkit/skills/computer-use-chatgpt-pro")}',
                    'test ! -e "$HOME/.codex/skills/dig" -a ! -L "$HOME/.codex/skills/dig"',
                    'test ! -e "$HOME/.codex/skills/dig-core" -a ! -L "$HOME/.codex/skills/dig-core"',
                    'test ! -e "$HOME/.codex/skills/amazon-search"',
                    'test -d "$HOME/.codex/skills/custom-keep"',
                    f'test "$(head -n 1 "$HOME/.codex/devkit/source-root.txt")" = {shell_path(ROOT)}',
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
                    f"export DEVKIT_SOURCE_ROOT={shell_path(ROOT)}",
                    f"SCRIPT_DIR={shell_path(script_dir)}",
                    'mkdir -p "$HOME/.config/opencode/skills" "$HOME/.config/opencode/devkit/source/plugins/devkit/skills" "$HOME/.claude/plugins/marketplaces/murakotaro4/plugins/devkit/skills"',
                    'mkdir -p "$HOME/.config/opencode/devkit/source/plugins/devkit/skills/dig" "$HOME/.config/opencode/devkit/source/plugins/devkit/skills/dig-core" "$HOME/.config/opencode/devkit/source/plugins/devkit/skills/amazon-search"',
                    'mkdir -p "$HOME/.claude/plugins/marketplaces/murakotaro4/plugins/devkit/skills/dig-opencode"',
                    'ln -s "$HOME/.config/opencode/devkit/source/plugins/devkit/skills/dig" "$HOME/.config/opencode/skills/dig"',
                    'ln -s "$HOME/.config/opencode/devkit/source/plugins/devkit/skills/dig-core" "$HOME/.config/opencode/skills/dig-core"',
                    'ln -s "$HOME/.config/opencode/devkit/source/plugins/devkit/skills/amazon-search" "$HOME/.config/opencode/skills/amazon-search"',
                    'ln -s "$HOME/.claude/plugins/marketplaces/murakotaro4/plugins/devkit/skills/dig-opencode" "$HOME/.config/opencode/skills/dig-opencode"',
                    'mkdir -p "$HOME/.config/opencode/skills/custom-keep"',
                    f"source {shell_path(runtime_sync_sh)}",
                    'sync_devkit_opencode_runtime "$HOME"',
                    'test ! -e "$HOME/.config/opencode/skills/dig" -a ! -L "$HOME/.config/opencode/skills/dig"',
                    f'test "$(readlink "$HOME/.config/opencode/skills/gpt-pro")" = {shell_path(ROOT / "plugins/devkit/skills/gpt-pro")}',
                    f'test "$(readlink "$HOME/.config/opencode/skills/computer-use-chatgpt-pro")" = {shell_path(ROOT / "plugins/devkit/skills/computer-use-chatgpt-pro")}',
                    'test ! -e "$HOME/.config/opencode/skills/dig-core"',
                    'test ! -e "$HOME/.config/opencode/skills/amazon-search"',
                    'test ! -e "$HOME/.config/opencode/skills/dig-opencode"',
                    'test -d "$HOME/.config/opencode/skills/custom-keep"',
                    f'test "$(head -n 1 "$HOME/.config/opencode/devkit/source-root.txt")" = {shell_path(ROOT)}',
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
                    f"SCRIPT_DIR={shell_path(detached_script_dir)}",
                    f"source {shell_path(detached_runtime_sync)}",
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
        "plugins/devkit/skills/computer-use-chatgpt-pro/SKILL.md",
        "plugins/devkit/scripts/devkit-runtime-sync.sh",
        "plugins/devkit/scripts/devkit-runtime-sync.ps1",
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

    dig_skill_path = ROOT / "plugins/devkit/skills/dig/SKILL.md"
    if dig_skill_path.exists() and dig_skill_path.read_bytes()[:3] == b"\xef\xbb\xbf":
        problems.append("BOM not allowed in dig skill frontmatter: plugins/devkit/skills/dig/SKILL.md")

    if args.phase == "B":
        for rel in removed:
            if (ROOT / rel).exists():
                problems.append(f"must be removed in phase B: {rel}")

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    readme = re.sub(r"##\s+Migration Notice[\s\S]*?(?=\n##\s+|\Z)", "", readme)
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

    gpt_pro_skill = (ROOT / "plugins/devkit/skills/gpt-pro/SKILL.md").read_text(encoding="utf-8")
    deep_research_skill = (ROOT / "plugins/devkit/skills/deep-research/SKILL.md").read_text(encoding="utf-8")
    chrome_runner = ROOT / "plugins/devkit/scripts/chrome_chatgpt_runner.py"
    for required_text in [
        "Chrome の通常 `Default` profile",
        "専用 profile や API-first 経路へは切り替えない",
        "Chrome の再起動まで許可",
        "agent-browser",
        "Playwright `connectOverCDP`",
        "Chrome 拡張経路",
        "chrome_chatgpt_runner.py",
        "computer-use-chatgpt-pro",
        "localhost,127.0.0.1,::1",
    ]:
        if required_text not in gpt_pro_skill:
            problems.append(f"gpt-pro missing required contract text: {required_text}")
    for required_text in [
        "Chrome の通常 `Default` profile",
        "API-first 経路は使わない",
        "Chrome の再起動まで許可",
        "agent-browser",
        "Playwright `connectOverCDP`",
        "Chrome 拡張経路",
        "chrome_chatgpt_runner.py",
        "sandboxed iframe",
        "localhost,127.0.0.1,::1",
    ]:
        if required_text not in deep_research_skill:
            problems.append(f"deep-research missing required contract text: {required_text}")
    if not chrome_runner.exists():
        problems.append("missing Chrome Default profile ChatGPT runner")
    else:
        runner_text = chrome_runner.read_text(encoding="utf-8")
        for required_text in [
            "Default",
            "connectOverCDP",
            "agent-browser",
            "NO_PROXY",
            "restart-chrome",
            "extract-deep-research",
        ]:
            if required_text not in runner_text:
                problems.append(f"chrome_chatgpt_runner missing required text: {required_text}")
    for forbidden_text in [
        "この skill は `--auto-connect` 専用",
        "attach できる Chrome を用意できないなら、この skill は使わず停止する",
        "$HOME/.chrome-cdp-profile",
        "/Applications/Google\\ Chrome.app/Contents/MacOS/Google\\ Chrome",
    ]:
        if forbidden_text in deep_research_skill:
            problems.append(f"deep-research still contains removed browser contract text: {forbidden_text}")
    for forbidden_text in [
        "この skill は `--auto-connect` 専用",
        "attach できる Chrome を用意できないなら、この skill は使わず停止する",
    ]:
        if forbidden_text in gpt_pro_skill:
            problems.append(f"gpt-pro still contains removed fallback text: {forbidden_text}")

    computer_use_skill = (ROOT / "plugins/devkit/skills/computer-use-chatgpt-pro/SKILL.md").read_text(encoding="utf-8")
    for required_text in [
        'allowed-tools: ["Bash", "Read", "mcp__computer_use__*"]',
        "Computer UseでChatGPT Proに質問",
        "汎用のChatGPT Pro検索・調査は既存のgpt-proを使う",
        "agent-browser",
        "CDP",
        "headless",
        "DOM eval",
        "mcp__computer_use__.get_app_state",
        "macOS 以外",
        "自律ループをデフォルトにしない",
    ]:
        if required_text not in computer_use_skill:
            problems.append(f"computer-use-chatgpt-pro missing required contract text: {required_text}")

    for required_text in [
        "/devkit:gpt-pro",
        "$gpt-pro",
        "$computer-use-chatgpt-pro",
        "ブラウザ経由",
        "ChatGPT アプリ経由",
        "Chrome Default profile",
        "chrome_chatgpt_runner.py",
        "Playwright `connectOverCDP`",
    ]:
        if required_text not in readme:
            problems.append(f"README missing ChatGPT Pro routing text: {required_text}")
    if "/devkit:mermaid-show" in readme:
        problems.append("README still lists retired public skill: /devkit:mermaid-show")

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
        entries = manifest_entries(manifest)
        if "dig" in entries:
            problems.append(f"{manifest_name} still syncs Claude-only dig skill to other runtimes")
        if "gpt-pro" not in entries:
            problems.append(f"{manifest_name} missing public gpt-pro entry")
        if "computer-use-chatgpt-pro" not in entries:
            problems.append(f"{manifest_name} missing public computer-use-chatgpt-pro entry")
        if "amazon-search" in entries:
            problems.append(f"{manifest_name} still syncs removed skill: amazon-search")
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
        retired_entries = manifest_entries(retired_block)
        if "gpt-pro" in retired_entries:
            problems.append(f"{retired_name} incorrectly retires active skill: gpt-pro")
        for token in ["amazon-search", "mermaid-show"]:
            if token not in retired_entries:
                problems.append(f"{retired_name} missing retired skill cleanup entry: {token}")
        for token in [
            "dig",
            "dig-core",
            "dig-claude",
            "dig-codex",
            "dig-cursor",
            "dig-opencode",
            "codex-impl",
            "decomposition",
            "devkit-init",
        ]:
            if token not in retired_entries:
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
                        "if (-not ((Get-DevKitRetiredSkillEntries) -contains 'mermaid-show')) { exit 3 }; "
                        "if ((Get-DevKitSkillManifest) -contains 'amazon-search') { exit 4 }; "
                        "if (-not ((Get-DevKitRetiredSkillEntries) -contains 'amazon-search')) { exit 5 }"
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

    js_files: list[str] = []
    for path in (ROOT / "plugins/devkit").rglob("*"):
        rel = path.relative_to(ROOT)
        if any(part in {".venv", "__pycache__"} for part in rel.parts):
            continue
        try:
            if path.is_file() and path.suffix in {".js", ".mjs"}:
                js_files.append(rel.as_posix())
        except OSError:
            continue
    js_files = sorted(js_files)
    if js_files:
        problems.append(f"JavaScript files must be removed from plugins/devkit: {', '.join(js_files)}")

    try:
        run_runtime_smoke_checks()
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.strip() or exc.stdout.strip() or str(exc)
        problems.append(f"runtime sync smoke failed: {detail}")
    try:
        run_update_devkit_argument_smoke_checks()
    except (AssertionError, subprocess.CalledProcessError) as exc:
        if isinstance(exc, subprocess.CalledProcessError):
            detail = exc.stderr.strip() or exc.stdout.strip() or str(exc)
        else:
            detail = str(exc)
        problems.append(f"update-devkit argument smoke failed: {detail}")

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
