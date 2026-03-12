---
name: "devkit-init"
description: "DevKitの共有ワークフロールールをターゲットリポジトリに同期する。CLAUDE.mdに@import参照を追加し、AGENTS.mdにワークフローセクションを同期する。'devkit-init実行して' 'ワークフロー同期して' で起動。"
allowed-tools: ["Read", "Grep", "Glob", "Bash", "Write", "Edit"]
---

# /devkit-init - DevKit ワークフロー同期

ターゲットリポジトリに DevKit の共有ワークフロールール（agent team 前提の8フェーズ + レビューゲートの**運用契約**）を同期する。

## トピック
$ARGUMENTS

## 同期対象

DevKit の `shared/workflow.md`（SSOT）を以下の2経路で同期:

1. **CLAUDE.md**: `@import` でランタイム読み込み（常に最新）
2. **AGENTS.md**: マーカーセクション内に静的コピー（人間参照用）

> runtime 固有の hook / automation は同期対象に含めず、`shared/workflow.md` の運用契約だけを同期する。

## 実行ルール（必須）

### 1. 事前検証（フェイルファスト）

以下を順に検証し、いずれか失敗時は変更を一切行わず中断する。

1. **DevKit パス探索**（優先順）:
   - `.claude/devkit-init.json` に記録済みパスがあればそれを使用
   - `~/.agents/skills/*` の symlink target または `~/cursor/devkit` から DevKit ルートを逆算
   - 兄弟ディレクトリ探索: `../devkit/plugins/devkit/shared/workflow.md` の存在確認
   - いずれも失敗 → AskUserQuestion でユーザーにパスを質問

2. **ファイル存在検証**: DevKit の `shared/workflow.md` が存在すること
3. **相対パス計算**: DevKit パスからカレントプロジェクトへの相対パスを計算
4. **ターゲットファイル確認**: `CLAUDE.md` と `AGENTS.md` が存在し書き込み可能であること
5. **Git リポジトリ確認**: カレントディレクトリが git リポジトリであること

### 2. 冪等性チェック

- CLAUDE.md に `shared/workflow.md` の `@import` が既にあるか確認
- AGENTS.md に `<!-- devkit:workflow:start -->` マーカーが既にあるか確認
- `.claude/devkit-init.json` の `workflow_source_hash` と現在のファイルハッシュを比較
- ハッシュ一致 = 変更なし → 「最新の状態です」と報告して終了

### 3. CLAUDE.md 更新

- タイトル行（`# CLAUDE.md` や最初の `#` 見出し）の直後に `@<相対パス>/shared/workflow.md` を挿入
- 例: `@../devkit/plugins/devkit/shared/workflow.md`
- 既に存在する場合はスキップ

### 4. AGENTS.md 更新（最もデリケート）

**バックアップ**: まず `.claude/devkit-init-backup/AGENTS.md.bak` に現在の AGENTS.md をコピーする。

**既存重複セクション検出**:
- `## コミット前レビュー（クロスモデル必須）` や `## レビューゲート` 等の見出しを検出
- 検出したセクションの内容をユーザーに表示し、除去の可否を AskUserQuestion で確認
- 承認 → 旧セクションを除去
- 拒否 → 旧セクションを `<!-- deprecated: devkit-init により workflow セクションに統合済み -->` でラップ

**マーカーセクション挿入/更新**:
- `<!-- devkit:workflow:start -->` / `<!-- devkit:workflow:end -->` マーカーを検出
- マーカーが既にある場合: マーカー間の内容を `shared/workflow.md` の最新版で上書き
- マーカーがない場合: 既存セクション除去位置（または AGENTS.md の skills_system ブロック直前）にマーカーセクションを挿入

マーカーセクションのフォーマット:
```markdown
<!-- devkit:workflow:start -->
<!-- このセクションは devkit-init により自動管理されます。手動編集は次回同期時に上書きされます。 -->
## 統一開発ワークフロー（DevKit 同期）

(shared/workflow.md の全内容)
<!-- devkit:workflow:end -->
```

### 5. マニフェスト記録

`.claude/devkit-init.json` に状態を保存:

```json
{
  "version": "1.0",
  "initialized_at": "<ISO 8601>",
  "devkit_path": "<DevKit への相対パス>",
  "workflow_relative_path": "<shared/workflow.md への相対パス>",
  "workflow_source_hash": "<sha256 of workflow.md>"
}
```

ハッシュ計算: `shasum -a 256 <workflow.md path> | cut -d' ' -f1`

### 6. 検証 & レポート

- import 先ファイルの存在確認
- マーカー整合性確認（start/end ペアの存在）
- バックアップファイルの存在確認
- 変更サマリを出力:
  - CLAUDE.md: @import 追加/スキップ
  - AGENTS.md: マーカーセクション 挿入/更新
  - 旧セクション: 除去/deprecated ラップ/該当なし
  - ハッシュ: 前回 → 今回

## 再実行時の動作

- マーカー間の内容を最新の `shared/workflow.md` で上書き
- CLAUDE.md の @import 行はそのまま
- DevKit でワークフロー更新 → 各リポで `/devkit-init` 再実行 = 同期完了

## 注意事項

- 初回実行時、Claude Code が外部ファイル import の承認ダイアログを表示する場合がある
- マーカーセクション内の手動編集は次回同期時に上書きされる
- プロジェクト固有ルール（絶対ルール、技術スタック等）はマーカー外に配置すること
