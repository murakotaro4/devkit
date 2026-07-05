from __future__ import annotations

import pytest

import check_plugin_version_bump


def test_parse_semver_and_compare_semver():
    assert check_plugin_version_bump.parse_semver("5.2.0") == (5, 2, 0)
    assert check_plugin_version_bump.parse_semver("5.2.0-beta.1") == (5, 2, 0)
    assert check_plugin_version_bump.parse_semver("v5.2.0") is None
    assert check_plugin_version_bump.compare_semver((5, 2, 0), (5, 1, 9)) > 0
    assert check_plugin_version_bump.compare_semver((5, 1, 0), (5, 1, 0)) == 0
    assert check_plugin_version_bump.compare_semver((5, 0, 9), (5, 1, 0)) < 0


def test_requires_version_gate_normalizes_path_separator():
    assert check_plugin_version_bump.requires_version_gate(["plugins\\devkit\\skills\\x\\SKILL.md"])
    assert check_plugin_version_bump.requires_version_gate([".claude-plugin/marketplace.json"])
    assert not check_plugin_version_bump.requires_version_gate(["README.md"])


def test_parse_version_strips_bom_and_requires_version():
    assert check_plugin_version_bump.parse_version('\ufeff{"version": "5.2.0"}', "head") == "5.2.0"
    with pytest.raises(RuntimeError, match="version missing"):
        check_plugin_version_bump.parse_version("{}", "head")
