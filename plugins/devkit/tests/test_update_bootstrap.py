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
        "if (process.env.CLAUDE_MEM_RESTART_FAIL === '1') process.exit(1);\n"
        "const flag = process.env.CLAUDE_MEM_RESTART_FAIL_FLAG;\n"
        "if (flag && fs.existsSync(flag)) process.exit(1);\n",
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
    post_helpers: str = "",
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
        + post_helpers
        + "section_claude_mem_repair\n"
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
    for bad_port in ("abc", "0", "99999", "-1", ""):
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
    marker = home / ".claude-mem" / ".worker-start-attempted"
    failures = home / ".claude-mem" / "state" / "hook-failures.json"
    for bad_port in ("abc", ""):
        marker.write_text("1\n", encoding="utf-8")
        failures.write_text(
            json.dumps(
                {"consecutiveFailures": 3, "lastFailureAt": 99, "kept": "yes"}
            ),
            encoding="utf-8",
        )
        (tmp_path / "restart.log").unlink(missing_ok=True)
        result = _run_claude_mem_section(
            tmp_path,
            home=home,
            health_bodies=[body],
            extra_env={"CLAUDE_MEM_WORKER_PORT": bad_port},
        )
        assert result.returncode == 0, f"{bad_port!r}: {result.stderr + result.stdout}"
        assert "invalid CLAUDE_MEM_WORKER_PORT" in result.stdout, bad_port
        assert marker.exists(), bad_port
        payload = json.loads(failures.read_text(encoding="utf-8"))
        assert payload["consecutiveFailures"] == 3, bad_port
        assert payload["kept"] == "yes", bad_port
        assert "warnings:1" in result.stdout, bad_port
        assert not (tmp_path / "restart.log").exists(), bad_port


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


