---
name: "decomposition"
description: "計画やコンテキストから 5-30 分の単一責任サブタスクに分解し、plan ファイルへ追記する。dig 連携時は plan-only で使う。"
argument-hint: "[plan-file-path or context]"
allowed-tools: ["Read", "Grep", "Glob", "Bash"]
---

# /decomposition - タスク分解

計画ファイルまたは会話コンテキストから、実行可能なサブタスクへ分解する。

## 入力ソース

### dig からの連携時

- dig の Phase 3 から呼び出される
- `$ARGUMENTS` に plan file path が渡される
- dig 連携時は **plan-only** で動く
- Phase 3-4 では TaskCreate しない
- 実タスク化は dig-claude の Phase 5 で行う

### 独立実行時

- `$ARGUMENTS` にファイルパスがあれば読む
- 指定がなければ会話コンテキストから推測する
- 独立実行時も、まず plan へ分解結果を書くことを優先する

## 分解プロセス

### Step 1: コードベース探索

分解の前に、最低限以下を確認する。

- プロジェクト構造
- 類似実装
- 影響ファイル
- 依存関係

**探索していないものは分解しない。**

### Step 2: 主要コンポーネントの特定

タスク全体を主要コンポーネントに分ける。

- どの作業境界で分かれるか
- 依存順はどうなるか
- 並列化可能な部分はどこか

### Step 3: 詳細サブタスク作成

各サブタスクは次を満たすこと。

| 基準 | 説明 |
|------|------|
| 具体的 | アクション動詞、正確な file path、対象関数やテストを含む |
| 自己完結 | 説明文だけで着手できる |
| 適切な粒度 | 5-30 分で終わる |
| 検証可能 | Verify が具体的 |

### Step 4: What / Where / How / Why / Verify を書く

各サブタスクは description 相当として次の 5 セクションを持つ。

```markdown
**What**: [何をするか]
**Where**: [どこを触るか]
**How**: [どう実装するか]
**Why**: [なぜ必要か]
**Verify**: [どう確認するか]
```

### Step 5: plan file へ追記してカバレッジ検証

plan file がある場合は、以下のように追記する。

```markdown
## タスク分解結果

### 元タスク
[元タスクの要約]

### サブタスク一覧
| # | サブタスク | 依存 | 見積 |
|---|-----------|------|------|
| 1 | User モデル追加 | - | 10min |
| 2 | 認証 middleware 接続 | 1 | 15min |

### サブタスク詳細
#### User モデル追加
**What**: ...
**Where**: ...
**How**: ...
**Why**: ...
**Verify**: ...
```

検証項目:

- 元タスクを全範囲カバーしているか
- 各サブタスクに Verify があるか
- 依存関係に矛盾がないか
- `small` でも最低 1 件の実装サブタスクがあるか

## dig 連携での出力契約

dig 連携時、このスキルは **TaskCreate をしない**。出力は plan ファイル上の分解結果が正本である。

dig-claude 側は、Phase 4 review 通過後にその plan の summary を読み、Phase 5 開始時に以下の規約で task materialization する。

- タスク: `[Task 1] <summary>`, `[Task 2] <summary>` ...

## 独立実行時の扱い

独立実行でも、まずは plan ファイルや出力テキストに分解結果をまとめる。必要ならその後の実行担当が TaskCreate する。

## アンチパターン

- 曖昧な記述
- 30 分を超える巨大タスク
- Verify なし
- 存在しない file path や関数名
- 循環依存

## 重要

- 探索ファーストで分解する
- dig 連携時は plan-only で使う
- Phase 1-4 では TaskCreate しない
- plan 上のサブタスク名は prefix なしの summary で書く
- `[Task 1]`, `[Task 2]` ... の prefix 付与は Phase 5 materialization の責務とする
