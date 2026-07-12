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


def run_git(*args: str, cwd: Path | None = None) -> None:
    subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def test_ensure_devkit_repo_root_reuses_detached_head_checkout(tmp_path):
    source = tmp_path / "source"
    checkout = tmp_path / "checkout"
    plugin_root = source / "plugins" / "devkit"
    scripts = plugin_root / "scripts"

    for directory in (plugin_root / "skills", scripts, plugin_root / "templates"):
        directory.mkdir(parents=True)
        (directory / ".gitkeep").touch()
    shutil.copyfile(SCRIPTS / "devkit-lib.sh", scripts / "devkit-lib.sh")

    run_git("init", "--initial-branch=main", str(source))
    run_git("config", "user.email", "devkit-test@example.com", cwd=source)
    run_git("config", "user.name", "DevKit Test", cwd=source)
    run_git("add", ".", cwd=source)
    run_git("commit", "-m", "test fixture", cwd=source)
    run_git("clone", str(source), str(checkout))
    run_git("checkout", "--detach", cwd=checkout)

    env = os.environ.copy()
    env["DEVKIT_SOURCE_ROOT"] = checkout.as_posix()
    result = subprocess.run(
        [
            bash_path(),
            "-c",
            'source "$DEVKIT_SOURCE_ROOT/plugins/devkit/scripts/devkit-lib.sh" '
            "&& ensure_devkit_repo_root",
        ],
        env=env,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "Detached HEAD checkout. Reusing the existing DevKit checkout." in output
    assert "DEVKIT_REPO_PULL_FAILED" not in output


def test_get_devkit_repo_root_reuses_detached_head_checkout_in_powershell(tmp_path):
    pwsh = shutil.which("pwsh")
    if not pwsh:
        pytest.skip("pwsh is not installed")

    source = tmp_path / "source"
    checkout = tmp_path / "checkout"
    plugin_root = source / "plugins" / "devkit"
    scripts = plugin_root / "scripts"

    for directory in (plugin_root / "skills", scripts, plugin_root / "templates"):
        directory.mkdir(parents=True)
        (directory / ".gitkeep").touch()
    shutil.copyfile(SCRIPTS / "devkit-lib.ps1", scripts / "devkit-lib.ps1")

    run_git("init", "--initial-branch=main", str(source))
    run_git("config", "user.email", "devkit-test@example.com", cwd=source)
    run_git("config", "user.name", "DevKit Test", cwd=source)
    run_git("add", ".", cwd=source)
    run_git("commit", "-m", "test fixture", cwd=source)
    run_git("clone", str(source), str(checkout))
    run_git("checkout", "--detach", cwd=checkout)

    env = os.environ.copy()
    env["DEVKIT_SOURCE_ROOT"] = str(checkout)
    result = subprocess.run(
        [
            pwsh,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            '. "$env:DEVKIT_SOURCE_ROOT/plugins/devkit/scripts/devkit-lib.ps1"; '
            "Get-DevKitRepoRoot -UserHome $env:USERPROFILE "
            "-Logger { param($message) Write-Output $message }",
        ],
        env=env,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "Detached HEAD checkout. Reusing the existing DevKit checkout." in output
    assert "DEVKIT_REPO_PULL_FAILED" not in output
