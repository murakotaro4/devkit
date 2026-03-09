# devkit/scripts

補助スクリプト置き場。

## Harness

- 品質ゲートの標準入口は `uv` を使う。
- repo ルートからの手動実行:
  - `uv sync --project plugins/devkit`
  - `uv run --project plugins/devkit python plugins/devkit/scripts/devkit_harness.py verify-fast`
  - `uv run --project plugins/devkit python plugins/devkit/scripts/devkit_harness.py verify-full`
- `prek` と Claude hook も同じ Python ハーネスを呼び出す。

## update-devkit / update-ccx

`update-devkit` が主名称。`update-ccx` は互換 alias。
OpenSkills ベースの install / update は primary flow から外し、継続更新はこのコマンドを使う。

### 対応範囲

- Claude Code / Codex CLI / OpenCode の install / update
- Codex / OpenCode の DevKit 管理 user-level assets の再同期
- project `AGENTS.md` / `CLAUDE.md` workflow sync は対象外

### Runtime-local source root

- Codex: `~/.codex/devkit/source`
- OpenCode: `~/.config/opencode/devkit/source`

skills / commands / helper / templates は各 runtime の source root から直接同期する。

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
- PowerShell / cmd 版は install 済み script から Codex / OpenCode の runtime-local source root を更新する。

### それ以外のシェル

更新はインストール済みの `update-devkit` を使う。`update-ccx` でも同じ挙動を呼べる。

```bash
update-devkit
update-devkit --version
```

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

### 自動検出

| ツール | 検出方針 | 更新コマンド |
|--------|----------|--------------|
| Claude Code (native) | `claude update --help` と配置パス | `claude update` |
| Claude Code (npm) | npm / fnm 系パス | `npm update -g @anthropic-ai/claude-code` |
| Codex CLI (npm) | `Get-Command codex` の優先結果 + `where.exe codex` | `npm install -g @openai/codex` |
| opencode (npm) | npm / fnm 系パス | `npm install -g opencode-ai` |

### トラブルシューティング

#### `update-devkit` / `update-ccx` が見つからない

- PATH を確認する
- PowerShell / cmd は Marketplace の `devkit-setup.ps1` を再実行して launcher を再配置する

#### Windows で Codex 移行が止まる

- `%USERPROFILE%\.npmrc` に想定外の `prefix=` がないか確認する
- 移行対象は `C:\Users\<username>\.npm-global` だけ
- 失敗時は `~/.npmrc.update-ccx.bak.<timestamp>` から戻せる

#### Windows で npm が見つからない

- PowerShell / cmd 版は同じ Node バージョンの自己修復を 1 回試す
- 失敗時は `install_root=` と `expected_npm=` を確認する
- `other_npm_ready_versions=` は手動で `fnm default <version>` する際の候補
- 自動で別バージョンへは切り替えない

#### `where.exe codex` に複数候補が出る

- `fnm` 管理の Codex と standalone `codex.exe` が混在している
- `update-devkit` / `update-ccx` は standalone 側を削除しない
- PATH の優先順位を見直して、fnm 管理側が先に解決されるようにする
