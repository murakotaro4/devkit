#!/usr/bin/env python3
"""外部前提レジストリと repo 内の出現箇所が一致することを検証する。

この check は ``current_value`` が外部世界で最新かどうかは検出できない。
外部陳腐化の裏取りと更新は catch-up スキルの責務とする。
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Any


ROOT = Path.cwd()
REGISTRY_PATH = Path("plugins/devkit/premises.json")
REQUIRED_PREMISE_KEYS = {
    "id",
    "summary",
    "current_value",
    "value_patterns",
    "verify_hint",
    "update_notes",
    "last_verified",
    "occurrences",
}
TOKEN_BOUNDARY_LEFT = "(?<![A-Za-z0-9_"
TOKEN_BOUNDARY_RIGHT = "(?![A-Za-z0-9_"


def _is_string_list(value: object) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) and item for item in value)


def _has_token_boundaries(pattern: str) -> bool:
    return TOKEN_BOUNDARY_LEFT in pattern and TOKEN_BOUNDARY_RIGHT in pattern


def _schema_problems(registry: object) -> tuple[list[str], list[dict[str, Any]]]:
    problems: list[str] = []
    if not isinstance(registry, dict):
        return ["registry must be a JSON object"], []
    if registry.get("version") != 1:
        problems.append("registry.version must be 1")

    scan = registry.get("scan")
    if not isinstance(scan, dict):
        problems.append("registry.scan must be an object")
    else:
        for key in ("include_suffixes", "exclude_prefixes"):
            if not _is_string_list(scan.get(key)):
                problems.append(f"registry.scan.{key} must be a non-empty string list")

    raw_premises = registry.get("premises")
    if not isinstance(raw_premises, list):
        return problems + ["registry.premises must be a list"], []

    premises: list[dict[str, Any]] = []
    ids: set[str] = set()
    for index, raw in enumerate(raw_premises):
        label = f"premises[{index}]"
        if not isinstance(raw, dict):
            problems.append(f"{label} must be an object")
            continue
        missing = sorted(REQUIRED_PREMISE_KEYS - raw.keys())
        if missing:
            problems.append(f"{label} missing required keys: {', '.join(missing)}")
            continue

        premise_id = raw.get("id")
        if not isinstance(premise_id, str) or not premise_id:
            problems.append(f"{label}.id must be a non-empty string")
            continue
        if premise_id in ids:
            problems.append(f"duplicate premise id: {premise_id}")
        ids.add(premise_id)
        label = premise_id

        for key in ("summary", "current_value", "verify_hint", "update_notes"):
            if not isinstance(raw.get(key), str) or not raw[key]:
                problems.append(f"{label}.{key} must be a non-empty string")

        patterns = raw.get("value_patterns")
        compiled: list[re.Pattern[str]] = []
        if not _is_string_list(patterns):
            problems.append(f"{label}.value_patterns must be a non-empty string list")
        else:
            for pattern in patterns:
                if not _has_token_boundaries(pattern):
                    problems.append(f"{label} pattern lacks token boundaries: {pattern}")
                try:
                    compiled.append(re.compile(pattern))
                except re.error as exc:
                    problems.append(f"{label} invalid regex {pattern!r}: {exc}")

        obsolete_patterns = raw.get("obsolete_value_patterns", [])
        if not isinstance(obsolete_patterns, list) or not all(
            isinstance(pattern, str) and pattern for pattern in obsolete_patterns
        ):
            problems.append(f"{label}.obsolete_value_patterns must be a string list")
        else:
            for pattern in obsolete_patterns:
                if not _has_token_boundaries(pattern):
                    problems.append(
                        f"{label} obsolete pattern lacks token boundaries: {pattern}"
                    )
                try:
                    re.compile(pattern)
                except re.error as exc:
                    problems.append(
                        f"{label} invalid obsolete regex {pattern!r}: {exc}"
                    )

        current_value = raw.get("current_value")
        if isinstance(current_value, str) and compiled and not any(
            pattern.search(current_value) for pattern in compiled
        ):
            problems.append(f"{label}.current_value does not match any value_patterns")

        verified = raw.get("last_verified")
        if not isinstance(verified, str):
            problems.append(f"{label}.last_verified must be YYYY-MM-DD")
        else:
            try:
                date.fromisoformat(verified)
            except ValueError:
                problems.append(f"{label}.last_verified must be YYYY-MM-DD")
            else:
                if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", verified):
                    problems.append(f"{label}.last_verified must be YYYY-MM-DD")

        exclude_paths = raw.get("exclude_paths", [])
        if not isinstance(exclude_paths, list) or not all(
            isinstance(path, str) and path for path in exclude_paths
        ):
            problems.append(f"{label}.exclude_paths must be a string list")

        occurrences = raw.get("occurrences")
        if not isinstance(occurrences, list):
            problems.append(f"{label}.occurrences must be a list")
        else:
            seen_paths: set[str] = set()
            for occurrence_index, occurrence in enumerate(occurrences):
                occurrence_label = f"{label}.occurrences[{occurrence_index}]"
                if not isinstance(occurrence, dict):
                    problems.append(f"{occurrence_label} must be an object")
                    continue
                path = occurrence.get("path")
                expected_count = occurrence.get("count", 1)
                if "min_count" in occurrence:
                    problems.append(
                        f"{occurrence_label}.min_count is unsupported; use exact count"
                    )
                if not isinstance(path, str) or not path:
                    problems.append(f"{occurrence_label}.path must be a non-empty string")
                elif path in seen_paths:
                    problems.append(f"{label} duplicate occurrence path: {path}")
                else:
                    seen_paths.add(path)
                if (
                    not isinstance(expected_count, int)
                    or isinstance(expected_count, bool)
                    or expected_count < 1
                ):
                    problems.append(f"{occurrence_label}.count must be a positive integer")

        premises.append(raw)

    return problems, premises


def validate_registry(root: Path, registry: object, scan_files: list[str]) -> list[str]:
    """Validate a parsed registry against an explicit list of repo-relative files."""
    problems, premises = _schema_problems(registry)
    if problems or not isinstance(registry, dict) or not isinstance(registry.get("scan"), dict):
        return problems

    scan = registry["scan"]
    include_suffixes = tuple(scan["include_suffixes"])
    exclude_prefixes = tuple(scan["exclude_prefixes"])
    candidate_paths = sorted(
        {
            path.replace("\\", "/")
            for path in scan_files
            if path.replace("\\", "/").endswith(include_suffixes)
            and not path.replace("\\", "/").startswith(exclude_prefixes)
        }
    )

    contents: dict[str, str] = {}
    for relpath in candidate_paths:
        path = root / relpath
        if not path.is_file():
            continue
        try:
            contents[relpath] = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            problems.append(f"scan file is not UTF-8: {relpath}: {exc}")

    for premise in premises:
        premise_id = premise["id"]
        patterns = [re.compile(pattern) for pattern in premise["value_patterns"]]
        obsolete_patterns = [
            re.compile(pattern) for pattern in premise.get("obsolete_value_patterns", [])
        ]
        excluded = {path.replace("\\", "/") for path in premise.get("exclude_paths", [])}
        declared = {
            occurrence["path"].replace("\\", "/"): occurrence.get("count", 1)
            for occurrence in premise["occurrences"]
        }
        actual_counts: dict[str, int] = {}
        for relpath, content in contents.items():
            if relpath in excluded:
                continue
            count = sum(len(pattern.findall(content)) for pattern in patterns)
            if count:
                actual_counts[relpath] = count
            obsolete_count = sum(
                len(pattern.findall(content)) for pattern in obsolete_patterns
            )
            if obsolete_count:
                problems.append(
                    f"obsolete value present: {premise_id} {relpath} "
                    f"({obsolete_count} matches)"
                )

        actual_paths = set(actual_counts)
        declared_paths = set(declared)
        for path in sorted(actual_paths - declared_paths):
            problems.append(f"{premise_id} unregistered occurrence: {path} ({actual_counts[path]} matches)")
        for path in sorted(declared_paths - actual_paths):
            problems.append(f"{premise_id} declared occurrence has no match: {path}")
        for path in sorted(actual_paths & declared_paths):
            if actual_counts[path] != declared[path]:
                problems.append(
                    f"{premise_id} occurrence count mismatch: {path} "
                    f"(actual={actual_counts[path]}, expected={declared[path]})"
                )

    return problems


def git_scan_files(root: Path) -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    return sorted({raw.decode("utf-8") for raw in result.stdout.split(b"\0") if raw})


def main() -> int:
    try:
        registry = json.loads((ROOT / REGISTRY_PATH).read_text(encoding="utf-8"))
        scan_files = git_scan_files(ROOT)
        problems = validate_registry(ROOT, registry, scan_files)
    except (OSError, json.JSONDecodeError, subprocess.SubprocessError, UnicodeDecodeError) as exc:
        problems = [f"external premises check failed: {exc}"]

    payload = {"ok": not problems, "problems": problems}
    stream = sys.stdout if not problems else sys.stderr
    print(json.dumps(payload, ensure_ascii=False, indent=2), file=stream)
    return 0 if not problems else 2


if __name__ == "__main__":
    raise SystemExit(main())
