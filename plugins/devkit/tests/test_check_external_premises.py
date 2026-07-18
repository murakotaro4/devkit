from __future__ import annotations

import copy
import re
from pathlib import Path

from check_external_premises import validate_registry


PATTERN = r"(?<![A-Za-z0-9_])composer-2\.5(?![A-Za-z0-9_])"
CURSOR_SKILLS_PATTERN = r"(?<![A-Za-z0-9_])\.cursor[/\\]skills(?![A-Za-z0-9_.-])"


def registry(path: str = "docs/value.md", count: int = 1) -> dict[str, object]:
    return {
        "version": 1,
        "scan": {"include_suffixes": [".md"], "exclude_prefixes": ["ignored/"]},
        "premises": [
            {
                "id": "cursor-model",
                "summary": "model",
                "current_value": "composer-2.5",
                "value_patterns": [PATTERN],
                "obsolete_value_patterns": [],
                "verify_hint": "help",
                "update_notes": "update all",
                "last_verified": "2026-07-12",
                "occurrences": [{"path": path, "count": count}],
            }
        ],
    }


def write(root: Path, relpath: str, content: str) -> None:
    path = root / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_happy_path_and_crlf(tmp_path):
    write(tmp_path, "docs/value.md", "model: composer-2.5\r\n")
    assert validate_registry(tmp_path, registry(), ["docs/value.md"]) == []


def test_schema_errors_are_reported(tmp_path):
    broken = registry()
    broken["version"] = 2
    broken["premises"][0]["last_verified"] = "2026-99-99"
    broken["premises"][0]["value_patterns"] = ["composer-2.5"]
    problems = validate_registry(tmp_path, broken, [])
    assert any("version must be 1" in problem for problem in problems)
    assert any("token boundaries" in problem for problem in problems)
    assert any("YYYY-MM-DD" in problem for problem in problems)


def test_current_value_must_match_a_pattern(tmp_path):
    broken = registry()
    broken["premises"][0]["current_value"] = "composer-3"
    assert any("current_value" in problem for problem in validate_registry(tmp_path, broken, []))


def test_missing_occurrence_file_is_reported(tmp_path):
    problems = validate_registry(tmp_path, registry(), ["docs/value.md"])
    assert any("declared occurrence has no match" in problem for problem in problems)


def test_occurrence_count_rejects_too_few_matches(tmp_path):
    write(tmp_path, "docs/value.md", "composer-2.5\n")
    problems = validate_registry(tmp_path, registry(count=2), ["docs/value.md"])
    assert any("count mismatch" in problem for problem in problems)


def test_occurrence_count_rejects_extra_matches_from_partial_migration(tmp_path):
    write(tmp_path, "docs/value.md", "composer-2.5\ncomposer-2.5\n")
    problems = validate_registry(tmp_path, registry(count=1), ["docs/value.md"])
    assert any(
        "actual=2, expected=1" in problem for problem in problems
    ), "宣言数を上回る旧値の取り残し相当を検出できない"


def test_omitted_count_defaults_to_one(tmp_path):
    write(tmp_path, "docs/value.md", "composer-2.5\n")
    configured = registry()
    configured["premises"][0]["occurrences"][0].pop("count")
    assert validate_registry(tmp_path, configured, ["docs/value.md"]) == []


def test_legacy_min_count_is_rejected(tmp_path):
    configured = registry()
    occurrence = configured["premises"][0]["occurrences"][0]
    occurrence["min_count"] = occurrence.pop("count")
    problems = validate_registry(tmp_path, configured, [])
    assert any("min_count is unsupported" in problem for problem in problems)


def test_unregistered_tracked_occurrence_is_reported(tmp_path):
    write(tmp_path, "docs/value.md", "composer-2.5\n")
    write(tmp_path, "docs/extra.md", "composer-2.5\n")
    problems = validate_registry(tmp_path, registry(), ["docs/value.md", "docs/extra.md"])
    assert any("unregistered occurrence: docs/extra.md" in problem for problem in problems)


