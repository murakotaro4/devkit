---
name: "agent-orch-openai"
description: "agent-orch-core 用 OpenAI/Codex CLI アダプタ。能力プロファイルをCodexモデルへ解決する。"
argument-hint: "[task-or-goal]"
allowed-tools: ["Read", "Write", "Edit", "Grep", "Glob", "Bash"]
---

# /agent-orch-openai - OpenAI Adapter

`agent-orch-core` の契約を OpenAI Codex CLI にマッピングする。

## モデル解決（既定）

| profile | model | effort |
|---|---|---|
| `max_reasoning` | `gpt-5.3-codex` | `xhigh` |
| `high_fast` | `gpt-5.3-codex-spark` | `xhigh` |
| `fast_first` | `gpt-5.3-codex-spark` | `xhigh` |

fallback:
1. `gpt-5.3-codex-spark` が不可 -> `gpt-5.3-codex`
2. `xhigh` 非対応 -> `high`

## コマンドテンプレート

### Research（read-only + web search）
```bash
codex exec -C "$REPO" \
  -m "$MODEL" \
  -c model_reasoning_effort="$EFFORT" \
  --sandbox read-only \
  --search \
  "$PROMPT"
```

### Implementation（workspace-write）
```bash
codex exec -C "$REPO" \
  -m "$MODEL" \
  -c model_reasoning_effort="$EFFORT" \
  --sandbox workspace-write \
  "$PROMPT"
```

### Review（read-only）
```bash
codex exec -C "$REPO" \
  -m "$MODEL" \
  -c model_reasoning_effort="$EFFORT" \
  --sandbox read-only \
  "$PROMPT"
```

## 既知制約

- `codex help` ではモデル一覧が表示されない。実行検証結果を正とする。
- アカウント契約により一部モデルが拒否される場合がある。

## 参照ファイル

- `profiles.yaml` に model/effort マッピングを定義。
- 更新時はまず `profiles.yaml` を修正し、SKILL本文との整合を確認する。
