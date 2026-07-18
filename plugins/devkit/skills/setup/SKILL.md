---
name: "setup"
description: "対象リポジトリへ DevKit 標準ルールを、ユーザー環境へ updater と Cursor skills を同期し旧 updater 名の残骸を prune する。「セットアップして」「ルール同期して」「/setup」で起動"
argument-hint: "[target]"
allowed-tools: ["Read", "Grep", "Glob", "Bash", "Write", "Edit", "AskUserQuestion", "request_user_input", "TaskCreate", "TaskUpdate"]
---

# /setup

対象リポジトリに DevKit 標準ルールを冪等同期し、ユーザー環境へ思想 DB（thought-db）への参照、最新版の updater、Cursor skills を同期する。Claude 親では statusline を、Windows ではハーネスを問わず Windows Terminal の UDEV Gothic NF を必要に応じて適用する。

## トピック ($ARGUMENTS)

$ARGUMENTS

## ハーネス判定

正本は devkit リポジトリの `AGENTS.md`「スキル共通契約」。要点:

- `AskUserQuestion` が使える場合は Claude 親として扱う。
- なければ `spawn_agent` が使える場合は Codex 親として扱う。
- どちらでもない場合は判定不能として扱い、選択肢を箇条書きで提示して自由文回答を求める。
- `request_user_input` は plan mode 依存で不安定なため、判定キーに使わない(Codex 親 plan mode の質問手段としてのみ使う)。

statusline 適用は Claude Code 固有機能のため Claude 親だけで扱う。Codex 親では statusline は対象外として報告する。Windows Terminal のフォント適用はターミナルレベルの設定なので、Claude 親 / Codex 親のどちらでも扱う。

## 同期対象

- `AGENTS.md`: `<!-- devkit:rules:start -->` / `<!-- devkit:rules:end -->` 区間へ DevKit 標準ルールを同期する。
- `CLAUDE.md`: `@./AGENTS.md` 参照入口を整備する。既に同じ参照行がある場合は重複させない。
- `.claude/devkit-rules.json`: 同期 version、同期時刻、テンプレート SHA-256 を記録する。
- `~/.claude/CLAUDE.md` / `~/.codex/AGENTS.md`(ユーザーレベル): `<!-- devkit:thought-db:start -->` / `<!-- devkit:thought-db:end -->` 区間へ、思想 DB(`~/repos/thought-db`)への参照ブロックを同期する。thought-db が存在しない環境では skip として報告する。
- POSIX: plugin 同梱の `update-ccx.sh` / `devkit-lib.sh` を `~/.codex/bin/` へ、`update-ccx` shim を `~/.local/bin/` へ同期する。
- Windows: plugin 同梱の `update-ccx.ps1` / `update-ccx.cmd` / `devkit-lib.ps1` / `devkit-setup.ps1` / `devkit-codex-config.ps1` を `~/.codex/bin/` へ、`update-ccx.cmd` shim を `~/.local/bin/` へ同期する。旧 updater 名の残骸は両 OS で prune する。
- Cursor: `~/.cursor/` が存在する場合、plugin 同梱の配布スキル 9 本と必要な templates / scripts / statusline を `~/.cursor/` へ冪等同期する。
- Claude 親のみ: plugin 同梱の `statusline/install.js` で Claude Code の statusline 設定を確認し、ユーザー承認後に適用する。
- Windows のみ: Windows Terminal のフォント(UDEV Gothic NF)設定を確認し、ユーザー承認後に適用する。

## 実行ルール

### 1. 事前検証

1. `$ARGUMENTS` があれば対象リポジトリとして解釈し、なければ現在の作業ディレクトリを対象にする。
2. `SKILL.md` があるディレクトリを絶対パスで `SKILL_DIR` に入れ、テンプレートを `"$SKILL_DIR/../../templates/rules/agents-rules.md"` として解決する。
3. テンプレートが存在しない場合は停止し、解決した絶対パスを報告する。
4. 対象が git repo であることを `git -C "$TARGET_REPO" rev-parse --show-toplevel` で確認し、得られた repo root を対象にする。
5. repo root に `plugins/devkit/.claude-plugin/plugin.json` が存在する場合は DevKit repo 自身とみなし、対象外として停止する。

