# devkit

DevKit は Claude Code / Codex 向けの個人プラグインです。配布する skill は `dig` / `improve-skill` / `setup` / `refactor` / `memory-review` / `goal-prompt` / `handoff` / `backlog` / `catch-up` の 9 つにし、導入と更新は marketplace を正本にします。v7 では Node statusline も plugin に同梱します。

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

- `dig`: `/dig` として深掘り、計画、実装委譲、diff review、検証を扱うオーケストレーション skill。成果物は worktree 上で実装し、統合(merge / push または PR 提出)まで完了した変更。実装系で計画がまだ無い場合は `dig` が正道で、承認済み計画はゴール化引き継ぎで `goal-prompt` へ渡せる
- `improve-skill`: skill 改善の調査、設計、レビュー、更新を扱う skill
- `setup`: 対象リポジトリへの DevKit ルール同期、環境前提チェック(claude / codex / cursor-agent / node / python3)、thought-db 接続のユーザー環境同期、statusline 適用、Windows Terminal の JetBrainsMono Nerd Font 適用を扱う skill
- `refactor`: 技術的負債を棚卸し、優先順位付けと計画作成を行い、実装を `/dig` へ引き継ぐ skill
- `memory-review`: AI メモリを棚卸し、古い前提・矛盾・危険な自動化ルールを監査し、軽微修正または `/dig` 引き継ぎへ整理する skill
- `goal-prompt`: 不在実行に耐えるレビュー済みゴールファイル + 起動プロンプトを作る skill。実行はユーザーの 1 アクションに分離し、この skill は保存と起動プロンプト + 回収手順の提示で終了する。ゴール本文には `.claude/goal-runs/` への完了レポート書き出しを焼き込み、実行後の検収の界面にする
- `handoff`: セッション終了時に `.claude/handoff/` へ gitignore 対象の引継ぎドキュメントを書き出す skill
- `backlog`: repo に散らばる残課題の痕跡(`.claude/handoff/` / `.claude/plans/` / `.claude/goal-runs/` / git / gh の open PR)を read-only で横断棚卸しし、ダッシュボードとして提示して実装は `/dig` へ引き継ぐ skill
- `catch-up`: 外部世界のモデル世代・CLI フラグ・ハーネス機能・marketplace の変化を裏取りし、`premises.json` 起点で影響箇所を棚卸しして承認済み範囲を追従更新する skill

使い分けの軸は自律度です。対話しながら worktree 上で実装し、統合まで完遂するなら `dig`、任せて離れる作業の指示書を作るなら `goal-prompt`、`dig` で深掘り・計画済みの内容を自律実行へ移すならゴール化引き継ぎを使います。

`dig` と `setup` は Claude Code と Codex の両親ハーネスを想定します。Claude Code では既存の対話/承認ツールを使い、Codex では plan mode と組み込み plan / agent 機能へ読み替えます。`refactor` は read-only の計画化で終了し、実装は `/dig` 側へ接続します。`memory-review` の監査は read-only とし、書き込みはレポート保存と承認済み軽微修正だけに限定します。構成変更を伴う大きい修正は `/dig` へ引き継ぎます。`goal-prompt` は実行前のプロンプト authoring を担い、起動プロンプトと回収手順を提示して終了します。`handoff` は書き出し専用で、読み込み・自動復元・commit / push は行いません。`backlog` は read-only の横断棚卸しで、handoff が書き出した引継ぎや goal-prompt の完了レポートを読む側の工程を担い、実装は `/dig` へ接続します。`catch-up` は外部値の追従専用で、内部メモリ監査は `memory-review`、セッション内エラー起点の改善は `improve-skill retro`、workflow contract の変更は `/dig` を使います。

Codex への委譲ではモデルを `gpt-5.6-sol`、effort を Medium に固定します（計画レビュー・実装・diff レビュー共通。世代追従は `catch-up` スキルと `premises.json` で管理します）。Max は対応 surface の最深推論、Ultra は並列オーケストレーションとして説明だけに使い、DevKit の選択肢・CLI effort・config 値にはしません。

## Statusline

DevKit v7 は全 OS 対応の Node 単一実装 statusline を plugin に同梱します。通常の適用は `/setup` から行います。

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

## Update

Codex の git marketplace は Codex 起動時に自動アップグレードされます。すぐ反映したい場合だけ `update-ccx` を実行します。

```bash
update-ccx
update-ccx --version
```

`update-ccx` が唯一の updater コマンドです。旧名称 `update-devkit` は廃止され、`/setup` または updater 自身の更新時に残骸を prune します。互換 shim や fallback は提供しません。

`update-ccx` が行うこと:

- Claude Code / Codex CLI の install / update
- DevKit 管理 script の配置更新
- Codex marketplace `murakotaro4/devkit` の登録確認
- `devkit@murakotaro4` の有効化確認
- `codex plugin marketplace upgrade murakotaro4` による即時反映
- v6 移行 marker が無い場合の旧資産 prune

`--cli-only` は CLI 更新のみ、`--devkit-only` は DevKit 管理ファイルと Codex plugin 登録のみを処理します。

## Windows

Windows の初回 bootstrap は marketplace 配下の `devkit-setup.ps1` を使います。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "$HOME\.claude\plugins\marketplaces\murakotaro4\plugins\devkit\scripts\devkit-setup.ps1"
```

Windows だけ `~/.codex/config.toml` の合成を行います。合成時は DevKit の shared / windows template と `config.local.toml` を結合し、Codex が管理する marketplace / plugin runtime section は保持します。shared template は model を `gpt-5.6-sol` に固定し、通常・Plan の effort を Medium にします。

次回の Windows 更新では既存 `config.toml` を通常どおりバックアップしてから再合成し、旧 DevKit 固定値の `model` は template の `gpt-5.6-sol` へ置き換え、`model_context_window` / `model_auto_compact_token_limit` を取り除きます。これらの旧値は `config.local.toml` へ移送せず、local overlay の許可キーも拡張しません。

macOS / Linux / WSL では config 合成を行いません。Codex plugin 登録を正本として扱います。

### Windows: v5 からの移行

事前条件はありません。旧 updater のままで問題ありません。v6 の `update-ccx.ps1` は `devkit-lib` 欠落時に一回きり self-heal します。

`update-ccx` を 1 回実行すると、次を自動で処理します。

- repo pull
- managed copy 更新
- 旧 symlink / 旧配布物の prune
- 旧日次タスク `DevKitSkillsDailyUpdate` の解除 <!-- migration-allow -->
- Codex marketplace 登録と `devkit@murakotaro4` の plugin add
- `config.toml` 合成。Codex が管理する runtime section は保持します

確認:

- `codex plugin list` に `devkit@murakotaro4` が installed / enabled として表示される
- 新しい Codex セッションで `$dig` が見える

`RepoNightlyMaintainer-*` 系の旧タスクが残っている場合は、v6 で廃止した repo-maintainer の残骸です。必要に応じて手動で解除してください。

```powershell
Get-ScheduledTask -TaskName "RepoNightlyMaintainer-*" | Unregister-ScheduledTask -Confirm:$false
```

`%USERPROFILE%` 配下に `*.linkbak` が残っている場合は、手動で削除してください。

### Windows: DevKit refresh が「Get-DevKitRepoRoot」で失敗する場合

症状: `update-ccx` の `DevKit refresh` 段階が次のようなエラーで必ず失敗する。

```
用語 'Get-DevKitRepoRoot' は、コマンドレット、関数、スクリプト ファイル、または操作可能なプログラムの名前として認識されません。
```

原因: v7.0.1 未満のインストール済み `~/.codex/bin/update-ccx.ps1` は `devkit-lib.ps1` を関数の内側で dot-source していました。PowerShell の関数内 dot-source は関数の return と同時にスコープが消えるため、後続の `Section-DevKit` が `Get-DevKitRepoRoot` を呼べません。DevKit refresh 自体が新しい updater スクリプトの配布工程のため、旧ビルドのままではこのバグを自己更新で解消できません。

復旧(一度だけ手動実行が必要):

```powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File "$env:USERPROFILE\.claude\plugins\marketplaces\murakotaro4\plugins\devkit\scripts\update-ccx.ps1" --devkit-only
```

marketplace clone にある修正済み updater を一度直接実行すると、`~/.codex/bin/update-ccx.ps1` が新しいスクリプトに置き換わります。以後は通常どおり `update-ccx` を使えます。

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
- v7 skill surface / marketplace / smoke 検査
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
- `plugins/devkit/skills/dig/SKILL.md`: `dig` skill
- `plugins/devkit/skills/improve-skill/SKILL.md`: `improve-skill` skill
- `plugins/devkit/skills/setup/SKILL.md`: `setup` skill
- `plugins/devkit/skills/refactor/SKILL.md`: `refactor` skill
- `plugins/devkit/skills/memory-review/SKILL.md`: `memory-review` skill
- `plugins/devkit/skills/goal-prompt/SKILL.md`: `goal-prompt` skill
- `plugins/devkit/skills/handoff/SKILL.md`: `handoff` skill
- `plugins/devkit/skills/backlog/SKILL.md`: `backlog` skill
- `plugins/devkit/skills/catch-up/SKILL.md`: `catch-up` skill
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

`dig` を使う場合は、計画レビュー・実装・diff review の backend を計画承認前に選びます。通常の手作業でも `verify-full` を最終 gate として扱います。
