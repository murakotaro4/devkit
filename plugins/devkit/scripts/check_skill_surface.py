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
from typing import NamedTuple


ROOT = Path.cwd()
PLUGIN_DIR = ROOT / "plugins/devkit"
EXPECTED_SKILLS = {
    "backlog",
    "catch-up",
    "commit-push",
    "dig-goal",
    "improve-skill",
    "setup",
    "refactor",
    "memory-review",
    "handoff",
}
REQUIRED_PATHS = {
    "plugins/devkit/premises.json",
    "plugins/devkit/skills/setup/scripts/prune_legacy_cursor_sync.py",
    "plugins/devkit/skills/setup/scripts/sync_cursor_skills.py",
    "plugins/devkit/skills/setup/scripts/setup_terminal_font.py",
    "plugins/devkit/statusline/install.js",
    "plugins/devkit/statusline/statusline.js",
    "plugins/devkit/templates/codex/config.shared.toml",
    "plugins/devkit/templates/codex/config.windows.toml",
}
REMOVED_SKILL_DIRS = {
    "codex-search",
    "computer-use-chatgpt-pro",
    "deep-research",
    "discord-ops",
    "discord-rust-server-ops",
    "gpt-pro",
    "repo-maintainer",
    "repo-maintainer-init",
}
REMOVED_PATHS = {
    "plugins/devkit/scripts/chrome_chatgpt_runner.py",
    "plugins/devkit/scripts/repo_maintainer.py",
    "plugins/devkit/scripts/devkit-runtime-sync.sh",
    "plugins/devkit/scripts/devkit-runtime-sync.ps1",
    "plugins/devkit/scripts/devkit-skill-update.ps1",
    "plugins/devkit/.claude-plugin/marketplace.json",
    ".devkit",
}
MIN_PLUGIN_VERSION = (7, 0, 0)
SEMVER_PRERELEASE_IDENT = r"(?:0|[1-9]\d*|[A-Za-z-][0-9A-Za-z-]*)"
SEMVER_BUILD_IDENT = r"(?:[0-9A-Za-z-]+)"
SEMVER_RE = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    rf"(?:-({SEMVER_PRERELEASE_IDENT}(?:\.{SEMVER_PRERELEASE_IDENT})*))?"
    rf"(?:\+({SEMVER_BUILD_IDENT}(?:\.{SEMVER_BUILD_IDENT})*))?$"
)


class UpdateSmokeResult(NamedTuple):
    calls: list[str]
    stdout: str
    returncode: int


def shell_path(path: Path | str) -> str:
    raw = path.as_posix() if isinstance(path, Path) else str(path).replace("\\", "/")
    if len(raw) >= 3 and raw[1:3] == ":/":
        raw = f"/{raw[0].lower()}/{raw[3:]}"
    return json.dumps(raw)


def read_json(rel: str) -> object:
    raw = (ROOT / rel).read_text(encoding="utf-8").lstrip("\ufeff")
    return json.loads(raw)


def parse_semver_tuple(version: object) -> tuple[int, int, int] | None:
    if not isinstance(version, str):
        return None
    match = SEMVER_RE.match(version)
    if not match:
        return None
    return tuple(int(part) for part in match.groups()[:3])


def semver_at_least(version: object, minimum: tuple[int, int, int]) -> bool | None:
    if not isinstance(version, str):
        return None
    match = SEMVER_RE.match(version)
    if not match:
        return None

    numeric = tuple(int(part) for part in match.groups()[:3])
    prerelease = match.group(4)
    if numeric != minimum:
        return numeric > minimum
    return prerelease is None


