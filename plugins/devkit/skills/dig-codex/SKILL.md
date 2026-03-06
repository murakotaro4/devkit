---
name: "dig-codex"
description: "dig の Codex adapter。Plan Mode 必須で request_user_input を使い dig-core 契約を実行する。"
argument-hint: "[topic]"
allowed-tools: ["Read", "Grep", "Glob", "Bash"]
---

# /dig-codex - Codex Adapter

## 実行契約

- Plan Mode 必須
- 質問: `request_user_input`
- レビュー実行コマンド:
  - `REVIEW_PRIMARY_CMD: codex -a never exec review --uncommitted -m gpt-5.3-codex-spark`
  - `REVIEW_FALLBACK_CMD: codex -a never exec review --uncommitted -m gpt-5.3-codex -c 'model_reasoning_effort="medium"'`
- タイムアウト/リトライ:
  - `REVIEW_TIMEOUT_SECONDS: 180`
  - `REVIEW_BACKOFF_SECONDS: 5`
  - `REVIEW_RETRY_POLICY: no_same_model_retry_one_fallback_hop`

## 状態遷移

- `INIT -> PLAN_CHECK`
- Plan Mode true: `PLAN_CHECK -> INTERVIEW -> REVIEW_PRIMARY -> REVIEW_FALLBACK? -> REVIEW_PARSE -> REVIEW_GATE -> DONE`
- Plan Mode false: `PLAN_CHECK -> STOP(DIG_CODEX_PLAN_REQUIRED)`
- `REVIEW_PRIMARY` が unavailable の場合は 5 秒待機後 `REVIEW_FALLBACK` を 1 回だけ実行
- `REVIEW_PRIMARY/REVIEW_FALLBACK` とも unavailable の場合は `STOP(DIG_CODEX_PLAN_REVIEW_UNAVAILABLE)`
- `REVIEW_PARSE` で `REVIEW_COUNTS` が読めない場合は `STOP(DIG_CODEX_PLAN_REVIEW_UNAVAILABLE)`
- `REVIEW_GATE` で `critical>0 || high>0` の場合は `STOP(DIG_CODEX_PLAN_REVIEW_BLOCKED)`

## unavailable 判定

- 以下は unavailable として扱う:
  - プロセス終了コードが非 0
  - rate limit (`429`)
  - transport 切断（websocket/http disconnected）
  - 認証エラー
  - タイムアウト（180 秒）

## 非Plan時の停止文

- `ERROR_CODE: DIG_CODEX_PLAN_REQUIRED`
- `RERUN_COMMAND: $dig <topic>`
- `DIAGNOSTIC_COMMAND: echo current_mode_is_plan`

## 計画レビュー停止コード

- `DIG_CODEX_PLAN_REVIEW_UNAVAILABLE`
- `DIG_CODEX_PLAN_REVIEW_BLOCKED`

## 停止文テンプレート

- レビュー不能時:
  - `ERROR_CODE: DIG_CODEX_PLAN_REVIEW_UNAVAILABLE`
  - `RERUN_COMMAND: codex -a never exec review --uncommitted -m gpt-5.3-codex-spark`
  - `DIAGNOSTIC_COMMAND: codex --version`
- レビューNG時:
  - `ERROR_CODE: DIG_CODEX_PLAN_REVIEW_BLOCKED`
  - `RERUN_COMMAND: codex -a never exec review --uncommitted -m gpt-5.3-codex-spark`
  - `DIAGNOSTIC_COMMAND: echo REVIEW_COUNTS critical=<n> high=<n>`
