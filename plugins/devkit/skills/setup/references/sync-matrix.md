# 同期表

同期を始める直前に最後まで読む。repo-only では repo rules 行だけが実行対象であり、ユーザー環境の行と任意適用は対象外。

選択した範囲のスクリプトの JSON `changed` / `skipped` / `actions` を確認して報告する。

## 共通実行形

repo + ユーザー環境同期の実行形。repo-only は後述の既存 Python による直接実行形を使い、uv の環境準備を起動しない。`<script>` と `<args>` だけを同期対象表で差し替える。`--no-project` と `--python ">=3.10"` は対象 repo の環境から分離するため必須。2 つの変数は各コマンド実行時に必ず代入する。`TARGET_REPO` は `git -C "<対象>" rev-parse --show-toplevel` で得た git root の絶対パスを使う。`--check` 対応スクリプトは変更予定だけを確認できる。

```bash
SKILL_DIR="<この SKILL.md があるディレクトリの絶対パス>"
TARGET_REPO="<対象リポジトリの絶対パス>"
uv run --no-project --python ">=3.10" python "$SKILL_DIR/scripts/<script>" <args> --format json
```

## 同期対象

| 対象 | `<script>` / `<args>` | 冪等性・保全 | 失敗時 |
|---|---|---|---|
| repo rules | `sync_rules.py --target "$TARGET_REPO" --template "$SKILL_DIR/../../templates/rules/agents-rules.md"` | `AGENTS.md` の `devkit:rules:start` / `devkit:rules:end` 内だけ更新し、dual のみ `CLAUDE.md` の `@./AGENTS.md` を 1 行化。`.agents/devkit-rules.json` に SHA-256 と選択を記録。外側を保持 | 停止 |
| thought-db | `sync_thought_db.py --template "$SKILL_DIR/../../templates/rules/thought-db-user.md"` | `~/.claude/CLAUDE.md` / `~/.codex/AGENTS.md` の `devkit:thought-db:start` / `devkit:thought-db:end` 内だけ更新し、変更前に backup | `~/repos/thought-db` 不在は skip、その他は記録して継続 |
| updater | `sync_updater.py` | POSIX / Windows の最新版と shim を同期し、旧 updater 名・Windows の旧 `update-ccx.ps1` を prune。`source-root.txt` は変更しない | 記録して継続 |
| 旧 Cursor 資産 | `prune_legacy_cursor_sync.py` | manifest の hash 一致ファイルだけ削除。`skip_prune_modified` / `skip_irregular` は保持し、全完了時だけ manifest 削除 | 記録して継続 |
| compaction env | `sync_claude_env.py` | `~/.claude/settings.json` の他 key を保持し backup 後 atomic replace | 不正 JSON / 型 / symlink / directory は無変更で記録 |
| cursor-agent シム | `sync_cursor_agent_shims.py` | Windows の `%LOCALAPPDATA%\cursor-agent` に `cursor-agent.cmd` / `agent.cmd` を呼ぶ Git Bash shim を同期 | 非 Windows、環境変数不在、未導入は理由付き skip |

repo rules は `version` / 同期時刻 / template SHA-256 を記録する。thought-db 不在は private remote から `~/repos/thought-db` へ配置後の再実行を案内し、blocked にしない。旧 Cursor 資産は `~/.cursor/` または manifest がなければ directory を作らず skip する。Cursor は Claude Code plugin のスキルを読み込むため `.cursor/skills` へ独自同期しない。

## repo 別の選択と管理先

既存の対象 repo 設定はなかったため、設定だけを `.agents/devkit-rules-config.json` に置く。指示書・転送入口ではなく、スクリプトが読む JSON。作成・変更は対象 repo に対する明示選択の範囲で行い、再同期は保存済みの値を読む。スクリプト自身はこの設定を書き換えない。

```json
{"version": 1, "harness": "codex-only", "policy": "repo-local"}
```

- `harness`: `dual` / `codex-only`。Codex-only はルート `CLAUDE.md` を読み書きせず、`.claude` 内の metadata / backup / state に触れない。既存の入口や保護物も削除・移動しない。
- `policy`: `devkit` / `repo-local`。harness と独立した選択。`devkit` は従来の workflow / review / commit の既定を同期する。管理節外の repo 固有方針・現在のユーザー指示が優先する。`repo-local` はそれらの既定を生成せず、管理節外に方針を委ねる。一律計画承認・必須レビュー・自動 commit/push を再挿入しない。
- 設定がない場合だけ `dual` / `devkit`。設定ありの場合は 3 キーすべて必須。未知キー、重複キー、不正 JSON、型・値・version の不一致は書込み前に失敗する。選択を解除する設定削除は暗黙に行わない。
- 全 harness の metadata は `.agents/devkit-rules.json`（version / 同期時刻 / template SHA-256 / harness / policy）、変更前の AGENTS backup は `.agents/devkit-rules-backup/AGENTS.md.bak`。新規の常設指示書は生成しない。旧 `.claude/devkit-rules.json` と `.claude/devkit-rules-backup/` は読み書き・削除・移動せず保持し、初回に新管理先へ現行結果を記録する。dual の入口・参照正規化・既定規則は維持するが、metadata / backup の参照先は変わる。
- marker 内だけを置換し、外側の本文を保持する。backup は直前の AGENTS 全文を含むため自動公開しない。新管理先の同名 backup は次の実変更時に更新する。設定は repo で共有可能だが、metadata / backup の追跡・除外は repo 方針で選ぶ（gitignore 自動編集はしない）。
- 不正 marker、設定、不規則パス（symlink / directory）は backup を含む書込み前に検出して停止する。Codex-only で非対象の CLAUDE / `.claude` は検査もしない。I/O 障害や実行中の並行変更に対する複数ファイル transaction は保証しない。
- `--dry-run` は `sync_rules.py` の変更予定だけを出し、repo・metadata・backup・ユーザー環境を書き換えない。初回も再実行も指定できる。skill の repo-only dry-run では同スクリプトに渡し、他の同期を実行しない。
- 同梱 template は policy 区画から選択した本文だけを出力する。従来の独自 template は `devkit` のみ継続対応し、policy 区画がない独自 template に `repo-local` を指定した場合は無変更で停止する。

