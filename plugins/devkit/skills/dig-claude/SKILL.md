---
name: "dig-claude"
description: "dig の Claude adapter。AskUserQuestionTool と Codex レビューで dig-core 契約を実行する。"
argument-hint: "[topic]"
allowed-tools: ["Read", "Edit", "Write", "Grep", "Glob", "Bash"]
---

# /dig-claude - Claude Adapter

dig-core 契約を Claude Code 環境で実行する adapter。

> **allowed-tools 注記**: `AskUserQuestionTool`・`Skill`（decomposition呼び出し用）・`Agent`（Explore サブエージェント用）はClaude Codeのシステムツールであり、`allowed-tools` に記載不要（常に利用可能）。

### Plan Mode 共存パターン

Plan Mode が既に有効な場合、dig-core の5ステップをPlanファイルの構造として実行する:

1. **Step 1-2**（質問・終了確認）: AskUserQuestionTool で実行（Plan Mode内で利用可能）
2. **Step 3-4**（計画・分解・レビュー）: Planファイルに記載し、Codexレビューを実行
3. **Step 5**（実行）: ExitPlanMode後に実行

> Plan Modeの解除はdig側から行わない（ユーザーの意図を尊重）。

### フェーズ別ツール制御ガイダンス

- **Step 1-2**（質問・終了確認）: 調査目的の Read/Grep/Glob/Explore のみ使用する。Write/Edit/Bash によるファイル変更は行わない
- **Step 3-5**（分解・計画レビュー・実行）: Write/Edit/Bash を含む全ツールを使用可能

## 実行契約

| 機能 | Claude Code での実現手段 |
|------|--------------------------|
| 質問 | `AskUserQuestionTool` |
| コード探索 | `Explore` サブエージェント / `Grep` / `Glob` |
| 計画記載 | `Write` ツールでプランファイルを直接作成 |
| レビュー | `codex exec` (Bash経由、dig-core `REVIEW_RESULT_MARKER` 契約準拠) |
| 分解 | `devkit:decomposition` スキル |
| タスク管理 | `TaskCreate` / `TaskUpdate` / `TaskList` |
| 並列実行 | `Agent` tool（`isolation: "worktree"`） |

> **EnterPlanMode は呼ばない**。Plan Mode のシステムプロンプトが dig-core の5ステップ契約を上書きするため。プランファイルが必要な場合は Write ツールで直接作成する。

## 共通サニタイズ関数

全レビューゲートで使用する秘匿情報サニタイズ関数:

```bash
dig_sanitize() {
  local src="$1" dst="$2"
  cp "$src" "$dst" || { echo "SANITIZE_CP_FAILED"; return 2; }
  # Layer 1: key=value / key: value パターン
  sed -i -E 's/(api[_-]?key|secret|token|password|credential|private[_-]?key)\s*[=:]\s*\S+/\1=***REDACTED***/gi' "$dst" || { echo "SANITIZE_SED_FAILED"; return 2; }
  # Layer 2-5: 各 sed が失敗したら即停止（未サニタイズ状態での送信を防止）
  sed -i -E 's/(Bearer\s+)\S+/\1***REDACTED***/gi' "$dst" || { echo "SANITIZE_SED_FAILED"; return 2; }
  sed -i -E 's/(Authorization\s*[: ]+)(Basic|Bearer|Token|Digest)?\s*\S+/\1***REDACTED***/gi' "$dst" || { echo "SANITIZE_SED_FAILED"; return 2; }
  sed -i '/-----BEGIN.*PRIVATE KEY-----/,/-----END.*PRIVATE KEY-----/c\***PEM_REDACTED***' "$dst" || { echo "SANITIZE_SED_FAILED"; return 2; }
  sed -i -E 's/("(api[_-]?key|secret|token|password)"\s*:\s*")[^"]+"/\1***REDACTED***"/gi' "$dst" || { echo "SANITIZE_SED_FAILED"; return 2; }
  sed -i -E 's/([?&](token|key|secret|api_key)=)[^&\s]+/\1***REDACTED***/gi' "$dst" || { echo "SANITIZE_SED_FAILED"; return 2; }
  # 出力ファイル存在確認（壊れたファイルの送信を防止）
  [ -s "$dst" ] || { echo "SANITIZE_OUTPUT_EMPTY"; return 2; }
  # フェイルセーフ: 高エントロピー文字列検出
  if grep -qE '[A-Za-z0-9+/=]{64,}' "$dst"; then
    echo "HIGH_ENTROPY_DETECTED"
    return 1
  fi
  return 0
}
```

