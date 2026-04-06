# devkit/scripts

補助スクリプト置き場。

## Harness

- 品質ゲートの標準入口は `uv` を使う。
- repo ルートからの手動実行:
  - `uv sync --project plugins/devkit --group dev`
  - `uv run --project plugins/devkit python plugins/devkit/scripts/devkit_harness.py verify-fast`
  - `uv run --project plugins/devkit python plugins/devkit/scripts/devkit_harness.py verify-full`
- pytest テスト単独実行:
  - `uv run --project plugins/devkit --group dev pytest plugins/devkit/tests/ -v`
- devkit repo の Git hook 標準は `prek.toml`。
- `prek` と Claude hook も同じ Python ハーネスを呼び出す。
- `check_utf8_bom.py` は `pre-commit` では staged docs/config、`verify-fast` / `verify-full` では repo 全体の UTF-8 BOM を弾く。
- `node` / `npm` / `fnm` は外部 CLI 更新用にのみ残し、repo 内の check / hook は使わない。
- Claude hook は `node` launcher 経由で `uv` を優先し、未導入時は system Python へ fallback する。

### hook / gate の block 昇格

- `pre-push` gate は `origin/main` と同じ plugin version のままなら push を block する。
- `dig-claude` の計画レビュー（REVIEW_GATE_PLAN）は3 回目の失敗（`plan_review_attempts >= 3`）で `DIG_CLAUDE_REVIEW_BLOCKED` で commit/push を block する。block 解除には計画の根本修正が必要。
- `dig-codex` の Phase 4 は fail-close。レビュー不能時は `DIG_CODEX_PLAN_REVIEW_UNAVAILABLE`、`critical>0` または `high>0` の場合は `DIG_CODEX_PLAN_REVIEW_BLOCKED` で停止する。
- `check_dig_routing.py` は `dig-cursor` を含む runtime 参照整合（`dig` orchestrator / adapter / rerun 契約）を検証する。

## repo_maintainer.py

cross-repo nightly maintainer の共通 runner。

### 役割

- temp worktree で Codex を起動して repo 保全更新を行う
- `.devkit/repo-maintainer.toml` を読んで lane / phase / allowed paths を強制する
- AI review / local checks / GitHub PR / auto-merge を実行する
- target repo の `logs/skills/` と `reviews/` を更新する

### サブコマンド

```bash
python plugins/devkit/scripts/repo_maintainer.py init-scaffold --repo /path/to/repo
python plugins/devkit/scripts/repo_maintainer.py run --repo /path/to/repo
```

`init-scaffold` が target repo に生成するもの:

- `.devkit/repo-maintainer.toml`
- `MEMORY.md`
- `logs/skills/`
- `reviews/daily/`
- `reviews/weekly/`
- `.devkit/bin/repo-maintainer.{ps1,sh}`
- `.devkit/scheduler/` 配下の OS 別 template

`run` の補足:

- branch 名は `codex/maint/<yyyymmdd>-<lane>`
- PR title は `[repo-maintainer] ...`
- `review_commands` / `check_commands` 未通過時も PR までは作るが、auto-merge はしない

## update-devkit / update-ccx

`update-devkit` が主名称。`update-ccx` は互換 alias。
OpenSkills ベースの install / update は primary flow から外し、継続更新はこのコマンドを使う。

### 対応範囲

- Claude Code / Codex CLI / OpenCode の install / update
- Codex / OpenCode の DevKit 管理 user-level assets の再同期
- Codex / OpenCode の退役した DevKit 管理 skill link の掃除
- project `AGENTS.md` / `CLAUDE.md` workflow sync は対象外

### Shared DevKit source

- DevKit source: その環境で使う DevKit checkout
- この環境の例: `~/cursor/devkit`
- Codex の公開 skill: `~/.agents/skills`
- OpenCode の公開 skill: `~/.config/opencode/skills`

skills / commands / helper / templates は、その環境で選ばれた DevKit source から同期する。
Codex の公開 skill は `~/.agents/skills` へ、OpenCode の公開 skill は `~/.config/opencode/skills` へ同期する。
Codex / OpenCode へ同期する top-level skill は公開入口に限定し、`dig-core` などの internal adapter は DevKit source 側に残して `dig` から相対参照する。
`DEVKIT_SOURCE_ROOT` を設定しない場合は、直接実行した checkout または保存済みの `source-root.txt` を優先して再利用する。

### Windows (PowerShell / cmd)

