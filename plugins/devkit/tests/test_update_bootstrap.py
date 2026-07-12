from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "plugins" / "devkit" / "scripts"


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
    require_symlink_support()
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
    require_symlink_support()
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
    require_symlink_support()
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


def test_update_ccx_ps1_preserves_existing_source_root(tmp_path):
    pwsh = shutil.which("pwsh")
    if not pwsh:
        pytest.skip("pwsh is not installed")

    home = tmp_path / "home"
    codex_bin = home / ".codex" / "bin"
    default_checkout = home / "cursor" / "devkit"
    default_scripts = default_checkout / "plugins" / "devkit" / "scripts"
    caller_source_root = tmp_path / "caller-source"
    codex_bin.mkdir(parents=True)
    default_scripts.mkdir(parents=True)
    caller_source_root.mkdir()
    (codex_bin / "devkit-lib.ps1").write_text(
        'Set-Content -LiteralPath (Join-Path $env:USERPROFILE "selected-root.txt") -Value $env:DEVKIT_SOURCE_ROOT\n',
        encoding="utf-8",
    )
    (default_scripts / "devkit-lib.ps1").write_text("# default lib marker\n", encoding="utf-8")
    shutil.copyfile(SCRIPTS / "update-ccx.ps1", codex_bin / "update-ccx.ps1")

    env = os.environ.copy()
    env["HOME"] = str(home)
    env["USERPROFILE"] = str(home)
    env["DEVKIT_SOURCE_ROOT"] = str(caller_source_root)

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
    assert (home / "selected-root.txt").read_text(encoding="utf-8").strip() == str(caller_source_root)


# devkit-lib.ps1 の dot-source をスクリプトトップレベルで行うことを PowerShell AST で検証する。
# v7.0.1 未満の update-ccx.ps1 は Import-DevKitLibForUpdate 関数の内側で devkit-lib.ps1 を
# dot-source していた。PowerShell は関数内 dot-source のスコープを関数 return と同時に破棄する
# ため、後段の Section-DevKit が Get-DevKitRepoRoot を解決できず必ず失敗していた (PR #5)。
# この回帰を検知するため、regex による行マッチではなく AST で構造を検証する。
_AST_SCOPE_CHECK_SCRIPT = r"""
param(
  [Parameter(Mandatory = $true)]
  [string]$ScriptPath
)

$ErrorActionPreference = "Stop"

$tokens = $null
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($ScriptPath, [ref]$tokens, [ref]$parseErrors)

if ($parseErrors.Count -gt 0) {
  Write-Host ("FAIL: parse errors: {0}" -f (($parseErrors | ForEach-Object { $_.Message }) -join " | "))
  exit 1
}

function Test-HasChildScopeAncestor([System.Management.Automation.Language.Ast]$Node) {
  $current = $Node.Parent
  while ($null -ne $current) {
    if ($current -is [System.Management.Automation.Language.FunctionDefinitionAst]) {
      return $true
    }
    if ($current -is [System.Management.Automation.Language.ScriptBlockExpressionAst]) {
      return $true
    }
    $current = $current.Parent
  }
  return $false
}

function Test-TargetsDevKitLib([System.Management.Automation.Language.CommandAst]$CmdAst) {
  if ($CmdAst.CommandElements.Count -eq 0) {
    return $false
  }
  $targetText = $CmdAst.CommandElements[0].Extent.Text
  if ($targetText -match "Resolve-DevKitLibForUpdate") {
    return $true
  }
  if ($targetText -match "devkit-lib\.ps1") {
    return $true
  }
  return $false
}

$allCommandAsts = @($ast.FindAll({ param($node) $node -is [System.Management.Automation.Language.CommandAst] }, $true))

$dotSourceAsts = @($allCommandAsts | Where-Object { $_.InvocationOperator -eq [System.Management.Automation.Language.TokenKind]::Dot })

$devkitLibDotSources = @($dotSourceAsts | Where-Object { Test-TargetsDevKitLib $_ })

if ($devkitLibDotSources.Count -ne 1) {
  Write-Host ("FAIL: expected exactly 1 dot-source targeting Resolve-DevKitLibForUpdate/devkit-lib.ps1, found {0}" -f $devkitLibDotSources.Count)
  exit 1
}

$devkitLibDotSource = $devkitLibDotSources[0]

if (Test-HasChildScopeAncestor $devkitLibDotSource) {
  Write-Host "FAIL: devkit-lib dot-source has a FunctionDefinitionAst/ScriptBlockExpressionAst ancestor (child-scoped, not script-level)"
  exit 1
}

$topLevelMainCalls = @($allCommandAsts | Where-Object {
  ($_.GetCommandName() -eq "Main") -and -not (Test-HasChildScopeAncestor $_)
})

if ($topLevelMainCalls.Count -ne 1) {
  Write-Host ("FAIL: expected exactly 1 top-level Main invocation, found {0}" -f $topLevelMainCalls.Count)
  exit 1
}

$mainCall = $topLevelMainCalls[0]

if ($devkitLibDotSource.Extent.StartOffset -ge $mainCall.Extent.StartOffset) {
  Write-Host "FAIL: devkit-lib dot-source must precede the top-level Main invocation"
  exit 1
}

$childScopedDevKitLibDotSources = @($dotSourceAsts | Where-Object {
  (Test-TargetsDevKitLib $_) -and (Test-HasChildScopeAncestor $_)
})

if ($childScopedDevKitLibDotSources.Count -ne 0) {
  Write-Host ("FAIL: found {0} devkit-lib dot-source(s) nested inside a function definition or script block expression" -f $childScopedDevKitLibDotSources.Count)
  exit 1
}

Write-Host "OK"
exit 0
"""


def test_update_ccx_ps1_dot_sources_devkit_lib_at_script_scope(tmp_path):
    pwsh = shutil.which("pwsh")
    if not pwsh:
        pytest.skip("pwsh is not installed")

    checker_path = tmp_path / "check_dot_source_scope.ps1"
    checker_path.write_text(_AST_SCOPE_CHECK_SCRIPT, encoding="utf-8")

    result = subprocess.run(
        [
            pwsh,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(checker_path),
            "-ScriptPath",
            str(SCRIPTS / "update-ccx.ps1"),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr + result.stdout
    assert "OK" in result.stdout
