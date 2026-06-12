# devkit

Claude Code Marketplace 向けプラグイン + 共通スキル配布/更新の母体。
初回 bootstrap は Marketplace の `devkit-setup.ps1`、継続更新は `update-devkit` を主入口にする。`update-ccx` は互換 alias。

> **このREADMEについて**: 別PCでゼロから環境構築する場合も含め、前提ツールのインストールからスキル導入・運用まで一通り完了できる初心者向け完全ガイド。

## Migration Notice

`v1.0.0` で以下を破壊的変更として廃止:

- `devkit:codex`（旧）
- `devkit:agent-orch-core`（旧）
- `devkit:agent-orch-openai`（旧）
- `devkit:agent-orch-anthropic`（旧）
- `devkit:agent-orch-google`（旧）

置き換え先:

- dig の公開入口は `Claude: /dig` / `Cursor: /dig` / `Codex: $dig` / `OpenCode: /dig`
- runtime adapter の実体ファイルは `dig-core` / `dig-claude` / `dig-cursor` / `dig-codex` / `dig-opencode`
- Codex / OpenCode へ同期するトップレベル skill は公開入口だけに絞り、adapter は環境ごとの shared source checkout から内部参照する

自動ゲート（推奨）:

- ローカル: `prek` の `pre-commit` + `pre-push` で自動実行
- CI: GitHub Actions（`pull_request` + `workflow_dispatch`）で `uv run --project plugins/devkit python plugins/devkit/scripts/devkit_harness.py verify-full` を実行
- devkit 本体では Git hook の正規入口を `prek.toml` に固定し、旧 `.githooks` は stale clone を止めるための legacy shim だけ残す

Harness-first の手動入口:

```bash
uv sync --project plugins/devkit --group dev
uv run --project plugins/devkit python plugins/devkit/scripts/devkit_harness.py verify-fast
uv run --project plugins/devkit python plugins/devkit/scripts/devkit_harness.py verify-full
```

ローカルフックの有効化（標準）:

```bash
cargo install prek
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
| [Node.js](https://nodejs.org/) / npm | Claude/Codex/OpenCode の install/update 実行 | 公式サイトから LTS 版をインストール | `node -v && npm -v` |
| [Git](https://git-scm.com/) | shared source checkout の更新 | 公式サイトからインストール | `git --version` |
| [Claude Code](https://docs.anthropic.com/en/docs/claude-code) | メインのAIコーディングCLI | `npm install -g @anthropic-ai/claude-code` | `claude --version` |
| [prek](https://github.com/j178/prek) | Git hooks（pre-commit / pre-push）実行基盤 | Linux/WSL: `cargo install prek` / Windows: `scoop install prek` / macOS: `brew install prek` | `prek --version` |
| [uv](https://docs.astral.sh/uv/) | Pythonベースのハーネス実行・依存同期 | 公式インストーラ / `pipx install uv` など | `uv --version` |

補足:

- Claude hook は `node` launcher 経由で `uv` を優先し、未導入時は system Python へ fallback する
- `verify-fast` / `verify-full` の手動実行と依存同期は引き続き `uv` を正規入口とする

### 推奨ツール（レビューゲート用）

devkit のワークフローでは、agent team review を前提としつつ、Codex Spark CLI を標準レビューゲートに使う。
インストール推奨だが、未インストール時でも通常フェーズは進められる。review gate だけ代替 reviewer + ユーザー通知へ切り替える。
詳細は [レビューゲートと昇格制](#%E3%83%AC%E3%83%93%E3%83%A5%E3%83%BC%E3%82%B2%E3%83%BC%E3%83%88%E3%81%A8%E6%98%87%E6%A0%BC%E5%88%B6) セクション参照。

| ツール | 用途 | インストール | 確認コマンド |
|--------|------|-------------|-------------|
| [Codex CLI](https://github.com/openai/codex) | Spark / fallback review gate | `npm install -g @openai/codex` | `codex --version` |
| [OpenCode](https://github.com/opencode-ai/opencode) | 追加AI IDE（任意） | `npm install -g opencode-ai` | `opencode --version` |
| Google Chrome | ChatGPT Pro / Deep Research の Default profile 実行 | 公式サイトからインストール | Chrome を通常起動 |
| agent-browser | ChatGPT UI の主操作 backend | `npm install -g agent-browser` | `agent-browser --version` |

### Windows 環境の準備

Windows で devkit を使用する場合、以下の追加設定が必要。

#### 1. Marketplace bootstrap を使う

PowerShell / cmd の初回セットアップは、Marketplace 配布の `devkit-setup.ps1` を bootstrap として使う。
継続更新は bootstrap 後に `update-devkit` を使い、`update-ccx` は互換 alias として扱う。

#### 2. パス形式の違い

| 環境 | パス形式 | 例 |
|------|---------|---|
| Git Bash | `/c/Users/...` | `/c/Users/murak/cursor/devkit` |
| WSL | `/mnt/c/Users/...` | `/mnt/c/Users/murak/cursor/devkit` |
| cmd / PowerShell | `C:\Users\...` | `C:\Users\murak\cursor\devkit` |

本READMEのコマンドは `$HOME` を使用しているため、Git Bash / WSL ではそのまま動作する。

#### 3. npm グローバルパスの確認

```bash
npm config get prefix
```

Windows では npm / fnm の構成によって prefix が異なり得る。
`update-devkit` / `update-ccx` は legacy な `C:\Users\<username>\.npm-global` だけを自動移行し、それ以外の custom prefix は手動確認が必要として停止する。

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

PowerShell / cmd で `update-devkit` / `update-ccx` を使う場合:

- legacy な `~/.npm-global` は初回実行時に Codex だけ fnm 管理側へ移行する
- `%USERPROFILE%\.npmrc` に別の custom prefix がある場合は自動変更しない
- 既存の standalone `codex.exe` は削除しない

## 構成

- `plugins/devkit/.claude-plugin/`: Claude Code プラグイン定義
- `plugins/devkit/skills/*/SKILL.md`: スキル本体（`repo-maintainer` / `repo-maintainer-init` を含む）
- `plugins/devkit/scripts/`: 補助スクリプト（`devkit-setup.ps1`、`update-devkit` / `update-ccx`、`repo_maintainer.py`）
- `plugins/devkit/shared/`: 共有ワークフロー定義（workflow.md）
- `plugins/devkit/templates/`: OpenCode テンプレートと Codex 設定テンプレート

## 導入（初回）

### 基本方針

- OpenSkills ベースの install / update は primary flow から外した。
- devkit 本体の local Git hook は `prek.toml` を正本にする。
- PowerShell / cmd の初回 bootstrap は Marketplace 配布の `devkit-setup.ps1` を使う。
- 継続更新はインストール済みの `update-devkit` を使う。`update-ccx` は互換 alias。
- `update-devkit` / `update-ccx` は CLI 更新に加えて、Codex / OpenCode の DevKit 管理 user-level assets も同期する。
- project 単位の `AGENTS.md` / `CLAUDE.md` workflow sync は `update-devkit` の対象外。

### DevKit repo の hook 標準

- `~/cursor/devkit` では `prek install --hook-type pre-commit --hook-type pre-push` を標準にする。
- `pre-commit` では staged な `*.json`, `*.md`, `*.yaml`, `*.yml` の UTF-8 BOM 混入も検査する。
- `verify-fast` / `verify-full` でも repo 全体の UTF-8 BOM を検査する。
- 旧 `.githooks/pre-commit` は stale clone を fail-close にする legacy shim としてだけ残し、devkit 本体の正規ルートとしては使わない。
- 他 repo の hook 方式整理は別フェーズに分ける。

### Shared DevKit Source

- 共通 DevKit source: その環境で使う DevKit checkout
- この環境の例: `~/cursor/devkit`
- Codex の global skill: `~/.agents/skills`
- Codex の repo-local skill: `<repo>/.agents/skills`
- Claude の repo-local skill: `<repo>/.claude/skills`
- OpenCode の global skill: `~/.config/opencode/skills`

Codex / OpenCode はその環境で選ばれた DevKit checkout を共通 source として使い、skills / commands / helper / templates をそこから同期する。Codex の project 専用 skill は各 repo の `.agents/skills` に置き、Claude の project 専用 skill は `.claude/skills` に置く。`~/.codex/skills` は user-managed skill root ではない。
`DEVKIT_SOURCE_ROOT` を設定すれば source root を明示できる。未指定時は、直接実行している DevKit checkout、または直近 sync で保存された `source-root.txt` を優先して再利用する。

### Windows (PowerShell / cmd) bootstrap

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "$HOME\.claude\plugins\marketplaces\murakotaro4\plugins\devkit\scripts\devkit-setup.ps1" -RegisterDailyTask
```

bootstrap 後の更新:

```powershell
update-devkit --version
update-devkit
```

互換 alias:

```powershell
update-ccx --version
update-ccx
```

補足:

- 既存ユーザーは launcher 更新のために `devkit-setup.ps1` を 1 回再実行しておくと安全。
- Codex 側の helper / template / config も bootstrap / update 時に再同期される。
- OpenCode / Codex を起動中なら、更新後に再起動すると反映が確実。

### macOS / Linux / WSL / Git Bash bootstrap

初回だけは checkout または Marketplace 配下の script を直接実行する。checkout から実行した場合はその checkout を shared source として保存する。Marketplace bootstrap から実行した場合は、`DEVKIT_SOURCE_ROOT` か環境の既定 clone 先へ clone してから継続する。

```bash
# repo checkout から直接
bash ./plugins/devkit/scripts/update-devkit.sh --devkit-only

# または Marketplace 配置から直接
bash "$HOME/.claude/plugins/marketplaces/murakotaro4/plugins/devkit/scripts/update-devkit.sh" --devkit-only
```

この初回実行で `~/.codex/bin` に managed script が配置され、`~/.local/bin/update-devkit` と `update-ccx` の launcher はそこを呼ぶ。以降は bare command を使う。clone / update に失敗した場合は snapshot へ fallback せず停止する。

## 使い方（スラッシュ）

- Claude Code: `/dig` `/devkit:gpt-pro` `/devkit:deep-research` `/devkit:improve-skill` `/devkit:codex-search` `/devkit:codex-impl` `/devkit:devkit-init` `/devkit:repo-maintainer` `/devkit:repo-maintainer-init`
- OpenCode: 環境の標準手段でインストール済みスキルを呼び出し（`/devkit-*` はローカルで定義した場合のみ）
- Codex CLI: `$dig` `$gpt-pro` `$repo-maintainer` `$repo-maintainer-init`
- Codex Desktop (macOS + Computer Use): `$computer-use-chatgpt-pro`

Codex 連携の住み分け:

- 実装委譲: `/devkit:codex-impl`（Claude = 要件整理・レビュー・テスト、Codex = 実装。`codex exec --sandbox workspace-write -a never`、モデルは `~/.codex/config.toml` の既定に従う）
- ウェブ検索: `/devkit:codex-search`

ChatGPT Pro 相談の住み分け:

- ブラウザ経由: `/devkit:gpt-pro` または `$gpt-pro`（Chrome Default profile + CDP 前提）
- ChatGPT アプリ経由: `$computer-use-chatgpt-pro`

ChatGPT ブラウザ経路の実行契約:

- API-first にはせず、Chrome の通常 `Default` profile を正本にする
- 通常 Chrome が CDP 無効で起動中なら、必要に応じて Chrome の再起動まで許可する
- `localhost,127.0.0.1,::1` は proxy bypass 対象にする
- backend 優先順は `agent-browser`、Playwright `connectOverCDP`、runtime の Chrome 拡張経路
- 診断と実行の共通入口は `plugins/devkit/scripts/chrome_chatgpt_runner.py`
- Windows PowerShell / cmd では `py -3`、macOS / Linux / WSL / Git Bash では `python3` を使う

```bash
py -3 plugins/devkit/scripts/chrome_chatgpt_runner.py diagnose
py -3 plugins/devkit/scripts/chrome_chatgpt_runner.py --restart-chrome gpt-pro "調査内容"
py -3 plugins/devkit/scripts/chrome_chatgpt_runner.py --restart-chrome deep-research "調査内容"
```

補足（Codex の `$dig` 利用）:

- global/shared skill は `~/.agents/skills/<skill-name>` に置く
- project 専用 skill は `<repo>/.agents/skills/<skill-name>` に置く
- 例: `~/.agents/skills/dig`、`business-docs/.agents/skills/load-todo`
- `~/.codex/skills` は user-managed skill の配置先としては使わない
- `~/.agents/skills/dig/SKILL.md` は UTF-8 BOM なしであること（BOM があると frontmatter の `---` を解釈できず `$dig` が読み込まれない）
- `dig-core` / `dig-codex` などの内部 adapter は `~/.agents/skills` へは公開せず、shared source の `plugins/devkit/skills/` から `dig` が相対参照する

## Nightly Maintainer

cross-repo の nightly maintenance 用に、共有 skill と共通 runner を追加した。

- shared skill:
  - `repo-maintainer`: nightly / drift / weekly lane の repo 保全更新
  - `repo-maintainer-init`: 各 repo の scaffold 生成
- 共通 runner: `plugins/devkit/scripts/repo_maintainer.py`
- target repo 側の正本: `.devkit/repo-maintainer.toml`

初期化:

```bash
python plugins/devkit/scripts/repo_maintainer.py init-scaffold --repo /path/to/target-repo
```

手動実行:

```bash
python plugins/devkit/scripts/repo_maintainer.py run --repo /path/to/target-repo
```

`init-scaffold` は target repo に次を生成する:

- `.devkit/repo-maintainer.toml`
- `MEMORY.md`
- `logs/skills/`
- `reviews/daily/`
- `reviews/weekly/`
- PowerShell / POSIX wrapper
- Windows Task Scheduler / macOS `launchd` / Linux `systemd timer` / cron の template

補足:

- runner は temp worktree 上で Codex を実行し、branch / PR / auto-merge を処理する。
- AI review は `review_commands`、ローカル checks は `check_commands` に寄せる。
- auto-merge は `git.auto_merge=true` かつ review/check 通過時だけ有効。

## 更新

### 推奨コマンド

```bash
update-devkit
update-devkit --version
```

互換 alias:

```bash
update-ccx
update-ccx --version
```

更新内容:

- Claude Code / Codex CLI / OpenCode の install / update
- 保存済みの shared source checkout から Codex / OpenCode の DevKit 管理 user-level assets を再同期
- Codex の公開 skill は `~/.agents/skills` に同期する
- Codex / OpenCode の top-level skills は公開入口だけを再同期し、退役した internal adapter link は掃除する
- project `AGENTS.md` / `CLAUDE.md` の workflow sync は行わない
- `--runtime codex|opencode` を付けた場合は、その runtime の CLI と user-level assets だけを更新する

ハーネスだけ手動で回したい場合:

```bash
uv sync --project plugins/devkit --group dev
uv run --project plugins/devkit python plugins/devkit/scripts/devkit_harness.py verify-fast
uv run --project plugins/devkit python plugins/devkit/scripts/devkit_harness.py verify-full
```

補足:

- `uv` は DevKit 自身の開発・検証・Claude hook の入口として使う
- `node` / `npm` / `fnm` は外部 CLI の install/update 用にだけ使う
- `mermaid-show` は Node 依存の optional skill だったため公開面から削除した

必要なら OpenCode / Codex を再起動。

更新時の config 挙動:

- DevKit source が有効なら、helper / template を先に `~/.codex` 側へ再同期する
- その後に `~/.codex/config.toml` を再生成する
- `~/.codex/config.local.toml` があればそれも合成する
- config 再生成だけ失敗した場合は直前の config を復元し、更新は警告終了する

更新失敗時:

- Codex 利用自体は継続可能（非ブロック運用）
- 更新コマンドは非ゼロ終了コードで失敗を返す
- `~/.codex/logs/devkit-skill-update-status.json` に成功/失敗の状態が記録される

### Windows の npm 自己修復

PowerShell / cmd 版の `update-devkit` / `update-ccx` は、active/default の fnm 管理 Node に `npm` が見つからない場合、更新処理に入る前に同じ Node バージョンの自己修復を 1 回試す。

実行内容:

1. `npm` の欠落を Setup フェーズで検知する
1. `fnm install <current-version>` と `fnm default <current-version>` を実行する
1. それでも `npm` が戻らない場合は壊れた install root を `.update-ccx-broken.<timestamp>` として退避し、同じバージョンを再取得する
1. 修復できなければ npm ベースの更新を `SKIPPED` にし、Node version / install root / expected npm path を含む診断を 1 件だけ出す

補足:

- 別の Node バージョンへは自動で切り替えない
- `other_npm_ready_versions=` は手動復旧候補として表示するだけで、自動 fallback には使わない

### Windows の Codex 自動移行

PowerShell / cmd 版の `update-devkit` / `update-ccx` は、`%USERPROFILE%\.npmrc` に legacy な `prefix=C:\Users\<username>\.npm-global` がある場合だけ Codex を自動移行する。

実行内容:

1. `~/.npmrc.update-ccx.bak.<timestamp>` を作成
1. 旧 prefix から `@openai/codex` を uninstall
1. `.npmrc` から上記 `prefix=` 行だけ削除
1. 現在の Windows npm global prefix (`npm config get prefix`) に `@openai/codex` を再 install
1. その prefix が user PATH に無ければ先頭へ追加

補足:

- それ以外の custom prefix は自動変更しない
- 既存の standalone `codex.exe` は削除しない
- `where.exe codex` に複数候補がある場合は warning を表示する
- Windows で実行中の `codex.exe` がロックされている場合、Codex CLI 自己更新は warning 付きで `SKIPPED` になる

### インストール方法の自動検出

スクリプトは各ツールのインストール方法を自動検出し、適切な更新コマンドを実行する。

| ツール | 検出方法 | 更新コマンド |
|--------|---------|-------------|
| Claude Code (native) | `claude update --help` の存在 | `claude update` |
| Claude Code (homebrew-cask) | `brew list --cask claude` | `brew upgrade --cask claude` |
| Claude Code (npm) | node_modules パス | `npm update -g @anthropic-ai/claude-code` |
| Codex CLI (npm) | `Get-Command codex` / `where.exe codex` / Windows npm global prefix | `npm install -g @openai/codex` |
| Codex CLI (brew) | `brew list codex` | `brew upgrade codex` |
| opencode (npm) | `npm list -g opencode-ai` | `npm install -g opencode-ai` |
| opencode (brew) | `brew list opencode` | `brew upgrade opencode` |

### 出力例

```
=== Claude Code, Codex CLI, opencode & DevKit ===
Environment: wsl

[Before]
claude:   1.0.57 (native)
codex:    0.1.2505301636 (npm)
opencode: 0.3.5 (npm)

Updating Claude Code (native)... ✓
Updating Codex CLI (npm)... ✓
Updating opencode (npm)... ✓
✓ Codex runtime synced
✓ OpenCode runtime synced

[After]
claude:   1.0.58
codex:    0.1.2505301636
opencode: 0.3.5

✓ Update completed
```

## ロールバック

- `update-devkit` は project `AGENTS.md` / `CLAUDE.md` を変更しないため、ロールバック対象は CLI と user-level assets に限られる。
- Codex を外す場合は `~/.agents/skills` と `~/.codex` 配下の DevKit helper / template / config assets を削除する。
- OpenCode を外す場合は `~/.config/opencode` 配下の DevKit 管理 assets を削除する。
- project 単位で workflow sync 済みの `AGENTS.md` / `CLAUDE.md` は別途手動で管理する。

## レビューゲートと昇格制

devkit のワークフローでは、agent team review を前提としつつ、Codex Spark CLI を標準レビューゲートに使う。このセクションは全 runtime 共通の**運用契約**であり、runtime ごとの hook や automation は一部だけを機械強制してよい。

### 標準ゲート

全 runtime 共通で次の順序を使う:

| 優先度 | コマンド / 手段 | 条件 |
|--------|-----------------|------|
| 1st | `codex -a never exec review --uncommitted -m gpt-5.3-codex-spark` | Codex CLI が利用可能な場合の標準ゲート |
| 2nd | `codex -a never exec review --uncommitted -m gpt-5.4 -c 'model_reasoning_effort="medium"'` | spark 不可 / レートリミット / timeout / parse failure |
| 3rd | 独立した別 agent reviewer + ユーザー通知 | Codex CLI が unavailable または未導入の場合（ただし dig-codex の Phase 4 は適用外） |

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

`dig-codex` の Phase 4（計画レビュー）は fail-close で運用するため、代替レビューへフォールバックせず停止する。停止時は以下 3 行を必須とする:

- `ERROR_CODE: DIG_CODEX_PLAN_REVIEW_UNAVAILABLE` または `ERROR_CODE: DIG_CODEX_PLAN_REVIEW_BLOCKED`
- `RERUN_COMMAND: <one-line command>`
- `DIAGNOSTIC_COMMAND: <one-line command>`

### dig-claude の block 昇格

`dig-claude` の Phase 4（計画レビュー）は REVIEW_GATE_PLAN が必須。`critical=0 high=0` になるまで修正→再レビューを繰り返し、3 回目の失敗（`plan_review_attempts >= 3`）で `DIG_CLAUDE_REVIEW_BLOCKED` で commit/push を block して停止する。

### MCP 並列実行（Claude Code 運用知見）

Codex MCP サーバー経由のレビューを並列実行する場合の観測結果（2026-03 検証）:

- Claude Code の同一メッセージ内の MCP ツール呼び出しは**逐次処理**される（Claude Code 現行挙動、変更の可能性あり）
- **サブエージェント（Agent ツール）経由**なら同一 codex サーバーに対して真の並列実行が可能（10並列確認済み）
- codex MCP サーバーは **1 インスタンスで十分**（codex2 等の追加は不要）
- dig-claude の Phase 6 では、agent-parallel モードで各 implementer が worktree 内で独立完了した場合に限り、REVIEW_GATE_SUBTASK を並列レビュー可能（REVIEW_GATE_INTEGRATION は別途必須）
- この制約は MCP 経由の呼び出しに適用され、`codex exec` CLI（Bash）とは異なる経路

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

どちらも見つからない場合、CLI review gate は実行できない。通常フェーズでは独立した別 agent reviewer + ユーザー通知へ切り替え、`dig-codex` の Phase 4 は停止する。

## トラブルシュート

### OpenCode / Codex で補完が出ない

- アプリ再起動
- global/shared source の確認:
  ```bash
  cat ~/.codex/devkit/source-root.txt 2>/dev/null || cat ~/.config/opencode/devkit/source-root.txt
  ls -la ~/.agents/skills
  ```
- project 専用 skill を使う場合は repo root でも確認:
  ```bash
  ls -la ./.agents/skills
  ```
- `update-devkit --devkit-only` を再実行して user-level assets を再同期する

### `BLOCKED_LEGACY_SKILLS_ROOT` で止まる

- 旧 OpenSkills 方式で `~/.config/opencode/skills -> ~/.agent/skills` を使っていて、`~/.agent/skills` に DevKit 以外の custom skill が混在している
- custom skill を `~/.agent/skills` から退避してから `update-devkit --runtime opencode --devkit-only` を再実行する

### `update-devkit` / `update-ccx`: command not found

PATH が正しく設定されているか確認:

```bash
echo $PATH | tr ':' '\n' | grep devkit
```

PowerShell / cmd の場合は、Marketplace の `devkit-setup.ps1` を再実行して launcher を再配置する。

### npm update が失敗する

npm のグローバルディレクトリの権限を確認:

```bash
npm config get prefix
ls -la $(npm config get prefix)/lib/node_modules/
```

### Windows: npm グローバルコマンドが見つからない

- PowerShell / cmd 版は、active/default の fnm 管理 Node から `npm` が欠けていると同じ Node バージョンの自己修復を 1 回試す
- 失敗時はエラー内の `install_root=` と `expected_npm=` を確認する
- `other_npm_ready_versions=` が出ている場合、必要なら `fnm default <version>` で手動切替する
- **別バージョンへの自動切替は行わない**
- PATH 変更後はターミナルの再起動が必要

### Windows: Codex migration stopped on unexpected prefix

- `%USERPROFILE%\.npmrc` の `prefix=` を確認する
- `update-devkit` / `update-ccx` が自動移行するのは `C:\Users\<username>\.npm-global` だけ
- 失敗時は `~/.npmrc.update-ccx.bak.<timestamp>` から元に戻せる

### Windows: `where.exe codex` に複数候補がある

- fnm 管理の Codex と standalone `codex.exe` が混在している
- `update-devkit` / `update-ccx` は standalone 側を削除しない
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

1. フルパスで実行するか、PATH にバイナリのディレクトリを追加:

   ```bash
   # fnm の例（Windows ネイティブ）
   export PATH="$HOME/AppData/Roaming/fnm/node-versions/$(fnm current)/installation:$PATH"
   # fnm の例（WSL / macOS / Linux）
   eval "$(fnm env)"
   ```

1. `.bashrc` / `.zshrc` に fnm / nvm の初期化コマンドが含まれているか確認。
   Claude Code の bash 等、初期化スクリプトを読み込まない環境では手動で PATH を設定する必要がある。
