---
name: "agent-orch-anthropic"
description: "agent-orch-core 用 Anthropic/Claude Code アダプタ。能力プロファイルをClaudeモデルへ解決する。"
argument-hint: "[task-or-goal]"
allowed-tools: ["Read", "Write", "Edit", "Grep", "Glob", "Bash"]
---

# /agent-orch-anthropic - Anthropic Adapter

`agent-orch-core` の契約を Claude Code CLI にマッピングする。

## モデル解決（既定）

| profile | model alias | effort |
|---|---|---|
| `max_reasoning` | `opus` | `high` |
| `high_fast` | `sonnet` | `high` |
| `fast_first` | `sonnet` | `medium` |

fallback:
1. `opus` 不可 -> `sonnet`
2. `high` 過負荷時 -> `medium`

## コマンドテンプレート

### Research
```bash
claude -p \
  --model "$MODEL" \
  --effort "$EFFORT" \
  --permission-mode default \
  "$PROMPT"
```

### Implementation
```bash
claude -p \
  --model "$MODEL" \
  --effort "$EFFORT" \
  --permission-mode acceptEdits \
  --add-dir "$REPO" \
  "$PROMPT"
```

### Review
```bash
claude -p \
  --model "$MODEL" \
  --effort "$EFFORT" \
  --permission-mode default \
  "$PROMPT"
```

## 既知制約

- CLIオプションはバージョンで差異が出るため、`claude --help` を優先確認する。
- 長時間処理は `--max-budget-usd` などの実行ガードを必要に応じて付与する。

## 参照ファイル

- `profiles.yaml` に model/effort マッピングを定義。
