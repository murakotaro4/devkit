---
name: "goal-prompt"
description: "固まった会話・仕様・計画を /goal 用ファイルと起動文へ変換する。『Goal プロンプトを作って』『/goal で実行できる形にして』『/goal-prompt』で起動"
argument-hint: "[source]"
---

# /goal-prompt - Goal プロンプト保存生成

実装スキルではない。固まった会話・仕様・レビュー済み計画を意味を変えず Goal 実行形式へ変換し、`.claude/goal-runs/` へ保存してユーザー用の起動プロンプトを出す。

## 対象

$ARGUMENTS

## ハーネス判定

`AskUserQuestion` が使えれば Claude 親、なければ `spawn_agent` の有無で Codex 親 / 判定不能を分ける。質問は Claude 親が AskUserQuestion、Codex 親 plan mode が `request_user_input`、それ以外は選択肢付き自由文を使う。

## 入力ソース

ユーザー明示のファイル・Issue・PR・仕様・会話を最優先する。指定がなければ `.claude/plans/*.md`、現在の会話、自然文仕様の順に探す。採用した計画ファイルは報告し、候補を一意に選べない場合だけ確認する。

目的、成功条件、scope、非対象、検証、完了証拠を抽出する。成功条件や write_scope を決められない重大な不足だけ確認し、軽微な不足は安全側の既定とその採用を本文・報告に明示する。

## 上限停止の自動算出

毎回ユーザーへ聞かず、明示値がある場合だけ上書きする。

| 規模 | 上限停止 | 修正ループ | CI 待機 |
|---|---|---|---|
| 小規模 | 12 ターンまたは 45 分 | 20 巡 | 20 分 |
| 標準 | 24 ターンまたは 120 分 | 20 巡 | 30 分 |
| 大規模 | 40 ターンまたは 240 分 | 20 巡 | 45 分 |

修正ループは findings がゼロで終了する。第 1 巡は最初の独立レビュー。件数は重複除去後の actionable findings 総数（severity は区別しない）。件数が前巡以上が 2 巡連続、同一 finding（ファイル・箇所・根本原因同一。文言一致ではない）が 2 巡連続で再出、20 巡到達で停止する。

大規模を超える場合は複数 Goal への分割を提案する。

## Goal 本文

次を含む: 不在自律実行、目的、検証可能な成功条件、検証コマンドまたは客観的確認、write_scope / read_scope、非対象、破壊的操作・外部変更の扱い、上限停止、修正ループ停止条件、行き詰まり停止、完了証拠、`.claude/goal-runs/` 内の完了レポート保存先、秘密情報を値でなく参照方法にする指示。

## 保存契約

保存先は `.claude/goal-runs/YYYY-MM-DD-<slug>-goal.md`。既存ファイルがある場合は上書きせず、`-goal` の前へ連番を入れて `YYYY-MM-DD-<slug>-2-goal.md` から採番する。commit せず、`plugins/devkit/premises.json` へ登録しない。

`.claude/goal-runs/.gitignore` が無ければ `*` 1 行で新規作成し、既存の `.gitignore` は変更しない。git repo では `git check-ignore` で保存ファイルを確認し、未 ignore なら警告する。非 git では skip する。

保存後に、採番したファイルが 1 件だけ存在し、内容に目的・成功条件・scope・非対象・検証・上限停止・完了証拠・完了レポート保存先があることを再読込で確認する。git repo では `git check-ignore` の終了コードも記録する。ファイルパス、ignore 確認、抽出した各項目、下記の起動文を完了証拠として報告する。

## 起動プロンプト出力

```
/goal .claude/goal-runs/YYYY-MM-DD-<slug>-goal.md を読み、記載された成功条件を満たすまで実行する。完了時は成功条件ごとの達成状況、検証コマンドと終了コード、変更ファイル、残課題を会話へ提示する。上限停止: <自動算出した値>。
```

標準は repo 相対パス。別ハーネス版は明示依頼時だけ出し、Claude Code の `/goal` と同じ継続制御があるとは断定しない。`/goal` の実行はユーザーが行う。

## 禁止事項

Goal ファイルと専用 `.gitignore` の作成以外は変更しない。コード実装、PR、commit、push、計画レビュー、独立レビュー、Claude Code 組み込み `/goal` の自動発動、scheduler / loop 登録、thought-db 書き込みを行わない。