### 2. 環境前提チェック

対象 repo に依存しないユーザー環境の確認で、Claude 親 / Codex 親のどちらでも実行する。DevKit スキル群が前提にする CLI の存在を確認し、不足を報告する。

```bash
for cmd in claude codex cursor-agent node uv; do
  if command -v "$cmd" >/dev/null 2>&1; then echo "OK $cmd"; else echo "MISSING $cmd"; fi
done
```

| コマンド | 用途 | 不足時の影響と案内 |
|---------|------|--------------------|
| claude | Claude Code 親ハーネス。dig-goal の起動プロンプト提示形態における `claude --bg` 候補 | Claude 系の起動プロンプトを実行するユーザー側環境が不足する |
| codex | dig-goal の実装・レビュー backend。自律実行用ゴール本文の独立レビュー候補 | codex 系 backend とゴール本文の codex レビュー候補が使えない |
| cursor-agent | dig-goal の高速レーン(任意) | dig-goal で cursor-agent の選択肢を提示しないだけ。導入は任意 |
| node | statusline 適用 | statusline 適用が実行不可 |
| uv | ルール同期・thought-db 同期・updater 同期・Windows Terminal フォント適用スクリプトの Python runner | ルール同期・thought-db 同期・updater 同期・フォント適用が実行不可(必須) |

結果は OK / MISSING の一覧で報告し、MISSING には上表の影響と導入コマンドを添える。インストール自体はこのスキルでは行わない。

- `uv` が `MISSING` の場合: step 3-6 のルール同期・thought-db 同期・updater 同期・Cursor skills 同期と step 8 のフォント適用は実行不能のため、この時点で停止し、step 3 以降は実行しない。macOS では `brew install uv`、Windows では `winget install --id astral-sh.uv` を案内し、`uv` 導入後に `/setup` を再実行するよう伝える。
- `node` が `MISSING` の場合: step 7 の statusline 適用だけをスキップし、step 3-6 と step 8-9 は続行する。macOS/Homebrew 例として `brew install node` を案内し、statusline を適用したい場合は `node` 導入後に `/setup` を再実行するよう伝える。
- `claude` / `codex` / `cursor-agent` が `MISSING` の場合: 情報提供のみで、ルール同期・thought-db 同期・statusline 適用の制御条件にはしない。

### 3. `scripts/sync_rules.py` による冪等同期

スクリプトは、この SKILL.md があるディレクトリを基準にした絶対パスで実行する。

```bash
SKILL_DIR="<この SKILL.md があるディレクトリの絶対パス>"
TARGET_REPO="<対象リポジトリの絶対パス>"
uv run --no-project --python ">=3.10" python "$SKILL_DIR/scripts/sync_rules.py" \
  --target "$TARGET_REPO" \
  --template "$SKILL_DIR/../../templates/rules/agents-rules.md" \
  --format json
```

`--no-project` は対象 repo の `pyproject.toml` を誤って同期対象にしないため必須とする。`--python ">=3.10"` は対象 repo の非互換な既存 `.venv` やアクティブな virtualenv を避け、DevKit が要求する版のインタプリタを強制するために指定する。

結果 JSON の `changed` / `skipped` / `actions` を確認し、実際に同期した内容を報告する。2 回目以降は、テンプレートと対象ファイルが最新なら no-op になる。テンプレートが更新された場合は、マーカー区間だけを最新化し、マーカー外のプロジェクト固有記述は保持する。

### 4. thought-db 接続同期(ユーザー環境)

対象 repo に依存しないユーザー環境の同期で、Claude 親 / Codex 親のどちらでも実行する。

