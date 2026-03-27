---
name: "dig-claude"
description: "dig の Claude adapter。AskUserQuestionTool と Codex レビューで dig-core 契約を実行する。"
argument-hint: "[topic]"
allowed-tools: ["Read", "Edit", "Write", "Grep", "Glob", "Bash"]
---

# /dig-claude - Claude Adapter

> **Role**: dig-claude = dig-core 契約を Claude Code ツール（AskUserQuestionTool / Agent / TaskCreate / codex exec）にマッピングする adapter

## Plan Mode ↔ Phase マッピング

| モード | 対応フェーズ | 備考 |
|--------|------------|------|
| Plan Mode | Phase 1-4 | Phase 4 完了まで Plan Mode 内で実行可能 |
| Agent Mode | Phase 5-7 | ExitPlanMode 後に実行 |

> `AskUserQuestionTool`・`Agent`・`TaskCreate`・`TaskUpdate`・`TaskList` は Claude Code のシステムツールであり、frontmatter の `allowed-tools` には書かない。

## 7フェーズ対応

Claude runtime での dig は dig-core 契約の 7 フェーズを使う。

1. Phase 1: 要件ヒアリング
2. Phase 2: 調査
3. Phase 3: 計画作成
4. Phase 4: 計画レビュー
5. Phase 5: 実装
6. Phase 6: 実装レビューと検証
7. Phase 7: コミットとプッシュ

旧 5 ステップは補助理解にとどめる。実際の説明・plan・hook state は常に `Phase 1` から `Phase 7` を使う。

## Plan Mode 共存

Plan Mode が既に有効でも dig は継続できるが、dig 自身が EnterPlanMode / ExitPlanMode を操作しない。

- Phase 1-3: AskUserQuestionTool と plan ファイルで進める
- Phase 4: Plan Mode 内で `codex exec` を使い計画レビューを完了する（下記参照）
- Phase 5-7: ユーザーが通常実行へ進めた後に扱う

### Plan Mode での Phase 4 実行

Plan Mode 内でも `codex exec` は読み取り専用コマンドとして実行可能。Phase 3 でプランファイルを書き終えた後、**ExitPlanMode を呼ぶ前に** Phase 4 計画レビューを完了すること。

手順:
1. Phase 3 のプランファイル完成後、通常の Phase 4 手順（本ファイルの Phase 4 セクション）に従い `codex exec` でレビューを実行する
2. `critical=0` かつ `high=0` になるまで修正→再レビューを繰り返す
3. Phase 4 通過後に ExitPlanMode を呼ぶ

ExitPlanMode 前に Phase 4 が完了していない場合、PreToolUse hook が警告する。

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

Claude hook は `/dig` セッションを検出し、Phase 4 通過後の変更系ツールを監視する。

- `UserPromptSubmit`: dig セッション開始を記録
- `PostToolUse(Bash)`: plan review 成功を記録
- `PreToolUse`: Phase 4 は通過したが Phase 5 Tasks 未登録なら実装を block
- `Stop`: dig state を cleanup

つまり **Phase 4 通過後** に `[Task 1]` 以降のタスクが無いまま `Edit` / `Write` / `Agent` / 変更系 `Bash` に入ることは許可しない。

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

### Phase 1: 要件ヒアリング

**Phase 1 をスキップしてはならない**。最低 4 問を 1 ラウンドとして必ず実行する。

- 最低 1 ラウンド必須。4 問を AskUserQuestionTool で同時に質問する
- 4 問のカバー範囲: (a) 成功基準, (b) 制約・限界, (c) 対象外, (d) 優先度・トレードオフ
- 選択肢には description を付ける。`multiSelect: true` を活用してユーザーの回答負荷を下げる
- ラウンド数に上限なし。完了チェックリストが全て埋まるまで深堀りを続ける
- AskUserQuestion が失敗したら `DIG_CLAUDE_QUESTION_FAILED` で停止する
- 完了チェックリスト（全項目が確定するまで Phase 2 に進まない）:
  - [ ] 目的（何を達成するか）
  - [ ] 成功条件（何をもって完了とするか）
  - [ ] 制約（技術的制約、時間制約、互換性要件等）
  - [ ] 非対象（今回やらないこと）
  - [ ] 承認（ユーザーが上記に同意）
- 完了確認: AskUserQuestionTool で「要件は十分固まりましたか？」を必ず確認する。ユーザーが同意するまで Phase 2 に進まない
- Phase 1 完了後に `requirements_confirmed` トークンが記録される（PostToolUse hook による自動設定）

