# pytest ベースのワークフロー検証基盤の構築

## Context

現在のテスト基盤は standalone スクリプト（check_dig_hooks.py 等）で、以下の問題がある:

1. **カバレッジ不足**: hook ゲートのエッジケース（旧キーマイグレーション、Phase 順序違反、レビュー失敗パターン等）が未検証
2. **E2E シミュレーションがない**: dig セッション全体（Phase 1→7）の通しテストが存在しない
3. **手動実行が面倒**: 個別の `uv run` が必要で、失敗時のデバッグも困難
4. **ドキュメント整合性の断片的検証**: check_dig_routing.py はあるが、Phase 番号の一貫性や相互参照の網羅的検証がない

## 方針

- **pytest を dev dependency として追加** (`[dependency-groups]` で管理)
- `plugins/devkit/tests/` に pytest テストを新設
- 既存の check_*.py は **そのまま維持**（prek / harness 互換）
- pytest テストは hook モジュールを直接 import してユニットテスト + E2E シミュレーション
- prek.toml に `pytest` hook を追加（pre-commit）

## 変更対象ファイル

| # | ファイル | 変更内容 |
|---|---------|----------|
| 1 | `plugins/devkit/pyproject.toml` | pytest dev dependency 追加 + pytest 設定 |
| 2 | `plugins/devkit/tests/__init__.py` | 空ファイル |
| 3 | `plugins/devkit/tests/conftest.py` | 共通 fixtures（isolated_home, dig_session, hook_runner） |
| 4 | `plugins/devkit/tests/test_workflow_state.py` | workflow_state モジュールのユニットテスト |
| 5 | `plugins/devkit/tests/test_pre_tool_gate.py` | ゲート判定ロジックのユニットテスト |
| 6 | `plugins/devkit/tests/test_post_hooks.py` | post_task_tracker + post_ask_user のテスト |
| 7 | `plugins/devkit/tests/test_dig_e2e.py` | dig セッション E2E シミュレーション |
| 8 | `plugins/devkit/tests/test_document_consistency.py` | ドキュメント整合性テスト |
| 9 | `prek.toml` | pytest hook 追加 |
| 10 | `plugins/devkit/scripts/devkit_harness.py` | verify-fast に pytest 実行を追加 |
| 11 | `plugins/devkit/.claude-plugin/plugin.json` | version bump |

## 実装計画

### Task 1: pyproject.toml — pytest 導入 + uv.lock 更新

```toml
[dependency-groups]
dev = ["pytest>=8.0"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["scripts", "scripts/workflow"]
```

実装後に `uv sync --project plugins/devkit --group dev` で uv.lock を更新し、pytest が解決されることを確認する。

### Task 2: conftest.py — 共通 fixtures

```python
@pytest.fixture
def isolated_home(tmp_path):
    """HOME を tmp_path に隔離。workflow state と task files をクリーンに保つ"""
    monkeypatch.setenv("HOME", str(tmp_path))
    return tmp_path

@pytest.fixture
def hook_runner(isolated_home):
    """hook スクリプトを subprocess で実行するヘルパー"""
    def run(script_name, payload):
        ...
    return run

@pytest.fixture
def dig_session(hook_runner):
    """/dig セッションを開始済みの状態を返す"""
    hook_runner("user_prompt_submit.py", {"prompt": "/dig test topic"})
    return session_id
```

### Task 3: test_workflow_state.py — ユニットテスト

テストケース:
- `default_dig_state()` のキー構成
- `ensure_dig_state()` の旧キーマイグレーション（phase5_approved → phase4_approved）
- `ensure_dig_state()` の不正入力ハンドリング
- `sync_dig_tasks_from_store()` の [Task N] マッチング
- `sync_dig_tasks_from_store()` の stale task 除外
- `normalize_phase_token()` の legacy token 変換
- `append_phase()` の重複防止

### Task 4: test_pre_tool_gate.py — ゲート判定テスト

テストケース:
- Phase 1 未完了で plan 編集 → ask
- Phase 1 完了後の plan 編集 → pass
- Phase 4 未完了で ExitPlanMode → ask
- Phase 4 通過 + Tasks 未登録で Edit → block
- Phase 4 通過 + Tasks 登録済みで Edit → pass
- Phase 4 未通過で実装ツール → ask
- codex exec (読取専用) → pass
- codex exec + パイプ (変更系) → block
- review 未完了で git commit → block
- commit review 未完了で git push → block
- dig 非アクティブ時 → pass
- plan ファイルへの Write は Phase 4 gate の例外 → 適切に処理

### Task 5: test_post_hooks.py — PostToolUse テスト

