"""memory-review スキル(AI メモリ棚卸し・前提監査)の契約テスト."""

from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SKILL_PATH = REPO_ROOT / "plugins" / "devkit" / "skills" / "memory-review" / "SKILL.md"
OPENAI_YAML_PATH = (
    REPO_ROOT / "plugins" / "devkit" / "skills" / "memory-review" / "agents" / "openai.yaml"
)


def _skill_text() -> str:
    return SKILL_PATH.read_text(encoding="utf-8")


def _frontmatter() -> str:
    text = _skill_text()
    match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    assert match, "frontmatter が見つからない"
    return match.group(1)


def test_skill_exists():
    assert SKILL_PATH.exists(), "memory-review の SKILL.md が存在しない"


def test_skill_frontmatter_contract():
    frontmatter = _frontmatter()
    assert 'name: "memory-review"' in frontmatter
    assert "description:" in frontmatter
    assert "メモリを棚卸しして" in frontmatter
    assert "メモリ監査して" in frontmatter
    assert "前提を点検して" in frontmatter
    assert "/memory-review" in frontmatter
    assert 'argument-hint: "[scope]"' in frontmatter

    allowed_tools_match = re.search(r"allowed-tools:\s*\[(.*?)\]", frontmatter)
    assert allowed_tools_match, "allowed-tools が見つからない"
    allowed_tools = allowed_tools_match.group(1)
    expected_tools = [
        "Read",
        "Grep",
        "Glob",
        "Bash",
        "AskUserQuestion",
        "request_user_input",
        "TaskCreate",
        "TaskUpdate",
        "TaskOutput",
        "Skill",
        "Agent",
        "spawn_agent",
        "wait_agent",
        "Write",
        "Edit",
    ]
    actual_tools = re.findall(r'"([^"]+)"', allowed_tools)
    assert actual_tools == expected_tools


def test_write_contract_has_step_boundaries_and_approval_gates():
    text = _skill_text()
    assert "step 1-4(スコープ確認・正本特定・監査・分類)は read-only" in text
    assert "step 5 は、保存先をユーザーに確認した後の監査レポートファイルの新規作成のみ Write 可" in text
    assert "レポート保存のためのディレクトリ作成だけ許可" in text
    assert "step 6 は、ユーザーが承認した軽微修正の適用のみ Edit / Write 可" in text
    assert "自動削除しない" in text
    assert "delete candidate は提示のみ" in text
    assert "承認を得てから適用" in text


def test_audit_flow_contains_required_taxonomies_and_output_format():
    text = _skill_text()
    for viewpoint in (
        "矛盾",
        "古い前提",
        "曖昧な指示",
        "重複",
        "危険な自動化",
        "参照設計",
        "テスト・検証",
        "記憶候補抽出",
    ):
        assert viewpoint in text

    for classification in (
        "keep",
        "update",
        "merge",
        "move",
        "archive",
        "delete candidate",
        "needs human decision",
    ):
        assert classification in text

    assert "影響度 3 段階" in text
    assert "高: 誤実装、情報漏えい、破壊的操作、レビュー漏れ" in text
    assert "中: 判断ブレ、手戻り、テスト漏れ" in text
    assert "低: 重複、軽微な古さ、参照性低下" in text

    expected_sections = [
        "## 1. 結論(3件以内)",
        "## 2. 全体評価",
        "## 3. 重要な問題点",
        "## 4. 分類結果",
        "## 5. 矛盾リスト",
        "## 6. 古い前提リスト",
        "## 7. AI が勝手に決めると危険な点",
        "## 8. 修正案(文章レベル)",
        "## 9. 推奨する配置",
        "## 10. 記憶候補(report-only)",
        "## 11. 次アクション(3つ以内)",
    ]
    actual_sections = re.findall(r"^## \d+\. .+$", text, re.MULTILINE)
    assert actual_sections == expected_sections


def test_dig_handoff_contract():
    text = _skill_text()
    assert "plugins/devkit/skills/dig/SKILL.md" in text
    assert "dig step 2 計画草案" in text
    assert "$dig" in text
    assert "大きい変更" in text
    assert "構成変更を伴う大きい修正" in text


def test_harness_detection_section():
    text = _skill_text()
    assert "## ハーネス判定" in text
    assert "Claude 親" in text
    assert "Codex 親" in text
    assert "AskUserQuestion" in text
    assert "request_user_input" in text
    assert "1 呼び出し最大 3 問" in text


def test_external_memory_scope_and_default_session_log_exclusion():
    text = _skill_text()
    assert "Claude auto-memory" in text
    assert "~/.claude/projects/<slug>/memory/" in text
    assert "~/.codex/memories/MEMORY.md" in text
    assert "~/.codex/AGENTS.md" in text
    assert "対象 repo に言及している記述だけ" in text
    assert "過去セッションの会話ログは読まない" in text
    assert "~/.codex/sessions" in text
    assert "`docs/reviews/` がなければ作成する" in text


def test_agents_openai_yaml_exists():
    assert OPENAI_YAML_PATH.exists(), "agents/openai.yaml が存在しない"
    text = OPENAI_YAML_PATH.read_text(encoding="utf-8")
    assert 'display_name: "Memory Review"' in text
    assert "$memory-review" in text
    assert "$dig" in text
