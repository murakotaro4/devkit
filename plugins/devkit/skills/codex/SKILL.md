---
name: "codex"
description: "互換ラッパー。agent-orch-core + agent-orch-openai を使って従来の /codex 入口を維持する。"
argument-hint: "[goal]"
allowed-tools: ["Read", "Write", "Edit", "Grep", "Glob", "Bash"]
---

# /codex - 互換ラッパー（OpenAI優先）

このスキルは後方互換のために残している。
新規運用は `agent-orch-core` を推奨。

## 役割
- `/codex` 呼び出しを `agent-orch-core` フローに接続する。
- provider は `openai` を優先し、必要時のみフォールバックする。
- 調査 -> 実装 -> レビューのE2Eを維持する。

## 実行方針
1. Runtime Profile は core 契約を使用する。
2. `primary_provider` は `runtime_detected` を尊重する。
3. provider が OpenAI の場合は `agent-orch-openai` の model mapping を使用する。
4. 品質未達時は core の動的昇格規則で再試行する。
5. レビューは同系3並列 + 任意クロスレビュー1本を適用する。

## 推奨移行
- マルチプロバイダで運用する場合:
  - `/agent-orch-core "<goal>"`
- providerを明示したい場合:
  - `/agent-orch-openai "<goal>"`
  - `/agent-orch-anthropic "<goal>"`
  - `/agent-orch-google "<goal>"`

## 互換保証範囲
- `codex-search` は変更しない（従来どおり利用可能）。
- `/codex` は入口名を維持するが、内部仕様は共通基盤へ移行済み。
