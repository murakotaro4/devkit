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


def _section(text: str, heading: str) -> str:
    start = text.index(heading)
    heading_level = len(heading) - len(heading.lstrip("#"))
    following = re.search(rf"\n#{{1,{heading_level}}}\s", text[start + len(heading):])
    if not following:
        return text[start:]
    return text[start:start + len(heading) + following.start()]


def _between(text: str, start: str, end: str) -> str:
    start_index = text.index(start)
    end_index = text.index(end, start_index + len(start))
    return text[start_index:end_index]


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
        "spawn_agent",
        "wait_agent",
        "TaskCreate",
        "TaskUpdate",
        "TaskOutput",
        "Write",
        "Skill",
        "Agent",
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


def test_codex_model_effort_contract():
    text = _skill_text()
    policy = _section(text, "## Codex モデル / effort 契約")

    assert "Codex のモデルは `gpt-5.6-sol` を `-m` で明示し" in policy
    assert "`medium` に固定する" in policy
    assert "effort の選択質問は行わない" in policy
    assert "catch-up スキルと `premises.json` で管理" in policy
    assert "- Low:" not in policy and "- XHigh:" not in policy, "effort ladder が残っている"
    assert "Max は対応 surface の最深推論" in policy
    assert "Ultra は並列オーケストレーション" in policy
    assert "選択肢、CLI の effort、config 値にはしない" in policy
    assert "並列方針はモデル / effort と独立に決める" in policy
    assert "子 agent ごとの effort 選択を追加しない" in policy
    assert "モデル / effort を指定できる経路だけに適用" in policy

    baked_models = set(re.findall(r"-m\s+(gpt-[\w.\-]+)", text))
    assert baked_models == {"gpt-5.6-sol"}, f"想定外のモデル焼き込み: {baked_models}"
    concrete_efforts = set(re.findall(r'model_reasoning_effort="([^"<>]+)"', text))
    assert concrete_efforts == {"medium"}, f"medium 以外の effort が残っている: {concrete_efforts}"


def test_write_contract_limits_writes_and_execution():
    text = _skill_text()
    assert "step 1-8 は対象 repo に対して read-only" in text
    assert "step 7 の独立レビュー運用" in text
    assert "`JOB_DIR` の作成とレビューログ書き込みは可" in text
    assert "対象 repo への書き込みは不可" in text
    assert "step 9 の Write 保存は、ファイルが必要な形態" in text
    assert "4,000 字超 fallback の場合だけ" in text
    assert "既定のインライン `/goal` と Codex 貼付けでは親はゴールファイルを作らない" in text
    assert ".claude/goal-runs/YYYY-MM-DD-<slug>-goal.md" in text
    assert "ゴールファイル `YYYY-MM-DD-<slug>[-N]-goal.md`" in text
    assert "連番 `-N` は `-goal` サフィックスの前" in text
    assert "同名は上書きしない" in text
    assert "親が `.claude/goal-runs/` と `*` 1 行の `.gitignore` を ensure" in text
    assert "インライン経路では実行エージェントが自己保存時に同じ ensure" in text
    assert "親が保存した後は `git check-ignore` で ignore が効いているか検証する" in text
    assert "この skill は起動プロンプトを提示して終了する" in text
    assert "実行開始" in text and "行わない" in text
    assert "cron 登録" in text
    assert "`/schedule` 登録" in text
    assert "commit、push" in text
    assert "step 9 は、ユーザーが実行を選択した場合のみ実行" not in text
    assert "実行できる経路" not in text


def test_interview_rounds_are_present():
    text = _skill_text()
    for heading in (
        "Round 1: 実行形態と対象",
        "Round 2: ゴール定義",
        "Round 3: 境界と停止条件",
        "Round 4: 運用と実行戦略",
    ):
        assert heading in text

    for required in (
        "形態(現セッション `/goal` / 別ターミナル `claude --bg` / `/loop` / `/schedule` / Codex 貼付け)",
        "タスク型(実装 / 調査 / 状態確認 / 文書化 / 整理)",
        "完了状態、検証方法、検証コマンド、品質バー",
        "非対象、上限停止の種類と値、行き詰まり時の扱い、破壊的操作の可否",
        "実装系のみ委譲先・並列方針・トークン効率方針",
    ):
        assert required in text

    assert "エンジン選択" not in text
    assert "実行エンジン" not in text
    assert "`gpt-5.6-sol` / `medium` 固定のため質問しない" in text


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
    strategy = _between(text, "## プロンプトテンプレート", "## セルフチェック")
    stop_conditions = _section(strategy, "## 停止条件(3 種)")
    assert "blocker と試行内容を進捗ログへ記録" in stop_conditions
    assert "代替アプローチを 2 案検討" in stop_conditions
    assert "最有力の案で続行" in stop_conditions
    assert "既存制約の内側" in stop_conditions
    assert "代替試行せず即停止" in stop_conditions
    failure_modes = _section(text, "## 排除する失敗モード")
    assert "blocker 即停止による不在時間の空転" in failure_modes


