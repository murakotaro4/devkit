from __future__ import annotations

import json
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "plugins/devkit/skills/setup/scripts/setup_terminal_font.py"
SPEC = importlib.util.spec_from_file_location("setup_terminal_font", SCRIPT)
assert SPEC and SPEC.loader
terminal_font = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(terminal_font)


def run_script(*args: object) -> dict[str, object]:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), *(str(arg) for arg in args), "--format", "json"],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def make_settings(path: Path, content: bytes | str = '{}\n') -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content, encoding="utf-8")


def make_font_names(path: Path, *names: str) -> None:
    path.write_text("\n".join(names) + "\n", encoding="utf-8")


def make_winget(path: Path, body: str) -> Path:
    if os.name == "nt":
        # Windows は shebang を解釈しないため、python 本体を .cmd 経由で起動する
        impl = path.with_name(path.name + "-impl.py")
        impl.write_text(body + "\n", encoding="utf-8")
        cmd = path.with_name(path.name + ".cmd")
        cmd.write_text(f'@echo off\r\n"{sys.executable}" "{impl}" %*\r\n', encoding="utf-8")
        return cmd
    path.write_text(f"#!{sys.executable}\n{body}\n", encoding="utf-8")
    path.chmod(0o755)
    return path


def windows_args(settings: Path, fonts: Path, *extra: object) -> tuple[object, ...]:
    return ("--platform", "Windows", "--settings-path", settings, "--font-names-file", fonts, *extra)


def test_non_windows_is_skipped():
    result = run_script("--platform", "Linux")
    assert result["status"] == "skip"
    assert result["reason"] == "windows-only"


def test_platform_override_beats_windir():
    # 実 Windows ホスト(WINDIR あり)でも明示 --platform を優先して skip する
    env = {**os.environ, "WINDIR": "C:\\Windows"}
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--platform", "Linux", "--format", "json"],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    result = json.loads(completed.stdout)
    assert result["status"] == "skip"
    assert result["reason"] == "windows-only"


@pytest.mark.parametrize(
    ("names", "installed"),
    [
        (["JetBrainsMono NF Regular (TrueType)"], True),
        (["JetBrainsMono NF Bold Italic (OpenType)"], True),
        (["JetBrainsMono NF ExtraLight Italic (TrueType)"], True),
        (["JetBrainsMono NFM Bold (TrueType)"], False),
        (["JetBrainsMono NFP Regular (TrueType)"], False),
        (["JetBrainsMonoNL NF Regular (TrueType)"], False),
        (["JetBrainsMono Nerd Font Regular (TrueType)"], False),
    ],
)
def test_font_family_detection(tmp_path: Path, names: list[str], installed: bool):
    fonts = tmp_path / "fonts.txt"
    settings = tmp_path / "settings.json"
    make_font_names(fonts, *names)
    make_settings(settings)
    result = run_script(*windows_args(settings, fonts, "--check"))
    assert result["font_installed"] is installed


def test_fake_winget_arguments_and_successful_redetection(tmp_path: Path):
    fonts = tmp_path / "fonts.txt"
    settings = tmp_path / "settings.json"
    calls = tmp_path / "calls.json"
    make_font_names(fonts)
    make_settings(settings)
    winget = make_winget(
        tmp_path / "winget",
        f"import json, pathlib, sys\npathlib.Path({str(calls)!r}).write_text(json.dumps(sys.argv[1:]))\n"
        f"pathlib.Path({str(fonts)!r}).write_text('JetBrainsMono NF Regular (TrueType)\\n')",
    )
    result = run_script(*windows_args(settings, fonts, "--winget-cmd", winget))
    assert result["font_installed"] is True
    assert result["settings"][0]["changed"] is True
    assert json.loads(calls.read_text()) == [
        "install", "--id", "DEVCOM.JetBrainsMonoNerdFont", "--exact", "--silent",
        "--accept-package-agreements", "--accept-source-agreements",
    ]


