from __future__ import annotations

import json
import os
import shutil
import subprocess
from hashlib import sha256
from pathlib import Path

import pytest

from conftest import require_symlink_support


ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "plugins" / "devkit" / "scripts"


def test_update_ccx_scripts_have_claude_plugin_section():
    shell = (SCRIPTS / "update-ccx.sh").read_text(encoding="utf-8")

    for expected in (
        "=== [Claude Plugin] ===",
        "claude plugin marketplace update murakotaro4",
        "claude plugin marketplace remove --scope user murakotaro4",
        "claude plugin marketplace add --scope user murakotaro4/devkit",
        "claude plugin update --scope user devkit@murakotaro4",
        "claude plugin install --scope user devkit@murakotaro4",
        "/reload-plugins",
    ):
        assert expected in shell


def test_managed_updater_copy_excludes_retired_update_devkit_files():
    shell = (SCRIPTS / "update-ccx.sh").read_text(encoding="utf-8")
    managed_section = shell.split("section_managed_copy()", 1)[1].split(
        "codex_marketplace_section()", 1
    )[0]
    ordered_copy_markers = (
        "for script_name in update-ccx.sh devkit-lib.sh",
        'ensure_managed_file "$plugin_scripts/update-ccx.cmd"',
        "for script_name in devkit-lib.ps1 devkit-setup.ps1 devkit-codex-config.ps1",
        "for script_name in config.shared.toml config.windows.toml",
    )
    positions = [managed_section.index(marker) for marker in ordered_copy_markers]
    assert positions == sorted(positions)
    assert "update-ccx.ps1" not in managed_section

    powershell = (SCRIPTS / "devkit-lib.ps1").read_text(encoding="utf-8")
    managed_function = powershell.split("function Install-DevKitManagedFiles", 1)[1].split(
        "function Test-DevKitPathLooksManaged", 1
    )[0]
    managed_names = managed_function.split("foreach ($fileName in @(", 1)[1].split("))", 1)[0]
    assert '"update-ccx.sh"' in managed_names
    assert '"devkit-lib.sh"' in managed_names
    assert '"update-ccx.cmd"' in managed_names
    assert "update-devkit" not in managed_names
    assert "update-ccx.ps1" not in managed_names


def test_windows_managed_paths_respect_home_without_overwriting_it():
    shell = (SCRIPTS / "update-ccx.sh").read_text(encoding="utf-8")
    shim = shell.split("install_windows_update_shim()", 1)[1].split(
        "install_windows_codex_config()", 1
    )[0]
    config = shell.split("install_windows_codex_config()", 1)[1].split(
        "section_managed_copy()", 1
    )[0]
    managed = shell.split("section_managed_copy()", 1)[1].split(
        "codex_marketplace_section()", 1
    )[0]

    assert "initialize_windows_home" not in shell
    assert 'export HOME=' not in shell
    assert "windows_path_from_posix()" in shell
    assert 'cygpath -w "$input_path"' in shell
    assert 'windows_path_from_posix "$target_command_path"' in shim
    assert "using USERPROFILE fallback" in shim
    assert "DEVKIT_CODEX_CONFIG_SCRIPT" in config
    assert 'windows_path_from_posix "$config_script_path"' in config
    assert 'windows_path_from_posix "$HOME"' in config
    assert 'codex_bin="$HOME/.codex/bin"' in managed
    assert 'install_windows_update_shim "$local_bin/update-ccx.cmd" "$codex_bin/update-ccx.cmd"' in managed
    assert 'install_windows_codex_config "$codex_bin/devkit-codex-config.ps1"' in managed


def test_windows_source_root_state_is_native_and_shell_readers_accept_both_forms():
    shell = (SCRIPTS / "update-ccx.sh").read_text(encoding="utf-8")
    library = (SCRIPTS / "devkit-lib.sh").read_text(encoding="utf-8")
    bootstrap = shell.split("source_devkit_lib_for_update()", 1)[1].split(
        "source_devkit_lib_for_update || exit 1", 1
    )[0]
    persisted_reader = library.split("devkit_read_persisted_source_root()", 1)[1].split(
        "devkit_persist_codex_source_root()", 1
    )[0]
    persisted_writer = library.split("devkit_persist_codex_source_root()", 1)[1].split(
        "devkit_script_checkout_root()", 1
    )[0]

    assert "source_root_path_for_shell()" in shell
    assert bootstrap.count('source_root_path_for_shell "$') == 2
    assert "devkit_source_root_to_shell_path()" in library
    assert 'windows_path_to_posix "$source_root"' in library
    assert 'candidate="$(devkit_source_root_to_shell_path "$candidate" || true)"' in persisted_reader
    assert "devkit_source_root_to_state_path()" in library
    assert 'windows_path_from_posix "$source_root"' in library
    assert 'cygpath -w "$source_root"' in library
    assert 'state_root="$(devkit_source_root_to_state_path "$repo_root" || true)"' in persisted_writer
    assert "persisting POSIX path fallback" in persisted_writer


def test_fnm_noninteractive_environment_is_initialized_before_early_return():
    shell = (SCRIPTS / "update-ccx.sh").read_text(encoding="utf-8")
    resolver = shell.split("resolve_fnm_command()", 1)[1].split(
        "initialize_fnm_environment()", 1
    )[0]
    initializer = shell.split("initialize_fnm_environment()", 1)[1].split("ensure_fnm()", 1)[0]
    ensure = shell.split("ensure_fnm()", 1)[1].split("ensure_nodejs()", 1)[0]

    assert '"$HOME/.local/share/fnm"' in resolver
    assert '"$local_app_data/Microsoft/WinGet/Links"' in resolver
    assert '[[ -z "${FNM_MULTISHELL_PATH:-}" ]]' in initializer
    assert "fnm env --shell bash" in initializer
    assert 'eval "$fnm_environment"' in initializer
    assert 'WARNINGS+=("fnm: non-interactive shell environment initialization failed")' in initializer
    assert ensure.index("resolve_fnm_command") < ensure.index("OK fnm: already installed")
    assert ensure.index("initialize_fnm_environment") < ensure.index("OK fnm: already installed")


def test_updater_self_refresh_defines_all_retired_name_prune_targets():
    shell = (SCRIPTS / "update-ccx.sh").read_text(encoding="utf-8")
    powershell = (SCRIPTS / "devkit-lib.ps1").read_text(encoding="utf-8")
    for name in ("update-devkit.sh", "update-devkit.ps1", "update-devkit.cmd"):
        assert name in shell
        assert name in powershell
    assert '"$local_bin/update-devkit"' in shell
    assert '"$local_bin/update-devkit.cmd"' in shell
    assert '(Join-Path $localBin "update-devkit")' in powershell
    assert '(Join-Path $localBin "update-devkit.cmd")' in powershell


def test_updater_self_refresh_propagates_prune_failures():
    shell = (SCRIPTS / "update-ccx.sh").read_text(encoding="utf-8")
    managed_section = shell.split("section_managed_copy()", 1)[1].split(
        "codex_marketplace_section()", 1
    )[0]
    prune_loop = managed_section.split("local legacy_path", 1)[1]
    assert 'rm -f -- "$legacy_path"' in prune_loop
    assert 'if [[ -e "$legacy_path" || -L "$legacy_path" ]]' in prune_loop
    assert 'echo "PRUNE_FAILED: $legacy_path" >&2' in prune_loop
    assert 'ERRORS+=("DevKit managed file: failed to prune $legacy_path")' in prune_loop
    assert "return 1" in prune_loop

    powershell = (SCRIPTS / "devkit-lib.ps1").read_text(encoding="utf-8")
    remove_helper = powershell.split("function Remove-DevKitPathOrThrow", 1)[1].split(
        "function Get-DevKitLinkTargetPath", 1
    )[0]
    assert "Remove-Item -LiteralPath $Path" in remove_helper
    assert "if (Test-DevKitPathPresent -Path $Path)" in remove_helper
    assert 'throw "PRUNE_FAILED: $Path"' in remove_helper

    for function_name, next_function in (
        ("Remove-DevKitManagedSkillLinks", "Remove-DevKitLegacyCommandFile"),
        ("Remove-DevKitLegacyCommandFile", "Remove-DevKitLegacyScheduledTask"),
        ("Remove-DevKitLegacyAssets", None),
    ):
        function_body = powershell.split(f"function {function_name}", 1)[1]
        if next_function is not None:
            function_body = function_body.split(f"function {next_function}", 1)[0]
        assert "Remove-Item" not in function_body

    scheduled_task = powershell.split("function Remove-DevKitLegacyScheduledTask", 1)[1].split(
        "function Clear-DevKitMarketplaceHooks", 1
    )[0]
    assert "Unregister-ScheduledTask" in scheduled_task
    assert scheduled_task.count("Get-ScheduledTask") == 3
    assert 'throw "PRUNE_FAILED: scheduled task DevKitSkillsDailyUpdate"' in scheduled_task


