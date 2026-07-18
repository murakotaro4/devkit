---
name: "backlog"
description: "残課題を横断的に棚卸しし、鮮度を判定して次アクションを提示する read-only スキル。「残りの作業は?」「残課題を棚卸しして」「やり残しを確認して」「/backlog」で起動"
argument-hint: "[topic]"
allowed-tools: ["Read", "Grep", "Glob", "Bash", "AskUserQuestion", "request_user_input", "TaskCreate", "TaskUpdate", "Skill"]
---

# /backlog - 残課題の横断棚卸し + dig-goal 引き継ぎ

親エージェント = 対象 repo に散在する残課題の read-only スキャン、統合、鮮度判定、ダッシュボード提示、dig-goal への引き継ぎ。backlog 自身はファイル変更、実装、実装オーケストレーションを行わない。

## 対象

$ARGUMENTS

## ハーネス判定

正本は devkit リポジトリの `AGENTS.md`「スキル共通契約」。この SKILL.md は Claude 親 / Codex 親の二層構成で実行する。要点:

- `AskUserQuestion` が使える -> Claude 親。
- なければ `spawn_agent` が使える -> Codex 親。
- どちらでもない -> 判定不能として扱い、選択肢を箇条書きで提示して自由文回答を求める。
- `request_user_input` は plan mode 依存で不安定なため、判定キーに使わない(Codex 親 plan mode の質問手段としてのみ使う)。

## タスクリスト連動

正本は devkit リポジトリの `AGENTS.md`「スキル共通契約 > タスクリスト連動」。backlog 開始時に step 1-5 をタスクリストへ登録し、各 step の開始時に `in_progress`、完了時に `completed` へ更新する(Claude 親: TaskCreate / TaskUpdate、利用不可なら省略可。Codex 親: 組み込み plan 機能または通常の進捗報告で同等の進捗提示)。TaskList は現在のセッション内の進捗だけを表し、repo を横断する残課題の正本にはしない。

## read-only 契約

- allowed-tools に Write / Edit を含めない。ファイル作成・編集・削除・移動を行わない。
- Bash は `git status`、`git log`、`git branch`、`git stash list`、`rg`、`gh` などの読み取り用途だけに使う。生成物の書き込み、format、lint、test 実行、依存更新、コード生成には使わない。
- 結果はチャットへ提示するだけで、ダッシュボードやレポートをファイルへ保存しない。
- backlog は作業の残りを扱う。コードの技術的負債は refactor、コード内の TODO / FIXME / XXX / HACK の探索も refactor の領分として非対象にする。

## 境界

- refactor = コードの負債を棚卸しする。backlog = handoff、plan、goal run、git、GitHub に残る作業の残りを棚卸しする。
- handoff = セッション終了時に残作業を書く側。backlog = 既存の handoff を含む情報源を読む側。backlog は handoff を新規作成・更新しない。
- TaskList = セッション内の作業管理。backlog = セッションやブランチを跨いだ残課題の横断確認。
- コード内 TODO / FIXME は refactor の領分であり、backlog の情報源スキャンには含めない。

## フロー

### 1. スコープ確認

対象 repo は現在の repo を既定とする。`$ARGUMENTS` があれば、機能名、トピック、期間、ブランチなどの絞り込みヒントとして扱う。対象や絞り込みが曖昧で結果が大きく変わる場合だけ選択肢付き質問で確認し、小さい未知は仮定を明示して進める。

ハーネス別の質問手段:

- Claude 親: AskUserQuestion を使う。
- Codex 親 plan mode: `request_user_input` を使う。
- Codex 親通常 mode / 判定不能: 選択肢を箇条書きで提示して自由文回答を求める。

締めに、対象 repo / トピック / 期間 / 除外範囲 / 採用した仮定を短く提示する。

### 2. 情報源スキャン

親が read-only で次の情報源をスキャンする。存在しないディレクトリや該当項目ゼロも結果として記録し、黙って省略しない。

