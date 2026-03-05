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

### 推奨ツール（クロスレビュー用）

devkit のワークフローでは、異なるAIモデル間でコードレビュー（クロスレビュー）を行う。
インストール推奨だが必須ではない。未インストール時はクロスレビューがスキップされ、ユーザーに警告の上で手動レビューへ切り替わる（他フェーズは通常通り動作）。
詳細は [クロスレビューとフォールバック](#クロスレビューとフォールバック) セクション参照。

| ツール | 用途 | インストール | 確認コマンド |
|--------|------|-------------|-------------|
| [Codex CLI](https://github.com/openai/codex) | Claude Code 使用時のクロスレビュアー | `npm install -g @openai/codex` | `codex --version` |
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

パスが `C:\Users\<ユーザー名>\AppData\Roaming\npm` であることを確認。
PATH に含まれていない場合は手動で追加（環境変数の編集で `%APPDATA%\npm` を追加）。

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

## 構成

- `plugins/devkit/.claude-plugin/`: Claude Code プラグイン定義
- `plugins/devkit/skills/*/SKILL.md`: スキル本体
- `plugins/devkit/scripts/`: 補助スクリプト（update-ccx.sh 等）
- `plugins/devkit/shared/`: 共有ワークフロー定義（workflow.md）

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
- Task Scheduler に `DevKitSkillsDailyUpdate`（毎日07:00）を登録

リンク競合ポリシー:
- 既存の実ディレクトリが `~/.codex/skills/<skill>` にある場合は `BLOCKED_EXISTING_DIR` で停止（自動上書きしない）
- 指示された `Rename-Item` を実行して再試行する

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

更新失敗時:
- Codex 利用自体は継続可能（非ブロック運用）
- 更新ジョブは非ゼロ終了コードで失敗を返す（Task Scheduler で可観測）
- 復旧に成功した場合は `~/.codex/logs/devkit-skill-update-status.json` に `rolled_back` が記録される

### CLIツール一括更新: update-ccx.sh

Claude Code, Codex CLI, opencode を一括更新するスクリプト。

> **注意**: bash スクリプトのため macOS / WSL / Linux でのみ動作する。ネイティブ Windows (cmd/PowerShell) では WSL 経由で実行すること。

#### 対応環境

| 環境 | Claude Code | Codex CLI | opencode |
|------|-------------|-----------|----------|
| macOS | Homebrew Cask / npm / native | Homebrew / npm | Homebrew / npm |
| WSL | native / npm | npm | npm |
| Linux | native / npm | npm | npm |

#### セットアップ

スクリプトに PATH を通す:

```bash
# macOS (zsh)
echo 'export PATH="$HOME/.claude/plugins/marketplaces/murakotaro4/plugins/devkit/scripts:$PATH"' >> ~/.zshrc
source ~/.zshrc

# WSL / Linux (bash)
echo 'export PATH="$HOME/.claude/plugins/marketplaces/murakotaro4/plugins/devkit/scripts:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

実行権限付与（初回のみ）:

```bash
chmod +x ~/.claude/plugins/marketplaces/murakotaro4/plugins/devkit/scripts/update-ccx.sh
```

#### 使用方法

```bash
# 全ツールを更新
update-ccx.sh

# 現在のバージョンを表示
update-ccx.sh --version
update-ccx.sh -v
```

#### インストール方法の自動検出

スクリプトは各ツールのインストール方法を自動検出し、適切な更新コマンドを実行する。

| ツール | 検出方法 | 更新コマンド |
|--------|---------|-------------|
| Claude Code (native) | `claude update --help` の存在 | `claude update` |
| Claude Code (homebrew-cask) | `brew list --cask claude` | `brew upgrade --cask claude` |
| Claude Code (npm) | node_modules パス | `npm update -g @anthropic-ai/claude-code` |
| Codex CLI (npm) | `npm list -g @openai/codex` | `npm update -g @openai/codex` |
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

## クロスレビューとフォールバック

devkit のワークフローでは、コード品質を保つためにクロスモデルレビューを実施する。
異なるAIモデルが互いのコードをレビューすることで、単一モデルの盲点を補う。

### フォールバック戦略

全 runtime 共通で次の順序を使う:

| 優先度 | コマンド | 条件 |
|--------|---------|------|
| 1st | `codex -a never exec review --uncommitted -m gpt-5.3-codex-spark` | デフォルト |
| 2nd | `codex -a never exec review --uncommitted -m gpt-5.3-codex -c 'model_reasoning_effort="medium"'` | spark 不可 / レートリミット時 |
| 3rd | レビュースキップ + ユーザー通知 | codex CLI 未インストール or 全モデル不可時（ただし dig-codex の Phase 5 は適用外） |

### レビュースキップとは

3rd フォールバック（レビュースキップ）に到達した場合:

- レビューフェーズのみスキップされる（Phase 5: 計画レビュー、Phase 7: 実装レビュー）
- **他の全フェーズ（調査・計画・実装・コミット等）は引き続き必須**
- ユーザーに警告が表示され、続行可否の確認が行われる
- 品質保証のため、可能な限りレビュー用CLIのインストールを推奨

`dig-codex` の Phase 5（計画レビュー）は fail-close で運用するため、スキップしない。停止時は以下 3 行を必須とする:

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

どちらも見つからない場合、クロスレビューは実行できず常にスキップされる。

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

### `update-ccx.sh: command not found`

PATH が正しく設定されているか確認:

```bash
echo $PATH | tr ':' '\n' | grep devkit
```

PATH が通っていない場合は [セットアップ手順](#セットアップ) を再実行。

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

- `npm config get prefix` でインストール先を確認
- PATH に `%APPDATA%\npm` が含まれているか確認
- **PATH 変更後はターミナルの再起動が必要**

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

