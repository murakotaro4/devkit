---
name: "dig-core"
description: "dig 系の共通実行契約。7フェーズの質問・調査・計画・実装・レビュー・完了条件を定義する。"
argument-hint: "[topic]"
allowed-tools: ["Read", "Grep", "Glob", "Bash"]
---

# /dig-core - Shared Contract

> **dig** = runtime 解決と dig-core + adapter への委譲のみ
> **dig-core** = 7フェーズ・ゲート・タスク/コミット契約の SSOT
> **dig-\<adapter\>** = dig-core 契約を runtime 固有ツールにマッピングする adapter

## 共通フェーズ

1. Phase 1: 要件ヒアリング
2. Phase 2: 調査
3. Phase 3: 計画作成
4. Phase 4: 計画レビュー
5. Phase 5: 実装
6. Phase 6: 実装レビューと検証
7. Phase 7: コミットとプッシュ

旧 5 ステップ（質問 / 終了確認 / 分解 / 計画レビュー / 実行）は補助的な理解モデルとしてのみ残す。adapter の正規表現は 7 フェーズを使う。

## エージェントアーキテクチャ

dig のエージェント構成。Orchestrator は委譲と統合のみを担当し、自身では作業しない。

| 役割 | 担当範囲 | 備考 |
|------|---------|------|
| Orchestrator（本体） | フェーズ進行管理・委譲判断・統合・停止判断 | 自身では実装・調査・レビューを行わない |
| Plan agent | Phase 3 計画作成 | Orchestrator から委譲される |
| Eval agent（codex exec） | Phase 4/6 レビュー + Phase 2 調査 + 相談用途 | 外部モデルによる独立評価 |
| Implementer agent | Phase 5 実装 | worktree 分離で並列実行可能 |

- 各 adapter は上記の抽象ロールを runtime 固有ツールにマッピングする
- Orchestrator がどのフェーズをどのエージェントに委譲するかは adapter が定義する
- Eval agent は codex exec を通じて利用し、レビューだけでなく調査・相談にも使える

## Phase 1 契約

- 最低 1 ラウンドの質問を必須とする。質問なしの Phase 1 完了は認めない
- ラウンド数に上限を設けない。完了チェックリストが全て埋まるまで深堀りを続ける
- 1 ラウンドにつき原則 4 問を質問する
- 質問には必ず選択肢（description 付き）を含める。自由入力のみの質問は避ける
- 質問は runtime の質問ツール（AskUserQuestion / AskQuestion / request_user_input 等）を使って行う。テキスト出力で質問を並べない
- 質問は「非自明」「次の判断に効く」ものに限定する
- 完了チェックリスト（全項目が確定するまで Phase 2 に進まない）:
  - [ ] 目的（何を達成するか）
  - [ ] 成功条件（何をもって完了とするか）
  - [ ] 制約（技術的制約、時間制約、互換性要件等）
  - [ ] 非対象（今回やらないこと）
  - [ ] 承認（ユーザーが上記に同意）
- 完了確認: runtime の質問ツールでユーザーに「要件は十分固まりましたか？」を必ず確認する。ユーザーが同意するまで Phase 2 に進まない
- 完了時に `requirements_confirmed` トークンを記録する

### adapter 能力レベル

全 adapter が全ステップを実装するわけではない。runtime の制約に応じた能力レベルを定義:

| adapter | Phase 1-4（計画） | Phase 5-7（実行） | タスク管理 | 備考 |
|---------|-----------------|---------------|-----------|------|
| dig-claude | 全対応 | 全対応（並列含む） | TaskCreate/TaskUpdate/TaskList | フル機能。Phase 4 通過後に Phase 5 Tasks を materialize する |
| dig-cursor | 全対応 | 全対応（単一実行または疑似並列） | TodoWrite | Cursor toolchain 版。Phase 4 通過後に Todo を materialize する |
| dig-codex | 全対応 | 非対応（計画専用） | テキストベース | Plan Mode 内で完結。Phase 5-7 は実行しない |
| dig-opencode | 基本対応 | 非対応（計画専用） | 非対応 | 最小構成。Phase 5 以降は dig-claude に委譲 |

