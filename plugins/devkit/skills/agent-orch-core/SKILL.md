---
name: "agent-orch-core"
description: "マルチCLI対応の共通オーケストレーション基盤。調査→実装→レビューを能力プロファイルで統一運用する。"
argument-hint: "[goal]"
allowed-tools: ["Read", "Write", "Edit", "Grep", "Glob", "Bash"]
---

# /agent-orch-core - 共通オーケストレーション基盤

ベンダー固有のモデル名やCLI差分を隠蔽し、以下を共通運用する:
- 調査 -> 実装 -> レビュー
- 粒度制御（S/M/L）
- 品質ファースト動的昇格
- 品質ゲート停止

## 使い方

```text
/agent-orch-core "goal"
```

例:
- `/agent-orch-core "既存APIを壊さずに認証機能を追加"`
- `/agent-orch-core "このバグを修正して回帰テストまで完了"`

---

## Runtime Profile（固定契約）

```json
{
  "orchestrator_profile": "max_reasoning",
  "worker_profile": "fast_first",
  "reviewer_profile": "high_fast",
  "primary_provider": "runtime_detected",
  "provider_fallback_order": [
    "same_provider_alternatives",
    "other_providers"
  ],
  "max_loops": {
    "research": 3,
    "implementation": 3,
    "review": 3
  }
}
```

## Provider 解決

1. `primary_provider` が明示されていればそれを使用。
2. 明示がなければ `runtime_detected` を使用。
3. アダプタ選択:
   - `openai` -> `agent-orch-openai`
   - `anthropic` -> `agent-orch-anthropic`
   - `google` -> `agent-orch-google`
4. 失敗時は同一provider代替 -> 他providerへフォールバック。

## Task Pack 契約（固定）

```json
{
  "task_id": "string",
  "phase": "research|implement|review|fix",
  "objective": "string",
  "files": ["string"],
  "granularity": "S|M|L",
  "required_profile": "max_reasoning|high_fast|fast_first",
  "provider_override": "optional string",
  "dependencies": ["task_id"],
  "done_definition": ["string"],
  "test_commands": ["string"]
}
```

## 粒度制御（S/M/L）

- `S`: 1-2ファイル、局所変更、低依存
- `M`: 3-5ファイル、仕様変更あり
- `L`: 6+ファイル、高依存

ルール:
- `L` は直接実装しない。`M` 以下に再分割する。
- 独立タスクは並列、依存タスクは直列で実行。

## 標準フロー

### Phase 1: Research Loop
- 子タスク3枠（仕様/制約/写像）を実行
- Parentで `sufficient|insufficient` 判定
- 不足時は再調査（最大3ラウンド）
- 上限到達時は `max_reasoning` で争点深掘り

### Phase 2: Implementation Loop
- Parentが `implementation_task_pack` を生成
- `fast_first` で実装
- DoD未達/テスト失敗は failed task のみ再実行（最大3ループ）

### Phase 3: Review/Fix Loop
- 同一providerで3並列レビュー（`high_fast`）
- 任意で他providerクロスレビュー1本追加
- `critical/high > 0` ならFix実行 -> 再レビュー（最大3ループ）

### Phase 4: Quality Gate
終了条件:
1. DoD達成
2. 検証コマンド通過
3. `critical=0` かつ `high=0`
4. 主張-根拠対応表の必須列充足

## Review Merge 契約

```json
{
  "same_provider_reviews": 3,
  "cross_provider_reviews": 1,
  "severity_count": {
    "critical": 0,
    "high": 0,
    "medium": 0,
    "low": 0
  },
  "must_fix": ["string"]
}
```

## 注意

- 本スキルは「共通契約」を提供する。コマンド実行の具体は provider adapter を使う。
- モデル更新時は原則 adapter 側を修正する。必要時のみ core 変更を許可する。
