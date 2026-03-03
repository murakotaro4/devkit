---
name: "decomposition"
description: "計画やコンテキストからタスクを5-30分の単一責任サブタスクに分解しTaskCreateで登録する。『タスク分解して』『分解して実行』で起動"
argument-hint: "[plan-file-path or context]"
allowed-tools: ["Read", "Grep", "Glob", "Bash"]
---

# /decomposition - タスク分解

計画ファイルまたは会話コンテキストから、実行可能なサブタスクに分解する。

## トピック
$ARGUMENTS

## 入力ソース

### dig からの連携時（主要ユースケース）
- dig の Step 4 から呼び出される
- $ARGUMENTS に plan file パスが渡される
- plan file を Read で読み込み、分解の入力とする

### 独立実行時
- $ARGUMENTS にファイルパスがあればそのファイルを読む
- 指定がなければ会話コンテキストから推測する

## 分解プロセス（5ステップ）

### Step 1: コードベース探索

分解の前にコードベースを具体的に理解する。

- プロジェクト構造の把握（ディレクトリ、モジュール、パッケージ）
- 既存パターンの確認（類似機能の実装方法）
- 影響範囲の特定（変更対象ファイル）
- 依存関係の把握（ライブラリ、API、内部モジュール）

**探索していないものは分解しない。**

dig 連携時は dig の探索結果がコンテキストに含まれるため、追加探索は最小限に留める。

### Step 2: 主要コンポーネントの特定

タスク全体を主要コンポーネントに分割する:
- 作業の明確なフェーズ・領域は何か
- コンポーネント間の依存関係は何か
- どの順序で着手すべきか

### Step 3: 詳細サブタスク作成

各コンポーネントについて、以下の品質基準を満たすサブタスクを作成する。

**品質基準**:
| 基準 | 説明 | NG例 → OK例 |
|------|------|-------------|
| 具体的 | 明確なアクション動詞、正確なファイルパス、関数/クラス名 | "refactor the code" → "Extract calculateDiscount() to utils/discount.ts" |
| 自己完結 | 説明文だけで実行可能。追加の確認が不要 | "Wait for API approval then implement" → "Implement based on OpenAPI spec in docs/" |
| 適切な粒度 | 5-30分で完了する単一責任 | "Build entire auth system" → "Add JWT token validation to middleware" |
| 検証可能 | 具体的な検証手順を含む | "verify it works" → "npm test -- --grep 'JWT' passes" |

### Step 4: What/Where/How/Why/Verify 記述

各サブタスクの description に以下の5セクション構造を記述する:

```
**What**: [実行すべき具体的なアクション]
**Where**: [正確なファイルパス、関数/クラス名、行範囲]
**How**: [コードベースの既存パターンを参照した実装アプローチ]
**Why**: [目的と、全体タスクの中での位置づけ]
**Verify**: [具体的な検証手順 - 実行コマンド、期待出力、手動確認手順]
```

### Step 5: TaskCreate 実行 + plan file 追記 + カバレッジ検証

#### 5a. TaskCreate でサブタスクを登録

各サブタスクを TaskCreate で登録する。

**必須フィールド（validation ルール）**:
- **subject**: `[Phase 6.N] 内容` 形式（N は 1 から連番、アクション動詞で開始、50文字以内目安）
- **description**: What/Where/How/Why/Verify の5セクションを必ず含む
- **metadata**: `{phase: "phase_6"}` を必ず含める
- **activeForm**: 現在進行形（例: "User モデルを作成中"）

**登録例**:
```
TaskCreate:
  subject: "[Phase 6.1] User モデルをデータベーススキーマに作成"
  description: |
    **What**: User テーブル（id, email, password_hash, created_at）を追加
    **Where**: src/models/user.ts, src/migrations/003_create_users.ts
    **How**: src/models/post.ts の既存パターンに従い、TypeScript interface と Knex migration を定義
    **Why**: 認証機能の基盤としてユーザー資格情報を安全に保存する
    **Verify**: `npm run migrate` 実行後、`npm test -- --grep "User model"` でテーブル存在を確認
  metadata: {phase: "phase_6"}
  activeForm: "User モデルをデータベーススキーマに作成中"
```

#### 5b. 依存関係の設定

TaskUpdate で依存関係を設定する:
- サブタスク間の依存を `addBlockedBy` で設定
- 独立したサブタスクは blockedBy を設定しない（並列実行可能）
- 既存の Phase 6 本体タスクがあれば、Phase 6 本体に `addBlockedBy` で全サブタスクを紐付け

#### 5c. plan file への追記

plan file が存在する場合、分解結果セクションを追記する:

```markdown
## タスク分解結果

### 元タスク
[元タスクの要約]

### サブタスク一覧
| # | サブタスク | 依存 | 見積 |
|---|-----------|------|------|
| 6.1 | [内容] | - | Xmin |
| 6.2 | [内容] | 6.1 | Xmin |

### 依存関係グラフ
Task 6.1 → Task 6.2 → Task 6.4
Task 6.1 → Task 6.3 → Task 6.4

### スコープ
- サブタスク数: N
- 複雑度: Low/Medium/High
```

#### 5d. カバレッジ検証

分解完了後、以下を確認する:
- サブタスク全体で元タスクの全範囲をカバーしているか
- 各サブタスクに具体的な検証手順があるか
- 依存関係に矛盾（循環依存等）がないか
- 抜け漏れがあれば Step 2 に戻って追加分解する

## Phase 6 完了条件

workflow.md 準拠: **全サブタスク完了を TaskList で確認してから** Phase 6 本体を completed にする。
- 各サブタスク完了時: `TaskUpdate(taskId, status="completed")`
- Phase 6 本体完了: 全サブタスクが completed であることを TaskList で確認後に実行

## post-task-tracker.js との互換性

サブタスクの metadata に `{phase: "phase_6"}` を含めることで、post-task-tracker.js が自動的に phases_passed を更新する。

## アンチパターン（禁止事項）

- **曖昧な記述**: 「適切に実装する」「必要に応じて修正」等の非具体的な表現
- **巨大タスク**: 30分を超える見積もりのタスク（さらに分割する）
- **検証なし**: Verify セクションが空のタスク
- **架空の参照**: コードベースに存在しないファイルパスや関数名の参照
- **循環依存**: A→B→C→A のような依存関係

## 使用例

```
/decomposition .claude/plans/my-plan.md
/decomposition  （会話コンテキストから分解）
```

dig 連携時は自動的に呼び出されるため、ユーザーが直接実行する必要はない。

## 重要

- **探索ファースト**: コードベースを調査してから分解する。推測で分解しない
- **Phase 6.N 形式を厳守**: subject は `[Phase 6.N] 内容` 形式、metadata に `{phase: "phase_6"}`
- **What/Where/How/Why/Verify 構造を厳守**: description に5セクションを必ず含める
- **依存関係を明示**: TaskUpdate の addBlockedBy/addBlocks で自動設定
- **plan file にも記録**: 分解結果セクションを追記して可視化する
- **Phase 6 完了ゲート**: 全サブタスク完了を TaskList で確認してから Phase 6 本体を completed にする
