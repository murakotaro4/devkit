---
name: "dig-core"
description: "dig 系の共通実行契約。深掘り質問、終了確認、タスク分解、計画レビュー、実行の共通ステップを定義する。"
argument-hint: "[topic]"
allowed-tools: ["Read", "Grep", "Glob", "Bash"]
---

# /dig-core - Shared Contract

このスキルは `dig` adapter から参照される共通契約である。

## 共通ステップ

1. 深掘り質問
2. 終了確認
3. タスク分解（オプション）
4. 計画レビュー（review gate）
5. 実行

### adapter 能力レベル

全 adapter が全ステップを実装するわけではない。runtime の制約に応じた能力レベルを定義:

| adapter | Step 1-4（計画） | Step 5（実行） | タスク管理 | 備考 |
|---------|-----------------|---------------|-----------|------|
| dig-claude | 全対応 | 全対応（並列含む） | TaskCreate/TaskUpdate | フル機能 |
| dig-codex | 全対応 | 非対応（計画専用） | テキストベース | Plan Mode 内で完結。親タスク完了（mark_complete / dig-codex では `mark_parent_done` 関数）は不使用（実行フェーズなし） |
| dig-opencode | 基本対応 | 非対応（計画専用） | 非対応 | 最小構成。Step 5 以降は dig-claude に委譲 |

以下の契約セクションのうち、`REVIEW_GATE_PLAN`（レビュー契約）は全 adapter に適用。`register_parent`（タスク管理契約）はタスク管理対応 adapter（dig-claude, dig-codex）に適用（dig-opencode はタスク管理非対応のため対象外）。`mark_complete`・並列実行・`REVIEW_GATE_SUBTASK`・`REVIEW_GATE_INTEGRATION` は Step 5 対応 adapter（dig-claude）にのみ適用。計画専用 adapter は Step 4 の REVIEW_GATE_PLAN まで実行して完了とする。

## 安全ガード

- 読まないファイル:
  - `.env`, `.env.*`
  - `*.pem`, `*.key`, `id_rsa`
  - `credentials.json`, `secrets.*`
- 広域検索（`**/*`）前に、範囲・目的を提示して承認を得る。

## タスク管理契約

adapter は以下の操作を runtime のツールで実現する。

| 操作 | 目的 | タイミング |
|------|------|-----------|
| register_parent | dig セッション全体の親タスク登録 | Step 2 完了後 |
| mark_complete | タスク完了マーク | Step 5 各サブタスク・全体完了時 |

- サブタスク登録は `decomposition` スキルに委譲（SSOT は decomposition）。ただし decomposition スキルが利用不可な runtime（Codex 等）では、adapter が等価のテキストベース分解を直接実行してよい（dig-codex 参照）。
- register_parent で作成した親タスクを decomposition の Phase 6 本体として使用する。プランファイルに `parent_task_id: <id>` 行を記載し、decomposition はこれを authoritative input として Phase 6 本体の taskId を取得する。
  - dig-claude: TaskCreate で `[Phase 6] <topic>` 形式の subject で作成（decomposition の Phase 6.N 命名規則と整合）。taskId を `parent_task_id: <id>` としてプランファイルに記載。decomposition は addBlockedBy で全サブタスクを紐付け。
  - dig-codex: TaskCreate 非対応のため `parent_task_id` は不使用。プランファイル内の `## タスク追跡` セクションで親子関係をテキストベースで管理（チェックボックス形式）。
- 単純タスク（Step 3 スキップ時）: register_parent のみ。Step 5 の実装 + コミット成功後に mark_complete。
- 停止時のタスク cleanup: Step 3-5 で停止（レビューブロック・codex unavailable 等）した場合:
  1. TaskList で親タスクに紐づくサブタスクを取得
  2. 未完了サブタスクを全て TaskUpdate(status="cancelled") で取り消し
  3. 親タスクを TaskUpdate(status="cancelled") で取り消し
  4. dig-codex: プランファイルのチェックリストを `[x] CANCELLED` に更新
