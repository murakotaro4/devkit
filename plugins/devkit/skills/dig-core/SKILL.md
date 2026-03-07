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
4. 計画レビュー（review gate）
5. 実行

## 安全ガード

- 読まないファイル:
  - `.env`, `.env.*`
  - `*.pem`, `*.key`, `id_rsa`
  - `credentials.json`, `secrets.*`
- 広域検索（`**/*`）前に、範囲・目的を提示して承認を得る。

## レビュー契約

- レビューゲートは runtime 契約に従う。
- Bash で直接実行できる場合はそれを優先する。
- Bash 実行が unavailable な runtime では、adapter 契約に従って独立 reviewer を代替経路として使ってよい。
- Bash 経路を使う場合、レビュー結果の最終行は次の機械可読マーカーを必須とする:
  - `REVIEW_RESULT_MARKER=REVIEW_COUNTS`
  - `REVIEW_COUNTS critical=<int> high=<int>`
- 判定は `critical/high` で行う。
- `REVIEW_COUNTS` がパース不能な場合は「レビュー不能」として扱う。
- 停止条件: `critical=0` かつ `high=0`

## 停止時出力契約

- 停止時は以下3行を必須とする:
  - `ERROR_CODE: <CODE>`
  - `RERUN_COMMAND: <one-line command>`
  - `DIAGNOSTIC_COMMAND: <one-line command>`
- `STOP_OUTPUT_FIELDS: ERROR_CODE,RERUN_COMMAND,DIAGNOSTIC_COMMAND`

## コミット契約

コミット計画を含む場合は必ず以下の順序:
1. `git add`
2. コミット前レビューゲート
3. `git commit` + `git push`