## 手順

### Step 1: 深掘り質問（dig-core ステップ1）

AskUserQuestionTool で深掘りを続ける。AI判断でコードベース調査を織り交ぜ、具体的な文脈に基づいた質問を行う。

#### AskUserQuestion ベストプラクティス

| ルール | 内容 |
|--------|------|
| 基本 | **必須: 毎回4問を投げる**（`questions` 配列に4問を含めること） |
| 選択形式 | **原則: 複数選択（multiSelect: true）を使用** |
| description | 選択肢には **必ず description を付ける**。トレードオフや影響を説明 |
| 例外 | 終了確認・同意確認は **2問・単一選択でもOK**（明確な意思決定が必要なため） |
| 再質問上限 | 4問に満たない場合、同一ラウンド内で追加質問を投げる。**再質問ラウンドは最大2回まで** |
| 失敗時 | AskUserQuestion が拒否・空返答の場合は `DIG_CLAUDE_QUESTION_FAILED` で停止 |

#### 質問の原則

1. **非自明な質問のみ**: Yes/No で終わる質問は避ける
2. **選択肢を提示**: 2-4つの選択肢とトレードオフを説明
3. **回答から次へ**: ユーザーの回答を基に、さらに深い質問を生成
4. **多角的に**: 一つの観点に固執せず、様々な角度から質問
5. **バランスはAI判断**: 質問のバランス・観点の選択はAIが総合的に判断

#### コードベース調査

- **積極的に調査する**: Explore エージェントを1-3並列起動し、各エージェントに異なる調査焦点を与える
  - 例: (1)対象ファイルの既存実装、(2)関連コンポーネント、(3)テストパターン
- 調査結果を質問の文脈として統合する
- 既存コードのパターンや制約を踏まえた選択肢を提示
- 具体的なファイルパスやコード例を引用して質問を具体化

**調査ガード（読まないファイル）**:
- `.env`、`.env.*` ファイル
- 鍵ファイル（`*.pem`、`*.key`、`id_rsa` 等）
- シークレット/クレデンシャルファイル（`credentials.json`、`secrets.*` 等）

**広域検索の承認フロー**: `**/*` 等の広域検索前に、検索範囲・対象・目的をユーザーに提示し承認を得る。

### Step 2: 終了確認 + 親タスク登録（dig-core ステップ2）

#### AI総合判断

以下を総合的に判断して終了タイミングを決める:
- 必要十分な情報が集まった
- 主要な観点をカバーした
- これ以上深掘りする観点がなくなった

#### 確認（必須）

深掘り結果を要約し、AskUserQuestionTool で確認:
1. 「他の観点で聞きましょうか？」
2. 進め方（計画策定 / 即実行 / 追加調査）

ユーザーが「やめる」「キャンセル」と回答した場合:
```
ERROR_CODE: DIG_CLAUDE_USER_CANCELLED
RERUN_COMMAND: /dig <topic>
DIAGNOSTIC_COMMAND: echo "ユーザーがキャンセル"
STOP_OUTPUT_FIELDS: ERROR_CODE,RERUN_COMMAND,DIAGNOSTIC_COMMAND
```

#### 親タスク登録（ユーザー承認後）

ユーザーが進行を承認した直後に親タスクを登録:

```
TaskCreate:
  subject: "[Phase 6] <topic の要約>"
  description: "dig セッション: <Step 1-2 の要約>"
  metadata: {phase: "implementation_completed"}
  activeForm: "dig セッション実行中"
```

