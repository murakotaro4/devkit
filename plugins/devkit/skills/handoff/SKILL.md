---
name: "handoff"
description: "セッション終了時に、タスクの現在地・決定事項・次アクション・会話文脈を対象 repo の .claude/handoff/ へ引継ぎドキュメントとして書き出す(書き出し専用、gitignore 対象)。「引き継ぎを書いて」「引継ぎドキュメントを作って」「ハンドオフを作って」「/handoff」で起動"
argument-hint: "[topic]"
allowed-tools: ["Read", "Grep", "Glob", "Bash", "AskUserQuestion", "request_user_input", "TaskCreate", "TaskUpdate", "Write"]
---

# /handoff - セッション引継ぎドキュメント書き出し

親エージェント = 会話文脈・repo 状態・残作業の棚卸し、引継ぎ markdown の組み立て、対象 repo の `.claude/handoff/` への新規書き出し。書き出し専用で、読み込み・自動復元・commit / push は行わない。

## 対象

$ARGUMENTS

## ハーネス判定

正本は devkit リポジトリの `AGENTS.md`「スキル共通契約」。この SKILL.md は Claude 親 / Codex 親の二層構成で実行する。要点:

- `AskUserQuestion` が使える -> Claude 親。
- なければ `spawn_agent` が使える -> Codex 親。
- どちらでもない -> 判定不能として扱い、選択肢を箇条書きで提示して自由文回答を求める。
- `request_user_input` は plan mode 依存で不安定なため、判定キーに使わない(Codex 親 plan mode の質問手段としてのみ使う)。

## タスクリスト連動

正本は devkit リポジトリの `AGENTS.md`「スキル共通契約 > タスクリスト連動」。handoff 開始時に step 1-4 をタスクリストへ登録し、各 step の開始時に `in_progress`、完了時に `completed` へ更新する(Claude 親: TaskCreate / TaskUpdate、利用不可なら省略可。Codex 親: 組み込み plan 機能または通常の進捗報告で同等の進捗提示)。

## 書き込み契約

- step 1 は read-only。Bash は `git status`、`git diff`、`git log`、`rg`、`ls` など読み取り用途だけに使う。Bash での書き込み、mkdir、touch、ファイル編集は行わない。
- step 2 は `.claude/handoff/` の作成と `.claude/handoff/.gitignore` の新規作成のみ行える。新規 `.gitignore` の内容は `*` 1 行にする。既存 `.claude/handoff/.gitignore` がある場合は内容を書き換えず、repo の `.gitignore` と `.git/info/exclude` は変更しない。非 git repo では `.gitignore` 作成をスキップし、その旨を報告に注記する。
- step 4 は handoff ファイルの新規 Write のみ行える。保存先は対象 repo の `.claude/handoff/YYYY-MM-DD-<slug>.md`。同名ファイルは上書きせず、`YYYY-MM-DD-<slug>-2.md` のように連番にする。
- commit、push、既存ファイルの編集・削除は全 step で禁止する。
- 秘密情報、資格情報、トークン、個人情報を本文へ転記しない。必要な場合は値ではなく参照方法を書く。

既存 `.claude/handoff/.gitignore` がある場合も保存は中止しない。保存後、git repo なら `git check-ignore -q .claude/handoff/<ファイル名>` で ignore が効いているか検証する。効いていなければ報告に「handoff が未追跡差分に出る状態。コミットしないよう注意(既存 .gitignore の内容: <要約>)」という警告を含める。

## 出力契約

handoff ファイルは次のテンプレートをこの順序で持つ。

````markdown
# Handoff: <短いタイトル> (YYYY-MM-DD)

> 次セッションへの読み込ませ方: セッション冒頭で「.claude/handoff/<このファイル名> を読んで作業を再開して」と指示する。

## タスクの目的
<何を達成するためのセッションか。背景は必要最小限>

## 現在地
<いま何が分かっていて、どこで止まっているか>

## 完了したこと
- <完了済みの作業>

