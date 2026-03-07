# devkit

Claude Code Marketplace 向けプラグイン + 共通スキル配布の母体。
OpenSkillsでスキル本体を配布し、OpenCode / Codex CLI / Claude Code で同じスキルを使い回す。

> **このREADMEについて**: 別PCでゼロから環境構築する場合も含め、前提ツールのインストールからスキル導入・運用まで一通り完了できる初心者向け完全ガイド。

## Migration Notice

`v1.0.0` で以下を破壊的変更として廃止:
- `devkit:codex`（旧）
- `devkit:agent-orch-core`（旧）
- `devkit:agent-orch-openai`（旧）
- `devkit:agent-orch-anthropic`（旧）
- `devkit:agent-orch-google`（旧）

置き換え先:
- dig の入口は `Claude: /dig` / `Codex: $dig` / `OpenCode: /dig`
- runtime adapter は `dig-core` / `dig-claude` / `dig-codex` / `dig-opencode`

自動ゲート（推奨）:
- ローカル: `prek` の `pre-commit` + `pre-push` で自動実行
- CI: GitHub Actions（`pull_request` + `workflow_dispatch`）で `prek` の `pre-push` ステージを実行

ローカルフックの有効化（標準）:
```bash
# 既存設定がある場合のみ実行
git config --unset core.hooksPath || true

prek install --hook-type pre-commit --hook-type pre-push
```

手動チェック（デバッグ時）:
```bash
prek run --all-files --hook-stage pre-commit
prek run --all-files --hook-stage pre-push
```

CI チェック可視化（PR側の確認）:
```bash
# PR のチェックを待機して確認
gh pr checks <PR_NUMBER> --watch

# Workflow 実行履歴を確認
gh run list --workflow "DevKit Dig Checks" --limit 10

# 「チェックが出ない」を検知（最大5分待機）
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\ci\assert-pr-checks.ps1 -PrNumber <PR_NUMBER>
```

補足:
- 新規 workflow 追加直後は GitHub 側の登録タイミングによりチェック表示が遅れることがある。
- その場合は上記コマンドで状態を確認し、必要に応じて `workflow_dispatch` で手動起動する。

## Marketplace Plugin Release Rule

この repo は Claude Code Marketplace plugin を含む。

- plugin 実体: `plugins/devkit/.claude-plugin/plugin.json`
- `plugins/devkit/**` または `.claude-plugin/**` を変更した場合、push 前に `plugin.json` の version を上げる
- pre-push gate は `origin/main` と同じ version のままなら push を block する
- version の目安:
  - `patch`: docs / bugfix only
  - `minor`: workflow contract / user-visible behavior 変更
  - `major`: breaking change

## 前提条件

### 必須ツール

