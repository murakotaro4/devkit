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

## 状態遷移

- `INIT -> PLAN_CHECK`
- Plan Mode true: `PLAN_CHECK -> INTERVIEW -> PLAN_REVIEW -> DONE`
- Plan Mode false: `PLAN_CHECK -> STOP(DIG_CODEX_PLAN_REQUIRED)`

## 非Plan時の停止文

- `ERROR_CODE: DIG_CODEX_PLAN_REQUIRED`
- 再実行: Plan Mode で `/prompts:devkit-dig` を実行すること
- 診断: 現在モードが Plan か確認すること
