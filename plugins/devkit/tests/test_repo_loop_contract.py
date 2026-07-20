"""repo-loop スキル(リポジトリ自律改善ループ)の契約テスト."""

from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SKILL_PATH = REPO_ROOT / "plugins" / "devkit" / "skills" / "repo-loop" / "SKILL.md"
OPENAI_YAML_PATH = (
    REPO_ROOT / "plugins" / "devkit" / "skills" / "repo-loop" / "agents" / "openai.yaml"
)


def _skill_text() -> str:
    return SKILL_PATH.read_text(encoding="utf-8")


def _frontmatter() -> str:
    text = _skill_text()
    match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    assert match, "frontmatter が見つからない"
    return match.group(1)


def test_skill_exists():
    assert SKILL_PATH.exists(), "repo-loop の SKILL.md が存在しない"


def test_skill_frontmatter_contract():
    frontmatter = _frontmatter()
    assert 'name: "repo-loop"' in frontmatter
    assert "description:" in frontmatter
    assert "/repo-loop" in frontmatter
    assert "argument-hint:" in frontmatter
    assert "allowed-tools" not in frontmatter


def test_agents_openai_yaml_exists_and_has_display_name():
    assert OPENAI_YAML_PATH.exists(), "agents/openai.yaml が存在しない"
    text = OPENAI_YAML_PATH.read_text(encoding="utf-8")
    assert "display_name" in text


def test_outcome_five_values_are_documented():
    text = _skill_text()
    for outcome in ("noop", "draft_pr", "proposal", "blocked", "failed"):
        assert outcome in text, f"outcome `{outcome}` が記載されていない"


def test_select_one_contract():
    text = _skill_text()
    assert "SELECT_ONE" in text
    assert "1 回の run で複数課題を実装してはならない" in text
    assert "最大 3 件" in text


def test_noop_is_normal_outcome():
    text = _skill_text()
    assert "noop" in text
    assert "正常" in text
    # noop と正常が近い文脈で共起すること
    assert re.search(r"noop.*正常|正常.*noop", text, re.DOTALL)


def test_attempt_limit_is_two():
    text = _skill_text()
    assert "attempt" in text.lower() or "試行" in text
    assert "2 回" in text or "attempt < 2" in text or "attempt = 2" in text


def test_high_risk_downgrades_to_proposal():
    text = _skill_text()
    assert "high" in text
    assert "実装しない" in text
    assert "proposal" in text or "提案" in text


def test_draft_pr_exit_and_forbidden_publish_ops():
    text = _skill_text()
    assert "Draft PR" in text
    assert "auto-merge" in text
    assert "ready" in text.lower() or "ready 化" in text or "ready for review" in text
    assert "force push" in text
    assert "default branch" in text


def test_worktree_required():
    text = _skill_text()
    assert "専用 worktree" in text or "worktree" in text
    assert "通常 checkout には書き込まない" in text


def test_thoughtdb_readonly_and_nonfatal_missing():
    text = _skill_text()
    assert "read-only" in text
    assert "ThoughtDB" in text or "thought-db" in text
    assert "blocked にしない" in text


def test_private_thoughtdb_not_copied_to_public_artifacts():
    text = _skill_text()
    assert "転記しない" in text
    assert "公開" in text


def test_noninteractive_does_not_ask():
    text = _skill_text()
    assert "非対話" in text
    assert "質問しない" in text


def test_hidden_run_marker_dedup():
    text = _skill_text()
    assert "<!-- repo-loop-run:" in text
    assert "重複" in text or "冪等" in text or "同じ marker" in text


def test_no_scheduler_or_persistence_runtime():
    text = _skill_text()
    assert "LangGraph" in text or "Temporal" in text or "scheduler" in text
    assert "永続化" in text


def test_no_repo_maintainer_revival():
    text = _skill_text()
    assert "repo_maintainer.py" in text
    assert ".devkit/repo-maintainer.toml" in text
    assert "復活" in text


def test_progress_visibility_section():
    text = _skill_text()
    assert "## 進捗可視化" in text
    assert "1 ジョブ = 1 タスク" in text


def test_shared_skill_contract_reference():
    text = _skill_text()
    assert "スキル共通契約" in text