| ツール | 用途 | インストール | 確認コマンド |
|--------|------|-------------|-------------|
| [Node.js](https://nodejs.org/) / npm | CLIツール基盤・スキルインストール | 公式サイトから LTS 版をインストール | `node -v && npm -v` |
| [Git](https://git-scm.com/) | リポジトリクローン・SSH経由のスキル取得 | 公式サイトからインストール | `git --version` |
| [Claude Code](https://docs.anthropic.com/en/docs/claude-code) | メインのAIコーディングCLI | `npm install -g @anthropic-ai/claude-code` | `claude --version` |
| [prek](https://github.com/j178/prek) | Git hooks（pre-commit / pre-push）実行基盤 | Windows: `scoop install prek` / macOS: `brew install prek` | `prek --version` |

#### SSH 鍵のセットアップ（Git 用）

OpenSkills のインストールで SSH 接続が必要。未設定の場合:

```bash
ssh-keygen -t ed25519 -C "your_email@example.com"
# 生成された公開鍵 (~/.ssh/id_ed25519.pub) を GitHub に登録
# 接続確認:
ssh -T git@github.com
```

### 推奨ツール（レビューゲート用）

devkit のワークフローでは、agent team review を前提としつつ、Codex Spark CLI を標準レビューゲートに使う。
インストール推奨だが、未インストール時でも通常フェーズは進められる。review gate だけ代替 reviewer + ユーザー通知へ切り替える。
詳細は [レビューゲートと昇格制](#レビューゲートと昇格制) セクション参照。

| ツール | 用途 | インストール | 確認コマンド |
|--------|------|-------------|-------------|
| [Codex CLI](https://github.com/openai/codex) | Spark / fallback review gate | `npm install -g @openai/codex` | `codex --version` |
| [OpenCode](https://github.com/opencode-ai/opencode) | 追加AI IDE（任意） | `npm install -g opencode-ai` | `opencode --version` |

### Windows 環境の準備

Windows で devkit を使用する場合、以下の追加設定が必要。

#### 1. シンボリックリンクの有効化

devkit のセットアップで `ln -s` を使用するため、Windows ではシンボリックリンク作成権限が必要。

- **方法A（推奨）**: 開発者モードを有効化
  - `設定 > 更新とセキュリティ > 開発者向け > 開発者モード: ON`
- **方法B**: ターミナルを管理者権限で実行

#### 2. パス形式の違い

| 環境 | パス形式 | 例 |
|------|---------|---|
| Git Bash | `/c/Users/...` | `/c/Users/murak/.agent/skills` |
| WSL | `/mnt/c/Users/...` | `/mnt/c/Users/murak/.agent/skills` |
| cmd / PowerShell | `C:\Users\...` | `C:\Users\murak\.agent\skills` |

本READMEのコマンドは `$HOME` を使用しているため、Git Bash / WSL ではそのまま動作する。

#### 3. npm グローバルパスの確認

```bash
npm config get prefix
```

Windows では npm / fnm の構成によって prefix が異なり得る。
`update-ccx.cmd` は legacy な `C:\Users\<username>\.npm-global` だけを自動移行し、それ以外の custom prefix は手動確認が必要として停止する。

PATH に含まれていない場合は、利用中の prefix を PATH に追加する。

> **重要**: PATH 変更後はターミナルの再起動が必要。

#### 4. fnm / nvm 利用時の注意（重要）

Node.js バージョン管理ツール（fnm, nvm）を使用している場合、**シェル初期化で PATH が設定されないと npm グローバルインストールしたコマンド（codex, claude 等）が見つからない**。

- **症状**: `codex: command not found` だがインストール済み
- **原因**: `.bashrc` / `.zshrc` に fnm/nvm の初期化コマンドがない、またはシェルが初期化スクリプトを読み込まない環境（Claude Code の bash 等）
- **確認**: バイナリの場所を特定
  ```bash
  # fnm の場合
  find ~/AppData/Roaming/fnm -name "codex*" -type f 2>/dev/null
  # nvm の場合
  find ~/.nvm -name "codex*" -type f 2>/dev/null
  ```
- **対処**: フルパスで実行するか、PATH にバイナリのディレクトリを追加
  ```bash
  # 例: fnm の場合
  export PATH="$HOME/AppData/Roaming/fnm/node-versions/$(fnm current)/installation:$PATH"
  ```

PowerShell / cmd で `update-ccx.cmd` を使う場合:

- legacy な `~/.npm-global` は初回実行時に Codex だけ fnm 管理側へ移行する
- `%USERPROFILE%\.npmrc` に別の custom prefix がある場合は自動変更しない
- 既存の standalone `codex.exe` は削除しない

## 構成

- `plugins/devkit/.claude-plugin/`: Claude Code プラグイン定義
- `plugins/devkit/skills/*/SKILL.md`: スキル本体
- `plugins/devkit/scripts/`: 補助スクリプト（update-ccx.sh 等）
- `plugins/devkit/shared/`: 共有ワークフロー定義（workflow.md）
- `plugins/devkit/templates/`: OpenCode テンプレートと Codex 設定テンプレート

## 導入（初回）

### 1) OpenSkills でスキルをグローバル導入

```bash
npx openskills@latest install "git@github.com:murakotaro4/devkit.git" --global --universal -y
```

### 2) OpenCode: スキル参照（推奨）

スキル参照（OpenCodeの標準探索先に `.agent/skills` は含まれないため、symlinkで対応）:

```bash
ln -s "$HOME/.agent/skills" "$HOME/.config/opencode/skills"
```

> **Windows**: シンボリックリンク作成には開発者モードの有効化が必要（[前提条件 > Windows環境の準備](#1-シンボリックリンクの有効化) 参照）。
> Git Bash で実行する場合はそのままのコマンドで動作する。
> PowerShell の場合:
> ```powershell
> New-Item -ItemType SymbolicLink -Path "$env:USERPROFILE\.config\opencode\skills" -Target "$env:USERPROFILE\.agent\skills"
> ```
> cmd の場合:
> ```cmd
> mklink /D "%USERPROFILE%\.config\opencode\skills" "%USERPROFILE%\.agent\skills"
> ```

補足: OpenCode 用の `/dig` テンプレートは `plugins/devkit/templates/opencode/commands/dig.md` を参照。

### 3) Codex CLI: スキル参照（`$dig`）

ディレクトリが存在しない場合は先に作成:

```bash
mkdir -p "$HOME/.codex/skills"
```

スキル参照（`~/.codex/skills` へ symlink）:

```bash
ln -s "$HOME/.agent/skills/dig" "$HOME/.codex/skills/dig"
ln -s "$HOME/.agent/skills/dig-core" "$HOME/.codex/skills/dig-core"
ln -s "$HOME/.agent/skills/dig-claude" "$HOME/.codex/skills/dig-claude"
ln -s "$HOME/.agent/skills/dig-codex" "$HOME/.codex/skills/dig-codex"
ln -s "$HOME/.agent/skills/dig-opencode" "$HOME/.codex/skills/dig-opencode"
ln -s "$HOME/.agent/skills/gpt-pro" "$HOME/.codex/skills/gpt-pro"
ln -s "$HOME/.agent/skills/deep-research" "$HOME/.codex/skills/deep-research"
ln -s "$HOME/.agent/skills/mermaid-show" "$HOME/.codex/skills/mermaid-show"
ln -s "$HOME/.agent/skills/amazon-search" "$HOME/.codex/skills/amazon-search"
ln -s "$HOME/.agent/skills/improve-skill" "$HOME/.codex/skills/improve-skill"
ln -s "$HOME/.agent/skills/codex-search" "$HOME/.codex/skills/codex-search"
ln -s "$HOME/.agent/skills/devkit-init" "$HOME/.codex/skills/devkit-init"
```

> **Windows**: Stage 2 と同様、シンボリックリンク作成には開発者モードまたは管理者権限が必要。
>
> Codex での起動入口は `"$dig <topic>"` を使用する。

#### Windows (PowerShell) の推奨セットアップ（自動）

上記を手動で行う代わりに、次のスクリプトで一括セットアップできる。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "$HOME\.claude\plugins\marketplaces\murakotaro4\plugins\devkit\scripts\devkit-setup.ps1" -RegisterDailyTask
```

実行内容:
- `~/.codex/skills` / `~/.codex/bin` / `~/.codex/logs` を作成
- 12スキル（`dig` 系 + utility）のリンクを作成（SymbolicLink優先、不可ならJunction）
- `~/.codex/bin/devkit-skill-update.ps1` を配置
- `~/.codex/bin/update-ccx.ps1` / `update-ccx.cmd` を配置し、`~/.local/bin/update-ccx.cmd` shim を作成
- `~/.codex/bin/devkit-codex-config.ps1` と `~/.codex/devkit/templates/codex/*` を配置
- `~/.codex/devkit/source-root.txt` に DevKit のソースチェックアウト位置を記録
- `~/.codex/config.toml` を共有テンプレートから再生成
- Task Scheduler に `DevKitSkillsDailyUpdate`（毎日07:00）を登録

補足:
- `~/.local/bin` が user PATH に無ければ setup 時に追加する
- 新しい PowerShell / cmd では `update-ccx --version` を cwd に依存せず実行できる

リンク競合ポリシー:
- 既存の実ディレクトリが `~/.codex/skills/<skill>` にある場合は `BLOCKED_EXISTING_DIR` で停止（自動上書きしない）
- 指示された `Rename-Item` を実行して再試行する

#### Codex 設定の共有管理

DevKit は `~/.codex/config.toml` の完成ファイルをリポジトリに直接置くのではなく、共有テンプレートから毎回再生成する。
`devkit-setup.ps1` と `devkit-skill-update.ps1` の両方で再生成されるため、別PCでも同じ設定を揃えやすい。
更新ジョブは setup 時に記録した `source-root.txt` を使って、最新の helper/template をソースチェックアウトから `~/.codex` 側へ再同期してから再生成する。

- 共有テンプレート: `plugins/devkit/templates/codex/config.shared.toml`
- Windows 断片: `plugins/devkit/templates/codex/config.windows.toml`
- 各PC専用の差分: `~/.codex/config.local.toml`
- 生成先: `~/.codex/config.toml`
- バックアップ: `~/.codex/logs/backups/config-YYYYMMDD-HHmmss.toml`

`config.local.toml` は v1 では `projects.*.trust_level` のようなマシン依存値だけを書く前提。
共有テンプレートにある上位キーや `[features]` の再定義は許可しない。
初回導入時に `config.local.toml` が存在しない場合は、既存 `~/.codex/config.toml` 内の `projects.*.trust_level` を自動抽出して bootstrap する。

例:

```toml
[projects.'C:\Users\murak\repos']
trust_level = "trusted"

[projects.'\\?\C:\Users\murak\repos\devkit']
trust_level = "trusted"
```

### 4) （任意）各プロジェクトで AGENTS.md 同期

```bash
npx openskills@latest sync -y
```

## 使い方（スラッシュ）

- Claude Code: `/dig` `/devkit:gpt-pro` `/devkit:deep-research` `/devkit:mermaid-show` `/devkit:amazon-search` `/devkit:improve-skill` `/devkit:codex-search` `/devkit:devkit-init`
- OpenCode: 環境の標準手段でインストール済みスキルを呼び出し（`/devkit-*` はローカルで定義した場合のみ）
- Codex CLI: `$dig` `/prompts:devkit-gpt-pro` `/prompts:devkit-deep-research` `/prompts:devkit-improve-skill`

補足（Codex の `$dig` 利用）:
- `~/.codex/skills/dig*/SKILL.md` は UTF-8 BOM なしであること（BOM があると frontmatter の `---` を解釈できず `$dig` が読み込まれない）

## 更新

### スキル更新（OpenSkills）

```bash
npx openskills@latest update dig,dig-core,dig-claude,dig-codex,dig-opencode,gpt-pro,deep-research,mermaid-show,amazon-search,improve-skill,codex-search,devkit-init
```

必要なら OpenCode / Codex を再起動。

Windows (PowerShell) で毎朝更新を使う場合の手動実行:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "$HOME\.codex\bin\devkit-skill-update.ps1"
```

更新時の config 挙動:
- setup 時に記録した DevKit のソースパスが有効なら、helper/template を先に `~/.codex` へ再同期する
- スキル更新成功後に `~/.codex/config.toml` を再生成する
- `~/.codex/config.local.toml` があればそれも合成する
- config 再生成だけ失敗した場合は直前の config を復元し、更新ジョブは警告終了する

更新失敗時:
- Codex 利用自体は継続可能（非ブロック運用）
- 更新ジョブは非ゼロ終了コードで失敗を返す（Task Scheduler で可観測）
- 復旧に成功した場合は `~/.codex/logs/devkit-skill-update-status.json` に `rolled_back` が記録される

### CLIツール一括更新: update-ccx

Claude Code, Codex CLI, opencode を一括更新するスクリプト。

> `devkit-setup.ps1` は Codex 向けスキル配置・設定同期用。CLI 更新は `update-ccx` 系 (`.cmd` / `.ps1` / `.sh`) を使う。

#### 対応環境

| 環境 | Claude Code | Codex CLI | opencode |
|------|-------------|-----------|----------|
| Windows (PowerShell / cmd) | native / npm | npm / legacy prefix migration | npm |
| Windows (Git Bash) | native / npm | npm (fnm対応) | npm (fnm対応) |
| macOS | Homebrew Cask / npm / native | Homebrew / npm | Homebrew / npm |
| WSL | native / npm | npm | npm |
| Linux | native / npm | npm | npm |

#### セットアップ

Git Bash / WSL / Linux / macOS で `.sh` を使う場合は、スクリプトに PATH を通す:

```bash
# macOS (zsh)
echo 'export PATH="$HOME/.claude/plugins/marketplaces/murakotaro4/plugins/devkit/scripts:$PATH"' >> ~/.zshrc
source ~/.zshrc

# WSL / Linux (bash)
echo 'export PATH="$HOME/.claude/plugins/marketplaces/murakotaro4/plugins/devkit/scripts:$PATH"' >> ~/.bashrc
source ~/.bashrc

# Windows (Git Bash)
echo 'export PATH="$HOME/.claude/plugins/marketplaces/murakotaro4/plugins/devkit/scripts:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

実行権限付与（初回のみ）:

```bash
chmod +x ~/.claude/plugins/marketplaces/murakotaro4/plugins/devkit/scripts/update-ccx.sh
```

`devkit-setup.ps1` 実行済みなら、Windows (PowerShell / cmd) では bare `update-ccx` をそのまま使える:

```powershell
update-ccx --version
update-ccx
```

まだ setup 前で PATH を通していない場合は、フルパス実行でよい:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "$HOME\.claude\plugins\marketplaces\murakotaro4\plugins\devkit\scripts\update-ccx.ps1" --version
& "$HOME\.claude\plugins\marketplaces\murakotaro4\plugins\devkit\scripts\update-ccx.cmd"
```

#### 使用方法

```bash
# Unix / Git Bash / WSL
update-ccx.sh

# 現在のバージョンを表示
update-ccx.sh --version
update-ccx.sh -v
```

```cmd
REM Windows (PowerShell / cmd)
update-ccx
update-ccx --version
```

#### Windows の npm 自己修復

PowerShell / cmd 版は、active/default の fnm 管理 Node に `npm` が見つからない場合、更新処理に入る前に同じ Node バージョンの自己修復を 1 回試す。

実行内容:

1. `npm` の欠落を Setup フェーズで検知する
2. `fnm install <current-version>` と `fnm default <current-version>` を実行する
3. それでも `npm` が戻らない場合は壊れた install root を `.update-ccx-broken.<timestamp>` として退避し、同じバージョンを再取得する
4. 修復できなければ npm ベースの更新を `SKIPPED` にし、Node version / install root / expected npm path を含む診断を 1 件だけ出す

補足:

- 別の Node バージョンへは自動で切り替えない
- `other_npm_ready_versions=` は手動復旧候補として表示するだけで、自動 fallback には使わない

#### Windows の Codex 自動移行

PowerShell / cmd 版は、`%USERPROFILE%\.npmrc` に legacy な `prefix=C:\Users\<username>\.npm-global` がある場合だけ Codex を自動移行する。

実行内容:

1. `~/.npmrc.update-ccx.bak.<timestamp>` を作成
2. 旧 prefix から `@openai/codex` を uninstall
3. `.npmrc` から上記 `prefix=` 行だけ削除
4. 現在の Windows npm global prefix (`npm config get prefix`) に `@openai/codex` を再 install
5. その prefix が user PATH に無ければ先頭へ追加

補足:

- それ以外の custom prefix は自動変更しない
- 既存の standalone `codex.exe` は削除しない
- `where.exe codex` に複数候補がある場合は warning を表示する

#### インストール方法の自動検出

スクリプトは各ツールのインストール方法を自動検出し、適切な更新コマンドを実行する。

| ツール | 検出方法 | 更新コマンド |
|--------|---------|-------------|
| Claude Code (native) | `claude update --help` の存在 | `claude update` |
| Claude Code (homebrew-cask) | `brew list --cask claude` | `brew upgrade --cask claude` |
| Claude Code (npm) | node_modules パス | `npm update -g @anthropic-ai/claude-code` |
| Codex CLI (npm) | `Get-Command codex` / `where.exe codex` / Windows npm global prefix | `npm update -g @openai/codex` |
| Codex CLI (brew) | `brew list codex` | `brew upgrade codex` |
| opencode (npm) | `npm list -g opencode-ai` | `npm update -g opencode-ai` |
| opencode (brew) | `brew list opencode` | `brew upgrade opencode` |

#### 出力例

```
=== Claude Code, Codex CLI & opencode Update ===
Environment: wsl

[Before]
claude:   1.0.57 (native)
codex:    0.1.2505301636 (npm)
opencode: 0.3.5 (npm)

Updating Claude Code (native)... ✓
Updating Codex CLI (npm)... ✓
Updating opencode (npm)... ✓

[After]
claude:   1.0.58
codex:    0.1.2505301636
opencode: 0.3.5

✓ Update completed
```

## ロールバック

```bash
npx openskills@latest remove dig,dig-core,dig-claude,dig-codex,dig-opencode,gpt-pro,deep-research,mermaid-show,amazon-search,improve-skill,codex-search,devkit-init
```

- OpenCode: `~/.config/opencode/skills` の symlink を削除（旧方式の `~/.config/opencode/commands/devkit-*.md` を作成している場合はあわせて削除）
- Codex: `~/.codex/prompts/devkit-*.md` と `~/.codex/skills/{dig,dig-core,dig-claude,dig-codex,dig-opencode,gpt-pro,deep-research,mermaid-show,amazon-search,improve-skill,codex-search,devkit-init}` の symlink を削除
- AGENTS.md を同期していた場合は該当ブロックを削除

## レビューゲートと昇格制

devkit のワークフローでは、agent team review を前提としつつ、Codex Spark CLI を標準レビューゲートに使う。このセクションは全 runtime 共通の**運用契約**であり、runtime ごとの hook や automation は一部だけを機械強制してよい。

### 標準ゲート

全 runtime 共通で次の順序を使う:

| 優先度 | コマンド / 手段 | 条件 |
|--------|-----------------|------|
| 1st | `codex -a never exec review --uncommitted -m gpt-5.3-codex-spark` | Codex CLI が利用可能な場合の標準ゲート |
| 2nd | `codex -a never exec review --uncommitted -m gpt-5.3-codex -c 'model_reasoning_effort="medium"'` | spark 不可 / レートリミット / timeout / parse failure |
| 3rd | 独立した別 agent reviewer + ユーザー通知 | Codex CLI が unavailable または未導入の場合（ただし dig-codex の Phase 5 は適用外） |

Codex CLI は**推奨**であり、通常フェーズの必須前提ではない。CLI が使えない場合は、implementer と別 agent reviewer で review gate を代替する。

### 規模判定

規模判定は `変更種別` を先に見て、その後に `ファイル数` と `変更行数` で引き上げる。最終ランクは最も高いものを採用する。

- `small`
  - 1 ファイル
  - 変更行数 30 行以内
  - 共有 workflow、共通 template、script、hook、skill contract、認証/権限/secret/migration/削除系を含まない
- `medium`
  - 2〜5 ファイル
  - または 31〜200 行
  - または共有 workflow、共通 template、setup/update script、hook、skill contract、認証/権限/secret/migration/削除系を含む
- `large`
  - 6 ファイル以上
  - または 200 行超
  - または複数サブシステムへ跨る

### 昇格条件

`medium` 以上では、標準 gate に加えて**追加の review 視点**を入れる。

- `medium`
  - 追加の独立 reviewer を 1 つ入れる
  - 別モデル review は推奨だが必須ではない
- `large`
  - 追加の独立 reviewer を 1 つ以上入れる
  - 別モデル review を強く推奨する

規模に関係なく、以下では最低 `medium` として扱う:

- `shared/workflow.md`、共通 template、setup / update script の変更
- 権限、認証、secret、削除、migration を含む変更

### dig-codex の例外

`dig-codex` の Phase 5（計画レビュー）は fail-close で運用するため、代替レビューへフォールバックせず停止する。停止時は以下 3 行を必須とする:

- `ERROR_CODE: DIG_CODEX_PLAN_REVIEW_UNAVAILABLE` または `ERROR_CODE: DIG_CODEX_PLAN_REVIEW_BLOCKED`
- `RERUN_COMMAND: <one-line command>`
- `DIAGNOSTIC_COMMAND: <one-line command>`

### CLI の確認方法

レビュー用CLIが正しくインストール・PATH設定されているか確認:

```bash
# Unix / WSL / Git Bash
which codex && codex --version
which claude && claude --version
```

```powershell
# Windows (PowerShell)
Get-Command codex
Get-Command claude
```

```cmd
# Windows (cmd)
where.exe codex
where.exe claude
```

どちらも見つからない場合、CLI review gate は実行できない。通常フェーズでは独立した別 agent reviewer + ユーザー通知へ切り替え、`dig-codex` の Phase 5 は停止する。

## トラブルシュート

### `openskills install/update` が失敗する

SSH 到達確認:

```bash
git ls-remote git@github.com:murakotaro4/devkit.git HEAD
```

SSH 鍵が GitHub に登録されているか確認:

```bash
ssh -T git@github.com
```

### OpenCode / Codex で補完が出ない

- アプリ再起動
- symlink / 配置パスの確認:
  ```bash
  ls -la ~/.config/opencode/skills
  ls -la ~/.codex/skills/
  ```

### `update-ccx.sh` / `update-ccx.cmd`: command not found

PATH が正しく設定されているか確認:

```bash
echo $PATH | tr ':' '\n' | grep devkit
```

PowerShell / cmd の場合は、`devkit-setup.ps1` を再実行して shim を再配置するか、フルパスで `update-ccx.cmd` を実行してもよい。

### `update-ccx.sh` 権限エラー

実行権限を付与:

```bash
chmod +x ~/.claude/plugins/marketplaces/murakotaro4/plugins/devkit/scripts/update-ccx.sh
```

### npm update が失敗する

npm のグローバルディレクトリの権限を確認:

```bash
npm config get prefix
ls -la $(npm config get prefix)/lib/node_modules/
```

### Windows: シンボリックリンク作成に失敗する

- 開発者モードが有効か確認（`設定 > 開発者向け > 開発者モード`）
- または管理者権限でターミナルを起動して再実行

### Windows: npm グローバルコマンドが見つからない

- PowerShell / cmd 版は、active/default の fnm 管理 Node から `npm` が欠けていると同じ Node バージョンの自己修復を 1 回試す
- 失敗時はエラー内の `install_root=` と `expected_npm=` を確認する
- `other_npm_ready_versions=` が出ている場合、必要なら `fnm default <version>` で手動切替する
- **別バージョンへの自動切替は行わない**
- PATH 変更後はターミナルの再起動が必要

### Windows: Codex migration stopped on unexpected prefix

- `%USERPROFILE%\.npmrc` の `prefix=` を確認する
- `update-ccx.cmd` が自動移行するのは `C:\Users\<username>\.npm-global` だけ
- 失敗時は `~/.npmrc.update-ccx.bak.<timestamp>` から元に戻せる

### Windows: `where.exe codex` に複数候補がある

- fnm 管理の Codex と standalone `codex.exe` が混在している
- `update-ccx` は standalone 側を削除しない
- PATH の優先順位を見直して、fnm 管理側が先に解決されるようにする

### fnm / nvm: CLI コマンドが見つからない（★よくある問題）

`codex: command not found` や `claude: command not found` だがインストール済みの場合、fnm / nvm のシェル初期化が読み込まれていない可能性が高い。

1. バイナリの場所を特定:
   ```bash
   # fnm（Windows ネイティブ）
   find ~/AppData/Roaming/fnm -name "codex*" -type f 2>/dev/null
   # fnm（WSL / macOS / Linux）
   find ~/.local/share/fnm -name "codex*" -type f 2>/dev/null
   # nvm
   find ~/.nvm -name "codex*" -type f 2>/dev/null
   ```

2. フルパスで実行するか、PATH にバイナリのディレクトリを追加:
   ```bash
   # fnm の例（Windows ネイティブ）
   export PATH="$HOME/AppData/Roaming/fnm/node-versions/$(fnm current)/installation:$PATH"
   # fnm の例（WSL / macOS / Linux）
   eval "$(fnm env)"
   ```

3. `.bashrc` / `.zshrc` に fnm / nvm の初期化コマンドが含まれているか確認。
   Claude Code の bash 等、初期化スクリプトを読み込まない環境では手動で PATH を設定する必要がある。
