#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform as platform_module
import shutil
import tempfile
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


FONT_FACE = "UDEV Gothic NF"
DOWNLOAD_URL = "https://github.com/yuru7/udev-gothic/releases/download/v2.2.0/UDEVGothic_NF_v2.2.0.zip"
EXPECTED_SHA256 = "45faeef7b5d8bc591bcc5887a2ca0c5fb9028066f18a5a52cd6f10b7d655ba37"
DOWNLOAD_TIMEOUT_SECONDS = 60
MAX_DOWNLOAD_BYTES = 200 * 1024 * 1024
FONT_MEMBERS = {
    "UDEV Gothic NF Regular (TrueType)": "UDEVGothic_NF_v2.2.0/UDEVGothicNF-Regular.ttf",
    "UDEV Gothic NF Bold (TrueType)": "UDEVGothic_NF_v2.2.0/UDEVGothicNF-Bold.ttf",
    "UDEV Gothic NF Italic (TrueType)": "UDEVGothic_NF_v2.2.0/UDEVGothicNF-Italic.ttf",
    "UDEV Gothic NF Bold Italic (TrueType)": "UDEVGothic_NF_v2.2.0/UDEVGothicNF-BoldItalic.ttf",
}
REGISTRY_PATHS = (
    ("HKEY_LOCAL_MACHINE", r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts"),
    ("HKEY_CURRENT_USER", r"Software\Microsoft\Windows NT\CurrentVersion\Fonts"),
)
EXPECTED_VALUE_NAMES = tuple(FONT_MEMBERS)


def normalize_registry_value_name(value_name: str) -> str:
    return " ".join(value_name.split()).casefold()


def font_is_registered(value_names: Iterable[str]) -> bool:
    actual = {normalize_registry_value_name(name) for name in value_names}
    expected = {normalize_registry_value_name(name) for name in EXPECTED_VALUE_NAMES}
    return expected.issubset(actual)


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


def read_font_registry_values() -> list[tuple[str, str]]:
    import winreg  # type: ignore[import-not-found]  # Windows-only, intentionally lazy.

    roots = {
        "HKEY_LOCAL_MACHINE": winreg.HKEY_LOCAL_MACHINE,
        "HKEY_CURRENT_USER": winreg.HKEY_CURRENT_USER,
    }
    values: list[tuple[str, str]] = []
    for root_name, key_path in REGISTRY_PATHS:
        try:
            with winreg.OpenKey(roots[root_name], key_path) as key:
                index = 0
                while True:
                    try:
                        name, data, _value_type = winreg.EnumValue(key, index)
                    except OSError:
                        break
                    values.append((name, str(data)))
                    index += 1
        except FileNotFoundError:
            continue
    return values


def registry_font_path(value: str) -> Path:
    path = Path(os.path.expandvars(value))
    if path.is_absolute():
        return path
    windows_dir = Path(os.environ.get("WINDIR", r"C:\Windows"))
    return windows_dir / "Fonts" / path


def real_font_is_registered() -> bool:
    expected = {
        normalize_registry_value_name(name): name for name in EXPECTED_VALUE_NAMES
    }
    valid: set[str] = set()
    for name, data in read_font_registry_values():
        normalized = normalize_registry_value_name(name)
        if normalized in expected and registry_font_path(data).is_file():
            valid.add(normalized)
    return valid == set(expected)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_archive(destination: Path) -> None:
    with urllib.request.urlopen(DOWNLOAD_URL, timeout=DOWNLOAD_TIMEOUT_SECONDS) as response:  # noqa: S310
        content_length = response.headers.get("Content-Length")
        if content_length is not None and int(content_length) > MAX_DOWNLOAD_BYTES:
            raise ValueError("font archive exceeds the 200MB download limit")
        total = 0
        with destination.open("wb") as output:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_DOWNLOAD_BYTES:
                    raise ValueError("font archive exceeds the 200MB download limit")
                output.write(chunk)


def stage_fonts(archive: Path, staging_dir: Path) -> dict[str, Path]:
    staged: dict[str, Path] = {}
    total = 0
    with zipfile.ZipFile(archive) as bundle:
        infos = bundle.infolist()
        for value_name, member_name in FONT_MEMBERS.items():
            matches = [info for info in infos if info.filename == member_name]
            if len(matches) != 1 or matches[0].is_dir():
                raise ValueError(f"required font member must appear exactly once: {member_name}")
            info = matches[0]
            destination = staging_dir / Path(member_name).name
            written = 0
            with bundle.open(info) as source, destination.open("wb") as output:
                while True:
                    chunk = source.read(1024 * 1024)
                    if not chunk:
                        break
                    written += len(chunk)
                    total += len(chunk)
                    if total > MAX_DOWNLOAD_BYTES:
                        raise ValueError("expanded font files exceed the 200MB limit")
                    output.write(chunk)
            if written != info.file_size:
                raise ValueError(f"font member size mismatch: {member_name}")
            staged[value_name] = destination
    return staged


def write_font_name_seam(path: Path) -> None:
    existing = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    normalized = {normalize_registry_value_name(name) for name in existing}
    additions = [
        name for name in EXPECTED_VALUE_NAMES
        if normalize_registry_value_name(name) not in normalized
    ]
    if additions:
        path.parent.mkdir(parents=True, exist_ok=True)
        prefix = "\n" if existing and path.read_bytes()[-1:] not in (b"\n", b"\r") else ""
        with path.open("a", encoding="utf-8") as handle:
            handle.write(prefix + "\n".join(additions) + "\n")


def register_fonts(installed: dict[str, Path], font_names_path: Path | None) -> None:
    if font_names_path is not None:
        write_font_name_seam(font_names_path)
        return

    import winreg  # type: ignore[import-not-found]  # Windows-only, intentionally lazy.

    key_path = r"Software\Microsoft\Windows NT\CurrentVersion\Fonts"
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as key:
        for value_name, path in installed.items():
            winreg.SetValueEx(key, value_name, 0, winreg.REG_SZ, str(path.resolve()))


def refresh_font_cache(installed: Iterable[Path]) -> list[str]:
    notes: list[str] = []
    try:
        import ctypes

        gdi32 = ctypes.windll.gdi32
        user32 = ctypes.windll.user32
        for path in installed:
            if not gdi32.AddFontResourceW(str(path.resolve())):
                notes.append(f"Font cache refresh did not load {path.name}; restart may be required.")
        result = ctypes.c_ulong()
        if not user32.SendMessageTimeoutW(0xFFFF, 0x001D, 0, 0, 0x0002, 5000, ctypes.byref(result)):
            notes.append("WM_FONTCHANGE broadcast timed out; restart may be required.")
    except Exception as exc:  # Cache refresh is best-effort after durable registration.
        notes.append(f"Font cache refresh failed: {exc}")
    return notes


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
        "download": "not-run",
        "settings": [],
        "actions": [],
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    platform_name = args.platform or platform_module.system()
    result = base_result(platform_name)
    if args.platform:
        # 明示指定を最優先する(実 Windows ホストの WINDIR で上書きさせない)
        is_windows = args.platform.casefold() == "windows"
    else:
        is_windows = platform_name.casefold() == "windows" or bool(os.environ.get("WINDIR"))
    if not is_windows:
        result.update({"status": "skip", "reason": "windows-only"})
        return result

    font_names_path = Path(args.font_names_file) if args.font_names_file else None
    registered = (
        font_is_registered(read_font_names(font_names_path))
        if font_names_path is not None else real_font_is_registered()
    )
    result["font_installed"] = registered
    if args.check and not registered:
        result.update({"status": "check", "reason": "font-not-registered"})
        result["actions"].append("Install UDEV Gothic NF before applying Windows Terminal settings.")
        return result

    if not registered:
        archive_arg = Path(args.font_zip) if args.font_zip else None
        try:
            temp_parent = str(archive_arg.parent) if archive_arg is not None else None
            with tempfile.TemporaryDirectory(prefix="devkit-udev-font-", dir=temp_parent) as temp_dir_value:
                temp_dir = Path(temp_dir_value)
                archive = archive_arg or (temp_dir / "UDEVGothic_NF_v2.2.0.zip")
                if archive_arg is None:
                    download_archive(archive)
                elif not archive.is_file():
                    raise FileNotFoundError(archive)
                if archive.stat().st_size > MAX_DOWNLOAD_BYTES:
                    raise ValueError("font archive exceeds the 200MB download limit")
                actual_hash = sha256_file(archive)
                if actual_hash.casefold() != args.expected_sha256.casefold():
                    result.update({"status": "error", "download": "hash-mismatch", "reason": "hash-mismatch"})
                    result["actions"].append(
                        f"Font archive SHA-256 mismatch: expected {args.expected_sha256}, got {actual_hash}."
                    )
                    return result
                result["download"] = "downloaded"
                staging_dir = temp_dir / "staging"
                staging_dir.mkdir()
                staged = stage_fonts(archive, staging_dir)
                fonts_dir = (
                    Path(args.fonts_dir) if args.fonts_dir
                    else Path(os.environ["LOCALAPPDATA"]) / "Microsoft/Windows/Fonts"
                )
                fonts_dir.mkdir(parents=True, exist_ok=True)
                installed: dict[str, Path] = {}
                for value_name, staged_path in staged.items():
                    destination = fonts_dir / staged_path.name
                    shutil.copy2(staged_path, destination)
                    installed[value_name] = destination
                register_fonts(installed, font_names_path)
                if font_names_path is None:
                    result["actions"].extend(refresh_font_cache(installed.values()))
                result["actions"].append("Restart Windows Terminal if the new font is not visible yet.")
        except Exception as exc:
            result.update({"status": "error", "download": "failed", "reason": "font-install-failed"})
            result["actions"].append(str(exc))
            return result
        registered = (
            font_is_registered(read_font_names(font_names_path))
            if font_names_path is not None else real_font_is_registered()
        )
        result["font_installed"] = registered
        if not registered:
            result.update({"status": "error", "reason": "font-not-registered"})
            result["actions"].append(
                "Register all four UDEV Gothic NF styles, then rerun /setup."
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
    parser = argparse.ArgumentParser(description="Configure UDEV Gothic NF in Windows Terminal.")
    parser.add_argument("--check", action="store_true", help="Report changes without installing or writing")
    parser.add_argument("--format", choices=["json"], default="json")
    parser.add_argument("--settings-path", action="append", default=[])
    parser.add_argument("--font-names-file")
    parser.add_argument("--font-zip")
    parser.add_argument("--expected-sha256", default=EXPECTED_SHA256)
    parser.add_argument("--fonts-dir")
    parser.add_argument("--platform")
    args = parser.parse_args()
    print(json.dumps(run(args), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
