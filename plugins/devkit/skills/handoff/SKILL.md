---
name: "handoff"
description: "セッション終了時に、タスクの現在地・決定事項・次アクション・会話文脈を対象 repo の .claude/handoff/ へ引継ぎドキュメントとして書き出す(書き出し専用、gitignore 対象)。「引き継ぎを書いて」「引継ぎドキュメントを作って」「ハンドオフを作って」「/handoff」で起動"
argument-hint: "[topic]"
allowed-tools: ["Read", "Grep", "Glob", "Bash", "AskUserQuestion", "request_user_input", "TaskCreate", "TaskUpdate", "Write"]
---

# /handoff - セッション引継ぎドキュメント書き出し

会話と repo 状態を、次セッションが再開できる文書として `.claude/handoff/` へ新規保存する。書き出し専用で、読み込みモード・自動復元・commit / push は非対象。

## 対象

$ARGUMENTS

## ハーネス・進捗

| 判定 | 質問 |
|---|---|
| `AskUserQuestion` が使える Claude 親 | AskUserQuestion |
| それがなく `spawn_agent` が使える Codex 親 | plan mode は `request_user_input`、通常 mode は選択肢付き自由文 |
| 判定不能 | 選択肢付き自由文 |

`request_user_input` は判定キーにしない。step 1-4 は利用可能なタスクリストまたは通常報告で開始・完了を示す。長時間処理は実体を `git status` / `git diff` で確認し、停滞時だけ報告する。

## 書き込み契約

- step 1 は read-only。Bash は `git status`、`git diff`、`git log`、`rg` 等の読み取りだけに使う。
- 保存先は `.claude/handoff/YYYY-MM-DD-<slug>.md`。同名は上書きせず `-2` から連番にする。
- git repo では `.claude/handoff/.gitignore` がなければ `*` 1 行で新規作成する。既存なら触らず、repo の `.gitignore` と `.git/info/exclude` も変更しない。非 git repo では作成をスキップして保存は続ける。
- handoff と必要な専用 `.gitignore` の新規 Write 以外は行わず、既存ファイルの編集・削除、commit、push をしない。
- 秘密情報・資格情報・個人情報は値でなく参照方法を書く。

保存後、git repo では `git check-ignore -q .claude/handoff/<ファイル名>` を確認する。未 ignore なら「handoff が未追跡差分に出る状態」と警告し、コミットしない。

## 出力契約

次の順序で、空欄を作らず「なし」「未実行」も明示する。

```markdown
# Handoff: <短いタイトル> (YYYY-MM-DD)
> 次セッションへの読み込ませ方: 「.claude/handoff/<このファイル名> を読んで作業を再開して」

## タスクの目的
## 現在地
## 完了したこと
## 未完了・残作業
## 次のアクション(推奨順)
## 決定事項と理由
## 未解決の質問・保留事項
## 変更ファイル一覧
<コミット済みと未コミットを区別>
## 検証状態
<未実行は「未実行」と明記>
## 会話文脈の要約
```

内容は、再開可能性 / 次アクション具体性 / 事実と推測の区別 / 秘密情報なし / パスの曖昧さなし / 保存先契約を満たすこと。

## フロー

### 1. 棚卸し(read-only)

目的、決定と理由、却下案、残作業、未解決質問、ユーザー意図を会話から抽出する。repo では `git status --short`、`git diff --stat`、`git log --oneline -10` と検証結果を確認し、非 git なら明記する。

### 2. slug と保存先

slug は `^[a-z0-9]+(-[a-z0-9]+)*$`。`$ARGUMENTS` をそのまま slug に使わず、合致しなければ正規化した slug を提案して確認する。合致する場合は質問しない。保存先と専用 `.gitignore` を書き込み契約どおり準備する。

### 3. 生成とセルフチェック

出力契約へ統合し、保存前に全文を提示する。観測事実と推測を分け、上記 6 条件を満たすまで直す。

### 4. 保存と報告

handoff を新規 Write し、ignore 状態を検証する。保存パス、gitignore 状態(作成 / 既存 / 非 git でスキップ / 未 ignore)、次セッションへの読み込ませ方を報告する。