以下の契約セクションのうち、`REVIEW_GATE_PLAN` は全 adapter に適用する。`Phase 5 task materialization`・`mark_complete`・並列実行・`REVIEW_GATE_SUBTASK`・`REVIEW_GATE_INTEGRATION` は Phase 5-7 対応 adapter（dig-claude / dig-cursor）に適用する。計画専用 adapter は Phase 4 の REVIEW_GATE_PLAN まで実行して完了とする。

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
| materialize_phase5_tasks | タスク登録 | Phase 4 通過後、Phase 5 開始時 |
| mark_complete | タスク完了マーク | Phase 5 各タスク・全体完了時 |

- Phase 1-4 では TaskCreate しない。計画・分解・レビューは plan ファイル上のテキストだけで保持する。
- サブタスク分解の SSOT は `decomposition` だが、dig-claude からの Phase 3-4 呼び出しは **plan-only** とする。TaskCreate は行わず、承認済みの分解結果を Phase 5 開始時に materialize する。
- Phase 5 materialization の登録規約:
  - タスク: `[Task 1] <summary>`, `[Task 2] <summary>` ...
  - タスク番号は dig セッションごとに 1 から振り直す
  - `small` でも最低 1 件の `[Task 1]` を作る
  - 各タスクは 5-10 分の単一責務に分解する。What/Where/How/Why/Verify を含める
  - write_scope が重複しないタスク同士は並列実行可能とする
- dig-claude は Phase 4 通過後に、全タスクを一括登録し、task id 群を plan に追記してよい。
- dig-cursor は Phase 4 通過後に、TodoWrite で実装タスクを一括登録し、進捗を TODO 状態で管理する。
- dig-codex は TaskCreate 非対応のため、Phase 1-4 の plan / checklist だけを管理し、Phase 5 materialization は行わない。
- 停止時のタスク cleanup: Phase 5-7 で停止（レビューブロック・codex unavailable 等）した場合:
  1. dig-claude: TaskList で登録済みタスクを取得し、未完了タスクを TaskUpdate(status="cancelled") で取り消す
  2. dig-cursor: TodoWrite で未完了タスクを完了にしないまま保持し、進捗メモに中断理由を記録する
  3. dig-codex: プランファイルのチェックリストを `[x] CANCELLED` に更新
- 複合タスク: Phase 3 で分解済み plan を作成 → Phase 4 review 通過 → Phase 5 materialization → 各完了時に mark_complete。
- 全タスク完了手順（必須）:
  1. 全タスクが完了（dig-claude: TaskList、dig-cursor: TodoWrite の status 確認。単純タスクは該当なし）
  2. コミット契約のコミット前レビュー通過 + `git commit` 成功
  3. 上記2条件を満たした後に全タスクを mark_complete（dig-claude: TaskUpdate(status="completed")、dig-cursor: TodoWrite で `completed`）
  4. 未完了タスクがある場合、または commit 未成功の場合は完了しない
  5. `git push` は完了の条件に含めない（push 失敗はリトライ可能であり、commit 成功で作業は保全されている）

## 並列実行契約

Phase 5 の実行方式を 2 モードで定義する。adapter が自動選択する。

| モード | 条件 | 説明 |
|--------|------|------|
| agent-parallel | Agent ツール利用可。原則これを第一候補とする | orchestrator と implementer を分離し、worktree 分離でサブエージェント実行 |
| tool-parallel | Agent 実行が不可能な部分のみ | 同一コンテキストで順次実行（独立ツール呼び出しは並列化） |