- 複合タスク: register_parent → decomposition がサブタスク登録＋親に紐付け → 各完了時に mark_complete。
- 親タスク完了手順（必須）:
  1. 全サブタスクが完了（複合タスク時は TaskList で確認、単純タスクは該当なし）
  2. コミット契約のコミット前レビュー通過 + `git commit` 成功
  3. 上記2条件を満たした後に親タスクを mark_complete（TaskUpdate(status="completed")）
  4. 未完了サブタスクがある場合、または commit 未成功の場合は完了しない
  5. `git push` は親タスク完了の条件に含めない（push 失敗はリトライ可能であり、commit 成功で作業は保全されている）

## 並列実行契約

Step 5 の実行方式を2モードで定義する。adapter が自動選択する。

| モード | 条件 | 説明 |
|--------|------|------|
| agent-parallel | 独立サブタスク3件以上 AND ファイル重複なし AND Agent ツール利用可 | worktree 分離でサブエージェント並列実行 |
| tool-parallel | 上記以外 | 同一コンテキストで順次実行（独立ツール呼び出しは並列化） |

- Agent ツールが利用不可な runtime は常に tool-parallel。
- agent-parallel では Claude Code の Agent tool の `isolation: "worktree"` パラメータを使用。これは Claude Code システムの組み込み機能であり、dig 固有の拡張ではない。
- agent-parallel のサブエージェント失敗時は tool-parallel にフォールバック。
- shared workflow 契約との統合:
  - Step 3: プランファイルに workflow Phase 1 (Intake & Team Declaration) 準拠の初期値を記載:
    - sizing policy に基づきサイズ判定: `small`（1ファイル中心）/ `medium`（通常の機能追加）/ `large`（中規模以上・高リスク）
    - サイズから team_shape を決定: `small` → `micro_team`、`medium` → `standard_team`、`large` → `expanded_team`
    - `role_assignment`: dig 本体 = `Coordinator`。`Planner` = dig 本体。`Reviewer` = codex exec（クロスモデルレビュー、別モデルなので分離要件を満たす）。`Implementer` = サブエージェント（agent-parallel）or dig 本体（tool-parallel）。`Researcher` = Explore サブエージェント（Step 1 のコードベース探索）。expanded_team 時は Researcher が必須参加し、AGENTS.md の最小構成（Implementer(2+) + Researcher or 追加 Reviewer）を充足
    - `write_scope`: Where セクションから抽出した対象ファイルリスト。複数 Implementer 時は各サブエージェントのスコープを明記
  - Step 5: 実行モード確定後に team_shape を再確認:
    - agent-parallel 確定時: `expanded_team` に昇格（Implementer が2+、Researcher = Explore サブエージェントで AGENTS.md の expanded_team 最小構成を充足）
    - agent-parallel 条件不成立でフォールバック時:
      - sizing が `large` の場合: tool-parallel では Implementer が1人のため expanded_team の構造要件（Implementer(2+)）を満たせない。ユーザーに「large タスクだが agent-parallel 不可のため standard_team で実行する」旨を通知し、承認を得てから standard_team で続行。承認なしでは実行しない（dig-claude: AskUserQuestionTool、dig-codex: 計画フェーズのみのため該当なし）
      - sizing が `small`/`medium` の場合: agent-parallel 昇格のみで expanded_team になっていたため `standard_team`（medium）または `micro_team`（small）に戻す
  - **Reviewer 分離保証**: 全 team_shape で `Reviewer` は `codex exec`（外部モデル）が担当。dig 本体が Implementer を兼ねる tool-parallel でも、レビューは codex exec 経由で別モデルが実行するため、workflow の「Implementer と Reviewer の分離」要件を満たす

## レビュー契約

- レビューゲートは runtime 契約に従う。
- Bash で直接実行できる場合はそれを優先する。
- Bash 実行が unavailable な runtime では、adapter 契約に従って独立 reviewer を代替経路として使ってよい。
- Bash 経路を使う場合、レビュー結果の最終行は次の機械可読マーカーを必須とする:
  - `REVIEW_RESULT_MARKER=REVIEW_COUNTS`
  - `REVIEW_COUNTS critical=<int> high=<int>`
