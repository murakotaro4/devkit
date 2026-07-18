from __future__ import annotations

from pathlib import Path

import check_legacy_migration


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _findings(root: Path) -> list[dict[str, object]]:
    return check_legacy_migration.scan_dir(root)["findings"]


def test_detects_representative_legacy_patterns(tmp_path):
    legacy_command = "/devkit:" "codex"
    legacy_discord = "discord-" "rust-" "server-ops"
    legacy_sync = "devkit-" "runtime-sync"
    legacy_open = "opencode-" "ai"
    legacy_question_tool = "AskUser" "QuestionTool"
    _write(
        tmp_path / "docs" / "bad.md",
        f"{legacy_command}\n{legacy_discord}\n{legacy_sync}\n{legacy_open}\n{legacy_question_tool}\n",
    )

    tokens = {finding["token"] for finding in _findings(tmp_path)}

    assert legacy_command in tokens
    assert legacy_discord in tokens
    assert legacy_sync in tokens
    assert legacy_open in tokens
    assert legacy_question_tool in tokens


def test_detects_retired_dig_surfaces(tmp_path):
    # Positive fixtures intentionally reconstruct retired tokens; tests/ is excluded in repo mode.
    retired_tokens = (
        "/" + "dig",
        "/devkit:" + "dig",
        "$" + "dig",
        "plugins/devkit/skills/" + "dig/",
        "/" + "goal-" + "prompt",
        "devkit:" + "goal-" + "prompt",
        "$" + "goal-" + "prompt",
        "skills/" + "goal-" + "prompt",
    )
    _write(tmp_path / "docs" / "retired.md", "\n".join(retired_tokens) + "\n")

    tokens = {finding["token"] for finding in _findings(tmp_path)}

    assert set(retired_tokens) <= tokens


def test_current_dig_goal_surfaces_are_not_detected(tmp_path):
    current_tokens = (
        "/dig-goal",
        "$dig-goal",
        "devkit:dig-goal",
        "plugins/devkit/skills/dig-goal/",
    )
    _write(tmp_path / "docs" / "current.md", "\n".join(current_tokens) + "\n")

    assert _findings(tmp_path) == []


def test_prune_implementations_are_allowed_exceptions(tmp_path):
    retired = "/" + "dig"
    for relpath in (
        "plugins/devkit/scripts/devkit-lib.sh",
        "plugins/devkit/scripts/devkit-lib.ps1",
    ):
        _write(tmp_path / relpath, retired + "\n")

    assert _findings(tmp_path) == []


def test_retired_surface_replacement_points_to_dig_goal(tmp_path):
    retired = "/" + "goal-" + "prompt"
    _write(tmp_path / "docs" / "retired.md", retired + "\n")

    findings = _findings(tmp_path)

    assert len(findings) == 1
    assert "/dig-goal" in str(findings[0]["replacement"])


def test_migration_allow_suppresses_line(tmp_path):
    legacy = "auto-" "retro"
    _write(tmp_path / "docs" / "ok.md", f"{legacy} migration-allow\n")

    assert _findings(tmp_path) == []


def test_changelog_is_allowed_exception(tmp_path):
    legacy = "scripts/" "workflow.md"
    _write(tmp_path / "CHANGELOG.md", f"{legacy}\n")

    assert _findings(tmp_path) == []


def test_readme_migration_notice_allows_only_that_section(tmp_path):
    legacy = "discord-" "rust-" "skill"
    _write(
        tmp_path / "README.md",
        f"## Migration Notice\n{legacy}\n## Normal\n{legacy}\n",
    )

    findings = _findings(tmp_path)

    assert len(findings) == 1
    assert findings[0]["line"] == 4
