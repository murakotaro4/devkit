# devkit

DevKit は Claude Code / Codex / Cursor 向けの個人開発キットです。配布する skill は `dig-goal` / `improve-skill` / `setup` / `refactor` / `memory-review` / `handoff` / `backlog` / `catch-up` / `commit-push` の 9 本にし、Claude Code / Codex の導入と更新は marketplace、Cursor への配布は Claude Code plugin 経由を正本にします。Node statusline も plugin に同梱します。

## Migration Notice

v6.0.0 は配布面を整理する breaking release です。

- 削除 skill: `gpt-pro`, `deep-research`, `computer-use-chatgpt-pro`, `codex-search`, `discord-rust-server-ops`, `repo-maintainer`, `repo-maintainer-init`, `amazon-search`
- 旧 alias / 表記: `/devkit:gpt-pro`, `/devkit:deep-research`, `/devkit:computer-use-chatgpt-pro`, `/devkit:codex-search`, `/devkit:discord-ops`, `/devkit:repo-maintainer`, `/devkit:repo-maintainer-init`
- 削除 script / scaffold: `chrome_chatgpt_runner.py`, `repo_maintainer.py`, `devkit-runtime-sync.*`, `devkit-skill-update.ps1`, `.devkit/`
- symlink 同期は廃止。旧 root 例: `~/.agents/skills`, `~/.agent/skills`, `~/.codex/skills`, `~/.config/opencode/skills`
- OpenCode 配布、`opencode-ai` 更新、旧日次タスク `DevKitSkillsDailyUpdate` は廃止
- 旧 dig adapter 名: `dig-core`, `dig-claude`, `dig-codex`, `dig-cursor`, `dig-opencode`, `codex-impl`, `decomposition`, `devkit-init`
- 単独表記の `AskUserQuestionTool` はハーネス中立の質問手段へ置き換え

v6 の置き換え先は marketplace 配布の `dig` と `improve-skill` です。updater は移行時に旧 symlink / 旧 helper / 旧タスクを prune し、以後は Codex marketplace の git source と Claude Code plugin marketplace を正本にします。

## Skills

- `dig-goal`: `/dig-goal` として深掘り、計画、実行オーケストレーション、現セッション自律実行を扱う skill。同席実装は worktree 上の実装済み diff と統合(既定は PR の提出 + CI green 確認 + merge。PR 不可 repo では直接統合の merge / push)まで完遂し、現セッション自律実行は独立レビュー後にそのまま実行して `.claude/goal-runs/` の完了レポートまで作成する。起動プロンプト提示はユーザーが明示した例外形態のみ
- `improve-skill`: skill 改善の調査、設計、レビュー、更新を扱う skill
- `setup`: 対象リポジトリへの DevKit ルール同期、環境前提チェック(claude / codex / cursor-agent / node / uv)、thought-db 接続・updater のユーザー環境同期、旧 updater 名と Cursor 同期資産の残骸 prune、statusline 適用、Windows Terminal の UDEV Gothic NF(GitHub release からのダウンロード)適用を扱う skill
- `refactor`: 技術的負債を棚卸し、優先順位付けと計画作成を行い、実装を `/dig-goal` へ引き継ぐ skill
- `memory-review`: AI メモリを棚卸し、古い前提・矛盾・危険な自動化ルールを監査し、軽微修正または `/dig-goal` 引き継ぎへ整理する skill
- `handoff`: セッション終了時に `.claude/handoff/` へ gitignore 対象の引継ぎドキュメントを書き出す skill
- `backlog`: repo に散らばる残課題の痕跡(`.claude/handoff/` / `.claude/plans/` / `.claude/goal-runs/` / git / gh の open PR)を read-only で横断棚卸しし、ダッシュボードとして提示して実装は `/dig-goal` へ引き継ぐ skill
- `catch-up`: 外部世界のモデル世代・CLI フラグ・ハーネス機能・marketplace の変化を裏取りし、`premises.json` 起点で影響箇所を棚卸しして承認済み範囲を追従更新する skill
- `commit-push`: 未コミット変更を論理グループ(最大 5)に分割し、分割案のユーザー承認・secret 2 層検査・literal pathspec の add・グループ単位 5 段階検証を経て日本語 Conventional Commits で commit し、upstream へ明示単一 refspec で push する skill

