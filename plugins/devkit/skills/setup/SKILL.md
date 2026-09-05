---
name: "setup"
description: "DevKitのルールを対象リポジトリへ、利用資産をユーザー環境へ同期する。『セットアップして』『ルール同期して』『/setup』で起動"
argument-hint: "[target]"
allowed-tools: ["Read", "Grep", "Glob", "Bash", "Write", "Edit", "AskUserQuestion", "request_user_input", "TaskCreate", "TaskUpdate"]
---

# /setup

対象 repo へ標準ルールを、ユーザー環境へ thought-db 接続・updater・compaction env・cursor-agent シムを冪等同期する。旧 updater 名と Cursor 同期資産を安全に prune し、必要な環境だけ statusline と Windows Terminal font を適用する。

## トピック ($ARGUMENTS)

$ARGUMENTS

## ハーネス判定

`AGENTS.md`「スキル共通契約」に従う。`request_user_input` は判定キーに使わない。

| 親 | 判定 | 質問 | statusline | Windows font |
|---|---|---|---|---|
| Claude 親 | `AskUserQuestion` が使える | `AskUserQuestion` | 対象 | 対象 |
| Codex 親 | 上記がなく `spawn_agent` が使える | plan mode は `request_user_input`、通常 mode は選択肢 + 自由文 | 対象外 | 対象 |
| 判定不能 | どちらもない | 選択肢 + 自由文 | 対象外 | 対象 |

## 実行前提

対象は `$ARGUMENTS`、なければ cwd の git root。テンプレートは `SKILL_DIR/../../templates/rules/agents-rules.md`。不足、非 git repo、または `plugins/devkit/.claude-plugin/plugin.json` がある DevKit repo 自身なら変更せず停止する。

同期前に [環境と任意適用](references/environment.md) の「環境前提チェック」だけを読み、`claude` / `codex` / `cursor-agent` / `node` / `uv` の可否と影響を確定する。`uv` が無ければ同期前に停止する。他の不足は同文書の表に従って継続・skip を分ける。インストール自体は行わない。

## 同期

同期を始める直前に [同期表](references/sync-matrix.md) を最後まで読み、共通実行形、各スクリプトの引数、保全条件、失敗時の扱い、OS 差分、compaction env の不変条件を適用する。全スクリプトの JSON `changed` / `skipped` / `actions` を確認する。

通常の同期・prune に差分承認ゲートは置かない。承認が必要なのは statusline と Windows Terminal font だけ。適用直前に [環境と任意適用](references/environment.md) の該当節を読み、check の差分を提示して選択肢付き質問で承認を得る。

## 検証と完了報告

検証直前に [同期表](references/sync-matrix.md) の「検証とレポート」を読む。changed・no-op・skip・failure と path、MISSING、ユーザーが skip した項目、再実行条件を区別して報告する。statusline と font も最新なら no-op とし、不要な backup や再設定を増やさない。commit / push は対象 repo の `AGENTS.md` に従う。