```bash
SKILL_DIR="<この SKILL.md があるディレクトリの絶対パス>"
uv run --no-project --python ">=3.10" python "$SKILL_DIR/scripts/sync_thought_db.py" \
  --template "$SKILL_DIR/../../templates/rules/thought-db-user.md" \
  --format json
```

結果 JSON の `changed` / `skipped` / `actions` を確認して報告する。冪等で、マーカー区間が最新なら no-op になる。マーカー外のユーザー記述は保持し、既存ファイルを書き換える場合は同ディレクトリの `devkit-thought-db-backup/` へ退避してから置換する。`~/repos/thought-db` が存在しない環境では skip になるため、「thought-db 未配置。使う場合は private リモートから `~/repos/thought-db` へ clone 後に /setup を再実行」と案内する。`~/.codex/AGENTS.md` は Codex 未導入環境でも作成する(後から Codex を導入した場合に配線済みにするための意図的な設計)。

### 5. updater 同期(ユーザー環境)

対象 repo に依存しないユーザー環境の同期で、Claude 親 / Codex 親のどちらでも実行する。承認ゲートは置かず、plugin 同梱の最新版を管理先へ冪等同期する。

```bash
SKILL_DIR="<この SKILL.md があるディレクトリの絶対パス>"
uv run --no-project --python ">=3.10" python "$SKILL_DIR/scripts/sync_updater.py" --format json
```

結果 JSON の `changed` / `skipped` / `actions` を確認して報告する。POSIX では `~/.codex/bin/update-ccx.sh` に実行権を付け、両 OS とも `~/.local/bin/` の shim を plugin 同梱 `devkit-lib` の実装と同形式で同期する。旧 updater 名の残骸があれば削除し、`actions` に記録する。`~/.codex/devkit/source-root.txt` は変更しない。変更予定だけを確認する場合は `--check` を付けると書き込みを行わない。

### 6. Cursor skills 同期(ユーザー環境)

対象 repo に依存しないユーザー環境の同期で、Claude 親 / Codex 親のどちらでも実行する。承認ゲートは置かず、`~/.cursor/` が存在する場合だけ plugin 同梱の配布スキルと必要資産を冪等同期する。

```bash
SKILL_DIR="<この SKILL.md があるディレクトリの絶対パス>"
uv run --no-project --python ">=3.10" python "$SKILL_DIR/scripts/sync_cursor_skills.py" --format json
```

結果 JSON の `changed` / `skipped` / `actions` を確認して報告する。`~/.cursor/` が存在しない場合はディレクトリを作らず skip として報告する。管理 manifest と一致する廃止ファイルだけを prune し、ユーザーが変更したファイル、symlink、manifest 非掲載ファイルは保持して該当する skip action を報告する。同期失敗時は失敗を記録して後続の statusline / フォント step を続行し、最終レポートに明記する。変更予定だけを確認する場合は `--check` を付けると書き込みを行わない。

### 7. statusline 適用

Claude 親のみ実行する。Codex 親ではこの step をスキップし、「statusline は Claude Code 固有機能のため対象外。ルール同期・thought-db 接続同期・updater 同期・Cursor skills 同期を実施」と報告する。step 2 で `node` が `MISSING` だった場合もこの step はスキップし、`node` 導入後の `/setup` 再実行を案内する。

Claude 親では plugin 同梱の installer を確認する。

```bash
SKILL_DIR="<この SKILL.md があるディレクトリの絶対パス>"
STATUSLINE_INSTALL="$SKILL_DIR/../../statusline/install.js"
node "$STATUSLINE_INSTALL" --check
```

`--check` の結果を提示し、選択肢付き質問で適用可否を確認する。

- 未導入または DevKit 管理済み: ユーザーが適用を選んだ場合に `node "$STATUSLINE_INSTALL"` を実行する。
- 他の statusline 設定を検出した場合: 既存設定を上書きするかを追加確認し、承認された場合だけ `node "$STATUSLINE_INSTALL" --force` を実行する。
- ユーザーがスキップを選んだ場合: ルール同期・thought-db 接続同期・updater 同期・Cursor skills 同期の結果を報告する。