> **Phase 6 互換**: subject を `[Phase 6]` 形式、metadata.phase を `implementation_completed` にすることで、decomposition の既存規約（Phase 6.N 命名、addBlockedBy 紐付け、post-task-tracker.js の完了フック）と完全互換。

親タスクの ID を保持し、プランファイルに `parent_task_id: <id>` として記載。

### Step 3: タスク分解 + 分解レビュー（dig-core ステップ3・オプション）

複雑なタスク（複数ファイル変更、依存関係あり）の場合のみ実行。単純なタスク（1ファイル変更、明確な手順）はスキップ。

#### 3a. プランファイル作成

Write ツールで実装計画の骨格を作成（Step 1-2 の要約 + 分解対象の定義 + `parent_task_id: <id>`）。

workflow Phase 1 準拠の初期値を記載:
- sizing policy に基づきサイズ判定: `small` / `medium` / `large`
- `team_shape`: small → `micro_team`、medium → `standard_team`、large → `expanded_team`
- `role_assignment`: dig = Coordinator/Planner、codex exec = Reviewer、サブエージェント or dig = Implementer、Explore サブエージェント = Researcher（expanded_team 時は必須参加。AGENTS.md の Implementer(2+) + Researcher 最小構成を充足）
- `write_scope`: 対象ファイルリスト

#### 3b. decomposition 呼び出し

`devkit:decomposition <plan_file_path>` を実行。decomposition がサブタスクを TaskCreate で登録し、プランファイルに分解結果セクションを追記。

#### 3c. REVIEW_GATE_DECOMPOSITION

分解結果が書き込まれたプランファイルを対象にレビュー:

```bash
dig_sanitize <plan_file_path> /tmp/dig_decomp_review_$$.md
# 戻り値1(HIGH_ENTROPY) or 2(cp/sed失敗): AskUserQuestionTool でユーザー確認
# 承認 → 続行、拒否/失敗 → rm -f /tmp/dig_decomp_review_$$.md して STOP(DIG_CLAUDE_DECOMP_REVIEW_BLOCKED)
# ユーザー確認なしでは絶対にレビューに進まない

codex exec -m gpt-5.3-codex-spark -c model_reasoning_effort="medium" \
  "以下のファイルのタスク分解セクションをレビューしてください: /tmp/dig_decomp_review_$$.md。
   観点: 元タスクの全範囲カバー、粒度の適切さ（5-30分）、依存関係の矛盾、検証手順の具体性。
   最終行に REVIEW_RESULT_MARKER=REVIEW_COUNTS と REVIEW_COUNTS critical=<int> high=<int> を出力"

rm -f /tmp/dig_decomp_review_$$.md
```

- 判定: dig-core レビュー契約準拠（critical=0 かつ high=0 で通過）
- Step 3 スキップ時はこのゲートもスキップ

### Step 4: 計画レビューゲート（dig-core ステップ4）

> **スキル競合の回避**: このステップは **Bash ツールで `codex exec` を直接実行** する。
> Skill ツールは呼ばない。`/harness-review`・`/codex-review` 等のスキルは使用しない。

Step 4 では:
- **Step 3 実行済みの場合**: プランファイルに実装詳細を追記（必要に応じて）
- **Step 3 スキップの場合（単純タスク）**: Write ツールで最小限のプランファイルを作成（Step 1-2 の要約 + `parent_task_id: <id>` + 実装手順）。これにより REVIEW_GATE_PLAN の入力が保証される
- REVIEW_GATE_PLAN を実行（サニタイズ済みファイル経由）:

```bash
dig_sanitize <plan_file_path> /tmp/dig_plan_review_$$.md
# 戻り値1(HIGH_ENTROPY) or 2(cp/sed失敗): AskUserQuestionTool でユーザー確認
# 承認 → 続行、拒否/失敗 → rm -f /tmp/dig_plan_review_$$.md して STOP(DIG_CLAUDE_REVIEW_BLOCKED)
# ユーザー確認なしでは絶対にレビューに進まない

codex exec -m gpt-5.3-codex-spark -c model_reasoning_effort="medium" \
  "以下のプランファイルをレビューしてください: /tmp/dig_plan_review_$$.md。
   観点: 実現可能性、既存構造との整合性、見落としているエッジケース。
   重大度(critical/high/medium/low)を付けて指摘してください。
   最終行に REVIEW_RESULT_MARKER=REVIEW_COUNTS と REVIEW_COUNTS critical=<int> high=<int> を必ず出力してください"

rm -f /tmp/dig_plan_review_$$.md
```

