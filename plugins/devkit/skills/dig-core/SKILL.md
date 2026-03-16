---
name: "dig-core"
description: "dig 系の共通実行契約。8フェーズの質問・調査・計画・実装・レビュー・完了条件を定義する。"
argument-hint: "[topic]"
allowed-tools: ["Read", "Grep", "Glob", "Bash"]
---

# /dig-core - Shared Contract

このスキルは `dig` adapter から参照される共通契約である。

## 共通フェーズ（workflow.md 準拠）

1. Phase 1: 依頼確認と体制決め
2. Phase 2: 要件ヒアリング
3. Phase 3: 調査
4. Phase 4: 計画作成
5. Phase 5: 計画レビュー
6. Phase 6: 実装
7. Phase 7: 実装レビューと検証
8. Phase 8: コミットとプッシュ

旧 5 ステップ（質問 / 終了確認 / 分解 / 計画レビュー / 実行）は補助的な理解モデルとしてのみ残す。adapter の正規表現は 8 フェーズを使う。

## Phase 2 契約

- 最低 1 ラウンドの質問を必須とする。質問なしの Phase 2 完了は認めない
- 1 ラウンドにつき原則 4 問を質問する
- 質問には必ず選択肢（description 付き）を含める。自由入力のみの質問は避ける
- 質問は「非自明」「次の判断に効く」ものに限定する
- 完了時に `requirements_confirmed` トークンを記録する
- 成功条件、制約、非対象、承認の 4 点が確定した時点で完了とする

### adapter 能力レベル

全 adapter が全ステップを実装するわけではない。runtime の制約に応じた能力レベルを定義:

| adapter | Phase 1-5（計画） | Phase 6-8（実行） | タスク管理 | 備考 |
|---------|-----------------|---------------|-----------|------|
| dig-claude | 全対応 | 全対応（並列含む） | TaskCreate/TaskUpdate/TaskList | フル機能。Phase 5 通過後に Phase 6 Tasks を materialize する |
| dig-codex | 全対応 | 非対応（計画専用） | テキストベース | Plan Mode 内で完結。Phase 6-8 は実行しない |
| dig-opencode | 基本対応 | 非対応（計画専用） | 非対応 | 最小構成。Phase 6 以降は dig-claude に委譲 |

以下の契約セクションのうち、`REVIEW_GATE_PLAN` は全 adapter に適用する。`Phase 6 task materialization`・`mark_complete`・並列実行・`REVIEW_GATE_SUBTASK`・`REVIEW_GATE_INTEGRATION` は Phase 6-8 対応 adapter（dig-claude）にのみ適用する。計画専用 adapter は Phase 5 の REVIEW_GATE_PLAN まで実行して完了とする。

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
| materialize_phase6_tasks | タスク登録 | Phase 5 通過後、Phase 6 開始時 |
| mark_complete | タスク完了マーク | Phase 6 各タスク・全体完了時 |

- Phase 1-5 では TaskCreate しない。計画・分解・レビューは plan ファイル上のテキストだけで保持する。
- サブタスク分解の SSOT は `decomposition` だが、dig-claude からの Phase 4-5 呼び出しは **plan-only** とする。TaskCreate は行わず、承認済みの分解結果を Phase 6 開始時に materialize する。
- Phase 6 materialization の登録規約:
  - タスク: `[Task 1] <summary>`, `[Task 2] <summary>` ...
  - タスク番号は dig セッションごとに 1 から振り直す
  - `small` でも最低 1 件の `[Task 1]` を作る
  - 各タスクは 5-15 分の単一責務に分解する。What/Where/How/Why/Verify を含める
  - write_scope が重複しないタスク同士は並列実行可能とする
- dig-claude は Phase 5 通過後に、全タスクを一括登録し、task id 群を plan に追記してよい。
- dig-codex は TaskCreate 非対応のため、Phase 1-5 の plan / checklist だけを管理し、Phase 6 materialization は行わない。
- 停止時のタスク cleanup: Phase 6-8 で停止（レビューブロック・codex unavailable 等）した場合:
  1. TaskList で登録済みタスクを取得
  2. 未完了タスクを全て TaskUpdate(status="cancelled") で取り消し
  3. dig-codex: プランファイルのチェックリストを `[x] CANCELLED` に更新
