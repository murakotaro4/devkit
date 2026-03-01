# devkit/scripts

開発環境用のユーティリティスクリプト集。

## update-ccx.sh

Claude Code, Codex CLI, opencode を一括更新するスクリプト。

### 対応環境

| 環境 | Claude Code | Codex CLI | opencode |
|------|-------------|-----------|----------|
| macOS | Homebrew Cask / npm / native | Homebrew / npm | Homebrew / npm |
| WSL | native / npm | npm | npm |
| Linux | native / npm | npm | npm |
| Windows (Git Bash) | native / npm | npm (fnm対応) | npm (fnm対応) |

### セットアップ

スクリプトにPATHを通す必要があります。

#### macOS (zsh)

```bash
echo 'export PATH="$HOME/.claude/plugins/marketplaces/murakotaro4/plugins/devkit/scripts:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

#### WSL / Linux (bash)

```bash
echo 'export PATH="$HOME/.claude/plugins/marketplaces/murakotaro4/plugins/devkit/scripts:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

#### Windows (Git Bash)

```bash
echo 'export PATH="$HOME/.claude/plugins/marketplaces/murakotaro4/plugins/devkit/scripts:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

fnm を使用している場合は、`.bashrc` で fnm の PATH 設定が先に行われていることを確認してください:

```bash
# fnm の PATH を通す（winget の場合の例）
export PATH="/c/Users/<username>/AppData/Local/Microsoft/WinGet/Packages/Schniz.fnm_Microsoft.Winget.Source_8wekyb3d8bbwe:$PATH"
eval "$(fnm env --use-on-cd --shell bash)"
```

#### 実行権限付与（初回のみ）

```bash
chmod +x ~/.claude/plugins/marketplaces/murakotaro4/plugins/devkit/scripts/update-ccx.sh
```

### 使用方法

```bash
# 全ツールを更新
update-ccx.sh

# 現在のバージョンを表示
update-ccx.sh --version
update-ccx.sh -v
```

### 出力例

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

### インストール方法の自動検出

スクリプトは各ツールのインストール方法を自動検出し、適切な更新コマンドを実行します。

| ツール | 検出方法 | 更新コマンド |
|--------|---------|-------------|
| Claude Code (native) | `claude update --help` の存在 | `claude update` |
| Claude Code (homebrew-cask) | `brew list --cask claude` | `brew upgrade --cask claude` |
| Claude Code (npm) | node_modules パス | `npm update -g @anthropic-ai/claude-code` |
| Codex CLI (npm) | `npm list -g @openai/codex` | `npm update -g @openai/codex` |
| Codex CLI (brew) | `brew list codex` | `brew upgrade codex` |
| opencode (npm) | `npm list -g opencode-ai` | `npm update -g opencode-ai` |
| opencode (brew) | `brew list opencode` | `brew upgrade opencode` |

### トラブルシューティング

#### "command not found" エラー

PATHが正しく設定されているか確認:

```bash
echo $PATH | tr ':' '\n' | grep devkit
```

#### 権限エラー

実行権限を付与:

```bash
chmod +x ~/.claude/plugins/marketplaces/murakotaro4/plugins/devkit/scripts/update-ccx.sh
```

#### npm update が失敗する

npm のグローバルディレクトリの権限を確認:

```bash
npm config get prefix
ls -la $(npm config get prefix)/lib/node_modules/
```