def write_executable(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def run_checked(cmd: list[str], *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env or os.environ.copy(),
    )


def resolve_bash() -> str:
    bash = shutil.which("bash")
    if not bash:
        raise AssertionError("bash が見つからない: PATH で bash を解決できません")
    return bash


def assert_skill_surface(problems: list[str]) -> None:
    skills_dir = PLUGIN_DIR / "skills"
    actual = {path.name for path in skills_dir.iterdir() if path.is_dir()}
    if actual != EXPECTED_SKILLS:
        problems.append(
            "skills surface mismatch: "
            f"expected={sorted(EXPECTED_SKILLS)} actual={sorted(actual)}"
        )

    for name in sorted(EXPECTED_SKILLS):
        for relpath in ("SKILL.md", "agents/openai.yaml"):
            path = skills_dir / name / relpath
            if not path.is_file():
                problems.append(
                    f"expected skill surface file missing: plugins/devkit/skills/{name}/{relpath}"
                )

    for name in sorted(REMOVED_SKILL_DIRS):
        rel = f"plugins/devkit/skills/{name}"
        if (ROOT / rel).exists():
            problems.append(f"removed skill directory still exists: {rel}")

    for rel in sorted(REMOVED_PATHS):
        if (ROOT / rel).exists():
            problems.append(f"removed path still exists: {rel}")

    for rel in sorted(REQUIRED_PATHS):
        if not (ROOT / rel).is_file():
            problems.append(f"required distribution file missing: {rel}")


def assert_marketplace_manifest(problems: list[str]) -> None:
    manifest = read_json(".claude-plugin/marketplace.json")
    if not isinstance(manifest, dict):
        problems.append("root marketplace manifest is not an object")
        return

    plugins = manifest.get("plugins")
    if not isinstance(plugins, list) or not plugins:
        problems.append("root marketplace manifest has no plugins entry")
        return

    plugin = plugins[0]
    if not isinstance(plugin, dict):
        problems.append("root marketplace plugin entry is not an object")
        return

    source = plugin.get("source")
    if not isinstance(source, str) or not source.strip():
        problems.append("root marketplace source is missing")
        return

    source_dir = (ROOT / source).resolve()
    if not source_dir.is_dir():
        problems.append(f"root marketplace source directory does not exist: {source}")


def assert_no_opencode_in_windows_updater_surface(problems: list[str]) -> None:
    # update-ccx.ps1 の委譲シム廃止(v13)により Windows 実行正本は update-ccx.sh に
    # 一本化された。旧 run_powershell_smoke_checks() が ps1 に対して行っていた
    # OpenCode command surface 検査を、正本となった update-ccx.sh に対して行う。
    target = PLUGIN_DIR / "scripts/update-ccx.sh"
    content = target.read_text(encoding="utf-8")
    if re.search(r"opencode|opencode-ai", content, re.IGNORECASE):
        problems.append(f"{target} contains OpenCode command surface")


FAKE_CODEX = """#!/bin/sh
printf 'codex %s\\n' "$*" >> "$DEVKIT_TEST_CALL_LOG"
if [ "$1" = "--version" ]; then
  echo "codex 0.142.5"
  exit 0
fi
if [ "$1" = "plugin" ] && [ "$2" = "list" ] && [ "$3" = "--json" ]; then
  if [ "${DEVKIT_FAKE_CODEX_INSTALLED:-0}" = "1" ]; then
    printf '{"plugins":[{"name":"devkit","marketplace":"murakotaro4","enabled":%s}]}\\n' "${DEVKIT_FAKE_CODEX_ENABLED:-true}"
  elif [ "${DEVKIT_FAKE_CODEX_AVAILABLE:-0}" = "1" ]; then
    if [ "${DEVKIT_FAKE_CODEX_AVAILABLE_SHAPE:-installed}" = "plugins" ]; then
      printf '{"plugins":[],"available":[{"name":"devkit","marketplace":"murakotaro4"}]}\\n'
    else
      printf '{"installed":[],"available":[{"name":"devkit","marketplace":"murakotaro4"}]}\\n'
    fi
  else
    printf '{"plugins":[]}\\n'
  fi
  exit 0
fi
if [ "$1" = "plugin" ]; then
  exit 0
fi
exit 0
"""


FAKE_CLAUDE = """#!/bin/sh
printf 'claude %s\\n' "$*" >> "$DEVKIT_TEST_CALL_LOG"
if [ "$1" = "--version" ]; then
  echo "claude 0.0.0"
  exit 0
fi
if [ "$1" = "plugin" ] && [ "$2" = "marketplace" ] && [ "$3" = "list" ] && [ "$4" = "--json" ]; then
  if [ "${DEVKIT_FAKE_CLAUDE_LIST_FAIL:-0}" = "1" ]; then
    exit 1
  fi
  if [ "${DEVKIT_FAKE_CLAUDE_MARKETPLACE:-1}" = "1" ]; then
    if [ "${DEVKIT_FAKE_CLAUDE_MARKETPLACE_SHAPE:-ok}" = "ok" ]; then
      printf '[{"name":"murakotaro4","source":"github","repo":"murakotaro4/devkit"}]\\n'
    else
      printf '%s\\n' \
        '[' \
        '  {"name":"murakotaro4","source":"local","repo":"other/devkit"},' \
        '  {"name":"other","source":"github","repo":"murakotaro4/devkit"}' \
        ']'
    fi
  else
    printf '[]\\n'
  fi
  exit 0
fi
if [ "$1" = "plugin" ] && [ "$2" = "list" ] && [ "$3" = "--json" ]; then
  if [ "${DEVKIT_FAKE_CLAUDE_LIST_FAIL:-0}" = "1" ]; then
    exit 1
  fi
  if [ "${DEVKIT_FAKE_CLAUDE_INSTALLED:-1}" = "1" ]; then
    if [ "${DEVKIT_FAKE_CLAUDE_SCOPE:-user}" = "user" ]; then
      printf '[{"id":"devkit@murakotaro4","version":"0.0.0","scope":"user","enabled":true}]\\n'
    else
      printf '%s\\n' \
        '[' \
        '  {"id":"devkit@murakotaro4","version":"0.0.0","scope":"project","enabled":true},' \
        '  {"id":"other@murakotaro4","version":"0.0.0","scope":"user","enabled":true}' \
        ']'
    fi
  else
    printf '[]\\n'
  fi
  exit 0
fi
if [ "$1" = "plugin" ]; then
  exit 0
fi
exit 0
"""


FAKE_TOOL = """#!/bin/sh
printf '%s %s\\n' "$(basename "$0")" "$*" >> "$DEVKIT_TEST_CALL_LOG"
case "$(basename "$0")" in
  curl)
    exit 0
    ;;
  git)
    exit 0
    ;;
esac
exit 0
"""


def prepare_update_smoke_home(home_path: Path) -> Path:
    source_root = home_path / "source"
    (source_root / "plugins").mkdir(parents=True)
    target = source_root / "plugins/devkit"
    try:
        target.symlink_to(PLUGIN_DIR, target_is_directory=True)
    except OSError:
        shutil.copytree(PLUGIN_DIR, target)
    return source_root


def write_codex_config(home_path: Path, body: str) -> None:
    config = home_path / ".codex/config.toml"
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(body, encoding="utf-8")


def run_update_devkit_smoke(
    label: str,
    *,
    config_body: str | None,
    installed: bool,
    enabled: bool = True,
    enabled_value: str | None = None,
    available: bool = False,
    available_shape: str = "installed",
    force_shell_fallback: bool = False,
    claude_marketplace: bool = True,
    claude_marketplace_shape: str = "ok",
    claude_installed: bool = True,
    claude_scope: str = "user",
    claude_list_fail: bool = False,
    expect_success: bool = True,
) -> UpdateSmokeResult:
    with tempfile.TemporaryDirectory(prefix=f"devkit-{label}-home-") as home, tempfile.TemporaryDirectory(
        prefix=f"devkit-{label}-bin-"
    ) as fake_bin:
        home_path = Path(home)
        source_root = prepare_update_smoke_home(home_path)
        if config_body is not None:
            write_codex_config(home_path, config_body)

        fake_bin_path = Path(fake_bin)
        write_executable(fake_bin_path / "codex", FAKE_CODEX)
        write_executable(fake_bin_path / "claude", FAKE_CLAUDE)
        if force_shell_fallback:
            write_executable(fake_bin_path / "python3", "#!/bin/sh\nexit 127\n")
        write_executable(fake_bin_path / "opencode", FAKE_TOOL)
        for tool in ("curl", "git"):
            write_executable(fake_bin_path / tool, FAKE_TOOL)

        call_log = home_path / "tool-calls.log"
        env = os.environ.copy()
        env.update(
            {
                "DEVKIT_SOURCE_ROOT": str(source_root),
                "DEVKIT_TEST_CALL_LOG": str(call_log),
                "DEVKIT_FAKE_CODEX_INSTALLED": "1" if installed else "0",
                "DEVKIT_FAKE_CODEX_ENABLED": enabled_value or ("true" if enabled else "false"),
                "DEVKIT_FAKE_CODEX_AVAILABLE": "1" if available else "0",
                "DEVKIT_FAKE_CODEX_AVAILABLE_SHAPE": available_shape,
                "DEVKIT_FAKE_CLAUDE_MARKETPLACE": "1" if claude_marketplace else "0",
                "DEVKIT_FAKE_CLAUDE_MARKETPLACE_SHAPE": claude_marketplace_shape,
                "DEVKIT_FAKE_CLAUDE_INSTALLED": "1" if claude_installed else "0",
                "DEVKIT_FAKE_CLAUDE_SCOPE": claude_scope,
                "DEVKIT_FAKE_CLAUDE_LIST_FAIL": "1" if claude_list_fail else "0",
                "HOME": home,
                "USERPROFILE": home,
                "PATH": f"{fake_bin}{os.pathsep}{env.get('PATH', '')}",
            }
        )
        result = subprocess.run(
            [resolve_bash(), (PLUGIN_DIR / "scripts/update-ccx.sh").as_posix(), "--devkit-only"],
            cwd=ROOT,
            env=env,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        if expect_success and result.returncode != 0:
            raise subprocess.CalledProcessError(
                result.returncode, result.args, output=result.stdout, stderr=result.stderr
            )
        return UpdateSmokeResult(
            call_log.read_text(encoding="utf-8").splitlines(), result.stdout, result.returncode
        )


def assert_ordered_subset(lines: list[str], expected: list[str], label: str) -> None:
    position = 0
    for expected_line in expected:
        while position < len(lines) and lines[position] != expected_line:
            position += 1
        if position >= len(lines):
            raise AssertionError(f"{label} missing expected command {expected_line!r}: {lines}")
        position += 1


def assert_no_opencode(lines: list[str], label: str) -> None:
    if any(line.startswith("opencode ") for line in lines):
        raise AssertionError(f"{label} invoked opencode: {lines}")
    if any("opencode-ai" in line for line in lines):
        raise AssertionError(f"{label} invoked opencode package update: {lines}")


def assert_default_claude_plugin_update(calls: list[str], label: str) -> None:
    assert_ordered_subset(
        calls,
        [
            "claude plugin marketplace list --json",
            "claude plugin marketplace update murakotaro4",
            "claude plugin list --json",
            "claude plugin update --scope user devkit@murakotaro4",
        ],
        f"{label} Claude plugin",
    )


def run_codex_marketplace_smoke_checks() -> None:
    registered = run_update_devkit_smoke(
        "registered",
        config_body='[marketplaces.murakotaro4]\nsource_type = "git"\nsource = "murakotaro4/devkit"\n',
        installed=True,
    )
    assert_ordered_subset(
        registered.calls,
        [
            "codex plugin marketplace upgrade murakotaro4",
            "codex plugin add devkit@murakotaro4",
        ],
        "registered marketplace",
    )
    if "codex plugin marketplace add murakotaro4/devkit" in registered.calls:
        raise AssertionError(f"registered marketplace unexpectedly added source: {registered}")
    assert_no_opencode(registered.calls, "registered marketplace")
    assert_default_claude_plugin_update(registered.calls, "registered marketplace")

    disabled = run_update_devkit_smoke(
        "disabled",
        config_body='[marketplaces.murakotaro4]\nsource_type = "git"\nsource = "murakotaro4/devkit"\n',
        installed=True,
        enabled=False,
    )
    assert_ordered_subset(
        disabled.calls,
        [
            "codex plugin marketplace upgrade murakotaro4",
            "codex plugin add devkit@murakotaro4",
        ],
        "disabled plugin",
    )
    assert_no_opencode(disabled.calls, "disabled plugin")
    assert_default_claude_plugin_update(disabled.calls, "disabled plugin")

    missing = run_update_devkit_smoke("missing", config_body=None, installed=False, available=True)
    assert_ordered_subset(
        missing.calls,
        [
            "codex plugin marketplace add murakotaro4/devkit",
            "codex plugin marketplace upgrade murakotaro4",
            "codex plugin add devkit@murakotaro4",
        ],
        "missing marketplace",
    )
    assert_no_opencode(missing.calls, "missing marketplace")
    assert_default_claude_plugin_update(missing.calls, "missing marketplace")

    missing_shell_fallback = run_update_devkit_smoke(
        "missing-fallback",
        config_body=None,
        installed=False,
        available=True,
        available_shape="plugins",
        force_shell_fallback=True,
    )
    assert_ordered_subset(
        missing_shell_fallback.calls,
        [
            "codex plugin marketplace add murakotaro4/devkit",
            "codex plugin marketplace upgrade murakotaro4",
            "codex plugin add devkit@murakotaro4",
        ],
        "missing marketplace shell fallback",
    )
    assert_no_opencode(missing_shell_fallback.calls, "missing marketplace shell fallback")
    assert_default_claude_plugin_update(missing_shell_fallback.calls, "missing marketplace shell fallback")

    disabled_shell_fallback = run_update_devkit_smoke(
        "disabled-fallback",
        config_body='[marketplaces.murakotaro4]\nsource_type = "git"\nsource = "murakotaro4/devkit"\n',
        installed=True,
        enabled_value='"false"',
        force_shell_fallback=True,
    )
    assert_ordered_subset(
        disabled_shell_fallback.calls,
        [
            "codex plugin marketplace upgrade murakotaro4",
            "codex plugin add devkit@murakotaro4",
        ],
        "disabled plugin shell fallback",
    )
    assert_no_opencode(disabled_shell_fallback.calls, "disabled plugin shell fallback")
    assert_default_claude_plugin_update(disabled_shell_fallback.calls, "disabled plugin shell fallback")

    local_source = run_update_devkit_smoke(
        "local",
        config_body='[marketplaces.murakotaro4]\nsource_type = "local"\npath = "/tmp/devkit"\n',
        installed=False,
    )
    assert_ordered_subset(
        local_source.calls,
        [
            "codex plugin marketplace remove murakotaro4",
            "codex plugin marketplace add murakotaro4/devkit",
            "codex plugin marketplace upgrade murakotaro4",
            "codex plugin add devkit@murakotaro4",
        ],
        "local marketplace",
    )
    assert_no_opencode(local_source.calls, "local marketplace")
    assert_default_claude_plugin_update(local_source.calls, "local marketplace")


def run_claude_plugin_smoke_checks() -> None:
    replace = run_update_devkit_smoke(
        "claude-marketplace-replace",
        config_body='[marketplaces.murakotaro4]\nsource_type = "git"\nsource = "murakotaro4/devkit"\n',
        installed=True,
        force_shell_fallback=True,
        claude_marketplace_shape="replace",
    )
    assert_ordered_subset(
        replace.calls,
        [
            "claude plugin marketplace list --json",
            "claude plugin marketplace remove --scope user murakotaro4",
            "claude plugin marketplace add --scope user murakotaro4/devkit",
            "claude plugin list --json",
            "claude plugin update --scope user devkit@murakotaro4",
        ],
        "unexpected Claude marketplace replacement",
    )
    if "claude plugin marketplace update murakotaro4" in replace.calls:
        raise AssertionError(f"unexpected Claude marketplace was updated in place: {replace.calls}")

    missing = run_update_devkit_smoke(
        "claude-missing",
        config_body='[marketplaces.murakotaro4]\nsource_type = "git"\nsource = "murakotaro4/devkit"\n',
        installed=True,
        claude_marketplace=False,
        claude_installed=False,
    )
    assert_ordered_subset(
        missing.calls,
        [
            "claude plugin marketplace list --json",
            "claude plugin marketplace add --scope user murakotaro4/devkit",
            "claude plugin list --json",
            "claude plugin install --scope user devkit@murakotaro4",
        ],
        "missing Claude plugin",
    )

    list_failure = run_update_devkit_smoke(
        "claude-list-failure",
        config_body='[marketplaces.murakotaro4]\nsource_type = "git"\nsource = "murakotaro4/devkit"\n',
        installed=True,
        claude_list_fail=True,
        expect_success=False,
    )
    if list_failure.returncode != 1:
        raise AssertionError(f"Claude list failure returned {list_failure.returncode}, expected 1")
    assert_ordered_subset(
        list_failure.calls,
        ["claude plugin marketplace list --json"],
        "Claude list failure",
    )
    if any(line.startswith("claude plugin marketplace update") for line in list_failure.calls):
        raise AssertionError(f"Claude list failure was treated as registered: {list_failure.calls}")

    project_scope_shell_fallback = run_update_devkit_smoke(
        "claude-project-scope-fallback",
        config_body='[marketplaces.murakotaro4]\nsource_type = "git"\nsource = "murakotaro4/devkit"\n',
        installed=True,
        force_shell_fallback=True,
        claude_scope="project",
    )
    assert_ordered_subset(
        project_scope_shell_fallback.calls,
        [
            "claude plugin marketplace list --json",
            "claude plugin marketplace update murakotaro4",
            "claude plugin list --json",
            "claude plugin install --scope user devkit@murakotaro4",
        ],
        "project-scope Claude plugin shell fallback",
    )
    if "claude plugin update --scope user devkit@murakotaro4" in project_scope_shell_fallback.calls:
        raise AssertionError(
            "project-scope Claude plugin was treated as user-installed: "
            f"{project_scope_shell_fallback.calls}"
        )


def run_prune_smoke_checks() -> None:
    if os.name == "nt":
        return

    with tempfile.TemporaryDirectory(prefix="devkit-prune-home-") as home:
        home_path = Path(home)
        legacy_target = PLUGIN_DIR / "skills/dig-goal"
        for root in (
            ".agents/skills",
            ".codex/skills",
            ".agent/skills",
            ".config/opencode/skills",
        ):
            root_path = home_path / root
            root_path.mkdir(parents=True)
            (root_path / "dig").symlink_to(legacy_target, target_is_directory=True)
            (root_path / "custom-keep").mkdir()

        legacy_bin = home_path / ".codex/bin"
        legacy_bin.mkdir(parents=True)
        for name in ("devkit-runtime-sync.sh", "devkit-runtime-sync.ps1", "devkit-skill-update.ps1"):
            (legacy_bin / name).write_text("legacy\n", encoding="utf-8")

        env = os.environ.copy()
        env.update({"HOME": home, "DEVKIT_SOURCE_ROOT": str(ROOT)})
        script = "\n".join(
            [
                "set -euo pipefail",
                f"SCRIPT_DIR={shell_path(PLUGIN_DIR / 'scripts')}",
                f"source {shell_path(PLUGIN_DIR / 'scripts/devkit-lib.sh')}",
                f"prune_legacy_devkit_assets {shell_path(home_path)} {shell_path(ROOT)}",
            ]
        )
        run_checked([resolve_bash(), "-lc", script], env=env)

        for root in (
            ".agents/skills",
            ".codex/skills",
            ".agent/skills",
            ".config/opencode/skills",
        ):
            root_path = home_path / root
            if (root_path / "dig").exists() or (root_path / "dig").is_symlink():
                raise AssertionError(f"legacy skill link was not pruned: {root}/dig")
            if not (root_path / "custom-keep").is_dir():
                raise AssertionError(f"user skill directory was removed: {root}/custom-keep")
        if not (home_path / ".codex/devkit/.migrated-v6").is_file():
            raise AssertionError("migration marker was not written")
        if any((legacy_bin / name).exists() for name in ("devkit-runtime-sync.sh", "devkit-skill-update.ps1")):
            raise AssertionError("legacy bin assets were not pruned")

    with tempfile.TemporaryDirectory(prefix="devkit-prune-marker-home-") as home:
        home_path = Path(home)
        marker = home_path / ".codex/devkit/.migrated-v6"
        marker.parent.mkdir(parents=True)
        marker.write_text("migrated-v6\n", encoding="utf-8")
        managed_skills_root = home_path / ".agent/skills"
        managed_skills_root.mkdir(parents=True)
        for retired_name in ("dig", "goal-prompt"):
            retired_skill = managed_skills_root / retired_name
            retired_skill.mkdir()
            (retired_skill / "SKILL.md").write_text(
                "\n".join(
                    (
                        "---",
                        f'name: "{retired_name}"',
                        "---",
                        "正本は devkit リポジトリの `AGENTS.md`。",
                        "",
                    )
                ),
                encoding="utf-8",
            )
        (managed_skills_root / "custom-keep").mkdir()

        user_skills_root = home_path / ".codex/skills"
        user_skills_root.mkdir(parents=True)
        for retired_name in ("dig", "goal-prompt"):
            user_skill = user_skills_root / retired_name
            user_skill.mkdir()
            (user_skill / "SKILL.md").write_text(
                "\n".join(
                    (
                        "---",
                        f'name: "{retired_name}"',
                        "description: devkit リポジトリの `AGENTS.md` を参考にした独自スキル",
                        "---",
                        "ユーザー所有スキル。",
                        "",
                    )
                ),
                encoding="utf-8",
            )

        env = os.environ.copy()
        env.update({"HOME": home, "DEVKIT_SOURCE_ROOT": str(ROOT)})
        script = "\n".join(
            [
                "set -euo pipefail",
                f"SCRIPT_DIR={shell_path(PLUGIN_DIR / 'scripts')}",
                f"source {shell_path(PLUGIN_DIR / 'scripts/devkit-lib.sh')}",
                f"prune_legacy_devkit_assets {shell_path(home_path)} {shell_path(ROOT)}",
            ]
        )
        run_checked([resolve_bash(), "-lc", script], env=env)
        for retired_name in ("dig", "goal-prompt"):
            if (managed_skills_root / retired_name).exists():
                raise AssertionError(f"retired live skill was not pruned: {retired_name}")
            if not (user_skills_root / retired_name / "SKILL.md").is_file():
                raise AssertionError(f"user-owned same-name skill was pruned: {retired_name}")
        if not (managed_skills_root / "custom-keep").is_dir():
            raise AssertionError("v9 prune removed a user skill directory")
        if not (home_path / ".codex/devkit/.migrated-v9-dig-goal").is_file():
            raise AssertionError("v9 dig-goal migration marker was not written")


def run_legacy_ps1_shim_prune_smoke_checks() -> None:
    # update-ccx.ps1 の委譲シム廃止(v13)の回帰テスト。section_prune_legacy_assets()
    # は devkit-lib.sh の .migrated-v6 marker とは独立に、常時この shim を prune する
    # 必要がある(prune_legacy_devkit_assets 自体は marker があると早期 return するため)。
    # OS_TYPE の判定は実 uname 依存のため、この検証は Windows(Git Bash)上でのみ意味を持つ。
    if os.name != "nt":
        return

    for marker_present in (False, True):
        label = "ps1-shim-marker" if marker_present else "ps1-shim-no-marker"
        with tempfile.TemporaryDirectory(prefix=f"devkit-{label}-home-") as home, tempfile.TemporaryDirectory(
            prefix=f"devkit-{label}-bin-"
        ) as fake_bin:
            home_path = Path(home)
            source_root = prepare_update_smoke_home(home_path)

            codex_bin = home_path / ".codex/bin"
            codex_bin.mkdir(parents=True)
            stale_ps1 = codex_bin / "update-ccx.ps1"
            stale_ps1.write_text("# stale legacy delegating shim\n", encoding="utf-8")

            if marker_present:
                marker_dir = home_path / ".codex/devkit"
                marker_dir.mkdir(parents=True, exist_ok=True)
                (marker_dir / ".migrated-v6").write_text("migrated-v6\n", encoding="utf-8")

            fake_bin_path = Path(fake_bin)
            write_executable(fake_bin_path / "codex", FAKE_CODEX)
            write_executable(fake_bin_path / "claude", FAKE_CLAUDE)
            write_executable(fake_bin_path / "opencode", FAKE_TOOL)
            for tool in ("curl", "git"):
                write_executable(fake_bin_path / tool, FAKE_TOOL)

            call_log = home_path / "tool-calls.log"
            env = os.environ.copy()
            env.update(
                {
                    "DEVKIT_SOURCE_ROOT": str(source_root),
                    "DEVKIT_TEST_CALL_LOG": str(call_log),
                    "DEVKIT_FAKE_CODEX_INSTALLED": "1",
                    "DEVKIT_FAKE_CODEX_ENABLED": "true",
                    "DEVKIT_FAKE_CLAUDE_MARKETPLACE": "1",
                    "DEVKIT_FAKE_CLAUDE_MARKETPLACE_SHAPE": "ok",
                    "DEVKIT_FAKE_CLAUDE_INSTALLED": "1",
                    "DEVKIT_FAKE_CLAUDE_SCOPE": "user",
                    "HOME": home,
                    "USERPROFILE": home,
                    "PATH": f"{fake_bin}{os.pathsep}{env.get('PATH', '')}",
                }
            )
            result = subprocess.run(
                [resolve_bash(), (PLUGIN_DIR / "scripts/update-ccx.sh").as_posix(), "--devkit-only"],
                cwd=ROOT,
                env=env,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            if result.returncode != 0:
                raise AssertionError(
                    f"{label}: update-ccx.sh --devkit-only failed (exit {result.returncode})\n"
                    f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
                )
            if stale_ps1.exists():
                raise AssertionError(f"{label}: stale update-ccx.ps1 was not pruned: {stale_ps1}")


def run_powershell_smoke_checks() -> None:
    pwsh = shutil.which("pwsh")
    if not pwsh:
        return

    command = rf"""
$ErrorActionPreference = "Stop"
$Root = {str(ROOT)!r}
$Tmp = New-Item -ItemType Directory -Path ([IO.Path]::Combine([IO.Path]::GetTempPath(), "devkit-pwsh-" + [Guid]::NewGuid().ToString()))
try {{
  . (Join-Path $Root "plugins/devkit/scripts/devkit-codex-config.ps1")
  $configHome = Join-Path $Tmp.FullName "config-home"
  $configPaths = Get-DevKitCodexConfigPaths -UserHome $configHome
  New-Item -ItemType Directory -Path $configPaths.TemplateRoot -Force | Out-Null
  Copy-Item -LiteralPath (Join-Path $Root "plugins/devkit/templates/codex/config.shared.toml") -Destination $configPaths.SharedTemplatePath -Force
  Copy-Item -LiteralPath (Join-Path $Root "plugins/devkit/templates/codex/config.windows.toml") -Destination $configPaths.WindowsTemplatePath -Force
  Set-Content -LiteralPath $configPaths.TargetPath -Encoding UTF8 -Value "model = `"gpt-5.4`"`nmodel_reasoning_effort = `"xhigh`"`nplan_mode_reasoning_effort = `"xhigh`"`nmodel_context_window = 1000000`nmodel_auto_compact_token_limit = 9000000`n`n[marketplaces.murakotaro4]`nsource_type = `"git`"`nsource = `"murakotaro4/devkit`"`n`n[plugins.`"devkit@murakotaro4`"]`nenabled = true`n"

  $configResult = Install-DevKitCodexConfig -UserHome $configHome -OsName "windows"
  if ([string]::IsNullOrWhiteSpace($configResult.BackupPath)) {{ throw "config backup path missing" }}
  if (-not (Test-Path -LiteralPath $configResult.BackupPath)) {{ throw "config backup file missing" }}
  $backup = Get-Content -LiteralPath $configResult.BackupPath -Raw -Encoding UTF8
  if (-not $backup.Contains('model = "gpt-5.4"')) {{ throw "legacy model pin missing from backup" }}
  if (-not $backup.Contains('model_reasoning_effort = "xhigh"')) {{ throw "legacy model effort missing from backup" }}
  if (-not $backup.Contains('plan_mode_reasoning_effort = "xhigh"')) {{ throw "legacy plan effort missing from backup" }}
  if (-not $backup.Contains('model_context_window = 1000000')) {{ throw "legacy context pin missing from backup" }}
  if (-not $backup.Contains('model_auto_compact_token_limit = 9000000')) {{ throw "legacy auto-compact pin missing from backup" }}
  if (-not $backup.Contains("[marketplaces.murakotaro4]")) {{ throw "marketplace runtime section missing from backup" }}
  if (-not $backup.Contains("[plugins.`"devkit@murakotaro4`"]")) {{ throw "plugin runtime section missing from backup" }}
  if (Test-Path -LiteralPath $configPaths.LocalOverlayPath) {{ throw "legacy pins were moved to local overlay" }}

  $installed = Get-Content -LiteralPath $configPaths.TargetPath -Raw -Encoding UTF8
  if (-not $installed.Contains('model = "gpt-5.6-sol"')) {{ throw "model is not pinned to gpt-5.6-sol" }}
  if ($installed.Contains('model = "gpt-5.4"')) {{ throw "legacy model pin retained" }}
  if ($installed -match '(?m)^model_context_window\s*=') {{ throw "legacy context pin retained" }}
  if ($installed -match '(?m)^model_auto_compact_token_limit\s*=') {{ throw "legacy auto-compact pin retained" }}
  if (-not $installed.Contains('model_reasoning_effort = "medium"')) {{ throw "model effort is not medium" }}
  if (-not $installed.Contains('plan_mode_reasoning_effort = "medium"')) {{ throw "plan effort is not medium" }}
  if ($installed.Contains('model_reasoning_effort = "xhigh"')) {{ throw "legacy model effort retained" }}
  if ($installed.Contains('plan_mode_reasoning_effort = "xhigh"')) {{ throw "legacy plan effort retained" }}
  if ($installed -match '(?i)model_reasoning_effort\s*=\s*"(?:max|ultra)"') {{ throw "unsupported effort retained" }}
  if (-not $installed.Contains('features.multi_agent = true')) {{ throw "multi-agent feature lost" }}
  if (-not $installed.Contains('sandbox = "unelevated"')) {{ throw "Windows sandbox lost" }}
  if (-not $installed.Contains("[marketplaces.murakotaro4]")) {{ throw "marketplace runtime section lost" }}
  if (-not $installed.Contains("[plugins.`"devkit@murakotaro4`"]")) {{ throw "plugin runtime section lost" }}

  $script:TaskLog = New-Object System.Collections.Generic.List[string]
  $script:LegacyTaskPresent = $true
  function Get-ScheduledTask {{ param([string]$TaskName) if ($script:LegacyTaskPresent -and $TaskName -eq "DevKitSkillsDailyUpdate") {{ return [pscustomobject]@{{ TaskName = $TaskName }} }} }}
  function Unregister-ScheduledTask {{ param([string]$TaskName, [switch]$Confirm) $script:TaskLog.Add("unregister:$TaskName") | Out-Null; $script:LegacyTaskPresent = $false }}
  function Register-ScheduledTask {{ param([string]$TaskName) $script:TaskLog.Add("register:$TaskName") | Out-Null }}
  . (Join-Path $Root "plugins/devkit/scripts/devkit-lib.ps1")
  $userHome = Join-Path $Tmp.FullName "home"
  New-Item -ItemType Directory -Path $userHome | Out-Null

  # update-ccx.ps1 の委譲シム廃止(v13)の回帰テスト。marker 不在で 1 回目、
  # marker 実在(1 回目の呼び出しが書き込む)で 2 回目を検証し、両方で prune されることを確認する。
  $legacyPs1Bin = Join-Path $userHome ".codex\bin"
  New-Item -ItemType Directory -Path $legacyPs1Bin -Force | Out-Null
  $legacyPs1Path = Join-Path $legacyPs1Bin "update-ccx.ps1"
  Set-Content -LiteralPath $legacyPs1Path -Encoding UTF8 -Value "# stale legacy delegating shim`n"
  $migratedV6Marker = Join-Path $userHome ".codex\devkit\.migrated-v6"

  Remove-DevKitLegacyAssets -UserHome $userHome -SourceRoot $Root -Logger $null
  if (-not ($script:TaskLog -contains "unregister:DevKitSkillsDailyUpdate")) {{ throw "legacy task was not unregistered" }}
  if (($script:TaskLog | Where-Object {{ $_ -like "register:*" }}).Count -gt 0) {{ throw "new scheduled task was registered" }}
  if (Test-Path -LiteralPath $legacyPs1Path) {{ throw "stale update-ccx.ps1 was not pruned (no marker)" }}
  if (-not (Test-Path -LiteralPath $migratedV6Marker)) {{ throw "migrated-v6 marker was not written after first prune" }}

  Set-Content -LiteralPath $legacyPs1Path -Encoding UTF8 -Value "# stale legacy delegating shim (re-seeded)`n"
  Remove-DevKitLegacyAssets -UserHome $userHome -SourceRoot $Root -Logger $null
  if (Test-Path -LiteralPath $legacyPs1Path) {{ throw "stale update-ccx.ps1 was not pruned (marker present)" }}
}} finally {{
  Remove-Item -LiteralPath $Tmp.FullName -Recurse -Force -ErrorAction SilentlyContinue
}}
"""
    run_checked([pwsh, "-NoProfile", "-Command", command])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", default="B")
    args = parser.parse_args()

    problems: list[str] = []
    assert_skill_surface(problems)
    assert_marketplace_manifest(problems)
    assert_no_opencode_in_windows_updater_surface(problems)
    try:
        run_codex_marketplace_smoke_checks()
    except (AssertionError, subprocess.CalledProcessError) as exc:
        detail = exc.stderr.strip() if isinstance(exc, subprocess.CalledProcessError) else str(exc)
        if isinstance(exc, subprocess.CalledProcessError) and not detail:
            detail = exc.stdout.strip() or str(exc)
        problems.append(f"codex marketplace smoke failed: {detail}")

    try:
        run_claude_plugin_smoke_checks()
    except (AssertionError, subprocess.CalledProcessError) as exc:
        detail = exc.stderr.strip() if isinstance(exc, subprocess.CalledProcessError) else str(exc)
        if isinstance(exc, subprocess.CalledProcessError) and not detail:
            detail = exc.stdout.strip() or str(exc)
        problems.append(f"Claude plugin smoke failed: {detail}")

    try:
        run_prune_smoke_checks()
    except (AssertionError, subprocess.CalledProcessError) as exc:
        detail = exc.stderr.strip() if isinstance(exc, subprocess.CalledProcessError) else str(exc)
        if isinstance(exc, subprocess.CalledProcessError) and not detail:
            detail = exc.stdout.strip() or str(exc)
        problems.append(f"legacy prune smoke failed: {detail}")

    try:
        run_legacy_ps1_shim_prune_smoke_checks()
    except (AssertionError, subprocess.CalledProcessError) as exc:
        detail = exc.stderr.strip() if isinstance(exc, subprocess.CalledProcessError) else str(exc)
        if isinstance(exc, subprocess.CalledProcessError) and not detail:
            detail = exc.stdout.strip() or str(exc)
        problems.append(f"legacy update-ccx.ps1 shim prune smoke failed: {detail}")

    try:
        run_powershell_smoke_checks()
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.strip() or exc.stdout.strip() or str(exc)
        problems.append(f"PowerShell smoke failed: {detail}")

    plugin = read_json("plugins/devkit/.claude-plugin/plugin.json")
    if not isinstance(plugin, dict):
        problems.append("plugin.json is not an object")
    else:
        version_ok = semver_at_least(plugin.get("version"), MIN_PLUGIN_VERSION)
        if version_ok is None:
            problems.append("plugin.json version must be a valid semantic version")
        elif not version_ok:
            problems.append("plugin.json version must be >= 7.0.0")
        description = plugin.get("description")
        if not isinstance(description, str) or not description.strip():
            problems.append("plugin.json description missing")

    if problems:
        print(json.dumps({"phase": args.phase, "problems": problems}, ensure_ascii=False, indent=2))
        return 2

    print(json.dumps({"phase": args.phase, "ok": True}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