質問は「非自明」「選択肢付き」「次の判断に効く」ものに限定する。

### Phase 2: 調査

コードベース調査を織り交ぜて、質問の文脈を具体化する。

- `Agent` を 1-3 本まで並列で使ってよい
- 調査対象は既存実装、関連コンポーネント、テストパターンを優先
- `.env`, `*.pem`, `*.key`, `credentials.json`, `secrets.*` は読まない
- `**/*` のような広域検索前には範囲と目的をユーザーに伝える

### Phase 3: 計画作成

plan ファイルを作り、承認前の分解結果をテキストでまとめる。

plan には最低限以下を入れる。

- topic の要約
- write_scope
- Phase 5 で実装したいサブタスク案
- 各サブタスクの REVIEW_GATE_SUBTASK 方針（sizing に基づき「必須」or「実装結果次第でスキップ可」。最終判定は Phase 6 で実 diff に基づき行う）
- REVIEW_GATE_INTEGRATION 方針（サブタスク数に基づき「必須」or「スキップ可」）

`devkit:decomposition` を呼ぶ場合も **plan-only** で使う。Phase 3 では TaskCreate しない。

計画の末尾で sizing / team_shape / role_assignment を確定する:

- Coordinator が sizing policy で `small` / `medium` / `large` を決める
- サイズから team_shape を決定: `small` → `micro_team`、`medium` → `standard_team`、`large` → `expanded_team`
- `team_shape` と `role_assignment` を確定する

### Phase 4: 計画レビュー

分解済み plan を Codex でレビューする。

> **レビュー経路**: Phase 4 では Path B（計画書レビュー）を使用する。サニタイズ済み plan ファイルを codex exec に渡す方式。`review --uncommitted` は Phase 6 用であり、Phase 4 では使用しない。

レビュー実行コマンド:
- REVIEW_PRIMARY_CMD: `codex exec -m gpt-5.3-codex-spark -c model_reasoning_effort="medium"`
- REVIEW_FALLBACK_CMD: `codex exec -m gpt-5.4 -c model_reasoning_effort="medium"`
- REVIEW_TIMEOUT_SECONDS: 180
- REVIEW_BACKOFF_SECONDS: 5
- REVIEW_RETRY_POLICY: no_same_model_retry_one_fallback_hop

```bash
dig_sanitize <plan_file_path> /tmp/dig_plan_review_$$.md
REVIEW_PRIMARY_CMD \
  "以下のプランファイルをレビューしてください: /tmp/dig_plan_review_$$.md。
   観点: 実現可能性、既存構造との整合性、抜け漏れ、リスク、依存関係。
   最終行に REVIEW_RESULT_MARKER=REVIEW_COUNTS と REVIEW_COUNTS critical=<int> high=<int> を必ず出力してください"
rm -f /tmp/dig_plan_review_$$.md
```

- `critical=0` かつ `high=0` なら通過
- それ以外は修正して再レビュー
- PRIMARY がタイムアウト/rate limit/エラーなら 5 秒待機後 REVIEW_FALLBACK_CMD で 1 回リトライ
- 両方失敗なら `DIG_CLAUDE_PLAN_REVIEW_UNAVAILABLE` で停止
- 3 回目の失敗（`plan_review_attempts >= 3`）または `REVIEW_COUNTS` パース不能なら `DIG_CLAUDE_REVIEW_BLOCKED` で停止

### Phase 5: 実装

**ExitPlanMode 後（Plan Mode からの復帰後）の必須手順**:

1. `/devkit:decomposition` を plan-only で実行し、サブタスクを細分化する（What/Where/How/Why/Verify を含める）
2. `[Task 1]`, `[Task 2]`... を TaskCreate で一括登録する（親タスク不要）
3. TaskList で登録結果を確認してから実装に入る

この 3 ステップを省略してはならない。hook が Phase 5 Tasks 未登録の実装を block する。

Phase 5 開始時に初めて Tasks を materialize する。

#### 5a. タスクを一括登録

Phase 4 通過後、実装前に必ず以下を作る。

- タスク: `[Task 1] <summary>`, `[Task 2] <summary>` ...

ルール:

- `small` でも最低 1 件の `[Task 1]` を作る
- 番号は dig セッションごとに 1 から振り直す
- タスク description は What / Where / How / Why / Verify を含める
- 実装開始前に `TaskList` で登録結果を確認する

decomposition 粒度指針:

- 各タスクは 5-10 分の単一責務に分解する
- 並列実行可能なタスク同士は `write_scope` を分離する
- 依存関係がある場合は `addBlockedBy` で明示する

#### 5a-1. タスク進捗の可読表示

TaskCreate はシステム内部 ID（例: `#38`）を割り当てる。`TaskList` はこの内部 ID で依存を表示するが、ユーザーには不透明である。

PostToolUse hook が TaskList 呼び出し時にフォーマットスクリプトを自動実行し、`additionalContext` 経由で `[Task N]` ラベル付きの可読出力を注入する。手動で実行する場合:

```bash
python3 scripts/workflow/format_task_progress.py "$DIG_SESSION_ID"
```

**ルール:**
- `TaskList` の raw 出力を直接ユーザーに見せない
- 進捗報告時は必ずフォーマット済み出力を使う
- マッピングに存在しない ID は `#数字` のまま表示する（部分失敗時のフォールバック）

#### 5b. 実行モード選択

`agent-parallel を常に第一候補` とする。

1. `[Task N]` ごとの write_scope を見て独立性を確認
2. 可能なら `Agent` を並列起動する
3. 重複があれば write_scope を再分割して並列続行を試みる
4. 再分割不能な部分だけ tool-parallel に落とす

single-task でも、原則は orchestrator 本体ではなく Agent に実装させる。

#### 5c. agent-parallel 実行

各 Agent の prompt には以下を含める。

- 対応する `[Task N]` の subject / description
- write_scope
- sizing（small/medium/large）と REVIEW_GATE_SUBTASK のスキップ可否
- REVIEW_GATE_SUBTASK の実行方法
- コミット契約

各 Agent は worktree で独立実装し、サブタスク単位でレビューと commit まで完了させる。

> **MCP 並列化の観測結果（2026-03 検証、Claude Code 現行挙動）**: Claude Code の同一メッセージ内で複数の MCP ツール呼び出しを行った場合、実際の送信は逐次処理される。サブエージェント（Agent ツール）経由なら各プロセスが独立して MCP リクエストを発行するため、同一 codex サーバーに対しても真の並列実行が可能（10並列で動作確認済み）。codex MCP サーバーは 1 インスタンスで十分。この挙動は Claude Code / MCP 側の変更で変わりうるため、必要なら再検証する。なお、この制約は MCP 経由の呼び出しに適用され、`codex exec` CLI を Bash で直接実行する場合とは異なる経路である。

#### 5d. tool-parallel / sequential 実行

Agent に乗らない部分だけ、本体が順次実行する。

- 読み取り系は並列化してよい
- 変更系はサブタスク単位で区切る
- 各サブタスクの commit 前に REVIEW_GATE_SUBTASK を通す（スキップ条件は Phase 6 REVIEW_GATE_SUBTASK セクションに従う）

### Phase 6: 実装レビューと検証

#### REVIEW_GATE_SUBTASK

各 `[Task N]` の完了後、コミット前にレビューする。

```bash
git diff --staged | dig_sanitize /dev/stdin /tmp/dig_subtask_review_$$.diff

# small の場合:
codex exec -m gpt-5.3-codex-spark -c model_reasoning_effort="medium" \
  "以下の diff ファイルをレビューしてください: /tmp/dig_subtask_review_$$.diff。
   サブタスク: <subtask_subject>。
   観点: 実装の正当性、副作用、既存テストへの影響。
   最終行に REVIEW_RESULT_MARKER=REVIEW_COUNTS と REVIEW_COUNTS critical=<int> high=<int> を出力"

# medium の場合:
codex exec -m gpt-5.3-codex-spark -c model_reasoning_effort="medium" \
  "以下の diff ファイルをレビューしてください: /tmp/dig_subtask_review_$$.diff。
   サブタスク: <subtask_subject>。
   観点: 実装の正当性、副作用、既存テストへの影響、統合影響、インターフェース契約、パフォーマンス影響。
   最終行に REVIEW_RESULT_MARKER=REVIEW_COUNTS と REVIEW_COUNTS critical=<int> high=<int> を出力"

# large の場合:
codex exec -m gpt-5.3-codex-spark -c model_reasoning_effort="medium" \
  "以下の diff ファイルをレビューしてください: /tmp/dig_subtask_review_$$.diff。
   サブタスク: <subtask_subject>。
   観点: 実装の正当性、副作用、既存テストへの影響、統合影響、インターフェース契約、パフォーマンス影響、セキュリティ影響、ロールバック可能性。
   最終行に REVIEW_RESULT_MARKER=REVIEW_COUNTS と REVIEW_COUNTS critical=<int> high=<int> を出力"

rm -f /tmp/dig_subtask_review_$$.diff
```