def test_prompt_template_and_self_check_contract():
    text = _skill_text()
    for section in (
        "## 実行モード: 不在自律実行",
        "## 目的",
        "## 成功条件(検証可能)",
        "## 検証コマンド",
        "## 制約・非対象",
        "## 停止条件(3 種)",
        "## 実行戦略(実装系のみ)",
        "## 進捗管理",
        "## 実装後レビュー",
        "## 完了レポート",
        "## 実行前提",
    ):
        assert section in text

    for check in (
        "検証可能性",
        "上限停止必須",
        "非対象・破壊的操作明記",
        "実行形態との無矛盾",
        "秘密情報なし",
        "受け渡し制約への適合",
        "実装系ゴール",
        "完了レポート",
    ):
        assert check in text

    self_check = _section(text, "## セルフチェック")
    assert len(re.findall(r"^\d+\. ", self_check, re.MULTILINE)) == 10
    assert "`実行戦略(実装系のみ)` と `実装後レビュー`" in text
    assert "逸脱時ログ記録の 1 行" in text
    assert "戦略から逸脱が必要なら理由を進捗ログに記録して保守的に判断する" in text
    assert "TaskCreate / TaskUpdate" in text
    assert "現セッション `/goal` ではインライン objective 全文が Unicode 文字数で 4,000 字以内" in text
    assert "Codex 貼付けは字数に関わらず全文 1 ブロックのまま" in text
    assert "4,001 字以上なら `.claude/goal-runs/` へのファイル保存 + 参照型へ fallback" in text
    assert "ファイル形態では参照パスが具体化済み" in text
    strategy = _between(text, "## プロンプトテンプレート", "## セルフチェック")
    assert strategy.index("## 実行モード: 不在自律実行") < strategy.index("## 目的")
    progress_management = _section(strategy, "## 進捗管理")
    assert "次にやること / 直近で決めた方針" in progress_management
    assert "コンテキスト圧縮後" in progress_management
    constraints = _section(strategy, "## 制約・非対象")
    assert "成功条件を満たしたことにしない" in constraints
    assert strategy.index("## 実装後レビュー") < strategy.index("## 完了レポート")
    assert strategy.index("## 完了レポート") < strategy.index("## 実行前提")
    completion_report = _section(strategy, "## 完了レポート")
    assert "読み返し" in completion_report
    for required in (
        ".claude/goal-runs/",
        "停止種別",
        "成功条件ごとの達成状況",
        "検証コマンド結果",
        "逸脱と判断ログ要約",
        "残課題",
        "変更ファイル一覧",
        "末尾の `-goal` サフィックスを除いた basename",
        "英小文字・数字・ハイフンへスラッグ化",
        "`YYYY-MM-DD-<slug>.md`",
        "step 6 の組み立て時に該当する具体名をこの節へ焼き込み",
        "`<basename>-2.md` からの連番",
        "「制約・非対象」や `write_scope` より優先する運用メタデータ領域として常に書き込みを許可",
        "実際に保存したファイル名の連番を反映した `<slug>-N.md` をレポート名として優先する(実ファイル名が正)",
    ):
        assert required in completion_report
    step6 = _section(text, "### 6. 組み立て + セルフチェック")
    assert "未保存なら短い名前から作る `YYYY-MM-DD-<slug>.md`" in step6
    assert "具体名をテンプレート本文へ焼き込む" in step6
    assert "objective 全文(ヘッダー・空行・本文込み、`/goal` プレフィックスを除く)" in step6
    assert "Unicode 文字数で数え、4,000 字以内ならインライン、4,001 字以上なら fallback" in step6
    assert "Codex 貼付けは字数に関わらず常に全文 1 ブロックとし、ファイル fallback へ分岐しない" in step6
    assert strategy.index("- 並列方針:") < strategy.index("- モデル / effort:")
    assert '`-m gpt-5.6-sol` + `model_reasoning_effort="medium"` 固定' in strategy
    assert "spawn_agent など非対応経路は適用なし" in strategy


