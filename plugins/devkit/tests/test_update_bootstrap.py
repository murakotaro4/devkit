from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from hashlib import sha256
from pathlib import Path

import pytest


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
        'ensure_managed_file "$plugin_scripts/update-ccx.ps1"',
    )
    positions = [managed_section.index(marker) for marker in ordered_copy_markers]
    assert positions == sorted(positions)

    powershell = (SCRIPTS / "devkit-lib.ps1").read_text(encoding="utf-8")
    managed_function = powershell.split("function Install-DevKitManagedFiles", 1)[1].split(
        "function Test-DevKitPathLooksManaged", 1
    )[0]
    managed_names = managed_function.split("foreach ($fileName in @(", 1)[1].split("))", 1)[0]
    assert '"update-ccx.sh"' in managed_names
    assert '"devkit-lib.sh"' in managed_names
    assert '"update-ccx.cmd"' in managed_names
    assert '"update-ccx.ps1"' in managed_names
    assert "update-devkit" not in managed_names


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


def test_v9_migration_contract_is_present_in_both_libraries(tmp_path):
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

    pwsh = shutil.which("pwsh")
    if not pwsh:
        return

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
    if not _probe_symlink_support():
        pytest.skip("symlinks are unavailable")

    home = tmp_path / "home"
    marker_dir = home / ".codex" / "devkit"
    marker_dir.mkdir(parents=True)
    (marker_dir / ".migrated-v6").write_text("migrated-v6\n", encoding="utf-8")

    managed_link = home / ".agents" / "skills" / "dig"
    managed_link.parent.mkdir(parents=True)
    managed_target = ROOT / "plugins" / "devkit" / "skills" / "dig"
    assert not managed_target.exists()
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


def _probe_symlink_support() -> bool:
    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            probe_dir = Path(tmp_dir)
            target = probe_dir / "target"
            target.mkdir()
            (probe_dir / "link").symlink_to(target, target_is_directory=True)
    except (OSError, NotImplementedError):
        return False
    return True


SYMLINK_SUPPORTED = _probe_symlink_support()


def require_symlink_support() -> None:
    if not SYMLINK_SUPPORTED:
        pytest.skip("Windows runner など symlink 作成権限がない環境では実行できません")


def bash_path() -> str:
    bash = shutil.which("bash")
    if not bash:
        raise AssertionError("bash が見つからない: PATH で bash を解決できません")
    return str(Path(bash).resolve())


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


@pytest.mark.skipif(
    os.name == "nt",
    reason="Git Bash が HOME を POSIX パスへ変換するためパス文字列比較が成立しない (CI Linux で検証)",
)
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
    assert (home / "selected-root.txt").read_text(encoding="utf-8") == f"{default_checkout}\n"


@pytest.mark.skipif(
    os.name == "nt",
    reason="Git Bash が HOME を POSIX パスへ変換するためパス文字列比較が成立しない (CI Linux で検証)",
)
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
    assert (home / "selected-root.txt").read_text(encoding="utf-8") == f"{default_checkout}\n"


@pytest.mark.skipif(
    os.name == "nt",
    reason="Git Bash が HOME を POSIX パスへ変換するためパス文字列比較が成立しない (CI Linux で検証)",
)
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
    assert (home / "selected-root.txt").read_text(encoding="utf-8") == f"{caller_source_root}\n"


@pytest.mark.skipif(
    os.name == "nt",
    reason="Git Bash が HOME を POSIX パスへ変換するためパス文字列比較が成立しない (CI Linux で検証)",
)
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
    assert (home / "selected-root.txt").read_text(encoding="utf-8") == f"{caller_source_root}\n"


def test_windows_updater_launchers_have_independent_git_bash_contract():
    cmd = (SCRIPTS / "update-ccx.cmd").read_text(encoding="utf-8")
    powershell = (SCRIPTS / "update-ccx.ps1").read_text(encoding="utf-8")

    cmd_search = (
        r"%ProgramFiles%\Git\bin\bash.exe",
        r"%ProgramFiles(x86)%\Git\bin\bash.exe",
        "where git.exe",
        r"%~dp1..\bin\bash.exe",
    )
    ps_search = (
        'Join-Path $env:ProgramFiles "Git\\bin\\bash.exe"',
        "${env:ProgramFiles(x86)}",
        "where.exe git.exe",
        '"bin\\bash.exe"',
    )
    ps_bootstrap = (
        'Join-Path $PSScriptRoot "update-ccx.sh"',
        '".codex\\devkit\\source-root.txt"',
        '"plugins\\devkit\\scripts\\update-ccx.sh"',
    )

    for text, expected in (
        (cmd, cmd_search),
        (powershell, ps_search),
        (powershell, ps_bootstrap),
    ):
        positions = [text.index(item) for item in expected]
        assert positions == sorted(positions)

    assert cmd.index(r"%~dp0update-ccx.sh") < cmd.index("call :resolve_update_script")
    cmd_fallback = cmd.rsplit(":resolve_update_script", 1)[1]
    assert cmd_fallback.index(r"%HOME%") < cmd_fallback.index(r"%USERPROFILE%")
    assert cmd_fallback.index(r"%USERPROFILE%") < cmd_fallback.index(
        r".codex\devkit\source-root.txt"
    )

    ps_fallback = powershell.split("function Find-UpdateScript", 1)[1]
    assert ps_fallback.index("$env:HOME") < ps_fallback.index("$env:USERPROFILE")
    assert ps_fallback.index("$env:USERPROFILE") < ps_fallback.index(
        '".codex\\devkit\\source-root.txt"'
    )

    assert r"System32\bash.exe" not in cmd
    assert r"System32\bash.exe" not in powershell
    assert "update-ccx.ps1" not in cmd
    assert "update-ccx.cmd" not in powershell
    assert '"%DEVKIT_BASH%" "%DEVKIT_UPDATE_SH%" %*' in cmd
    assert "exit /b %ERRORLEVEL%" in cmd
    assert "& $bash $updateScript @UpdaterArgs" in powershell
    assert "exit $LASTEXITCODE" in powershell


@pytest.mark.skipif(os.name != "nt", reason="Windows launcher runtime smoke")
def test_update_ccx_cmd_uses_source_root_fallback_when_adjacent_shell_is_missing(tmp_path):
    bash_candidates = [
        Path(os.environ.get("ProgramFiles", "")) / "Git/bin/bash.exe",
        Path(os.environ.get("ProgramFiles(x86)", "")) / "Git/bin/bash.exe",
    ]
    git = shutil.which("git.exe")
    if git:
        bash_candidates.append(Path(git).parent.parent / "bin/bash.exe")
    if not any(candidate.is_file() for candidate in bash_candidates):
        pytest.skip("Git for Windows bash is not installed")

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
