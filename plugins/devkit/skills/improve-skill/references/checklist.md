# Improve Skill Checklist

`improve-skill` が返すチェックリストの評価基準。

## 1. Trigger Precision

- [ ] `description` に「何をするか」と「いつ使うか」が両方入っている
- [ ] `refresh` と `create` の2モードが明示されている
- [ ] 依頼文の代表例が `description` か本文に含まれている

## 2. Interview Workflow

- [ ] 実行開始時に `AskUserQuestionTool` を必須化している
- [ ] 回答不足時の再質問ルールがある
- [ ] 未確定のまま推測で進めないルールがある

## 3. Session Handling

- [ ] 「現在セッションのみ参照」が明記されている
- [ ] `refresh` で対象スキル未確定時の分岐が定義されている
- [ ] セッション要件から改善項目へのマッピング手順がある

## 4. Output Contract

- [ ] 出力形式が固定（`必須修正` / `推奨修正` / `確認事項` / `完了条件`）
- [ ] 各項目に `対象ファイル` / `理由` / `期待状態` が含まれる
- [ ] 出力は提案のみで、編集やコミットを行わない

## 5. Resource Quality

- [ ] `scripts/` は非破壊で再現可能な出力を返す
- [ ] `references/` は手順を分岐別に説明している
- [ ] 役割が重複するファイルを作っていない

## 6. Safety and Limits

- [ ] `.env` や秘密情報を読む手順を含まない
- [ ] 対象範囲外のリポジトリ変更を指示しない
- [ ] モード外（第三モード）を追加しない