#### モデル運用切替規則

- `gpt-5.3-codex-spark` を第一候補
- レートリミット時のみ `gpt-5.4`（`model_reasoning_effort="medium"` 維持）へ切替可。実施時は理由を記録
- レートリミット以外の失敗は停止して原因特定

> **共有 workflow との差異**: 共有 workflow の標準ゲートは `codex -a never exec review --uncommitted` サブコマンド用で fallback は `gpt-5.4`。dig-claude も同じく `gpt-5.4` を fallback に使用する（コマンド形式のみ `codex exec -m` が異なる）。

#### レビュー観点

- **実現可能性**: 技術的に実現可能か
- **リスク・欠落**: 見落としているリスクや要素はないか
- **代替アプローチ**: 他の有効なアプローチはないか
- **矛盾・整合性**: 計画内に矛盾はないか

#### レビュー優先規則

利用先リポジトリのエージェント向け正本（CLAUDE.md または CLAUDE.md が参照する AGENTS.md 等）に Codex レビュー規定が存在する場合、レビュープロンプト・判定基準・指摘対応フローはその規定に準拠する。dig-core 契約の REVIEW_COUNTS マーカー出力は追加要件として維持する（リポジトリ規定を拡張する形で統合）。

#### 判定（dig-core レビュー契約準拠）

レビュー出力の末尾2行を確認:
```
REVIEW_RESULT_MARKER=REVIEW_COUNTS     ← マーカー行
REVIEW_COUNTS critical=<int> high=<int> ← カウント行（パース対象）
```

| 重大度 | 対応 |
|--------|------|
| critical/high | 必須修正 → 再レビュー |
| medium/low | 採否判断し理由を記録。同一指摘が2回連続なら記録して次ステップへ |

- `critical=0` かつ `high=0` → Step 5へ
- それ以外 → 修正 → 再レビュー（最大3回）
- `REVIEW_COUNTS` がパース不能（マーカー行なし or フォーマット不一致） → 「レビュー不能」としてユーザーに判断依頼
- 3回超過 → ユーザーに判断依頼

### Step 5: 実行（dig-core ステップ5）

#### 実行モード自動選択

Step 5 冒頭で実行モードを選択:

```
1. TaskList でサブタスク一覧を取得
2. 独立サブタスク（blockedBy なし）をカウント
3. ファイル重複チェック（Where セクションから対象ファイルを抽出）
4. 条件判定:
   - 独立サブタスク >= 3 AND ファイル重複なし → agent-parallel
   - それ以外 → tool-parallel
5. Step 5 開始状態を記録:
   STEP5_START=$(git rev-parse HEAD)
   STEP5_BRANCH=$(git rev-parse --abbrev-ref HEAD)
6. team_shape を再確認:
   - agent-parallel 確定時: expanded_team に昇格 + role_assignment に Researcher/Implementer(2+) を反映
   - フォールバック時（sizing=large）: tool-parallel では Implementer 1人のため expanded_team 不可。AskUserQuestionTool で「large タスクだが agent-parallel 不可のため standard_team で実行する」旨を通知し承認を得る
   - フォールバック時（sizing=small/medium）: 元の team_shape に戻す
```

#### agent-parallel 実行パターン

Agent tool は Claude Code のシステムツールであり、`isolation: "worktree"` と `subagent_type` は組み込みパラメータ。

