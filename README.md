# devkit

Claude Code Marketplace 向けプラグイン + 共通スキル配布の母体。
OpenSkillsでスキル本体を配布し、OpenCode / Codex / Claude Code で同じスキルを使い回す。

## 構成

- `plugins/devkit/.claude-plugin/`: Claude Code プラグイン
- `plugins/devkit/skills/*/SKILL.md`: スキル本体
- `plugins/devkit/commands/*.md`: コマンド shim（skills 優先前提）

## 導入（初回）

### 1) OpenSkills でスキルをグローバル導入

```bash
npx openskills@latest install "git@github.com:murakotaro4/devkit.git" --global --universal -y
```

### 2) OpenCode: スキル参照 + /devkit-xxx コマンド

スキル参照（OpenCodeの標準探索先に `.agent/skills` は含まれないため、symlinkで対応）:

```bash
ln -s "$HOME/.agent/skills" "$HOME/.config/opencode/skills"
```

コマンド（例: `~/.config/opencode/commands/devkit-dig.md`）:

```md
---
description: Use the devkit dig skill
---
skill({ name: "dig" })
User input: $ARGUMENTS
```

同様に `devkit-codex.md` / `devkit-gpt-pro.md` を作成する。

### 3) Codex CLI: スキル参照 + /prompts:devkit-xxx

スキル参照（`~/.codex/skills` へ symlink）:

```bash
ln -s "$HOME/.agent/skills/dig" "$HOME/.codex/skills/dig"
ln -s "$HOME/.agent/skills/codex" "$HOME/.codex/skills/codex"
ln -s "$HOME/.agent/skills/gpt-pro" "$HOME/.codex/skills/gpt-pro"
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

同様に `devkit-codex.md` / `devkit-gpt-pro.md` を作成する。

### 4) （任意）各プロジェクトで AGENTS.md 同期

```bash
npx openskills@latest sync -y
```

## 使い方（スラッシュ）

- Claude Code: `/devkit:dig` `/devkit:codex` `/devkit:gpt-pro`
- OpenCode: `/devkit-dig` `/devkit-codex` `/devkit-gpt-pro`
- Codex CLI: `/prompts:devkit-dig` `/prompts:devkit-codex` `/prompts:devkit-gpt-pro`

## 更新

```bash
npx openskills@latest update dig,codex,gpt-pro
```

必要なら OpenCode / Codex を再起動。

## ロールバック

```bash
npx openskills@latest remove dig,codex,gpt-pro
```

- OpenCode: `~/.config/opencode/commands/devkit-*.md` と `~/.config/opencode/skills` を削除
- Codex: `~/.codex/prompts/devkit-*.md` と `~/.codex/skills/{dig,codex,gpt-pro}` の symlink を削除
- AGENTS.md を同期していた場合は該当ブロックを削除

## トラブルシュート（最小）

- `openskills install/update` が失敗する: `git ls-remote git@github.com:murakotaro4/devkit.git HEAD` で SSH 到達確認
- OpenCode/Codexで補完が出ない: アプリ再起動、または symlink/配置パスの確認
