---
name: "dig-cursor"
description: "dig の Cursor adapter。AskQuestion / Plan Mode / codex review を使って dig-core 契約を実行する。"
argument-hint: "[topic]"
allowed-tools: ["ReadFile", "Edit", "Glob", "rg", "Shell", "AskQuestion", "TodoWrite", "CreatePlan"]
---

# /dig-cursor - Cursor Adapter

dig-core 契約を Cursor IDE 環境で実行する adapter。

## 7フェーズ対応

Cursor runtime での dig は、`workflow.md` と同じ 7 フェーズを使う。

1. Phase 1: 要件ヒアリング
2. Phase 2: 調査
3. Phase 3: 計画作成
4. Phase 4: 計画レビュー
5. Phase 5: 実装
6. Phase 6: 実装レビューと検証
7. Phase 7: コミットとプッシュ

## 実行契約

| 機能 | Cursor での実現手段 |
|------|---------------------|
| 質問 | `AskQuestion` |
| コード探索 | `rg` / `Glob` / `ReadFile` |
| plan 記載 | plan ファイル編集（`CreatePlan` を使った場合も最終的に plan ファイルへ反映） |
| 計画レビュー / 実装レビュー | `codex exec`（Shell 経由） |
| タスク管理 | `TodoWrite` |
| 実装 | Agent mode の編集ツール |

## Cursor 固有ルール

- Plan Mode が有効な間は編集・書き込みを行わない
- Phase 1 は `AskQuestion` で最低 1 ラウンド（原則 4 問）を実施する
- Phase 4 のレビューゲート通過前に実装へ進まない
- 既存の dig-claude フローを踏襲しつつ、Cursor のツール制約に合わせて同等の停止コードを使う

## Phase 4: 計画レビュー

レビュー実行コマンド:
- REVIEW_PRIMARY_CMD: `codex -a never exec review --uncommitted -m gpt-5.3-codex-spark -c model_reasoning_effort="medium"`
- REVIEW_FALLBACK_CMD: `codex -a never exec review --uncommitted -m gpt-5.4 -c model_reasoning_effort="medium"`
- REVIEW_TIMEOUT_SECONDS: 180
- REVIEW_BACKOFF_SECONDS: 5
- REVIEW_RETRY_POLICY: no_same_model_retry_one_fallback_hop

レビュー対象と期待出力:
- Phase 4 は plan ファイルを中心にレビューする（`CreatePlan` を使った場合は plan 内容をファイルへ反映してからレビューする）
- 未コミット差分がある場合はその差分も対象に含める
- 実行結果の最終行に `REVIEW_RESULT_MARKER=REVIEW_COUNTS REVIEW_COUNTS critical=<int> high=<int>` を必須で出力させる
- `REVIEW_COUNTS` が取れない場合は失敗扱いとして fallback または停止コードへ進む

判定:
- `critical=0` かつ `high=0` で通過
- それ以外は修正して再レビュー
- PRIMARY/FALLBACK が両方失敗した場合は `DIG_CURSOR_PLAN_REVIEW_UNAVAILABLE`
- `REVIEW_COUNTS` がパース不能、または 3 回失敗で `DIG_CURSOR_REVIEW_BLOCKED`

## Phase 6: 実装レビューと検証

- `dig-core` の `REVIEW_GATE_SUBTASK` / `REVIEW_GATE_INTEGRATION` 契約をそのまま適用する
- small ではスキップ条件を許容、medium/large では `REVIEW_GATE_SUBTASK` を必須とする
- レビュー不能時は停止コードを返す
- 停止時は `dig-core` の停止時出力契約（3行 + `STOP_OUTPUT_FIELDS`）を必ず満たす

## 停止コード

| コード | 条件 |
|--------|------|
| `DIG_CURSOR_USER_CANCELLED` | ユーザーが Phase 1 でキャンセル |
| `DIG_CURSOR_QUESTION_FAILED` | AskQuestion が失敗・空返答 |
| `DIG_CURSOR_REVIEW_BLOCKED` | plan review が critical/high 未解消 |
| `DIG_CURSOR_PLAN_REVIEW_UNAVAILABLE` | PRIMARY / FALLBACK 両方が利用不能 |
| `DIG_CURSOR_SUBTASK_REVIEW_BLOCKED` | サブタスクレビューが critical/high 未解消 |
| `DIG_CURSOR_SUBTASK_REVIEW_UNAVAILABLE` | サブタスクレビューで PRIMARY / FALLBACK 両方が利用不能 |
| `DIG_CURSOR_INTEGRATION_REVIEW_BLOCKED` | 統合レビューが critical/high 未解消 |
| `DIG_CURSOR_INTEGRATION_REVIEW_UNAVAILABLE` | 統合レビューで PRIMARY / FALLBACK 両方が利用不能 |
| `DIG_CURSOR_IMPLEMENTATION_BLOCKED` | Plan Mode 解除前、または Phase 4 未通過で実装要求 |

停止時は必ず以下を出す。

- `ERROR_CODE: <CODE>`
- `RERUN_COMMAND: /dig runtime=cursor <topic>`
- `DIAGNOSTIC_COMMAND: <one-line command>`
- `STOP_OUTPUT_FIELDS: ERROR_CODE,RERUN_COMMAND,DIAGNOSTIC_COMMAND`

## 重要

- `dig-core` の共通契約を優先し、runtime 固有差分だけをこの adapter に書く
- `/dig` 入口は維持し、`runtime=cursor` でこの adapter に分岐する
- 計画専用で終えず、Cursor runtime では Phase 5-7 まで実行可能とする