テストケース:
- REVIEW_COUNTS critical=0 high=0 → phase4_approved=True
- REVIEW_COUNTS critical=1 high=0 → phase4_approved=False + attempts++
- 3 回失敗 → review_blocked=True
- REVIEW_COUNTS パース不能 → review_blocked=True
- phase4_approved 後の REVIEW_COUNTS → 無視（Phase 6 レビュー）
- AskUserQuestion 完了 → requirements_confirmed=True + ask_user_count++

### Task 6: test_dig_e2e.py — E2E ワークフローシミュレーション

dig セッション全体を hook 呼び出しで再現:

```
Phase 1: /dig 起動 → AskUserQuestion → requirements_confirmed
Phase 2: 調査（hook 影響なし）
Phase 3: plan ファイル作成（requirements_confirmed 後なので pass）
Phase 4: codex exec review → REVIEW_COUNTS → phase4_approved
Phase 5: TaskCreate [Task 1] → phase5_tasks_registered → Edit pass
Phase 6: git commit（review phases_passed 設定後）→ pass
Phase 7: git push（commit_review_completed 設定後）→ pass
```

注: REVIEW_GATE_SUBTASK / INTEGRATION は hook 強制ではなく adapter 契約（dig-claude 側の運用義務）。E2E テストでは hook が強制する Phase 4/5/commit/push ゲートのみを検証し、adapter 契約の遵守はドキュメント整合性テストで間接検証する。

```
```

異常系:
- Phase 順序スキップ（Phase 4 review なしで実装）
- 旧セッション state でのマイグレーション動作
- stop_dig_session による cleanup

### Task 7: test_document_consistency.py — ドキュメント整合性

テストケース:
- workflow.md と AGENTS.md の 7 フェーズ定義一致
- dig-core のフェーズ一覧と workflow.md の一致
- dig-claude のフェーズ一覧と workflow.md の一致
- workflow state tokens の一覧と ドキュメント定義の一致
- Phase 番号の一貫性（grep で全ファイルの Phase N 参照を検証）
- 停止コードが dig-claude/dig-codex の両方で定義されているか
- レビューコマンドの同期（gpt-5.3-codex-spark / gpt-5.4）

### Task 8: prek.toml + harness 統合

prek.toml に追加:
```toml
[[repos.hooks]]
id = "pytest"
name = "Run pytest"
entry = "uv run --project plugins/devkit --group dev pytest plugins/devkit/tests/ -x -q"
language = "system"
pass_filenames = false
stages = ["pre-commit", "pre-push"]
```

devkit_harness.py の CHECKS_FAST に pytest を追加（`--group dev` 付き）。

scripts/README.md に pytest 実行方法と verify-fast への統合を追記。

### Task 9: plugin.json version bump

4.0.0 → 4.1.0 (minor: テスト基盤追加)

## REVIEW_GATE 判定

| Task | REVIEW_GATE_SUBTASK |
|------|---------------------|
| Task 1 (pyproject.toml) | スキップ可: 設定のみ |
| Task 2 (conftest.py) | 必須: テスト基盤の中核 |
| Task 3 (test_workflow_state) | 必須: hook ロジック検証 |
| Task 4 (test_pre_tool_gate) | 必須: ゲート判定検証 |
| Task 5 (test_post_hooks) | 必須: レビュー判定検証 |
| Task 6 (test_dig_e2e) | 必須: E2E シミュレーション |
| Task 7 (test_document_consistency) | 必須: ドキュメント整合性 |
| Task 8 (prek + harness) | スキップ可: 統合のみ |
| Task 9 (version) | スキップ可 |

REVIEW_GATE_INTEGRATION: 必須

## Codex レビュー指摘対応

| # | 指摘 | 重度 | 対応 |
|---|------|------|------|
| 1 | pytest 実行方式と uv run の整合性 | high | `uv run --group dev pytest` を明示。prek / harness も同じ形式に統一 |
| 2 | uv.lock 更新が未計画 | high | Task 1 に `uv sync --group dev` ステップを追加 |
| 3 | scripts/README.md の更新漏れ | medium | Task 8 に追記を追加 |
| 4 | E2E で REVIEW_GATE_SUBTASK/INTEGRATION を扱う範囲 | medium | hook 強制のみを E2E テスト対象に限定。adapter 契約はドキュメント整合性テストで間接検証 |

## 検証方法

1. `uv sync --project plugins/devkit --group dev` で pytest が使えることを確認
2. `uv run --project plugins/devkit --group dev pytest plugins/devkit/tests/ -v` で全テスト通過
3. 既存の check スクリプトが引き続き動作することを確認:
   - `uv run plugins/devkit/scripts/check_dig_hooks.py`
   - `uv run plugins/devkit/scripts/check_dig_routing.py`
4. `prek run --hook-stage pre-commit` で pytest hook が動作