```
独立サブタスクごとに Agent tool を並列起動:
  - subagent_type: "general-purpose"
  - isolation: "worktree"
  - prompt に含める内容:
    - サブタスクの What/Where/How/Why/Verify
    - REVIEW_GATE_SUBTASK の実行手順（サニタイズ + codex exec）
    - コミット契約（git add → サニタイズ済み diff レビュー → commit）
  - 各サブエージェントは worktree 内で独立に実装・レビュー・コミット
  - **マージ順序（dig-core コミット契約準拠）**:
    1. 全サブエージェント完了後、REVIEW_GATE_INTEGRATION を先に実行（マージ前）
       - 各 worktree の diff を結合してサニタイズ済みファイルを作成:
         ```bash
         (for wt in $WORKTREE_BRANCHES; do git diff $STEP5_START..$wt; done) > /tmp/dig_combined_$$.raw
         dig_sanitize /tmp/dig_combined_$$.raw /tmp/dig_integration_review_$$.diff
         rm -f /tmp/dig_combined_$$.raw
         ```
    2. INTEGRATION レビュー通過後に worktree ブランチを STEP5_BRANCH に `--no-ff` マージ
       - INTEGRATION review が dig-core コミット契約の「コミット前レビュー」に相当
       - `--no-ff` マージコミットが「git commit」に相当
       - この2ステップで dig-core の3ステップ構成（add → レビュー → commit）を充足
    3. マージ成功したサブタスクのみ TaskUpdate(status="completed")
    4. マージ失敗（conflict）時: TaskUpdate せず、ユーザーに通知して手動解決を依頼
  - 失敗時のフォールバック手順:
    1. 成功済みサブエージェントの worktree ブランチをリスト化
    2. INTEGRATION レビュー通過済みの分のみ STEP5_BRANCH にマージ
    3. 失敗サブタスクのみ tool-parallel で再試行
    4. 未マージ worktree は `git worktree remove` でクリーンアップ
  - **停止時 worktree cleanup**: 全 STOP 経路で `git worktree list` → 未マージ worktree を `git worktree remove` でクリーンアップ後に停止
```

#### tool-parallel 実行パターン

```
依存関係順にサブタスクを順次実行。
独立ツール呼び出し（Read, Grep 等）は可能な限り並列化。
各サブタスク完了後の順序:
  1. git add → REVIEW_GATE_SUBTASK（サニタイズ経由） → commit
  2. commit 成功後に TaskUpdate(status="completed")
  ※ レビュー失敗時は TaskUpdate しない（agent-parallel と同一ポリシー）
```

#### REVIEW_GATE_SUBTASK

各サブタスクの実装完了後、コミット前に:

```bash
# サニタイズ済みファイルのみ作成（生 diff をファイルに書き出さない）
git diff --staged | dig_sanitize /dev/stdin /tmp/dig_subtask_review_$$.diff
# 戻り値1(HIGH_ENTROPY) or 2(cp/sed失敗): AskUserQuestionTool でユーザー確認
# 承認 → 続行、拒否/失敗 → rm -f /tmp/dig_subtask_review_$$.diff して STOP(DIG_CLAUDE_SUBTASK_REVIEW_BLOCKED)
# ユーザー確認なしでは絶対にレビューに進まない

codex exec -m gpt-5.3-codex-spark -c model_reasoning_effort="medium" \
  "以下の diff ファイルをレビューしてください: /tmp/dig_subtask_review_$$.diff。
   サブタスク: <subtask_subject>。
   観点: 実装の正当性、副作用の有無、既存テストへの影響。
   最終行に REVIEW_RESULT_MARKER=REVIEW_COUNTS と REVIEW_COUNTS critical=<int> high=<int> を出力"

rm -f /tmp/dig_subtask_review_$$.diff
```

- スキップ条件: 変更5行未満 or ドキュメントのみの変更
- agent-parallel 時: 各サブエージェントの worktree 内で実行（worktree 分離のため競合なし）
- tool-parallel 時: 各サブタスク完了後に順次実行

#### REVIEW_GATE_INTEGRATION

全サブタスク完了後、最終確認として:

