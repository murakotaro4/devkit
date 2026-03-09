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
2. **Step 3-4**（計画・レビュー）: Planファイルに記載し、Codexレビューを実行
3. **Step 5**（実行）: ExitPlanMode後に実行

> Plan Modeの解除はdig側から行わない（ユーザーの意図を尊重）。

### フェーズ別ツール制御ガイダンス

- **Step 1-3**（質問・終了確認・分解）: 調査目的の Read/Grep/Glob/Explore のみ使用する。Write/Edit/Bash によるファイル変更は行わない
- **Step 4-5**（計画レビュー・実行）: Write/Edit/Bash を含む全ツールを使用可能

## 実行契約

| 機能 | Claude Code での実現手段 |
|------|--------------------------|
| 質問 | `AskUserQuestionTool` |
| コード探索 | `Explore` サブエージェント / `Grep` / `Glob` |
| 計画記載 | `Write` ツールでプランファイルを直接作成 |
| レビュー | `codex exec` (Bash経由、dig-core `REVIEW_RESULT_MARKER` 契約準拠) |
| 分解 | `devkit:decomposition` スキル |

> **EnterPlanMode は呼ばない**。Plan Mode のシステムプロンプトが dig-core の5ステップ契約を上書きするため。プランファイルが必要な場合は Write ツールで直接作成する。

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

### Step 2: 終了確認（dig-core ステップ2）

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

### Step 3: タスク分解（dig-core ステップ3・オプション）

複雑なタスク（複数ファイル変更、依存関係あり）の場合のみ実行:
- `devkit:decomposition` を呼び出してサブタスク登録
- 単純なタスク（1ファイル変更、明確な手順）はスキップ

### Step 4: 計画レビューゲート（dig-core ステップ4）

> **スキル競合の回避**: このステップは **Bash ツールで `codex exec` を直接実行** する。
> Skill ツールは呼ばない。`/harness-review`・`/codex-review` 等のスキルは使用しない。

実装計画を Write ツールでプランファイルに書き出し、クロスモデルレビューを実行:

#### レビューコマンド

```bash
REVIEW_PRIMARY_CMD='codex exec -m gpt-5.3-codex-spark -c model_reasoning_effort="medium"'
REVIEW_FALLBACK_CMD='codex exec -m gpt-5.3-codex-spark -c model_reasoning_effort="low"'
REVIEW_TIMEOUT_SECONDS=180

$REVIEW_PRIMARY_CMD "以下のプランファイルをレビューしてください: <plan_file_path>。観点: 実現可能性、既存構造との整合性、見落としているエッジケース。重大度(critical/high/medium/low)を付けて指摘してください。最終行に REVIEW_RESULT_MARKER=REVIEW_COUNTS と REVIEW_COUNTS critical=<int> high=<int> を必ず出力してください"
```

#### モデル運用切替規則

- `gpt-5.3-codex-spark` を第一候補
- レートリミット時のみ `REVIEW_FALLBACK_CMD` へ切替可。実施時は理由を記録
- レートリミット以外の失敗は停止して原因特定

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

分解済みタスクまたは計画に従い実装を実行。

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
   codex exec -m gpt-5.3-codex-spark -c model_reasoning_effort="medium" \
     "git diff --staged をレビューしてください。観点: <変更内容に応じたレビュー指示>。最終行に REVIEW_RESULT_MARKER=REVIEW_COUNTS と REVIEW_COUNTS critical=<int> high=<int> を必ず出力してください"
   ```
   - 停止条件: `critical=0` かつ `high=0`
3. **コミット+プッシュ**: `git commit` + `git push`（ユーザー承認後）

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

停止時は必ず以下を出力:
- `ERROR_CODE: <CODE>`
- `RERUN_COMMAND: /dig <topic>`
- `DIAGNOSTIC_COMMAND: <診断コマンド>`
- `STOP_OUTPUT_FIELDS: ERROR_CODE,RERUN_COMMAND,DIAGNOSTIC_COMMAND`

## 重要

- **EnterPlanMode は呼ばない**。Plan Mode の WF が dig-core 契約を上書きするため
- **ユーザーの思考を引き出す**: 答えを与えるのではなく、質問で引き出す
- **コードベース調査を積極的に**: 具体的な文脈に基づいた質問を行う
- **クロスモデルレビューは Bash で直接実行**: Skill ツール経由のレビューは使わない
- **コミットセクションは3ステップ構成**: ステージング → コミット前レビュー → コミット+プッシュ
- dig-core 契約の5ステップを忠実に実行する
- allowed-tools に Edit/Write を含む（実行フェーズで必要）
