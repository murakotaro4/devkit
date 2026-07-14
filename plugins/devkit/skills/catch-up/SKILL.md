---
name: "catch-up"
description: "外部世界(モデル世代・CLI フラグ・ハーネス機能)の変化に、repo のドキュメント・テンプレート・検査値を premises.json レジストリ起点で追従更新する。実機裏取り→影響棚卸し→更新計画→承認→適用→独立レビュー→version bump 提案まで一気通貫。『キャッチアップして』『新モデルに追従して』『世代更新して』『/catch-up』で起動"
argument-hint: "[何が変わったか]"
allowed-tools: ["Read", "Grep", "Glob", "Bash", "Edit", "Write", "WebSearch", "WebFetch", "AskUserQuestion", "request_user_input", "spawn_agent", "wait_agent", "TaskCreate", "TaskUpdate", "TaskOutput"]
---

# /catch-up - 外部前提の追従更新

外部世界で変わったモデル世代、CLI フラグ、ハーネス機能、marketplace 名を、`plugins/devkit/premises.json` を起点に裏取り・棚卸し・更新する。

## 対象

$ARGUMENTS

## ハーネス判定

正本は devkit リポジトリの `AGENTS.md`「スキル共通契約」。フロー開始前に利用可能なツール名で判定し、この SKILL.md も実行に必要な要点を自己完結で保持する。

- `AskUserQuestion` が使える -> Claude 親。
- `AskUserQuestion` がなく `spawn_agent` が使える -> Codex 親。
- どちらでもない -> 判定不能として扱う。
- `request_user_input` は判定キーに使わず、Codex 親 plan mode の質問手段としてだけ使う。

質問は Claude 親では AskUserQuestion、Codex 親 plan mode では `request_user_input`、Codex 親通常 mode / 判定不能では選択肢を箇条書きで提示して自由文回答を求める。

## タスクリスト連動

正本は `AGENTS.md`「スキル共通契約 > タスクリスト連動」。開始時に step 1-8 を登録し、開始時 `in_progress`、完了時 `completed` へ更新する。Claude 親は TaskCreate / TaskUpdate が利用可能なら使い、Codex 親は組み込み plan 機能または通常の進捗報告で同等に示す。

## 進捗可視化

正本は devkit リポジトリの `AGENTS.md`「スキル共通契約 > 委譲・長時間ジョブの進捗可視化」。要点:

- 委譲ジョブは 1 ジョブ = 1 タスクとしてタスクリストへ登録し、開始時 in_progress・完了時 completed へ更新する(親 step のタスクへ blockedBy で紐付ける)。
- Claude 親の外部 CLI 委譲は Bash `run_in_background` で起動し、完了自動通知を契機に回収する。定期ハートビートは逐次表示せず、出力増分が長時間ない場合のみ停滞状況を報告する。
- Codex 親の子 agent 委譲は `wait_agent` で黙って待たず、定期的に進捗をユーザーへ提示する。
- 実体の進捗は `git status` / `git diff` で確認し、resume を進捗確認に使わない。

## フロー

### 1. 変化の受領とスコープ確認

選択肢付き質問を 1 ラウンド行い、変化の種別、情報源、対象範囲、version bump 希望を確認する。目的 / 成功条件 / 非対象 / 採用した仮定を短く合意する。

### 2. 実機裏取り(read-only)

`command -v` で利用可否を確認してから `codex --version`、`cursor-agent --help`、`claude --help` などを実行し、公式 release note も WebSearch / WebFetch で確認する。実機出力の該当行と URL を証拠として記録する。裏取り不能な項目は確定事項にせず仮定と明示し、ユーザー確認を得る。

### 3. レジストリ起点の影響棚卸し(read-only)

`plugins/devkit/premises.json` を読み、先に `plugins/devkit/scripts/check_external_premises.py` を実行する。red なら地図が壊れている別件として報告して停止する。green なら該当 premise の occurrences と repo 全体の `rg` を突き合わせ、今回の旧値と適用時に `obsolete_value_patterns` へ移す pattern を特定する。既存の obsolete pattern がある場合は、その取り残しがゼロであることも確認して、次の棚卸し表を提示する。

| premise | 旧値 -> 新値 | ファイル:出現数 | update_notes | 影響テスト |
|---|---|---|---|---|

レジストリが無い repo では grep ベースの臨時棚卸しへ fallback し、レジストリ新設を提案する。

### 4. 更新計画と承認

write_scope、ファイルごとの具体編集、検証コマンド、version bump 案を提示して明示承認を得る。値だけの追従は patch、workflow contract の変更は minor を提案する。**承認前に Edit / Write を使わない。**

### 5. 適用

承認済み write_scope 内だけを編集する。docs / tests / plugin manifest と同時に `premises.json` の `current_value`、`value_patterns`、`occurrences`、`last_verified` を更新する。値の移行時は旧値の pattern を `obsolete_value_patterns` へ移し、取り残しゼロを `check_external_premises.py` で強制する。

### 6. 検証

devkit repo では次を green まで実行する。

```bash
uv run --project plugins/devkit python plugins/devkit/scripts/check_external_premises.py
uv run --project plugins/devkit python plugins/devkit/scripts/devkit_harness.py verify-fast
```

### 7. 独立レビュー(必須・スキップ不可)

- Claude 親: `codex -a never exec -m gpt-5.6-sol -c model_reasoning_effort="medium" review --uncommitted < /dev/null` を background 起動し、完了通知で回収する。
- Codex 親: `spawn_agent` explorer に read-only 指示、承認済み計画、diff 全文を渡す。

指摘を修正して再検証し、追加 findings がなくなるまで独立レビューを繰り返す。

### 8. 完了報告と version bump 提案

変更サマリー、裏取り証拠、レジストリ diff、検証結果、bump 後 version を報告する。commit / push はユーザーが明示した場合だけ行う。

## 他スキルとの境界

- `memory-review` は内部メモリ・ルールを監査して発見する。外部値の更新実務は catch-up が担う。
- `improve-skill retro` はセッション内エラー起点のスキル修正。catch-up は外部世界の変化起点の値追従を担う。
- `dig` は汎用実装。catch-up はレジストリ登録済みの値の追従専用で、workflow contract 自体の変更や新 backend 追加は dig へ渡す。

## 注意

- check は repo とレジストリの一致を検証するだけで、外部世界での最新性は検出しない。
- 証拠の無い推測で外部前提を書き換えない。
- 承認済み write_scope を越えない。
