---
name: codex
description: "Codex（GPT）にタスクを委譲するオーケストレーター"
argument-hint: "[topic]"
allowed-tools: ["Read", "Write", "Edit", "Grep", "Glob", "Bash"]
---

# /codex - Codex委譲オーケストレーター

Codex（GPT）にタスクを委譲する7フェーズオーケストレーター。
深掘り質問→コードベース探索→プラン作成→レビュー→並列実行→レビュー→統合の流れで処理する。

## 使い方

```
/codex "topic"
```

例：
- `/codex "このPRのコードレビュー"`
- `/codex "認証機能の実装"`
- `/codex "パフォーマンス改善の分析"`

---

## 7フェーズ動作フロー

### Phase 1: 深掘り質問

AskUserQuestionでtopicについて深掘りする。

**質問の観点:**
- What: 具体的に何を実行するか
- Why: なぜそれが必要か
- How: どのように実現するか
- Scope: 対象範囲はどこまでか
- Constraints: 制約や制限は何か
- Parallelization: どのタスクが並列実行可能か

**終了条件:**
- 疑問点がなくなった
- ユーザーが終了を希望した

---

### Phase 2: コードベース探索

**Codexによる並列探索を実行し、実装に必要なコンテキストを収集する。**

**実行方法:**
- `codex exec` コマンドを使用（MCP使用禁止）
- Taskツールでサブエージェント（Bash）をspawnして並列実行

**探索タスク（最大4個並列）:**

| タスク | 目的 | プロンプト例 |
|--------|------|--------------|
| 1. 関連ファイル・依存関係 | 対象機能に関連するファイルと依存関係を特定 | "List all files related to X and their dependencies" |
| 2. 既存実装パターン | 類似機能の実装パターンを分析 | "Analyze existing implementation patterns for similar features" |
| 3. リスク・制約 | 潜在的なリスクと技術的制約を洗い出し | "Identify risks, constraints, and potential issues" |
| 4. ドメイン知識 | 関連するドメイン知識を収集 | "Gather domain knowledge and business rules relevant to X" |

**コマンド形式:**

```bash
codex exec -C /path/to/project -m gpt-5.2 -c model_reasoning_effort="high" --sandbox read-only "探索プロンプト"
```

**実行パターン:**

```
# Step 1: バックグラウンドで4タスク並列起動
Task(subagent_type="Bash", prompt="codex exec -C /path -m gpt-5.2 -c model_reasoning_effort=\"high\" --sandbox read-only \"関連ファイル探索...\"", run_in_background=true, timeout=300000)
Task(subagent_type="Bash", prompt="codex exec -C /path -m gpt-5.2 -c model_reasoning_effort=\"high\" --sandbox read-only \"実装パターン分析...\"", run_in_background=true, timeout=300000)
Task(subagent_type="Bash", prompt="codex exec -C /path -m gpt-5.2 -c model_reasoning_effort=\"high\" --sandbox read-only \"リスク・制約分析...\"", run_in_background=true, timeout=300000)
Task(subagent_type="Bash", prompt="codex exec -C /path -m gpt-5.2 -c model_reasoning_effort=\"high\" --sandbox read-only \"ドメイン知識収集...\"", run_in_background=true, timeout=300000)

# Step 2: 全タスク完了を待機
TaskOutput(task_id=agentId1, block=true, timeout=300000)
TaskOutput(task_id=agentId2, block=true, timeout=300000)
TaskOutput(task_id=agentId3, block=true, timeout=300000)
TaskOutput(task_id=agentId4, block=true, timeout=300000)
```

**設定:**
- タイムアウト: 300秒（5分）
- リトライ: 最大1回
- 並列数: Claudeの判断で1-4個（基本4個全て）

**結果統合:**
- 4つの探索結果をセクション別に連結して `exploration_context` として保持
- Phase 3（プラン作成）: 全結果をプランプロンプトに埋め込み
- Phase 6（実装レビュー）: リスク・制約セクションのみ参照

---

### Phase 3: プラン作成

1. EnterPlanModeでプランモードに入る
2. 以下を含むプランを作成：
   - **Phase 2の探索結果サマリー**（関連ファイル、パターン、リスク）
   - 各タスクの説明
   - 対応するcodex execコマンド（`-C`、`-m`、`-c`、`--sandbox`を含む）
   - 実行順序（並列可能なものを明示）
   - sandbox設定の判断根拠
3. ExitPlanModeでユーザー承認待ち

**プラン作成時のプロンプトに含める情報:**

```
## コードベース探索結果

### 関連ファイル・依存関係
{exploration_context.files}

### 既存実装パターン
{exploration_context.patterns}

### リスク・制約
{exploration_context.risks}

### ドメイン知識
{exploration_context.domain}
```

---

### Phase 4: プランレビュー（ループ）

**プラン承認後、実行前にレビューを実施。**

1. Skillツールで `claude-code-harness:codex-review` を呼び出す
   - プランの内容をCodexに渡してレビュー依頼
2. レビュー結果を確認：
   - **指摘あり**: プランを修正し、再度Phase 4を実行
   - **指摘ゼロ**: Phase 5へ進む

**ループ上限:** 最大3回。3回修正しても指摘が残る場合はユーザーに確認。

---

