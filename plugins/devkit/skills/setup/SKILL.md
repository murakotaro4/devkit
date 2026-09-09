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

## 同期範囲

`/setup --repo-only [target]` または「repo rulesだけ」「ルール同期だけ」の依頼は **repo-only** として扱う。この場合は下記の repo 前提を確認し、同期表の `repo rules` 行（`sync_rules.py`）だけを実行して検証・報告後に終了する。thought-db、updater、prune、Claude 環境変数、shim、statusline、font は実行しない。ユーザー環境用の環境前提チェックも実行しない。Python 3.10 以上と git だけが必要で、既存 Python でスクリプトを直接実行できる。`--repo-only` は skill の振り分け引数であり、スクリプトの引数ではない。

引数なしの `/setup` は従来の repo + ユーザー環境同期を維持する。ただしユーザーが指定した範囲が最優先。Codex-only は対象 repo の生成対象を選ぶ設定であり、ユーザー環境同期の許可やマシン全体の Claude 廃止を意味しない。repo 設定を理由にユーザー環境への操作範囲を拡張しない。

## 実行前提

対象は `$ARGUMENTS` から `--repo-only` / `--dry-run` を除いた target、なければ cwd の git root。テンプレートは `SKILL_DIR/../../templates/rules/agents-rules.md`。repo 別の選択は `.agents/devkit-rules-config.json`（同期表参照）を読み、未設定時は dual / devkit とする。設定作成・変更はユーザーが選択した範囲だけ行い、起動した親ハーネスから推測しない。テンプレート不足、非 git repo、または `plugins/devkit/.claude-plugin/plugin.json` がある DevKit repo 自身なら変更せず停止する。

repo + ユーザー環境同期の場合だけ、同期前に [環境と任意適用](references/environment.md) の「環境前提チェック」だけを読み、`claude` / `codex` / `cursor-agent` / `node` / `uv` の可否と影響を確定する。`uv` が無ければ同期前に停止する。他の不足は同文書の表に従って継続・skip を分ける。インストール自体は行わない。

## 同期

同期を始める直前に [同期表](references/sync-matrix.md) を最後まで読み、共通実行形、各スクリプトの引数、保全条件、失敗時の扱い、OS 差分、compaction env の不変条件を適用する。選択した範囲のスクリプトの JSON `changed` / `skipped` / `actions` を確認する。

通常の同期・prune に差分承認ゲートは置かない。承認が必要なのは statusline と Windows Terminal font だけ。適用直前に [環境と任意適用](references/environment.md) の該当節を読み、check の差分を提示して選択肢付き質問で承認を得る。

## 検証と完了報告

検証直前に [同期表](references/sync-matrix.md) の「検証とレポート」を読む。changed・no-op・skip・failure と path、MISSING、ユーザーが skip した項目、再実行条件を区別して報告する。statusline と font も最新なら no-op とし、不要な backup や再設定を増やさない。commit / push は対象 repo の `AGENTS.md` に従う。
