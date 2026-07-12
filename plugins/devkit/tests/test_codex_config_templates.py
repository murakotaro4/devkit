"""Windows 向け Codex config template の契約テスト。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib


REPO_ROOT = Path(__file__).resolve().parents[3]
TEMPLATE_DIR = REPO_ROOT / "plugins" / "devkit" / "templates" / "codex"
SHARED_PATH = TEMPLATE_DIR / "config.shared.toml"
WINDOWS_PATH = TEMPLATE_DIR / "config.windows.toml"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _parse(path: Path) -> dict[str, Any]:
    return tomllib.loads(_read(path))


def _string_values(value: Any) -> list[str]:
    if isinstance(value, dict):
        return [item for nested in value.values() for item in _string_values(nested)]
    if isinstance(value, list):
        return [item for nested in value for item in _string_values(nested)]
    return [value] if isinstance(value, str) else []


def test_shared_template_pins_model_and_medium_effort():
    shared = _parse(SHARED_PATH)

    for removed_key in ("model_context_window", "model_auto_compact_token_limit"):
        assert removed_key not in shared
    assert shared["model"] == "gpt-5.6-sol"
    assert shared["model_reasoning_effort"] == "medium"
    assert shared["plan_mode_reasoning_effort"] == "medium"
    assert not ({"max", "ultra"} & {value.lower() for value in _string_values(shared)})


def test_shared_and_windows_templates_preserve_exact_platform_contract():
    windows = _parse(WINDOWS_PATH)
    merged = tomllib.loads(f"{_read(SHARED_PATH).rstrip()}\n\n{_read(WINDOWS_PATH)}")

    assert windows == {
        "features": {"shell_snapshot": False},
        "windows": {"sandbox": "unelevated"},
    }
    assert merged["features"] == {
        "js_repl": True,
        "multi_agent": True,
        "apps": True,
        "prevent_idle_sleep": True,
        "unified_exec": True,
        "fast_mode": True,
        "shell_snapshot": False,
    }
    assert merged["windows"] == {"sandbox": "unelevated"}
    assert merged["notice"] == {"hide_full_access_warning": True}
    assert merged["model_reasoning_effort"] == "medium"
    assert merged["plan_mode_reasoning_effort"] == "medium"
    assert merged["model"] == "gpt-5.6-sol"
    for removed_key in ("model_context_window", "model_auto_compact_token_limit"):
        assert removed_key not in merged
    assert not ({"max", "ultra"} & {value.lower() for value in _string_values(merged)})
