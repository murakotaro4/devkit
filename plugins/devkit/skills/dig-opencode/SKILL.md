---
name: "dig-opencode"
description: "dig の OpenCode adapter。Plan agent + question を優先し、不可時はメッセージ質問や Build agent 切替で dig-core 契約を実行する。"
argument-hint: "[topic]"
allowed-tools: ["Read", "Grep", "Glob", "Bash"]
---

# /dig-opencode - OpenCode Adapter

Inputs:
- `plan_agent_available`
- `question_tool_available`
- `bash_available_in_plan`
- `build_agent_available`

## 状態遷移

1. `INIT -> PLAN_ENV_CHECK`
2. `plan_agent_available=false` -> `STOP(DIG_OPENCODE_PLAN_AGENT_REQUIRED)`
3. `plan_agent_available=true` -> `PLAN_ENTRY`
4. `question_tool_available=true` -> `QUESTION_TOOL_FLOW`
5. `question_tool_available=false` -> `MESSAGE_QUESTION_FLOW`
6. レビュー到達時:
   - bash 可 -> `PLAN_REVIEW`
   - bash 不可 + build 可 -> `BUILD_REVIEW`
   - それ以外 -> `STOP(DIG_OPENCODE_BUILD_REQUIRED)`
7. Build 切替は 1 回再試行し、失敗時停止する。

## 停止コード

- `DIG_OPENCODE_PLAN_AGENT_REQUIRED`
- `DIG_OPENCODE_BUILD_REQUIRED`