def test_winget_success_without_registration_does_not_write(tmp_path: Path):
    fonts = tmp_path / "fonts.txt"
    settings = tmp_path / "settings.json"
    make_font_names(fonts)
    make_settings(settings)
    original = settings.read_bytes()
    winget = make_winget(tmp_path / "winget", "raise SystemExit(0)")
    result = run_script(*windows_args(settings, fonts, "--winget-cmd", winget))
    assert result["reason"] == "font-not-registered"
    assert result["settings"] == []
    assert "Restart Windows" in result["actions"][0]
    assert settings.read_bytes() == original


def test_winget_failure_does_not_write(tmp_path: Path):
    fonts = tmp_path / "fonts.txt"
    settings = tmp_path / "settings.json"
    make_font_names(fonts)
    make_settings(settings)
    winget = make_winget(tmp_path / "winget", "import sys\nprint('package failed', file=sys.stderr)\nraise SystemExit(9)")
    result = run_script(*windows_args(settings, fonts, "--winget-cmd", winget))
    assert result["winget"] == "failed"
    assert "package failed" in result["actions"][0]
    assert result["settings"] == []


def test_missing_winget_includes_manual_install_guidance(tmp_path: Path):
    fonts = tmp_path / "fonts.txt"
    settings = tmp_path / "settings.json"
    make_font_names(fonts)
    make_settings(settings)
    result = run_script(*windows_args(settings, fonts, "--winget-cmd", tmp_path / "missing"))
    assert result["winget"] == "missing"
    assert "nerdfonts.com" in result["actions"][0]
    assert result["settings"] == []


@pytest.mark.parametrize(
    "content",
    [
        '{}\n',
        '{ // comment\n "profiles": {"defaults": {}}\n}\n',
        '{"profiles": {"defaults": {},},}\n',
        b'\xef\xbb\xbf{"profiles": {}}\n',
    ],
)
def test_json_jsonc_trailing_comma_and_bom_are_updated(tmp_path: Path, content: bytes | str):
    fonts = tmp_path / "fonts.txt"
    settings = tmp_path / "settings.json"
    make_font_names(fonts, "JetBrainsMono NF Regular (TrueType)")
    make_settings(settings, content)
    had_bom = settings.read_bytes().startswith(b"\xef\xbb\xbf")
    result = run_script(*windows_args(settings, fonts))
    assert result["settings"][0]["changed"] is True
    assert Path(result["settings"][0]["backup"]).exists()
    raw = settings.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf") is had_bom
    data = json.loads(raw.decode("utf-8-sig"))
    assert data["profiles"]["defaults"]["font"]["face"] == "JetBrainsMono NF"


def test_jsonc_trailing_comma_cleanup_preserves_string_content(tmp_path: Path):
    fonts = tmp_path / "fonts.txt"
    settings = tmp_path / "settings.json"
    make_font_names(fonts, "JetBrainsMono NF Regular (TrueType)")
    make_settings(settings, '{"literal": ",} and ,]", // comment\n "profiles": {},}\n')
    result = run_script(*windows_args(settings, fonts))
    assert result["settings"][0]["changed"] is True
    data = json.loads(settings.read_text())
    assert data["literal"] == ",} and ,]"


def test_backup_collision_and_second_run_noop(tmp_path: Path):
    fonts = tmp_path / "fonts.txt"
    settings = tmp_path / "settings.json"
    make_font_names(fonts, "JetBrainsMono NF Regular (TrueType)")
    make_settings(settings, '{"profiles":{"defaults":{"font":{"face":"Other"}}}}')
    first = run_script(*windows_args(settings, fonts))
    first_backup = Path(first["settings"][0]["backup"])
    make_settings(settings, '{"profiles":{"defaults":{"font":{"face":"Other"}}}}')
    second = run_script(*windows_args(settings, fonts))
    second_backup = Path(second["settings"][0]["backup"])
    # 秒境界を跨ぐと衝突サフィックスは付かないため、名前の形は検査しない
    # (衝突サフィックスの決定論的検査は test_backup_path_collision_suffix)
    assert first_backup != second_backup
    third = run_script(*windows_args(settings, fonts))
    assert third["settings"][0] == {"path": str(settings), "changed": False, "backup": None}
    assert len(list(first_backup.parent.iterdir())) == 2