- Agent ツールが利用不可な runtime は常に tool-parallel。
- agent-parallel では Claude Code の Agent tool の `isolation: "worktree"` パラメータを使用。これは Claude Code システムの組み込み機能であり、dig 固有の拡張ではない。
- agent-parallel を常に第一候補とし、single-task でも orchestrator 自身ではなく Agent を実装担当にする。
- ファイル重複がある場合は全面フォールバックせず、Coordinator が `write_scope` を再分割して並列続行を試みる。再分割不能な部分だけ tool-parallel に落とす。
- shared workflow 契約との統合:
  - Phase 3: プランファイルの末尾で sizing / team_shape / role_assignment を確定:
    - sizing policy に基づきサイズ判定: `small`（1ファイル中心）/ `medium`（通常の機能追加）/ `large`（中規模以上・高リスク）
    - サイズから team_shape を決定: `small` → `micro_team`、`medium` → `standard_team`、`large` → `expanded_team`
    - `role_assignment`: dig 本体 = `Coordinator`。`Planner` = dig 本体。`Reviewer` = codex exec。`Implementer` = Agent を優先。`Researcher` = Explore サブエージェント
    - `write_scope`: Where セクションから抽出した対象ファイルリスト。複数 Implementer 時は各サブエージェントのスコープを明記
  - Phase 5: 実行モード確定後に team_shape を再確認し、必要なら AgentTeams を増員する
  - **Reviewer 分離保証**: 全 team_shape で `Reviewer` は `codex exec`（外部モデル）が担当する

## レビュー契約

- レビューゲートは runtime 契約に従う。
- Bash で直接実行できる場合はそれを優先する。
- Bash 実行が unavailable な runtime では、adapter 契約に従って独立 reviewer を代替経路として使ってよい。

### レビュー経路（2本）

Phase 4 と Phase 6 ではレビュー対象が異なる。経路を混同しないこと。

| 経路 | コマンド形式 | 対象 | 使用フェーズ | 制約 |
|------|------------|------|------------|------|
| Path A: 差分レビュー | `codex exec review --uncommitted` | 未コミットの差分 | Phase 6（REVIEW_GATE_SUBTASK / INTEGRATION） | カスタムプロンプト併用不可 |
| Path B: 計画書/プロンプトレビュー | `codex exec -m <model> "<prompt>"` | 計画書ファイル、または任意のプロンプト | Phase 4（REVIEW_GATE_PLAN）、Phase 2 調査 | ファイル入力はサニタイズ必須 |

- Phase 4 で `review --uncommitted` を使うと、計画段階で差分が空の場合にレビューが機能しない
- Phase 6 で Path B を使うと、差分以外のコンテキストが混入する
- adapter は両経路の具体的なコマンド・モデル名・タイムアウトを定義する

### REVIEW_COUNTS マーカー

- Bash 経路を使う場合、レビュー結果の最終行は次の機械可読マーカーを必須とする:
  - `REVIEW_RESULT_MARKER=REVIEW_COUNTS`
  - `REVIEW_COUNTS critical=<int> high=<int>`
- 判定は `critical/high` で行う。
- `REVIEW_COUNTS` がパース不能な場合は「レビュー不能」として扱う。
- 停止条件: `critical=0` かつ `high=0`

### ゲート責任分担

| 責任 | dig-core（この文書） | adapter |
|------|---------------------|---------|
| マーカー形式 | `REVIEW_COUNTS critical=<int> high=<int>` を定義 | — |
| パス基準 | `critical=0 && high=0` を定義 | — |
| ゲート ID | REVIEW_GATE_PLAN / SUBTASK / INTEGRATION / DECOMPOSITION を定義 | — |
| 停止コード名 | — | `DIG_<RUNTIME>_*` プレフィックスで定義 |
| パース失敗時挙動 | — | PRIMARY → FALLBACK → 停止の順序を定義 |
| PRIMARY/FALLBACK コマンド | — | 具体的なモデル名・フラグ・タイムアウトを定義 |

### レビューゲート定義