## 未完了・残作業
- <残っている作業>

## 次のアクション(推奨順)
1. <次に実行する具体的な作業。ファイル・コマンドレベルで書く>

## 決定事項と理由
- <決定>: <理由>

## 未解決の質問・保留事項
- <質問または保留事項。なければ「なし」>

## 変更ファイル一覧
git status --short / diff --stat 由来で、コミット済みと未コミットを区別する。

```text
<コミット済み変更>
<未コミット変更>
```

## 検証状態
- <実行したテスト・lint と結果。未実行は「未実行」と明記>

## 会話文脈の要約
<議論の流れとユーザー意図。解釈を含む場合は「推測」と明示する>
````

## セルフチェック

step 3 で、提示前に 6 項目を必ず確認する。

1. 再開可能性: このファイルだけで前提知識なしに再開できる。
2. 次アクション具体性: 次の作業がファイル・コマンドレベルで具体化されている。
3. 事実と推測の区別: 観測事実と解釈・推測が分かれている。
4. 秘密情報なし: 秘密情報、資格情報、トークン、個人情報の値を含まない。
5. パスの曖昧さなし: repo ルート相対パスまたは絶対パスで書かれている。
6. 保存先契約: パス、命名、gitignore の扱いが書き込み契約と一致している。

## フロー

### 1. 棚卸し(read-only)

会話文脈から、目的、決定と理由、却下案、未解決質問、ユーザー意図を抽出する。`git status --short`、`git diff --stat`、`git log --oneline -10` で repo 状態を確認し、非 git repo ならその旨を記録する。タスクリストの完了・未完了、セッション中のテスト・lint 結果も転記する。

### 2. slug 決定と保存先準備

slug は英小文字・数字・ハイフンのみ、1-4 語を目安にする(`^[a-z0-9]+(-[a-z0-9]+)*$`)。`$ARGUMENTS` はトピックのヒントとして扱い、そのまま slug に使わない。この形式に合致する場合だけ質問なしで採用し、合致しない場合(日本語、空白、`/` などを含む場合)は形式に正規化した slug を提案して 1 問だけ確認する。`$ARGUMENTS` がなければトピックから slug を提案して同様に確認する。質問手段はハーネス判定に従う。

保存パスは `.claude/handoff/YYYY-MM-DD-<slug>.md` とし、同名があれば `-2` から連番にする。対象 repo が git repo なら `.claude/handoff/` と `.claude/handoff/.gitignore` を準備する。`.gitignore` が存在しない場合だけ `*` 1 行で新規作成し、既存の場合は内容を触らない。準備は冪等に行う。非 git repo では `.gitignore` 作成をスキップする。

### 3. handoff 生成 + セルフチェック

出力契約のテンプレートへ情報を統合する。セルフチェック 6 項目を満たすまで修正し、保存前にチャットへ全文提示する。事実と推測を混ぜず、秘密情報は値を書かずに参照方法だけを書く。

### 4. 保存と報告

Write で handoff ファイルを新規保存する。git repo なら `git check-ignore -q .claude/handoff/<ファイル名>` で ignore 状態を検証する。ignore が効いていない場合は、既存 `.claude/handoff/.gitignore` の内容を要約し、handoff が未追跡差分に出る状態なのでコミットしないよう警告する。

報告には、保存パス、gitignore 状態(作成 / 既存 / 非 git でスキップ / 未 ignore 警告)、次セッションへの読み込ませ方 1 行を含める。

## 注意

- 読み込みモード、自動復元、handoff 一覧、SessionStart hook は非対象。
- commit、push は行わない。
- repo の `.gitignore` と `.git/info/exclude` には触らない。
- 非 git repo では保存のみ行い、gitignore 準備と check-ignore はスキップする。
- 会話要約は事実ベースで書き、解釈を含む場合は推測と明示する。
- 質問は slug 確認の 1 問だけにする。`$ARGUMENTS` が slug 形式に合致する場合は質問しない。