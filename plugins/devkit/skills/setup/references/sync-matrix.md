# 同期表

同期を始める直前に最後まで読む。

全スクリプトの JSON `changed` / `skipped` / `actions` を確認して報告する。

## 共通実行形

`<script>` と `<args>` だけを同期対象表で差し替える。`--no-project` と `--python ">=3.10"` は対象 repo の環境から分離するため必須。2 つの変数は各コマンド実行時に必ず代入する。`TARGET_REPO` は `git -C "<対象>" rev-parse --show-toplevel` で得た git root の絶対パスを使う。`--check` 対応スクリプトは変更予定だけを確認できる。

```bash
SKILL_DIR="<この SKILL.md があるディレクトリの絶対パス>"
TARGET_REPO="<対象リポジトリの絶対パス>"
uv run --no-project --python ">=3.10" python "$SKILL_DIR/scripts/<script>" <args> --format json
```

## 同期対象

| 対象 | `<script>` / `<args>` | 冪等性・保全 | 失敗時 |
|---|---|---|---|
| repo rules | `sync_rules.py --target "$TARGET_REPO" --template "$SKILL_DIR/../../templates/rules/agents-rules.md"` | `AGENTS.md` の `devkit:rules:start` / `devkit:rules:end` 内だけ更新し、`CLAUDE.md` の `@./AGENTS.md` を 1 行化、`.claude/devkit-rules.json` に SHA-256 を記録。外側を保持 | 停止 |
| thought-db | `sync_thought_db.py --template "$SKILL_DIR/../../templates/rules/thought-db-user.md"` | `~/.claude/CLAUDE.md` / `~/.codex/AGENTS.md` の `devkit:thought-db:start` / `devkit:thought-db:end` 内だけ更新し、変更前に backup | `~/repos/thought-db` 不在は skip、その他は記録して継続 |
| updater | `sync_updater.py` | POSIX / Windows の最新版と shim を同期し、旧 updater 名・Windows の旧 `update-ccx.ps1` を prune。`source-root.txt` は変更しない | 記録して継続 |
| 旧 Cursor 資産 | `prune_legacy_cursor_sync.py` | manifest の hash 一致ファイルだけ削除。`skip_prune_modified` / `skip_irregular` は保持し、全完了時だけ manifest 削除 | 記録して継続 |
| compaction env | `sync_claude_env.py` | `~/.claude/settings.json` の他 key を保持し backup 後 atomic replace | 不正 JSON / 型 / symlink / directory は無変更で記録 |
| cursor-agent シム | `sync_cursor_agent_shims.py` | Windows の `%LOCALAPPDATA%\cursor-agent` に `cursor-agent.cmd` / `agent.cmd` を呼ぶ Git Bash shim を同期 | 非 Windows、環境変数不在、未導入は理由付き skip |

repo rules は `version` / 同期時刻 / template SHA-256 を記録する。thought-db 不在は private remote から `~/repos/thought-db` へ配置後の再実行を案内し、blocked にしない。旧 Cursor 資産は `~/.cursor/` または manifest がなければ directory を作らず skip する。Cursor は Claude Code plugin のスキルを読み込むため `.cursor/skills` へ独自同期しない。

## updater の OS 差分

| OS | 管理対象・不変条件 |
|---|---|
| POSIX | `update-ccx.sh` / `devkit-lib.sh` を `~/.codex/bin/`、`update-ccx` shim を `~/.local/bin/` へ同期し、shell script に実行権を付ける |
| Windows | bash 正本チェーン、`update-ccx.cmd` launcher、`devkit-lib.ps1` / `devkit-setup.ps1` / `devkit-codex-config.ps1`、shim を同期。launcher は `HOME`、次に `USERPROFILE` を使い、保存する source root は Windows 絶対 path。bash は旧 POSIX 形式も読む |

Windows updater の PowerShell 責務は Claude Code native installer、Cursor Agent native installer（`https://cursor.com/install?win32=true`）、Codex config templating、v6 migration marker 前の旧日次 task cleanup に限る。Cursor Agent の導入・更新は `update-ccx`（default / `--cli-only`）が行い、Cursor IDE 本体の更新・認証・壊れた launcher の再 install は非対象。

## compaction env の不変条件

管理値は `CLAUDE_CODE_AUTO_COMPACT_WINDOW=1000000` と `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=50`。既存の top-level / `env` key を保持する。project / local / managed scope の同名値が優先されうる。反映確認は `/status` 等で行い、確実な反映には新規セッションを使う。

## 検証とレポート

- `AGENTS.md` の rules marker、thought-db 対象 2 ファイルの marker は各 1 組。
- `CLAUDE.md` の `@./AGENTS.md` は 1 行。
- metadata の `template_sha256` は template と一致。
- updater / Cursor prune / compaction env / shim は changed・no-op・skip・failure と path を区別。
- statusline は installer 結果、font は `status` / `font_installed` / `download` / `settings` / `actions` を報告。
- MISSING、ユーザーが skip した項目、再実行条件を報告。
- マーカー内の手動編集は次回上書きされる。project 固有ルールは外側へ書く。
- 再実行時は最新管理値だけを同期し、最新なら no-op。改変済みの旧 Cursor 資産だけ再判定する。
