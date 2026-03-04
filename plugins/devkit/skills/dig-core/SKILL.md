---
name: "dig-core"
description: "dig 系の共通実行契約。深掘り質問、終了確認、タスク分解、計画レビュー、実行の共通ステップを定義する。"
argument-hint: "[topic]"
allowed-tools: ["Read", "Grep", "Glob", "Bash"]
---

# /dig-core - Shared Contract

このスキルは `dig` adapter から参照される共通契約である。

## 共通ステップ

1. 深掘り質問
2. 終了確認
3. タスク分解（オプション）
4. 計画レビュー（クロスモデル）
5. 実行

## 安全ガード

- 読まないファイル:
  - `.env`, `.env.*`
  - `*.pem`, `*.key`, `id_rsa`
  - `credentials.json`, `secrets.*`
- 広域検索（`**/*`）前に、範囲・目的を提示して承認を得る。

## レビュー契約

- レビューは Bash で直接実行する。
- 判定は `critical/high` で行う。
- 停止条件: `critical=0` かつ `high=0`

## コミット契約

コミット計画を含む場合は必ず以下の順序:
1. `git add`
2. コミット前クロスモデルレビュー
3. `git commit` + `git push`