- 複合タスク: Phase 4 で分解済み plan を作成 → Phase 5 review 通過 → Phase 6 materialization → 各完了時に mark_complete。
- 全タスク完了手順（必須）:
  1. 全タスクが完了（複合タスク時は TaskList で確認、単純タスクは該当なし）
  2. コミット契約のコミット前レビュー通過 + `git commit` 成功
  3. 上記2条件を満たした後に全タスクを mark_complete（TaskUpdate(status="completed")）
  4. 未完了タスクがある場合、または commit 未成功の場合は完了しない
  5. `git push` は完了の条件に含めない（push 失敗はリトライ可能であり、commit 成功で作業は保全されている）

## 並列実行契約

Phase 6 の実行方式を 2 モードで定義する。adapter が自動選択する。

| モード | 条件 | 説明 |
|--------|------|------|
| agent-parallel | Agent ツール利用可。原則これを第一候補とする | orchestrator と implementer を分離し、worktree 分離でサブエージェント実行 |
| tool-parallel | Agent 実行が不可能な部分のみ | 同一コンテキストで順次実行（独立ツール呼び出しは並列化） |

- Agent ツールが利用不可な runtime は常に tool-parallel。
- agent-parallel では Claude Code の Agent tool の `isolation: "worktree"` パラメータを使用。これは Claude Code システムの組み込み機能であり、dig 固有の拡張ではない。
- agent-parallel を常に第一候補とし、single-task でも orchestrator 自身ではなく Agent を実装担当にする。
- ファイル重複がある場合は全面フォールバックせず、Coordinator が `write_scope` を再分割して並列続行を試みる。再分割不能な部分だけ tool-parallel に落とす。
- shared workflow 契約との統合:
  - Phase 4: プランファイルに workflow Phase 1（依頼確認と体制決め）準拠の初期値を記載:
    - sizing policy に基づきサイズ判定: `small`（1ファイル中心）/ `medium`（通常の機能追加）/ `large`（中規模以上・高リスク）
    - サイズから team_shape を決定: `small` → `micro_team`、`medium` → `standard_team`、`large` → `expanded_team`
    - `role_assignment`: dig 本体 = `Coordinator`。`Planner` = dig 本体。`Reviewer` = codex exec。`Implementer` = Agent を優先。`Researcher` = Explore サブエージェント
    - `write_scope`: Where セクションから抽出した対象ファイルリスト。複数 Implementer 時は各サブエージェントのスコープを明記
  - Phase 6: 実行モード確定後に team_shape を再確認し、必要なら AgentTeams を増員する
  - **Reviewer 分離保証**: 全 team_shape で `Reviewer` は `codex exec`（外部モデル）が担当する

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
| REVIEW_GATE_DECOMPOSITION | Phase 4 後（分解実行直後） | 分解結果ファイル | 分解スキップ時 |
| REVIEW_GATE_PLAN | Phase 5 | 実装計画全体 | なし（必須） |
| REVIEW_GATE_SUBTASK | Phase 7 各サブタスク後 | サニタイズ済み diff ファイル | 変更5行未満 or ドキュメントのみ |
| REVIEW_GATE_INTEGRATION | Phase 7 全完了後 | サニタイズ済み統合 diff ファイル | サブタスク1件以下（0件=単純タスク、1件=SUBTASK で済み） |

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

## セッション振り返り（自動実行）

> セッション完了時に毎回実行する。
> エラー・リトライ・ユーザーからの修正指摘があった場合は修正提案を行う。
> 改善点がなければ「振り返り不要」と報告してスキップする。
> **エラー隔離**: 振り返り自体が失敗しても、コミット済みの成果物には影響しない。失敗時は警告メッセージのみ出力し、digワークフローは正常終了とする。

`devkit:improve-skill` を実行。
