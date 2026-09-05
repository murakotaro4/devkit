---
name: "repo-loop"
description: "手動・定期・イベント起点で改善を1件選び、Draft PRか提案Issueまで進める。『リポジトリを自動改善して』『定期メンテナンスして』『CI failureを直して』『/repo-loop』で起動"
argument-hint: "[objective or repo-loop/v1 trigger envelope]"
---

# /repo-loop - リポジトリ自律改善ループ

trigger と最新のリポジトリ状態から、価値が高く安全で検証可能な改善を 1 件だけ選ぶ。low / medium risk は専用 worktree で実装・検証・独立レビューを行い、事前承認なしで Draft PR まで進める。high risk は提案 Issue へ降格する。ready 化・merge・auto-merge は行わない。

## 対象

$ARGUMENTS

## ハーネス判定

`AGENTS.md`「スキル共通契約」に従う。`request_user_input` は判定キーに使わない。

| 親 | 判定 | 手動実行の重大な質問 | 進捗 |
|---|---|---|---|
| Claude 親 | `AskUserQuestion` が使える | `AskUserQuestion` | 外部 CLI は `run_in_background`、完了自動通知と TaskOutput で回収 |
| Codex 親 | 上記がなく `spawn_agent` が使える | plan mode は `request_user_input`、通常 mode は選択肢 + 自由文 | 黙って待たず定期報告 |
| 判定不能 | どちらもない | 選択肢 + 自由文 | 利用可能な手段で報告 |

非対話実行では質問しない。手動でも成功条件・安全性・外部影響を変える不明点だけ質問する。委譲・長時間ジョブは 1 ジョブ = 1 タスクとし、実体は `git status` / `git diff`、停滞は出力増分で判断する。

## dig / refactor / backlog との境界

repo-loop は課題を自選し、low / medium risk を Draft PR へ運ぶ。dig はユーザー要求起点で計画承認後に統合まで完遂する。repo-loop から dig を自動呼び出さない。refactor / backlog は read-only の棚卸しであり、repo-loop は今回の 1 件を選ぶ範囲だけ調査する。

## 入力契約

自然文を既定とし、外部 loop・scheduler・event からは次の envelope も受け付ける。runtime や schema validator は追加しない。

```json
{
  "schema": "repo-loop/v1",
  "trigger": {
    "type": "manual | schedule | event",
    "name": "ci_failure | issue | pull_request | push | security | custom",
    "id": "",
    "url": "",
    "summary": ""
  },
  "objective": "",
  "scope": [],
  "proposal_only": false
}
```

必須は `trigger.type` だけ。選定を始める直前に [選定と計画](references/selection.md) を読み、trigger 差分、信頼境界、1件選定、risk、出口を確定する。`schedule` / `event`、または定期・夜間・CI 起動等が明記された入力は非対話とする。

## 実装から完了まで

low / medium risk の実装を始める直前に [実装と公開](references/delivery.md) を最後まで読む。worktree、baseline、検証、秘密検査、独立レビュー、公開、重複防止、RECORD、cleanup の順序と停止条件を変更しない。

すべての終端は RECORD を通る。状態は論理状態であり、ファイルや DB へ永続化しない。起動は契約内の branch・編集・検証・commit・push・Draft PR・提案・失敗 Issue を許可するが、merge・auto-merge・ready 化・force push・default branch への直接 push・deploy・release・secrets / permissions / repository settings・destructive operation は許可しない。Draft PR / 提案・失敗 Issue 以外の publish も許可しない。