def test_untracked_file_is_included_when_scan_files_contains_it(tmp_path):
    write(tmp_path, "docs/value.md", "composer-2.5\n")
    write(tmp_path, "docs/untracked.md", "composer-2.5\n")
    problems = validate_registry(tmp_path, registry(), ["docs/value.md", "docs/untracked.md"])
    assert any("unregistered occurrence: docs/untracked.md" in problem for problem in problems)


def test_declaration_whose_literal_disappeared_is_reported(tmp_path):
    write(tmp_path, "docs/value.md", "no model here\n")
    problems = validate_registry(tmp_path, registry(), ["docs/value.md"])
    assert any("declared occurrence has no match" in problem for problem in problems)


def test_exclude_paths_are_premise_specific(tmp_path):
    write(tmp_path, "docs/value.md", "composer-2.5\n")
    write(tmp_path, "docs/fixture.md", "composer-2.5\n")
    configured = copy.deepcopy(registry())
    configured["premises"][0]["exclude_paths"] = ["docs/fixture.md"]
    assert validate_registry(
        tmp_path, configured, ["docs/value.md", "docs/fixture.md"]
    ) == []


def test_token_boundary_rejects_longer_identifier(tmp_path):
    write(tmp_path, "docs/value.md", "composer-2.5Tool\n")
    problems = validate_registry(tmp_path, registry(), ["docs/value.md"])
    assert any("declared occurrence has no match" in problem for problem in problems)


def test_cursor_skills_pattern_rejects_lookalike_directories():
    pattern = re.compile(CURSOR_SKILLS_PATTERN)

    assert pattern.search("~/.cursor/skills/setup/SKILL.md")
    assert pattern.search(r"C:\Users\user\.cursor\skills\setup\SKILL.md")
    for value in (
        "~/.cursor/skills-old",
        "~/.cursor/skills.backup",
        "~/.cursor/skills_extra",
        "~/.cursorx/skills",
    ):
        assert not pattern.search(value)


def test_obsolete_pattern_fails_when_old_value_remains(tmp_path):
    write(tmp_path, "docs/value.md", "composer-2.5\ncomposer-2.4\n")
    configured = registry()
    configured["premises"][0]["obsolete_value_patterns"] = [
        r"(?<![A-Za-z0-9_])composer-2\.4(?![A-Za-z0-9_])"
    ]
    problems = validate_registry(tmp_path, configured, ["docs/value.md"])
    assert any(
        problem == "obsolete value present: cursor-model docs/value.md (1 matches)"
        for problem in problems
    )


def test_obsolete_pattern_is_green_when_old_value_is_absent(tmp_path):
    write(tmp_path, "docs/value.md", "composer-2.5\n")
    configured = registry()
    configured["premises"][0]["obsolete_value_patterns"] = [
        r"(?<![A-Za-z0-9_])composer-2\.4(?![A-Za-z0-9_])"
    ]
    assert validate_registry(tmp_path, configured, ["docs/value.md"]) == []


def test_obsolete_patterns_default_to_empty_list(tmp_path):
    write(tmp_path, "docs/value.md", "composer-2.5\n")
    configured = registry()
    configured["premises"][0].pop("obsolete_value_patterns")
    assert validate_registry(tmp_path, configured, ["docs/value.md"]) == []


def test_obsolete_scan_respects_premise_exclude_paths(tmp_path):
    write(tmp_path, "docs/value.md", "composer-2.5\n")
    write(tmp_path, "docs/fixture.md", "composer-2.4\n")
    configured = registry()
    configured["premises"][0]["obsolete_value_patterns"] = [
        r"(?<![A-Za-z0-9_])composer-2\.4(?![A-Za-z0-9_])"
    ]
    configured["premises"][0]["exclude_paths"] = ["docs/fixture.md"]
    assert validate_registry(
        tmp_path, configured, ["docs/value.md", "docs/fixture.md"]
    ) == []


def test_obsolete_pattern_requires_token_boundaries(tmp_path):
    configured = registry()
    configured["premises"][0]["obsolete_value_patterns"] = ["composer-2.4"]
    problems = validate_registry(tmp_path, configured, [])
    assert any("obsolete pattern lacks token boundaries" in problem for problem in problems)