```bash
# tool-parallel 時: HEAD に全サブタスクの commit が含まれる
git diff $STEP5_START..HEAD | dig_sanitize /dev/stdin /tmp/dig_integration_review_$$.diff

# agent-parallel 時: マージ前に各 worktree の diff を結合
# for wt in <worktree_branches>; do git diff STEP5_START..$wt; done | dig_sanitize /dev/stdin /tmp/dig_integration_review_$$.diff

# 戻り値1(HIGH_ENTROPY) or 2(cp/sed失敗): AskUserQuestionTool でユーザー確認
# 承認 → 続行、拒否/失敗 → rm -f /tmp/dig_integration_review_$$.diff して STOP(DIG_CLAUDE_INTEGRATION_REVIEW_BLOCKED)
# ユーザー確認なしでは絶対にレビューに進まない

codex exec -m gpt-5.3-codex-spark -c model_reasoning_effort="medium" \
  "以下の diff ファイルをレビューしてください: /tmp/dig_integration_review_$$.diff。
   観点: サブタスク間の統合整合性、インターフェース契約の一貫性、全体的な副作用。
   最終行に REVIEW_RESULT_MARKER=REVIEW_COUNTS と REVIEW_COUNTS critical=<int> high=<int> を出力"

rm -f /tmp/dig_integration_review_$$.diff
```

- スキップ条件: サブタスク1件以下（0件=単純タスクで Step 3 スキップ時、1件=SUBTASK ゲートで済み）
- `$STEP5_START` は Step 5 開始時の `git rev-parse HEAD` で記録
- **実行タイミング**: agent-parallel 時は STEP5_BRANCH へのマージ前に実行（レビュー通過後にマージ）。tool-parallel 時は全サブタスク commit 後に実行

#### 親タスク完了処理

**最終 commit 成功後**に実行。各モードでの「最終 commit」の定義:
- **tool-parallel（2件以上）**: 各サブタスクは既にコミット済み（最後のサブタスク commit 成功 = 全 commit 完了）。REVIEW_GATE_INTEGRATION 通過を確認後、親タスクを完了
- **tool-parallel（1件サブタスク）**: REVIEW_GATE_INTEGRATION スキップ（SUBTASK ゲートで済み）。最後の commit 成功後、親タスクを完了
- **agent-parallel**: INTEGRATION レビュー通過 → STEP5_BRANCH へ `--no-ff` マージ（マージコミット生成を保証）成功を「最終 commit」として親タスクを完了
- **単純タスク（Step 3 スキップ）**: コミット契約（git add → レビュー → commit）成功後に親タスクを完了

```
1. TaskList で親タスクに紐づく全サブタスクを取得
2. 全サブタスクが completed であることを確認
3. TaskUpdate(taskId=<parent_task_id>, status="completed", metadata={phase: "implementation_completed"}) で親タスクを完了
4. 単純タスク（Step 3 スキップ時）: サブタスクなし → git commit 成功後に TaskUpdate(status="completed")
```

> **順序の根拠**: 実装差分がコミット前レビューを通過し、`git commit` が成功してからタスクを完了にする。commit 失敗時にタスクだけ完了済みになる状態を防止。`git push` は親タスク完了の条件に含めない（push 失敗はリトライ可能であり、ローカル commit が成功していれば作業は保全されている）。0件パス（単純タスク）でもコミット前レビュー + commit 成功が親完了の前提条件。

#### 正常完了マーカー（オプション）

正常完了時、以下をオプション出力する（後方互換: 既存downstreamが無視しても問題なし）:
```
DIG_CLAUDE_STATUS: COMPLETED
<1行サマリ>
```

#### コミット契約（dig-core 準拠・3ステップ構成）

コミットが必要な場合は必ず以下の順序:

1. **ステージング**: `git add <files>`
2. **コミット前クロスモデルレビュー**:
   ```bash
   git diff --staged | dig_sanitize /dev/stdin /tmp/dig_commit_review_$$.diff
   # 戻り値1(HIGH_ENTROPY) or 2(cp/sed失敗): AskUserQuestionTool でユーザー確認
   # 承認 → 続行、拒否/失敗 → rm -f /tmp/dig_commit_review_$$.diff して STOP(DIG_CLAUDE_REVIEW_BLOCKED)
   # ユーザー確認なしでは絶対にレビューに進まない
   codex exec -m gpt-5.3-codex-spark -c model_reasoning_effort="medium" \
     "以下の diff ファイルをレビューしてください: /tmp/dig_commit_review_$$.diff。
      観点: <変更内容に応じたレビュー指示>。
      最終行に REVIEW_RESULT_MARKER=REVIEW_COUNTS と REVIEW_COUNTS critical=<int> high=<int> を必ず出力してください"
   rm -f /tmp/dig_commit_review_$$.diff
   ```
   - 停止条件: `critical=0` かつ `high=0`