def test_launch_command_table_and_codex_stdin_guard():
    text = _skill_text()
    assert "## 起動プロンプトの手引き" in text
    launch_guide = _section(text, "## 起動プロンプトの手引き")
    for surface in ("現セッション `/goal`", "別ターミナル `claude --bg`", "`/loop`", "`/schedule`", "Codex 貼付け"):
        assert surface in launch_guide
    assert launch_guide.count("提示のみ") >= 5
    assert (
        'cd "<対象repo>" && claude --bg --permission-mode acceptEdits --allowedTools "..." '
        '"/goal <保存したゴールファイルの絶対パス> '
        "の成功条件を満たす or stop after <N> turns。まず "
        '<保存したゴールファイルの絶対パス> を読め" < /dev/null'
    ) in launch_guide
    assert '--allowedTools "..."' in launch_guide
    assert "親が `.claude/goal-runs/<slug>-goal.md` へ保存" in launch_guide
    assert "同じマシン・同じ checkout から絶対パスで参照" in launch_guide
    assert "絶対パス" in launch_guide
    assert "Bash(codex:*)" in launch_guide
    assert "or stop after <N> turns" in launch_guide
    assert "4,000 字以内" in launch_guide
    assert "現セッション `/goal`(既定・インライン自己完結型)" in launch_guide
    assert "開始時に本文全文を .claude/goal-runs/<slug>-goal.md へ保存" in launch_guide
    assert "自己保存に失敗しても停止せず、失敗を進捗ログへ記録して続行せよ" in launch_guide
    assert launch_guide.count("同名ファイルが既にある場合は上書きせず") >= 2
    assert "objective 全文(ヘッダー・空行・本文込み)が Unicode 文字数で 4,000 字以内" in launch_guide
    assert "現セッション `/goal`(4,000 字超 fallback)" in launch_guide
    assert ".claude/goal-runs/YYYY-MM-DD-<slug>-goal.md" in launch_guide
    assert "/loop <interval> .claude/goal-runs/<file>-goal.md" in launch_guide
    assert "/schedule <trigger> .claude/goal-runs/<file>-goal.md" in launch_guide
    assert "同じマシン・同じ checkout で実行する前提" in launch_guide
    assert "loop 停止・schedule 解除までゴールファイルを削除しない" in launch_guide
    assert "登録はユーザーの 1 アクション" in launch_guide
    assert "codex exec" not in launch_guide
    assert "claude -p" not in launch_guide
    codex_paste_row = next(
        line for line in launch_guide.splitlines() if line.startswith("| Codex 貼付け")
    )
    assert "ゴール本文全文を 1 ブロックで提示" in codex_paste_row
    assert "常に本文全文を続け、ファイル参照へ分岐しない" in codex_paste_row
    assert "開始時に本文全文を `.claude/goal-runs/<slug>-goal.md` へ保存" in codex_paste_row
    assert "自己保存に失敗しても停止せず" in codex_paste_row
    assert "以下のゴールプロンプトを不在自律実行せよ" in codex_paste_row
    assert "質問・確認・承認求めを出力せず" in codex_paste_row
    assert "絶対パス" not in codex_paste_row
    assert "stop after" not in codex_paste_row

    offenders = [
        line for line in text.splitlines()
        if "codex -a never exec" in line and "< /dev/null" not in line
    ]
    assert not offenders, f"stdin 閉鎖(< /dev/null)がない codex コマンド行: {offenders}"

    codex_goal_offenders = [
        line for line in text.splitlines()
        if "codex -a never exec" in line
        and re.search(r"(?<![A-Za-z0-9_.-])/goal\b", line)
    ]
    assert not codex_goal_offenders, f"codex exec コマンド行に /goal が含まれている: {codex_goal_offenders}"

    model_offenders = [
        line for line in text.splitlines()
        if re.search(r"codex[^\n]*\s-m\s+(?!gpt-5\.6-sol\b)\S+", line, re.IGNORECASE)
    ]
    assert not model_offenders, f"gpt-5.6-sol 以外のモデル焼き込みがある: {model_offenders}"


