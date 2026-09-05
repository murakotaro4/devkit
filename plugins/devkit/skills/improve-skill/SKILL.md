---
name: "improve-skill"
description: "現在セッションを根拠にスキルの改善案または修正を作る。手動の『スキルを改善して』『セッションを振り返って直して』『/improve-skill』で起動。"
allowed-tools: ["Read", "Edit", "Write", "Grep", "Glob", "Bash", "AskUserQuestion", "request_user_input", "spawn_agent", "wait_agent", "TaskCreate", "TaskUpdate", "TaskOutput"]
---

# /improve-skill - Session-Aware Skill Improver

現在セッションだけを根拠に、スキル改善を提案または適用する。手動起動専用で、他スキルから自動起動しない。

## トピック

$ARGUMENTS

## ハーネス判定

`request_user_input` は判定キーに使わない。

| 判定 | 質問 | 独立レビュー |
|---|---|---|
| `AskUserQuestion` が使える Claude 親 | `AskUserQuestion` | codex |
| 上記がなく `spawn_agent` が使える Codex 親 | plan mode は `request_user_input`、通常 mode は選択肢 + 自由文 | `spawn_agent` / `wait_agent` |
| 判定不能 | 選択肢 + 自由文 | 利用可能な別系統 |

主要工程をタスク化し、委譲も 1 ジョブ = 1 タスクとする。Codex 親は待機中も進捗を示し、停滞時だけ継続時間と推定原因を報告する。

## モード契約

| モード | 判定 | 出力・書き込み | 固有条件 |
|---|---|---|---|
| `refresh` | `$ARGUMENTS` に `--refresh` | 改善チェックリストのみ。Edit / Write / commit 禁止 | 対象スキルを名前かパスで確定 |
| `create` | `$ARGUMENTS` に `--create` | 新規案チェックリストのみ。Edit / Write / commit 禁止 | スキル採用基準との照合を含める |
| `retro` | それ以外(引数なし含む) | 承認後だけ対象へ編集。commit は明示時のみ | 1 セッション 1 回。plan mode は提案まで |

`refresh/create` は回答不足のまま推測しない。候補提示と再質問でも確定できなければ停止する。`retro` は検出なしなら「振り返り不要」、実行済みなら「振り返り済み」、自身の失敗は警告して終了する。

## 共通骨格

1. 現在セッションから根拠を抽出する。履歴ファイルを勝手に参照しない。
2. 対象の関連ファイルを読み、根本原因と最小変更を分析する。
3. モード差分に従い提案を提示し、書き込みがある場合は先に承認を得る。
4. 承認範囲だけ適用し、独立レビューを行う。提案専用モードは適用・レビューなし。

モードを確定したら、質問前に [質問フロー](references/question-flow.md) の該当モードを読む。評価・承認・適用前には [評価と適用](references/checklist.md) の該当節を読む。

## refresh / create

質問前に [質問フロー](references/question-flow.md) を最後まで読む。回答不足のまま推測せず、現在セッションの抽出、`refresh` / `create` の生成、採用基準への照合、固定見出しのチェックリスト出力まで同文書に従う。提案だけで終了し、編集・独立レビュー・commit は行わない。

## retro

検出前に [評価と適用](references/checklist.md) の「retro」を読む。現在セッションのエラー、ユーザーフィードバック、再利用可能な即興手順を分析し、before / after と対象ファイルを提示する。承認差分だけ適用して独立レビューを行い、commit はユーザー明示時だけ今回編集したファイルへ限定する。

## 参照資産

- `references/checklist.md`
- `references/question-flow.md`
- `scripts/session_extract.py`
- `scripts/refresh_mapper.py`
- `scripts/create_blueprint.py`
