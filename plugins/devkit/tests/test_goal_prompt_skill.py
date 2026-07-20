"""goal-prompt スキル(Goal プロンプト保存生成)の契約テスト。"""

from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SKILL_PATH = REPO_ROOT / "plugins" / "devkit" / "skills" / "goal-prompt" / "SKILL.md"
OPENAI_YAML_PATH = SKILL_PATH.parent / "agents" / "openai.yaml"


def _skill_text() -> str:
    return SKILL_PATH.read_text(encoding="utf-8")


def _frontmatter() -> str:
    match = re.match(r"^---\n(.*?)\n---\n", _skill_text(), re.DOTALL)
    assert match, "frontmatter が見つからない"
    return match.group(1)


def _section(text: str, heading: str) -> str:
    start = text.index(heading)
    level = len(heading) - len(heading.lstrip("#"))
    match = re.search(rf"^#{{1,{level}}} (?!#)", text[start + len(heading) :], re.MULTILINE)
    return text[start:] if match is None else text[start : start + len(heading) + match.start()]


def test_skill_exists_and_frontmatter_contract():
    assert SKILL_PATH.exists()
    frontmatter = _frontmatter()
    assert 'name: "goal-prompt"' in frontmatter
    assert "description:" in frontmatter
    assert 'argument-hint: "[source]"' in frontmatter


def test_openai_yaml_surface():
    assert OPENAI_YAML_PATH.exists()
    metadata = OPENAI_YAML_PATH.read_text(encoding="utf-8")
    assert 'display_name: "Goal Prompt"' in metadata
    assert "$goal-prompt" in metadata


def test_not_an_implementation_skill():
    text = _skill_text()
    assert "実装スキルではない" in text


def test_save_destination_and_filename_contract():
    save_contract = _section(_skill_text(), "## 保存契約")
    assert ".claude/goal-runs/YYYY-MM-DD-<slug>-goal.md" in save_contract
    assert "既存ファイルがある場合は上書きせず" in save_contract
    assert "`-goal` サフィックスの前に連番を挟んだ `YYYY-MM-DD-<slug>-2-goal.md` から採番する" in save_contract


def test_gitignore_creation_contract():
    save_contract = _section(_skill_text(), "## 保存契約")
    assert "`.claude/goal-runs/.gitignore` が無ければ `*` 1 行で新規作成し" in save_contract
    assert "既存の `.gitignore` は内容を変更しない" in save_contract
    assert "`git check-ignore` で保存ファイルが ignore されているか確認し" in save_contract
    assert "ignore されていなければ最終出力で警告する" in save_contract
    assert "非 git ディレクトリでは検証不能のため skip する" in save_contract


def test_launch_prompt_output_basic_form():
    launch = _section(_skill_text(), "## 起動プロンプト出力")
    assert (
        "/goal .claude/goal-runs/YYYY-MM-DD-<slug>-goal.md を読み、"
        "記載された成功条件を満たすまで実行する。"
    ) in launch
    assert "完了時は成功条件ごとの達成状況、検証コマンドと終了コード、変更ファイル、残課題を会話へ提示する。" in launch
    assert "上限停止: <自動算出した値>。" in launch


def test_auto_calculated_stop_limits_contract():
    limits = _section(_skill_text(), "## 上限停止の自動算出")
    assert "毎回ユーザーへ聞かない" in limits
    for row in (
        ("小規模", "12 ターンまたは 45 分", "2 周", "20 分"),
        ("標準", "24 ターンまたは 120 分", "3 周", "30 分"),
        ("大規模", "40 ターンまたは 240 分", "4 周", "45 分"),
    ):
        for phrase in row:
            assert phrase in limits
    assert "複数 Goal への分割を提案" in limits


def test_prohibited_actions_contract():
    prohibitions = _section(_skill_text(), "## 禁止事項")
    for phrase in (
        "コード変更しない。",
        "実装しない。",
        "PR を作らない。",
        "commit しない。",
        "push しない。",
        "計画レビューしない。",
        "Goal プロンプトの独立レビューを行わない",
        "Claude Code 組み込み `/goal` を自動発動しない",
        "scheduler・loop 登録をしない。",
        "thought-db へ書き込まない。",
    ):
        assert phrase in prohibitions


def test_retired_terms_are_absent():
    text = _skill_text()
    for retired in ("現セッション自律実行", "起動プロンプト提示", "dig-goal"):
        assert retired not in text
