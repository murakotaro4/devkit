"""catch-up スキルの契約テスト。"""

from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SKILL_PATH = REPO_ROOT / "plugins/devkit/skills/catch-up/SKILL.md"
OPENAI_YAML_PATH = REPO_ROOT / "plugins/devkit/skills/catch-up/agents/openai.yaml"


def text() -> str:
    return SKILL_PATH.read_text(encoding="utf-8")


def test_frontmatter_contract():
    content = text()
    frontmatter = re.match(r"^---\n(.*?)\n---\n", content, re.DOTALL)
    assert frontmatter
    value = frontmatter.group(1)
    assert 'name: "catch-up"' in value
    assert 'argument-hint: "[何が変わったか]"' in value
    for phrase in ("キャッチアップして", "新モデルに追従して", "世代更新して", "/catch-up"):
        assert phrase in value
    for tool in ("Read", "Edit", "Write", "WebSearch", "AskUserQuestion", "spawn_agent"):
        assert f'"{tool}"' in value


def test_eight_step_workflow_and_registry_contract():
    content = text()
    headings = re.findall(r"^### (\d+)\. ", content, re.MULTILINE)
    assert headings == [str(number) for number in range(1, 9)]
    assert "plugins/devkit/premises.json" in content
    assert "check_external_premises.py" in content
    assert "current_value" in content
    assert "obsolete_value_patterns" in content
    assert "occurrences" in content
    assert "last_verified" in content


def test_approval_and_independent_review_contract():
    content = text()
    assert "承認前に Edit / Write を使わない" in content
    assert "独立レビュー(必須・スキップ不可)" in content
    assert "指摘を修正して再検証" in content
    assert "commit / push はユーザーが明示した場合だけ" in content


def test_harness_task_progress_and_boundaries():
    content = text()
    for heading in ("## ハーネス判定", "## タスクリスト連動", "## 進捗可視化"):
        assert heading in content
    assert "スキル共通契約" in content
    for boundary in ("memory-review", "improve-skill retro", "dig-goal"):
        assert boundary in content
    assert "workflow contract 自体の変更" in content


def test_openai_yaml_contract():
    content = OPENAI_YAML_PATH.read_text(encoding="utf-8")
    assert 'display_name: "Catch Up"' in content
    assert "short_description:" in content
    assert "$catch-up" in content
