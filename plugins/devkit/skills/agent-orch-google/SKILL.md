---
name: "agent-orch-google"
description: "agent-orch-core 用 Google/Gemini CLI アダプタ。能力プロファイルをGeminiモデルへ解決する。"
argument-hint: "[task-or-goal]"
allowed-tools: ["Read", "Write", "Edit", "Grep", "Glob", "Bash"]
---

# /agent-orch-google - Google Adapter

`agent-orch-core` の契約を Gemini CLI にマッピングする。

## モデル解決（既定）

| profile | model | effort相当 |
|---|---|---|
| `max_reasoning` | `gemini-2.5-pro` | prompt内で高推論を指定 |
| `high_fast` | `gemini-2.5-flash` | prompt内で高推論を指定 |
| `fast_first` | `gemini-2.5-flash` | prompt内で標準推論を指定 |

fallback:
1. `gemini-2.5-flash` 不可 -> `gemini-2.5-pro`
2. 失敗時は他providerへフォールバック（core側ルール）

## コマンドテンプレート

### Research
```bash
gemini \
  --model "$MODEL" \
  --sandbox \
  --prompt "$PROMPT"
```

### Implementation
```bash
gemini \
  --model "$MODEL" \
  --sandbox \
  --checkpointing \
  --prompt "$PROMPT"
```

### Review
```bash
gemini \
  --model "$MODEL" \
  --sandbox \
  --prompt "$PROMPT"
```

## 既知制約

- Gemini CLI は effort オプションを持たないため、推論強度は prompt で明示する。
- 非対話実行時の挙動は CLIバージョン差異があるため `gemini --help` を確認する。

## 参照ファイル

- `profiles.yaml` に model/mode マッピングを定義。
