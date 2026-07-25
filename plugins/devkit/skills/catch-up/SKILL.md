---
name: "catch-up"
description: "外部世界(モデル世代・CLI フラグ・ハーネス機能)の変化に、repo のドキュメント・テンプレート・検査値を premises.json レジストリ起点で追従更新する。実機裏取り→影響棚卸し→更新計画→承認→適用→独立レビュー→version bump 提案まで一気通貫。『キャッチアップして』『新モデルに追従して』『世代更新して』『/catch-up』で起動"
argument-hint: "[何が変わったか]"
allowed-tools: ["Read", "Grep", "Glob", "Bash", "Edit", "Write", "WebSearch", "WebFetch", "AskUserQuestion", "request_user_input", "spawn_agent", "wait_agent", "TaskCreate", "TaskUpdate", "TaskOutput"]
---

# /catch-up - 外部前提の追従更新

モデル世代、CLI フラグ、ハーネス機能、marketplace 名の変化を `plugins/devkit/premises.json` 起点で裏取り・更新する。

## 対象

$ARGUMENTS

## ハーネス・進捗

| 判定 | 質問 | 独立レビュー |
|---|---|---|
| `AskUserQuestion` が使える Claude 親 | AskUserQuestion | 外部 Codex |
| それがなく `spawn_agent` が使える Codex 親 | plan mode は `request_user_input`、通常 mode は選択肢付き自由文 | read-only 子 agent |
| 判定不能 | 選択肢付き自由文 | 利用可能な独立 backend |

`request_user_input` は判定キーにしない。step 1-8 と委譲ジョブはタスクリストまたは通常報告で開始・完了を示す。長時間ジョブは実体を `git status` / `git diff` で確認し、停滞時だけ報告する。Codex 親は `wait_agent` で黙って待たない。

## フロー

### 1. 変化とスコープ

変化の種別、情報源、対象、version bump 希望のうち結果を左右する未知だけ確認し、目的 / 成功条件 / 非対象 / 仮定を揃える。

### 2. 実機裏取り(read-only)

`command -v` 後に各 CLI の version / help と公式情報を確認し、該当出力と URL を証拠化する。裏取り不能な値は確定せず、仮定として承認対象にする。

### 3. レジストリ起点の影響棚卸し(read-only)

`plugins/devkit/premises.json` を読み、最初に `plugins/devkit/scripts/check_external_premises.py` を実行する。red なら別件のレジストリ破損として報告し、更新を停止する。green なら `current_value`、`value_patterns`、`occurrences`、`obsolete_value_patterns`、`last_verified` と repo 全体の検索結果を照合し、旧値の取り残しも確認する。

| premise | 旧値 -> 新値 | ファイル:出現数 | update_notes | 影響テスト |
|---|---|---|---|---|

レジストリがない repo は grep で臨時棚卸しし、新設を提案する。

### 4. 更新計画と承認

承認前に Edit / Write を使わない。計画は第 1 層「承認用サマリー」と第 2 層「詳細」に分け、第 1 層に次を含める。

1. 何を / なぜ
2. 判断してほしい点(推奨付き、最大 3 件程度)
3. 既定からの逸脱・採用した仮定
4. 後戻りしにくい操作・外部影響
5. backend 表(計画レビュー / 実装 / diff レビュー)
6. green 条件
7. 独立レビュー状態(`実施済み(指摘 N 件反映)` / `skip(理由)` / `適用なし`)と backend

承認時点の独立レビュー状態は `skip(承認時点では未実施。適用後 step 7 で実施)` とする。詳細には write_scope、ファイル別変更、検証コマンド、version bump 案を置く。値だけの追従は patch、workflow contract 変更は minor を提案する。

### 5. 適用

承認済み write_scope 内で docs / tests / plugin manifest と `premises.json` を同期する。値の移行では旧 pattern を `obsolete_value_patterns` へ移し、取り残しを許さない。

### 6. 検証

devkit repo では次を green にする。

```bash
uv run --project plugins/devkit python plugins/devkit/scripts/check_external_premises.py
uv run --project plugins/devkit python plugins/devkit/scripts/devkit_harness.py verify-fast
```

### 7. 独立レビュー(必須・スキップ不可)

Claude 親は `codex -a never exec -m gpt-5.6-sol -c model_reasoning_effort="medium" review --uncommitted < /dev/null`、Codex 親は `spawn_agent` で承認計画と diff の read-only review を行う。指摘を修正・再検証し、追加 findings がなくなるまで繰り返す。

### 8. 完了報告と version bump 提案

変更、裏取り証拠、レジストリ diff、検証、bump 後 version を報告する。commit / push はユーザーが明示した場合だけ行う。

## 境界

内部メモリ監査は memory-review、セッション内エラー起点の改善は improve-skill retro、workflow contract 自体の変更や新 backend は dig が担う。catch-up は外部変化による登録済み premise の追従に限定する。check は repo とレジストリの一致を検証するもので、外部の最新性は別途裏取る。