使い分けの軸はタスク規模ではなく自律度です。`dig-goal` は、対話しながら worktree 上で実装し統合まで完遂する同席実装、判断を前倒しして独立レビュー後そのまま同一セッションで完遂する現セッション自律実行、定期実行・別ターミナル・別 PC・後で実行・白紙コンテキスト実行を明示した場合の起動プロンプト提示、の 3 形態を扱います。

`dig-goal` と `setup` は Claude Code と Codex の両親ハーネスを想定します。`dig-goal` の Claude 親は計画作成・承認に plan mode / `ExitPlanMode` を既定で使い、Codex 親では plan mode と組み込み plan / agent 機能へ読み替えます。`refactor` は read-only の計画化で終了し、実装は `/dig-goal` 側へ接続します。`memory-review` の監査は read-only とし、書き込みはレポート保存と承認済み軽微修正だけに限定します。構成変更を伴う大きい修正は `/dig-goal` へ引き継ぎます。`handoff` は書き出し専用で、読み込み・自動復元・commit / push は行いません。`backlog` は read-only の横断棚卸しで、handoff が書き出した引継ぎや dig-goal の完了レポートを読む側の工程を担い、実装は `/dig-goal` へ接続します。`catch-up` は外部値の追従専用で、内部メモリ監査は `memory-review`、セッション内エラー起点の改善は `improve-skill retro`、workflow contract の変更は `/dig-goal` を使います。`commit-push` はレビュアー機能を持たない commit / push 専用の工程で、レビューが必要な実装は `/dig-goal` を使います。

Codex への委譲ではモデルを `gpt-5.6-sol`、effort を Medium に固定します（計画レビュー・実装・diff レビュー共通。世代追従は `catch-up` スキルと `premises.json` で管理します）。Max は対応 surface の最深推論、Ultra は並列オーケストレーションとして説明だけに使い、DevKit の選択肢・CLI effort・config 値にはしません。

## Statusline

DevKit は全 OS 対応の Node 単一実装 statusline を plugin に同梱します。通常の適用は `/setup` から行います。

手動で適用する場合:

```bash
node <plugin>/statusline/install.js
```

`install.js` は `~/.claude/settings.json` の `statusLine` キーへ冪等マージし、他の設定キーは保持します。設定に焼き込む実行対象は plugin cache ではなく DevKit 管理コピーの `~/.claude/devkit-statusline.js` です。macOS / Linux / WSL / Windows で同じ Node 実装を使います。

表示は 2 行構成です。1 行目に `dir | model | branch` の識別情報を出し、2 行目に context window、5hr、weekly、scoped usage、セッションコストを並べます。表示できる使用率やコストが無い場合は 1 行目だけを出力します。

セッションコストは Claude Code から渡される `cost.total_cost_usd` を使います。`https://open.er-api.com/v6/latest/USD` の `rates.JPY` が取得できる場合は円換算して整数の `¥` 表示にし、取得できない場合は `$8.23` のように USD 表示へフォールバックします。為替レートは statusline cache directory に 24 時間キャッシュします。

weekly usage は reset 時刻が分かる場合、`wk 20% (残り 2d4h)` のようにリセットまでの残り時間を併記します。`DEVKIT_STATUSLINE_NO_FETCH=1` を指定すると、usage API に加えて FX もネットワーク取得せず、有効なキャッシュだけを参照します。FX の有効キャッシュが無い場合は USD 表示のままにします。

## Install

### Claude Code

Claude Code 側は marketplace plugin として導入します。

```bash
claude plugin marketplace add murakotaro4/devkit
claude plugin add devkit@murakotaro4
```

Claude Code の plugin UI を使う環境では、`murakotaro4` marketplace から `devkit` を追加してください。

### Codex

Codex 側も marketplace を正本にします。

```bash
codex plugin marketplace add murakotaro4/devkit
codex plugin add devkit@murakotaro4
```

登録済みか確認する場合:

```bash
codex plugin list --json
```

### Cursor

