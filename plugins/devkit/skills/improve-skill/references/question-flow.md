# Improve Skill Question Flow

`improve-skill` は手動起動専用。引数なしでは `retro`（セッション振り返り修正）を実行する。
他スキルからの自動起動契約は存在しない。

## Step 1: モード確定（--refresh / --create 時のみ）

`--refresh` または `--create` で呼び出された場合、対応するモードで進める。
引数なしの場合はこのフローに入らず、`retro` が実行される。

## Step 2: 共通深掘り（必須）

モード確定後に次を質問する。

- 優先観点（トリガー精度/短文化/再利用資産/安全性/検証性）
- 完了条件（何が満たされれば採用できるか）

## Step 3: refresh 分岐

追加質問:

- 対象スキル（名前またはパス）
- 反映したいセッション要件の優先順位

対象が不明/不存在なら近い候補を提示し、再質問する。  
それでも未確定なら停止する。

## Step 4: create 分岐

追加質問:

- スキル名の方向性（動詞先頭）
- 想定トリガー文（ユーザーが何と言ったら起動するか）
- 必須リソース（scripts/references/assets）

## Step 5: 出力

どちらの分岐でも、日本語で次の固定見出しを返す。

- `必須修正`
- `推奨修正`
- `確認事項`
- `完了条件`

各項目は `対象ファイル` / `理由` / `期待状態` を含める。

## セッション抽出と生成

必要なら SKILL.md のディレクトリを基準に、先に現在セッションの要約を `/tmp/current-session.txt` へ書き出す。read-only sandbox 等で `/tmp` を使えなければ会話コンテキストから直接作る。

```bash
SKILL_DIR="<この SKILL.md があるディレクトリの絶対パス>"
uv run --no-project --python ">=3.10" python "$SKILL_DIR/scripts/session_extract.py" --input-file /tmp/current-session.txt --format json > /tmp/improve-skill-session.json
```

`refresh` は対象スキルの絶対パスを `TARGET_SKILL_DIR`、`create` は skills 親の絶対パスを `BASE_SKILLS_DIR` として次を実行する。
共通起動形は `uv run --no-project --python ">=3.10" python` とする。

| モード | 生成 |
|---|---|
| `refresh` | `"$SKILL_DIR/scripts/refresh_mapper.py" --skill "$TARGET_SKILL_DIR" --session-json /tmp/improve-skill-session.json --format markdown` |
| `create` | `"$SKILL_DIR/scripts/create_blueprint.py" --session-json /tmp/improve-skill-session.json --base-path "$BASE_SKILLS_DIR" --format markdown` |

`create` は demand-pull、2 repo またはセッションの証拠、最小手段の梯子、反復性 / 即興リスク / ハーネス非重複 / 監査可能性 / 撤退性へ照合する。満たさなければ理由と梯子上の代替手段を示す。

## 出力形式

```markdown
## 必須修正
- [ ] 対象: `path/to/file` | 理由: ... | 期待状態: ...

## 推奨修正
- [ ] 対象: `path/to/file` | 理由: ... | 期待状態: ...

## 確認事項
- [ ] ...

## 完了条件
- [ ] ...
```