### 8. ターミナルフォント適用(Windows のみ)

Claude 親 / Codex 親のどちらでも実行する。ターミナルレベルの設定であり、ハーネスには依存しない。非 Windows 環境では skip し、「macOS/Linux は対象外(macOS は Ghostty 既定が JetBrains Mono)」と報告する。

Windows では現在の検出・変更予定を確認する。

```bash
SKILL_DIR="<この SKILL.md があるディレクトリの絶対パス>"
uv run --no-project --python ">=3.10" python "$SKILL_DIR/scripts/setup_terminal_font.py" --check --format json
```

結果 JSON を提示し、選択肢付き質問で承認を得てから適用する。Codex 親通常 mode または判定不能では、選択肢を箇条書きで提示して自由文回答を求める。

```bash
uv run --no-project --python ">=3.10" python "$SKILL_DIR/scripts/setup_terminal_font.py" --format json
```

ダウンロード失敗、SHA-256 不一致、フォント未登録、Windows Terminal 未検出は案内のみとし、setup 全体を停止しない。フォントを検出できない場合の settings.json 書き込みはスクリプト側のゲートで抑止する。

### 9. 検証とレポート

1. `AGENTS.md` に `devkit:rules` の start/end マーカーが 1 組あることを確認する。
2. `CLAUDE.md` に `@./AGENTS.md` が 1 行だけあることを確認する。
3. `.claude/devkit-rules.json` の `template_sha256` がテンプレートの SHA-256 と一致することを確認する。
4. thought-db 同期を実行した場合は、`~/.claude/CLAUDE.md` と `~/.codex/AGENTS.md` に `devkit:thought-db` の start/end マーカーが 1 組ずつあることを確認する。skip の場合はその旨を報告する。
5. updater 同期の `changed` / `skipped` / `actions` を報告し、同期または prune したパスを示す。
6. Cursor skills 同期の `changed` / `skipped` / `actions` と、`~/.cursor/` 不在による skip または同期失敗を報告する。
7. statusline を適用した場合は installer の結果 JSON を報告する。
8. ターミナルフォント確認を実行した場合は `status` / `font_installed` / `download` / `settings` / `actions` を含む結果 JSON を報告する。
9. 変更ファイル、no-op だった項目、ユーザーがスキップした項目を分けて報告する。環境前提チェックで MISSING があった場合は、影響と導入コマンドを報告に含める。

## 再実行時の動作

DevKit 更新後に `/setup` を再実行すると、ルール・thought-db 参照・updater・Cursor skills・statusline・Windows Terminal フォント設定を最新へ同期する。ルール同期・thought-db 同期・updater 同期・Cursor skills 同期は冪等で、管理対象が最新なら no-op になる。テンプレートが変わった場合はマーカー区間だけを置換し、マーカー外の記述は保持する。updater の同期元が変わった場合は該当ファイルと shim だけを更新し、旧 updater 名の残骸は毎回 prune 対象として確認する。Cursor の同期元が変わった場合は manifest で管理するファイルだけを更新または安全に prune し、manifest 非掲載のユーザーファイルは保持する。Claude 親で statusline 適用を選ぶと、同梱最新版を管理先へ再コピーして設定を更新する。フォントの face が既に UDEV Gothic NF なら no-op となり、バックアップも増やさない。

## 注意

- ルール同期、updater 同期、Cursor skills 同期は設計上、差分承認ゲートなしで実行する(冪等同期が本務のため)。承認ゲートがあるのは statusline 適用とターミナルフォント適用のみで、この非対称は意図的なもの。
- マーカー内の手動編集は次回 `/setup` 実行時に上書きされる。
- プロジェクト固有ルールはマーカー外に書く。
- DevKit repo 自身には実行しない。
- commit / push は対象リポジトリの AGENTS.md の Commit Rules に従う。
