---
name: "setup"
description: "対象リポジトリへ DevKit 標準ルールを、ユーザー環境へ updater・compaction env・cursor-agent シムを同期し旧 updater 名と Cursor 同期資産の残骸を prune する。「セットアップして」「ルール同期して」「/setup」で起動"
argument-hint: "[target]"
allowed-tools: ["Read", "Grep", "Glob", "Bash", "Write", "Edit", "AskUserQuestion", "request_user_input", "TaskCreate", "TaskUpdate"]
---

# /setup

対象 repo へ DevKit 標準ルールを、ユーザー環境へ thought-db 接続・updater・compaction env・cursor-agent シムを冪等同期する。旧 updater 名と Cursor 同期資産を安全に prune し、Claude 親では statusline、Windows では Windows Terminal の UDEV Gothic NF を必要に応じて適用する。Cursor は Claude Code plugin のスキルを読み込むため、`.cursor/skills` への独自同期は行わない。

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

### 環境前提チェック

`command -v` で `claude` / `codex` / `cursor-agent` / `node` / `uv` を確認し、OK / MISSING と影響を報告する。インストール自体は行わない。

| MISSING | 影響 |
|---|---|
| `uv` | 必須同期と Windows font を実行できないため、同期前に停止。macOS は `brew install uv`、Windows は `winget install --id astral-sh.uv` |
| `node` | statusline だけ skip。他の同期と font は継続。必要なら `brew install node` |
| `claude` | goal-prompt の `/goal` 実行環境がない。同期は継続 |
| `codex` | dig の実装・計画レビュー・diff レビュー backend が使えない。同期は継続 |
| `cursor-agent` | dig の任意高速 lane が使えない。同期は継続 |

## 同期

共通実行形は次の 1 つ。`<script>` と `<args>` だけを下表で差し替える。`--no-project` と `--python ">=3.10"` は対象 repo の環境から分離するため必須。

2 つの変数は各コマンド実行時に必ず代入する。シェル変数は呼び出し間で失われるため、同じブロック内で代入する。`TARGET_REPO` は `git -C "<対象>" rev-parse --show-toplevel` で得た repo root を使う。

```bash
SKILL_DIR="<この SKILL.md があるディレクトリの絶対パス>"
TARGET_REPO="<対象リポジトリの絶対パス>"
uv run --no-project --python ">=3.10" python "$SKILL_DIR/scripts/<script>" <args> --format json
```

全スクリプトの JSON `changed` / `skipped` / `actions` を確認して報告する。`--check` 対応スクリプトは変更予定だけを確認できる。

| 対象 | `<script>` / `<args>` | 冪等性・保全 | 失敗時 |
|---|---|---|---|
| repo rules | `sync_rules.py --target "$TARGET_REPO" --template "$SKILL_DIR/../../templates/rules/agents-rules.md"` | `AGENTS.md` の `devkit:rules:start` / `devkit:rules:end` だけ更新し、`CLAUDE.md` の `@./AGENTS.md` を 1 行化、`.claude/devkit-rules.json` に SHA-256 を記録。外側を保持 | 停止 |
| thought-db | `sync_thought_db.py --template "$SKILL_DIR/../../templates/rules/thought-db-user.md"` | `~/.claude/CLAUDE.md` / `~/.codex/AGENTS.md` の `devkit:thought-db:start` / `devkit:thought-db:end` だけ更新し、変更前に backup | `~/repos/thought-db` 不在は skip、その他は記録して後続継続 |
| updater | `sync_updater.py` | POSIX / Windows の最新版と shim を同期し、旧 updater 名・Windows の旧 `update-ccx.ps1` を prune。`source-root.txt` は変更しない | 記録して後続継続 |
| 旧 Cursor 資産 | `prune_legacy_cursor_sync.py` | manifest の hash 一致ファイルだけ削除。`skip_prune_modified` / `skip_irregular` は保持し、全完了時だけ manifest 削除 | 記録して後続継続 |
| compaction env | `sync_claude_env.py` | `~/.claude/settings.json` の他 key を保持し backup 後 atomic replace | 不正 JSON / 型 / symlink / directory は無変更で記録 |
| cursor-agent シム | `sync_cursor_agent_shims.py` | Windows の `%LOCALAPPDATA%\cursor-agent` に `cursor-agent.cmd` / `agent.cmd` を呼ぶ Git Bash shim を同期 | 非 Windows、環境変数不在、未導入は理由付き skip |

