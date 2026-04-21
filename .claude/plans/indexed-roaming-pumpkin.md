# fix: OpenCode sync で Codex ソースパスのレガシーリンクを認識させる

## Context

`update-devkit` 実行時に OpenCode runtime の skill symlink が `BLOCKED_EXISTING_LINK` で更新されない。
原因: 既存の symlink が `~/.codex/devkit/source/plugins/devkit/skills/...`（Codex ソースパス）を指しているが、OpenCode sync のレガシーターゲットリストにこのパスが含まれていないため、未知のリンクとして BLOCKED される。

## 修正対象ファイル

### 1. `plugins/devkit/scripts/devkit-runtime-sync.sh`（bash 版）

**`sync_devkit_opencode_runtime()` 内の 3 箇所に Codex ソースパスを追加:**

#### a. `prune_legacy_opencode_managed_entries`（行 495-499）
- 第 5 引数として `"$user_home/.codex/devkit/source/plugins/devkit/skills"` を追加
- 関数シグネチャ（行 398）で `$5` を受け取るよう変更し、`case` パターン（行 414）に追加

#### b. `prune_devkit_managed_skill_links`（行 500-503）
- 第 4 引数として `"$user_home/.codex/devkit/source/plugins/devkit/skills"` を追加
- 関数は `$@` で可変長引数を処理済みなので呼び出し側の追加のみ

#### c. `ensure_linked_dir`（行 506-511）
- レガシーターゲット引数として `"$user_home/.codex/devkit/source/plugins/devkit/skills/$skill"` を追加
- 関数は `$@` で可変長引数を処理済みなので呼び出し側の追加のみ

### 2. `plugins/devkit/scripts/devkit-runtime-sync.ps1`（PowerShell 版）

**`Ensure-DevKitLinkedDirectory` 関数（行 404）:**
- `[string[]]$AdditionalLegacyTargets = @()` パラメータを追加
- レガシー判定ロジック（行 413-414）で追加ターゲットも照合

**`Sync-DevKitOpenCodeRuntime` 内（行 674-680）:**
- `Ensure-DevKitLinkedDirectory` 呼び出しに `-AdditionalLegacyTargets` で Codex ソースパスとマーケットプレイスパスを渡す

**`Remove-DevKitLegacyOpenCodeManagedEntries`（行 667-671）:**
- Codex ソースパスも認識するよう `-CodexSourceSkillsRoot` パラメータを追加

### 3. `plugins/devkit/.claude-plugin/plugin.json`

- version を patch bump する（例: `4.5.0` → `4.5.1`）
- `plugins/devkit/**` の変更時は Release Rules により必須

### 4. `plugins/devkit/scripts/README.md`

- レガシーリンク移行の挙動変更に関する記述を追記（必要な場合のみ）

## 変更の要約

| ファイル | 変更行数（概算） | 内容 |
|---------|----------------|------|
| `devkit-runtime-sync.sh` | ~10 行 | 呼び出し側にレガシーパス追加 + prune 関数に引数追加 |
| `devkit-runtime-sync.ps1` | ~15 行 | パラメータ追加 + 呼び出し側追加 |
| `plugin.json` | 1 行 | version patch bump |
| `scripts/README.md` | 必要に応じて | レガシー移行挙動の追記 |

## Phase 6: Review Gate 方針

- sizing: `small`（2 ファイル、変更 ~25 行、スクリプト変更なので最低 `medium` 起点）→ `medium` に引き上げ
- team_shape: `standard_team`
- role_assignment: Coordinator=自分, Planner=自分, Implementer=subagent, Reviewer=独立 agent
- REVIEW_GATE_SUBTASK: 必須（medium）
- REVIEW_GATE_INTEGRATION: 必須（medium）

## Phase 5 タスク

- [Task 1] bash 版 `prune_legacy_opencode_managed_entries` 関数に第 5 引数対応を追加
- [Task 2] bash 版 `sync_devkit_opencode_runtime` の 3 箇所の呼び出しに Codex ソースパスを追加
- [Task 3] PowerShell 版 `Ensure-DevKitLinkedDirectory` に `AdditionalLegacyTargets` パラメータ追加
- [Task 4] PowerShell 版 `Sync-DevKitOpenCodeRuntime` の呼び出しに Codex ソースパスを追加
- [Task 5] PowerShell 版 `Remove-DevKitLegacyOpenCodeManagedEntries` に Codex ソースパス対応追加
- [Task 6] `plugin.json` の version を patch bump
- [Task 7] `scripts/README.md` の同期（必要に応じて）

依存: [Task 1] → [Task 2], [Task 3] → [Task 4], [Task 3] → [Task 5]

## 検証方法

1. 事前確認: `ls -la ~/.config/opencode/skills/` で既存の Codex ソースパスへのリンクを確認
2. `update-devkit` を実行し `BLOCKED_EXISTING_LINK` が出ないことを確認
3. `ls -la ~/.config/opencode/skills/` で symlink が正規パス（`<repo>/plugins/devkit/skills/...`）を指していることを確認
4. Codex 側が壊れていないことを確認: `ls -la ~/.agents/skills/` で Codex の symlink も正常か確認
5. pre-push gate で version bump が通ることを確認

## Codex レビュー結果

**critical=0, high=0, medium=2, low=2** → medium 2 件を反映済み
- [medium] plugin.json version bump と README 同期の欠落 → Task 6, 7 として追加
- [medium] テスト方針の不足 → 検証ステップ 1, 4, 5 を追加
- [low] bash 側の位置引数リスク → `prune_legacy_opencode_managed_entries` は 1 箇所からしか呼ばれないため許容
- [low] PS 側の存在性チェック → `Convert-DevKitToFullPath` が未存在パスを空文字列で返すため noop になり安全
