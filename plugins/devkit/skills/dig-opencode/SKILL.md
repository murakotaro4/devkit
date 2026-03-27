---
name: "dig-opencode"
description: "dig の OpenCode adapter。Plan agent + question を優先し、不可時はメッセージ質問や Build agent 切替で dig-core 契約を実行する。"
argument-hint: "[topic]"
allowed-tools: ["Read", "Grep", "Glob", "Bash"]
---

# /dig-opencode - OpenCode Adapter

> **Role**: dig-opencode = dig-core 契約を OpenCode（Plan agent / Build agent / question）にマッピングする最小構成 adapter

## Plan Mode ↔ Phase マッピング

| モード | 対応フェーズ | 備考 |
|--------|------------|------|
| Plan agent | Phase 1-4 | 計画専用。Phase 5-7 は dig-claude に委譲 |

## Phase 1 契約（OpenCode 固有）

- `question_tool_available=true`: question ツールで質問。ラウンド数に上限なし
- `question_tool_available=false`: MESSAGE_QUESTION_FLOW で質問。ラウンド数に上限なし
- 完了チェックリスト（全項目が確定するまで Phase 2 に進まない）:
  - [ ] 目的 / [ ] 成功条件 / [ ] 制約 / [ ] 非対象 / [ ] 承認（ユーザー同意）
- 完了確認: 利用可能な質問手段で「要件は十分固まりましたか？」を必ず確認する

## codex exec パターン

| パターン | コマンド形式 | 用途 | 条件 |
|---------|------------|------|------|
| plan review | `codex exec -m <model> "<review prompt>"` | 計画書のレビュー | bash_available_in_plan=true |
| consultation | `codex exec -m <model> "<advisory prompt>"` | 調査・相談 | bash_available_in_plan=true |

- bash_available_in_plan=false の場合は Build agent で代替

## エージェントマッピング

| dig-core ロール | OpenCode での実現 | 備考 |
|----------------|-------------------|------|
| Orchestrator | dig-opencode 本体 | Plan agent 内でフェーズ進行管理 |
| Plan agent | 本体が直接実行 | Plan agent モードで計画を作成 |
| Eval agent | codex exec（bash 経由）or Build agent | runtime 能力検出に依存 |
| Implementer | dig-claude に委譲 | Phase 5-7 は非対応 |

## 入力パラメータ

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