3. **コミット + プッシュ**: `git commit` + `git push`（AGENTS.md Phase 8 準拠）。ただし親タスク完了は `git commit` 成功時点で判定する（push 失敗はリトライ可能であり、完了条件に含めない）

> Step 4 の「計画レビュー」と上記の「コミット前レビュー」は別物。**両方必須**。

### セッション振り返り（dig-core 契約）

> 実行フェーズでエラーやリトライが発生した場合のみ実行。
> エラーがなければ「振り返り不要」と報告してスキップ。
> **エラー隔離**: auto-retro自体が失敗しても、コミット済みの成果物には影響しない。

`devkit:improve-skill --auto-retro` を実行。

## 停止コード

| コード | 条件 |
|--------|------|
| `DIG_CLAUDE_USER_CANCELLED` | ユーザーが Step 2 でキャンセル |
| `DIG_CLAUDE_REVIEW_BLOCKED` | Codex レビューで critical/high 未解消（3回超過） |
| `DIG_CLAUDE_CODEX_UNAVAILABLE` | `codex exec` が実行不可 |
| `DIG_CLAUDE_QUESTION_FAILED` | AskUserQuestion が拒否・空返答・タイムアウトを返した |
| `DIG_CLAUDE_DECOMP_REVIEW_BLOCKED` | 分解レビューで critical/high 未解消 |
| `DIG_CLAUDE_SUBTASK_REVIEW_BLOCKED` | サブタスクレビューで critical/high 未解消 |
| `DIG_CLAUDE_INTEGRATION_REVIEW_BLOCKED` | 統合レビューで critical/high 未解消 |

停止時は必ず以下を出力:
- `ERROR_CODE: <CODE>`
- `RERUN_COMMAND: /dig <topic>`
- `DIAGNOSTIC_COMMAND: <診断コマンド>`
- `STOP_OUTPUT_FIELDS: ERROR_CODE,RERUN_COMMAND,DIAGNOSTIC_COMMAND`

停止時の cleanup 手順（dig-core 契約準拠・Step 3-5 の STOP 経路で実行）:
1. 一時ファイル削除（`rm -f /tmp/dig_*_review_$$.*`）
2. 親タスク登録済みの場合: 未完了サブタスク → 親タスクの順で TaskUpdate(status="cancelled")
3. agent-parallel 実行中の場合: `git worktree list` で残存 worktree を検出し、`git worktree remove` でクリーンアップ

> 早期退出パス（Step 1-2 での DIG_CLAUDE_USER_CANCELLED / DIG_CLAUDE_QUESTION_FAILED）は親タスク未登録のため cleanup 不要（一時ファイル削除のみ）。

## 重要

- **EnterPlanMode は呼ばない**。Plan Mode の WF が dig-core 契約を上書きするため
- **ユーザーの思考を引き出す**: 答えを与えるのではなく、質問で引き出す
- **コードベース調査を積極的に**: 具体的な文脈に基づいた質問を行う
- **クロスモデルレビューは Bash で直接実行**: Skill ツール経由のレビューは使わない
- **コミットセクションは3ステップ構成**: ステージング → コミット前レビュー → コミット + プッシュ（AGENTS.md Phase 8 準拠。親タスク完了は commit 成功時点）
- **全レビューでサニタイズ必須**: dig_sanitize 関数経由でのみ外部モデルに送信
- **タスク管理**: Step 2 で親タスク登録、Step 5 で各サブタスク＋親タスク完了
- dig-core 契約の5ステップを忠実に実行する
- allowed-tools に Edit/Write を含む（実行フェーズで必要）