Cursor は Claude Code plugin のスキルを読み込むため、devkit を Claude Code に導入済みなら追加作業なしで Cursor からも利用できます。v10.1.0 で追加した `~/.cursor/skills` への独自同期は二重表示を招くため v11.0.0 で撤去しました。既存の同期資産は manifest の hash と一致するものだけを `/setup` または `update-ccx --devkit-only` が自動で掃除し、改変済みファイルと manifest 非掲載ファイルは保持します。

## Update

Codex の git marketplace は Codex 起動時に自動アップグレードされます。すぐ反映したい場合だけ `update-ccx` を実行します。

```bash
update-ccx
update-ccx --version
```

`update-ccx` が唯一の updater コマンドです。実装正本は全 OS 共通の `update-ccx.sh` です。旧名称 `update-devkit` は廃止され、`/setup` または updater 自身の更新時に残骸を prune します。

`update-ccx` が行うこと:

- Claude Code / Codex CLI の install / update
- DevKit 管理 script の配置更新
- v10.1.0 の manifest が存在する場合の旧 Cursor skills / templates / scripts / statusline 安全 prune
- Codex marketplace `murakotaro4/devkit` の登録確認
- `devkit@murakotaro4` の有効化確認
- `codex plugin marketplace upgrade murakotaro4` による即時反映
- Claude Code marketplace `murakotaro4` の source / repo 検証と update / 再登録
- Claude Code plugin `devkit@murakotaro4` の update / install（実行中セッションには `/reload-plugins` を案内）
- v6 移行 marker が無い場合の旧資産 prune

`--cli-only` は CLI 更新のみ、`--devkit-only` は DevKit 管理ファイルと Claude/Codex plugin 登録のみを処理します。

## Windows