def test_windows_shell_migration_removes_legacy_task_before_v6_marker_path():
    shell = (SCRIPTS / "update-ccx.sh").read_text(encoding="utf-8")
    cleanup = shell.split("remove_windows_legacy_scheduled_task()", 1)[1].split(
        "section_managed_copy()", 1
    )[0]
    migration = shell.split("section_prune_legacy_assets()", 1)[1].split(
        "resolve_devkit_python()", 1
    )[0]

    for expected in (
        "powershell.exe -NoProfile -ExecutionPolicy Bypass",
        ". $env:DEVKIT_POWERSHELL_LIB",
        "Remove-DevKitLegacyScheduledTask",
        "legacy scheduled task cleanup failed; continuing migration",
        'WARNINGS+=("DevKit migration: legacy scheduled task cleanup failed")',
    ):
        assert expected in cleanup
    assert '[[ "$OS_TYPE" == "windows" && ! -f "$HOME/.codex/devkit/.migrated-v6" ]]' in migration
    assert migration.index("remove_windows_legacy_scheduled_task") < migration.index(
        "prune_legacy_devkit_assets"
    )


def test_devkit_python_resolver_probes_supported_commands_in_order():
    shell = (SCRIPTS / "update-ccx.sh").read_text(encoding="utf-8")
    resolver = shell.split("resolve_devkit_python()", 1)[1].split(
        "section_prune_cursor_sync()", 1
    )[0]
    section = shell.split("section_prune_cursor_sync()", 1)[1].split("main()", 1)[0]

    probes = (
        "python3 -c",
        "python -c",
        "py -3 -c",
    )
    positions = [resolver.index(probe) for probe in probes]
    assert positions == sorted(positions)
    assert resolver.count("sys.version_info >= (3, 10)") == 3
    assert 'if [[ -z "$DEVKIT_PYTHON_KIND" ]]; then' in section
    assert 'local -a python_command=("$DEVKIT_PYTHON_KIND")' in section
    assert 'python_command=(py -3)' in section
    assert '"${python_command[@]}"' in section
    assert "command -v " + "python3" not in section
    assert "resolve_devkit_python" not in section


def test_json_state_readers_use_resolved_devkit_python_kind_not_command_v():
    shell = (SCRIPTS / "update-ccx.sh").read_text(encoding="utf-8")

    marketplace_state = shell.split("claude_marketplace_state()", 1)[1].split(
        "claude_plugin_devkit_state()", 1
    )[0]
    plugin_state = shell.split("claude_plugin_devkit_state()", 1)[1].split(
        "section_codex_plugin()", 1
    )[0]

    for body in (marketplace_state, plugin_state):
        assert "command -v " + "python3" not in body
        assert 'DEVKIT_PYTHON_KIND' in body
        assert '"${python_command[@]}" -c' in body
        assert "' 2>/dev/null)\"; then" in body

    # codex_plugin_devkit_state() is unreferenced dead code and must be removed entirely.
    assert "codex_plugin_devkit_state" not in shell

    main_body = shell.split("main()", 1)[1]
    cli_only_blocks = main_body.split('if [[ "$CLI_ONLY" != true ]]; then')
    assert len(cli_only_blocks) == 3
    second_cli_only_block = cli_only_blocks[2]
    assert 'DEVKIT_PYTHON_KIND="$(resolve_devkit_python || true)"' in second_cli_only_block
    assert second_cli_only_block.index(
        'DEVKIT_PYTHON_KIND="$(resolve_devkit_python || true)"'
    ) < second_cli_only_block.index("section_prune_legacy_assets")