repo rules は `version` / 同期時刻 / template SHA-256 を記録する。thought-db がない場合は private remote から `~/repos/thought-db` へ配置後の再実行を案内するが、blocked にしない。旧 Cursor 資産は `~/.cursor/` または manifest がなければ directory を作らず skip する。

### updater の OS 差分

| OS | 管理対象・不変条件 |
|---|---|
| POSIX | `update-ccx.sh` / `devkit-lib.sh` を `~/.codex/bin/`、`update-ccx` shim を `~/.local/bin/` へ同期し、shell script に実行権を付ける |
| Windows | bash 正本チェーン、`update-ccx.cmd` launcher、`devkit-lib.ps1` / `devkit-setup.ps1` / `devkit-codex-config.ps1`、shim を同期。launcher は `HOME`、次に `USERPROFILE` を使い、保存する source root は Windows 絶対 path。bash は旧 POSIX 形式も読む |

Windows updater の PowerShell 責務は Claude Code native installer、Cursor Agent native installer（`https://cursor.com/install?win32=true`）、Codex config templating、v6 migration marker 前の旧日次 task cleanup に限る。Cursor Agent の導入・更新は `update-ccx`（default / `--cli-only`）が行い、Cursor IDE 本体の更新・認証・壊れた launcher の再 install は非対象。

### compaction env の不変条件

管理値は `CLAUDE_CODE_AUTO_COMPACT_WINDOW=1000000` と `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=50`。既存の top-level / `env` key を保持する。project / local / managed scope の同名値が優先されうる。反映確認は `/status` 等で行い、確実な反映には新規セッションを使う。

## 承認が必要な適用

通常の同期・prune に差分承認ゲートは置かない。承認が必要なのは statusline と Windows Terminal font だけ。

### statusline 適用

Claude 親かつ `node` がある場合だけ適用する。check と apply は別のシェル呼び出しになり変数が持ち越されないため、毎回 `SKILL_DIR` を代入する。

```bash
SKILL_DIR="<この SKILL.md があるディレクトリの絶対パス>"
node "$SKILL_DIR/../../statusline/install.js" --check
```

差分を提示し、選択肢付き質問で承認後に適用する。DevKit 管理済み / 未導入は `--check` を外した同形、他設定との競合は上書きを追加確認して末尾に `--force` を付けた同形を使う（いずれも `SKILL_DIR` の代入を含める）。Codex 親・判定不能・node 不在は理由付き skip。

### ターミナルフォント適用(Windows のみ)

非 Windows は skip。Windows は次を確認し、選択肢付き質問で承認後、同じコマンドから `--check` だけ外して適用する。

```bash
SKILL_DIR="<この SKILL.md があるディレクトリの絶対パス>"
uv run --no-project --python ">=3.10" python "$SKILL_DIR/scripts/setup_terminal_font.py" --check --format json
```

ダウンロード失敗、SHA-256 不一致、font 未登録、Windows Terminal 未検出は案内のみで setup 全体を止めない。font 未検出時は settings.json を書かない。

### 検証とレポート

次の不変条件と各 JSON 結果を確認する。

- `AGENTS.md` の rules marker、thought-db 対象 2 ファイルの marker は各 1 組。
- `CLAUDE.md` の `@./AGENTS.md` は 1 行。
- metadata の `template_sha256` は template と一致。
- updater / Cursor prune / compaction env / shim は changed・no-op・skip・failure と path を区別。
- statusline は installer 結果、font は `status` / `font_installed` / `download` / `settings` / `actions` を報告。
- MISSING、ユーザーが skip した項目、再実行条件を報告。
- statusline と font も管理値が最新なら no-op とし、不要な backup や再設定を増やさない。

## 注意

- マーカー内の手動編集は次回上書きされる。project 固有ルールは外側へ書く。
- 再実行時は最新管理値だけを同期し、最新なら no-op。改変済みの旧 Cursor 資産だけ次回も再判定する。
- commit / push は対象 repo の `AGENTS.md` に従う。
