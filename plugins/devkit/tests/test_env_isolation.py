"""実ユーザー環境(HOME / USERPROFILE)をテスト・CI smoke が汚染しないことを保証する回帰テスト.

背景: 実インシデントとして ~/.codex/devkit/source-root.txt が削除済み一時ディレクトリを
指す状態になった。最有力の犯人は scripts/ci/windows-updater-smoke.ps1 で、実
USERPROFILE から managed path(.codex/bin, .codex/devkit, .local/bin)を導出して
Remove-Item していた。真犯人の断定に依存せず、このクラスの事故を構造的に塞ぐための
回帰テストを以下の観点で用意する。

1. 静的検査: windows-updater-smoke.ps1 が、ガード用 snapshot 関数の外で実
   $env:USERPROFILE / $env:HOME から managed path を導出していないこと
2. conftest.py の autouse fixture が、os.environ をそのまま継承するサブプロセス
   呼び出しでも実ホームを渡さないこと
3. check_skill_surface.py の run_update_devkit_smoke が USERPROFILE を HOME と
   同じサンドボックス値に設定して子プロセスを起動すること
4. runtime テスト: sync_updater.py の Path.home()、cmd → Git Bash チェーン、
   update-ccx.sh の cygpath 失敗時 USERPROFILE fallback という 3 つの子プロセス
   経路で、テストが管理する疑似ホーム(fake_user_home)配下の sentinel が一切
   変更・削除されないこと

絶対に守ること: sentinel ファイルは必ずこのテストが管理する疑似ホームの中にだけ
作成する。実プロセスの HOME / USERPROFILE(実ユーザー環境)へは絶対に書き込まない。
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import check_skill_surface


ROOT = Path(__file__).resolve().parents[3]
PLUGIN_ROOT = ROOT / "plugins/devkit"
SMOKE_SCRIPT = ROOT / "scripts/ci/windows-updater-smoke.ps1"
SYNC_UPDATER_SCRIPT = PLUGIN_ROOT / "skills/setup/scripts/sync_updater.py"
UPDATE_CCX_SH = PLUGIN_ROOT / "scripts/update-ccx.sh"
UPDATE_CCX_CMD = PLUGIN_ROOT / "scripts/update-ccx.cmd"

MANAGED_RELATIVE_DIRS = (".codex/bin", ".codex/devkit", ".local/bin")
GUARD_FUNCTION_NAME = "Get-RealManagedPathGuardSnapshot"


def _seed_managed_sentinels(fake_home: Path) -> dict[str, Path]:
    """疑似ホーム配下の managed path に sentinel ファイルを置き、パス一覧を返す。"""
    sentinels: dict[str, Path] = {}
    for relative_dir in MANAGED_RELATIVE_DIRS:
        directory = fake_home / relative_dir
        directory.mkdir(parents=True, exist_ok=True)
        sentinel = directory / "SENTINEL.txt"
        sentinel.write_text(f"sentinel:{relative_dir}\n", encoding="utf-8")
        sentinels[relative_dir] = sentinel
    return sentinels


def _assert_sentinels_unchanged(sentinels: dict[str, Path]) -> None:
    for relative_dir, sentinel in sentinels.items():
        assert sentinel.is_file(), f"sentinel が消えている: {relative_dir}"
        assert sentinel.read_text(encoding="utf-8") == f"sentinel:{relative_dir}\n", (
            f"sentinel が書き換えられている: {relative_dir}"
        )


# ---------------------------------------------------------------------------
# 1. 静的検査: ガード用 snapshot 関数の外での実環境 managed path 導出を禁止する
# ---------------------------------------------------------------------------


def _extract_guard_function_span(source: str) -> tuple[int, int]:
    match = re.search(
        rf"function {re.escape(GUARD_FUNCTION_NAME)} \{{.*?\n\}}\n",
        source,
        re.DOTALL,
    )
    assert match, f"{GUARD_FUNCTION_NAME} 関数本体を抽出できない(関数名または構造が変わった)"
    return match.span()


def test_smoke_script_derives_managed_paths_only_inside_guard_snapshot_function():
    source = SMOKE_SCRIPT.read_text(encoding="utf-8")
    start, end = _extract_guard_function_span(source)
    outside = source[:start] + source[end:]

    forbidden_patterns = [
        r"Join-Path\s+\$env:USERPROFILE",
        r"Join-Path\s+\$env:HOME",
    ]
    for pattern in forbidden_patterns:
        found = re.findall(pattern, outside)
        assert not found, (
            f"ガード用 snapshot 関数({GUARD_FUNCTION_NAME})の外で実環境から managed path を"
            f"導出している箇所がある: pattern={pattern} matches={found}"
        )


def test_smoke_script_guard_function_reads_both_userprofile_and_home():
    source = SMOKE_SCRIPT.read_text(encoding="utf-8")
    start, end = _extract_guard_function_span(source)
    guard_body = source[start:end]
    assert "$env:USERPROFILE" in guard_body
    assert "$env:HOME" in guard_body


def test_smoke_script_hard_guard_runs_before_sandbox_directory_is_created():
    source = SMOKE_SCRIPT.read_text(encoding="utf-8")
    guard_call_index = source.index("$guardSnapshot = Get-RealManagedPathGuardSnapshot")
    validate_call_index = source.index("Assert-SandboxCandidateSafe -Candidate $sandboxCandidate")
    create_call_index = source.index("$sandboxRoot = New-SmokeSandboxRoot -Candidate $sandboxCandidate")
    assert guard_call_index < validate_call_index < create_call_index, (
        "ハードガード(snapshot -> 検証)が New-Item によるサンドボックス作成より前に"
        "実行される順序になっていない"
    )


# ---------------------------------------------------------------------------
# 2. conftest.py の autouse fixture が実ホームを渡さないことの有効性検査
# ---------------------------------------------------------------------------


def test_conftest_isolates_home_and_userprofile_for_naive_subprocess_inheritance():
    fake_home = os.environ.get("HOME")
    fake_userprofile = os.environ.get("USERPROFILE")
    assert fake_home, "conftest の autouse fixture が HOME を設定していない"
    assert fake_userprofile, "conftest の autouse fixture が USERPROFILE を設定していない"
    assert fake_home == fake_userprofile, "autouse fixture は HOME と USERPROFILE を同じ疑似ホームに揃えるはず"
    assert "devkit-test-home" in fake_home.replace("\\", "/"), (
        f"HOME が conftest の疑似ホーム命名規則と一致しない(実ホームが漏れている可能性): {fake_home}"
    )

    # os.environ をそのまま継承する「素朴な」サブプロセス呼び出しでも、実ホームではなく
    # conftest が用意した疑似ホームが渡ることを確認する。
    result = subprocess.run(
        [sys.executable, "-c", "import os; print(os.environ.get('HOME')); print(os.environ.get('USERPROFILE'))"],
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        check=True,
    )
    lines = result.stdout.splitlines()
    assert lines[0] == fake_home
    assert lines[1] == fake_userprofile


# ---------------------------------------------------------------------------
# 3. check_skill_surface.py の run_update_devkit_smoke が USERPROFILE を隔離すること
# ---------------------------------------------------------------------------


def test_run_update_devkit_smoke_sets_userprofile_matching_sandboxed_home(monkeypatch):
    real_run = check_skill_surface.subprocess.run
    captured_envs: list[dict[str, str]] = []

    def spy_run(cmd, **kwargs):
        env = kwargs.get("env")
        if env is not None and "DEVKIT_TEST_CALL_LOG" in env:
            captured_envs.append(dict(env))
        return real_run(cmd, **kwargs)

    monkeypatch.setattr(check_skill_surface.subprocess, "run", spy_run)

    # marketplace 名の具体値は premises.json のレジストリ対象なので、ここでは
    # env 隔離だけを検証する最小構成(config_body なし = 未登録マーケットプレース)を使う。
    check_skill_surface.run_update_devkit_smoke(
        "env-isolation-probe",
        config_body=None,
        installed=False,
        available=True,
    )

    assert captured_envs, "update-ccx.sh 起動時の env をキャプチャできなかった"
    for env in captured_envs:
        assert "USERPROFILE" in env, "USERPROFILE が子プロセス env に設定されていない(実 USERPROFILE が漏れる経路)"
        assert env["USERPROFILE"] == env["HOME"], (
            "USERPROFILE がサンドボックス化された HOME と一致していない: "
            f"HOME={env.get('HOME')} USERPROFILE={env.get('USERPROFILE')}"
        )


# ---------------------------------------------------------------------------
# 4. runtime テスト: 3 つの子プロセス経路で疑似ホームの sentinel が不変であること
# ---------------------------------------------------------------------------


@pytest.mark.skipif(os.name != "nt", reason="[platform] HOME/USERPROFILE 分離は Windows 固有の懸念")
def test_sync_updater_path_home_resolves_only_within_isolated_userprofile(tmp_path):
    fake_user_home = tmp_path / "fake-user-home"
    sentinels = _seed_managed_sentinels(fake_user_home)
    normalized_fake_home = str(fake_user_home.resolve())

    def run_check(home_value: Path, userprofile_value: Path) -> dict:
        env = os.environ.copy()
        env["HOME"] = str(home_value)
        env["USERPROFILE"] = str(userprofile_value)
        result = subprocess.run(
            [sys.executable, str(SYNC_UPDATER_SCRIPT), "--check", "--format", "json"],
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
        return json.loads(result.stdout)

    matching = run_check(fake_user_home, fake_user_home)
    assert matching["changed"] is True
    assert matching["actions"], "sync_updater --check がアクションを報告しなかった"
    for action in matching["actions"]:
        _, _, path_part = action.partition(":")
        resolved = Path(path_part).resolve()
        assert str(resolved).startswith(normalized_fake_home), (
            f"Path.home() が疑似ホーム以外を指している可能性がある: {action}"
        )
    _assert_sentinels_unchanged(sentinels)

    # HOME と USERPROFILE が乖離するケース: Python の Path.home() は Windows で
    # USERPROFILE を優先するため、HOME だけ別ディレクトリを指しても結果は変わらず、
    # HOME 側のディレクトリには一切触れないはず。
    mismatched_home = tmp_path / "mismatched-home-should-be-ignored"
    mismatched = run_check(mismatched_home, fake_user_home)
    assert mismatched == matching
    assert not mismatched_home.exists(), "Path.home() が USERPROFILE ではなく HOME 側を実際に参照した"
    _assert_sentinels_unchanged(sentinels)


@pytest.mark.skipif(os.name != "nt", reason="[platform] cmd -> Git Bash チェーンは Windows 固有")
def test_update_ccx_cmd_to_bash_chain_forwards_isolated_home_and_preserves_sentinels(tmp_path):
    bash_candidates = [
        Path(os.environ.get("ProgramFiles", "")) / "Git/bin/bash.exe",
        Path(os.environ.get("ProgramFiles(x86)", "")) / "Git/bin/bash.exe",
    ]
    git = shutil.which("git.exe")
    if git:
        bash_candidates.append(Path(git).parent.parent / "bin/bash.exe")
    if not any(candidate.is_file() for candidate in bash_candidates):
        pytest.skip("[tool:bash] Git for Windows bash is not installed")

    fake_user_home = tmp_path / "fake-user-home"
    sentinels = _seed_managed_sentinels(fake_user_home)
    other_userprofile = tmp_path / "other-userprofile"
    other_userprofile.mkdir()

    def run_chain(label: str, home_value: Path, userprofile_value: Path) -> str:
        installed_bin = tmp_path / f"installed-bin-{label}"
        installed_bin.mkdir()
        shutil.copyfile(UPDATE_CCX_CMD, installed_bin / "update-ccx.cmd")
        # 実 update-ccx.sh の代わりに、cmd -> bash チェーンで実際に見えている $HOME を
        # 観測点として書き出すだけのスタブに差し替える(実処理は動かさない)。
        (installed_bin / "update-ccx.sh").write_text(
            "\n".join(
                [
                    "#!/bin/bash",
                    'out="$(dirname "$0")/../observed-env-' + label + '.txt"',
                    "{",
                    '  if [ -f "$HOME/.codex/bin/SENTINEL.txt" ]; then echo "HOME_SENTINEL_VISIBLE=1"; '
                    'else echo "HOME_SENTINEL_VISIBLE=0"; fi',
                    "} > \"$out\"",
                    "",
                ]
            ),
            encoding="utf-8",
        )

        env = os.environ.copy()
        env["HOME"] = str(home_value)
        env["USERPROFILE"] = str(userprofile_value)

        result = subprocess.run(
            ["cmd.exe", "/d", "/c", str(installed_bin / "update-ccx.cmd")],
            env=env,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        assert result.returncode == 0, result.stdout + result.stderr
        marker = tmp_path / f"observed-env-{label}.txt"
        assert marker.is_file(), f"cmd -> bash チェーンの観測点マーカーが作られなかった: {result.stdout}"
        return marker.read_text(encoding="utf-8")

    matching_observation = run_chain("matching", fake_user_home, fake_user_home)
    assert "HOME_SENTINEL_VISIBLE=1" in matching_observation, (
        f"cmd -> bash チェーンが疑似ホームの HOME を正しく伝播していない: {matching_observation}"
    )
    _assert_sentinels_unchanged(sentinels)

    # HOME と USERPROFILE が異なる値のケース: bash 側の $HOME が USERPROFILE に
    # すり替わっていないことを確認する。
    mismatched_observation = run_chain("mismatched", fake_user_home, other_userprofile)
    assert "HOME_SENTINEL_VISIBLE=1" in mismatched_observation, (
        f"HOME/USERPROFILE 乖離時に bash の $HOME が正しく伝播していない: {mismatched_observation}"
    )
    _assert_sentinels_unchanged(sentinels)


def _truncated_update_ccx_sh(tmp_path: Path) -> Path:
    """update-ccx.sh から末尾の `main "$@"; exit $?` 呼び出しを除いたコピーを作る。

    source しても main() が自動実行されず、個別関数だけを直接呼び出せる。
    update-ccx.sh はトップレベルで `source_devkit_lib_for_update || exit 1` を実行し
    隣接する devkit-lib.sh を要求するため、同じディレクトリへ実物をコピーしておく。
    """
    source = UPDATE_CCX_SH.read_text(encoding="utf-8")
    lines = source.splitlines()
    assert lines[-1].strip() == 'main "$@"; exit $?', "update-ccx.sh の末尾行の前提が変わった(要更新)"
    truncated = "\n".join(lines[:-1]) + "\n"
    lib_path = tmp_path / "update-ccx-lib.sh"
    lib_path.write_text(truncated, encoding="utf-8")
    shutil.copyfile(UPDATE_CCX_SH.parent / "devkit-lib.sh", tmp_path / "devkit-lib.sh")
    return lib_path


@pytest.mark.skipif(os.name != "nt", reason="[platform] cygpath fallback は Windows 固有")
def test_update_ccx_cygpath_failure_userprofile_fallback_preserves_sentinels(tmp_path):
    bash = shutil.which("bash")
    if not bash:
        pytest.skip("[tool:bash] bash が見つからない")

    fake_user_home = tmp_path / "fake-user-home"
    sentinels = _seed_managed_sentinels(fake_user_home)
    lib_script = _truncated_update_ccx_sh(tmp_path)

    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()

    def run_fallback(label: str, home_value: Path, userprofile_value: Path) -> tuple[subprocess.CompletedProcess, Path]:
        ps_log = tmp_path / f"powershell-calls-{label}.log"
        check_skill_surface.write_executable(
            fake_bin / "powershell.exe",
            "\n".join(
                [
                    "#!/bin/sh",
                    'printf \'DEVKIT_WINDOWS_HOME=%s\\n\' "$DEVKIT_WINDOWS_HOME" >> '
                    + check_skill_surface.shell_path(ps_log),
                    "exit 0",
                    "",
                ]
            ),
        )

        env = os.environ.copy()
        env["HOME"] = str(home_value)
        env["USERPROFILE"] = str(userprofile_value)
        env["PATH"] = f"{fake_bin}{os.pathsep}{env.get('PATH', '')}"

        # cygpath は PATH 上の stub では shadow できない。CI の Git Bash は
        # 拡張子なしの stub を実行可能と見なさず実 cygpath.exe を解決してしまい、
        # fallback 分岐に入らなかった(実際に devkit-checks-windows が落ちた)。
        # 同一シェル内の関数定義なら外部コマンドより優先され、`command -v` も
        # 成功するため、環境に依存せず決定論的に失敗させられる。
        script = "\n".join(
            [
                "set -euo pipefail",
                f"source {check_skill_surface.shell_path(lib_script)}",
                "cygpath() { return 1; }",
                f'install_windows_codex_config "{fake_user_home.as_posix()}/.codex/bin/devkit-codex-config.ps1"',
            ]
        )
        result = subprocess.run(
            [bash, "-c", script],
            env=env,
            cwd=tmp_path,
            capture_output=True,
            text=True,
        )
        return result, ps_log

    matching_result, matching_log = run_fallback("matching", fake_user_home, fake_user_home)
    assert matching_result.returncode == 0, matching_result.stdout + matching_result.stderr
    assert "USERPROFILE fallback" in matching_result.stderr, matching_result.stderr
    assert matching_log.is_file(), "cygpath fallback 分岐が発火せず powershell.exe が呼ばれなかった"
    assert f"DEVKIT_WINDOWS_HOME={fake_user_home}" in matching_log.read_text(encoding="utf-8")
    _assert_sentinels_unchanged(sentinels)

    # HOME と USERPROFILE が異なる値のケース。fallback は仕様どおり USERPROFILE を
    # 使うため、疑似 USERPROFILE 側へ渡ることは許容しつつ、HOME 側の sentinel が
    # 一切変更・削除されないことを確認する。
    other_userprofile = tmp_path / "other-userprofile-fallback"
    other_userprofile.mkdir()
    mismatched_result, mismatched_log = run_fallback("mismatched", fake_user_home, other_userprofile)
    assert mismatched_result.returncode == 0, mismatched_result.stdout + mismatched_result.stderr
    assert "USERPROFILE fallback" in mismatched_result.stderr, mismatched_result.stderr
    assert mismatched_log.is_file()
    assert f"DEVKIT_WINDOWS_HOME={other_userprofile}" in mismatched_log.read_text(encoding="utf-8")
    _assert_sentinels_unchanged(sentinels)
