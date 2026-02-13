# devkit

Claude Code Marketplace 向けプラグイン + 共通スキル配布の母体。
OpenSkillsでスキル本体を配布し、OpenCode / Codex / Claude Code で同じスキルを使い回す。

## 構成

- `plugins/devkit/.claude-plugin/`: Claude Code プラグイン
- `plugins/devkit/skills/*/SKILL.md`: スキル本体
- `plugins/devkit/scripts/`: 補助スクリプト

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

補足: 旧方式の `~/.config/opencode/commands/devkit-*.md` はこのリポジトリでは配布しない。

### 3) Codex CLI: スキル参照 + /prompts:devkit-xxx

スキル参照（`~/.codex/skills` へ symlink）:

```bash
ln -s "$HOME/.agent/skills/dig" "$HOME/.codex/skills/dig"
ln -s "$HOME/.agent/skills/codex" "$HOME/.codex/skills/codex"  # 互換ラッパー
ln -s "$HOME/.agent/skills/agent-orch-core" "$HOME/.codex/skills/agent-orch-core"
ln -s "$HOME/.agent/skills/agent-orch-openai" "$HOME/.codex/skills/agent-orch-openai"
ln -s "$HOME/.agent/skills/agent-orch-anthropic" "$HOME/.codex/skills/agent-orch-anthropic"
ln -s "$HOME/.agent/skills/agent-orch-google" "$HOME/.codex/skills/agent-orch-google"
ln -s "$HOME/.agent/skills/gpt-pro" "$HOME/.codex/skills/gpt-pro"
ln -s "$HOME/.agent/skills/deep-research" "$HOME/.codex/skills/deep-research"
ln -s "$HOME/.agent/skills/mermaid-show" "$HOME/.codex/skills/mermaid-show"
ln -s "$HOME/.agent/skills/amazon-search" "$HOME/.codex/skills/amazon-search"
```

プロンプト（例: `~/.codex/prompts/devkit-dig.md`）:

```md
---
description: Use the devkit dig skill
argument-hint: [ARGS]
---
$dig
User input: $ARGUMENTS
```

同様に `devkit-codex.md` / `devkit-agent-orch-core.md` / `devkit-gpt-pro.md` / `devkit-deep-research.md` を作成する。

### 4) （任意）各プロジェクトで AGENTS.md 同期

```bash
npx openskills@latest sync -y
```

## 使い方（スラッシュ）

- Claude Code: `/devkit:dig` `/devkit:codex` `/devkit:agent-orch-core` `/devkit:agent-orch-openai` `/devkit:agent-orch-anthropic` `/devkit:agent-orch-google` `/devkit:gpt-pro` `/devkit:deep-research` `/devkit:mermaid-show` `/devkit:amazon-search`
- OpenCode: 環境の標準手段でインストール済みスキルを呼び出し（`/devkit-*` はローカルで定義した場合のみ）
- Codex CLI: `/prompts:devkit-dig` `/prompts:devkit-codex` `/prompts:devkit-agent-orch-core` `/prompts:devkit-gpt-pro` `/prompts:devkit-deep-research`

## 更新

```bash
npx openskills@latest update dig,codex,agent-orch-core,agent-orch-openai,agent-orch-anthropic,agent-orch-google,gpt-pro,deep-research,mermaid-show,amazon-search
```

必要なら OpenCode / Codex を再起動。

## ロールバック

```bash
npx openskills@latest remove dig,codex,agent-orch-core,agent-orch-openai,agent-orch-anthropic,agent-orch-google,gpt-pro,deep-research,mermaid-show,amazon-search
```

- OpenCode: `~/.config/opencode/skills` の symlink を削除（旧方式の `~/.config/opencode/commands/devkit-*.md` を作成している場合はあわせて削除）
- Codex: `~/.codex/prompts/devkit-*.md` と `~/.codex/skills/{dig,codex,agent-orch-core,agent-orch-openai,agent-orch-anthropic,agent-orch-google,gpt-pro,deep-research,mermaid-show,amazon-search}` の symlink を削除
- AGENTS.md を同期していた場合は該当ブロックを削除

## トラブルシュート（最小）

- `openskills install/update` が失敗する: `git ls-remote git@github.com:murakotaro4/devkit.git HEAD` で SSH 到達確認
- OpenCode/Codexで補完が出ない: アプリ再起動、または symlink/配置パスの確認