| ゲートID | 位置 | 対象 | スキップ条件 |
|----------|------|------|-------------|
| REVIEW_GATE_DECOMPOSITION | Phase 3 後（分解実行直後） | 分解結果ファイル | 分解スキップ時 |
| REVIEW_GATE_PLAN | Phase 4 | 実装計画全体 | なし（必須） |
| REVIEW_GATE_SUBTASK | Phase 6 各サブタスク後 | サニタイズ済み diff ファイル | small: 変更5行未満 or ドキュメントのみ。medium/large: スキップ不可 |
| REVIEW_GATE_INTEGRATION | Phase 6 全完了後 | サニタイズ済み統合 diff ファイル | サブタスク1件以下（0件=単純タスク、1件=SUBTASK で済み） |

全ゲートで REVIEW_RESULT_MARKER=REVIEW_COUNTS 契約を共有。

> **独立レビュー保証**: small で REVIEW_GATE_SUBTASK と REVIEW_GATE_INTEGRATION が両方スキップされる場合でも、REVIEW_GATE_PLAN（Phase 4、必須）が独立レビューとして機能する。Phase 6 ゲートのスキップは Phase 4 通過済みが前提であり、独立 reviewer ゼロにはならない。

### medium/large の追加レビュー視点

`medium` 以上では REVIEW_GATE_SUBTASK を全タスクで必須とするだけでなく、以下の追加レビュー視点を含める:

- レビュー prompt に「統合影響・インターフェース契約・パフォーマンス影響」を観点として追加する
- `large` ではさらに「セキュリティ影響・ロールバック可能性」を観点に含める
- adapter は REVIEW_GATE_SUBTASK および REVIEW_GATE_INTEGRATION の codex exec prompt にこれらの観点を sizing に応じて付加する

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

`git push` は AGENTS.md Phase 7 に従い実行するが、dig のコミット契約における必須ステップ（品質ゲート）ではない。push 失敗はリトライ可能であり、ローカル commit 成功時点で作業は保全されている。親タスク完了も `git commit` 成功時点で判定する。

**agent-parallel 時の適用**: 各サブエージェントは worktree 内で上記3ステップ（REVIEW_GATE_SUBTASK 含む）を実行。統合時は REVIEW_GATE_INTEGRATION がコミット前レビューに相当し、`--no-ff` マージコミットが `git commit` に相当する。この2ステップで上記3ステップ構成を充足する（`git add` は merge 操作に内包）。

## サブエージェント戦略

dig 全体を一度にサブエージェント化しない。段階的に切り出す。

| 優先度 | 対象 | 理由 |
|--------|------|------|
| 1st | Phase 4 Eval（レビューゲート） | codex exec 1本で完結する薄いサブエージェント。失敗時の影響が限定的 |
| 2nd | Phase 2 調査 | codex exec の相談パターンまたは Explore サブエージェントで委譲 |
| 3rd | Phase 3 Plan | 計画作成を専用 agent に委譲 |
| 後回し | dig 全体のオーケストレーション | 上記の個別切り出しが安定してから検討 |

## codex exec パターン（参照）

adapter が codex exec を使う場面の共通パターン定義。具体的なモデル名・フラグは各 adapter が定義する。

| パターン | コマンド形式 | 用途 | フェーズ |
|---------|------------|------|---------|
| diff review | `codex exec review --uncommitted` | 未コミット差分のレビュー | Phase 6 |
| plan review | `codex exec -m <model> "<review prompt>"` + ファイル入力 | 計画書のレビュー | Phase 4 |
| consultation | `codex exec -m <model> "<advisory prompt>"` | 調査・相談・アドバイス | Phase 2、任意 |
| file review | `codex exec -m <model> "<prompt>"` + サニタイズ済みファイル | ファイルベースのレビュー | Phase 4/6 |

## セッション振り返り（自動実行）

> セッション完了時に毎回実行する。
> エラー・リトライ・ユーザーからの修正指摘があった場合は修正提案を行う。
> 改善点がなければ「振り返り不要」と報告してスキップする。
> **エラー隔離**: 振り返り自体が失敗しても、コミット済みの成果物には影響しない。失敗時は警告メッセージのみ出力し、digワークフローは正常終了とする。

`devkit:improve-skill` を実行。
