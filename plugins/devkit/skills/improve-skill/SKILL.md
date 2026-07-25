---
name: "improve-skill"
description: "既存スキルの改善提案（refresh）・新規スキル作成提案（create）・セッション振り返り修正（retro）。手動起動専用。「スキルを改善して」「セッションを振り返って直して」「/improve-skill」で起動。"
allowed-tools: ["Read", "Edit", "Write", "Grep", "Glob", "Bash", "AskUserQuestion", "request_user_input", "spawn_agent", "wait_agent", "TaskCreate", "TaskUpdate", "TaskOutput"]
---

# /improve-skill - Session-Aware Skill Improver

現在セッションだけを根拠に、スキル改善を提案または適用する。手動起動専用で、他スキルから自動起動しない。

## トピック

$ARGUMENTS

## ハーネス判定

`request_user_input` は判定キーに使わない。

| 判定 | 質問 | 独立レビュー |
|---|---|---|
| `AskUserQuestion` が使える Claude 親 | `AskUserQuestion` | codex |
| 上記がなく `spawn_agent` が使える Codex 親 | plan mode は `request_user_input`、通常 mode は選択肢 + 自由文 | `spawn_agent` / `wait_agent` |
| 判定不能 | 選択肢 + 自由文 | 利用可能な別系統 |

主要工程をタスク化し、委譲も 1 ジョブ = 1 タスクとする。Codex 親は待機中も進捗を示し、停滞時だけ継続時間と推定原因を報告する。

## モード契約

| モード | 判定 | 出力・書き込み | 固有条件 |
|---|---|---|---|
| `refresh` | `$ARGUMENTS` に `--refresh` | 改善チェックリストのみ。Edit / Write / commit 禁止 | 対象スキルを名前かパスで確定 |
| `create` | `$ARGUMENTS` に `--create` | 新規案チェックリストのみ。Edit / Write / commit 禁止 | スキル採用基準との照合を含める |
| `retro` | それ以外(引数なし含む) | 承認後だけ対象へ編集。commit は明示時のみ | 1 セッション 1 回。plan mode は提案まで |

`refresh/create` は回答不足のまま推測しない。候補提示と再質問でも確定できなければ停止する。`retro` は検出なしなら「振り返り不要」、実行済みなら「振り返り済み」、自身の失敗は警告して終了する。

## 共通骨格

1. 現在セッションから根拠を抽出する。履歴ファイルを勝手に参照しない。
2. 対象の関連ファイルを読み、根本原因と最小変更を分析する。
3. モード差分に従い提案を提示し、書き込みがある場合は先に承認を得る。
4. 承認範囲だけ適用し、独立レビューを行う。提案専用モードは適用・レビューなし。

詳細な質問と評価は `references/question-flow.md` と `references/checklist.md` を使う。

## refresh / create

優先観点(トリガー精度 / 短文化 / 再利用資産 / 安全性 / 検証性)と完了条件を選択肢付きで確認する。`refresh` は対象と反映要件、`create` は名前・想定トリガー・必須リソースを追加確認する。

必要なら SKILL.md のディレクトリを基準に、次の共通抽出を実行する。read-only sandbox 等で `/tmp` を使えなければ会話コンテキストから直接作る。

```bash
SKILL_DIR="<この SKILL.md があるディレクトリの絶対パス>"
uv run --no-project --python ">=3.10" python "$SKILL_DIR/scripts/session_extract.py" \
  --input-file /tmp/current-session.txt --format json \
  > /tmp/improve-skill-session.json
```

生成時は `TARGET_SKILL_DIR` を対象スキルの絶対パス、`BASE_SKILLS_DIR` を skills 親ディレクトリの絶対パスとする。共通起動形 `uv run --no-project --python ">=3.10" python` に次の引数を加える。

| モード | 生成 |
|---|---|
| `refresh` | `"$SKILL_DIR/scripts/refresh_mapper.py" --skill "$TARGET_SKILL_DIR" --session-json /tmp/improve-skill-session.json --format markdown` |
| `create` | `"$SKILL_DIR/scripts/create_blueprint.py" --session-json /tmp/improve-skill-session.json --base-path "$BASE_SKILLS_DIR" --format markdown` |

`create` の提案は devkit `AGENTS.md` の採用基準に照合する。

- demand-pull: 観測された反復する痛みが起点か
- 証拠テスト: 2 つ以上の repo またはセッションで観測したか
- 最小手段の梯子: ルール 1 行 → check スクリプト → 既存スキルへの 1 観点追加で足りないか
- 5 テスト: 反復性 / 即興リスク / ハーネス非重複 / 監査可能性 / 撤退性

満たさなければ理由と、梯子上の代替手段を示す。

## retro

### 検出

現在セッションのツール結果、エラー、リトライ、ユーザー指摘から次の 3 系統を検出する。

| 系統 | 候補 |
|---|---|
| エラー | 誤ツール・パス・引数、環境・encoding 制約、冪等性不足など |
| ユーザーフィードバック | 手順・出力・workflow の修正、却下、不満 |
| 第 3 検出系統 | 再利用可能な即興手順、反復する手順ずれ、反復する環境回避策 |

第 3 検出系統は report-only 候補として分析に載せ、承認前に反映しない。不確かな候補だけ質問する。

### 分析・承認

候補に関係するスキルの SKILL.md / CLAUDE.md / REFERENCE.md / references / scripts を読み、原因と最小差分を提案する。編集対象は、エラー・フィードバック・第 3 検出系統に関係する SKILL.md / CLAUDE.md だけとし、他スキルや scripts は変更しない。before / after と対象ファイルを提示し、選択肢付きで承認を得る。

### 適用・レビュー

承認差分だけ適用する。Claude 親の独立レビューは次の非対話形を使う。

```bash
codex -a never exec -m gpt-5.6-sol -c model_reasoning_effort="medium" "<レビュー依頼内容>" < /dev/null
```

Codex 親は `spawn_agent` へ read-only レビューを依頼する。指摘があれば修正後に再レビューする。commit はユーザー明示時のみ、今回編集したファイルだけを stage する。

## チェックリスト出力(refresh/create)

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

## 参照

- `references/checklist.md`
- `references/question-flow.md`
- `scripts/session_extract.py`
- `scripts/refresh_mapper.py`
- `scripts/create_blueprint.py`
