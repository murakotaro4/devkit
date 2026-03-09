---
name: "improve-skill"
description: "既存スキルの改善（refresh）・新規作成（create）・セッション振り返り自動修正（auto-retro）。手動起動またはワークフロー最終ステップとして自動トリガー。"
allowed-tools: ["Read", "Edit", "Write", "Grep", "Glob", "Bash"]
---

# /improve-skill - Session-Aware Skill Improver

現在セッションを根拠に、スキル改善を提案する。
`refresh` / `create` では提案チェックリストのみ返す。`auto-retro` では修正適用→Codexレビュー→コミットまで実行する。

## トピック
$ARGUMENTS

## 目的

- `refresh` / `create`: 手動起動。AskUserQuestionで用途確定→チェックリスト返却（既存動作維持）
- `auto-retro`: **自動トリガー対応**。`$ARGUMENTS`に`--auto-retro`を含む場合に起動。会話コンテキストからエラーを自動検出→修正適用→Codexレビュー→コミット

## 実行ルール（必須）

### モード判定（ディスパッチ）
- `$ARGUMENTS` に `--auto-retro` を含む → `auto-retro` モード（モード確認のAskUserQuestion不要）
- それ以外 → AskUserQuestionで `refresh` / `create` を確定（既存動作）

### refresh / create（手動呼び出し時）

1. 最初に `AskUserQuestionTool` で以下を質問する。
- モード: `refresh` / `create`
- 優先観点: `トリガー精度` / `短文化` / `再利用資産` / `安全性` / `検証性`
- 完了条件: 何を満たせばOKか
2. 回答が曖昧または不足なら、再質問して停止する。
3. `refresh` では対象スキル（名前かパス）を必ず特定する。
4. `refresh` の対象が不明/不存在なら候補を提示して再質問する。確定できなければ停止する。
5. 常に提案のみを返し、ファイル編集・コミットはしない。

> **重要**: refresh/createモードではEdit/Writeツールを使用しない（提案のみ）。
> `allowed-tools`はフロントマター全体で設定されるため、モード判定直後にこの制約を遵守すること。

### auto-retro（自動トリガー時）

1. モード確認のAskUserQuestionは**不要**（`--auto-retro`で確定済み）
2. 1セッション1回制約: 既に実行済みなら「振り返り済み」と報告してスキップ
3. エラー検出結果が0件なら「振り返り不要」と報告してスキップ
4. 修正案をユーザーに提示し、AskUserQuestionで承認確認する（安全のため人間承認必須）。ユーザーが「スキップ」を選べば即終了（親ワークフローは正常続行）
5. 修正対象は**エラーが発生したスキルのSKILL.md / CLAUDE.mdのみ**（_coreスクリプトや他スキルへの変更は禁止。読み込みは許可）
6. auto-retro自体が失敗した場合は警告メッセージのみ出力し、呼び出し元ワークフローの成果物には影響しない

## モード別フロー

### refresh: 既存スキル改善（セッション反映）

1. 現在セッション要約を `/tmp/current-session.txt` にまとめてから要件を抽出する。

```bash
python3 plugins/devkit/skills/improve-skill/scripts/session_extract.py \
  --input-file /tmp/current-session.txt \
  --format json \
  > /tmp/improve-skill-session.json
```

2. 対象スキルへマッピングして改善チェックリストを生成する。

```bash
python3 plugins/devkit/skills/improve-skill/scripts/refresh_mapper.py \
  --skill plugins/devkit/skills/<target-skill> \
  --session-json /tmp/improve-skill-session.json \
  --format markdown
```

3. 生成結果を日本語で提示する（チェックリストのみ）。

### create: 新規スキル作成（セッション起点）

1. 現在セッション要約を `/tmp/current-session.txt` にまとめてから要件を抽出する。

```bash
python3 plugins/devkit/skills/improve-skill/scripts/session_extract.py \
  --input-file /tmp/current-session.txt \
  --format json \
  > /tmp/improve-skill-session.json
```

2. 新規スキル案のチェックリストを生成する。

```bash
python3 plugins/devkit/skills/improve-skill/scripts/create_blueprint.py \
  --session-json /tmp/improve-skill-session.json \
  --base-path plugins/devkit/skills \
  --format markdown
```

3. 生成結果を日本語で提示する（チェックリストのみ）。

### auto-retro: セッション振り返り自動修正

> 他スキルの最終ステップから `--auto-retro` 引数付きで自動トリガーされる。
> `--auto-retro` 以外の追加引数は不要（対象スキルはエラーコンテキストから自動判定）。

#### Step 0: エラー検出

会話コンテキスト（ツール呼び出し結果、エラーメッセージ、リトライ履歴）を自己振り返りし検出:
- ツール呼び出しがエラーで失敗→別ツール/アプローチに切り替えた
- SKILL.mdの手順と異なる手順を即興で実行した
- スクリプトの引数形式を試行錯誤した
- エンコーディングや環境制約でリトライが発生した

検出に自信がない場合 → ユーザーにAskUserQuestionで確認
検出結果0件 → 「振り返り不要」と報告してスキップ

#### Step 1: 根本原因分析

対象スキルの全ファイル（SKILL.md, CLAUDE.md, REFERENCE.md, scripts/）と_core依存を読み込み、各エラーを分類:

| 失敗カテゴリ | 修正方針 |
|-------------|---------|
| 誤ツール使用 | 「禁止」セクション追加 |
| スクリプト名/パス誤り | パス・コマンド例の追加 |
| 引数形式エラー | JSON例の追加 |
| 環境制約（WSL/Box等） | 「注意事項」追加 |
| エンコーディング問題 | UTF-8対応手順の追加 |
| 機能未活用 | _coreから機能ドキュメントを伝播 |
| 冪等性欠如 | 事前チェックステップ追加 |
| その他 | ユーザーに手動対応を提案 |

#### Step 2: 修正案生成・承認

- 各ギャップに対する具体的な編集案（before/after diff形式）を生成
- 全修正案をユーザーに提示
- AskUserQuestionで承認確認

#### Step 3: 適用・Codexレビュー・コミット

- 対象ファイルに編集適用
- 変更ファイルをすべてステージング
- Codexレビュー（CLAUDE.mdルール準拠）
- コミット: `fix(skills): セッション振り返り — <skill-name> <原因要約>`

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

- `refresh/create` 以外に `auto-retro` モードが存在する（3モード構成）
- `auto-retro` のみファイル編集・コミットを行う。`refresh/create` は引き続き提案のみ
- 現在セッション以外（履歴ファイル等）を勝手に参照しない
- ユーザー回答が不足したまま推測で出力しない（refresh/create時）
