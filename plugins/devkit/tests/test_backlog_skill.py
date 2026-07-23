"""backlog スキル(残課題の横断棚卸し)の契約テスト."""

from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SKILL_PATH = REPO_ROOT / "plugins" / "devkit" / "skills" / "backlog" / "SKILL.md"
OPENAI_YAML_PATH = REPO_ROOT / "plugins" / "devkit" / "skills" / "backlog" / "agents" / "openai.yaml"


def _skill_text() -> str:
    return SKILL_PATH.read_text(encoding="utf-8")


def _frontmatter() -> str:
    text = _skill_text()
    match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    assert match, "frontmatter が見つからない"
    return match.group(1)


def test_skill_exists():
    assert SKILL_PATH.exists(), "backlog の SKILL.md が存在しない"


def test_skill_frontmatter_contract():
    frontmatter = _frontmatter()
    assert 'name: "backlog"' in frontmatter
    assert "description:" in frontmatter
    assert "残りの作業は?" in frontmatter
    assert "残課題を棚卸しして" in frontmatter
    assert "やり残しを確認して" in frontmatter
    assert "/backlog" in frontmatter
    assert 'argument-hint: "[topic]"' in frontmatter

    allowed_tools_match = re.search(r"allowed-tools:\s*\[(.*?)\]", frontmatter)
    assert allowed_tools_match, "allowed-tools が見つからない"
    actual_tools = re.findall(r'"([^"]+)"', allowed_tools_match.group(1))
    assert actual_tools == [
        "Read",
        "Grep",
        "Glob",
        "Bash",
        "AskUserQuestion",
        "request_user_input",
        "TaskCreate",
        "TaskUpdate",
        "Skill",
    ]
    assert "Write" not in actual_tools
    assert "Edit" not in actual_tools


def test_read_only_contract_and_five_step_flow():
    text = _skill_text()
    assert "## read-only 契約" in text
    assert "allowed-tools に Write / Edit を含めない" in text
    for step in (
        "### 1. スコープ確認",
        "### 2. 情報源スキャン",
        "### 3. 統合と鮮度判定",
        "### 4. ダッシュボード提示",
        "### 5. dig への引き継ぎで終了",
    ):
        assert step in text
    assert "チャットへ提示" in text
    assert "ファイルへは保存しない" in text


def test_dashboard_starts_with_summary_and_marks_backends_not_applicable():
    text = _skill_text()
    dashboard = text[text.index("### 4. ダッシュボード提示") : text.index("### 5. dig への引き継ぎで終了")]
    assert "結論 + 推奨次アクション(3 件以内)" in dashboard
    assert "先頭提示" in dashboard
    assert "計画レビュー / 実装 / diff レビューをすべて「適用なし」" in dashboard
    assert "独立レビュー状態: `適用なし`" in dashboard


def test_sources_freshness_and_gh_fallback_are_present():
    text = _skill_text()
    for source in (
        ".claude/handoff/*.md",
        ".claude/plans/*.md",
        ".claude/goal-runs/*.md",
        "未 push commit",
        "未マージブランチ",
        "git stash list",
        "open PR",
        "未解決レビューコメント",
        "CI が落ちている check",
    ):
        assert source in text
    assert "PR 更新時刻" in text
    assert "要確認" in text
    assert "gh 不在のため未確認" in text


def test_boundaries_and_dig_handoff_are_present():
    text = _skill_text()
    assert "## 境界" in text
    assert "refactor = コードの負債" in text
    assert "backlog = handoff、plan、goal run、git、GitHub に残る作業の残り" in text
    assert "handoff = セッション終了時に残作業を書く側" in text
    assert "backlog = 既存の handoff を含む情報源を読む側" in text
    assert "TaskList = セッション内" in text
    assert "コード内 TODO / FIXME は refactor の領分" in text
    assert "## dig step 2 計画草案" in text
    assert "### backlog 由来の根拠" in text
    assert "$dig" in text


def test_harness_and_task_list_contract():
    text = _skill_text()
    assert "## ハーネス判定" in text
    assert "## タスクリスト連動" in text
    assert "スキル共通契約" in text
    assert "AskUserQuestion" in text
    assert "request_user_input" in text
    assert "step 1-5" in text


def test_agents_openai_yaml_exists_and_mentions_backlog_surface():
    assert OPENAI_YAML_PATH.exists(), "agents/openai.yaml が存在しない"
    text = OPENAI_YAML_PATH.read_text(encoding="utf-8")
    assert 'display_name: "Backlog"' in text
    assert "$backlog" in text
