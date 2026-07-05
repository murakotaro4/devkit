"""statusline Node 実装の契約テスト."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
STATUSLINE = REPO_ROOT / "plugins" / "devkit" / "statusline" / "statusline.js"
INSTALL = REPO_ROOT / "plugins" / "devkit" / "statusline" / "install.js"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _strip_ansi(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


def _node_env(tmp_path: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["HOME"] = str(tmp_path / "home")
    env["DEVKIT_STATUSLINE_CACHE_DIR"] = str(tmp_path / "cache")
    return env


def test_statusline_static_contract():
    text = _read(STATUSLINE)

    assert "rate_limits" in text
    assert "five_hour" in text
    assert "seven_day" in text
    assert "used_percentage" in text
    assert "remaining_percentage" in text
    assert "context_window" in text
    assert "os.tmpdir()" in text
    assert '"/tmp/' not in text and "'/tmp/" not in text
    assert 'process.platform === "darwin"' in text
    assert 'process.platform !== "win32"' in text
    assert "DEVKIT_STATUSLINE_NO_FETCH" in text
    assert "CACHE_TTL_SECONDS = 60" in text
    assert "CACHE_STALE_SECONDS = 300" in text
    assert "total_cost_usd" in text
    assert "open.er-api.com/v6/latest/USD" in text
    assert "FX_CACHE_TTL_SECONDS = 86400" in text
    assert "FX_FAILURE_TTL_SECONDS = 300" in text
    assert "fx_error" in text
    assert ".claude-fx-cache.json" in text
    assert "AbortSignal.timeout(2000)" in text
    assert "weekly_scoped" in text
    assert "oauth-2025-04-20" in text
    assert "Claude Code-credentials" in text
    assert "lstatSync" in text
    assert "0o600" in text


def test_install_static_contract():
    text = _read(INSTALL)

    assert "--check" in text
    assert "--force" in text
    assert "devkit-statusline.js" in text
    assert "settings.json" in text
    assert "statusLine" in text
    assert "process.env.HOME || os.homedir()" in text
    assert "replace(/\\\\/g, \"/\")" in text
    assert "renameSync" in text
    assert "copyFileSync" in text


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_statusline_node_smoke_with_stdin_rates(tmp_path):
    work = tmp_path / "repo"
    work.mkdir()
    if shutil.which("git"):
        subprocess.run(["git", "init"], cwd=work, check=True, capture_output=True)
        subprocess.run(["git", "checkout", "-b", "status-test"], cwd=work, check=True, capture_output=True)
        subprocess.run(
            [
                "git",
                "-c",
                "user.name=Devkit Test",
                "-c",
                "user.email=devkit-test@example.invalid",
                "commit",
                "--allow-empty",
                "-m",
                "init",
            ],
            cwd=work,
            check=True,
            capture_output=True,
        )

    fixture = {
        "workspace": {"current_dir": str(work)},
        "model": {"display_name": "Sonnet"},
        "context_window": {"used_percentage": 30},
        "rate_limits": {
            "five_hour": {"used_percentage": 55, "resets_at": 1893456000},
            "seven_day": {"remaining_percentage": 80},
        },
    }
    env = _node_env(tmp_path)
    env["DEVKIT_STATUSLINE_NO_FETCH"] = "1"

    result = subprocess.run(
        ["node", str(STATUSLINE)],
        input=json.dumps(fixture),
        text=True,
        encoding="utf-8",
        capture_output=True,
        env=env,
        cwd=REPO_ROOT,
        check=False,
    )

    assert result.returncode == 0
    lines = _strip_ansi(result.stdout.strip()).splitlines()
    assert len(lines) == 2
    assert "repo | Sonnet" in lines[0]
    assert "ctx 残り 70%" in lines[1]
    assert "5hr 55%" in lines[1]
    assert "wk 20%" in lines[1]
    if shutil.which("git"):
        assert "status-test" in lines[0]


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_statusline_no_fetch_uses_stale_usage_cache(tmp_path):
    work = tmp_path / "repo"
    work.mkdir()
    env = _node_env(tmp_path)
    cache_dir = Path(env["DEVKIT_STATUSLINE_CACHE_DIR"])
    cache_dir.mkdir(parents=True)
    cache_file = cache_dir / ".claude-usage-cache.json"
    cache_file.write_text(
        json.dumps(
            {
                "five_hour": {"used_percentage": 42},
                "seven_day": {"used_percentage": 17},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    stale_time = time.time() - 120
    os.utime(cache_file, (stale_time, stale_time))
    env["DEVKIT_STATUSLINE_NO_FETCH"] = "1"
    fixture = {
        "workspace": {"current_dir": str(work)},
        "model": {"display_name": "Sonnet"},
    }

    result = subprocess.run(
        ["node", str(STATUSLINE)],
        input=json.dumps(fixture),
        text=True,
        encoding="utf-8",
        capture_output=True,
        env=env,
        cwd=REPO_ROOT,
        check=False,
    )

    output = _strip_ansi(result.stdout)
    assert result.returncode == 0
    assert "5hr" in output
    assert "ago" in output


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_statusline_weekly_reset_remaining(tmp_path):
    work = tmp_path / "repo"
    work.mkdir()
    fixture = {
        "workspace": {"current_dir": str(work)},
        "model": {"display_name": "Sonnet"},
        "rate_limits": {
            "seven_day": {
                "remaining_percentage": 80,
                "resets_at": int(time.time() + (2 * 24 * 60 * 60) + (4 * 60 * 60)),
            },
        },
    }
    env = _node_env(tmp_path)
    env["DEVKIT_STATUSLINE_NO_FETCH"] = "1"

    result = subprocess.run(
        ["node", str(STATUSLINE)],
        input=json.dumps(fixture),
        text=True,
        encoding="utf-8",
        capture_output=True,
        env=env,
        cwd=REPO_ROOT,
        check=False,
    )

    assert result.returncode == 0
    output = _strip_ansi(result.stdout)
    assert "wk 20% (残り " in output
    assert "d" in output


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_statusline_cost_usd_fallback(tmp_path):
    work = tmp_path / "repo"
    work.mkdir()
    fixture = {
        "workspace": {"current_dir": str(work)},
        "model": {"display_name": "Sonnet"},
        "cost": {"total_cost_usd": 8.234},
    }
    env = _node_env(tmp_path)
    env["DEVKIT_STATUSLINE_NO_FETCH"] = "1"

    result = subprocess.run(
        ["node", str(STATUSLINE)],
        input=json.dumps(fixture),
        text=True,
        encoding="utf-8",
        capture_output=True,
        env=env,
        cwd=REPO_ROOT,
        check=False,
    )

    assert result.returncode == 0
    assert "$8.23" in _strip_ansi(result.stdout)


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_statusline_cost_jpy_from_cache(tmp_path):
    work = tmp_path / "repo"
    work.mkdir()
    env = _node_env(tmp_path)
    cache_dir = Path(env["DEVKIT_STATUSLINE_CACHE_DIR"])
    cache_dir.mkdir(parents=True)
    (cache_dir / ".claude-fx-cache.json").write_text(
        json.dumps({"rates": {"JPY": 150.0}}) + "\n",
        encoding="utf-8",
    )
    env["DEVKIT_STATUSLINE_NO_FETCH"] = "1"
    fixture = {
        "workspace": {"current_dir": str(work)},
        "model": {"display_name": "Sonnet"},
        "cost": {"total_cost_usd": 8.234},
    }

    result = subprocess.run(
        ["node", str(STATUSLINE)],
        input=json.dumps(fixture),
        text=True,
        encoding="utf-8",
        capture_output=True,
        env=env,
        cwd=REPO_ROOT,
        check=False,
    )

    assert result.returncode == 0
    assert "¥1,235" in _strip_ansi(result.stdout)


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_statusline_cost_uses_usd_with_recent_fx_failure_cache(tmp_path):
    work = tmp_path / "repo"
    work.mkdir()
    env = _node_env(tmp_path)
    cache_dir = Path(env["DEVKIT_STATUSLINE_CACHE_DIR"])
    cache_dir.mkdir(parents=True)
    cache_file = cache_dir / ".claude-fx-cache.json"
    cache_file.write_text(json.dumps({"fx_error": True}) + "\n", encoding="utf-8")
    os.utime(cache_file, None)
    env["DEVKIT_STATUSLINE_NO_FETCH"] = "1"
    fixture = {
        "workspace": {"current_dir": str(work)},
        "model": {"display_name": "Sonnet"},
        "cost": {"total_cost_usd": 8.234},
    }

    result = subprocess.run(
        ["node", str(STATUSLINE)],
        input=json.dumps(fixture),
        text=True,
        encoding="utf-8",
        capture_output=True,
        env=env,
        cwd=REPO_ROOT,
        check=False,
    )

    output = _strip_ansi(result.stdout)
    assert result.returncode == 0
    assert "$8.23" in output
    assert "¥" not in output


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_statusline_cost_missing_hides_cost_segment(tmp_path):
    work = tmp_path / "repo"
    work.mkdir()
    fixture = {
        "workspace": {"current_dir": str(work)},
        "model": {"display_name": "Sonnet"},
        "rate_limits": {"seven_day": {"remaining_percentage": 80}},
    }
    env = _node_env(tmp_path)
    env["DEVKIT_STATUSLINE_NO_FETCH"] = "1"

    result = subprocess.run(
        ["node", str(STATUSLINE)],
        input=json.dumps(fixture),
        text=True,
        encoding="utf-8",
        capture_output=True,
        env=env,
        cwd=REPO_ROOT,
        check=False,
    )

    assert result.returncode == 0
    output = _strip_ansi(result.stdout)
    assert "$" not in output
    assert "¥" not in output


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
@pytest.mark.parametrize("stdin", ["", "{not-json"])
def test_statusline_empty_or_broken_stdin_exits_zero(tmp_path, stdin):
    env = _node_env(tmp_path)
    env["DEVKIT_STATUSLINE_NO_FETCH"] = "1"

    result = subprocess.run(
        ["node", str(STATUSLINE)],
        input=stdin,
        text=True,
        encoding="utf-8",
        capture_output=True,
        env=env,
        cwd=REPO_ROOT,
        check=False,
    )

    assert result.returncode == 0
    assert " | " in result.stdout


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_install_is_idempotent_and_writes_managed_command(tmp_path):
    env = _node_env(tmp_path)

    first = subprocess.run(["node", str(INSTALL)], text=True, encoding="utf-8", capture_output=True, env=env, check=False)
    settings_path = tmp_path / "home" / ".claude" / "settings.json"
    first_bytes = settings_path.read_bytes()
    second = subprocess.run(["node", str(INSTALL)], text=True, encoding="utf-8", capture_output=True, env=env, check=False)
    second_bytes = settings_path.read_bytes()

    assert first.returncode == 0
    assert second.returncode == 0
    assert first_bytes == second_bytes
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    command = settings["statusLine"]["command"]
    assert settings["statusLine"]["type"] == "command"
    assert settings["statusLine"]["padding"] == 0
    assert "devkit-statusline.js" in command
    assert "\\" not in command
    copied = tmp_path / "home" / ".claude" / "devkit-statusline.js"
    assert copied.read_text(encoding="utf-8") == STATUSLINE.read_text(encoding="utf-8")
    check = subprocess.run(
        ["node", str(INSTALL), "--check"], text=True, encoding="utf-8", capture_output=True, env=env, check=False
    )
    assert check.returncode == 0
    assert json.loads(check.stdout)["state"] == "managed"


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_install_check_reports_state_without_changes(tmp_path):
    env = _node_env(tmp_path)

    result = subprocess.run(
        ["node", str(INSTALL), "--check"], text=True, encoding="utf-8", capture_output=True, env=env, check=False
    )

    assert result.returncode == 0
    assert json.loads(result.stdout)["state"] == "not-installed"
    assert not (tmp_path / "home").exists()


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_install_foreign_statusline_requires_force(tmp_path):
    env = _node_env(tmp_path)
    claude_dir = tmp_path / "home" / ".claude"
    claude_dir.mkdir(parents=True)
    settings_path = claude_dir / "settings.json"
    fake_script = tmp_path / "elsewhere" / "devkit-statusline.js"
    settings_path.write_text(
        json.dumps({"theme": "dark", "statusLine": {"type": "command", "command": f'node "{fake_script}"', "padding": 1}})
        + "\n",
        encoding="utf-8",
    )
    before = settings_path.read_text(encoding="utf-8")

    check = subprocess.run(
        ["node", str(INSTALL), "--check"], text=True, encoding="utf-8", capture_output=True, env=env, check=False
    )
    blocked = subprocess.run(["node", str(INSTALL)], text=True, encoding="utf-8", capture_output=True, env=env, check=False)

    assert check.returncode == 0
    assert json.loads(check.stdout)["state"] == "foreign"
    assert settings_path.read_text(encoding="utf-8") == before
    assert blocked.returncode == 3
    assert settings_path.read_text(encoding="utf-8") == before
    assert "devkit-statusline.js" in blocked.stderr
    forced = subprocess.run(
        ["node", str(INSTALL), "--force"], text=True, encoding="utf-8", capture_output=True, env=env, check=False
    )
    assert forced.returncode == 0
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    assert settings["theme"] == "dark"
    assert "devkit-statusline.js" in settings["statusLine"]["command"]
    assert settings["statusLine"]["padding"] == 0
