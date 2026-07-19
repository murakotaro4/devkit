# devkit/scripts

DevKit の setup / update / verification scripts を置くディレクトリです。marketplace 配布を正本にし、skill surface は `dig-goal` / `improve-skill` / `setup` / `refactor` / `memory-review` / `handoff` / `backlog` / `catch-up` / `commit-push` の 9 本を扱います。

## Entry Points

### update-ccx

`update-ccx` が唯一の updater です。実装正本は全 OS 共通の `update-ccx.sh` です。旧名称 `update-devkit` は廃止され、同期時に残骸を prune します。

- POSIX: `update-ccx.sh` を直接実行
- Windows: `update-ccx.cmd` が Git for Windows の Bash を探索して `update-ccx.sh` を実行
- 旧 PowerShell チェーン互換: `update-ccx.ps1` を 1 リリースだけ委譲シムとして残し、cmd を経由せず同じ Git Bash 探索と bootstrap を行う

主な責務:

- Claude Code / Codex CLI の install / update
- managed script の配置更新
- v10.1.0 の manifest が存在する場合の旧 Cursor 同期資産の安全 prune
- Codex marketplace `murakotaro4/devkit` の登録確認
- Codex plugin `devkit@murakotaro4` の有効化確認
- `codex plugin marketplace upgrade murakotaro4` による即時反映
- Claude Code marketplace `murakotaro4` の source / repo 検証と update / 再登録
- Claude Code plugin `devkit@murakotaro4` の update / install（実行中セッションには `/reload-plugins` を案内）
- v9 dig-goal migration marker が無い場合の統合前 live skill directory prune
- v6 migration marker が無い場合の旧 DevKit 管理資産 prune

対応引数:

```bash
update-ccx
update-ccx --version
update-ccx --cli-only
update-ccx --devkit-only
```

旧 Cursor 同期資産の移行掃除は `plugins/devkit/skills/setup/scripts/prune_legacy_cursor_sync.py` に安全ロジックを集約します。manifest の hash と一致する通常ファイルだけを prune し、ユーザー改変・symlink・manifest 非掲載ファイルは保持します。`~/.cursor/`、manifest、Python 3.10 以上のいずれかが無い環境では skip し、prune 自体の失敗は他 section の実行後に updater 全体を非ゼロ終了させます。`sync_cursor_skills.py` は v10.1.0 updater の初回更新を成立させる一時互換 stub で、同期せず同じ prune へ委譲します。

#### Windows stage 1 breaking change

Windows でも updater のロジックは `update-ccx.sh` だけに置きます。`update-ccx.cmd` と 1 リリース残置する `update-ccx.ps1` は、Git for Windows の Bash と、同居または `~/.codex/devkit/source-root.txt` 配下の `update-ccx.sh` を見つけて委譲するだけです。WSL の `System32\bash.exe` は使いません。

Windows でも呼び出し側が設定した `HOME` を尊重し、managed files は `$HOME` 配下へ配置します。生成する cmd shim と Codex config templating はコピー先の実パスを参照し、ランチャーの source-root fallback は `HOME`、次に `USERPROFILE` の順で探します。また、非対話 shell では fnm の shell 環境を明示初期化し、失敗時は警告して継続します。

PowerShell を残す責務は、`update-ccx.sh` からの Claude Code native installer 呼び出し、`devkit-codex-config.ps1` による Windows Codex config templating、v6 migration marker を書く前の `Remove-DevKitLegacyScheduledTask` による旧日次タスク削除の 3 点です。旧 PowerShell updater 固有の npm repair、`.npmrc` legacy Codex prefix migration、レジストリからの PATH 再読込は廃止します。install 直後にコマンドが PATH へ現れない場合は警告し、ターミナル再起動を案内します。Cursor legacy manifest の prune では `python3`、`python`、`py -3` の順に Python 3.10 以上を実行確認します。

Windows での継続更新には Git for Windows が必須です。ランチャーは標準の 2 箇所、次に `where git` から導出した `Git\bin\bash.exe` の順で探索します。

### devkit-setup.ps1

Windows の初回 bootstrap 用です。Marketplace 配下から実行し、bash 正本チェーン、Git Bash launcher、PowerShell helper、Windows 用 Codex config template を配置します。継続更新は `update-ccx` を使います。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "$HOME\.claude\plugins\marketplaces\murakotaro4\plugins\devkit\scripts\devkit-setup.ps1"
```

### devkit-codex-config.ps1

Windows の `~/.codex/config.toml` 合成専用です。

- shared template と windows template を結合する
- shared template は model を `gpt-5.6-sol` に固定し、通常・Plan の effort を Medium にする
- `~/.codex/config.local.toml` があれば結合する
- Codex が書く marketplace / plugin runtime section を保持する
- 次回更新時は既存 `config.toml` をバックアップしてから再合成し、旧 DevKit 固定値の `model` は template の `gpt-5.6-sol` へ置き換え、`model_context_window` / `model_auto_compact_token_limit` を削除する
- 削除する旧固定値は `config.local.toml` へ移送せず、local overlay の許可キーも拡張しない
- macOS / Linux / WSL では config 合成を行わない

### devkit-lib.sh / devkit-lib.ps1

update 系 script の共通 library です。

- DevKit source root 解決
- managed file 配置
- command shim 作成
- source-root state 保存
- v9 dig-goal migration marker と統合前 live skill directory prune
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

配布面を検査します。

- `plugins/devkit/skills/` が `dig-goal` / `improve-skill` / `setup` / `refactor` / `memory-review` / `handoff` / `backlog` / `catch-up` / `commit-push` の 9 本と完全一致すること
- `plugins/devkit/statusline/statusline.js` と `plugins/devkit/statusline/install.js` が存在すること
- `plugins/devkit/skills/setup/scripts/setup_terminal_font.py` が存在すること
- `plugins/devkit/templates/codex/config.shared.toml` と `config.windows.toml` が存在すること
- 削除済み directory / script / duplicate manifest / scaffold が存在しないこと
- ルート marketplace manifest の source directory が存在すること
- fake Codex binary による marketplace add / remove / upgrade / plugin add smoke
- fake Claude binary による marketplace update / add と plugin update / install / list failure smoke
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
