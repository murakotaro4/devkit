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

dig-core 契約の 7 フェーズに従う。旧 5 ステップは補助理解のみ。

Plan Mode 中でも codex exec は読み取り専用として実行可能。Phase 4 はExitPlanMode 前に完了すること。

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
REVIEW_PRIMARY_CMD \
  "以下のプランファイルをレビューしてください: <plan_file_path>。
   観点: 実現可能性、既存構造との整合性、抜け漏れ、リスク、依存関係。
   最終行に REVIEW_RESULT_MARKER=REVIEW_COUNTS と REVIEW_COUNTS critical=<int> high=<int> を必ず出力してください"
```

- `critical=0` かつ `high=0` なら通過
- それ以外は修正して再レビュー
- PRIMARY がタイムアウト/rate limit/エラーなら 5 秒待機後 REVIEW_FALLBACK_CMD で 1 回リトライ
- 両方失敗なら `DIG_CLAUDE_PLAN_REVIEW_UNAVAILABLE` で停止
- 3 回目の失敗（`plan_review_attempts >= 3`）または `REVIEW_COUNTS` パース不能なら `DIG_CLAUDE_REVIEW_BLOCKED` で停止

### Phase 5: 実装

**ExitPlanMode 後の必須手順**: decomposition → TaskCreate で `[Task 1]`+ を一括登録 → TaskList で確認 → 実装開始。hook が未登録の実装を block する。

実行モード: `agent-parallel を常に第一候補` とする。single-task でも Agent に実装させる。
- Agent prompt には dig-core のタスク管理契約に基づくスコープ・sizing・レビュー方針を含める
- 各 Agent は worktree で独立実装し、サブタスク単位で commit まで完了させる
- ファイル重複時は write_scope を再分割。再分割不能な部分だけ tool-parallel

PostToolUse hook が TaskList 呼び出し時に `format_task_progress.py` で `[Task N]` ラベル付き可読出力を注入する。

> **MCP 並列化の観測結果（2026-03 検証）**: 同一メッセージ内の MCP 呼び出しは逐次処理される。Agent 経由なら真の並列実行が可能（10並列確認済み）。codex MCP サーバーは 1 インスタンスで十分。

### Phase 6: 実装レビューと検証

dig-core のレビューゲート契約に従う。Phase 6 では Path A（diff review）を使用。

#### REVIEW_GATE_SUBTASK

各 `[Task N]` の完了後、コミット前にレビュー。Phase 4 とはコマンド形式が異なる:
- PRIMARY: `codex exec review --uncommitted -m gpt-5.3-codex-spark`
- FALLBACK: `codex exec review --uncommitted -m gpt-5.4`

- small: 変更5行未満 or ドキュメントのみはスキップ可
- medium: + 統合影響、インターフェース契約、パフォーマンス影響を観点に追加
- large: + セキュリティ影響、ロールバック可能性を追加
- agent-parallel: 各 implementer が独立して実行。停止時は Coordinator が全体停止

#### REVIEW_GATE_INTEGRATION

複数サブタスクがある場合、`git diff $PHASE5_START..HEAD` で全体統合レビュー。
- 0-1 件のサブタスクならスキップ可
- sizing に応じて追加観点を付加（SUBTASK と同様）

### Phase 7: コミットとプッシュ

`git add` → コミット前レビュー → `git commit` → `git push`（push は完了の必須条件に含めない）。
全 `[Task N]` が completed + レビューゲート通過 + commit 成功で完了。

### セッション振り返り（Phase 7 完了後）

dig-core 契約の「セッション振り返り」に従い `devkit:improve-skill` を実行。

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
| Explorer | Agent ツール（`subagent_type: "Explore"`） | Phase 2 コードベース探索。3+本並列 |
| Researcher | codex-search / deep-research スキル | Phase 2 外部調査。3+本並列 |
| Plan agent | Agent ツール（plan-only prompt） | Phase 3 計画作成 |
| Eval agent | codex exec（レビュー専用） | Phase 4/6 レビュー |
| Implementer | Agent ツール（`isolation: "worktree"`） | Phase 5 実装 |

## 停止コード

| コード | 条件 |
|--------|------|
| `DIG_CLAUDE_USER_CANCELLED` | Phase 1 でキャンセル |
| `DIG_CLAUDE_QUESTION_FAILED` | AskUserQuestion 失敗 |
| `DIG_CLAUDE_REVIEW_BLOCKED` | レビューで critical/high 未解消 |
| `DIG_CLAUDE_CODEX_UNAVAILABLE` | codex exec 利用不能 |
| `DIG_CLAUDE_PLAN_REVIEW_UNAVAILABLE` | Phase 4 PRIMARY/FALLBACK 両方利用不能 |
| `DIG_CLAUDE_SUBTASK_REVIEW_UNAVAILABLE` | Phase 6 SUBTASK レビュー利用不能 |
| `DIG_CLAUDE_INTEGRATION_REVIEW_UNAVAILABLE` | Phase 6 INTEGRATION レビュー利用不能 |

停止時出力は dig-core の停止時出力契約に従う。`RERUN_COMMAND: /dig <topic>`

## cleanup

停止時: `/tmp/dig_*` 一時ファイル削除、未完了タスクを cancel、未マージ worktree を削除。

## 重要

7フェーズ必須。Phase 5 前に TaskCreate 必須。実装は Agent 優先。レビューは codex exec 必須。