def test_authoring_only_contract():
    text = _skill_text()
    for retired in (
        "tmux",
        "pipe-pane",
        "capture-pane",
        "Goal achieved",
        "claude agents",
        "エンジン選択",
        "codex exec 投入",
        "headless claude -p",
        "headless `claude -p`",
        "実行メカニズム一覧",
        "起動コマンド決定表",
        "必ず「実行しますか？」と確認",
        "実行(オプション",
        "監視または引き渡し",
        "監視 or 引き渡し",
        "引き渡し",
    ):
        assert retired not in text

    assert "### 7. ゴールプロンプト独立レビュー" in text
    step7 = _section(text, "### 7. ゴールプロンプト独立レビュー")
    assert '-C "<対象repo>"' in step7
    assert "--sandbox read-only" in step7
    assert "< /dev/null" in step7
    assert "JOB_DIR=<echo された記録済みのパス>" in step7
    assert "シェル変数はツール呼び出し間で失われるため" in step7
    assert "run_in_background" in step7
    assert "完了通知後に記録済み `JOB_DIR` の `review.log` を必ず読み" in step7
    assert "指摘ゼロを確認してから step 8 へ進む" in step7
    assert "指摘があれば step 6 に戻る" in step7
    assert "Agent(Claude サブエージェント)" in step7
    assert "`spawn_agent`(explorer)" in step7
    assert "`wait_agent`" in step7
    assert "step 8 へ進まない" in step7
    assert "保存はせず" in step7
    assert "再実行を案内して停止" in step7
    assert '-m gpt-5.6-sol -c model_reasoning_effort="medium"' in step7
    concrete_review_efforts = re.findall(r'model_reasoning_effort="([^"<>]+)"', step7)
    assert {value.lower() for value in concrete_review_efforts} == {"medium"}

    step9 = _section(text, "### 9. 成果物提示(必要時のみ保存)")
    assert "既定のインライン `/goal` と Codex 貼付けでは、親はゴールファイルを作らず" in step9
    assert "レビュー済み本文全文を含む自己完結起動ブロック 1 個 + 代替 1" in step9
    assert "ファイルが必要な形態" in step9
    assert "4,000 字超 fallback" in step9
    assert "`.claude/goal-runs/` へ Write でゴールファイルを新規保存" in step9
    assert "起動プロンプト" in step9 and "提示して終了" in step9
    assert "検収チェックリスト" in step9
    assert "具体的な完了レポート名を本文へ焼き込み" in step9
    assert "loop 停止・schedule 解除までゴールファイルを削除しない" in step9
    step8 = _section(text, "### 8. ユーザー最終確認")
    for step in (step8, step9):
        assert "Round 1 で Codex 貼付けを選択した場合" in step
        assert "不在自律実行ヘッダー付きの Codex 貼付け起動文を必ず含める" in step
    # 実行への言及は複合語の契約文脈だけ許す(skill 自身は実行しない)
    assert "起動" in step9 and "実行" not in step9.replace("再実行", "").replace("不在自律実行", "").replace("実行形態", "")

    assert "/goal` を付けるのは Claude 系の起動プロンプトだけ" in text
    assert "委譲先 codex exec には素の実装指示" in text


def test_dig_handoff_mode_contract():
    text = _skill_text()
    assert "## dig 引き継ぎモード" in text
    assert "計画にない項目だけの差分確認 1 ラウンド" in text
    assert "目的 / write_scope / 受け入れ条件 / 検証コマンド / 非対象は承認済み計画から転記" in text
    assert "起動プロンプト形態" in text
    assert "上限停止値" in text
    assert "行き詰まり停止の扱い" in text
    assert "破壊的操作の可否" in text
    assert "権限、進捗管理、実装戦略" in text
    assert "commit / push 禁止" in text
    assert "実装後レビュー要件、どの停止種別でも書き出す完了レポート要件は転記必須項目" in text
    assert "組み立て + セルフチェック 10 項目、独立レビュー、最終確認、成果物提示(必要時のみ保存)" in text
    assert "セルフチェック 10 項目" in text


def test_autonomous_execution_declaration_contract():
    text = _skill_text()
    strategy = _between(text, "## プロンプトテンプレート", "## セルフチェック")
    declaration = _section(strategy, "## 実行モード: 不在自律実行")
    assert "OK なら OK と返答してください" in declaration
    assert "承認求め" in declaration
    assert "停止条件(3 種)と即停止条件が常に優先する" in declaration
    assert "行き詰まり停止する(続行しない)" in declaration
    assert declaration.index("進捗ログへ記録して続行する") < declaration.index(
        "停止条件(3 種)と即停止条件が常に優先する"
    )

    failure_modes = _section(text, "## 排除する失敗モード")
    assert "確認待ち停止" in failure_modes

    execution_prerequisites = _section(strategy, "## 実行前提")
    assert (
        "確認・承認求め(「OK なら OK と返答してください」型を含む)も不可。"
        "冒頭の「実行モード: 不在自律実行」節に従う。"
    ) in execution_prerequisites


def test_retired_goal_prompt_phrases_are_absent():
    text = _skill_text()
    assert "docs" + "/goals" not in text
    for retired in (
        "`/goal` は" + "ユーザー" + "タイプ専用",
        "ユーザー" + "タイプ専用",
        "入れ子 " + "`claude -p`" + " は" + "非" + "公式",
        "非" + "公式の入れ子実行",
        "tmux",
        "pipe-pane",
        "capture-pane",
        "Goal achieved",
        "kill-session",
        "claude agents",
        "監視 or 引き渡し",
        "codex exec 投入",
    ):
        assert retired not in text


def test_agents_openai_yaml_exists_and_mentions_goal_prompt_and_dig():
    assert OPENAI_YAML_PATH.exists(), "agents/openai.yaml が存在しない"
    text = OPENAI_YAML_PATH.read_text(encoding="utf-8")
    assert 'display_name: "Goal Prompt"' in text
    assert "$goal-prompt" in text
    assert "$dig" in text
