from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "plugins" / "devkit" / "scripts"


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


def test_update_ccx_ps1_bootstraps_missing_lib_from_persisted_source_root(tmp_path):
    pwsh = shutil.which("pwsh")
    if not pwsh:
        pytest.skip("pwsh is not installed")

    home = tmp_path / "home"
    codex_bin = home / ".codex" / "bin"
    state_dir = home / ".codex" / "devkit"
    codex_bin.mkdir(parents=True)
    state_dir.mkdir(parents=True)
    (state_dir / "source-root.txt").write_text(f"{ROOT}\n", encoding="utf-8")
    shutil.copyfile(SCRIPTS / "update-ccx.ps1", codex_bin / "update-ccx.ps1")

    env = os.environ.copy()
    env["HOME"] = str(home)
    env["USERPROFILE"] = str(home)

    result = subprocess.run(
        [
            pwsh,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(codex_bin / "update-ccx.ps1"),
            "--version",
        ],
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr + result.stdout
    assert (codex_bin / "devkit-lib.ps1").is_file()


def test_update_ccx_ps1_bootstraps_missing_lib_from_default_checkout(tmp_path):
    pwsh = shutil.which("pwsh")
    if not pwsh:
        pytest.skip("pwsh is not installed")

    home = tmp_path / "home"
    codex_bin = home / ".codex" / "bin"
    default_checkout = home / "cursor" / "devkit"
    codex_bin.mkdir(parents=True)
    default_checkout.parent.mkdir(parents=True)
    default_checkout.symlink_to(ROOT, target_is_directory=True)
    shutil.copyfile(SCRIPTS / "update-ccx.ps1", codex_bin / "update-ccx.ps1")

    env = os.environ.copy()
    env["HOME"] = str(home)
    env["USERPROFILE"] = str(home)

    result = subprocess.run(
        [
            pwsh,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(codex_bin / "update-ccx.ps1"),
            "--version",
        ],
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr + result.stdout
    assert (codex_bin / "devkit-lib.ps1").is_file()


def test_update_ccx_ps1_ignores_stale_persisted_source_root(tmp_path):
    pwsh = shutil.which("pwsh")
    if not pwsh:
        pytest.skip("pwsh is not installed")

    home = tmp_path / "home"
    codex_bin = home / ".codex" / "bin"
    state_dir = home / ".codex" / "devkit"
    default_checkout = home / "cursor" / "devkit"
    codex_bin.mkdir(parents=True)
    state_dir.mkdir(parents=True)
    default_checkout.parent.mkdir(parents=True)
    default_checkout.symlink_to(ROOT, target_is_directory=True)
    (state_dir / "source-root.txt").write_text(f"{tmp_path / 'missing'}\n", encoding="utf-8")
    shutil.copyfile(SCRIPTS / "update-ccx.ps1", codex_bin / "update-ccx.ps1")

    env = os.environ.copy()
    env["HOME"] = str(home)
    env["USERPROFILE"] = str(home)

    result = subprocess.run(
        [
            pwsh,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(codex_bin / "update-ccx.ps1"),
            "--version",
        ],
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr + result.stdout
    assert (codex_bin / "devkit-lib.ps1").is_file()


def test_update_ccx_ps1_prefers_default_checkout_over_existing_stale_persisted_root(tmp_path):
    pwsh = shutil.which("pwsh")
    if not pwsh:
        pytest.skip("pwsh is not installed")

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
    (stale_scripts / "devkit-lib.ps1").write_text('throw "stale lib"\n', encoding="utf-8")
    (state_dir / "source-root.txt").write_text(f"{stale_root}\n", encoding="utf-8")
    shutil.copyfile(SCRIPTS / "update-ccx.ps1", codex_bin / "update-ccx.ps1")

    env = os.environ.copy()
    env["HOME"] = str(home)
    env["USERPROFILE"] = str(home)

    result = subprocess.run(
        [
            pwsh,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(codex_bin / "update-ccx.ps1"),
            "--version",
        ],
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr + result.stdout
    assert (codex_bin / "devkit-lib.ps1").read_text(encoding="utf-8") != 'throw "stale lib"\n'


def test_update_ccx_ps1_sets_bootstrap_source_root_before_sourcing_lib(tmp_path):
    pwsh = shutil.which("pwsh")
    if not pwsh:
        pytest.skip("pwsh is not installed")

    home = tmp_path / "home"
    codex_bin = home / ".codex" / "bin"
    default_checkout = home / "cursor" / "devkit"
    default_scripts = default_checkout / "plugins" / "devkit" / "scripts"
    codex_bin.mkdir(parents=True)
    default_scripts.mkdir(parents=True)
    (default_scripts / "devkit-lib.ps1").write_text(
        'Set-Content -LiteralPath (Join-Path $env:USERPROFILE "selected-root.txt") -Value $env:DEVKIT_SOURCE_ROOT\n',
        encoding="utf-8",
    )
    shutil.copyfile(SCRIPTS / "update-ccx.ps1", codex_bin / "update-ccx.ps1")

    env = os.environ.copy()
    env["HOME"] = str(home)
    env["USERPROFILE"] = str(home)

    result = subprocess.run(
        [
            pwsh,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(codex_bin / "update-ccx.ps1"),
            "--version",
        ],
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr + result.stdout
    assert (home / "selected-root.txt").read_text(encoding="utf-8").strip() == str(default_checkout)


def test_update_ccx_ps1_sets_normal_source_root_before_sourcing_existing_lib(tmp_path):
    pwsh = shutil.which("pwsh")
    if not pwsh:
        pytest.skip("pwsh is not installed")

    home = tmp_path / "home"
    codex_bin = home / ".codex" / "bin"
    default_checkout = home / "cursor" / "devkit"
    default_scripts = default_checkout / "plugins" / "devkit" / "scripts"
    codex_bin.mkdir(parents=True)
    default_scripts.mkdir(parents=True)
    (codex_bin / "devkit-lib.ps1").write_text(
        'Set-Content -LiteralPath (Join-Path $env:USERPROFILE "selected-root.txt") -Value $env:DEVKIT_SOURCE_ROOT\n',
        encoding="utf-8",
    )
    (default_scripts / "devkit-lib.ps1").write_text("# default lib marker\n", encoding="utf-8")
    shutil.copyfile(SCRIPTS / "update-ccx.ps1", codex_bin / "update-ccx.ps1")

    env = os.environ.copy()
    env["HOME"] = str(home)
    env["USERPROFILE"] = str(home)

    result = subprocess.run(
        [
            pwsh,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(codex_bin / "update-ccx.ps1"),
            "--version",
        ],
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr + result.stdout
    assert (home / "selected-root.txt").read_text(encoding="utf-8").strip() == str(default_checkout)
