from __future__ import annotations

import importlib.util
import json
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import require_symlink_support


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "plugins/devkit/skills/setup/scripts/sync_claude_env.py"
EXPECTED_ENV = {
    "CLAUDE_CODE_AUTO_COMPACT_WINDOW": "1000000",
    "CLAUDE_AUTOCOMPACT_PCT_OVERRIDE": "50",
}


def _load_module():
    spec = importlib.util.spec_from_file_location("sync_claude_env_under_test", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(path: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--settings-file", str(path), *args, "--format", "json"],
        check=check,
        capture_output=True,
        text=True,
    )


def _payload(result: subprocess.CompletedProcess[str]) -> dict[str, object]:
    return json.loads(result.stdout)


def test_creates_settings_and_is_idempotent(tmp_path: Path):
    settings = tmp_path / ".claude/settings.json"
    first = _payload(_run(settings))
    assert first["changed"] is True
    assert json.loads(settings.read_text(encoding="utf-8")) == {"env": EXPECTED_ENV}

    second = _payload(_run(settings))
    assert second == {"actions": [], "changed": False, "skipped": True}


def test_merges_without_losing_other_keys_and_preserves_mode(tmp_path: Path):
    settings = tmp_path / "settings.json"
    settings.write_text(
        json.dumps({"theme": "dark", "env": {"OTHER": "kept"}}), encoding="utf-8"
    )
    settings.chmod(0o640)
    original_mode = stat.S_IMODE(settings.stat().st_mode)

    _run(settings)
    value = json.loads(settings.read_text(encoding="utf-8"))
    assert value == {"theme": "dark", "env": {"OTHER": "kept", **EXPECTED_ENV}}
    assert stat.S_IMODE(settings.stat().st_mode) == original_mode


def test_check_reports_change_without_writing_or_backing_up(tmp_path: Path):
    settings = tmp_path / "settings.json"
    original = b'{"env":{"OTHER":"value"}}\n'
    settings.write_bytes(original)

    payload = _payload(_run(settings, "--check"))
    assert payload["changed"] is True
    assert settings.read_bytes() == original
    assert not (tmp_path / "devkit-env-backup").exists()


@pytest.mark.parametrize(
    "content",
    [b"{broken", b"[]", b'{"env":null}', b'{"env":[]}', b'{"env":"bad"}'],
)
def test_invalid_json_shapes_fail_without_changes(tmp_path: Path, content: bytes):
    settings = tmp_path / "settings.json"
    settings.write_bytes(content)

    result = _run(settings, check=False)
    assert result.returncode != 0
    assert settings.read_bytes() == content
    assert _payload(result)["changed"] is False


def test_directory_target_fails_without_changes(tmp_path: Path):
    settings = tmp_path / "settings.json"
    settings.mkdir()

    result = _run(settings, check=False)
    assert result.returncode != 0
    assert settings.is_dir()


def test_symlink_target_fails_without_changes(tmp_path: Path):
    require_symlink_support()
    target = tmp_path / "target.json"
    target.write_text("{}", encoding="utf-8")
    settings = tmp_path / "settings.json"
    settings.symlink_to(target)

    result = _run(settings, check=False)
    assert result.returncode != 0
    assert target.read_text(encoding="utf-8") == "{}"
    assert settings.is_symlink()


def test_backup_failure_prevents_settings_write(tmp_path: Path):
    settings = tmp_path / "settings.json"
    original = b'{"other":true}\n'
    settings.write_bytes(original)
    (tmp_path / "devkit-env-backup").write_text("blocks directory creation", encoding="utf-8")

    result = _run(settings, check=False)
    assert result.returncode != 0
    assert settings.read_bytes() == original


def test_incomplete_backup_is_removed_on_fsync_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    module = _load_module()
    settings = tmp_path / "settings.json"
    original = b'{"other":true}\n'
    settings.write_bytes(original)

    def fail_fsync(_fd: int) -> None:
        raise OSError("simulated fsync failure")

    monkeypatch.setattr(module.os, "fsync", fail_fsync)
    with pytest.raises(OSError, match="simulated fsync failure"):
        module.sync(settings, False)

    assert settings.read_bytes() == original
    assert list((tmp_path / "devkit-env-backup").glob("*.bak")) == []


def test_existing_file_gets_timestamped_backup(tmp_path: Path):
    settings = tmp_path / "settings.json"
    original = b'{"other":true}\n'
    settings.write_bytes(original)

    _run(settings)
    backups = list((tmp_path / "devkit-env-backup").glob("settings.json.*Z.bak"))
    assert len(backups) == 1
    assert backups[0].read_bytes() == original