- `.claude/handoff/*.md`: 「未完了・残作業」「次のアクション」「未解決の質問・保留事項」相当の節を読む。
- `.claude/plans/*.md`: 未実装、未承認、未検証、保留として残る計画項目を確認する。
- `.claude/goal-runs/*.md`: 未検収の実行レポート、停止条件、残作業を確認する。
- git: `git status --short`、現在ブランチの upstream との差、未 push commit、未マージブランチ、未コミット差分、`git stash list` を確認する。upstream がない場合はその事実を注記する。
- GitHub: `command -v gh` が通る場合だけ、open PR、未解決レビューコメント、CI が落ちている check を確認する。`gh` がない場合は PR 系スキャンをスキップし、「gh 不在のため未確認」と注記する。認証や権限で取得できない場合も同様に理由を明記する。

各候補に根拠パス、ブランチ、PR、または確認コマンドを付け、同じ作業を指す候補を後で統合できる形にする。

### 3. 統合と鮮度判定

同じ作業を指す候補をまとめ、情報源の日付、commit、ブランチ状態、PR 更新時刻、CI 状態を突き合わせる。古い handoff や plan の記述だけを根拠に未完了と断定しない。

候補は次に分類する:

| 状態 | 判断基準 |
|------|----------|
| 未完了 | 現在の差分、open PR、失敗中の CI、明示された残作業など、未完了を示す新しい根拠がある |
| 要確認 | 完了済みの可能性が高い、根拠が古い、情報源が矛盾する、または外部状態を取得できない |
| 完了済み | merge、検収、解消済みレビューなど、完了を示すより新しい根拠がある |

完了済みの可能性が高い項目は「未完了」へ混ぜず「要確認」へ置き、確認に必要なファイルまたはコマンドを添える。完了済みは重複再提案を避けるための根拠として短く示す。

### 4. ダッシュボード提示

結果をチャットへカテゴリ別に提示し、その後に推奨順の次アクションを示す。ファイルへは保存しない。

カテゴリは少なくとも、未コミット / ブランチ・未 push / PR・レビュー / CI / handoff・plan・goal run / 要確認に分ける。空のカテゴリは「該当なし」または「未確認」と明示する。各項目には状態、根拠、推奨アクションを付ける。

次アクションは `path/to/file` の確認・編集、`git diff -- ...`、`gh pr view ...` など、ファイル・コマンドレベルで具体化する。依存関係、緊急度、ブロッカー、短時間で閉じられるかを考慮して推奨順を付ける。

### 5. dig-goal への引き継ぎで終了

実装が必要な項目をユーザーが選んだ場合は、承認された項目を dig-goal の step 2 (調査 + 計画) に渡す計画草案として整形して出力する。詳細な実行契約は `plugins/devkit/skills/dig-goal/SKILL.md` を参照する。backlog 自身はここで終了し、実装・backend 選択・レビュー・修正ループはすべて dig-goal 側のフローで行う。

引き継ぎ形式:

```markdown
## dig-goal step 2 計画草案

### 目的
...

### write_scope
- ...

### 実装手順
1. ...

### 検証
- ...

### 非対象
- ...

### backlog 由来の根拠
- `.claude/handoff/...` ...
- `gh pr view ...` ...
```

ハーネス別の終了動作:

- Claude 親: Skill ツールが使える場合は dig-goal を起動し、上記の計画草案を渡す。利用不可なら、ユーザーに `/dig-goal` で計画草案を実行するよう案内する。
- Codex 親: `$dig-goal` を起動し、計画草案を渡すよう案内する。
- どちらの場合も、ユーザーが望むならダッシュボード提示のみで終了してよい。

## 注意

- 本スキル自身はファイルを変更せず、ダッシュボードも保存しない。
- 本スキル自身は実装 backend を選ばない。backend 選択は dig-goal 側の承認フローで行う。
- 未完了という記述と現在の repo / GitHub 状態が矛盾する場合は、より新しい根拠を優先しつつ「要確認」にする。
- `gh` 不在、未認証、権限不足、ネットワーク失敗は PR 系項目がないことを意味しない。未確認理由を明記する。
- 秘密情報、資格情報、トークン、個人情報をダッシュボードへ転記しない。