初回 bootstrap は Marketplace の `devkit-setup.ps1` を使う。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "$HOME\.claude\plugins\marketplaces\murakotaro4\plugins\devkit\scripts\devkit-setup.ps1" -RegisterDailyTask
```

以降の更新:

```powershell
update-devkit
update-devkit --version
update-ccx
```

補足:

- 既存ユーザーは launcher 更新のために `devkit-setup.ps1` を 1 回再実行しておくと安全。
- PowerShell / cmd 版は install 済み script から保存済みの DevKit source を参照して同期する。

### それ以外のシェル

初回だけは checkout または Marketplace 配下の script を直接実行し、その後はインストール済みの `update-devkit` を使う。checkout からの初回実行ではその checkout を shared source として保存する。Marketplace bootstrap では `DEVKIT_SOURCE_ROOT` または環境の既定 clone 先へ clone してから進む。`update-ccx` でも同じ挙動を呼べる。

```bash
bash ./plugins/devkit/scripts/update-devkit.sh --devkit-only

# 以降
update-devkit
update-devkit --version
```

この初回実行で `~/.codex/bin` に managed script が配置され、`~/.local/bin/update-devkit` と `update-ccx` がそこを呼ぶ。clone / update に失敗した場合は snapshot へ fallback せず停止する。

### Windows の npm 自己修復

PowerShell / cmd 版は、active/default の fnm 管理 Node から `npm` が消えている場合、更新前に同じ Node バージョンの自己修復を 1 回試す。

流れ:

1. Setup で `npm` の欠落を検知
1. `fnm install <current-version>` と `fnm default <current-version>` を実行
1. まだ `npm` が戻らない場合は壊れた install root を `.update-ccx-broken.<timestamp>` として退避し、同じバージョンを再取得
1. 失敗時は npm 系の更新を `SKIPPED` にし、診断エラーを 1 件だけ出す

補足:

- 別の Node バージョンには自動切替しない
- `other_npm_ready_versions=` は手動復旧候補

### Windows の Codex 自動移行

PowerShell / cmd 版は、`%USERPROFILE%\.npmrc` に次の legacy prefix がある場合だけ Codex を自動移行する。

```text
prefix=C:\Users\<username>\.npm-global
```

実行内容:

1. `~/.npmrc.update-ccx.bak.<timestamp>` を作成
1. legacy prefix から `@openai/codex` を uninstall
1. `.npmrc` から上記 `prefix=` 行だけ削除
1. 現在の Windows npm global prefix (`npm config get prefix`) に `@openai/codex` を再 install
1. その prefix が user PATH に無ければ先頭へ追加

注意点:

- 上記以外の custom prefix は自動書き換えしない。手動確認が必要というエラーで停止する
- 既存の standalone `codex.exe` は削除しない
- `where.exe codex` に複数候補が残る場合は warning を出す
- Windows で実行中の `codex.exe` がロックされている場合、Codex CLI 自己更新は warning 付きで `SKIPPED` になる

### 自動検出

| ツール | 検出方針 | 更新コマンド |
|--------|----------|--------------|
| Claude Code (native) | `claude update --help` と配置パス | `claude update` |
| Claude Code (npm) | npm / fnm 系パス | `npm update -g @anthropic-ai/claude-code` |
| Codex CLI (npm) | `Get-Command codex` の優先結果 + `where.exe codex` | `npm install -g @openai/codex` |
| opencode (npm) | npm / fnm 系パス | `npm install -g opencode-ai` |

`--runtime codex|opencode` を使うと、その runtime の CLI と user-level assets だけを更新する。

### トラブルシューティング

#### `update-devkit` / `update-ccx` が見つからない

- PATH を確認する
- PowerShell / cmd は Marketplace の `devkit-setup.ps1` を再実行して launcher を再配置する
- shell は初回 bootstrap を script 直接実行で 1 回済ませる

#### Windows で Codex 移行が止まる

- `%USERPROFILE%\.npmrc` に想定外の `prefix=` がないか確認する
- 移行対象は `C:\Users\<username>\.npm-global` だけ
- 失敗時は `~/.npmrc.update-ccx.bak.<timestamp>` から戻せる

#### `BLOCKED_LEGACY_SKILLS_ROOT` で止まる

- `~/.agent/skills` に DevKit 以外の custom skill が混在している
- custom skill を退避してから `update-devkit --runtime opencode --devkit-only` を再実行する

#### Windows で npm が見つからない

- PowerShell / cmd 版は同じ Node バージョンの自己修復を 1 回試す
- 失敗時は `install_root=` と `expected_npm=` を確認する
- `other_npm_ready_versions=` は手動で `fnm default <version>` する際の候補
- 自動で別バージョンへは切り替えない

#### `where.exe codex` に複数候補が出る

- `fnm` 管理の Codex と standalone `codex.exe` が混在している
- `update-devkit` / `update-ccx` は standalone 側を削除しない
- PATH の優先順位を見直して、fnm 管理側が先に解決されるようにする
