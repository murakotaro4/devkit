"""refactor スキル(技術的負債棚卸し + dig-goal 引き継ぎ)の契約テスト."""

from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SKILL_PATH = REPO_ROOT / "plugins" / "devkit" / "skills" / "refactor" / "SKILL.md"
OPENAI_YAML_PATH = (
    REPO_ROOT / "plugins" / "devkit" / "skills" / "refactor" / "agents" / "openai.yaml"
)


def _skill_text() -> str:
    return SKILL_PATH.read_text(encoding="utf-8")


def _frontmatter() -> str:
    text = _skill_text()
    match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    assert match, "frontmatter が見つからない"
    return match.group(1)


def test_skill_exists():
    assert SKILL_PATH.exists(), "refactor の SKILL.md が存在しない"


def test_skill_frontmatter_read_only_contract():
    frontmatter = _frontmatter()
    assert 'name: "refactor"' in frontmatter
    assert "description:" in frontmatter
    assert "リファクタリングして" in frontmatter
    assert "負債を棚卸しして" in frontmatter
    assert "/refactor" in frontmatter
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
        "Skill",
    ]
    actual_tools = re.findall(r'"([^"]+)"', allowed_tools)
    assert actual_tools == expected_tools
    assert "Write" not in actual_tools, "read-only 契約に反して Write が含まれている"
    assert "Edit" not in actual_tools, "read-only 契約に反して Edit が含まれている"


def test_dig_goal_handoff_contract():
    text = _skill_text()
    assert "plugins/devkit/skills/dig-goal/SKILL.md" in text
    assert "dig-goal の step 2" in text
    assert "計画草案" in text
    assert "Skill ツール" in text
    assert "$dig-goal" in text
    assert "実装・backend 選択・レビュー" in text


def test_inventory_and_prioritization_flow_headings():
    text = _skill_text()
    assert "### 2. 棚卸し" in text
    assert "git log --numstat" in text
    assert "ホットスポット" in text
    assert "コード重複" in text
    assert "TODO/FIXME" in text
    assert "テスト欠落" in text
    assert "依存の問題" in text
    assert "file:line" in text
    assert "影響" in text
    assert "コスト" in text
    assert "リスク" in text

    assert "### 3. 優先順位付け" in text
    assert "影響 x コスト x リスク" in text
    assert "S/A/B/C" in text
    assert "選択肢付き質問" in text


def test_harness_detection_section():
    text = _skill_text()
    assert "## ハーネス判定" in text
    assert "Claude 親" in text
    assert "Codex 親" in text
    assert "AskUserQuestion" in text
    assert "request_user_input" in text


def test_agents_openai_yaml_exists():
    assert OPENAI_YAML_PATH.exists(), "agents/openai.yaml が存在しない"
    text = OPENAI_YAML_PATH.read_text(encoding="utf-8")
    assert 'display_name: "Refactor"' in text
    assert "$refactor" in text
    assert "$dig-goal" in text
