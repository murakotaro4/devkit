# devkit/scripts

補助スクリプト置き場。

## update-ccx

Claude Code、Codex CLI、opencode をまとめて install / update する。

### 入口

| 環境 | 推奨コマンド | 補足 |
|------|--------------|------|
| Windows (PowerShell / cmd) | `update-ccx` | setup 後は `~/.local/bin/update-ccx.cmd` shim からどこでも呼べる |
| Windows (Git Bash / WSL) | `update-ccx.sh` | `.sh` は LF 固定。Git Bash / WSL から直接使う |
| macOS / Linux | `update-ccx.sh` | 既存の bash 入口 |

> `devkit-setup.ps1` は Codex 向けスキル配置・設定同期用。ただし Windows では `update-ccx` の shim 配置もここで行う。

### 対応内容

| 環境 | Claude Code | Codex CLI | opencode |
|------|-------------|-----------|----------|
| Windows (PowerShell / cmd) | native / npm | npm / legacy prefix migration | npm |
| Windows (Git Bash) | native / npm | npm (fnm 対応) | npm (fnm 対応) |
| WSL | native / npm | npm | npm |
| macOS | Homebrew Cask / npm / native | Homebrew / npm | Homebrew / npm |
| Linux | native / npm | npm | npm |

### Windows での使い方

`devkit-setup.ps1` 実行済みなら、PowerShell / cmd からどこでも:

```cmd
update-ccx
update-ccx --version
```

Windows の bare `update-ccx` は `~/.codex/devkit/source-root.txt` に記録された DevKit checkout の `scripts\update-ccx.ps1` を優先し、解決できない場合だけ `~/.codex/bin\update-ccx.ps1` を使う。
既存ユーザーがこの launcher 挙動へ追随するには、`devkit-skill-update.ps1` または `devkit-setup.ps1` を 1 回再実行して `~/.codex/bin/update-ccx.cmd` を更新する必要がある。

setup 前、または shim が未配置の場合:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "$HOME\.claude\plugins\marketplaces\murakotaro4\plugins\devkit\scripts\update-ccx.ps1" --version
& "$HOME\.claude\plugins\marketplaces\murakotaro4\plugins\devkit\scripts\update-ccx.cmd"
```

### Windows の npm 自己修復

PowerShell / cmd 版は、active/default の fnm 管理 Node から `npm` が消えている場合、更新前に同じ Node バージョンの自己修復を 1 回試す。

流れ:

1. Setup で `npm` の欠落を検知
2. `fnm install <current-version>` と `fnm default <current-version>` を実行
3. まだ `npm` が戻らない場合は壊れた install root を `.update-ccx-broken.<timestamp>` として退避し、同じバージョンを再取得
4. 失敗時は npm 系の更新を `SKIPPED` にし、診断エラーを 1 件だけ出す

補足:

- 別の Node バージョンには自動切替しない
- `other_npm_ready_versions=` は手動復旧候補

### Git Bash / WSL / Unix の使い方

```bash
# PATH を追加
echo 'export PATH="$HOME/.claude/plugins/marketplaces/murakotaro4/plugins/devkit/scripts:$PATH"' >> ~/.bashrc
source ~/.bashrc

# 実行
update-ccx.sh
update-ccx.sh --version
update-ccx.sh -v
```

macOS の zsh は `~/.zshrc` に同じ PATH を追加する。

### Windows の Codex 自動移行

PowerShell / cmd 版は、`%USERPROFILE%\.npmrc` に次の legacy prefix がある場合だけ Codex を自動移行する。

```text
prefix=C:\Users\<username>\.npm-global
```

実行内容:

1. `~/.npmrc.update-ccx.bak.<timestamp>` を作成
2. legacy prefix から `@openai/codex` を uninstall
3. `.npmrc` から上記 `prefix=` 行だけ削除
4. 現在の Windows npm global prefix (`npm config get prefix`) に `@openai/codex` を再 install
5. その prefix が user PATH に無ければ先頭へ追加

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

#### `update-ccx.cmd` / `update-ccx.sh` が見つからない

- スクリプトディレクトリを PATH に追加する
- またはフルパスで `update-ccx.ps1` / `update-ccx.cmd` / `update-ccx.sh` を実行する

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
- `update-ccx` は standalone 側を削除しない
- PATH の優先順位を見直して、fnm 管理側が先に解決されるようにする
補足:

- 実体は `~/.codex/bin/update-ccx.ps1` / `update-ccx.cmd`
- bare `update-ccx` は `source-root.txt` の checkout を優先し、解決できない場合だけ上記実体へフォールバックする
- `~/.local/bin/update-ccx.cmd` shim から呼び出す
- `~/.local/bin` が user PATH に無ければ setup/update 時に追加する
