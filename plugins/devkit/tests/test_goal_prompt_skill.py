"""goal-prompt スキル(ゴールプロンプト作成)の契約テスト."""

from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SKILL_PATH = REPO_ROOT / "plugins" / "devkit" / "skills" / "goal-prompt" / "SKILL.md"
OPENAI_YAML_PATH = (
    REPO_ROOT / "plugins" / "devkit" / "skills" / "goal-prompt" / "agents" / "openai.yaml"
)


def _skill_text() -> str:
    return SKILL_PATH.read_text(encoding="utf-8")


def _frontmatter() -> str:
    text = _skill_text()
    match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    assert match, "frontmatter が見つからない"
    return match.group(1)


def test_skill_exists():
    assert SKILL_PATH.exists(), "goal-prompt の SKILL.md が存在しない"


def test_skill_frontmatter_contract():
    frontmatter = _frontmatter()
    assert 'name: "goal-prompt"' in frontmatter
    assert "description:" in frontmatter
    assert "ゴールプロンプトを作って" in frontmatter
    assert "夜間実行の指示書を作って" in frontmatter
    assert "ループ用プロンプトを作って" in frontmatter
    assert "/goal-prompt" in frontmatter
    assert 'argument-hint: "[task]"' in frontmatter
    assert '"/goal"' not in frontmatter

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
        "Skill",
    ]
    actual_tools = re.findall(r'"([^"]+)"', allowed_tools)
    assert actual_tools == expected_tools
    assert "Edit" not in actual_tools


def test_harness_and_task_list_contract():
    text = _skill_text()
    assert "## ハーネス判定" in text
    assert "## タスクリスト連動" in text
    assert "スキル共通契約" in text
    assert "Claude 親" in text
    assert "Codex 親" in text
    assert "AskUserQuestion" in text
    assert "request_user_input" in text
    assert "step 1-9" in text
    assert "1 呼び出し最大 3 問" in text


def test_write_contract_limits_writes_and_execution():
    text = _skill_text()
    assert "step 1-7 は read-only" in text
    assert "step 8 は、ユーザーがファイル保存を選択した場合に Write で新規保存" in text
    assert "docs/goals/YYYY-MM-DD-<slug>.md" in text
    assert "同名ファイルは上書きせず" in text
    assert "step 9 は、ユーザーが実行を選択した場合のみ実行" in text
    assert "cron 登録" in text
    assert "`/schedule` 登録" in text
    assert "commit、push" in text


def test_interview_rounds_are_present():
    text = _skill_text()
    for heading in (
        "Round 1: 実行形態と対象",
        "Round 2: ゴール定義",
        "Round 3: 境界と停止条件",
        "Round 4: 運用",
    ):
        assert heading in text

    for required in (
        "形態(`/goal` / `/loop` / `/schedule` / headless / codex exec / 通常セッション)",
        "完了状態、検証方法、検証コマンド、品質バー",
        "非対象、上限停止の種類と値、行き詰まり時の扱い、破壊的操作の可否",
        "進捗の残し方、権限、途中中断と再開、完了報告の形式",
    ):
        assert required in text


def test_failure_modes_and_stop_conditions():
    text = _skill_text()
    assert "排除する失敗モード" in text
    assert "停止条件欠落" in text
    assert "ゴール誤解釈・スコープドリフト" in text
    assert "エージェント自己申告のみの成功条件は禁止" in text
    assert "実行中は質問不可。曖昧な点は保守的解釈 + 判断を進捗ログに記録" in text
    assert "達成停止" in text
    assert "上限停止" in text
    assert "行き詰まり停止" in text
    assert "上限停止は省略禁止" in text


def test_prompt_template_and_self_check_contract():
    text = _skill_text()
    for section in (
        "## 目的",
        "## 成功条件(検証可能)",
        "## 検証コマンド",
        "## 制約・非対象",
        "## 停止条件(3 種)",
        "## 進捗報告",
        "## 実行前提",
    ):
        assert section in text

    for check in (
        "検証可能性",
        "上限停止必須",
        "非対象・破壊的操作明記",
        "実行形態との無矛盾",
        "秘密情報なし",
        "機構の長さ・受け渡し制約への適合",
    ):
        assert check in text

    assert "/goal` 条件文 4,000 字上限" in text
    assert "長い本文はファイル参照" in text
    assert "CLI 引数は短い起動指示だけ" in text


def test_launch_command_table_and_codex_stdin_guard():
    text = _skill_text()
    assert "## 起動コマンド決定表" in text
    for surface in ("/goal", "/loop", "/schedule", "claude -p", "codex exec", "通常セッション"):
        assert surface in text

    offenders = [
        line for line in text.splitlines()
        if "codex -a never exec" in line and "< /dev/null" not in line
    ]
    assert not offenders, f"stdin 閉鎖(< /dev/null)がない codex コマンド行: {offenders}"

    model_offenders = [
        line for line in text.splitlines()
        if re.search(r"codex[^\n]*\s-m\s+\S+", line, re.IGNORECASE)
    ]
    assert not model_offenders, f"codex モデル焼き込みがある: {model_offenders}"


def test_execution_contract_is_confirmation_gated_and_bounded():
    text = _skill_text()
    assert "必ず「実行しますか？」と確認" in text
    assert "Codex 親は常に生成 + コマンド提示まで" in text
    assert "JOB_DIR=$(mktemp -d" in text
    assert 'echo "JOB_DIR=' in text
    assert "-C \"<対象repo>\"" in text
    assert "--sandbox workspace-write" in text
    assert "$JOB_DIR/codex.log" in text
    assert "--sandbox read-only" in text
    assert "60-120 秒ハートビート" in text
    assert "時刻・経過・ログ増分" in text
    assert "停止条件が機能したか" in text
    assert "loop` スキル不在時の fallback" in text
    assert "ループはセッションが開いている間だけ動く" in text
    assert "通常セッションのルール" in text
    assert "$dig" in text
    assert "`/goal` はユーザータイプ専用" in text
    assert "`/schedule` は登録しない" in text


def test_agents_openai_yaml_exists_and_mentions_goal_prompt_and_dig():
    assert OPENAI_YAML_PATH.exists(), "agents/openai.yaml が存在しない"
    text = OPENAI_YAML_PATH.read_text(encoding="utf-8")
    assert 'display_name: "Goal Prompt"' in text
    assert "$goal-prompt" in text
    assert "$dig" in text
