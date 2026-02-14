---
name: "improve-skill"
description: "既存スキルに現在セッション内容を反映して改善する（refresh）か、現在セッション内容から新規スキルを作成する（create）。『skillを改善したい』『会話内容を反映してskill化したい』依頼で起動し、AskUserQuestionToolで深掘りして日本語チェックリストのみ返す。"
allowed-tools: ["Read", "Grep", "Glob", "Bash"]
---

# /improve-skill - Session-Aware Skill Improver

現在セッションを根拠に、スキル改善を提案する。  
実装適用は行わず、提案チェックリストだけを返す。

## トピック
$ARGUMENTS

## 目的

- 毎回 `AskUserQuestionTool` で用途を確定する
- 用途は `refresh` と `create` の2つのみ
- 出力は日本語チェックリスト（`必須修正` / `推奨修正` / `確認事項` / `完了条件`）のみ
- 参照するセッション情報は現在セッションのみ

## 実行ルール（必須）

1. 最初に `AskUserQuestionTool` で以下を質問する。
- モード: `refresh` / `create`
- 優先観点: `トリガー精度` / `短文化` / `再利用資産` / `安全性` / `検証性`
- 完了条件: 何を満たせばOKか
2. 回答が曖昧または不足なら、再質問して停止する。
3. `refresh` では対象スキル（名前かパス）を必ず特定する。
4. `refresh` の対象が不明/不存在なら候補を提示して再質問する。確定できなければ停止する。
5. 常に提案のみを返し、ファイル編集・コミットはしない。

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

## チェックリスト出力フォーマット（固定）

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

- `refresh/create` 以外の第三モードを作らない
- 現在セッション以外（履歴ファイル等）を勝手に参照しない
- ユーザー回答が不足したまま推測で出力しない
