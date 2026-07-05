# devkit

DevKit は Claude Code / Codex 向けの個人プラグインです。配布する skill は `dig` と `improve-skill` の 2 つに固定し、導入と更新は marketplace を正本にします。

## Migration Notice

v6.0.0 は配布面を整理する breaking release です。

- 削除 skill: `gpt-pro`, `deep-research`, `computer-use-chatgpt-pro`, `codex-search`, `discord-rust-server-ops`, `repo-maintainer`, `repo-maintainer-init`
- 旧 alias / 表記: `/devkit:gpt-pro`, `/devkit:deep-research`, `/devkit:computer-use-chatgpt-pro`, `/devkit:codex-search`, `/devkit:discord-ops`, `/devkit:repo-maintainer`, `/devkit:repo-maintainer-init`
- 削除 script / scaffold: `chrome_chatgpt_runner.py`, `repo_maintainer.py`, `devkit-runtime-sync.*`, `devkit-skill-update.ps1`, `.devkit/`
- symlink 同期は廃止。旧 root 例: `~/.agents/skills`, `~/.agent/skills`, `~/.codex/skills`, `~/.config/opencode/skills`
- OpenCode 配布、`opencode-ai` 更新、旧日次タスク `DevKitSkillsDailyUpdate` は廃止
- 旧 dig adapter 名: `dig-core`, `dig-claude`, `dig-codex`, `dig-cursor`, `dig-opencode`, `codex-impl`, `decomposition`, `devkit-init`
- 単独表記の `AskUserQuestionTool` はハーネス中立の質問手段へ置き換え

v6 の置き換え先は marketplace 配布の `dig` と `improve-skill` です。`update-devkit` は移行時に旧 symlink / 旧 helper / 旧タスクを prune し、以後は Codex marketplace の git source と Claude Code plugin marketplace を正本にします。

## Skills

- `dig`: `/dig` として深掘り、計画、実装委譲、diff review、検証を扱うオーケストレーション skill
- `improve-skill`: skill 改善の調査、設計、レビュー、更新を扱う skill

`dig` は Claude Code と Codex の両親ハーネスを想定します。Claude Code では既存の対話/承認ツールを使い、Codex では plan mode と組み込み plan / agent 機能へ読み替えます。

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

Codex の git marketplace は Codex 起動時に自動アップグレードされます。すぐ反映したい場合だけ `update-devkit` を実行します。

```bash
update-devkit
update-devkit --version
```

`update-ccx` は互換 alias です。

```bash
update-ccx
update-ccx --version
```

`update-devkit` が行うこと:

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

Windows だけ `~/.codex/config.toml` の合成を行います。合成時は DevKit の shared / windows template と `config.local.toml` を結合し、Codex が管理する marketplace / plugin runtime section は保持します。

macOS / Linux / WSL では config 合成を行いません。Codex plugin 登録を正本として扱います。

## Manual Cleanup

`update-devkit` は v6 marker により一度だけ旧資産を prune します。手動で残骸を掃除する場合は、DevKit 管理物だけを対象にしてください。

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
- v6 skill surface / marketplace / smoke 検査
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
- `plugins/devkit/scripts/`: setup / update / check scripts
- `plugins/devkit/templates/`: Windows Codex config templates
- `plugins/devkit/tests/`: deterministic tests

## Release Rule

この repo は Claude Code Marketplace plugin を含みます。

- `plugins/devkit/**` または `.claude-plugin/**` を変更した場合、push 前に `plugins/devkit/.claude-plugin/plugin.json` の version を上げる
- pre-push gate は `origin/main` と同じ version のままなら push を block する
- version の目安:
  - `patch`: docs / bugfix only
  - `minor`: workflow contract / user-visible behavior 変更
  - `major`: breaking change

## Review Policy

この repo でファイル変更を伴う作業は、親エージェントの diff 自レビューに加えて独立 review を 1 回以上実施します。指摘が出た場合は修正後に再 review し、追加 findings がなくなるまで繰り返します。

`dig` を使う場合は、計画レビュー・実装・diff review の backend を計画承認前に選びます。通常の手作業でも `verify-full` を最終 gate として扱います。
