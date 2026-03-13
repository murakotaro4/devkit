---
name: "dig-claude"
description: "dig の Claude adapter。AskUserQuestionTool と Codex レビューで dig-core 契約を実行する。"
argument-hint: "[topic]"
allowed-tools: ["Read", "Edit", "Write", "Grep", "Glob", "Bash"]
---

# /dig-claude - Claude Adapter

dig-core 契約を Claude Code 環境で実行する adapter。

> `AskUserQuestionTool`・`Agent`・`TaskCreate`・`TaskUpdate`・`TaskList` は Claude Code のシステムツールであり、frontmatter の `allowed-tools` には書かない。

## 8フェーズ対応

Claude runtime での dig は、`workflow.md` と同じ 8 フェーズを使う。

1. Phase 1: 依頼確認と体制決め
2. Phase 2: 要件ヒアリング
3. Phase 3: 調査
4. Phase 4: 計画作成
5. Phase 5: 計画レビュー
6. Phase 6: 実装
7. Phase 7: 実装レビューと検証
8. Phase 8: コミットとプッシュ

旧 5 ステップは補助理解にとどめる。実際の説明・plan・hook state は常に `Phase 1` から `Phase 8` を使う。

## Plan Mode 共存

Plan Mode が既に有効でも dig は継続できるが、dig 自身が EnterPlanMode / ExitPlanMode を操作しない。

- Phase 1-5: AskUserQuestionTool と plan ファイルで進める
- Phase 6-8: ユーザーが通常実行へ進めた後に扱う

## 実行契約

| 機能 | Claude Code での実現手段 |
|------|--------------------------|
| 質問 | `AskUserQuestionTool` |
| コード探索 | `Agent` / `Grep` / `Glob` / `Read` |
| plan 記載 | `Write` |
| 計画レビュー / 実装レビュー | `codex exec` |
| 分解 | `devkit:decomposition` |
| タスク管理 | `TaskCreate` / `TaskUpdate` / `TaskList` |
| 実装 | `Agent` を優先、必要時のみ本体または tool-parallel |

## Hook 前提

Claude hook は `/dig` セッションを検出し、Phase 5 通過後の変更系ツールを監視する。

- `UserPromptSubmit`: dig セッション開始を記録
- `PostToolUse(Bash)`: plan review 成功を記録
- `PreToolUse`: Phase 5 は通過したが Phase 6 Tasks 未登録なら実装を block
- `Stop`: dig state を cleanup

つまり **Phase 5 通過後** に `[Phase 6]` 親タスクと `[Task 1]` 以降のサブタスクが無いまま `Edit` / `Write` / `Agent` / 変更系 `Bash` に入ることは許可しない。

## 共通サニタイズ関数

全レビューゲートで使用する秘匿情報サニタイズ関数:

```bash
dig_sanitize() {
  local src="$1" dst="$2"
  cp "$src" "$dst" || { echo "SANITIZE_CP_FAILED"; return 2; }
  sed -i -E 's/(api[_-]?key|secret|token|password|credential|private[_-]?key)\s*[=:]\s*\S+/\1=***REDACTED***/gi' "$dst" || { echo "SANITIZE_SED_FAILED"; return 2; }
  sed -i -E 's/(Bearer\s+)\S+/\1***REDACTED***/gi' "$dst" || { echo "SANITIZE_SED_FAILED"; return 2; }
  sed -i -E 's/(Authorization\s*[: ]+)(Basic|Bearer|Token|Digest)?\s*\S+/\1***REDACTED***/gi' "$dst" || { echo "SANITIZE_SED_FAILED"; return 2; }
  sed -i '/-----BEGIN.*PRIVATE KEY-----/,/-----END.*PRIVATE KEY-----/c\***PEM_REDACTED***' "$dst" || { echo "SANITIZE_SED_FAILED"; return 2; }
  sed -i -E 's/("(api[_-]?key|secret|token|password)"\s*:\s*")[^"]+"/\1***REDACTED***"/gi' "$dst" || { echo "SANITIZE_SED_FAILED"; return 2; }
  sed -i -E 's/([?&](token|key|secret|api_key)=)[^&\s]+/\1***REDACTED***/gi' "$dst" || { echo "SANITIZE_SED_FAILED"; return 2; }
  [ -s "$dst" ] || { echo "SANITIZE_OUTPUT_EMPTY"; return 2; }
  if grep -qE '[A-Za-z0-9+/=]{64,}' "$dst"; then
    echo "HIGH_ENTROPY_DETECTED"
    return 1
  fi
  return 0
}
```

