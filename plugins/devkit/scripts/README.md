# devkit/scripts

DevKit の setup / update / verification scripts を置くディレクトリです。v7 では marketplace 配布を正本にし、skill surface は `dig` / `improve-skill` / `setup` / `refactor` / `memory-review` / `goal-prompt` / `handoff` / `backlog` / `catch-up` を扱います。

## Entry Points

### update-devkit / update-ccx

`update-devkit` が主名称です。`update-ccx` は互換 alias です。

- POSIX: `update-devkit.sh`, `update-ccx.sh`
- Windows: `update-devkit.ps1`, `update-ccx.ps1`
- cmd launcher: `update-devkit.cmd`, `update-ccx.cmd`

主な責務:

- Claude Code / Codex CLI の install / update
- managed script の配置更新
- Codex marketplace `murakotaro4/devkit` の登録確認
- Codex plugin `devkit@murakotaro4` の有効化確認
- `codex plugin marketplace upgrade murakotaro4` による即時反映
- v6 migration marker が無い場合の旧 DevKit 管理資産 prune

対応引数:

```bash
update-devkit
update-devkit --version
update-devkit --cli-only
update-devkit --devkit-only
```

#### Windows: DevKit refresh が「Get-DevKitRepoRoot」で失敗する場合

症状: `update-ccx` / `update-devkit` の `DevKit refresh` 段階が「用語 'Get-DevKitRepoRoot' は…認識されません」で必ず失敗する。

原因: v7.0.1 未満のインストール済み `~/.codex/bin/update-ccx.ps1` は `devkit-lib.ps1` を関数の内側で dot-source していました。PowerShell の関数内 dot-source は関数の return と同時にスコープが消えるため、後続の `Section-DevKit` が `Get-DevKitRepoRoot` を呼べません。DevKit refresh 自体が新しい updater スクリプトの配布工程のため、旧ビルドのままでは自己更新でこのバグを解消できません。

復旧(一度だけ手動実行が必要): marketplace clone にある修正済み updater を直接実行します。

```powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File "$env:USERPROFILE\.claude\plugins\marketplaces\murakotaro4\plugins\devkit\scripts\update-ccx.ps1" --devkit-only
```

`~/.codex/bin/update-ccx.ps1` が新しいスクリプトに置き換わったあとは、通常どおり `update-ccx` / `update-devkit` を使えます。回帰防止のテストは `plugins/devkit/tests/test_update_bootstrap.py` の `test_update_ccx_ps1_dot_sources_devkit_lib_at_script_scope` です。

### devkit-setup.ps1

Windows の初回 bootstrap 用です。Marketplace 配下から実行し、PowerShell / cmd launcher と Windows 用 Codex config template を配置します。継続更新は `update-devkit` を使います。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "$HOME\.claude\plugins\marketplaces\murakotaro4\plugins\devkit\scripts\devkit-setup.ps1"
```

### devkit-codex-config.ps1

Windows の `~/.codex/config.toml` 合成専用です。

- shared template と windows template を結合する
- shared template は Codex モデルを固定せず、通常・Plan の effort を Medium にする
- `~/.codex/config.local.toml` があれば結合する
- Codex が書く marketplace / plugin runtime section を保持する
- 次回更新時は既存 `config.toml` をバックアップしてから再合成し、旧 DevKit 固定値の `model` / `model_context_window` / `model_auto_compact_token_limit` を削除する
- 削除する旧固定値は `config.local.toml` へ移送せず、local overlay の許可キーも拡張しない
- macOS / Linux / WSL では config 合成を行わない

### devkit-lib.sh / devkit-lib.ps1

update 系 script の共通 library です。

- DevKit source root 解決
- managed file 配置
- command shim 作成
- source-root state 保存
- v6 migration marker と旧資産 prune

## Checks

`devkit_harness.py` が標準入口です。

```bash
uv sync --project plugins/devkit --group dev
uv run --project plugins/devkit python plugins/devkit/scripts/devkit_harness.py verify-fast
uv run --project plugins/devkit python plugins/devkit/scripts/devkit_harness.py verify-full
```

`verify-fast` の順序:

1. `check_utf8_bom.py`
2. `check_skill_surface.py`
3. `check_legacy_migration.py`
4. `check_external_premises.py`
5. detect-secrets baseline 照合
6. pytest

`verify-full` は `verify-fast` に `check_plugin_version_bump.py` を加えます。

### check_utf8_bom.py

git 追跡下の text metadata file に UTF-8 BOM が混入していないかを検査します。

### check_skill_surface.py

v7 の配布面を検査します。

- `plugins/devkit/skills/` が `dig` / `improve-skill` / `setup` / `refactor` / `memory-review` / `goal-prompt` / `handoff` / `backlog` / `catch-up` と完全一致すること
- `plugins/devkit/statusline/statusline.js` と `plugins/devkit/statusline/install.js` が存在すること
- `plugins/devkit/skills/setup/scripts/setup_terminal_font.py` が存在すること
- `plugins/devkit/templates/codex/config.shared.toml` と `config.windows.toml` が存在すること
- 削除済み directory / script / duplicate manifest / scaffold が存在しないこと
- ルート marketplace manifest の source directory が存在すること
- fake Codex binary による marketplace add / remove / upgrade / plugin add smoke
- legacy prune の symlink 削除と user directory 保持
- marker 存在時の no-op
- pwsh がある環境で、実 Codex config template による旧固定値除去と runtime section 保持を確認する Windows smoke

### check_legacy_migration.py

退役 token が docs / skills / scripts に残っていないことを検査します。README の `Migration Notice` と prune 実装だけは旧資産削除の説明に必要なため例外です。

### check_external_premises.py

`plugins/devkit/premises.json` のスキーマ、宣言 occurrence の正確な出現数、未登録出現を検査します。`obsolete_value_patterns` に移した旧値は走査対象でゼロ件であることを強制し、部分移行の取り残しも検出します。走査には tracked file と未追跡 file の両方を含め、モデル名・CLI フラグ・ハーネス判定キー・marketplace 名の repo 内インベントリを同期させます。

この check は `current_value` が外部世界で最新かどうかを検出しません。外部 release note と実機での裏取り、値の追従更新は `catch-up` skill の責務です。実装は CRLF と OS 非依存の path 処理を考慮していますが、Windows 対応設計であり、現 CI (`ubuntu-latest`) では未実証です。

### check_plugin_version_bump.py

`plugins/devkit/**` または `.claude-plugin/**` にコミット済み差分（`origin/main` との merge-base から `HEAD` まで）がある場合、HEAD の `plugins/devkit/.claude-plugin/plugin.json` の version が `origin/main` より大きいことを検査します。未コミットの worktree 差分は対象外です（pre-push 意味論。push されるのは HEAD のため）。

## Removed Runners

v6 では browser automation runner と cross-repo maintenance runner は配布しません。関連する skill / scaffold / tests も配布面から外しています。現在の scripts README に載っていない runner はサポート対象外です。