Windows の初回 bootstrap は marketplace 配下の `devkit-setup.ps1` を使います。継続更新は `update-ccx.cmd` が Git for Windows の Bash で `update-ccx.sh` を起動します。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "$HOME\.claude\plugins\marketplaces\murakotaro4\plugins\devkit\scripts\devkit-setup.ps1"
```

Windows だけ `~/.codex/config.toml` の合成を行います。合成時は DevKit の shared / windows template と `config.local.toml` を結合し、Codex が管理する marketplace / plugin runtime section は保持します。shared template は model を `gpt-5.6-sol` に固定し、通常・Plan の effort を Medium にします。

次回の Windows 更新では既存 `config.toml` を通常どおりバックアップしてから再合成し、旧 DevKit 固定値の `model` は template の `gpt-5.6-sol` へ置き換え、`model_context_window` / `model_auto_compact_token_limit` を取り除きます。これらの旧値は `config.local.toml` へ移送せず、local overlay の許可キーも拡張しません。

macOS / Linux / WSL では config 合成を行いません。Codex plugin 登録を正本として扱います。

### Windows updater stage 1 breaking change

Windows の updater 実装を PowerShell から bash 正本へ一本化しました。`update-ccx.cmd` は Git for Windows の Bash launcher で、`update-ccx.ps1` は旧チェーン互換のため 1 リリースだけ残す直接委譲シムです。両者は互いを呼ばず、同居する `update-ccx.sh`、次に `~/.codex/devkit/source-root.txt` が指す checkout の script を探します。WSL の `System32\bash.exe` は使いません。

Windows でも明示された `HOME` を尊重し、managed files は `$HOME` 配下へ配置します。生成する cmd shim と Codex config templating はコピー先の実パスを参照し、ランチャーの source-root fallback は `HOME`、次に `USERPROFILE` の順で探します。非対話 Git Bash では fnm の shell 環境も updater が初期化し、初期化できない場合は警告して後続処理を継続します。

PowerShell の残置責務は次の 3 点だけです。

- `update-ccx.sh` から Windows の Claude Code native installer を呼ぶ
- `devkit-codex-config.ps1` を dot-source して Codex config templating を行う
- v6 migration marker を書く前に `devkit-lib.ps1` の `Remove-DevKitLegacyScheduledTask` で旧日次タスクを削除する

旧 `update-ccx.ps1` 固有の npm repair、`.npmrc` legacy Codex prefix migration、レジストリからの PATH 再読込は廃止しました。install 成功直後にコマンドが PATH へ現れない場合、updater は警告とターミナル再起動案内を出して処理を続けます。

Git for Windows が見つからない場合は exit 1 で停止します。探索順は `%ProgramFiles%\Git\bin\bash.exe`、`%ProgramFiles(x86)%\Git\bin\bash.exe`、`where git` の `Git\cmd\git.exe` から導出する `Git\bin\bash.exe` です。

## Manual Cleanup

`update-ccx` は v6 marker により一度だけ旧資産を prune します。廃止済みの旧名称 `update-devkit` の残骸は `/setup` と updater 同期でも削除します。手動で残骸を掃除する場合は、DevKit 管理物だけを対象にしてください。

確認例:

```bash
ls -la ~/.codex/bin
ls -la ~/.codex/devkit
find ~ -name '*.linkbak' -maxdepth 5 2>/dev/null
```

削除候補:

- `*.linkbak`
- 古い `~/.codex/bin` 配下の DevKit helper
- stale な `~/.codex/devkit/source-root.txt`

自作 skill や他 plugin の cache は削除対象にしません。

## Development

DevKit 自身の検証は `uv` ハーネスを正本にします。

```bash
uv sync --project plugins/devkit --group dev
uv run --project plugins/devkit python plugins/devkit/scripts/devkit_harness.py verify-fast
uv run --project plugins/devkit python plugins/devkit/scripts/devkit_harness.py verify-full
```

`verify-fast` / `verify-full` は次を実行します。

- UTF-8 BOM 検査
- skill surface / marketplace / smoke 検査
- legacy migration token 検査
- detect-secrets baseline 照合
- pytest
- plugin version bump gate (`verify-full` のみ)

ローカル hook は `prek.toml` を正本にします。

```bash
prek install --hook-type pre-commit --hook-type pre-push
prek run --all-files --hook-stage pre-push
```

## Repository Layout

- `plugins/devkit/.claude-plugin/plugin.json`: plugin metadata
- `.claude-plugin/marketplace.json`: marketplace manifest
- `plugins/devkit/skills/dig-goal/SKILL.md`: `dig-goal` skill
- `plugins/devkit/skills/improve-skill/SKILL.md`: `improve-skill` skill
- `plugins/devkit/skills/setup/SKILL.md`: `setup` skill
- `plugins/devkit/skills/setup/scripts/prune_legacy_cursor_sync.py`: v10.1.0 の Cursor 独自同期資産を manifest 基準で安全に prune
- `plugins/devkit/skills/setup/scripts/sync_cursor_skills.py`: v10.1.0 updater 初回更新用の一時互換 stub(prune へ委譲)
- `plugins/devkit/skills/refactor/SKILL.md`: `refactor` skill
- `plugins/devkit/skills/memory-review/SKILL.md`: `memory-review` skill
- `plugins/devkit/skills/handoff/SKILL.md`: `handoff` skill
- `plugins/devkit/skills/backlog/SKILL.md`: `backlog` skill
- `plugins/devkit/skills/catch-up/SKILL.md`: `catch-up` skill
- `plugins/devkit/skills/commit-push/SKILL.md`: `commit-push` skill
- `plugins/devkit/premises.json`: 外部前提と repo 内 occurrence のレジストリ
- `plugins/devkit/statusline/`: Node statusline implementation and installer
- `plugins/devkit/scripts/`: setup / update / check scripts
- `plugins/devkit/templates/`: Windows Codex config templates
- `plugins/devkit/templates/rules/`: repository rule sync templates
- `plugins/devkit/tests/`: deterministic tests

## Release Rule

version 運用ルールの正本は `AGENTS.md` の「Release Rules」です。要点:

- `plugins/devkit/**` または `.claude-plugin/**` を変更した場合、push 前に `plugins/devkit/.claude-plugin/plugin.json` の version を上げる
- pre-push gate は version が `origin/main` の version 以下なら push を block する（厳密に上回る必要がある）
- version の目安は patch = docs / bugfix only、minor = workflow contract / user-visible behavior 変更、major = breaking change

## Review Policy

この repo でファイル変更を伴う作業は、親エージェントの diff 自レビューに加えて独立 review を 1 回以上実施します。指摘が出た場合は修正後に再 review し、追加 findings がなくなるまで繰り返します。

`dig-goal` の同席実装を使う場合は、計画レビュー・実装・diff review の backend を計画承認前に選びます。通常の手作業でも `verify-full` を最終 gate として扱います。
