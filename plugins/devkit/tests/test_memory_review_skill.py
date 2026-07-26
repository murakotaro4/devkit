"""memory-review スキル(AI メモリ棚卸し・前提監査)の契約テスト."""

from __future__ import annotations

import ast
import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SKILL_PATH = REPO_ROOT / "plugins" / "devkit" / "skills" / "memory-review" / "SKILL.md"
OPENAI_YAML_PATH = (
    REPO_ROOT / "plugins" / "devkit" / "skills" / "memory-review" / "agents" / "openai.yaml"
)

EXPECTED_TOOLS = [
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
EXPECTED_CLASSIFICATIONS = {
    "keep",
    "update",
    "merge",
    "move",
    "archive",
    "delete candidate",
    "needs human decision",
}
EXPECTED_VIEWPOINTS = {
    "矛盾",
    "古い前提",
    "曖昧な指示",
    "重複",
    "危険な自動化",
    "検証可能性",
    "記憶候補抽出",
}


def _skill_text() -> str:
    return SKILL_PATH.read_text(encoding="utf-8")


def _frontmatter() -> str:
    match = re.match(r"^---\n(.*?)\n---\n", _skill_text(), re.DOTALL)
    assert match, "frontmatter が見つからない"
    return match.group(1)


def test_skill_exists():
    assert SKILL_PATH.exists()


def test_skill_frontmatter_contract():
    frontmatter = _frontmatter()
    assert re.search(r'^name: "memory-review"$', frontmatter, re.MULTILINE)
    assert re.search(r'^argument-hint: "\[scope\]"$', frontmatter, re.MULTILINE)
    assert all(trigger in frontmatter for trigger in ("メモリを棚卸しして", "メモリ監査して", "前提を点検して"))
    tools = re.search(r"^allowed-tools:\s*(\[.*\])$", frontmatter, re.MULTILINE)
    assert tools
    assert ast.literal_eval(tools.group(1)) == EXPECTED_TOOLS


def test_write_contract_has_step_boundaries_and_approval_gates():
    text = _skill_text()
    write_contract = text[text.index("## 書き込み契約") : text.index("## 監査対象 × 観点")]
    rows = dict(re.findall(r"^\| ([^|]+) \| ([^|]+) \|$", write_contract, re.MULTILINE))
    assert {"1-4", "5", "6", "7"} <= rows.keys()
    assert "read-only" in rows["1-4"]
    assert "新規作成" in rows["5"]
    assert "承認された軽微修正" in rows["6"]
    assert all(operation in write_contract for operation in ("削除", "上書き", "移動"))


def test_audit_taxonomies_are_complete():
    text = _skill_text()
    classifications = re.search(r"全項目を `([^`]+)` のいずれか", text)
    assert classifications
    assert {item.strip() for item in classifications.group(1).split("/")} == EXPECTED_CLASSIFICATIONS
    audit_section = text[text.index("## 監査対象 × 観点") : text.index("## フロー")]
    assert all(viewpoint in audit_section for viewpoint in EXPECTED_VIEWPOINTS)
    impact_levels = re.search(r"影響度を `([^`]+)` のいずれか", text)
    assert impact_levels
    assert {item.strip() for item in impact_levels.group(1).split("/")} == {"高", "中", "低"}
    assert "4 役(監査役 / 矛盾検出役 / 安全性レビュー役 / 修正案作成役)" in audit_section


def test_report_has_fixed_ordered_sections():
    text = _skill_text()
    report = text[text.index("### 5. 監査レポート出力") : text.index("### 6. 修正の承認と適用")]
    sections = re.findall(r"^## (\d+)\. ", report, re.MULTILINE)
    assert sections == [str(number) for number in range(1, 12)]


def test_conclusion_preserves_seven_category_summary():
    text = _skill_text()
    report = text[text.index("### 5. 監査レポート出力") : text.index("### 6. 修正の承認と適用")]
    categories = re.findall(r"^\d+\. (.+)$", report, re.MULTILINE)
    assert len(categories) == 7
    assert all(
        label in "\n".join(categories)
        for label in ("何を / なぜ", "判断してほしい点", "逸脱", "外部影響", "backend", "検証", "独立レビュー状態")
    )
    assert {"実施済み(指摘 N 件反映)", "skip(理由)", "適用なし"} <= set(re.findall(r"`([^`]+)`", report))


def test_dig_handoff_contract():
    text = _skill_text()
    handoff = text[text.index("### 6. 修正の承認と適用") : text.index("### 7. 完了報告")]
    assert "plugins/devkit/skills/dig/SKILL.md" in handoff
    assert "dig step 2 計画草案" in handoff
    assert all(field in handoff for field in ("目的", "write_scope", "実装手順", "検証", "非対象", "根拠"))
    assert "$dig" in handoff


def test_harness_detection_is_centralized():
    text = _skill_text()
    section = text[text.index("## ハーネス判定") : text.index("## 範囲と不変条件")]
    assert all(tool in section for tool in ("request_user_input", "wait_agent"))
    assert "判定キーに使わない" in section


def test_external_memory_scope_and_session_log_exclusion():
    text = _skill_text()
    assert all(
        path in text
        for path in (
            "~/.claude/projects/<slug>/memory/",
            "~/.codex/memories/MEMORY.md",
            "~/.codex/AGENTS.md",
            "~/repos/thought-db/",
            "~/.codex/sessions",
            "docs/reviews/",
        )
    )
    assert "過去セッションの会話ログは読まない" in text


def test_agents_openai_yaml_exists():
    assert OPENAI_YAML_PATH.exists()
    text = OPENAI_YAML_PATH.read_text(encoding="utf-8")
    assert 'display_name: "Memory Review"' in text
    assert all(skill in text for skill in ("$memory-review", "$dig"))
