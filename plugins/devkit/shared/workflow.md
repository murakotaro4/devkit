# devkit 統一開発ワークフロー（絶対ルール）

このルールはすべてのタスクに適用される。タスクの大小に関わらず全8フェーズを通過すること。

## 前提条件

- codex CLI (OpenAI Codex CLI) がインストール済みであること
- 未インストール時はレビューフェーズでユーザーに警告し手動レビューに切り替え

### レビュー CLI フォールバック戦略

**Claude Code が親の場合**（通常の対話セッション）:

| 優先度 | コマンド | 条件 |
|--------|---------|------|
| 1st | `codex exec review --uncommitted -m gpt-5.3-codex-spark` | デフォルト |
| 2nd | `codex exec review --uncommitted -m gpt-5.3-codex` (effort=medium) | spark レートリミット時 |
| 3rd | レビュースキップ + ユーザー通知 | codex CLI 未インストール or 全モデル不可時 |

**Codex CLI が親の場合**（dig-codex 経由等）:

| 優先度 | コマンド | 条件 |
|--------|---------|------|
| 1st | `claude -p --model haiku --tools 'Read,Grep,Glob'` | デフォルト |
| 2nd | `claude -p --model sonnet --tools 'Read,Grep,Glob'` | haiku 不可時 |
| 3rd | レビュースキップ + ユーザー通知 | claude CLI 未インストール or 全モデル不可時 |

## 8フェーズ必須フロー

| # | フェーズ | 完了条件 |
|---|---------|----------|
| 1 | 調査1（初期理解） | 対象の特定 |
| 2 | 深掘り（要件確認） | ユーザー承認 |
| 3 | 調査2（技術調査） | アプローチ確定 |
| 4 | 計画 | plan file 完成 |
| 5 | 計画レビュー | critical/high=0 |
| 6 | 実装 | DoD 達成 |
| 7 | 実装レビュー | critical/high=0 |
| 8 | コミット&プッシュ | push 完了 |

### Phase 2: 深掘り（要件確認）

- runtime に応じた質問手段を使う
  - Claude: AskUserQuestion
  - Codex Plan Mode: request_user_input
  - OpenCode: question（不可時はメッセージ質問）
- コードベース調査を織り交ぜて具体的な文脈で質問

### Phase 4: 計画（plan 作成）

- runtime に応じて plan を開始
  - Claude: EnterPlanMode
  - Codex: Plan Mode 前提
  - OpenCode: Plan agent 前提
- コミットセクションは3ステップ構成必須: ステージング -> コミット前レビュー -> コミット+プッシュ

### Phase 5: 計画レビュー（必須・省略禁止）

- クロスモデルレビューを Bash で直接実行（Skill ツール経由禁止）
- 停止条件: `critical=0` かつ `high=0`

### Phase 8: コミット&プッシュ

1. git add でステージング
2. コミット前クロスモデルレビュー
3. git commit + git push

## スキル連携マッピング（任意）

| フェーズ | 加速用スキル |
|---------|-------------|
| Phase 1,3 | /codex-search, /deep-research |
| Phase 2 | /dig |
| Phase 4-5 | /dig（計画+レビュー部分） |

## 禁止事項

- 計画なしの実装開始（Phase 4 スキップ禁止）
- レビューなしのコミット（Phase 5, 7 スキップ禁止）
- フェーズの無断スキップ
