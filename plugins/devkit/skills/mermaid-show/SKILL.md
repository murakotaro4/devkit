---
name: "mermaid-show"
description: "Mermaid（.mmd / Markdown内```mermaid）をPNGにレンダリングして表示する。Ghostty/kitty protocol でのインライン表示（kitten icat）に対応。「Mermaidを表示して」「構成図を表示」「diagrams.mdの図を出して」「Mermaidをレンダリングして」などで起動。"
argument-hint: "[path(.md|.mmd)] [--id <anchor>] [--index <n>] [--open]"
allowed-tools: ["Bash", "Read"]
---

# /devkit:mermaid-show - Mermaid表示（PNG / Ghosttyインライン）

Mermaid図を `npx mmdc` でPNGにレンダリングし、可能なら `kitten icat` でインライン表示する。
`kitten icat` が非TTY等で失敗する環境でも、生成したPNGのパスは必ず出す（必要なら `--open` でビューア起動）。

## 使い方

```bash
# Markdown内の <a id="..."></a> を指定して表示（推奨）
/devkit:mermaid-show /Users/murakotaro/PycharmProjects/personal-ops/03_systems/home-computing/diagrams.md --id diagram-now

# Markdown内の n番目（1始まり）の ```mermaid ブロックを表示
/devkit:mermaid-show /Users/murakotaro/PycharmProjects/personal-ops/03_systems/home-computing/diagrams.md --index 2

# .mmd を直接表示
/devkit:mermaid-show ./diagram.mmd
```

## 実行（同梱スクリプト）

原則として同梱スクリプトを呼び出すだけにする。

```bash
SCRIPT1="$HOME/.agent/skills/mermaid-show/scripts/mermaid-show.sh"
SCRIPT2="$HOME/.claude/plugins/marketplaces/murakotaro4/plugins/devkit/skills/mermaid-show/scripts/mermaid-show.sh"

if [ -x "$SCRIPT1" ]; then
  bash "$SCRIPT1" $ARGUMENTS
elif [ -x "$SCRIPT2" ]; then
  bash "$SCRIPT2" $ARGUMENTS
else
  echo "error: mermaid-show.sh が見つかりません。OpenSkillsで devkit を install するか、Claude Codeプラグインの配置を確認してください。" >&2
  exit 1
fi
```

## 仕様メモ

- 入力: `.mmd` または `.md/.markdown`
- Markdownの指定方法:
  - `--id <anchor>`: `<a id="..."></a>` を起点に直後の最初の ```mermaid ブロックを表示
  - `--index <n>`: n番目（1始まり）の ```mermaid ブロックを表示
  - 未指定時: 1枚目を表示し、検出したブロック数と `--index` 候補（+ 推測できる `--id`）を表示
- 出力: `/tmp/mermaid-show/<timestamp-pid>/diagram.mmd` と `diagram.png`
- `--open`: macOSは `open`、Linuxは `xdg-open` でPNGを開く（インライン表示とは独立）
