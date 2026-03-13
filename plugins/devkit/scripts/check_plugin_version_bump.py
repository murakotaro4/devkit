#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path.cwd()
BASE_REF = os.environ.get("DIG_VERSION_BASE_REF", "origin/main")


def run_git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def parse_version(raw: str, source_label: str) -> str:
    normalized = raw.lstrip("\ufeff")
    try:
        data = json.loads(normalized)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"invalid JSON in {source_label}: {exc}") from exc
    version = data.get("version")
    if not isinstance(version, str) or not version.strip():
        raise RuntimeError(f"version missing in {source_label}")
    return version.strip()


def parse_semver(version: str) -> tuple[int, int, int] | None:
    match = re.match(r"^(\d+)\.(\d+)\.(\d+)(?:[-+].*)?$", version)
    if not match:
        return None
    return tuple(int(match.group(index)) for index in range(1, 4))


def compare_semver(left: tuple[int, int, int], right: tuple[int, int, int]) -> int:
    for index in range(3):
        if left[index] != right[index]:
            return left[index] - right[index]
    return 0


def find_plugin_json_rel_path() -> str | None:
    candidates = [
        "plugins/devkit/.claude-plugin/plugin.json",
        ".claude-plugin/plugin.json",
    ]
    for rel in candidates:
        if (ROOT / rel).exists():
            return rel
    return None


def get_merge_base(ref: str) -> str | None:
    try:
        return run_git("merge-base", "HEAD", ref)
    except subprocess.CalledProcessError:
        return None


def get_changed_files(base_sha: str) -> list[str]:
    output = run_git("diff", "--name-only", f"{base_sha}...HEAD")
    if not output:
      return []
    return [line.strip() for line in output.splitlines() if line.strip()]


def requires_version_gate(changed_files: list[str]) -> bool:
    for changed in changed_files:
        unix_path = changed.replace("\\", "/")
        if unix_path.startswith("plugins/devkit/") or unix_path.startswith(".claude-plugin/"):
            return True
    return False


def read_head_version(plugin_json_rel: str) -> str:
    abs_path = ROOT / plugin_json_rel
    if not abs_path.exists():
        raise RuntimeError(f"missing file: {plugin_json_rel}")
    return parse_version(abs_path.read_text(encoding="utf-8"), f"{plugin_json_rel} (HEAD)")


def read_base_version(ref: str, plugin_json_rel: str) -> str:
    try:
        raw = run_git("show", f"{ref}:{plugin_json_rel}")
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            f"cannot read {plugin_json_rel} from {ref}: {exc.stderr.strip()}"
        ) from exc
    return parse_version(raw, f"{plugin_json_rel} ({ref})")


def run_check() -> tuple[int, dict[str, object]]:
    plugin_json_rel = find_plugin_json_rel_path()
    if not plugin_json_rel:
        return 0, {
            "ok": True,
            "skipped": True,
            "reason": "plugin.json not found in current repo",
            "baseRef": BASE_REF,
        }

    merge_base = get_merge_base(BASE_REF)
    if not merge_base:
        return 0, {
            "ok": True,
            "skipped": True,
            "reason": f"cannot resolve merge-base with {BASE_REF}",
            "baseRef": BASE_REF,
        }
    changed_files = get_changed_files(merge_base)

    if not requires_version_gate(changed_files):
        return 0, {
            "ok": True,
            "skipped": True,
            "reason": "no changes under plugins/devkit/** or .claude-plugin/*",
            "baseRef": BASE_REF,
            "mergeBase": merge_base,
        }

    try:
        head_version = read_head_version(plugin_json_rel)
        base_version = read_base_version(BASE_REF, plugin_json_rel)
    except RuntimeError as exc:
        return 0, {
            "ok": True,
            "skipped": True,
            "reason": str(exc),
            "baseRef": BASE_REF,
            "mergeBase": merge_base,
        }
    parsed_head = parse_semver(head_version)
    parsed_base = parse_semver(base_version)

    if not parsed_head or not parsed_base:
        return 2, {
            "ok": False,
            "reason": "version must be semver",
            "headVersion": head_version,
            "baseVersion": base_version,
        }

    if compare_semver(parsed_head, parsed_base) <= 0:
        return 2, {
            "ok": False,
            "reason": "plugin version not bumped",
            "required": f">{base_version}",
            "headVersion": head_version,
            "baseVersion": base_version,
            "baseRef": BASE_REF,
        }

    return 0, {
        "ok": True,
        "skipped": False,
        "baseRef": BASE_REF,
        "baseVersion": base_version,
        "headVersion": head_version,
    }


def main() -> int:
    code, payload = run_check()
    if code == 0:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    print(json.dumps(payload, ensure_ascii=False, indent=2), file=sys.stderr)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
