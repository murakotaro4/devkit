# Plan: dig ワークフロー強制メカニズムの強化

## Context

前回の `/dig` セッション（remote とローカル同期）で、以下の違反が発生した:

1. **Phase 5 Codex レビューをスキップ** — ExitPlanMode しようとして REVIEW_GATE_PLAN を飛ばした
2. **review iteration を回さなかった** — `critical=0 high=0` になるまで修正→再レビューのループが必要
3. **タスク登録（Phase 6 materialization）を計画に含めなかった**
4. **REVIEW_GATE_SUBTASK / INTEGRATION を計画に明記しなかった**

これらは全て dig-core / dig-claude の既存契約に記載されているが、hook による機械的強制が不足していたため守られなかった。

## 根本原因分析

| 違反 | 根本原因 | 現状の強制 |
|------|---------|-----------|
| Phase 5 スキップ | hook が Phase 5 実行を検証しない。`phase5_approved` は Bash 出力からの受動的検出のみ | 検出のみ（block なし） |
| review iteration 不足 | hook が review 回数や失敗結果を追跡しない | なし |
| Task materialization 未記載 | Phase 4 plan content の検証なし | Phase 6 開始時の block のみ |
| REVIEW_GATE 未記載 | 同上 | なし |

## sizing / team_shape

- **sizing**: `medium` — hook / gate / workflow 契約変更を含む
- **team_shape**: `standard_team`
- **role_assignment**:
  - `Coordinator` + `Planner`: dig 本体
  - `Implementer`: Agent（worktree 分離）
  - `Reviewer`: `codex exec`（独立外部モデル）
- **write_scope**:
  - Task 1: memory files + `MEMORY.md`
  - Task 2: `pre_tool_gate.py`, `post_task_tracker.py`, `workflow_state.py`, `user_prompt_submit.py`, `stop_dig_session.py`
  - Task 3: `AGENTS.md`, `plugins/devkit/shared/workflow.md`, `README.md`, `plugins/devkit/scripts/README.md`
  - Task 4: `plugins/devkit/.claude-plugin/plugin.json`

## 3 層対策

### Layer 1: feedback memory（全セッションで即効）

**対象ファイル**: `/Users/murakotaro/.claude/projects/-Users-murakotaro-PycharmProjects-devkit/memory/`

4 件の feedback memory を保存。

> **注**: 保存先パスは Claude Code の auto memory 仕様（`~/.claude/projects/<project-hash>/memory/`）に従う。これはユーザーごとのローカル設定であり、リポジトリに共有するものではない。共有すべきルールは Layer 3（AGENTS.md）で管理する。

1. **`feedback_dig_phase5_review.md`**: dig セッションで Phase 5 Codex レビューを絶対にスキップしない。ExitPlanMode 前に必ず `codex exec` で REVIEW_GATE_PLAN を実行し、`critical=0 high=0` を確認する
2. **`feedback_dig_review_iteration.md`**: Codex レビューで `critical>0` または `high>0` が出たら、計画を修正して再レビューを繰り返す。`critical=0 high=0` になるまで ExitPlanMode しない。最大 3 回まで。4 回目で停止
3. **`feedback_dig_task_materialization.md`**: dig の計画には必ず Phase 6 タスク materialization（親タスク + サブタスク一覧 + 依存関係）を含める
4. **`feedback_dig_review_gates.md`**: dig の計画には必ず各タスクの REVIEW_GATE_SUBTASK 判定（スキップ可否含む）と REVIEW_GATE_INTEGRATION 判定を明記する

### Layer 2: hook 強化（機械的 block/warn 追加）

#### 2a. `pre_tool_gate.py` の強化

**ファイル**: `plugins/devkit/scripts/workflow/pre_tool_gate.py`

変更点:
1. **git commit を block に昇格**（現在は warn のみ）
   - `plan_review_completed` AND `implementation_review_completed` が phases_passed に両方ない場合は block
   - メッセージ: "Phase 5 と Phase 7 のレビューが完了していません"
2. **git push を block に昇格**（現在は warn のみ）
   - `commit_review_completed` が phases_passed にない場合は block
   - メッセージ: "Phase 8 のコミットレビューが完了していません"

#### 2b. `post_task_tracker.py` の強化

**ファイル**: `plugins/devkit/scripts/workflow/post_task_tracker.py`

変更点:
1. **review iteration counter の追加**
   - dig state に `plan_review_attempts: 0` フィールドを追加
   - **検出パターンの汎化**: `REVIEW_COUNTS critical=<int> high=<int>` を `REVIEW_RESULT_MARKER=REVIEW_COUNTS` マーカー行の有無に関わらず、Bash 出力中の `REVIEW_COUNTS critical=(\d+) high=(\d+)` 正規表現でパースする。`/tmp/dig_plan_review_*` ファイルパスの存在を検出条件から外し、マーカー行のみで判定する。これにより codex exec 以外の独立 reviewer 出力にも対応
   - `critical=0 high=0` の場合のみ `phase5_approved = True` に設定（現状通り）
   - `critical>0` または `high>0` の場合はカウントのみ更新し、`phase5_approved` は False のまま
2. **max 3 回制限**
   - 3 回まで再レビュー可。4 回目（`plan_review_attempts >= 3` かつ最新結果が `critical>0` or `high>0`）で `DIG_CLAUDE_REVIEW_BLOCKED` メッセージを出力

