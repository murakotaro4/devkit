from __future__ import annotations

from pathlib import Path

import check_skill_surface


REPO_ROOT = Path(__file__).resolve().parents[3]


def test_expected_skill_surface_matches_repository():
    skills_dir = REPO_ROOT / "plugins" / "devkit" / "skills"
    actual = {path.name for path in skills_dir.iterdir() if path.is_dir()}

    assert actual == check_skill_surface.EXPECTED_SKILLS == {"dig", "improve-skill"}


def test_removed_surface_contract_covers_v6_retirements():
    assert {
        "gpt-pro",
        "deep-research",
        "computer-use-chatgpt-pro",
        "codex-search",
        "discord-rust-server-ops",
        "repo-maintainer",
        "repo-maintainer-init",
    }.issubset(check_skill_surface.REMOVED_SKILL_DIRS)
    assert "plugins/devkit/scripts/chrome_chatgpt_runner.py" in check_skill_surface.REMOVED_PATHS
    assert "plugins/devkit/scripts/repo_maintainer.py" in check_skill_surface.REMOVED_PATHS
    assert "plugins/devkit/scripts/devkit-runtime-sync.sh" in check_skill_surface.REMOVED_PATHS
    assert "plugins/devkit/scripts/devkit-skill-update.ps1" in check_skill_surface.REMOVED_PATHS
    assert "plugins/devkit/.claude-plugin/marketplace.json" in check_skill_surface.REMOVED_PATHS
    assert ".devkit" in check_skill_surface.REMOVED_PATHS


def test_root_marketplace_source_points_to_existing_plugin_dir():
    market = check_skill_surface.read_json(".claude-plugin/marketplace.json")
    source = market["plugins"][0]["source"]

    assert (REPO_ROOT / source).is_dir()


def test_plugin_version_semver_floor_parser():
    assert check_skill_surface.parse_semver_tuple("6.0.0") == (6, 0, 0)
    assert check_skill_surface.parse_semver_tuple("6.0.0-alpha") == (6, 0, 0)
    assert check_skill_surface.parse_semver_tuple("6.0.1") == (6, 0, 1)
    assert check_skill_surface.parse_semver_tuple("6.1.0") == (6, 1, 0)
    assert check_skill_surface.parse_semver_tuple("7.0.0") == (7, 0, 0)
    assert check_skill_surface.parse_semver_tuple("6.0") is None
    assert check_skill_surface.parse_semver_tuple("not-a-version") is None
    assert check_skill_surface.parse_semver_tuple("06.0.0") is None
    assert check_skill_surface.semver_at_least("6.0.0", (6, 0, 0)) is True
    assert check_skill_surface.semver_at_least("6.0.0+build.1", (6, 0, 0)) is True
    assert check_skill_surface.semver_at_least("6.0.0-alpha", (6, 0, 0)) is False
    assert check_skill_surface.semver_at_least("6.0", (6, 0, 0)) is None


def test_ordered_subset_accepts_interleaved_commands():
    check_skill_surface.assert_ordered_subset(
        ["codex plugin list --json", "codex plugin marketplace upgrade murakotaro4"],
        ["codex plugin list --json", "codex plugin marketplace upgrade murakotaro4"],
        "unit",
    )


def test_powershell_codex_plugin_update_contract_is_enforced():
    problems: list[str] = []

    check_skill_surface.assert_powershell_codex_plugin_update_contract(problems)

    assert problems == []