def test_backup_path_collision_suffix(tmp_path: Path):
    from datetime import datetime, timezone

    settings = tmp_path / "settings.json"
    settings.write_text("{}", encoding="utf-8")
    now = datetime(2026, 7, 12, 15, 8, 52, tzinfo=timezone.utc)
    first = terminal_font.backup_path_for(settings, now=now)
    assert first.name == "settings.json.20260712T150852Z"
    first.parent.mkdir(parents=True)
    first.write_text("x", encoding="utf-8")
    second = terminal_font.backup_path_for(settings, now=now)
    assert second.name == "settings.json.20260712T150852Z-1"
    second.write_text("x", encoding="utf-8")
    third = terminal_font.backup_path_for(settings, now=now)
    assert third.name == "settings.json.20260712T150852Z-2"


@pytest.mark.parametrize(
    "content",
    [
        "{broken",
        '{"profiles": {}} /*',
        "[]",
        '{"profiles": []}',
        '{"profiles": {"defaults": []}}',
        '{"profiles":{"defaults":{"font":[]}}}',
    ],
)
def test_invalid_json_and_unexpected_structures_are_unchanged(tmp_path: Path, content: str):
    fonts = tmp_path / "fonts.txt"
    settings = tmp_path / "settings.json"
    make_font_names(fonts, "JetBrainsMono NF Regular (TrueType)")
    make_settings(settings, content)
    original = settings.read_bytes()
    result = run_script(*windows_args(settings, fonts))
    assert "error" in result["settings"][0]
    assert settings.read_bytes() == original
    assert not (settings.parent / "devkit-font-backup").exists()


def test_check_never_runs_winget_or_changes_files(tmp_path: Path):
    fonts = tmp_path / "fonts.txt"
    settings = tmp_path / "settings.json"
    called = tmp_path / "called"
    make_font_names(fonts)
    make_settings(settings)
    original = settings.read_bytes()
    winget = make_winget(tmp_path / "winget", f"import pathlib\npathlib.Path({str(called)!r}).touch()")
    result = run_script(*windows_args(settings, fonts, "--winget-cmd", winget, "--check"))
    assert result["reason"] == "font-not-registered"
    assert not called.exists()
    assert settings.read_bytes() == original
    assert not (settings.parent / "devkit-font-backup").exists()


def test_check_reports_would_change_for_registered_font(tmp_path: Path):
    fonts = tmp_path / "fonts.txt"
    settings = tmp_path / "settings.json"
    make_font_names(fonts, "JetBrainsMono NF Regular (TrueType)")
    make_settings(settings)
    result = run_script(*windows_args(settings, fonts, "--check"))
    assert result["settings"][0]["would_change"] is True
    assert settings.read_text() == '{}\n'


def test_backup_failure_is_reported_and_later_candidate_continues(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    first = tmp_path / "first/settings.json"
    second = tmp_path / "second/settings.json"
    make_settings(first)
    make_settings(second)
    original = first.read_bytes()
    real_copy2 = terminal_font.shutil.copy2

    def fail_first_copy(source: Path, destination: Path) -> object:
        if Path(source) == first:
            raise OSError("backup denied")
        return real_copy2(source, destination)

    monkeypatch.setattr(terminal_font.shutil, "copy2", fail_first_copy)
    first_result = terminal_font.inspect_or_update(first, check=False)
    second_result = terminal_font.inspect_or_update(second, check=False)
    assert first_result["reason"] == "backup-failed"
    assert first.read_bytes() == original
    assert second_result["changed"] is True