repo-only の直接実行例（既存の Python 3.10 以上を使い、setup / update 全体は起動しない）:

```bash
RULES_PYTHON="<既存の Python 3.10 以上の実行ファイル絶対パス>"
"$RULES_PYTHON" "<配布済み skill>/scripts/sync_rules.py" --target "<対象 repo>" --template "<配布済み plugin>/templates/rules/agents-rules.md" --dry-run --format json
```

適用承認後に `--dry-run` だけを外して実行し、同じ引数でもう一度実行して `changed=false` / `actions=[]` を確認する。元の依頼が適用まで許可していれば追加承認は不要。

## updater の OS 差分

| OS | 管理対象・不変条件 |
|---|---|
| POSIX | `update-ccx.sh` / `devkit-lib.sh` を `~/.codex/bin/`、`update-ccx` shim を `~/.local/bin/` へ同期し、shell script に実行権を付ける |
| Windows | bash 正本チェーン、`update-ccx.cmd` launcher、`devkit-lib.ps1` / `devkit-setup.ps1` / `devkit-codex-config.ps1`、shim を同期。launcher は `HOME`、次に `USERPROFILE` を使い、保存する source root は Windows 絶対 path。bash は旧 POSIX 形式も読む |

Windows updater の PowerShell 責務は Claude Code native installer、Cursor Agent native installer（`https://cursor.com/install?win32=true`）、Codex config templating、v6 migration marker 前の旧日次 task cleanup に限る。Cursor Agent の導入・更新は `update-ccx`（default / `--cli-only`）が行い、Cursor IDE 本体の更新・認証・壊れた launcher の再 install は非対象。

## compaction env の不変条件

管理値は `CLAUDE_CODE_AUTO_COMPACT_WINDOW=1000000` と `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=50`。既存の top-level / `env` key を保持する。project / local / managed scope の同名値が優先されうる。反映確認は `/status` 等で行い、確実な反映には新規セッションを使う。

## 検証とレポート

- `AGENTS.md` の rules marker は 1 組。thought-db はユーザー環境同期を選択した場合だけ対象 2 ファイルを確認。
- dual のみ `CLAUDE.md` の `@./AGENTS.md` は 1 行。Codex-only は新規生成なし・既存 CLAUDE / `.claude` 無変更を確認。
- `.agents/devkit-rules.json` の `template_sha256` は template と一致し、harness / policy は選択と一致。
- updater / Cursor prune / compaction env / shim は changed・no-op・skip・failure と path を区別。
- statusline は installer 結果、font は `status` / `font_installed` / `download` / `settings` / `actions` を報告。
- MISSING、ユーザーが skip した項目、再実行条件を報告。
- マーカー内の手動編集は次回上書きされる。project 固有ルールは外側へ書く。
- 再実行時は最新管理値だけを同期し、最新なら no-op。改変済みの旧 Cursor 資産だけ再判定する。

## 既存更新計画との境界（D1 / D2 / L1）

[business-docs #17 の D1 計画](https://github.com/murakotaro4/business-docs/pull/17) はこの repo rules の source 対応。マシン全体の updater 選択や配布を実装したことにはならない。

[business-docs #14](https://github.com/murakotaro4/business-docs/issues/14) と [devkit #53](https://github.com/murakotaro4/devkit/issues/53) の整合案は、repo の harness と別にマシン側の更新 component を明示選択し、CLI / plugin / version probe / success marker / health check を選択集合に揃えること。明示的な対象外と、選択した対象の失敗・lock・timeout・skip を区別し、後者は成功扱いしない。#53 の書込み前 preflight・trusted source・共有 lock・厳格な成否・no-op backup 抑制は維持する。Codex-only 選択と unattended 契約が実装・配布されるまでは、#14 の現行 Codex npm 更新経路を切り替えない。Issue 本文の更新、updater 実装、Scheduler / Automation の変更は別作業。

配布後の business-docs 確認は別承認で行う: (1) 適用対象 checkout の HEAD・既存差分・AGENTS 管理節外の権限と、配布済み script / template の版・内容を確認、(2) 同 repo の設定を codex-only / repo-local として明示保存、(3) repo-only の dry-run で変更先が AGENTS と新管理先だけか確認、(4) 許可された適用後、既存 CLAUDE / `.claude` 保護物と管理節外が無変更か確認、(5) 2 回目が no-op か確認、(6) 新規 Codex セッションで AGENTS の読込元と承認・レビュー・Git 境界を確認する。保護物の内容を外部公開せず、旧 metadata の削除や実 checkout の強制同期をしない。source テストの PASS と実環境の再生成解消は別の完了状態として報告する。