def test_claude_mem_repair_stale_kill_retry_recovers(tmp_path):
    # ゾンビ port シナリオ: 初回 restart は port bind 失敗、残留プロセス掃除が
    # 成功した後の再試行で復旧する。
    home = tmp_path / "home"
    _prepare_claude_mem_home(home, consecutive_failures=7, marker=True)
    fail_flag = tmp_path / "restart-fail-flag"
    fail_flag.write_text("1\n", encoding="utf-8")
    kill_log = tmp_path / "kill.log"
    post_helpers = (
        "claude_mem_kill_stale_processes() {\n"
        f'  echo killed >> "{kill_log.as_posix()}"\n'
        f'  rm -f -- "{fail_flag.as_posix()}"\n'
        "  return 0\n"
        "}\n"
        "sleep() { :; }\n"
    )
    bodies = [json.dumps({"status": "ok", "version": "13.13.1"})]
    result = _run_claude_mem_section(
        tmp_path,
        home=home,
        health_bodies=bodies,
        health_fail_times=1,
        extra_env={"CLAUDE_MEM_RESTART_FAIL_FLAG": fail_flag.as_posix()},
        post_helpers=post_helpers,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert "warnings:0" in result.stdout
    assert "errors:0" in result.stdout
    assert kill_log.exists()
    restart_log = (tmp_path / "restart.log").read_text(encoding="utf-8").strip().splitlines()
    assert len(restart_log) == 2
    payload = json.loads(
        (home / ".claude-mem" / "state" / "hook-failures.json").read_text(encoding="utf-8")
    )
    assert payload["consecutiveFailures"] == 0


def test_claude_mem_repair_stale_kill_noop_skips_retry(tmp_path):
    # 掃除対象が見つからなければ再試行せず、従来どおり restart 失敗の WARN を残す。
    home = tmp_path / "home"
    _prepare_claude_mem_home(home, consecutive_failures=2)
    post_helpers = "claude_mem_kill_stale_processes() { return 1; }\n"
    result = _run_claude_mem_section(
        tmp_path,
        home=home,
        health_fail_times=1,
        restart_fail=True,
        post_helpers=post_helpers,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert "warnings:1" in result.stdout
    assert "worker restart failed" in result.stdout
    restart_log = (tmp_path / "restart.log").read_text(encoding="utf-8").strip().splitlines()
    assert len(restart_log) == 1
    payload = json.loads(
        (home / ".claude-mem" / "state" / "hook-failures.json").read_text(encoding="utf-8")
    )
    assert payload["consecutiveFailures"] == 2


def test_claude_mem_kill_stale_processes_windows_powershell_contract(tmp_path):
    home = tmp_path / "home"
    _prepare_claude_mem_home(home)
    helpers = _claude_mem_helpers_source()
    ps_log = tmp_path / "powershell.log"
    probe_template = (
        "OS_TYPE=windows\n"
        "windows_path_from_posix() {\n"
        "  printf 'C:\\\\converted\\\\%s\\n' \"${1##*/}\"\n"
        "}\n"
        "powershell.exe() {\n"
        f'  printf \'%s\\n\' "$DEVKIT_MEM_CHROMA_DIR" "$DEVKIT_MEM_CACHE_ROOT" >> "{ps_log.as_posix()}"\n'
        "  echo \"$DEVKIT_TEST_KILL_COUNT\"\n"
        "}\n"
        + helpers
        + "\n"
        "if claude_mem_kill_stale_processes; then echo KILLED; else echo NOKILL; fi\n"
    )
    probe_path = tmp_path / "claude-mem-kill-stale-probe.sh"
    probe_path.write_text(probe_template, encoding="utf-8", newline="\n")
    env = {
        **{
            k: v
            for k, v in os.environ.items()
            if k not in ("CLAUDE_MEM_WORKER_PORT", "CLAUDE_MEM_DATA_DIR")
        },
        "HOME": str(home),
    }
    result = subprocess.run(
        [_bash_path(), str(probe_path.as_posix())],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**env, "DEVKIT_TEST_KILL_COUNT": "3"},
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert "KILLED" in result.stdout
    # powershell へは forward slash 化した Windows パスを env で渡す
    ps_lines = ps_log.read_text(encoding="utf-8").strip().splitlines()
    assert ps_lines == ["C:/converted/chroma", "C:/converted/claude-mem"]

    result = subprocess.run(
        [_bash_path(), str(probe_path.as_posix())],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**env, "DEVKIT_TEST_KILL_COUNT": "0"},
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert "NOKILL" in result.stdout


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

def _cursor_agent_helpers_source() -> str:
    shell = (SCRIPTS / "update-ccx.sh").read_text(encoding="utf-8")
    # Production windows_path_to_posix only (not the functions between it and
    # cursor_agent_install_dir, which would source libs / overwrite OS_TYPE).
    path_start = shell.index("windows_path_to_posix()")
    path_end = shell.index(chr(10) + "source_root_path_for_shell()")
    early_start = shell.index("cursor_agent_install_dir()")
    early_end = shell.index(chr(10) + "resolve_command_path()")
    ensure_start = shell.index(chr(10) + "ensure_cursor_agent()")
    ensure_end = shell.index(chr(10) + "section_setup()")
    setup_start = shell.index(chr(10) + "section_setup()")
    setup_end = shell.index(chr(10) + "update_claude()")
    update_start = shell.index(chr(10) + "update_cursor_agent()")
    update_end = shell.index(chr(10) + "windows_path_from_posix()")
    return (
        shell[path_start:path_end]
        + shell[early_start:early_end]
        + shell[ensure_start:ensure_end]
        + shell[setup_start:setup_end]
        + shell[update_start:update_end]
    )


def _cursor_agent_prelude(os_type: str) -> str:
    return (
        "set -o pipefail\n"
        f"OS_TYPE={json.dumps(os_type)}\n"
        "ERRORS=()\n"
        "WARNINGS=()\n"
        'CURSOR_AGENT_CMD=""\n'
        "CURSOR_AGENT_SKIP_UPDATE=false\n"
        "resolve_command_path() {\n"
        '  echo "$1"\n'
        "}\n"
        "join_summary_parts() {\n"
        "  local IFS=' / '\n"
        '  echo "$*"\n'
        "}\n"
    )


def _fake_cursor_agent_shell_source(*, version: str, update_exit: int = 0) -> str:
    """POSIX launcher body; usable as .cmd on non-Windows hosts."""
    return (
        "#!/bin/sh\n"
        'if [ "$1" = "--version" ]; then\n'
        f'  printf "%s\\n" "{version}"\n'
        "  exit 0\n"
        "fi\n"
        'if [ "$1" = "update" ]; then\n'
        f"  exit {update_exit}\n"
        "fi\n"
        "exit 0\n"
    )


def _write_fake_cursor_agent(path: Path, *, version: str = "2026.08.04-test", update_exit: int = 0) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix.lower() == ".cmd" and os.name == "nt":
        # Payload uses LF only; newline=CRLF performs the sole CRLF translation.
        # Embedding CRLF in the payload would become CR+CRLF under that mode.
        path.write_text(
            "@echo off\n"
            f'if "%~1"=="--version" (\n'
            f"  echo {version}\n"
            "  exit /b 0\n"
            ")\n"
            f'if "%~1"=="update" (\n'
            f"  exit /b {update_exit}\n"
            ")\n"
            "exit /b 0\n",
            encoding="utf-8",
            newline='\r\n',
        )
        return
    # Linux CI simulates OS_TYPE=windows with a .cmd path, but bash executes it
    # directly (no cmd.exe). Keep the .cmd name for the known-launcher contract.
    _write_exec(
        path,
        _fake_cursor_agent_shell_source(version=version, update_exit=update_exit),
    )


@pytest.mark.skipif(os.name != "nt", reason="[platform] Windows .cmd CRLF fixture bytes")
def test_fake_cursor_agent_cmd_bytes_are_single_crlf(tmp_path):
    """Batch fixture must be CRLF without doubled CR from newline translation."""
    path = tmp_path / "fake-launcher.cmd"
    _write_fake_cursor_agent(path, version="crlf-check")
    data = path.read_bytes()
    assert b'\r\r\n' not in data
    assert b'\r\n' in data
    assert data.startswith(b'@echo off\r\n')
    # Invoke via cmd.exe (same as Git Bash for *.cmd), not bash-as-script.
    result = subprocess.run(
        ["cmd.exe", "/c", str(path), "--version"],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 0, result.stderr
    assert "crlf-check" in result.stdout


def _shell_posix_path(path: Path) -> str:
    """Normalize a filesystem path the way Git Bash probes see it.

    Prefer `bash -c 'cd ... && pwd'` over bare `cygpath -u`: MSYS remaps Windows
    Temp to `/tmp/...` inside the probe, while `Path.as_posix()` stays `C:/Users/...`
    when cygpath is missing from PATH.
    """
    converted = subprocess.run(
        [_bash_path(), "-c", 'cd "$1" && pwd', "_", str(path)],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if converted.returncode == 0 and converted.stdout.strip():
        return converted.stdout.strip().rstrip("/")
    located_cygpath = shutil.which("cygpath")
    if located_cygpath:
        via_cygpath = subprocess.run(
            [located_cygpath, "-u", str(path)],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        if via_cygpath.returncode == 0 and via_cygpath.stdout.strip():
            return via_cygpath.stdout.strip().rstrip("/")
    return path.as_posix().rstrip("/")


def _run_cursor_agent_probe(
    tmp_path: Path,
    *,
    home: Path,
    os_type: str,
    body: str,
    extra_env: dict[str, str] | None = None,
    path_prefix: list[Path] | None = None,
) -> subprocess.CompletedProcess[str]:
    probe = _cursor_agent_prelude(os_type) + _cursor_agent_helpers_source() + "\n" + body
    probe_path = tmp_path / "cursor-agent-probe.sh"
    probe_path.write_text(probe, encoding="utf-8", newline="\n")

    path_entries: list[str] = []
    for tool in ("bash", "curl", "head", "tr", "uname", "cygpath"):
        located = shutil.which(tool)
        if located:
            path_entries.append(str(Path(located).resolve().parent))
    if path_prefix:
        path_entries = [str(p) for p in path_prefix] + path_entries
    seen: set[str] = set()
    filtered: list[str] = []
    for entry in path_entries:
        if entry and entry not in seen:
            seen.add(entry)
            filtered.append(entry)

    env = {
        **os.environ,
        "HOME": str(home),
        "PATH": os.pathsep.join(filtered),
    }
    env.pop("LOCALAPPDATA", None)
    if extra_env:
        env.update(extra_env)

    return subprocess.run(
        [_bash_path(), str(probe_path.as_posix())],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        cwd=str(tmp_path),
    )


def test_cursor_agent_wiring_in_setup_update_and_flags():
    shell = (SCRIPTS / "update-ccx.sh").read_text(encoding="utf-8")
    assert "ensure_cursor_agent()" in shell
    assert "update_cursor_agent()" in shell
    assert "=== Claude Code, Codex CLI, Cursor Agent & DevKit ===" in shell
    assert "Cursor Agent:" in shell
    assert "https://cursor.com/install" in shell
    assert "https://cursor.com/install?win32=true" in shell
    assert "cursor-agent update failed" in shell

    setup = shell.split("section_setup()", 1)[1].split("update_claude()", 1)[0]
    assert "ensure_cursor_agent" in setup
    update = shell.split("section_update()", 1)[1].split("windows_path_from_posix()", 1)[0]
    assert "update_cursor_agent" in update
    assert "cursor-agent: $(get_cursor_agent_version)" in update

    # raw version helper must not extract semver
    version_fn = shell.split("get_cursor_agent_version()", 1)[1].split(
        "resolve_command_path()", 1
    )[0]
    assert "grep -oE" not in version_fn

    usage = shell.split("show_usage()", 1)[1].split("parse_args()", 1)[0]
    assert "Claude/Codex/Cursor Agent CLIs only" in usage

    main = shell.split("main()", 1)[1]
    assert 'if [[ "$DEVKIT_ONLY" != true ]]; then' in main
    assert "section_setup" in main
    assert "section_update" in main
    # Cursor Agent is CLI-path only: setup/update live under DEVKIT_ONLY guard
    cli_path = main.split('if [[ "$DEVKIT_ONLY" != true ]]; then', 1)[1].split(
        "fi\n", 1
    )[0]
    assert "section_setup" in cli_path
    assert "section_update" in cli_path


def test_cursor_agent_posix_resolves_outside_path(tmp_path):
    home = tmp_path / "home"
    local_bin = home / ".local" / "bin"
    _write_fake_cursor_agent(local_bin / "cursor-agent", version="2026.08.04-out-of-path")
    # PATH intentionally excludes local_bin; resolver must prepend it.
    result = _run_cursor_agent_probe(
        tmp_path,
        home=home,
        os_type="linux",
        body=(
            "resolve_cursor_agent_command\n"
            'printf "cmd:%s\\n" "$CURSOR_AGENT_CMD"\n'
            'printf "ver:%s\\n" "$(get_cursor_agent_version)"\n'
            "ensure_cursor_agent\n"
            'printf "errors:%s\\n" "${#ERRORS[@]}"\n'
        ),
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert "cmd:" in result.stdout and "cursor-agent" in result.stdout
    assert "ver:2026.08.04-out-of-path" in result.stdout
    assert "already installed" in result.stdout
    assert "errors:0" in result.stdout


def test_cursor_agent_windows_resolves_cmd_without_installer(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    local_app = tmp_path / "LocalAppData"
    install_dir = local_app / "cursor-agent"
    _write_fake_cursor_agent(install_dir / "cursor-agent.cmd", version="2026.08.04-win-cmd")
    install_log = tmp_path / "install.log"
    result = _run_cursor_agent_probe(
        tmp_path,
        home=home,
        os_type="windows",
        extra_env={"LOCALAPPDATA": str(local_app)},
        body=(
            f'INSTALL_LOG="{install_log.as_posix()}"\n'
            "powershell.exe() {\n"
            '  echo "powershell-called" >> "$INSTALL_LOG"\n'
            "  return 1\n"
            "}\n"
            "ensure_cursor_agent\n"
            'printf "cmd:%s\\n" "$CURSOR_AGENT_CMD"\n'
            'printf "ver:%s\\n" "$(get_cursor_agent_version)"\n'
            'printf "errors:%s\\n" "${#ERRORS[@]}"\n'
        ),
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert "already installed" in result.stdout
    assert "ver:2026.08.04-win-cmd" in result.stdout
    assert "errors:0" in result.stdout
    assert not install_log.exists()


def test_cursor_agent_missing_runs_installer_and_resolves_posix(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    install_log = tmp_path / "install.log"
    launcher = home / ".local" / "bin" / "cursor-agent"
    result = _run_cursor_agent_probe(
        tmp_path,
        home=home,
        os_type="linux",
        body=(
            f'INSTALL_LOG="{install_log.as_posix()}"\n'
            f'LAUNCHER="{launcher.as_posix()}"\n'
            "curl() {\n"
            '  echo "$*" >> "$INSTALL_LOG"\n'
            '  mkdir -p "$(dirname "$LAUNCHER")"\n'
            "  cat > \"$LAUNCHER\" <<'EOF'\n"
            "#!/bin/sh\n"
            'if [ "$1" = "--version" ]; then echo 2026.08.04-installed; exit 0; fi\n'
            "exit 0\n"
            "EOF\n"
            '  chmod +x "$LAUNCHER"\n'
            "}\n"
            "ensure_cursor_agent\n"
            'printf "ver:%s\\n" "$(get_cursor_agent_version)"\n'
            'printf "errors:%s\\n" "${#ERRORS[@]}"\n'
            'printf "exists:%s\\n" "$([[ -x "$LAUNCHER" ]] && echo yes || echo no)"\n'
        ),
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert install_log.exists()
    assert "https://cursor.com/install" in install_log.read_text(encoding="utf-8")
    assert "ver:2026.08.04-installed" in result.stdout
    assert "errors:0" in result.stdout
    assert "exists:yes" in result.stdout


def test_cursor_agent_windows_missing_runs_installer(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    local_app = tmp_path / "LocalAppData"
    local_app.mkdir()
    install_log = tmp_path / "install.log"
    if os.name == "nt":
        # Reuse the CRLF-correct writer; powershell stub only installs the file.
        golden = tmp_path / "golden-launcher.cmd"
        _write_fake_cursor_agent(golden, version="2026.08.04-win-installed")
        create_launcher = (
            f'  GOLDEN="{golden.as_posix()}"\n'
            '  install_dir="$(cursor_agent_install_dir)"\n'
            '  mkdir -p "$install_dir"\n'
            '  cp "$GOLDEN" "$install_dir/cursor-agent.cmd"\n'
        )
    else:
        # Linux CI: bash executes the .cmd path directly; emit a shebang script.
        create_launcher = (
            '  install_dir="$(cursor_agent_install_dir)"\n'
            '  mkdir -p "$install_dir"\n'
            "  cat > \"$install_dir/cursor-agent.cmd\" <<'EOF'\n"
            "#!/bin/sh\n"
            'if [ "$1" = "--version" ]; then echo 2026.08.04-win-installed; exit 0; fi\n'
            "exit 0\n"
            "EOF\n"
            '  chmod +x "$install_dir/cursor-agent.cmd"\n'
        )
    result = _run_cursor_agent_probe(
        tmp_path,
        home=home,
        os_type="windows",
        extra_env={"LOCALAPPDATA": str(local_app)},
        body=(
            f'INSTALL_LOG="{install_log.as_posix()}"\n'
            "powershell.exe() {\n"
            '  echo "$*" >> "$INSTALL_LOG"\n'
            + create_launcher
            + "  return 0\n"
            + "}\n"
            + "ensure_cursor_agent\n"
            + 'printf "ver:%s\\n" "$(get_cursor_agent_version)"\n'
            + 'printf "errors:%s\\n" "${#ERRORS[@]}"\n'
        ),
    )
    assert result.returncode == 0, result.stderr + result.stdout
    log = install_log.read_text(encoding="utf-8")
    assert "https://cursor.com/install?win32=true" in log
    assert "ver:2026.08.04-win-installed" in result.stdout
    assert "errors:0" in result.stdout



def test_cursor_agent_installer_failure_is_error(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    result = _run_cursor_agent_probe(
        tmp_path,
        home=home,
        os_type="linux",
        body=(
            "curl() { return 22; }\n"
            "ensure_cursor_agent\n"
            'printf "errors:%s\\n" "${#ERRORS[@]}"\n'
            'printf "error0:%s\\n" "${ERRORS[0]-}"\n'
        ),
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert "errors:1" in result.stdout
    assert "native install failed" in result.stdout


def test_cursor_agent_update_failure_is_error(tmp_path):
    home = tmp_path / "home"
    _write_fake_cursor_agent(
        home / ".local" / "bin" / "cursor-agent",
        version="2026.08.04-upd",
        update_exit=7,
    )
    result = _run_cursor_agent_probe(
        tmp_path,
        home=home,
        os_type="linux",
        body=(
            "resolve_cursor_agent_command >/dev/null\n"
            "update_cursor_agent\n"
            'printf "errors:%s\\n" "${#ERRORS[@]}"\n'
            'printf "error0:%s\\n" "${ERRORS[0]-}"\n'
        ),
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert "errors:1" in result.stdout
    assert "exit code 7" in result.stdout


def test_cursor_agent_install_without_launcher_is_error(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    result = _run_cursor_agent_probe(
        tmp_path,
        home=home,
        os_type="linux",
        body=(
            "curl() { :; }\n"  # pretend install succeeded but create nothing
            "ensure_cursor_agent\n"
            'printf "errors:%s\\n" "${#ERRORS[@]}"\n'
            'printf "error0:%s\\n" "${ERRORS[0]-}"\n'
        ),
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert "errors:1" in result.stdout
    assert "launcher was not found" in result.stdout


def test_cursor_agent_broken_launcher_is_error_without_reinstall(tmp_path):
    home = tmp_path / "home"
    broken = home / ".local" / "bin" / "cursor-agent"
    broken.parent.mkdir(parents=True)
    _write_exec(
        broken,
        "#!/bin/sh\n"
        "exit 1\n",
    )
    install_log = tmp_path / "install.log"
    result = _run_cursor_agent_probe(
        tmp_path,
        home=home,
        os_type="linux",
        body=(
            f'INSTALL_LOG="{install_log.as_posix()}"\n'
            "curl() { echo called >> \"$INSTALL_LOG\"; return 0; }\n"
            "ensure_cursor_agent\n"
            'printf "errors:%s\\n" "${#ERRORS[@]}"\n'
            'printf "error0:%s\\n" "${ERRORS[0]-}"\n'
        ),
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert "errors:1" in result.stdout
    assert "broken installation" in result.stdout
    assert not install_log.exists()


def test_cursor_agent_raw_version_in_before_after(tmp_path):
    home = tmp_path / "home"
    _write_fake_cursor_agent(
        home / ".local" / "bin" / "cursor-agent",
        version="2026.08.04-raw-build",
    )
    result = _run_cursor_agent_probe(
        tmp_path,
        home=home,
        os_type="linux",
        body=(
            "detect_claude_install() { echo skip; }\n"
            "detect_codex_install() { echo skip; }\n"
            "get_claude_version() { echo unknown; }\n"
            "get_codex_version() { echo unknown; }\n"
            "update_claude() { :; }\n"
            "update_codex() { :; }\n"
            # Re-open section_update from the real script via helpers already loaded;
            # call the version lines directly for Before/After contract.
            "resolve_cursor_agent_command >/dev/null\n"
            'before="cursor-agent: $(get_cursor_agent_version)"\n'
            'after="cursor-agent: $(get_cursor_agent_version)"\n'
            'printf "before:%s\\n" "$before"\n'
            'printf "after:%s\\n" "$after"\n'
            "update_cursor_agent\n"
            'printf "errors:%s\\n" "${#ERRORS[@]}"\n'
        ),
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert "before:cursor-agent: 2026.08.04-raw-build" in result.stdout
    assert "after:cursor-agent: 2026.08.04-raw-build" in result.stdout
    assert "errors:0" in result.stdout
    # Must keep raw build id, not strip to x.y.z only
    assert "2026.08.04-raw-build" in result.stdout


def test_cursor_agent_version_flag_includes_raw_line(tmp_path):
    home = tmp_path / "home"
    _write_fake_cursor_agent(
        home / ".local" / "bin" / "cursor-agent",
        version="2026.08.04-version-flag",
    )
    # Minimal show_versions using helpers
    result = _run_cursor_agent_probe(
        tmp_path,
        home=home,
        os_type="linux",
        body=(
            "get_claude_version() { echo 1.0.0; }\n"
            "get_codex_version() { echo 2.0.0; }\n"
            "show_versions() {\n"
            '  echo "Environment: $OS_TYPE"\n'
            '  echo "Claude Code: $(get_claude_version)"\n'
            '  echo "Codex CLI:   $(get_codex_version)"\n'
            '  echo "Cursor Agent: $(get_cursor_agent_version)"\n'
            "}\n"
            "show_versions\n"
        ),
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert "Cursor Agent: 2026.08.04-version-flag" in result.stdout



def test_cursor_agent_path_prepend_is_idempotent(tmp_path):
    home = tmp_path / "home"
    local_bin = home / ".local" / "bin"
    local_bin.mkdir(parents=True)
    body = (
        # Same bash process that prepends PATH; captures MSYS /tmp remap of HOME.
        'printf "ref:%s\n" "$HOME/.local/bin"\n'
        'export PATH=""\n'
        'prepend_cursor_agent_path\n'
        'echo "after1:$PATH"\n'
        'prepend_cursor_agent_path\n'
        'prepend_cursor_agent_path\n'
        'echo "after3:$PATH"\n'
        'export PATH="/other:$HOME/.local/bin/extra:$HOME/.local/bin"\n'
        'prepend_cursor_agent_path\n'
        'echo "already:$PATH"\n'
        'export PATH="/other:$HOME/.local/bin-extra"\n'
        'prepend_cursor_agent_path\n'
        'echo "sibling:$PATH"\n'
    )
    result = _run_cursor_agent_probe(
        tmp_path, home=home, os_type="linux", body=body
    )
    assert result.returncode == 0, result.stderr + result.stdout
    lines = {
        line.split(":", 1)[0]: line.split(":", 1)[1]
        for line in result.stdout.splitlines()
        if ":" in line
        and line.split(":", 1)[0] in {"ref", "after1", "after3", "already", "sibling"}
    }
    expected = lines["ref"]
    assert expected == _shell_posix_path(local_bin)
    assert lines["after1"] == expected
    assert lines["after3"] == expected
    assert lines["already"].endswith(expected)
    assert lines["already"].split(":").count(expected) == 1
    assert lines["sibling"].startswith(expected + ":")
    assert lines["sibling"].endswith("/.local/bin-extra")



def test_cursor_agent_broken_launcher_default_flow_single_error(tmp_path):
    home = tmp_path / "home"
    broken = home / ".local" / "bin" / "cursor-agent"
    broken.parent.mkdir(parents=True)
    _write_exec(broken, "#!/bin/sh" + chr(10) + "exit 1" + chr(10))
    update_log = tmp_path / "update.log"
    body = (
        'UPDATE_LOG="__LOG__"\n'
        'detect_claude_install() { echo skip; }\n'
        'detect_codex_install() { echo skip; }\n'
        'get_claude_version() { echo unknown; }\n'
        'get_codex_version() { echo unknown; }\n'
        'update_claude() { :; }\n'
        'update_codex() { :; }\n'
        'update_cursor_agent() {\n'
        '  echo called >> "$UPDATE_LOG"\n'
        '  ERRORS+=("Cursor Agent: cursor-agent update failed (exit code 99)")\n'
        '}\n'
        'ensure_fnm() { :; }\n'
        'ensure_nodejs() { :; }\n'
        'ensure_claude() { :; }\n'
        'ensure_codex() { :; }\n'
        'section_setup\n'
        'section_update\n'
        'echo "errors:${#ERRORS[@]}"\n'
        'echo "warnings:${#WARNINGS[@]}"\n'
        'echo "skip:$CURSOR_AGENT_SKIP_UPDATE"\n'
        'if ((${#ERRORS[@]} > 0)); then echo "error0:${ERRORS[0]}"; fi\n'
    ).replace("__LOG__", update_log.as_posix())
    result = _run_cursor_agent_probe(
        tmp_path, home=home, os_type="linux", body=body
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert "errors:1" in result.stdout
    assert "warnings:0" in result.stdout
    assert "skip:true" in result.stdout
    assert "broken installation" in result.stdout
    assert "cursor-agent update failed" not in result.stdout
    assert not update_log.exists()


def test_cursor_agent_installer_failure_default_flow_no_double_warn(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    update_log = tmp_path / "update.log"
    body = (
        'UPDATE_LOG="__LOG__"\n'
        'curl() { return 22; }\n'
        'detect_claude_install() { echo skip; }\n'
        'detect_codex_install() { echo skip; }\n'
        'get_claude_version() { echo unknown; }\n'
        'get_codex_version() { echo unknown; }\n'
        'update_claude() { :; }\n'
        'update_codex() { :; }\n'
        'update_cursor_agent() { echo called >> "$UPDATE_LOG"; }\n'
        'ensure_fnm() { :; }\n'
        'ensure_nodejs() { :; }\n'
        'ensure_claude() { :; }\n'
        'ensure_codex() { :; }\n'
        'section_setup\n'
        'section_update\n'
        'echo "errors:${#ERRORS[@]}"\n'
        'echo "warnings:${#WARNINGS[@]}"\n'
        'echo "skip:$CURSOR_AGENT_SKIP_UPDATE"\n'
        'if ((${#ERRORS[@]} > 0)); then echo "error0:${ERRORS[0]}"; fi\n'
    ).replace("__LOG__", update_log.as_posix())
    result = _run_cursor_agent_probe(
        tmp_path, home=home, os_type="linux", body=body
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert "errors:1" in result.stdout
    assert "warnings:0" in result.stdout
    assert "skip:true" in result.stdout
    assert "error0:Cursor Agent: native install failed" in result.stdout
    assert "not installed, skipping update" not in result.stdout
    assert not update_log.exists()


def _cursor_agent_main_harness_source() -> str:
    shell = (SCRIPTS / "update-ccx.sh").read_text(encoding="utf-8")
    show_start = shell.index("show_versions()")
    parse_end = shell.index(chr(10) + "join_summary_parts()")
    main_start = shell.index(chr(10) + "main()")
    main_end = shell.index(chr(10) + 'main "$@"; exit $?')
    setup_start = shell.index(chr(10) + "section_setup()")
    setup_end = shell.index(chr(10) + "update_claude()")
    update_start = shell.index(chr(10) + "update_cursor_agent()")
    update_end = shell.index(chr(10) + "windows_path_from_posix()")
    return (
        shell[show_start:parse_end]
        + shell[setup_start:setup_end]
        + shell[update_start:update_end]
        + shell[main_start:main_end]
    )


def _run_cursor_agent_main_flags(
    tmp_path: Path,
    *,
    args: list[str],
    home: Path,
) -> subprocess.CompletedProcess[str]:
    call_log = tmp_path / ("calls-" + ("-".join(args) if args else "default") + ".log")
    args_lit = " ".join(json.dumps(a) for a in args)
    stub_lines = [
        'CALL_LOG="__LOG__"',
        'log_call() { echo "$1" >> "$CALL_LOG"; }',
        'section_managed_copy() { log_call managed; }',
        'section_prerequisites() { log_call prereq; }',
        'section_prune_legacy_assets() { log_call prune_legacy; }',
        'section_prune_cursor_sync() { log_call prune_cursor; }',
        'section_codex_plugin() { log_call codex_plugin; }',
        'section_claude_plugin() { log_call claude_plugin; }',
        'section_claude_mem_repair() { log_call claude_mem; }',
        'resolve_devkit_python() { return 1; }',
        'ensure_fnm() { :; }',
        'ensure_nodejs() { :; }',
        'ensure_claude() { log_call ensure_claude; }',
        'ensure_codex() { log_call ensure_codex; }',
        'ensure_cursor_agent() {',
        '  log_call ensure_cursor_agent',
        '  CURSOR_AGENT_SKIP_UPDATE=false',
        '  CURSOR_AGENT_CMD="/fake/cursor-agent"',
        '  return 0',
        '}',
        'detect_claude_install() { echo skip; }',
        'detect_codex_install() { echo skip; }',
        'get_claude_version() { echo c-ver; }',
        'get_codex_version() { echo x-ver; }',
        'get_cursor_agent_version() { echo ca-ver; }',
        'update_claude() { :; }',
        'update_codex() { :; }',
        'update_cursor_agent() { log_call update_cursor_agent; }',
        'resolve_cursor_agent_command() {',
        '  [[ -n "$CURSOR_AGENT_CMD" ]] || return 1',
        '  return 0',
        '}',
    ]
    stubs = (chr(10).join(stub_lines) + chr(10)).replace("__LOG__", call_log.as_posix())
    probe = (
        "set -o pipefail" + chr(10)
        + 'OS_TYPE="linux"' + chr(10)
        + "ERRORS=()" + chr(10)
        + "WARNINGS=()" + chr(10)
        + "CLI_ONLY=false" + chr(10)
        + "DEVKIT_ONLY=false" + chr(10)
        + 'RUN_MODE="run"' + chr(10)
        + 'DEVKIT_PYTHON_KIND=""' + chr(10)
        + 'CURSOR_AGENT_CMD=""' + chr(10)
        + "CURSOR_AGENT_SKIP_UPDATE=false" + chr(10)
        + "join_summary_parts() {" + chr(10)
        + "  local IFS=' / '" + chr(10)
        + '  echo "$*"' + chr(10)
        + "}" + chr(10)
        # Real section_*/main first; stubs override update_cursor_agent afterward.
        + _cursor_agent_main_harness_source()
        + stubs
        + chr(10)
        + f"main {args_lit}" + chr(10)
        + 'echo "exit:$?"' + chr(10)
    )
    probe_path = tmp_path / (
        "main-flags-" + ("-".join(args) if args else "default") + ".sh"
    )
    probe_path.write_text(probe, encoding="utf-8", newline=chr(10))
    path_entries: list[str] = []
    for tool in ("bash", "head", "tr", "uname"):
        located = shutil.which(tool)
        if located:
            path_entries.append(str(Path(located).resolve().parent))
    env = {
        **os.environ,
        "HOME": str(home),
        "PATH": os.pathsep.join(dict.fromkeys(path_entries)),
    }
    result = subprocess.run(
        [_bash_path(), str(probe_path.as_posix())],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        cwd=str(tmp_path),
    )
    setattr(result, "call_log", call_log)
    return result


def test_cursor_agent_main_flag_boundaries_runtime(tmp_path):
    home = tmp_path / "home"
    home.mkdir()

    default = _run_cursor_agent_main_flags(tmp_path, args=[], home=home)
    assert default.returncode == 0, default.stderr + default.stdout
    default_calls = default.call_log.read_text(encoding="utf-8").splitlines()
    assert "ensure_cursor_agent" in default_calls
    assert default_calls.count("update_cursor_agent") == 1
    assert "managed" in default_calls

    cli_only = _run_cursor_agent_main_flags(tmp_path, args=["--cli-only"], home=home)
    assert cli_only.returncode == 0, cli_only.stderr + cli_only.stdout
    cli_calls = cli_only.call_log.read_text(encoding="utf-8").splitlines()
    assert "ensure_cursor_agent" in cli_calls
    assert cli_calls.count("update_cursor_agent") == 1
    assert "managed" not in cli_calls
    assert "codex_plugin" not in cli_calls

    devkit_only = _run_cursor_agent_main_flags(
        tmp_path, args=["--devkit-only"], home=home
    )
    assert devkit_only.returncode == 0, devkit_only.stderr + devkit_only.stdout
    devkit_calls = devkit_only.call_log.read_text(encoding="utf-8").splitlines()
    assert "ensure_cursor_agent" not in devkit_calls
    assert "update_cursor_agent" not in devkit_calls
    assert "managed" in devkit_calls

    version = _run_cursor_agent_main_flags(tmp_path, args=["--version"], home=home)
    assert version.returncode == 0, version.stderr + version.stdout
    assert "Cursor Agent: ca-ver" in version.stdout
    assert "Claude Code: c-ver" in version.stdout
    assert (not version.call_log.exists()) or (
        version.call_log.read_text(encoding="utf-8") == ""
    )
    assert "=== [" not in version.stdout
