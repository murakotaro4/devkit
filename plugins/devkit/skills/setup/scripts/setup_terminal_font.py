#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import platform as platform_module
import re
import shlex
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


FONT_FACE = "JetBrainsMono Nerd Font"
PACKAGE_ID = "DEVCOM.JetBrainsMonoNerdFont"
REGISTRY_PATHS = (
    ("HKEY_LOCAL_MACHINE", r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts"),
    ("HKEY_CURRENT_USER", r"Software\Microsoft\Windows NT\CurrentVersion\Fonts"),
)
STYLE_WORDS = {
    "regular", "bold", "italic", "light", "medium", "semibold",
    "extrabold", "thin", "extralight",
}


def normalize_font_family(value_name: str) -> str:
    name = re.sub(r"\s*\([^)]*\)\s*$", "", value_name).strip()
    words = name.split()
    while words and words[-1].casefold() in STYLE_WORDS:
        words.pop()
    return " ".join(words).casefold()


def font_is_registered(value_names: Iterable[str]) -> bool:
    return any(normalize_font_family(name) == FONT_FACE.casefold() for name in value_names)


def read_font_names(path: Path | None) -> list[str]:
    if path is not None:
        return path.read_text(encoding="utf-8").splitlines() if path.exists() else []

    import winreg  # type: ignore[import-not-found]  # Windows-only, intentionally lazy.

    roots = {
        "HKEY_LOCAL_MACHINE": winreg.HKEY_LOCAL_MACHINE,
        "HKEY_CURRENT_USER": winreg.HKEY_CURRENT_USER,
    }
    names: list[str] = []
    for root_name, key_path in REGISTRY_PATHS:
        try:
            with winreg.OpenKey(roots[root_name], key_path) as key:
                index = 0
                while True:
                    try:
                        names.append(winreg.EnumValue(key, index)[0])
                    except OSError:
                        break
                    index += 1
        except FileNotFoundError:
            continue
    return names


def default_settings_paths() -> list[Path]:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        return []
    root = Path(local_app_data)
    return [
        root / "Packages/Microsoft.WindowsTerminal_8wekyb3d8bbwe/LocalState/settings.json",
        root / "Packages/Microsoft.WindowsTerminalPreview_8wekyb3d8bbwe/LocalState/settings.json",
        root / "Packages/Microsoft.WindowsTerminalCanary_8wekyb3d8bbwe/LocalState/settings.json",
        root / "Microsoft/Windows Terminal/settings.json",
    ]


def strip_jsonc(text: str) -> str:
    output: list[str] = []
    index = 0
    in_string = False
    escaped = False
    while index < len(text):
        char = text[index]
        if in_string:
            output.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            index += 1
            continue
        if char == '"':
            in_string = True
            output.append(char)
            index += 1
            continue
        if text.startswith("//", index):
            index += 2
            while index < len(text) and text[index] not in "\r\n":
                index += 1
            continue
        if text.startswith("/*", index):
            end = text.find("*/", index + 2)
            if end == -1:
                raise ValueError("unterminated block comment")
            index = end + 2
            continue
        output.append(char)
        index += 1
    uncommented = "".join(output)
    output = []
    index = 0
    in_string = False
    escaped = False
    while index < len(uncommented):
        char = uncommented[index]
        if in_string:
            output.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            index += 1
            continue
        if char == '"':
            in_string = True
            output.append(char)
            index += 1
            continue
        if char == ",":
            lookahead = index + 1
            while lookahead < len(uncommented) and uncommented[lookahead].isspace():
                lookahead += 1
            if lookahead < len(uncommented) and uncommented[lookahead] in "}]":
                index += 1
                continue
        output.append(char)
        index += 1
    return "".join(output)


def parse_settings(raw: bytes) -> tuple[Any, bool]:
    has_bom = raw.startswith(b"\xef\xbb\xbf")
    text = raw[3:].decode("utf-8") if has_bom else raw.decode("utf-8")
    try:
        return json.loads(text), has_bom
    except json.JSONDecodeError:
        return json.loads(strip_jsonc(text)), has_bom


def desired_settings(data: Any) -> tuple[dict[str, Any] | None, str | None, bool]:
    if not isinstance(data, dict):
        return None, "unexpected-structure", False
    profiles = data.get("profiles")
    if profiles is None:
        profiles = data["profiles"] = {}
    if not isinstance(profiles, dict):
        return None, "unexpected-structure", False
    defaults = profiles.get("defaults")
    if defaults is None:
        defaults = profiles["defaults"] = {}
    if not isinstance(defaults, dict):
        return None, "unexpected-structure", False
    font = defaults.get("font")
    if font is None:
        font = defaults["font"] = {}
    if not isinstance(font, dict):
        return None, "unexpected-structure", False
    changed = font.get("face") != FONT_FACE
    if changed:
        font["face"] = FONT_FACE
    return data, None, changed


def backup_path_for(path: Path, now: datetime | None = None) -> Path:
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    directory = path.parent / "devkit-font-backup"
    candidate = directory / f"{path.name}.{stamp}"
    suffix = 0
    while candidate.exists():
        suffix += 1
        candidate = directory / f"{path.name}.{stamp}-{suffix}"
    return candidate


def inspect_or_update(path: Path, check: bool) -> dict[str, Any]:
    result: dict[str, Any] = {"path": str(path)}
    try:
        raw = path.read_bytes()
        data, has_bom = parse_settings(raw)
    except OSError as exc:
        result.update({"error": str(exc), "reason": "read-failed"})
        return result
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        result.update({"error": f"invalid-json: {exc}", "reason": "invalid-json"})
        return result
    desired, error, changed = desired_settings(data)
    if error:
        result.update({"error": error, "reason": error})
        return result
    if check:
        result["would_change"] = changed
        return result
    result["changed"] = changed
    result["backup"] = None
    if not changed:
        return result

    try:
        backup = backup_path_for(path)
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, backup)
    except OSError as exc:
        result.update({"changed": False, "backup": None, "error": str(exc), "reason": "backup-failed"})
        return result
    payload = json.dumps(desired, ensure_ascii=False, indent=4) + "\n"
    encoded = (("\ufeff" if has_bom else "") + payload).encode("utf-8")
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.", delete=False) as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
            temp_path = Path(handle.name)
        os.replace(temp_path, path)
    except OSError as exc:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        result.update({"changed": False, "backup": str(backup), "error": str(exc), "reason": "write-failed"})
        return result
    result["backup"] = str(backup)
    result["comments_removed"] = True
    return result