def test_devkit_python_resolver_ignores_windows_store_stub_via_execution_probe():
    shell = (SCRIPTS / "update-ccx.sh").read_text(encoding="utf-8")
    resolver_body = shell.split("resolve_devkit_python()", 1)[1].split(
        "section_prune_cursor_sync()", 1
    )[0]

    script = (
        "resolve_devkit_python()" + resolver_body
        + "\n"
        + "python3() {\n"
        + '    echo "Python was not found; run without arguments to install from the Microsoft Store, or disable this shortcut from Settings > Apps > Advanced app settings > App execution aliases." >&2\n'
        + "    return 49\n"
        + "}\n"
        + "python() { return 0; }\n"
        + "resolve_devkit_python\n"
    )

    result = subprocess.run(
        [bash_path(), "-c", script],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert result.returncode == 0, result.stderr + result.stdout
    assert result.stdout.strip() == "python"
    assert result.stderr == ""


def test_v9_migration_contract_is_present_in_both_libraries():
    shell = (SCRIPTS / "devkit-lib.sh").read_text(encoding="utf-8")
    powershell = (SCRIPTS / "devkit-lib.ps1").read_text(encoding="utf-8")

    retired_names = ("dig", "goal-" + "prompt")
    for text in (shell, powershell):
        assert ".migrated-v9-dig-goal" in text
        for retired_name in retired_names:
            assert retired_name in text
    shell_migration = shell.split("prune_legacy_devkit_assets()", 1)[1]
    assert shell_migration.index('if [[ ! -f "$v9_marker" ]]') < shell_migration.index(
        'if [[ -f "$marker" ]]'
    )
    powershell_migration = powershell.split("function Remove-DevKitLegacyAssets", 1)[1]
    assert powershell_migration.index("if (-not (Test-Path -LiteralPath $v9MarkerPath))") < (
        powershell_migration.index("if (Test-Path -LiteralPath $markerPath)")
    )
    shell_provenance = shell.split("devkit_v9_retired_skill_entry_is_managed()", 1)[1].split(
        "devkit_prune_v9_retired_skill_dirs()", 1
    )[0]
    assert "devkit_path_is_devkit_source" in shell_provenance
    assert "devkit リポジトリの `AGENTS.md`" in shell_provenance
    powershell_provenance = powershell.split(
        "function Test-DevKitV9RetiredSkillEntryManaged", 1
    )[1].split("function Remove-DevKitV9RetiredSkillDirs", 1)[0]
    assert "Test-DevKitPathLooksManaged" in powershell_provenance
    assert "devkit リポジトリの `AGENTS.md`" in powershell_provenance
    powershell_reparse = powershell.split("function Test-DevKitReparsePoint", 1)[1].split(
        "function Test-DevKitFileContentEqual", 1
    )[0]
    assert "Test-DevKitPathPresent" in powershell_reparse
    assert "Test-Path" not in powershell_reparse


def test_v9_migration_contract_runtime_pwsh_probe(tmp_path):
    pwsh = shutil.which("pwsh")
    if not pwsh:
        pytest.skip("[tool:pwsh] pwsh is not installed")

    # One runtime probe covers marker-missing prune/create and marker-present no-op.
    home = tmp_path / "pwsh-home"
    marker_dir = home / ".codex" / "devkit"
    marker_dir.mkdir(parents=True)
    (marker_dir / ".migrated-v6").write_text("migrated-v6\n", encoding="utf-8")
    retired_name = "goal-" + "prompt"
    retired = home / ".codex" / "skills" / retired_name
    retired.mkdir(parents=True)
    (retired / "SKILL.md").write_text(
        f'---\nname: "{retired_name}"\n---\n正本は devkit リポジトリの `AGENTS.md`。\n',
        encoding="utf-8",
    )
    user_skill = home / ".codex" / "skills" / "dig"
    user_skill.mkdir(parents=True)
    (user_skill / "SKILL.md").write_text(
        '---\nname: "dig"\ndescription: devkit リポジトリの `AGENTS.md` を参考\n---\n'
        "ユーザー所有スキル。\n",
        encoding="utf-8",
    )
    duplicate_name_user_skill = home / ".agent" / "skills" / "dig"
    duplicate_name_user_skill.mkdir(parents=True)
    (duplicate_name_user_skill / "SKILL.md").write_text(
        '---\nname: "dig"\nname: [custom]\n---\n'
        "本文で devkit リポジトリの `AGENTS.md` を参照。\n",
        encoding="utf-8",
    )
    powershell_path = str(SCRIPTS / "devkit-lib.ps1").replace("'", "''")
    home_path = str(home).replace("'", "''")
    root_path = str(ROOT).replace("'", "''")
    invoke = (
        f". '{powershell_path}'; "
        f"Remove-DevKitLegacyAssets -UserHome '{home_path}' -SourceRoot '{root_path}' "
        "-Logger {}"
    )

    first = subprocess.run(
        [pwsh, "-NoProfile", "-Command", invoke],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert first.returncode == 0, first.stderr + first.stdout
    assert not retired.exists()
    assert (user_skill / "SKILL.md").is_file()
    assert (duplicate_name_user_skill / "SKILL.md").is_file()
    assert (marker_dir / ".migrated-v9-dig-goal").is_file()

    sentinel = home / ".codex" / "skills" / retired_name / "sentinel"
    sentinel.parent.mkdir(parents=True)
    sentinel.write_text("keep\n", encoding="utf-8")
    second = subprocess.run(
        [pwsh, "-NoProfile", "-Command", invoke],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert second.returncode == 0, second.stderr + second.stdout
    assert sentinel.is_file()


def test_v9_shell_migration_prunes_once_and_writes_marker(tmp_path):
    home = tmp_path / "home"
    marker_dir = home / ".codex" / "devkit"
    marker_dir.mkdir(parents=True)
    (marker_dir / ".migrated-v6").write_text("migrated-v6\n", encoding="utf-8")
    retired_paths = []
    # These directories intentionally model the retired live-skill surface.
    for root in (
        home / ".agents" / "skills",
        home / ".codex" / "skills",
        home / ".agent" / "skills",
        home / ".config" / "opencode" / "skills",
    ):
        for name in ("dig", "goal-" + "prompt"):
            path = root / name
            path.mkdir(parents=True)
            (path / "SKILL.md").write_text(
                f'---\nname: "{name}"\n---\n正本は devkit リポジトリの `AGENTS.md`。\n',
                encoding="utf-8",
            )
            retired_paths.append(path)

    command = (
        f'source "{SCRIPTS / "devkit-lib.sh"}"; '
        f'prune_legacy_devkit_assets "{home}" "{ROOT}"'
    )
    result = subprocess.run(
        [bash_path(), "-c", command],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert result.returncode == 0, result.stderr + result.stdout
    assert (marker_dir / ".migrated-v9-dig-goal").is_file()
    assert all(not path.exists() for path in retired_paths)


def test_v9_shell_migration_preserves_unmanaged_same_name_skills(tmp_path):
    home = tmp_path / "home"
    marker_dir = home / ".codex" / "devkit"
    marker_dir.mkdir(parents=True)
    (marker_dir / ".migrated-v6").write_text("migrated-v6\n", encoding="utf-8")
    user_skill_files = []
    skills_root = home / ".codex" / "skills"
    for name in ("dig", "goal-" + "prompt"):
        skill_file = skills_root / name / "SKILL.md"
        skill_file.parent.mkdir(parents=True)
        if name == "dig":
            content = (
                '---\nname: "dig"\n'
                'description: devkit リポジトリの `AGENTS.md` を参考\n---\n'
                "ユーザー所有スキル。\n"
            )
        else:
            content = (
                f'---\nname: "{name}"\nname: [custom]\n---\n'
                "本文で devkit リポジトリの `AGENTS.md` を参照。\n"
            )
        skill_file.write_text(content, encoding="utf-8")
        user_skill_files.append(skill_file)

    command = (
        f'source "{SCRIPTS / "devkit-lib.sh"}"; '
        f'prune_legacy_devkit_assets "{home}" "{ROOT}"'
    )
    result = subprocess.run(
        [bash_path(), "-c", command],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert result.returncode == 0, result.stderr + result.stdout
    assert (marker_dir / ".migrated-v9-dig-goal").is_file()
    assert all(skill_file.is_file() for skill_file in user_skill_files)


def test_v9_shell_migration_handles_dangling_symlink_provenance(tmp_path):
    # dangling 検証には「devkit source 配下だが実在しないパス」が必要。
    # v14 で撤去済みの dig-goal ディレクトリを使う(dig / goal-prompt は実在するため不可)。
    # symlink 権限に依存しない前提チェックのため、skip ガードより前で常に検証する。
    managed_target = ROOT / "plugins" / "devkit" / "skills" / "dig-goal"
    assert not managed_target.exists()

    require_symlink_support()

    home = tmp_path / "home"
    marker_dir = home / ".codex" / "devkit"
    marker_dir.mkdir(parents=True)
    (marker_dir / ".migrated-v6").write_text("migrated-v6\n", encoding="utf-8")

    managed_link = home / ".agents" / "skills" / "dig"
    managed_link.parent.mkdir(parents=True)
    try:
        managed_link_target = os.path.relpath(managed_target, start=managed_link.parent)
    except ValueError:
        # Windows runners may place the repo and tmp_path on different drives.
        # An absolute dangling target still verifies that DevKit-source provenance is pruned.
        managed_link_target = managed_target
    managed_link.symlink_to(managed_link_target, target_is_directory=True)

    unmanaged_link = home / ".codex" / "skills" / ("goal-" + "prompt")
    unmanaged_link.parent.mkdir(parents=True)
    unmanaged_target = tmp_path / "unrelated-user-skills" / ("goal-" + "prompt")
    assert not unmanaged_target.exists()
    unmanaged_link.symlink_to(unmanaged_target, target_is_directory=True)

    command = (
        f'source "{SCRIPTS / "devkit-lib.sh"}"; '
        f'prune_legacy_devkit_assets "{home}" "{ROOT}"'
    )
    result = subprocess.run(
        [bash_path(), "-c", command],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert result.returncode == 0, result.stderr + result.stdout
    assert not managed_link.is_symlink()
    assert unmanaged_link.is_symlink()
    assert (marker_dir / ".migrated-v9-dig-goal").is_file()


def test_v9_shell_migration_is_noop_when_marker_exists(tmp_path):
    home = tmp_path / "home"
    marker_dir = home / ".codex" / "devkit"
    marker_dir.mkdir(parents=True)
    (marker_dir / ".migrated-v6").write_text("migrated-v6\n", encoding="utf-8")
    (marker_dir / ".migrated-v9-dig-goal").write_text(
        "migrated-v9-dig-goal\n", encoding="utf-8"
    )
    sentinel = home / ".codex" / "skills" / "dig" / "sentinel"
    sentinel.parent.mkdir(parents=True)
    sentinel.write_text("keep\n", encoding="utf-8")

    command = (
        f'source "{SCRIPTS / "devkit-lib.sh"}"; '
        f'prune_legacy_devkit_assets "{home}" "{ROOT}"'
    )
    result = subprocess.run(
        [bash_path(), "-c", command],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert result.returncode == 0, result.stderr + result.stdout
    assert sentinel.is_file()


def bash_path() -> str:
    bash = shutil.which("bash")
    if not bash:
        raise AssertionError("bash が見つからない: PATH で bash を解決できません")
    return str(Path(bash).resolve())


def normalize_git_bash_path(value: str) -> Path:
    """Git Bash が出力したパス文字列を、ネイティブ Path として比較可能な形へ正規化する。

    POSIX では文字列比較がそのまま成立するため素通しする。Windows では Git Bash が
    HOME 等を POSIX パス表記(例: /c/Users/...)へ変換して出力するため、bash 経由の
    cygpath -w でネイティブ Windows パスへ変換してから比較する。
    """
    stripped = value.strip()
    if os.name != "nt":
        return Path(stripped)

    result = subprocess.run(
        [bash_path(), "-c", 'cygpath -w "$1"', "_", stripped],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode != 0 or not result.stdout.strip():
        raise AssertionError(
            f"cygpath -w によるパス正規化に失敗した: input={stripped!r} "
            f"returncode={result.returncode} stderr={result.stderr!r}"
        )
    return Path(result.stdout.strip())


def test_source_root_state_round_trips_windows_and_legacy_posix_forms(tmp_path):
    home = tmp_path / "home"
    repo_root = tmp_path / "checkout"
    (home / ".codex" / "devkit").mkdir(parents=True)
    (repo_root / "plugins" / "devkit").mkdir(parents=True)

    probe = r'''
source "$1"
repo_root="$2"
user_home="$3"
uname() { printf '%s\n' 'MINGW64_NT-10.0'; }
windows_path_to_posix() {
  case "$1" in
    'C:\checkout') printf '%s\n' "$repo_root" ;;
    "$repo_root") printf '%s\n' "$repo_root" ;;
    *) return 1 ;;
  esac
}
windows_path_from_posix() {
  [[ "$1" == "$repo_root" ]] || return 1
  printf '%s\n' 'C:\checkout'
}
state_file="$(devkit_codex_source_root_state_file "$user_home")"
printf '%s\n' 'C:\checkout' >"$state_file"
windows_read="$(devkit_read_persisted_source_root "$user_home")"
printf '%s\n' "$repo_root" >"$state_file"
posix_read="$(devkit_read_persisted_source_root "$user_home")"
[[ -n "$windows_read" && "$windows_read" == "$posix_read" ]] || exit 20
[[ -d "$windows_read/plugins/devkit" ]] || exit 21
devkit_persist_codex_source_root "$user_home" "$repo_root"
printf '%s\n%s\n%s\n' "$windows_read" "$posix_read" "$(tr -d '\r\n' <"$state_file")"
'''
    result = subprocess.run(
        [
            bash_path(),
            "-c",
            probe,
            "source-root-probe",
            (SCRIPTS / "devkit-lib.sh").as_posix(),
            repo_root.as_posix(),
            home.as_posix(),
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert result.returncode == 0, result.stderr + result.stdout
    windows_read, posix_read, persisted = result.stdout.splitlines()
    assert windows_read
    assert windows_read == posix_read
    assert persisted == r"C:\checkout"


def test_update_ccx_sh_bootstraps_missing_lib_from_persisted_source_root(tmp_path):
    home = tmp_path / "home"
    codex_bin = home / ".codex" / "bin"
    state_dir = home / ".codex" / "devkit"
    codex_bin.mkdir(parents=True)
    state_dir.mkdir(parents=True)
    (state_dir / "source-root.txt").write_text(f"{ROOT}\n", encoding="utf-8")
    shutil.copyfile(SCRIPTS / "update-ccx.sh", codex_bin / "update-ccx.sh")

    env = os.environ.copy()
    env["HOME"] = str(home)

    result = subprocess.run(
        [bash_path(), (codex_bin / "update-ccx.sh").as_posix(), "--version"],
        env=env,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert result.returncode == 0, result.stderr + result.stdout
    assert (codex_bin / "devkit-lib.sh").is_file()


def test_update_ccx_sh_bootstraps_missing_lib_from_default_checkout(tmp_path):
    require_symlink_support()
    home = tmp_path / "home"
    codex_bin = home / ".codex" / "bin"
    default_checkout = home / "cursor" / "devkit"
    codex_bin.mkdir(parents=True)
    default_checkout.parent.mkdir(parents=True)
    default_checkout.symlink_to(ROOT, target_is_directory=True)
    shutil.copyfile(SCRIPTS / "update-ccx.sh", codex_bin / "update-ccx.sh")

    env = os.environ.copy()
    env["HOME"] = str(home)

    result = subprocess.run(
        [bash_path(), (codex_bin / "update-ccx.sh").as_posix(), "--version"],
        env=env,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert result.returncode == 0, result.stderr + result.stdout
    assert (codex_bin / "devkit-lib.sh").is_file()


def test_update_ccx_sh_ignores_stale_persisted_source_root(tmp_path):
    require_symlink_support()
    home = tmp_path / "home"
    codex_bin = home / ".codex" / "bin"
    state_dir = home / ".codex" / "devkit"
    default_checkout = home / "cursor" / "devkit"
    codex_bin.mkdir(parents=True)
    state_dir.mkdir(parents=True)
    default_checkout.parent.mkdir(parents=True)
    default_checkout.symlink_to(ROOT, target_is_directory=True)
    (state_dir / "source-root.txt").write_text(f"{tmp_path / 'missing'}\n", encoding="utf-8")
    shutil.copyfile(SCRIPTS / "update-ccx.sh", codex_bin / "update-ccx.sh")

    env = os.environ.copy()
    env["HOME"] = str(home)

    result = subprocess.run(
        [bash_path(), (codex_bin / "update-ccx.sh").as_posix(), "--version"],
        env=env,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert result.returncode == 0, result.stderr + result.stdout
    assert (codex_bin / "devkit-lib.sh").is_file()


def test_update_ccx_sh_prefers_default_checkout_over_existing_stale_persisted_root(tmp_path):
    require_symlink_support()
    home = tmp_path / "home"
    codex_bin = home / ".codex" / "bin"
    state_dir = home / ".codex" / "devkit"
    default_checkout = home / "cursor" / "devkit"
    stale_root = tmp_path / "stale"
    stale_scripts = stale_root / "plugins" / "devkit" / "scripts"
    codex_bin.mkdir(parents=True)
    state_dir.mkdir(parents=True)
    default_checkout.parent.mkdir(parents=True)
    stale_scripts.mkdir(parents=True)
    default_checkout.symlink_to(ROOT, target_is_directory=True)
    (stale_scripts / "devkit-lib.sh").write_text("return 42\n", encoding="utf-8")
    (state_dir / "source-root.txt").write_text(f"{stale_root}\n", encoding="utf-8")
    shutil.copyfile(SCRIPTS / "update-ccx.sh", codex_bin / "update-ccx.sh")

    env = os.environ.copy()
    env["HOME"] = str(home)

    result = subprocess.run(
        [bash_path(), (codex_bin / "update-ccx.sh").as_posix(), "--version"],
        env=env,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert result.returncode == 0, result.stderr + result.stdout
    assert (codex_bin / "devkit-lib.sh").read_text(encoding="utf-8") != "return 42\n"


def test_update_ccx_sh_exports_bootstrap_source_root_before_sourcing_lib(tmp_path):
    home = tmp_path / "home"
    codex_bin = home / ".codex" / "bin"
    default_checkout = home / "cursor" / "devkit"
    default_scripts = default_checkout / "plugins" / "devkit" / "scripts"
    codex_bin.mkdir(parents=True)
    default_scripts.mkdir(parents=True)
    (default_scripts / "devkit-lib.sh").write_text(
        'printf "%s\\n" "$DEVKIT_SOURCE_ROOT" > "$HOME/selected-root.txt"\n',
        encoding="utf-8",
    )
    shutil.copyfile(SCRIPTS / "update-ccx.sh", codex_bin / "update-ccx.sh")

    env = os.environ.copy()
    env["HOME"] = str(home)

    result = subprocess.run(
        [bash_path(), (codex_bin / "update-ccx.sh").as_posix(), "--version"],
        env=env,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert result.returncode == 0, result.stderr + result.stdout
    assert normalize_git_bash_path(
        (home / "selected-root.txt").read_text(encoding="utf-8")
    ) == default_checkout


def test_update_ccx_sh_exports_normal_source_root_before_sourcing_existing_lib(tmp_path):
    home = tmp_path / "home"
    codex_bin = home / ".codex" / "bin"
    default_checkout = home / "cursor" / "devkit"
    default_scripts = default_checkout / "plugins" / "devkit" / "scripts"
    codex_bin.mkdir(parents=True)
    default_scripts.mkdir(parents=True)
    (codex_bin / "devkit-lib.sh").write_text(
        'printf "%s\\n" "$DEVKIT_SOURCE_ROOT" > "$HOME/selected-root.txt"\n',
        encoding="utf-8",
    )
    (default_scripts / "devkit-lib.sh").write_text("# default lib marker\n", encoding="utf-8")
    shutil.copyfile(SCRIPTS / "update-ccx.sh", codex_bin / "update-ccx.sh")

    env = os.environ.copy()
    env["HOME"] = str(home)

    result = subprocess.run(
        [bash_path(), (codex_bin / "update-ccx.sh").as_posix(), "--version"],
        env=env,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert result.returncode == 0, result.stderr + result.stdout
    assert normalize_git_bash_path(
        (home / "selected-root.txt").read_text(encoding="utf-8")
    ) == default_checkout


def test_update_ccx_sh_bootstraps_from_existing_source_root(tmp_path):
    home = tmp_path / "home"
    codex_bin = home / ".codex" / "bin"
    caller_source_root = tmp_path / "caller-source"
    caller_scripts = caller_source_root / "plugins" / "devkit" / "scripts"
    codex_bin.mkdir(parents=True)
    caller_scripts.mkdir(parents=True)
    (caller_scripts / "devkit-lib.sh").write_text(
        'printf "%s\\n" "$DEVKIT_SOURCE_ROOT" > "$HOME/selected-root.txt"\n',
        encoding="utf-8",
    )
    shutil.copyfile(SCRIPTS / "update-ccx.sh", codex_bin / "update-ccx.sh")

    env = os.environ.copy()
    env["HOME"] = str(home)
    env["DEVKIT_SOURCE_ROOT"] = str(caller_source_root)

    result = subprocess.run(
        [bash_path(), (codex_bin / "update-ccx.sh").as_posix(), "--version"],
        env=env,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert result.returncode == 0, result.stderr + result.stdout
    assert (codex_bin / "devkit-lib.sh").is_file()
    assert normalize_git_bash_path(
        (home / "selected-root.txt").read_text(encoding="utf-8")
    ) == caller_source_root


def test_update_ccx_sh_preserves_existing_source_root(tmp_path):
    home = tmp_path / "home"
    codex_bin = home / ".codex" / "bin"
    default_checkout = home / "cursor" / "devkit"
    default_scripts = default_checkout / "plugins" / "devkit" / "scripts"
    caller_source_root = tmp_path / "caller-source"
    codex_bin.mkdir(parents=True)
    default_scripts.mkdir(parents=True)
    caller_source_root.mkdir()
    (codex_bin / "devkit-lib.sh").write_text(
        'printf "%s\\n" "$DEVKIT_SOURCE_ROOT" > "$HOME/selected-root.txt"\n',
        encoding="utf-8",
    )
    (default_scripts / "devkit-lib.sh").write_text("# default lib marker\n", encoding="utf-8")
    shutil.copyfile(SCRIPTS / "update-ccx.sh", codex_bin / "update-ccx.sh")

    env = os.environ.copy()
    env["HOME"] = str(home)
    env["DEVKIT_SOURCE_ROOT"] = str(caller_source_root)

    result = subprocess.run(
        [bash_path(), (codex_bin / "update-ccx.sh").as_posix(), "--version"],
        env=env,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert result.returncode == 0, result.stderr + result.stdout
    assert normalize_git_bash_path(
        (home / "selected-root.txt").read_text(encoding="utf-8")
    ) == caller_source_root


def test_windows_updater_cmd_launcher_has_independent_git_bash_contract():
    # update-ccx.ps1 の委譲シムは v13 で廃止された。Windows の実行正本は
    # update-ccx.cmd (Git for Windows Bash launcher) 経由の update-ccx.sh のみ。
    cmd = (SCRIPTS / "update-ccx.cmd").read_text(encoding="utf-8")

    cmd_search = (
        r"%ProgramFiles%\Git\bin\bash.exe",
        r"%ProgramFiles(x86)%\Git\bin\bash.exe",
        "where git.exe",
        r"%~dp1..\bin\bash.exe",
    )
    positions = [cmd.index(item) for item in cmd_search]
    assert positions == sorted(positions)

    assert cmd.index(r"%~dp0update-ccx.sh") < cmd.index("call :resolve_update_script")
    cmd_fallback = cmd.rsplit(":resolve_update_script", 1)[1]
    assert cmd_fallback.index(r"%HOME%") < cmd_fallback.index(r"%USERPROFILE%")
    assert cmd_fallback.index(r"%USERPROFILE%") < cmd_fallback.index(
        r".codex\devkit\source-root.txt"
    )

    assert r"System32\bash.exe" not in cmd
    assert "update-ccx.ps1" not in cmd
    assert '"%DEVKIT_BASH%" "%DEVKIT_UPDATE_SH%" %*' in cmd
    assert "exit /b %ERRORLEVEL%" in cmd


def test_update_ccx_ps1_shim_is_retired():
    assert not (SCRIPTS / "update-ccx.ps1").exists()


@pytest.mark.skipif(os.name != "nt", reason="[platform] Windows launcher runtime smoke")
def test_update_ccx_cmd_uses_source_root_fallback_when_adjacent_shell_is_missing(tmp_path):
    bash_candidates = [
        Path(os.environ.get("ProgramFiles", "")) / "Git/bin/bash.exe",
        Path(os.environ.get("ProgramFiles(x86)", "")) / "Git/bin/bash.exe",
    ]
    git = shutil.which("git.exe")
    if git:
        bash_candidates.append(Path(git).parent.parent / "bin/bash.exe")
    if not any(candidate.is_file() for candidate in bash_candidates):
        pytest.skip("[tool:bash] Git for Windows bash is not installed")

    home = tmp_path / "home"
    installed_bin = home / ".codex" / "bin"
    state_dir = home / ".codex" / "devkit"
    source_root = tmp_path / "checkout"
    source_scripts = source_root / "plugins" / "devkit" / "scripts"
    installed_bin.mkdir(parents=True)
    state_dir.mkdir(parents=True)
    source_scripts.mkdir(parents=True)
    shutil.copyfile(SCRIPTS / "update-ccx.cmd", installed_bin / "update-ccx.cmd")
    (state_dir / "source-root.txt").write_text(f"{source_root}\n", encoding="utf-8")
    marker_path = source_root / "called.txt"
    (source_scripts / "update-ccx.sh").write_text(
        '#!/bin/bash\nprintf "%s\\n" "$1" > "$(dirname "$0")/../../../called.txt"\n',
        encoding="utf-8",
    )

    env = os.environ.copy()
    env["HOME"] = str(home)
    env["USERPROFILE"] = str(tmp_path / "different-profile")
    result = subprocess.run(
        ["cmd.exe", "/d", "/c", str(installed_bin / "update-ccx.cmd"), "sentinel"],
        env=env,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert result.returncode == 0, result.stderr + result.stdout
    assert marker_path.read_text(encoding="utf-8") == "sentinel\n"


def _bash_path() -> str:
    bash = shutil.which("bash")
    if not bash:
        raise AssertionError("bash が見つからない: PATH で bash を解決できません")
    return str(Path(bash).resolve())


def _shell_function(name: str, next_name: str) -> str:
    shell = (SCRIPTS / "update-ccx.sh").read_text(encoding="utf-8")
    body = shell.split(name + "()", 1)[1].split("\n}\n\n" + next_name + "()", 1)[0]
    return name + "()" + body + "\n}\n"




def _claude_mem_port_helpers() -> str:
    shell = (SCRIPTS / "update-ccx.sh").read_text(encoding="utf-8")
    start = shell.index("claude_mem_bootstrap_dir()")
    end = shell.index("\nclaude_mem_worker_healthy()")
    return shell[start:end]


def _claude_mem_resolve_helpers() -> str:
    shell = (SCRIPTS / "update-ccx.sh").read_text(encoding="utf-8")
    start = shell.index("claude_mem_version_sort_key()")
    end = shell.index("\nclaude_mem_expected_version()")
    return shell[start:end]


def _uid_fallback_port() -> str:
    result = subprocess.run(
        [
            _bash_path(),
            "-c",
            "uid=$(id -u 2>/dev/null) || uid=''; "
            "if [[ \"$uid\" =~ ^[0-9]+$ ]]; then echo $((37700 + (uid % 100))); else echo 37777; fi",
        ],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return result.stdout.strip()


def _install_claude_mem_cache_version(
    home: Path, version: str, *, orphaned: bool = False
) -> Path:
    cache_root = home / ".claude" / "plugins" / "cache" / "thedotmack" / "claude-mem"
    install = cache_root / version
    scripts = install / "scripts"
    scripts.mkdir(parents=True)
    if orphaned:
        (install / ".orphaned_at").write_text("1\n", encoding="utf-8")
    pkg_version = version
    (install / "package.json").write_text(
        json.dumps({"name": "claude-mem-plugin", "version": pkg_version}),
        encoding="utf-8",
    )
    _write_exec(scripts / "bun-runner.js", "#!/usr/bin/env node\n")
    (scripts / "worker-service.cjs").write_text("// stub\n", encoding="utf-8")
    return install


def _claude_mem_helpers_source() -> str:
    shell = (SCRIPTS / "update-ccx.sh").read_text(encoding="utf-8")
    start = shell.index("claude_mem_cache_root()")
    end = shell.index("\nsection_prune_legacy_assets()")
    return shell[start:end]


def _write_exec(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8", newline="\n")
    path.chmod(path.stat().st_mode | 0o111)


def _prepare_claude_mem_home(
    home: Path,
    *,
    version: str = "13.13.1",
    orphaned: bool = False,
    package_version: str | None = None,
    settings: object | None = ...,
    consecutive_failures: int | None = None,
    marker: bool = False,
    extra_fields: dict | None = None,
    data_dir: Path | None = None,
) -> Path:
    mem_home = data_dir if data_dir is not None else (home / ".claude-mem")
    mem_home.mkdir(parents=True)
    cache_root = home / ".claude" / "plugins" / "cache" / "thedotmack" / "claude-mem"
    install = cache_root / version
    scripts = install / "scripts"
    scripts.mkdir(parents=True)
    if orphaned:
        (install / ".orphaned_at").write_text("1\n", encoding="utf-8")
    pkg_version = version if package_version is None else package_version
    (install / "package.json").write_text(
        json.dumps({"name": "claude-mem-plugin", "version": pkg_version}),
        encoding="utf-8",
    )
    _write_exec(
        scripts / "bun-runner.js",
        "#!/usr/bin/env node\n"
        "const fs = require('fs');\n"
        "const log = process.env.CLAUDE_MEM_RESTART_LOG;\n"
        "if (log) fs.appendFileSync(log, process.argv.slice(2).join(' ') + '\\n');\n"
        "if (process.env.CLAUDE_MEM_RESTART_FAIL === '1') process.exit(1);\n",
    )
    (scripts / "worker-service.cjs").write_text("// stub\n", encoding="utf-8")
    if settings is not ...:
        if settings is not None:
            (mem_home / "settings.json").write_text(
                settings if isinstance(settings, str) else json.dumps(settings),
                encoding="utf-8",
            )
    else:
        (mem_home / "settings.json").write_text(
            json.dumps({"CLAUDE_MEM_WORKER_PORT": "37777"}),
            encoding="utf-8",
        )
    if consecutive_failures is not None:
        state_dir = mem_home / "state"
        state_dir.mkdir(parents=True)
        payload = {"consecutiveFailures": consecutive_failures, "lastFailureAt": 99}
        if extra_fields:
            payload.update(extra_fields)
        (state_dir / "hook-failures.json").write_text(
            json.dumps(payload),
            encoding="utf-8",
        )
    if marker:
        (mem_home / ".worker-start-attempted").write_text("1\n", encoding="utf-8")
    return install


def _run_claude_mem_section(
    tmp_path: Path,
    *,
    home: Path,
    health_bodies: list[str] | None = None,
    health_fail_times: int = 0,
    restart_fail: bool = False,
    hide_bun: bool = False,
    hide_curl: bool = False,
    hide_node: bool = False,
    os_type: str = "posix",
    path_convert_fail: bool = False,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    restart_log = tmp_path / "restart.log"
    health_log = tmp_path / "health.log"
    health_bodies = list(health_bodies or [])

    real_node = shutil.which("node")
    assert real_node, "system node is required for claude-mem repair tests"

    fail_left = tmp_path / "health-fail-left"
    fail_left.write_text(str(health_fail_times), encoding="utf-8")
    idx_file = tmp_path / "health-idx"
    idx_file.write_text("0", encoding="utf-8")
    bodies_file = tmp_path / "health-bodies.txt"
    bodies_file.write_text(
        "\n".join(health_bodies) + ("\n" if health_bodies else ""),
        encoding="utf-8",
    )

    curl_fn = ""
    if not hide_curl:
        curl_fn = "\n".join(
            [
                "curl() {",
                f'  echo "$*" >> "{health_log.as_posix()}"',
                f'  fail_left_file="{fail_left.as_posix()}"',
                '  if [[ -f "$fail_left_file" ]]; then',
                '    left="$(<"$fail_left_file")"',
                '    if [[ "$left" -gt 0 ]]; then',
                '      printf "%s\\n" "$((left - 1))" >"$fail_left_file"',
                "      return 22",
                "    fi",
                "  fi",
                f'  bodies="{bodies_file.as_posix()}"',
                f'  idx_file="{idx_file.as_posix()}"',
                "  idx=0",
                '  [[ -f "$idx_file" ]] && idx="$(<"$idx_file")"',
                '  mapfile -t lines <"$bodies"',
                '  body="${lines[$idx]-}"',
                '  printf "%s\\n" "$((idx + 1))" >"$idx_file"',
                '  if [[ -z "$body" ]]; then return 22; fi',
                '  printf "%s\\n" "$body"',
                "  return 0",
                "}",
                "",
            ]
        )

    bun_fn = ""
    if not hide_bun:
        bun_fn = "bun() { return 0; }\n"

    node_fn = ""
    if hide_node:
        node_fn = "node() { return 127; }\n"
    else:
        node_fn = (
            "node() {\n"
            f'  "{Path(real_node).as_posix()}" "$@"\n'
            "}\n"
        )

    helpers = _claude_mem_helpers_source()
    probe = (
        f"OS_TYPE={json.dumps(os_type)}\n"
        "WARNINGS=()\n"
        "ERRORS=()\n"
        + node_fn
        + curl_fn
        + bun_fn
        + "windows_path_from_posix() {\n"
        '  if [[ "$CLAUDE_MEM_PATH_CONVERT_FAIL" == 1 ]]; then return 1; fi\n'
        '  printf \'C:\\\\converted\\\\%s\\n\' "${1##*/}"\n'
        "}\n"
        + helpers
        + "\n"
        "section_claude_mem_repair\n"
        'printf "warnings:%s\\n" "${#WARNINGS[@]}"\n'
        'printf "errors:%s\\n" "${#ERRORS[@]}"\n'
        'if ((${#WARNINGS[@]} > 0)); then printf "warning0:%s\\n" "${WARNINGS[0]}"; fi\n'
    )

    path_entries: list[str] = []
    for tool in ("bash", "sort", "ls", "rm", "dirname", "basename", "uname", "cygpath"):
        located = shutil.which(tool)
        if located:
            path_entries.append(str(Path(located).resolve().parent))
    seen: set[str] = set()
    filtered_path: list[str] = []
    for entry in path_entries + os.environ.get("PATH", "").split(os.pathsep):
        if not entry or entry in seen:
            continue
        seen.add(entry)
        if hide_bun and (
            (Path(entry) / "bun").exists() or (Path(entry) / "bun.exe").exists()
        ):
            continue
        filtered_path.append(entry)

    env = {
        **os.environ,
        "HOME": str(home),
        "PATH": os.pathsep.join(filtered_path),
        "CLAUDE_MEM_RESTART_LOG": str(restart_log),
        "CLAUDE_MEM_PATH_CONVERT_FAIL": "1" if path_convert_fail else "0",
    }
    env.pop("CLAUDE_MEM_WORKER_PORT", None)
    env.pop("CLAUDE_MEM_DATA_DIR", None)
    if extra_env:
        env.update(extra_env)
    if restart_fail:
        env["CLAUDE_MEM_RESTART_FAIL"] = "1"

    probe_path = tmp_path / "claude-mem-repair-probe.sh"
    probe_path.write_text(probe, encoding="utf-8", newline="\n")
    return subprocess.run(
        [_bash_path(), str(probe_path.as_posix())],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        cwd=str(tmp_path),
    )


def test_claude_mem_repair_main_wiring_and_heading():
    shell = (SCRIPTS / "update-ccx.sh").read_text(encoding="utf-8")
    assert "=== [Claude Mem Worker] ===" in shell
    assert "section_claude_mem_repair()" in shell
    main = shell.split("main()", 1)[1]
    second_cli_only = main.split('if [[ "$CLI_ONLY" != true ]]; then')[2]
    assert "section_claude_mem_repair" in second_cli_only
    assert second_cli_only.index("section_claude_plugin") < second_cli_only.index(
        "section_claude_mem_repair"
    )
    assert main.count("section_claude_mem_repair") == 1


def test_claude_mem_repair_skips_when_not_installed(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    result = _run_claude_mem_section(tmp_path, home=home)
    assert result.returncode == 0, result.stderr + result.stdout
    assert "SKIP" in result.stdout
    assert "warnings:0" in result.stdout
    assert "errors:0" in result.stdout


def test_claude_mem_worker_port_fallbacks(tmp_path):
    home = tmp_path / "home space"
    _prepare_claude_mem_home(home, settings=None)
    helpers = _claude_mem_port_helpers()
    # uid ベース fallback は非 Windows 経路で検証する(Windows は MSYS UID を使わない)
    linux_helpers = "OS_TYPE=linux\n" + helpers
    uid_port = _uid_fallback_port()
    env_base = {
        k: v
        for k, v in os.environ.items()
        if k not in ("CLAUDE_MEM_WORKER_PORT", "CLAUDE_MEM_DATA_DIR")
    }
    env_base["HOME"] = str(home)
    for label, settings, expected in (
        ("missing", None, uid_port),
        ("broken", "{", uid_port),
        ("oob", {"CLAUDE_MEM_WORKER_PORT": 99999}, uid_port),
        ("string", {"CLAUDE_MEM_WORKER_PORT": "37777"}, "37777"),
        ("number", {"CLAUDE_MEM_WORKER_PORT": 37777}, "37777"),
    ):
        mem = home / ".claude-mem"
        settings_path = mem / "settings.json"
        if settings is None:
            settings_path.unlink(missing_ok=True)
        elif isinstance(settings, str):
            settings_path.write_text(settings, encoding="utf-8")
        else:
            settings_path.write_text(json.dumps(settings), encoding="utf-8")
        result = subprocess.run(
            [_bash_path(), "-c", linux_helpers + "\nclaude_mem_worker_port\n"],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=env_base,
        )
        assert result.returncode == 0, f"{label}: {result.stderr}"
        assert result.stdout.strip() == expected, label

    # Windows: id -u が数値でも 37777(process.getuid 不可時の既定)
    win_helpers = "OS_TYPE=windows\n" + helpers
    settings_path = home / ".claude-mem" / "settings.json"
    settings_path.unlink(missing_ok=True)
    result = subprocess.run(
        [_bash_path(), "-c", win_helpers + "\nclaude_mem_worker_port\n"],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env_base,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "37777"


def test_claude_mem_worker_port_env_overrides_settings(tmp_path):
    home = tmp_path / "home"
    _prepare_claude_mem_home(home, settings={"CLAUDE_MEM_WORKER_PORT": 37777})
    helpers = _claude_mem_port_helpers()
    result = subprocess.run(
                    [_bash_path(), "-c", helpers + "\nclaude_mem_worker_port\n"],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={
            **{
                k: v
                for k, v in os.environ.items()
                if k not in ("CLAUDE_MEM_WORKER_PORT", "CLAUDE_MEM_DATA_DIR")
            },
            "HOME": str(home),
            "CLAUDE_MEM_WORKER_PORT": "12345",
        },
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "12345"


def test_claude_mem_worker_port_invalid_env_does_not_fall_back(tmp_path):
    home = tmp_path / "home"
    _prepare_claude_mem_home(home, settings={"CLAUDE_MEM_WORKER_PORT": 37777})
    helpers = _claude_mem_port_helpers()
    env_base = {
        **{
            k: v
            for k, v in os.environ.items()
            if k not in ("CLAUDE_MEM_WORKER_PORT", "CLAUDE_MEM_DATA_DIR")
        },
        "HOME": str(home),
    }
    for bad_port in ("abc", "0", "99999", "-1"):
        result = subprocess.run(
            [_bash_path(), "-c", helpers + "\nclaude_mem_worker_port\n"],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            env={**env_base, "CLAUDE_MEM_WORKER_PORT": bad_port},
        )
        assert result.returncode != 0, bad_port

def test_claude_mem_data_dir_override_and_tilde(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    poison = home / ".claude-mem"
    poison.mkdir()
    (poison / "settings.json").write_text(
        '{"CLAUDE_MEM_WORKER_PORT": 99999}', encoding="utf-8"
    )
    (poison / ".worker-start-attempted").write_text("poison\n", encoding="utf-8")
    poison_state = poison / "state"
    poison_state.mkdir()
    (poison_state / "hook-failures.json").write_text(
        json.dumps({"consecutiveFailures": 99}), encoding="utf-8"
    )

    custom = home / "custom-mem"
    custom.mkdir()
    (custom / "settings.json").write_text(
        json.dumps({"CLAUDE_MEM_WORKER_PORT": 37777}), encoding="utf-8"
    )

    custom_abs = tmp_path / "override-mem"
    _prepare_claude_mem_home(
        home,
        data_dir=custom_abs,
        consecutive_failures=3,
        marker=True,
    )

    helpers = _claude_mem_port_helpers()
    env_base = {
        **{
            k: v
            for k, v in os.environ.items()
            if k not in ("CLAUDE_MEM_WORKER_PORT", "CLAUDE_MEM_DATA_DIR")
        },
        "HOME": str(home),
    }

    result = subprocess.run(
                    [_bash_path(), "-c", helpers + "\nclaude_mem_worker_port\n"],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**env_base, "CLAUDE_MEM_DATA_DIR": "~/custom-mem"},
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "37777"

    result = subprocess.run(
                    [_bash_path(), "-c", helpers + "\nclaude_mem_data_dir\n"],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**env_base, "CLAUDE_MEM_DATA_DIR": "~/custom-mem"},
    )
    assert result.returncode == 0, result.stderr
    assert normalize_git_bash_path(result.stdout) == custom

    assert (poison / ".worker-start-attempted").read_text(encoding="utf-8") == "poison\n"
    assert (
        json.loads(
            (poison_state / "hook-failures.json").read_text(encoding="utf-8")
        )["consecutiveFailures"]
        == 99
    )

    body = json.dumps({"status": "ok", "version": "13.13.1"})
    result = _run_claude_mem_section(
        tmp_path,
        home=home,
        health_bodies=[body],
        extra_env={"CLAUDE_MEM_DATA_DIR": str(custom_abs)},
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert not (custom_abs / ".worker-start-attempted").exists()
    payload = json.loads(
        (custom_abs / "state" / "hook-failures.json").read_text(encoding="utf-8")
    )
    assert payload["consecutiveFailures"] == 0
    assert (poison / ".worker-start-attempted").exists()
    assert (
        json.loads(
            (poison_state / "hook-failures.json").read_text(encoding="utf-8")
        )["consecutiveFailures"]
        == 99
    )





def test_claude_mem_data_dir_from_default_settings_top_level(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    custom = home / "from-settings"
    custom.mkdir()
    (custom / "settings.json").write_text(
        json.dumps({"CLAUDE_MEM_WORKER_PORT": 11111}), encoding="utf-8"
    )
    default_mem = home / ".claude-mem"
    default_mem.mkdir()
    (default_mem / "settings.json").write_text(
        json.dumps({
            "CLAUDE_MEM_DATA_DIR": str(custom),
            "CLAUDE_MEM_WORKER_PORT": 37771,
        }),
        encoding="utf-8",
    )
    helpers = _claude_mem_port_helpers()
    env = {
        **{
            k: v
            for k, v in os.environ.items()
            if k not in ("CLAUDE_MEM_WORKER_PORT", "CLAUDE_MEM_DATA_DIR")
        },
        "HOME": str(home),
    }
    result = subprocess.run(
        [_bash_path(), "-c", helpers + "\nclaude_mem_data_dir\n"],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
    )
    assert result.returncode == 0, result.stderr
    assert normalize_git_bash_path(result.stdout) == custom
    # port は bootstrap(~/.claude-mem)の settings から読む(custom の 11111 ではない)
    result = subprocess.run(
        [_bash_path(), "-c", helpers + "\nclaude_mem_worker_port\n"],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "37771"

def test_claude_mem_data_dir_from_default_settings_env_object(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    custom = home / "from-env-object"
    custom.mkdir()
    (custom / "settings.json").write_text(
        json.dumps({"CLAUDE_MEM_WORKER_PORT": 11111}), encoding="utf-8"
    )
    default_mem = home / ".claude-mem"
    default_mem.mkdir()
    (default_mem / "settings.json").write_text(
        json.dumps({
            "env": {
                "CLAUDE_MEM_DATA_DIR": str(custom),
                "CLAUDE_MEM_WORKER_PORT": 37772,
            }
        }),
        encoding="utf-8",
    )
    helpers = _claude_mem_port_helpers()
    env = {
        **{
            k: v
            for k, v in os.environ.items()
            if k not in ("CLAUDE_MEM_WORKER_PORT", "CLAUDE_MEM_DATA_DIR")
        },
        "HOME": str(home),
    }
    result = subprocess.run(
        [_bash_path(), "-c", helpers + "\nclaude_mem_data_dir\n"],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
    )
    assert result.returncode == 0, result.stderr
    assert normalize_git_bash_path(result.stdout) == custom
    result = subprocess.run(
        [_bash_path(), "-c", helpers + "\nclaude_mem_worker_port\n"],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "37772"

def test_claude_mem_data_dir_env_overrides_settings(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    from_settings = home / "from-settings"
    from_settings.mkdir()
    from_env = home / "from-env"
    from_env.mkdir()
    (from_env / "settings.json").write_text(
        json.dumps({"CLAUDE_MEM_WORKER_PORT": 37773}), encoding="utf-8"
    )
    default_mem = home / ".claude-mem"
    default_mem.mkdir()
    (default_mem / "settings.json").write_text(
        json.dumps({
            "CLAUDE_MEM_DATA_DIR": str(from_settings),
            "CLAUDE_MEM_WORKER_PORT": 11111,
        }),
        encoding="utf-8",
    )
    helpers = _claude_mem_port_helpers()
    env = {
        **{
            k: v
            for k, v in os.environ.items()
            if k not in ("CLAUDE_MEM_WORKER_PORT", "CLAUDE_MEM_DATA_DIR")
        },
        "HOME": str(home),
        "CLAUDE_MEM_DATA_DIR": str(from_env),
    }
    result = subprocess.run(
        [_bash_path(), "-c", helpers + "\nclaude_mem_data_dir\n"],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
    )
    assert result.returncode == 0, result.stderr
    assert normalize_git_bash_path(result.stdout) == from_env
    # env DATA_DIR あり → port もその bootstrap dir の settings から読む
    result = subprocess.run(
        [_bash_path(), "-c", helpers + "\nclaude_mem_worker_port\n"],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "37773"

def test_claude_mem_repair_invalid_env_port_skips_unchanged(tmp_path):
    home = tmp_path / "home"
    _prepare_claude_mem_home(
        home,
        consecutive_failures=3,
        marker=True,
        extra_fields={"kept": "yes"},
    )
    body = json.dumps({"status": "ok", "version": "13.13.1"})
    result = _run_claude_mem_section(
        tmp_path,
        home=home,
        health_bodies=[body],
        extra_env={"CLAUDE_MEM_WORKER_PORT": "abc"},
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert "invalid CLAUDE_MEM_WORKER_PORT" in result.stdout
    assert (home / ".claude-mem" / ".worker-start-attempted").exists()
    payload = json.loads(
        (home / ".claude-mem" / "state" / "hook-failures.json").read_text(encoding="utf-8")
    )
    assert payload["consecutiveFailures"] == 3
    assert payload["kept"] == "yes"
    assert "warnings:1" in result.stdout
    assert not (tmp_path / "restart.log").exists()


def test_claude_mem_repair_marker_uses_bootstrap_under_settings_datadir(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    custom = home / "custom-mem"
    custom.mkdir()
    (custom / ".worker-start-attempted").write_text("custom-marker\n", encoding="utf-8")
    (custom / "state").mkdir()
    (custom / "state" / "hook-failures.json").write_text(
        json.dumps({"consecutiveFailures": 3, "kept": "yes"}), encoding="utf-8"
    )
    _prepare_claude_mem_home(
        home,
        settings={
            "CLAUDE_MEM_DATA_DIR": str(custom),
            "CLAUDE_MEM_WORKER_PORT": 37777,
        },
        marker=True,
    )
    body = json.dumps({"status": "ok", "version": "13.13.1"})
    result = _run_claude_mem_section(tmp_path, home=home, health_bodies=[body])
    assert result.returncode == 0, result.stderr + result.stdout
    assert "Clearing stale claude-mem hook failure state" in result.stdout
    assert not (home / ".claude-mem" / ".worker-start-attempted").exists()
    assert (custom / ".worker-start-attempted").read_text(encoding="utf-8") == "custom-marker\n"
    payload = json.loads(
        (custom / "state" / "hook-failures.json").read_text(encoding="utf-8")
    )
    assert payload["consecutiveFailures"] == 0
    assert payload["kept"] == "yes"


def test_claude_mem_settings_json_bom_is_accepted(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    custom = home / "bom-custom"
    custom.mkdir()
    default_mem = home / ".claude-mem"
    default_mem.mkdir()
    bom = chr(0xFEFF)
    (default_mem / "settings.json").write_text(
        bom + json.dumps({
            "CLAUDE_MEM_DATA_DIR": str(custom),
            "CLAUDE_MEM_WORKER_PORT": 37774,
        }),
        encoding="utf-8",
    )
    helpers = _claude_mem_port_helpers()
    env = {
        **{
            k: v
            for k, v in os.environ.items()
            if k not in ("CLAUDE_MEM_WORKER_PORT", "CLAUDE_MEM_DATA_DIR")
        },
        "HOME": str(home),
    }
    result = subprocess.run(
        [_bash_path(), "-c", helpers + "\nclaude_mem_data_dir\n"],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
    )
    assert result.returncode == 0, result.stderr
    assert normalize_git_bash_path(result.stdout) == custom
    result = subprocess.run(
        [_bash_path(), "-c", helpers + "\nclaude_mem_worker_port\n"],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "37774"


def test_claude_mem_repair_healthy_same_version_no_restart(tmp_path):
    home = tmp_path / "home"
    _prepare_claude_mem_home(home, consecutive_failures=0)
    body = json.dumps({"status": "ok", "version": "13.13.1"})
    result = _run_claude_mem_section(tmp_path, home=home, health_bodies=[body])
    assert result.returncode == 0, result.stderr + result.stdout
    assert "OK claude-mem worker v13.13.1 is healthy" in result.stdout
    assert "warnings:0" in result.stdout
    assert "errors:0" in result.stdout
    assert not (tmp_path / "restart.log").exists()


def test_claude_mem_repair_healthy_clears_marker_and_counter_only(tmp_path):
    home = tmp_path / "home"
    _prepare_claude_mem_home(
        home,
        consecutive_failures=3,
        marker=True,
        extra_fields={"kept": "yes"},
    )
    body = json.dumps({"status": "ok", "version": "13.13.1"})
    result = _run_claude_mem_section(tmp_path, home=home, health_bodies=[body])
    assert result.returncode == 0, result.stderr + result.stdout
    assert "Clearing stale claude-mem hook failure state" in result.stdout
    assert not (home / ".claude-mem" / ".worker-start-attempted").exists()
    payload = json.loads(
        (home / ".claude-mem" / "state" / "hook-failures.json").read_text(encoding="utf-8")
    )
    assert payload["consecutiveFailures"] == 0
    assert payload["lastFailureAt"] == 0
    assert payload["kept"] == "yes"
    assert not (tmp_path / "restart.log").exists()
    assert "warnings:0" in result.stdout
    assert "errors:0" in result.stdout


def test_claude_mem_repair_restarts_once_on_version_mismatch(tmp_path):
    home = tmp_path / "home"
    _prepare_claude_mem_home(home, consecutive_failures=2)
    bodies = [
        json.dumps({"status": "ok", "version": "13.12.4"}),
        json.dumps({"status": "ok", "version": "13.13.1"}),
    ]
    result = _run_claude_mem_section(tmp_path, home=home, health_bodies=bodies)
    assert result.returncode == 0, result.stderr + result.stdout
    assert "Repairing claude-mem worker" in result.stdout
    restart_log = (tmp_path / "restart.log").read_text(encoding="utf-8").strip().splitlines()
    assert len(restart_log) == 1
    assert restart_log[0].endswith("worker-service.cjs restart")
    payload = json.loads(
        (home / ".claude-mem" / "state" / "hook-failures.json").read_text(encoding="utf-8")
    )
    assert payload["consecutiveFailures"] == 0
    assert "warnings:0" in result.stdout
    assert "errors:0" in result.stdout


def test_claude_mem_repair_restarts_once_when_unreachable(tmp_path):
    home = tmp_path / "home"
    install = _prepare_claude_mem_home(home, consecutive_failures=1, marker=True)
    bodies = [json.dumps({"status": "ok", "version": "13.13.1"})]
    result = _run_claude_mem_section(
        tmp_path,
        home=home,
        health_bodies=bodies,
        health_fail_times=1,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert "Repairing claude-mem worker" in result.stdout
    restart_log = (tmp_path / "restart.log").read_text(encoding="utf-8").strip().splitlines()
    assert len(restart_log) == 1
    assert not (home / ".claude-mem" / ".worker-start-attempted").exists()
    assert install.is_dir()


def test_claude_mem_repair_bun_missing_leaves_state(tmp_path):
    home = tmp_path / "home"
    _prepare_claude_mem_home(home, consecutive_failures=4, marker=True)
    result = _run_claude_mem_section(tmp_path, home=home, hide_bun=True)
    assert result.returncode == 0, result.stderr + result.stdout
    assert "warnings:1" in result.stdout
    assert "errors:0" in result.stdout
    assert (home / ".claude-mem" / ".worker-start-attempted").exists()
    payload = json.loads(
        (home / ".claude-mem" / "state" / "hook-failures.json").read_text(encoding="utf-8")
    )
    assert payload["consecutiveFailures"] == 4


def test_claude_mem_repair_restart_failure_leaves_counter(tmp_path):
    home = tmp_path / "home"
    _prepare_claude_mem_home(home, consecutive_failures=2, marker=True)
    result = _run_claude_mem_section(
        tmp_path,
        home=home,
        health_fail_times=1,
        restart_fail=True,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert "warnings:1" in result.stdout
    assert "errors:0" in result.stdout
    assert "manual recovery" in result.stdout
    payload = json.loads(
        (home / ".claude-mem" / "state" / "hook-failures.json").read_text(encoding="utf-8")
    )
    assert payload["consecutiveFailures"] == 2
    # cooldown marker is cleared before restart attempt
    assert not (home / ".claude-mem" / ".worker-start-attempted").exists()


def test_claude_mem_repair_rehealth_failure_leaves_counter(tmp_path):
    home = tmp_path / "home"
    _prepare_claude_mem_home(home, consecutive_failures=5)
    result = _run_claude_mem_section(
        tmp_path,
        home=home,
        health_fail_times=2,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert "warnings:1" in result.stdout
    assert "errors:0" in result.stdout
    assert "manual recovery" in result.stdout
    payload = json.loads(
        (home / ".claude-mem" / "state" / "hook-failures.json").read_text(encoding="utf-8")
    )
    assert payload["consecutiveFailures"] == 5


def test_claude_mem_repair_skips_orphaned_cache_and_prefers_latest(tmp_path):
    home = tmp_path / "home"
    _prepare_claude_mem_home(home, version="13.13.1")
    older = home / ".claude" / "plugins" / "cache" / "thedotmack" / "claude-mem" / "13.12.4"
    scripts = older / "scripts"
    scripts.mkdir(parents=True)
    (older / ".orphaned_at").write_text("1\n", encoding="utf-8")
    (older / "package.json").write_text(
        json.dumps({"version": "13.12.4"}), encoding="utf-8"
    )
    (scripts / "bun-runner.js").write_text("//\n", encoding="utf-8")
    (scripts / "worker-service.cjs").write_text("//\n", encoding="utf-8")
    helpers = _claude_mem_resolve_helpers()
    result = subprocess.run(
        [
            _bash_path(),
            "-c",
            helpers
            + "\n"
            + 'claude_mem_resolve_active_install "$HOME/.claude/plugins/cache/thedotmack/claude-mem"\n',
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, "HOME": str(home)},
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert result.stdout.strip().endswith("13.13.1")




def test_claude_mem_resolve_prefers_stable_over_prerelease(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    _install_claude_mem_cache_version(home, "13.13.1")
    _install_claude_mem_cache_version(home, "13.13.1-beta.1")
    helpers = _claude_mem_resolve_helpers()
    result = subprocess.run(
        [
            _bash_path(),
            "-c",
            helpers + '\nclaude_mem_resolve_active_install "$HOME/.claude/plugins/cache/thedotmack/claude-mem"\n',
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, "HOME": str(home)},
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().endswith("13.13.1")


def test_claude_mem_resolve_prefers_higher_core_even_if_prerelease(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    _install_claude_mem_cache_version(home, "13.13.1")
    _install_claude_mem_cache_version(home, "13.14.0-alpha")
    helpers = _claude_mem_resolve_helpers()
    result = subprocess.run(
        [
            _bash_path(),
            "-c",
            helpers + '\nclaude_mem_resolve_active_install "$HOME/.claude/plugins/cache/thedotmack/claude-mem"\n',
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, "HOME": str(home)},
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().endswith("13.14.0-alpha")




def test_claude_mem_resolve_prefers_newer_prerelease_on_same_core(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    _install_claude_mem_cache_version(home, "13.14.0-beta.1")
    _install_claude_mem_cache_version(home, "13.14.0-beta.2")
    helpers = _claude_mem_resolve_helpers()
    result = subprocess.run(
        [
            _bash_path(),
            "-c",
            helpers + '\nclaude_mem_resolve_active_install "$HOME/.claude/plugins/cache/thedotmack/claude-mem"\n',
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, "HOME": str(home)},
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().endswith("13.14.0-beta.2")


def test_claude_mem_repair_windows_path_conversion_failure_is_warn_only(tmp_path):
    home = tmp_path / "home"
    _prepare_claude_mem_home(home, consecutive_failures=2, marker=True)
    result = _run_claude_mem_section(
        tmp_path,
        home=home,
        health_fail_times=1,
        os_type="windows",
        path_convert_fail=True,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert "warnings:1" in result.stdout
    assert "errors:0" in result.stdout
    assert (home / ".claude-mem" / ".worker-start-attempted").exists()
    payload = json.loads(
        (home / ".claude-mem" / "state" / "hook-failures.json").read_text(encoding="utf-8")
    )
    assert payload["consecutiveFailures"] == 2