- 判定は `critical/high` で行う。
- `REVIEW_COUNTS` がパース不能な場合は「レビュー不能」として扱う。
- 停止条件: `critical=0` かつ `high=0`

### レビューゲート定義

| ゲートID | 位置 | 対象 | スキップ条件 |
|----------|------|------|-------------|
| REVIEW_GATE_DECOMPOSITION | Step 3 後（分解実行直後） | 分解結果ファイル | Step 3 スキップ時 |
| REVIEW_GATE_PLAN | Step 4 | 実装計画全体（既存） | なし（必須） |
| REVIEW_GATE_SUBTASK | Step 5 各サブタスク後 | サニタイズ済み diff ファイル | 変更5行未満 or ドキュメントのみ |
| REVIEW_GATE_INTEGRATION | Step 5 全完了後 | サニタイズ済み統合 diff ファイル | サブタスク1件以下（0件=単純タスク、1件=SUBTASK で済み） |

全ゲートで REVIEW_RESULT_MARKER=REVIEW_COUNTS 契約を共有。

### レビュー前秘匿情報サニタイズ（全ゲート共通・必須）

レビュー対象を外部モデルに送信する際は、必ずサニタイズ済みファイル経由で送信する。
`codex exec` に `git diff --staged` 等のコマンドを直接実行させない（再生成時にマスクが迂回される）。

全ゲートは共通サニタイズ関数 `dig_sanitize` を使用する（各ゲートで個別実装しない）。関数定義は各 adapter の SKILL.md に記載。

手順:
1. diff/テキストをパイプまたは一時ファイルに出力
2. `dig_sanitize <src> <dst>` を実行
3. `dig_sanitize` が非0を返した場合（HIGH_ENTROPY_DETECTED または cp/sed 失敗）: ユーザーに確認を求め、承認なしでは送信しない。ユーザー確認手段がない runtime（Codex 等）では即停止する
4. マスク済みファイルのパスを `codex exec` に渡してレビュー
5. レビュー完了後に一時ファイルを削除

マスク不可（ファイル全体が秘匿対象）の場合: レビュー対象から除外し、ユーザーに通知。

## 停止時出力契約

- 停止時は以下3行を必須とする:
  - `ERROR_CODE: <CODE>`
  - `RERUN_COMMAND: <one-line command>`
  - `DIAGNOSTIC_COMMAND: <one-line command>`
- `STOP_OUTPUT_FIELDS: ERROR_CODE,RERUN_COMMAND,DIAGNOSTIC_COMMAND`

## コミット契約

コミット計画を含む場合は必ず以下の順序:
1. `git add`
2. コミット前レビューゲート
3. `git commit`

`git push` は AGENTS.md Phase 8 に従い実行するが、dig のコミット契約における必須ステップ（品質ゲート）ではない。push 失敗はリトライ可能であり、ローカル commit 成功時点で作業は保全されている。親タスク完了も `git commit` 成功時点で判定する。

**agent-parallel 時の適用**: 各サブエージェントは worktree 内で上記3ステップ（REVIEW_GATE_SUBTASK 含む）を実行。統合時は REVIEW_GATE_INTEGRATION がコミット前レビューに相当し、`--no-ff` マージコミットが `git commit` に相当する。この2ステップで上記3ステップ構成を充足する（`git add` は merge 操作に内包）。

## セッション振り返り（条件付き自動実行）

> 実行フェーズでエラーやリトライが発生した場合のみ実行する。
> エラーがなければ「振り返り不要」と報告してスキップする。
> **エラー隔離**: auto-retro自体が失敗しても、コミット済みの成果物には影響しない。失敗時は警告メッセージのみ出力し、digワークフローは正常終了とする。

`devkit:improve-skill --auto-retro` を実行。
