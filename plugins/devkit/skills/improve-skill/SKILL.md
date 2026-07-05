---
name: "improve-skill"
description: "既存スキルの改善提案（refresh）・新規スキル作成提案（create）・セッション振り返り修正（retro）。手動起動専用。「スキルを改善して」「セッションを振り返って直して」「/improve-skill」で起動。"
allowed-tools: ["Read", "Edit", "Write", "Grep", "Glob", "Bash", "AskUserQuestion", "request_user_input", "spawn_agent", "wait_agent"]
---

# /improve-skill - Session-Aware Skill Improver

現在セッションを根拠に、スキル改善を提案または適用する。
`refresh` / `create` では提案チェックリストのみ返す。`retro` ではユーザー承認後に修正適用→レビュー→コミットまで実行する。

## トピック
$ARGUMENTS

## ハーネス判定と質問手段

この SKILL.md は Claude Code / OpenAI Codex のどちらの親ハーネスでも自己完結して実行する。選択肢付き質問は、Claude 親では AskUserQuestion、Codex 親の plan mode では `request_user_input`、Codex 親の通常 mode では選択肢を箇条書きにして自由文回答を求める。
親ハーネスが判定できない場合も、選択肢を箇条書きで提示して自由文回答を求める。

## 目的

- `refresh` / `create`: 手動起動。選択肢付き質問で用途確定→チェックリスト返却（既存動作維持）
- `retro`: 手動起動。会話コンテキストからエラーおよびユーザーフィードバックを検出→修正案提示→承認後に修正適用

## 実行ルール（必須）

### モード判定（ディスパッチ）

- `$ARGUMENTS` に `--refresh` を含む → `refresh` モード
- `$ARGUMENTS` に `--create` を含む → `create` モード
- それ以外（引数なし含む）→ `retro` モード

### refresh / create（手動呼び出し時）

1. 最初に選択肢付き質問で以下を確認する。
- モード: `refresh` / `create`
- 優先観点: `トリガー精度` / `短文化` / `再利用資産` / `安全性` / `検証性`
- 完了条件: 何を満たせばOKか
2. 回答が曖昧または不足なら、再質問して停止する。
3. `refresh` では対象スキル（名前かパス）を必ず特定する。
4. `refresh` の対象が不明/不存在なら候補を提示して再質問する。確定できなければ停止する。
5. 常に提案のみを返し、ファイル編集・コミットはしない。

> **重要**: refresh/createモードではEdit/Writeツールを使用しない（提案のみ）。
> `allowed-tools`はフロントマター全体で設定されるため、モード判定直後にこの制約を遵守すること。

### retro（手動振り返り時）

1. モード確認の選択肢付き質問は**不要**（手動起動時の通常動作）
2. 1セッション1回制約: 既に実行済みなら「振り返り済み」と報告してスキップ
3. エラーおよびユーザーフィードバックの検出結果が0件なら「振り返り不要」と報告してスキップ
4. 修正案をユーザーに提示し、選択肢付き質問で承認確認する。ユーザーが「スキップ」を選べば即終了
5. 修正対象は**エラーが発生した、またはユーザーフィードバックが関連するスキルのSKILL.md / CLAUDE.mdのみ**（他スキルや scripts 本体への変更は禁止。読み込みは許可）
6. retro 自体が失敗した場合は警告のみ出力して終了
7. Plan モード中の場合、Step 3（編集適用・レビュー・コミット）は実行せず、修正提案の提示のみ行う。Step 0-2 は通常通り実行する

## モード別フロー

### refresh: 既存スキル改善（セッション反映）

スクリプトは、この SKILL.md があるディレクトリを基準にした絶対パスで実行する。read-only sandbox でスクリプト実行や `/tmp` 書き込みができない場合は、スクリプトなしで会話コンテキストから直接チェックリストを作成する。

1. 現在セッション要約を `/tmp/current-session.txt` にまとめてから要件を抽出する。

```bash
SKILL_DIR="<この SKILL.md があるディレクトリの絶対パス>"
python3 "$SKILL_DIR/scripts/session_extract.py" \
  --input-file /tmp/current-session.txt \
  --format json \
  > /tmp/improve-skill-session.json
```

2. 対象スキルへマッピングして改善チェックリストを生成する。

```bash
SKILL_DIR="<この SKILL.md があるディレクトリの絶対パス>"
TARGET_SKILL_DIR="<対象スキルディレクトリの絶対パス>"
python3 "$SKILL_DIR/scripts/refresh_mapper.py" \
  --skill "$TARGET_SKILL_DIR" \
  --session-json /tmp/improve-skill-session.json \
  --format markdown
```

3. 生成結果を日本語で提示する（チェックリストのみ）。

### create: 新規スキル作成（セッション起点）

