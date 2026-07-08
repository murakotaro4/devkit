"""handoff スキル(セッション引継ぎ書き出し)の契約テスト."""

from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SKILL_PATH = REPO_ROOT / "plugins" / "devkit" / "skills" / "handoff" / "SKILL.md"
OPENAI_YAML_PATH = REPO_ROOT / "plugins" / "devkit" / "skills" / "handoff" / "agents" / "openai.yaml"


def _skill_text() -> str:
    return SKILL_PATH.read_text(encoding="utf-8")


def _frontmatter() -> str:
    text = _skill_text()
    match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    assert match, "frontmatter が見つからない"
    return match.group(1)


def test_skill_exists():
    assert SKILL_PATH.exists(), "handoff の SKILL.md が存在しない"


def test_skill_frontmatter_contract():
    frontmatter = _frontmatter()
    assert 'name: "handoff"' in frontmatter
    assert "description:" in frontmatter
    assert "引き継ぎを書いて" in frontmatter
    assert "引継ぎドキュメントを作って" in frontmatter
    assert "ハンドオフを作って" in frontmatter
    assert "/handoff" in frontmatter
    assert 'argument-hint: "[topic]"' in frontmatter

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
        "Write",
    ]
    actual_tools = re.findall(r'"([^"]+)"', allowed_tools)
    assert actual_tools == expected_tools
    assert "Edit" not in actual_tools
    assert "Skill" not in actual_tools


def test_harness_and_task_list_contract():
    text = _skill_text()
    assert "## ハーネス判定" in text
    assert "## タスクリスト連動" in text
    assert "スキル共通契約" in text
    assert "Claude 親" in text
    assert "Codex 親" in text
    assert "AskUserQuestion" in text
    assert "request_user_input" in text
    assert "step 1-4" in text


def test_write_contract_limits_writes_and_execution():
    text = _skill_text()
    assert "step 1 は read-only" in text
    assert ".claude/handoff/YYYY-MM-DD-<slug>.md" in text
    assert "同名ファイルは上書きせず" in text
    assert "連番" in text
    assert "commit、push" in text
    assert "repo の `.gitignore` と `.git/info/exclude` は変更しない" in text


def test_gitignore_self_contained_contract():
    text = _skill_text()
    assert ".claude/handoff/.gitignore" in text
    assert "`*` 1 行" in text
    assert "既存の場合は内容を触らない" in text
    assert "冪等" in text
    assert "非 git repo では `.gitignore` 作成をスキップ" in text
    assert "保存は中止しない" in text
    assert "git check-ignore -q .claude/handoff/<ファイル名>" in text
    assert "未追跡差分に出る状態" in text


def test_slug_is_sanitized_not_used_verbatim():
    text = _skill_text()
    assert "^[a-z0-9]+(-[a-z0-9]+)*$" in text
    assert "そのまま slug に使わない" in text
    assert "正規化した slug を提案" in text


def test_handoff_template_sections_and_resume_line():
    text = _skill_text()
    for section in (
        "# Handoff: <短いタイトル> (YYYY-MM-DD)",
        "次セッションへの読み込ませ方",
        "## タスクの目的",
        "## 現在地",
        "## 完了したこと",
        "## 未完了・残作業",
        "## 次のアクション(推奨順)",
        "## 決定事項と理由",
        "## 未解決の質問・保留事項",
        "## 変更ファイル一覧",
        "## 検証状態",
        "## 会話文脈の要約",
    ):
        assert section in text
    assert "コミット済みと未コミットを区別" in text
    assert "未実行は「未実行」と明記" in text


def test_self_check_keywords_are_present():
    text = _skill_text()
    for check in (
        "再開可能性",
        "次アクション具体性",
        "事実と推測の区別",
        "秘密情報なし",
        "パスの曖昧さなし",
        "保存先契約",
    ):
        assert check in text


def test_read_mode_is_out_of_scope():
    text = _skill_text()
    assert "読み込みモード" in text
    assert "非対象" in text
    assert "自動復元" in text


def test_agents_openai_yaml_exists_and_mentions_handoff_surface():
    assert OPENAI_YAML_PATH.exists(), "agents/openai.yaml が存在しない"
    text = OPENAI_YAML_PATH.read_text(encoding="utf-8")
    assert 'display_name: "Handoff"' in text
    assert "$handoff" in text
    assert ".claude/handoff" in text