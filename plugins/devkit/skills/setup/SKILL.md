---
name: "setup"
description: "対象リポジトリへ DevKit 標準ルールと対応環境設定を同期する。「セットアップして」「ルール同期して」「/setup」で起動"
argument-hint: "[target]"
allowed-tools: ["Read", "Grep", "Glob", "Bash", "Write", "Edit", "AskUserQuestion", "request_user_input", "TaskCreate", "TaskUpdate"]
---

# /setup

対象リポジトリに DevKit 標準ルールを冪等同期し、Claude 親では statusline などの Claude Code 向け環境設定も必要に応じて適用する。

## トピック ($ARGUMENTS)

$ARGUMENTS

## ハーネス判定

この SKILL.md は Claude Code / OpenAI Codex のどちらの親ハーネスでも自己完結して実行する。

- `AskUserQuestion` と `TaskCreate` / `TaskUpdate` が使える場合は Claude 親として扱う。
- `request_user_input` のみ使える場合は Codex 親の plan mode として扱う。
- どちらの質問ツールも使えない場合は Codex 親の通常 mode として扱い、選択肢を箇条書きで提示して自由文回答を求める。

statusline 適用は Claude Code 固有機能のため Claude 親だけで扱う。Codex 親ではルール同期のみを実行し、statusline は対象外として報告する。

## 同期対象

- `AGENTS.md`: `<!-- devkit:rules:start -->` / `<!-- devkit:rules:end -->` 区間へ DevKit 標準ルールを同期する。
- `CLAUDE.md`: `@./AGENTS.md` 参照入口を整備する。既に同じ参照行がある場合は重複させない。
- `.claude/devkit-rules.json`: 同期 version、同期時刻、テンプレート SHA-256 を記録する。
- Claude 親のみ: plugin 同梱の `statusline/install.js` で Claude Code の statusline 設定を確認し、ユーザー承認後に適用する。

## 実行ルール

### 1. 事前検証

1. `$ARGUMENTS` があれば対象リポジトリとして解釈し、なければ現在の作業ディレクトリを対象にする。
2. `SKILL.md` があるディレクトリを絶対パスで `SKILL_DIR` に入れ、テンプレートを `"$SKILL_DIR/../../templates/rules/agents-rules.md"` として解決する。
3. テンプレートが存在しない場合は停止し、解決した絶対パスを報告する。
4. 対象が git repo であることを `git -C "$TARGET_REPO" rev-parse --show-toplevel` で確認し、得られた repo root を対象にする。
5. repo root に `plugins/devkit/.claude-plugin/plugin.json` が存在する場合は DevKit repo 自身とみなし、対象外として停止する。

### 2. `scripts/sync_rules.py` による冪等同期

スクリプトは、この SKILL.md があるディレクトリを基準にした絶対パスで実行する。

```bash
SKILL_DIR="<この SKILL.md があるディレクトリの絶対パス>"
TARGET_REPO="<対象リポジトリの絶対パス>"
python3 "$SKILL_DIR/scripts/sync_rules.py" \
  --target "$TARGET_REPO" \
  --template "$SKILL_DIR/../../templates/rules/agents-rules.md" \
  --format json
```

結果 JSON の `changed` / `skipped` / `actions` を確認し、実際に同期した内容を報告する。2 回目以降は、テンプレートと対象ファイルが最新なら no-op になる。テンプレートが更新された場合は、マーカー区間だけを最新化し、マーカー外のプロジェクト固有記述は保持する。

### 3. statusline 適用

Claude 親のみ実行する。Codex 親ではこの step をスキップし、「statusline は Claude Code 固有機能のため対象外。ルール同期のみ実施」と報告する。

Claude 親では plugin 同梱の installer を確認する。

```bash
SKILL_DIR="<この SKILL.md があるディレクトリの絶対パス>"
STATUSLINE_INSTALL="$SKILL_DIR/../../statusline/install.js"
node "$STATUSLINE_INSTALL" --check
```

`--check` の結果を提示し、選択肢付き質問で適用可否を確認する。

- 未導入または DevKit 管理済み: ユーザーが適用を選んだ場合に `node "$STATUSLINE_INSTALL"` を実行する。
- 他の statusline 設定を検出した場合: 既存設定を上書きするかを追加確認し、承認された場合だけ `node "$STATUSLINE_INSTALL" --force` を実行する。
- ユーザーがスキップを選んだ場合: ルール同期結果だけを報告する。

### 4. 検証とレポート

1. `AGENTS.md` に `devkit:rules` の start/end マーカーが 1 組あることを確認する。
2. `CLAUDE.md` に `@./AGENTS.md` が 1 行だけあることを確認する。
3. `.claude/devkit-rules.json` の `template_sha256` がテンプレートの SHA-256 と一致することを確認する。
4. statusline を適用した場合は installer の結果 JSON を報告する。
5. 変更ファイル、no-op だった項目、ユーザーがスキップした項目を分けて報告する。

## 再実行時の動作

DevKit 更新後に `/setup` を再実行すると、ルールと statusline の両方を最新へ同期する。ルール同期は冪等で、テンプレート・マーカー区間・参照入口・同期メタデータが最新なら no-op になる。テンプレートが変わった場合は `AGENTS.md` のマーカー区間だけを置換し、マーカー外の記述は保持する。Claude 親で statusline 適用を選ぶと、同梱最新版を管理先へ再コピーして設定を更新する。

## 注意

- マーカー内の手動編集は次回 `/setup` 実行時に上書きされる。
- プロジェクト固有ルールはマーカー外に書く。
- DevKit repo 自身には実行しない。
- commit / push はユーザーが明示した場合のみ行う。
