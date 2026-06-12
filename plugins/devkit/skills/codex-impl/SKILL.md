---
name: "codex-impl"
description: "Codex CLI に実装を委譲する軽量スキル。Claude = 要件整理・レビュー・テスト、Codex = 実装。「Codexに実装させて」「実装を委譲して」「codexで作って」で起動"
argument-hint: "[task]"
allowed-tools: ["Bash", "Read", "Grep", "Glob"]
---

# /codex-impl - Codex 実装委譲スキル

Claude（計画・レビュー担当）と Codex CLI（実装担当）の役割分担で開発を進める軽量スキル。
連携は `codex exec`（Bash 経由）のみ。MCP / app-server は使わない。

## タスク

$ARGUMENTS

## 役割分担

| 担当 | 役割 |
|--------|------|
| Claude | 要件整理・実装指示の作成・diff レビュー・テスト実行・完了報告 |
| Codex | コードの実装・修正（commit はさせない） |

## 実行フロー

1. **要件整理（Claude）**: 依頼を実装指示 1 ブロックにまとめる。対象リポジトリ・変更範囲・受け入れ条件を明記する。曖昧な点が残るならユーザーに確認する
2. **実装委譲**: 標準コマンドで `codex exec` を実行する
3. **レビュー（Claude）**: `git diff` を全文読み、プロジェクトのテスト・リンタを実行する
4. **修正委譲**: 指摘があれば `codex exec resume --last "<指摘と修正指示>"` で再委譲する
5. 手順 3-4 を指摘解消まで繰り返し、完了サマリーを報告する

## 標準コマンド

```bash
codex exec -C "<repo>" --sandbox workspace-write -a never "<実装指示>"
```

- **モデルは指定しない**: `~/.codex/config.toml` の既定（最新モデル + reasoning effort xhigh）に従う。旧モデルを `-m` で焼き込まない
- 調査・相談のみの委譲: `--sandbox read-only`（ウェブ検索が必要なら `--search` を追加）
- sandbox の緩和（workspace 外への書き込み等）はユーザー確認の上でのみ行う

## 長時間タスク

- 既定: 通常実行（Bash timeout は最大 600000ms まで延長可）
- 多ファイル変更や 5 分超見込み: Bash `run_in_background` で起動し、完了後に diff レビューへ進む
- 進捗確認は `git status` / `git diff` で実態を見る（resume を進捗確認に使わない）

## レビューゲート

- 必須: Claude 自身の diff 全文レビュー + プロジェクトのテスト実行
- 任意（変更が大きい場合）: `codex -a never exec review --uncommitted` でセカンドオピニオンを取る

## 注意

- 秘密情報（`.env` / credentials / `*.pem` 等）を実装指示に含めない
- commit / push は Codex にさせず、レビュー通過後に Claude がユーザー確認の上で行う
- codex CLI が使えない場合はユーザーに報告し、承認を得て Claude 実装にフォールバックする