## フェーズ別ガイド

### Phase 1: 依頼確認と体制決め

- ユーザー依頼の曖昧さと期待成果を確認する
- 初期 sizing を `small` / `medium` / `large` で仮置きする
- dig 本体は `Coordinator` 兼 `Planner` として振る舞う

### Phase 2: 要件ヒアリング

AskUserQuestionTool で深掘りする。

- 原則 4 問、複数選択優先
- 選択肢には description を付ける
- 最大 2 ラウンドまで再質問可
- AskUserQuestion が失敗したら停止する

質問は「非自明」「選択肢付き」「次の判断に効く」ものに限定する。

### Phase 3: 調査

コードベース調査を織り交ぜて、質問の文脈を具体化する。

- `Agent` を 1-3 本まで並列で使ってよい
- 調査対象は既存実装、関連コンポーネント、テストパターンを優先
- `.env`, `*.pem`, `*.key`, `credentials.json`, `secrets.*` は読まない
- `**/*` のような広域検索前には範囲と目的をユーザーに伝える

### Phase 4: 計画作成

plan ファイルを作り、承認前の分解結果をテキストでまとめる。

plan には最低限以下を入れる。

- topic の要約
- sizing / team_shape
- role_assignment
- write_scope
- Phase 6 で実装したいサブタスク案

`devkit:decomposition` を呼ぶ場合も **plan-only** で使う。Phase 4 では TaskCreate しない。

### Phase 5: 計画レビュー

分解済み plan を Codex でレビューする。

```bash
dig_sanitize <plan_file_path> /tmp/dig_plan_review_$$.md
codex exec -m gpt-5.3-codex-spark -c model_reasoning_effort="medium" \
  "以下のプランファイルをレビューしてください: /tmp/dig_plan_review_$$.md。
   観点: 実現可能性、既存構造との整合性、抜け漏れ、リスク、依存関係。
   最終行に REVIEW_RESULT_MARKER=REVIEW_COUNTS と REVIEW_COUNTS critical=<int> high=<int> を必ず出力してください"
rm -f /tmp/dig_plan_review_$$.md
```

- `critical=0` かつ `high=0` なら通過
- それ以外は修正して再レビュー
- 3 回超過または `REVIEW_COUNTS` パース不能なら停止

### Phase 6: 実装

Phase 6 開始時に初めて Tasks を materialize する。

#### 6a. parent + subtasks を一括登録

Phase 5 通過後、実装前に必ず以下を作る。

- 親タスク: `[Phase 6] <topic>`
- サブタスク: `[Task 1] <summary>`, `[Task 2] <summary>` ...

ルール:

- `small` でも最低 1 件の `[Task 1]` を作る
- 番号は dig セッションごとに 1 から振り直す
- サブタスク description は What / Where / How / Why / Verify を含める
- 実装開始前に `TaskList` で登録結果を確認する

#### 6b. 実行モード選択

`agent-parallel を常に第一候補` とする。

1. `[Task N]` ごとの write_scope を見て独立性を確認
2. 可能なら `Agent` を並列起動する
3. 重複があれば write_scope を再分割して並列続行を試みる
4. 再分割不能な部分だけ tool-parallel に落とす

single-task でも、原則は orchestrator 本体ではなく Agent に実装させる。

#### 6c. agent-parallel 実行

各 Agent の prompt には以下を含める。

- 対応する `[Task N]` の subject / description
- write_scope
- REVIEW_GATE_SUBTASK の実行方法
- コミット契約

各 Agent は worktree で独立実装し、サブタスク単位でレビューと commit まで完了させる。

#### 6d. tool-parallel / sequential 実行

Agent に乗らない部分だけ、本体が順次実行する。

- 読み取り系は並列化してよい
- 変更系はサブタスク単位で区切る
- 各サブタスクの commit 前に REVIEW_GATE_SUBTASK を必ず通す

### Phase 7: 実装レビューと検証

#### REVIEW_GATE_SUBTASK

