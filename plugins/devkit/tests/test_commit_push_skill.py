"""commit-push スキル(安全な分割 commit + push)の契約テスト."""

from __future__ import annotations

import ast
import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SKILL_PATH = REPO_ROOT / "plugins" / "devkit" / "skills" / "commit-push" / "SKILL.md"
OPENAI_YAML_PATH = (
    REPO_ROOT / "plugins" / "devkit" / "skills" / "commit-push" / "agents" / "openai.yaml"
)
EXPECTED_ALLOWED_TOOLS = [
    "Read",
    "Grep",
    "Glob",
    "Bash",
    "AskUserQuestion",
    "request_user_input",
    "TaskCreate",
    "TaskUpdate",
]


def _skill_text() -> str:
    return SKILL_PATH.read_text(encoding="utf-8")


def _frontmatter() -> str:
    match = re.match(r"^---\n(.*?)\n---\n", _skill_text(), re.DOTALL)
    assert match
    return match.group(1)


def test_skill_exists():
    assert SKILL_PATH.exists()


def test_agents_openai_yaml_exists():
    assert OPENAI_YAML_PATH.exists()


def test_skill_frontmatter_contract():
    frontmatter = _frontmatter()
    assert re.search(r'^name: "commit-push"$', frontmatter, re.MULTILINE)
    assert re.search(r'^argument-hint: "\[scope\]"$', frontmatter, re.MULTILINE)
    tools = re.search(r"^allowed-tools:\s*(\[.*\])$", frontmatter, re.MULTILINE)
    assert tools
    assert ast.literal_eval(tools.group(1)) == EXPECTED_ALLOWED_TOOLS


def test_commit_safety_invariants():
    text = _skill_text()
    commit = text[text.index("### commit") : text.index("### secret 2 層検査")]
    assert "最大 5 個" in commit
    assert "日本語 Conventional Commits" in commit
    assert "`git --literal-pathspecs add -- <paths>`" in commit
    assert {"git add -A", "git add .", "git commit -a", "--no-verify"} <= set(re.findall(r"`([^`]+)`", commit))
    assert "staged path 完全一致" in commit
    assert "commit path 完全一致" in commit


def test_secret_two_layer_contract():
    text = _skill_text()
    section = text[text.index("### secret 2 層検査") : text.index("### push")]
    rows = re.findall(r"^\| (path|staged 内容) \| (.+) \|$", section, re.MULTILINE)
    assert {name for name, _ in rows} == {"path", "staged 内容"}
    assert "値は表示しない" in section
    assert "自動除外せず停止" in section
    assert "バイナリ・巨大ファイル" in section


def test_push_contract_uses_single_explicit_refspec():
    text = _skill_text()
    section = text[text.index("### push") : text.index("## フロー")]
    assert "`git rev-parse --abbrev-ref --symbolic-full-name @{u}`" in section
    assert "`git push <remote> HEAD:<branch>`" in section
    assert all(prohibited in section for prohibited in ("force push", "`--tags`", "複数 ref"))
    assert all(blocker in section for blocker in ("upstream 不在", "detached HEAD", "origin なし"))
    assert all(forbidden_recovery in section for forbidden_recovery in ("自動 rebase", "merge", "別 branch push"))
    assert "承認時と push 直前の remote / branch が完全一致する場合だけ進む" in section


def test_harness_contract_is_centralized():
    text = _skill_text()
    section = text[text.index("## ハーネス判定") : text.index("## 安全契約")]
    assert all(tool in section for tool in ("AskUserQuestion", "spawn_agent", "request_user_input", "TaskCreate", "TaskUpdate"))
    assert "判定キーに使わない" in section
    assert text.count("## ハーネス判定") == 1
