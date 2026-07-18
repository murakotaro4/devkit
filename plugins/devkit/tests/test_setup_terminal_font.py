from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "plugins/devkit/skills/setup/scripts/setup_terminal_font.py"
SPEC = importlib.util.spec_from_file_location("setup_terminal_font", SCRIPT)
assert SPEC and SPEC.loader
terminal_font = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(terminal_font)
UDEV_NAMES = tuple(terminal_font.EXPECTED_VALUE_NAMES)


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


def make_font_zip(path: Path, *, omit: str | None = None) -> str:
    with zipfile.ZipFile(path, "w") as bundle:
        for member in terminal_font.FONT_MEMBERS.values():
            if member != omit:
                bundle.writestr(member, f"dummy:{member}".encode())
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
        (list(UDEV_NAMES), True),
        (list(UDEV_NAMES[:-1]), False),
        (["UDEV Gothic 35NF Regular (TrueType)", *UDEV_NAMES[1:]], False),
    ],
)
def test_font_family_detection(tmp_path: Path, names: list[str], installed: bool):
    fonts = tmp_path / "fonts.txt"
    settings = tmp_path / "settings.json"
    make_font_names(fonts, *names)
    make_settings(settings)
    result = run_script(*windows_args(settings, fonts, "--check"))
    assert result["font_installed"] is installed


def test_local_zip_installs_all_styles_and_updates_settings(tmp_path: Path):
    fonts = tmp_path / "fonts.txt"
    fonts_dir = tmp_path / "installed-fonts"
    settings = tmp_path / "settings.json"
    archive = tmp_path / "font.zip"
    make_font_names(fonts, UDEV_NAMES[0])
    make_settings(settings)
    digest = make_font_zip(archive)
    result = run_script(
        *windows_args(
            settings, fonts, "--font-zip", archive,
            "--expected-sha256", digest, "--fonts-dir", fonts_dir,
        )
    )
    assert result["font_installed"] is True
    assert result["download"] == "downloaded"
    assert result["settings"][0]["changed"] is True
    assert {path.name for path in fonts_dir.iterdir()} == {
        Path(member).name for member in terminal_font.FONT_MEMBERS.values()
    }
    assert fonts.read_text(encoding="utf-8").splitlines() == list(UDEV_NAMES)
    data = json.loads(settings.read_text(encoding="utf-8"))
    assert data["profiles"]["defaults"]["font"]["face"] == "UDEV Gothic NF"


def test_hash_mismatch_does_not_write_settings(tmp_path: Path):
    fonts = tmp_path / "fonts.txt"
    settings = tmp_path / "settings.json"
    archive = tmp_path / "font.zip"
    make_font_names(fonts)
    make_settings(settings)
    make_font_zip(archive)
    original = settings.read_bytes()
    result = run_script(*windows_args(settings, fonts, "--font-zip", archive, "--expected-sha256", "0" * 64))
    assert result["download"] == "hash-mismatch"
    assert result["settings"] == []
    assert settings.read_bytes() == original


def test_missing_zip_member_does_not_write_settings(tmp_path: Path):
    fonts = tmp_path / "fonts.txt"
    settings = tmp_path / "settings.json"
    archive = tmp_path / "font.zip"
    make_font_names(fonts)
    make_settings(settings)
    digest = make_font_zip(archive, omit=next(iter(terminal_font.FONT_MEMBERS.values())))
    original = settings.read_bytes()
    result = run_script(*windows_args(settings, fonts, "--font-zip", archive, "--expected-sha256", digest))
    assert result["download"] == "failed"
    assert result["settings"] == []
    assert settings.read_bytes() == original


def test_missing_local_zip_is_download_failure(tmp_path: Path):
    fonts = tmp_path / "fonts.txt"
    settings = tmp_path / "settings.json"
    make_font_names(fonts)
    make_settings(settings)
    original = settings.read_bytes()
    result = run_script(*windows_args(settings, fonts, "--font-zip", tmp_path / "missing.zip"))
    assert result["download"] == "failed"
    assert result["settings"] == []
    assert settings.read_bytes() == original


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
    make_font_names(fonts, *UDEV_NAMES)
    make_settings(settings, content)
    had_bom = settings.read_bytes().startswith(b"\xef\xbb\xbf")
    result = run_script(*windows_args(settings, fonts))
    assert result["settings"][0]["changed"] is True
    assert Path(result["settings"][0]["backup"]).exists()
    raw = settings.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf") is had_bom
    data = json.loads(raw.decode("utf-8-sig"))
    assert data["profiles"]["defaults"]["font"]["face"] == "UDEV Gothic NF"


def test_jsonc_trailing_comma_cleanup_preserves_string_content(tmp_path: Path):
    fonts = tmp_path / "fonts.txt"
    settings = tmp_path / "settings.json"
    make_font_names(fonts, *UDEV_NAMES)
    make_settings(settings, '{"literal": ",} and ,]", // comment\n "profiles": {},}\n')
    result = run_script(*windows_args(settings, fonts))
    assert result["settings"][0]["changed"] is True
    data = json.loads(settings.read_text())
    assert data["literal"] == ",} and ,]"


def test_backup_collision_and_second_run_noop(tmp_path: Path):
    fonts = tmp_path / "fonts.txt"
    settings = tmp_path / "settings.json"
    make_font_names(fonts, *UDEV_NAMES)
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
    make_font_names(fonts, *UDEV_NAMES)
    make_settings(settings, content)
    original = settings.read_bytes()
    result = run_script(*windows_args(settings, fonts))
    assert "error" in result["settings"][0]
    assert settings.read_bytes() == original
    assert not (settings.parent / "devkit-font-backup").exists()


def test_check_never_reads_zip_or_changes_files(tmp_path: Path):
    fonts = tmp_path / "fonts.txt"
    settings = tmp_path / "settings.json"
    missing_archive = tmp_path / "missing.zip"
    make_font_names(fonts)
    make_settings(settings)
    original = settings.read_bytes()
    result = run_script(*windows_args(settings, fonts, "--font-zip", missing_archive, "--check"))
    assert result["reason"] == "font-not-registered"
    assert not missing_archive.exists()
    assert settings.read_bytes() == original
    assert not (settings.parent / "devkit-font-backup").exists()


def test_check_reports_would_change_for_registered_font(tmp_path: Path):
    fonts = tmp_path / "fonts.txt"
    settings = tmp_path / "settings.json"
    make_font_names(fonts, *UDEV_NAMES)
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