各 `[Task N]` の完了後、コミット前にレビューする。

```bash
git diff --staged | dig_sanitize /dev/stdin /tmp/dig_subtask_review_$$.diff
codex exec -m gpt-5.3-codex-spark -c model_reasoning_effort="medium" \
  "以下の diff ファイルをレビューしてください: /tmp/dig_subtask_review_$$.diff。
   サブタスク: <subtask_subject>。
   観点: 実装の正当性、副作用、既存テストへの影響。
   最終行に REVIEW_RESULT_MARKER=REVIEW_COUNTS と REVIEW_COUNTS critical=<int> high=<int> を出力"
rm -f /tmp/dig_subtask_review_$$.diff
```

- 変更 5 行未満またはドキュメントのみはスキップ可
- レビュー通過後にだけ `TaskUpdate(status="completed")` する

#### REVIEW_GATE_INTEGRATION

複数サブタスクがある場合、全体統合レビューを行う。

```bash
git diff $PHASE6_START..HEAD | dig_sanitize /dev/stdin /tmp/dig_integration_review_$$.diff
codex exec -m gpt-5.3-codex-spark -c model_reasoning_effort="medium" \
  "以下の diff ファイルをレビューしてください: /tmp/dig_integration_review_$$.diff。
   観点: 統合整合性、インターフェース契約、副作用。
   最終行に REVIEW_RESULT_MARKER=REVIEW_COUNTS と REVIEW_COUNTS critical=<int> high=<int> を出力"
rm -f /tmp/dig_integration_review_$$.diff
```

- 0 件または 1 件のサブタスクならスキップ可
- agent-parallel では worktree 差分を結合した diff を対象にする

### Phase 8: コミットとプッシュ

commit が必要な場合は常に以下の順で進める。

1. `git add`
2. コミット前レビュー
3. `git commit`
4. `git push`

親タスク完了条件:

1. 全 `[Task N]` が completed
2. 必要なレビューゲートを全て通過
3. `git commit` が成功
4. 上記を満たした後に `[Phase 6]` 親タスクを `completed`

`git push` は推奨だが、親タスク完了の必須条件には含めない。

## 停止コード

| コード | 条件 |
|--------|------|
| `DIG_CLAUDE_USER_CANCELLED` | ユーザーが Phase 2 でキャンセル |
| `DIG_CLAUDE_QUESTION_FAILED` | AskUserQuestion が拒否・空返答・タイムアウト |
| `DIG_CLAUDE_REVIEW_BLOCKED` | plan review が critical/high 未解消 |
| `DIG_CLAUDE_DECOMP_REVIEW_BLOCKED` | 分解レビューが critical/high 未解消 |
| `DIG_CLAUDE_SUBTASK_REVIEW_BLOCKED` | サブタスクレビューが critical/high 未解消 |
| `DIG_CLAUDE_INTEGRATION_REVIEW_BLOCKED` | 統合レビューが critical/high 未解消 |
| `DIG_CLAUDE_CODEX_UNAVAILABLE` | `codex exec` が使えない |

停止時は必ず以下を出す。

- `ERROR_CODE: <CODE>`
- `RERUN_COMMAND: /dig <topic>`
- `DIAGNOSTIC_COMMAND: <one-line command>`
- `STOP_OUTPUT_FIELDS: ERROR_CODE,RERUN_COMMAND,DIAGNOSTIC_COMMAND`

## cleanup

停止時の cleanup 手順:

1. `/tmp/dig_*` 一時ファイルを削除
2. Phase 6 Tasks 登録後なら、未完了の `[Task N]` を先に cancel
3. その後 `[Phase 6]` 親タスクを cancel
4. agent-parallel 中なら未マージ worktree を削除

Phase 1-5 で停止した場合は、TaskCreate 前なので task cleanup は不要。

## 重要

- dig の正規表現は 8 フェーズを使う
- Phase 1-5 では TaskCreate しない
- Phase 5 通過後 に `[Phase 6]` + `[Task 1]` 以降を一括登録する
- 実装は Agent を優先し、orchestrator と implementer を分離する
- レビューは全て `codex exec` で行い、`REVIEW_COUNTS` を必須にする
- hook により、Phase 6 task materialization 前の実装開始は block される
