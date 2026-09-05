# Improve Skill Checklist

`improve-skill` が返すチェックリストの評価基準。

## 1. Trigger Precision

- [ ] `description` に「何をするか」と「いつ使うか」が両方入っている
- [ ] `refresh` / `create` / `retro` の3モードが明示されている
- [ ] 手動起動の代表例が `description` か本文に含まれている

## 2. Interview Workflow

- [ ] `refresh` / `create` では実行開始時に選択肢付き質問を必須化している
- [ ] 回答不足時の再質問ルールがある
- [ ] 未確定のまま推測で進めないルールがある

## 3. Session Handling

- [ ] 「現在セッションのみ参照」が明記されている
- [ ] `refresh` で対象スキル未確定時の分岐が定義されている
- [ ] セッション要件から改善項目へのマッピング手順がある

## 4. Output Contract

- [ ] 出力形式が固定（`必須修正` / `推奨修正` / `確認事項` / `完了条件`）
- [ ] 各項目に `対象ファイル` / `理由` / `期待状態` が含まれる
- [ ] `refresh` / `create` は提案のみで、編集やコミットを行わない

## 5. Resource Quality

- [ ] `scripts/` は非破壊で再現可能な出力を返す
- [ ] `references/` は手順を分岐別に説明している
- [ ] 役割が重複するファイルを作っていない

## 6. Safety and Limits

- [ ] `.env` や秘密情報を読む手順を含まない
- [ ] 対象範囲外のリポジトリ変更を指示しない
- [ ] 手動起動専用であることが明記されている

## retro

現在セッションのツール結果、エラー、リトライ、ユーザー指摘から次の 3 系統を検出する。

| 系統 | 候補 |
|---|---|
| エラー | 誤ツール・パス・引数、環境・encoding 制約、冪等性不足など |
| ユーザーフィードバック | 手順・出力・workflow の修正、却下、不満 |
| 第 3 検出系統 | 再利用可能な即興手順、反復する手順ずれ、反復する環境回避策 |

第 3 検出系統は report-only 候補として分析に載せ、承認前に反映しない。不確かな候補だけ質問する。

候補に関係する SKILL.md / CLAUDE.md / REFERENCE.md / references / scripts を読み、原因と最小差分を提案する。編集対象は候補に関係する SKILL.md / CLAUDE.md だけとし、他スキルや scripts は変更しない。before / after と対象ファイルを提示し、選択肢付きで承認を得る。

承認差分だけ適用する。Claude 親の独立レビュー:

```bash
codex -a never exec -m gpt-5.6-sol -c model_reasoning_effort="medium" "<レビュー依頼内容>" < /dev/null
```

Codex 親は `spawn_agent` へ read-only レビューを依頼する。指摘があれば修正後に再レビューする。