- small: 変更 5 行未満またはドキュメントのみはスキップ可（REVIEW_GATE_PLAN が独立レビューを担保済み）
- medium/large: スキップ不可。全タスクで REVIEW_GATE_SUBTASK を実行する
- medium: レビュー prompt に「統合影響・インターフェース契約・パフォーマンス影響」を追加観点として含める
- large: 上記に加え「セキュリティ影響・ロールバック可能性」も観点に含める
- PRIMARY がタイムアウト/rate limit/エラーなら 5 秒待機後 REVIEW_FALLBACK_CMD で 1 回リトライ
- 両方失敗なら `DIG_CLAUDE_SUBTASK_REVIEW_UNAVAILABLE` で停止
- レビュー通過後にだけ `TaskUpdate(status="completed")` する

#### REVIEW_GATE_SUBTASK の並列実行（運用ガイド）

agent-parallel モードで複数の `[Task N]` が各 worktree で独立して完了した場合、REVIEW_GATE_SUBTASK を並列実行できる。

実行主体: 各 implementer サブエージェントが自身の worktree 内で既存の REVIEW_GATE_SUBTASK 手順をそのまま実行する（`dig_sanitize` → PRIMARY/FALLBACK → `REVIEW_COUNTS` 判定 → 停止コード発行 → レビュー通過後に `git commit`）。Coordinator がまとめて diff を準備するのではない。

並列化されるのは「複数 implementer サブエージェントの同時起動」であり、各サブエージェント内の手順は逐次・既存契約通り。いずれかのサブエージェントが停止コードを返した場合、Coordinator は全体を停止する。

> **注意**: REVIEW_GATE_SUBTASK の並列実行は REVIEW_GATE_INTEGRATION を代替しない。全サブタスク通過後、Coordinator は worktree 差分を結合した diff で REVIEW_GATE_INTEGRATION を実行する。

#### REVIEW_GATE_INTEGRATION

複数サブタスクがある場合、全体統合レビューを行う。

```bash
git diff $PHASE5_START..HEAD | dig_sanitize /dev/stdin /tmp/dig_integration_review_$$.diff

# small の場合:
codex exec -m gpt-5.3-codex-spark -c model_reasoning_effort="medium" \
  "以下の diff ファイルをレビューしてください: /tmp/dig_integration_review_$$.diff。
   観点: 統合整合性、インターフェース契約、副作用。
   最終行に REVIEW_RESULT_MARKER=REVIEW_COUNTS と REVIEW_COUNTS critical=<int> high=<int> を出力"

# medium の場合:
codex exec -m gpt-5.3-codex-spark -c model_reasoning_effort="medium" \
  "以下の diff ファイルをレビューしてください: /tmp/dig_integration_review_$$.diff。
   観点: 統合整合性、統合影響、インターフェース契約、副作用、パフォーマンス影響。
   最終行に REVIEW_RESULT_MARKER=REVIEW_COUNTS と REVIEW_COUNTS critical=<int> high=<int> を出力"

# large の場合:
codex exec -m gpt-5.3-codex-spark -c model_reasoning_effort="medium" \
  "以下の diff ファイルをレビューしてください: /tmp/dig_integration_review_$$.diff。
   観点: 統合整合性、統合影響、インターフェース契約、副作用、パフォーマンス影響、セキュリティ影響、ロールバック可能性。
   最終行に REVIEW_RESULT_MARKER=REVIEW_COUNTS と REVIEW_COUNTS critical=<int> high=<int> を出力"

rm -f /tmp/dig_integration_review_$$.diff
```

- 0 件または 1 件のサブタスクならスキップ可
- medium: レビュー prompt に「統合影響・パフォーマンス影響」を追加観点として含める
- large: 上記に加え「セキュリティ影響・ロールバック可能性」も観点に含める
- PRIMARY がタイムアウト/rate limit/エラーなら 5 秒待機後 REVIEW_FALLBACK_CMD で 1 回リトライ
- 両方失敗なら `DIG_CLAUDE_INTEGRATION_REVIEW_UNAVAILABLE` で停止
- agent-parallel では worktree 差分を結合した diff を対象にする

### Phase 7: コミットとプッシュ

commit が必要な場合は常に以下の順で進める。

1. `git add`
2. コミット前レビュー
3. `git commit`
4. `git push`

完了条件:

1. 全 `[Task N]` が completed
2. 必要なレビューゲートを全て通過
3. `git commit` が成功

`git push` は推奨だが、完了の必須条件には含めない。

### セッション振り返り（Phase 7 完了後）

Phase 7 完了後に `devkit:improve-skill` を実行する。
dig-core 契約の「セッション振り返り」に従う。

## codex exec パターン

| パターン | コマンド形式 | 用途 | フェーズ |
|---------|------------|------|---------|
| diff review | `codex exec review --uncommitted` | 未コミット差分のレビュー | Phase 6（REVIEW_GATE_SUBTASK / INTEGRATION） |
| plan review | `codex exec -m <model> "<review prompt>"` + サニタイズ済みファイル | 計画書のレビュー | Phase 4（REVIEW_GATE_PLAN） |
| consultation | `codex exec -m <model> "<advisory prompt>"` | 調査・相談・アドバイス | Phase 2、任意 |
| file review | `codex exec -m <model> "<prompt>"` + サニタイズ済みファイル | ファイルベースのレビュー | Phase 4/6 |

- Phase 4: Path B（plan review）を使用。計画書ファイルをサニタイズして codex exec に渡す
- Phase 6: Path A（diff review）を使用。`review --uncommitted` はカスタムプロンプト併用不可
- Phase 2: consultation パターンで調査・技術相談に使用可能
- 迷った場合: consultation パターンで codex exec に相談してよい

## エージェントマッピング

dig-core のエージェントアーキテクチャを Claude Code ツールに写像:

| dig-core ロール | Claude Code での実現 | 備考 |
|----------------|---------------------|------|
| Orchestrator | dig 本体エージェント | フェーズ進行管理・委譲・統合のみ |
| Plan agent | Agent ツール（plan-only prompt） | Phase 3 計画作成を委譲 |
| Eval agent | codex exec（上記4パターン） | Phase 4/6 レビュー + Phase 2 調査 + 相談 |
| Implementer | Agent ツール（`isolation: "worktree"`） | Phase 5 実装 |

## 停止コード

| コード | 条件 |
|--------|------|
| `DIG_CLAUDE_USER_CANCELLED` | ユーザーが Phase 1 でキャンセル |
| `DIG_CLAUDE_QUESTION_FAILED` | AskUserQuestion が拒否・空返答・タイムアウト |
| `DIG_CLAUDE_REVIEW_BLOCKED` | plan review が critical/high 未解消 |
| `DIG_CLAUDE_DECOMP_REVIEW_BLOCKED` | 分解レビューが critical/high 未解消 |
| `DIG_CLAUDE_SUBTASK_REVIEW_BLOCKED` | サブタスクレビューが critical/high 未解消 |
| `DIG_CLAUDE_INTEGRATION_REVIEW_BLOCKED` | 統合レビューが critical/high 未解消 |
| `DIG_CLAUDE_CODEX_UNAVAILABLE` | `codex exec` が使えない |
| `DIG_CLAUDE_PLAN_REVIEW_UNAVAILABLE` | PRIMARY / FALLBACK 両方が利用不能 |
| `DIG_CLAUDE_SUBTASK_REVIEW_UNAVAILABLE` | サブタスクレビューで PRIMARY / FALLBACK 両方が利用不能 |
| `DIG_CLAUDE_INTEGRATION_REVIEW_UNAVAILABLE` | 統合レビューで PRIMARY / FALLBACK 両方が利用不能 |

停止時は必ず以下を出す。

- `ERROR_CODE: <CODE>`
- `RERUN_COMMAND: /dig <topic>`
- `DIAGNOSTIC_COMMAND: <one-line command>`
- `STOP_OUTPUT_FIELDS: ERROR_CODE,RERUN_COMMAND,DIAGNOSTIC_COMMAND`

## cleanup

停止時の cleanup 手順:

1. `/tmp/dig_*` 一時ファイルを削除
2. Phase 5 Tasks 登録後なら、未完了タスクを全て cancel
3. agent-parallel 中なら未マージ worktree を削除

Phase 1-4 で停止した場合は、TaskCreate 前なので task cleanup は不要。

## 重要

- dig の正規表現は 7 フェーズを使う
- Phase 1-4 では TaskCreate しない
- Phase 4 通過後 に `[Task 1]` 以降を一括登録する
- 実装は Agent を優先し、orchestrator と implementer を分離する
- レビューは全て `codex exec` で行い、`REVIEW_COUNTS` を必須にする
- hook により、Phase 5 task materialization 前の実装開始は block される