スクリプトは、この SKILL.md があるディレクトリを基準にした絶対パスで実行する。read-only sandbox でスクリプト実行や `/tmp` 書き込みができない場合は、スクリプトなしで会話コンテキストから直接チェックリストを作成する。

1. 現在セッション要約を `/tmp/current-session.txt` にまとめてから要件を抽出する。

```bash
SKILL_DIR="<この SKILL.md があるディレクトリの絶対パス>"
python3 "$SKILL_DIR/scripts/session_extract.py" \
  --input-file /tmp/current-session.txt \
  --format json \
  > /tmp/improve-skill-session.json
```

2. 新規スキル案のチェックリストを生成する。

```bash
SKILL_DIR="<この SKILL.md があるディレクトリの絶対パス>"
BASE_SKILLS_DIR="$(dirname "$SKILL_DIR")"
python3 "$SKILL_DIR/scripts/create_blueprint.py" \
  --session-json /tmp/improve-skill-session.json \
  --base-path "$BASE_SKILLS_DIR" \
  --format markdown
```

3. 生成結果を日本語で提示する（チェックリストのみ）。

### retro: セッション振り返り修正

> `/improve-skill` を手動で起動したときの通常動作。
> 対象スキルはエラーおよびユーザーフィードバックのコンテキストから判定する。

#### Step 0: エラー・ユーザーフィードバック検出

会話コンテキスト（ツール呼び出し結果、エラーメッセージ、リトライ履歴、ユーザーの指摘）を自己振り返りし検出:
- ツール呼び出しがエラーで失敗→別ツール/アプローチに切り替えた
- SKILL.mdの手順と異なる手順を即興で実行した
- スクリプトの引数形式を試行錯誤した
- エンコーディングや環境制約でリトライが発生した
- ユーザーが手順や方針を修正・却下した（「それは違う」「こうして」等）
- ユーザーがスキルの出力に不満を示した（「いらない」「多すぎる」等）
- ユーザーがワークフローの進め方について指摘した

検出に自信がない場合 → ユーザーに選択肢付き質問で確認
検出結果0件 → 「振り返り不要」と報告してスキップ

#### Step 1: 根本原因分析

対象スキルの全ファイル（SKILL.md, CLAUDE.md, REFERENCE.md, references/, scripts/）を読み込み、各エラーを分類:

| 失敗カテゴリ | 修正方針 |
|-------------|---------|
| 誤ツール使用 | 「禁止」セクション追加 |
| スクリプト名/パス誤り | パス・コマンド例の追加 |
| 引数形式エラー | JSON例の追加 |
| 環境制約（WSL/Box等） | 「注意事項」追加 |
| エンコーディング問題 | UTF-8対応手順の追加 |
| 機能未活用 | スキル内 references/scripts の機能を SKILL.md へ伝播 |
| 冪等性欠如 | 事前チェックステップ追加 |
| ユーザーフィードバック | 手順・出力・ワークフローの改善を反映 |
| その他 | ユーザーに手動対応を提案 |

#### Step 2: 修正案生成・承認

- 各ギャップに対する具体的な編集案（before/after diff形式）を生成
- 全修正案をユーザーに提示
- 選択肢付き質問で承認確認

#### Step 3: 適用・レビュー・コミット

- 対象ファイルに編集適用
- 変更ファイルをすべてステージング
- Claude 親: Codexレビューを `codex exec` で実行する（CLAUDE.mdルール準拠）
- Codex 親: `spawn_agent`(explorer) に read-only 指示を明記してレビューを依頼する
- コミット: `fix(skills): セッション振り返り - <skill-name> <原因要約>`

## チェックリスト出力フォーマット（refresh/create用・固定）

```markdown
## 必須修正
- [ ] 対象: `path/to/file` | 理由: ... | 期待状態: ...

## 推奨修正
- [ ] 対象: `path/to/file` | 理由: ... | 期待状態: ...

## 確認事項
- [ ] 確認したい点 ...

## 完了条件
- [ ] 必須修正がすべて満たされている
- [ ] 出力が現在セッション要件に一致している
```

## 参照

- 詳細チェック項目: `references/checklist.md`
- 質問フロー詳細: `references/question-flow.md`
- スクリプト:
  - `scripts/session_extract.py`
  - `scripts/refresh_mapper.py`
  - `scripts/create_blueprint.py`

## 重要

- `refresh` / `create` / `retro` の3モード構成
- `retro` のみファイル編集・コミットを行う。`refresh/create` は引き続き提案のみ
- 他スキルの最終ステップから自動起動される契約は存在しない
- 現在セッション以外（履歴ファイル等）を勝手に参照しない
- ユーザー回答が不足したまま推測で出力しない（refresh/create時）