def base_result(platform_name: str) -> dict[str, Any]:
    return {
        "status": "ok",
        "platform": platform_name,
        "font_installed": False,
        "winget": "not-run",
        "settings": [],
        "actions": [],
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    platform_name = args.platform or platform_module.system()
    result = base_result(platform_name)
    if platform_name.casefold() != "windows" and not os.environ.get("WINDIR"):
        result.update({"status": "skip", "reason": "windows-only"})
        return result

    font_names_path = Path(args.font_names_file) if args.font_names_file else None
    registered = font_is_registered(read_font_names(font_names_path))
    result["font_installed"] = registered
    if args.check and not registered:
        result.update({"status": "check", "reason": "font-not-registered"})
        result["actions"].append("Install JetBrainsMono Nerd Font before applying Windows Terminal settings.")
        return result

    if not registered:
        command = shlex.split(args.winget_cmd) + [
            "install", "--id", PACKAGE_ID, "--exact", "--silent",
            "--accept-package-agreements", "--accept-source-agreements",
        ]
        try:
            completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", check=False)
        except FileNotFoundError:
            result.update({"status": "error", "winget": "missing", "reason": "winget-missing"})
            result["actions"].append("Install manually from nerdfonts.com or github.com/ryanoasis/nerd-fonts/releases.")
            return result
        if completed.returncode != 0:
            result.update({"status": "error", "winget": "failed", "reason": "winget-failed"})
            result["actions"].append((completed.stderr or completed.stdout).strip()[-500:])
            return result
        result["winget"] = "installed"
        registered = font_is_registered(read_font_names(font_names_path))
        result["font_installed"] = registered
        if not registered:
            result.update({"status": "error", "reason": "font-not-registered"})
            result["actions"].append(
                "Restart Windows or install the font manually, then rerun /setup after it appears in the Fonts registry."
            )
            return result

    candidates = [Path(value) for value in args.settings_path] if args.settings_path else default_settings_paths()
    existing = [path for path in candidates if path.is_file()]
    if not existing:
        result.update({"status": "skip", "reason": "windows-terminal-not-found"})
        result["actions"].append("Install Windows Terminal, then rerun /setup.")
        return result
    result["settings"] = [inspect_or_update(path, args.check) for path in existing]
    if any("error" in item for item in result["settings"]):
        result["status"] = "partial-error"
    elif args.check:
        result["status"] = "check"
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Configure JetBrainsMono Nerd Font in Windows Terminal.")
    parser.add_argument("--check", action="store_true", help="Report changes without installing or writing")
    parser.add_argument("--format", choices=["json"], default="json")
    parser.add_argument("--settings-path", action="append", default=[])
    parser.add_argument("--font-names-file")
    parser.add_argument("--winget-cmd", default="winget")
    parser.add_argument("--platform")
    args = parser.parse_args()
    print(json.dumps(run(args), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