#### 2c. `workflow_state.py` の強化

**ファイル**: `plugins/devkit/scripts/workflow/workflow_state.py`

変更点:
1. `default_dig_state()` に `plan_review_attempts: 0` を追加

#### 2d. `user_prompt_submit.py` の強化

**ファイル**: `plugins/devkit/scripts/workflow/user_prompt_submit.py`

変更点:
1. `/dig` セッション開始時の dig state 初期化で `plan_review_attempts: 0` を明示的に設定する（既存の `phase5_approved: False`, `phase6_tasks_registered: False` と同列に追加）

#### 2e. `stop_dig_session.py` の強化

**ファイル**: `plugins/devkit/scripts/workflow/stop_dig_session.py`

変更点:
1. dig セッション終了時の state リセットで `plan_review_attempts: 0` を明示的に含める（既存の `phase5_approved: False`, `phase6_tasks_registered: False` と同列に追加）

### Layer 3: 契約文書の明確化

#### 3a. `AGENTS.md`

**ファイル**: `AGENTS.md`

変更点:
1. Phase 5 セクションに「REVIEW_GATE_PLAN は必須。`critical=0 high=0` になるまで修正→再レビューを繰り返す。3 回まで再レビュー可、4 回目で停止」を追記
2. Phase 6 セクションに「計画には Phase 6 タスク materialization（親 + サブタスク + 依存関係）を含めること」を追記
3. Phase 7 セクションに「計画には各タスクの REVIEW_GATE_SUBTASK 判定と REVIEW_GATE_INTEGRATION 判定を明記すること」を追記

#### 3b. `plugins/devkit/shared/workflow.md` への同期

**ファイル**: `plugins/devkit/shared/workflow.md`

AGENTS.md の Shared Workflow セクションと同一内容を同期する（Maintenance Rules 準拠）。Phase 5/6/7 の追記を反映。

#### 3c. README.md の同期

**ファイル**: `README.md`, `plugins/devkit/scripts/README.md`

hook/gate の仕様変更を反映（Maintenance Rules: スクリプトの仕様変更時は README を同期）。

## Phase 6: タスク materialization

### 親タスク
- `[Phase 6] dig ワークフロー強制メカニズムの強化`

### サブタスク

| タスク | 概要 | write_scope |
|--------|------|-------------|
| `[Task 1] feedback memory 保存` | 4 件の feedback memory を作成し MEMORY.md にインデックス追加 | memory files + `MEMORY.md` |
| `[Task 2] hook 強化` | pre_tool_gate.py の block 昇格、post_task_tracker.py の iteration counter + パーサ汎化、workflow_state.py + user_prompt_submit.py + stop_dig_session.py の state リセット | `plugins/devkit/scripts/workflow/` (5ファイル) |
| `[Task 3] 契約文書の明確化` | AGENTS.md + shared/workflow.md + README.md 同期 | `AGENTS.md`, `plugins/devkit/shared/workflow.md`, `README.md`, `plugins/devkit/scripts/README.md` |
| `[Task 4] version bump` | plugin.json の minor version bump | `plugins/devkit/.claude-plugin/plugin.json` |

### タスク依存関係
- Task 1, 2, 3 は独立（並列実行可能）
- Task 4 は Task 2, 3 に依存（コード・契約変更が確定してから version bump）
- 親タスク完了条件: 全サブタスク completed + REVIEW_GATE_INTEGRATION 通過 + git commit 成功

### REVIEW_GATE 計画

- **REVIEW_GATE_SUBTASK (Task 1)**: memory ファイルのみ → ドキュメントのみのためスキップ可
- **REVIEW_GATE_SUBTASK (Task 2)**: hook / gate 変更 → **必須**（sizing policy により medium 起点）
- **REVIEW_GATE_SUBTASK (Task 3)**: AGENTS.md + shared/workflow.md 変更 → **必須**（shared workflow contract 変更）
- **REVIEW_GATE_SUBTASK (Task 4)**: 単一行の version bump → 変更5行未満のためスキップ可
- **REVIEW_GATE_INTEGRATION**: サブタスク 4 件 → **必須**

## 検証

1. feedback memory が正しく保存され、新しいセッションで読み込まれることを確認
2. `pre_tool_gate.py` のテスト:
   - `plan_review_completed` なしで `git commit` → block されること
   - `implementation_review_completed` なしで `git commit` → block されること
   - 両方ありで `git commit` → 通過すること
3. `post_task_tracker.py` のテスト:
   - `REVIEW_COUNTS critical=1 high=0` → `phase5_approved` が False のままであること
   - `REVIEW_COUNTS critical=0 high=0` → `phase5_approved` が True になること
   - `plan_review_attempts` がインクリメントされること
4. `AGENTS.md` の変更が Conventional Commits と AGENTS.md 自身の Maintenance Rules に従っていること
5. `shared/workflow.md` が AGENTS.md の Shared Workflow セクションと一致していること
6. `README.md` と `plugins/devkit/scripts/README.md` が hook 仕様変更を反映していること
7. `plugins/devkit/.claude-plugin/plugin.json` の version bump（minor: workflow contract 変更）
8. 新しいセッション開始時に `plan_review_attempts` が 0 にリセットされることを確認（dig state リセット）
