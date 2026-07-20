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


def test_init_fetches_latest_origin_for_observation():
    text = _skill_text()
    assert "git fetch <remote>" in text
    assert "<remote>/<default>" in text
    assert "観測基準" in text
    assert "fetch 不能なら警告" in text
    assert "既定名は" in text and "origin" in text


def test_prepare_worktree_revalidates_evidence_and_unique_branch():
    text = _skill_text()
    assert "repo-loop/<YYYYMMDD>-<slug>" in text
    assert "run_key" in text
    assert "一意サフィックス" in text
    assert "最新 base 上で再検証" in text
    assert "解消済みなら実装せず" in text
    assert "noop" in text
    assert "<remote>/<default>" in text


def test_commit_before_independent_review():
    text = _skill_text()
    assert "レビュー前に selected_task の実装を作業 branch へ commit する" in text
    assert "commit 済み diff" in text
    assert "レビュー済み commit の push" in text
    assert "--base <remote>/<default>" in text


def test_envelope_scope_constrains_write_scope():
    text = _skill_text()
    assert "envelope で `scope` が与えられた場合" in text
    assert "部分集合" in text
    assert "scope 外の変更が必要と判明したら実装せず" in text


def test_resolved_remote_used_throughout():
    text = _skill_text()
    assert "以降の fetch / base 解決 / レビュー / publication の全工程でその remote を使う" in text
    assert "origin/<default>" not in text


def test_risk_includes_none_before_risk_gate():
    text = _skill_text()
    assert '"risk": "low | medium | high | none"' in text
    assert "RISK_GATE 到達前に終了した run では" in text
    assert "none" in text


def test_worktree_cleanup_at_run_end():
    text = _skill_text()
    assert "git worktree remove" in text
    assert "--force" in text
    assert "この run が作成した一時 worktree" in text
    assert "branch は削除しない" in text
    assert "他セッションの worktree" in text


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