### Phase 5: 並列実行

1. Taskツールを**バックグラウンド**で並列起動
2. 各タスクでcodex execを実行
3. TodoWriteで進捗をトラック
4. エラー時は自動リトライ（最大2回）

**コマンド形式（実装タスク）:**

```bash
codex exec -C /path/to/project -m gpt-5.2-codex -c model_reasoning_effort="high" --sandbox workspace-write "実装プロンプト"
```

**実行パターン:**

```
# Step 1: バックグラウンドで並列起動（即座に返る）
Task(subagent_type="Bash", prompt="codex exec -C /path -m gpt-5.2-codex -c model_reasoning_effort=\"high\" --sandbox workspace-write '...'", run_in_background=true)
Task(subagent_type="Bash", prompt="codex exec -C /path -m gpt-5.2-codex -c model_reasoning_effort=\"high\" --sandbox workspace-write '...'", run_in_background=true)
→ 各タスクのagentIdが返される

# Step 2: 全タスク完了を待機
TaskOutput(task_id=agentId1, block=true)
TaskOutput(task_id=agentId2, block=true)

# Step 3: 結果を取得
Task(resume=agentId1, prompt="結果を報告")
Task(resume=agentId2, prompt="結果を報告")
```

---

### Phase 6: 実装レビュー（ループ）

**実行完了後、結果をレビュー。Phase 2で特定したリスク・制約を参照。**

1. Skillツールで `claude-code-harness:codex-review` を呼び出す
   - 実装結果・変更内容をCodexに渡してレビュー依頼
   - **Phase 2の「リスク・制約」セクションを含める**
2. レビュー結果を確認：
   - **指摘あり**: 指摘を修正し、再度Phase 6を実行
   - **指摘ゼロ**: Phase 7へ進む

**レビュープロンプトに含める情報:**

```
## 事前に特定されたリスク・制約
{exploration_context.risks}

上記のリスク・制約が適切に対処されているか確認してください。
```

**コマンド形式（レビュー）:**

```bash
codex exec -C /path/to/project -m gpt-5.2-codex -c model_reasoning_effort="high" --sandbox read-only "レビュープロンプト"
```

**ループ上限:** 最大3回。3回修正しても指摘が残る場合はユーザーに確認。

---

### Phase 7: 結果統合・報告

1. 全Codex出力を収集
2. 結果を統合・要約してユーザーに報告
3. エラーはまとめて報告
4. 必要に応じてコミット提案

---

## codex execコマンド形式

**必須オプション:**
- `-C <path>`: 作業ディレクトリを常に明示的に指定
- `-m <model>`: モデルを明示的に指定
- `-c model_reasoning_effort="<level>"`: 推論努力レベルを指定

**モデル・推論設定（フェーズ別）:**

| フェーズ | モデル | reasoning_effort | sandbox |
|----------|--------|------------------|---------|
| Phase 2（探索） | gpt-5.2 | high | read-only |
| Phase 5（実装） | gpt-5.2-codex | high | workspace-write |
| Phase 4, 6（レビュー） | gpt-5.2-codex | high | read-only |

**sandbox設定（タスク内容で判断）:**

| タスク種別 | sandbox | 例 |
|-----------|---------|-----|
| 探索・レビュー・分析 | `read-only` | コードベース探索、コードレビュー、調査 |
| 実装・修正 | `workspace-write` | 機能追加、バグ修正 |

```bash
# 探索フェーズ（読み取り専用、高推論）
codex exec -C /path/to/project -m gpt-5.2 -c model_reasoning_effort="high" --sandbox read-only "プロンプト"

# 実装フェーズ（書き込み可能、高推論）
codex exec -C /path/to/project -m gpt-5.2-codex -c model_reasoning_effort="high" --sandbox workspace-write "プロンプト"

# レビューフェーズ（読み取り専用、高推論）
codex exec -C /path/to/project -m gpt-5.2-codex -c model_reasoning_effort="high" --sandbox read-only "プロンプト"

# フルオート（確認なし + workspace-write）
codex exec -C /path/to/project -m gpt-5.2-codex -c model_reasoning_effort="high" --full-auto "プロンプト"
```

**注意**: `--approval-policy` はCLIでは使用不可。MCP経由（`mcp__codex__codex`）でのみ利用可能。

---

## リトライロジック

1. Codexがエラーを返した場合、エラー情報を含めて再実行
2. Phase 2（探索）: 最大1回リトライ
3. Phase 5（実装）: 最大2回リトライ
4. 規定回数失敗したらエラーとして記録し、最終報告に含める

---

## 制約

- Codexのセッションはステートレス（各呼び出しは独立）
- 各Codex呼び出しには完全なコンテキストを含める
- 並列実行時はファイル競合に注意してタスクを分割
- 探索結果（exploration_context）はセッション内で保持し、Phase 3・6で参照

---

## 実行チェックリスト

- [ ] Phase 1: 深掘り質問完了
- [ ] Phase 2: コードベース探索完了
- [ ] Phase 3: プラン作成・承認完了
- [ ] Phase 4: プランレビュー指摘ゼロ
- [ ] Phase 5: 並列実行完了
- [ ] Phase 6: 実装レビュー指摘ゼロ
- [ ] Phase 7: 結果報告完了
