---
name: "dig-goal"
description: "要求を深掘りし、調査・計画・実行オーケストレーションから現セッション自律実行まで完遂する。「深掘りして」「実装して」「ゴールプロンプトを作って」「夜間実行の指示書を作って」「/dig-goal」で起動"
argument-hint: "[task]"
---

# /dig-goal - 深掘り + 実行オーケストレーション + 自律実行

親エージェント = 深掘り・調査・計画・統括・報告。実行形態は、ユーザーが判断をリアルタイムに供給する同席実装、判断を前倒しして同じセッションで完遂する現セッション自律実行、ユーザーが明示した例外形態としての起動プロンプト提示、の 3 系統とする。

## 対象

$ARGUMENTS

## 実行形態

配布先には devkit リポジトリの `AGENTS.md` が同梱されないため、この SKILL.md も実行形態の要点を保持する。軸はタスク規模ではなく自律度。

- 同席実装: その場で完成させる。成果物は実装済み diff。ユーザーが同席し、判断をリアルタイムに供給する。
- 現セッション自律実行: 判断を前倒しして焼き込んだゴール本文を作り、独立レビュー後そのまま同一セッションで実行して完遂する。成果物は実行完了と `.claude/goal-runs/` の完了レポート。
- 起動プロンプト提示: 定期実行・別ターミナル・別 PC・後で実行・白紙コンテキスト実行などをユーザーが明示した場合だけ使う例外形態。完成した起動プロンプトと検収チェックリストを提示して終了する。

## ハーネス判定

正本は devkit リポジトリの `AGENTS.md`「スキル共通契約」。この SKILL.md は Claude 親 / Codex 親の二層構成で実行する。要点:

- `AskUserQuestion` が使える -> Claude 親。
- なければ `spawn_agent` が使える -> Codex 親。
- どちらでもない -> 判定不能として扱い、選択肢を箇条書きで提示して自由文回答を求める。
- `request_user_input` は plan mode 依存で不安定なため、判定キーに使わない(Codex 親 plan mode の質問手段としてのみ使う)。

## タスクリスト連動

正本は devkit リポジトリの `AGENTS.md`「スキル共通契約 > タスクリスト連動」。dig-goal 開始時に step 1-9 をタスクリストへ登録し、各 step の開始時に `in_progress`、完了時に `completed` へ更新する(Claude 親: TaskCreate / TaskUpdate、利用不可なら省略可。Codex 親: 組み込み plan 機能または通常の進捗報告で同等の進捗提示)。

既定の実行フェーズでは、ゴール本文の進捗管理節に従いタスク登録・更新を行う。

## 進捗可視化

正本は devkit リポジトリの `AGENTS.md`「スキル共通契約 > 委譲・長時間ジョブの進捗可視化」。すべての委譲・長時間ジョブで次を守る。

- 委譲ジョブは 1 ジョブ = 1 タスクとしてタスクリストへ登録し、開始時 in_progress・完了時 completed へ更新する(親 step のタスクへ blockedBy で紐付ける)。
- Claude 親の `codex exec` / `cursor-agent` 委譲は Bash `run_in_background` で起動し、完了自動通知を契機に回収する。定期ハートビートは逐次表示しない。待機中は数分おき(目安 2〜5 分)に TaskOutput またはログファイルで出力増分を確認し、増分ゼロが続く場合のみ停滞の継続時間と推定原因(内部レビュー待ち / 長考 / ハング)を報告する。
- Claude 親の Agent 委譲は元々バックグラウンド実行 + 完了自動通知のため追加の起動処置は不要で、通知駆動で回収する。停滞検知の考え方は codex exec 委譲と同じ。
- Codex 親の子 agent 委譲は `wait_agent` で黙って待たず、定期的に進捗をユーザーへ提示する。
- Codex 親の cursor-agent 委譲はジョブのログファイルで出力増分を確認し、定期的に進捗をユーザーへ提示する。
- 実体の進捗は `git status` / `git diff` で確認し、resume を進捗確認に使わない。

## Codex モデル / effort 契約

- Codex のモデルは `gpt-5.6-sol` を `-m` で明示し、effort(`model_reasoning_effort`)は `medium` に固定する。effort の選択質問は行わない。世代追従は catch-up スキルと `premises.json` で管理する(ユーザーが別モデルを明示指定した場合はそれに従う)。
- Max は対応 surface の最深推論、Ultra は並列オーケストレーションを表す。この skill では説明にだけ用い、選択肢、CLI の effort、config 値にはしない。
- 並列方針はモデル / effort と独立に決める。並列化は分割可能性と write_scope の独立性で判断する。
- Codex 親が `spawn_agent` を使う場合は、子 agent ごとの effort 選択を追加しない。上記の固定値は `codex exec` などモデル / effort を指定できる経路だけに適用する。

codex exec の非対話実行形は次に固定する。

```bash
codex -a never exec -m gpt-5.6-sol -c model_reasoning_effort="medium" "<内容>" < /dev/null
```

## 書き込み契約

深掘り・調査・計画・承認までの step 1-5 と、自律実行用ゴール本文の組み立て・独立レビューは対象 repo に対して read-only とする。同席実装の step 6-9 と現セッション自律実行への移行後は、承認済み計画またはゴール本文の契約(write_scope・制約・停止条件・実行戦略)に従って書き込み・委譲を行う。

実行フェーズのツール面を事前制限しないため、frontmatter には `allowed-tools: ["TaskCreate", "TaskUpdate", "TaskOutput"]` のような許可リストを置かない。作成フェーズでは、実行環境に存在する `AskUserQuestion`、`spawn_agent`、`request_user_input` なども以下の read-only 契約に従って使う。

- 作成・計画フェーズは対象 repo に対して read-only。Bash は `command -v`、`git status`、`rg`、`ls`、`find`、テスト・lint コマンドの存在確認など読み取り用途だけに使う。対象 repo への Bash 書き込み、mkdir、touch、ファイル編集は行わない。
- 例外は step 7 の独立レビュー運用だけ。`mktemp` による一時領域 `JOB_DIR` の作成とレビューログ書き込みは可とする。対象 repo への書き込みは不可。
- 既定(現セッション自律実行)でも、親は実行開始前にゴール本文全文を `.claude/goal-runs/YYYY-MM-DD-<slug>-goal.md` へ保存する。この保存はコンテキスト圧縮後の復帰点であり、保存に失敗した場合は実行を開始せず停止・報告する。
- 既定経路のゴールファイル・進捗ログ・完了レポートは、実行中に作業 worktree を作る場合でも常に起動元 checkout(スキル起動時の cwd を含む checkout)の `.claude/goal-runs/` を保存先とし、使い捨て worktree 内には置かない。step 6 の組み立て時に起動元 checkout 基準の具体パスへ解決して本文へ焼き込む。
- 対象が git 管理下にない場合は、起動元 checkout の代わりにスキル起動時の cwd を基準ディレクトリとし、その `.claude/goal-runs/` を同様に使う。ディレクトリと `*` 1 行の `.gitignore` は同様に ensure するが、検証不能のため `git check-ignore` は行わず skip する。
- 例外形態では、step 9 の Write 保存はファイルが必要な形態(`/loop`・`/schedule`・別ターミナルの背景起動)または 4,000 字超 fallback の場合だけ行う。例外形態のインライン `/goal` と Codex 貼付けでは親はゴールファイルを作らず、実行側の自己保存(best-effort)契約を維持する。
- 親が保存するゴールファイルの既定パスは `.claude/goal-runs/YYYY-MM-DD-<slug>-goal.md`。命名規則はゴールファイル `YYYY-MM-DD-<slug>[-N]-goal.md`、完了レポート `YYYY-MM-DD-<slug>[-N].md` とし、連番 `-N` は `-goal` サフィックスの前に置く(`<slug>-goal-2.md` ではなく `<slug>-2-goal.md`)。既定経路は step 6 で衝突しない最終 basename を確定し、例外形態の自己保存では同名を上書きせず連番へ進む。
- 親がファイル保存する経路では、親が `.claude/goal-runs/` と `*` 1 行の `.gitignore` を ensure する。例外形態のインライン経路では実行エージェントが自己保存時に同じ ensure を行う。このディレクトリと `.gitignore` の作成は実行移行・成果物保存の書き込み契約の例外とする。既存の `.gitignore` がある場合は内容を変更しない。
- git 管理下では、親が保存した後に `git check-ignore` で ignore が効いているか検証する。効いていない場合は保存を維持したまま、既定では実行直前の通知と最終報告、例外形態では起動プロンプト提示に「git 管理対象になっている」警告を添える(既存 `.gitignore` の内容は変更しない)。非 git では検証不能のためこの検証を skip する。
- 既定では step 8 で実行へ移行する。cron 登録・`/schedule` 登録はどの step でも行わない。作成フェーズは read-only、実行フェーズはゴール本文の契約に従う。直起動の書き込み・破壊的操作・外部状態変更は step 1 の明示回答から転記された許可がある場合だけ行う。commit / push・統合はゴール本文に記載された統合方法(既定は PR 経由。承認済み計画がある場合はその統合方法)に従う。統合しないが明示された場合は commit / push を行わない。無回答・曖昧な回答から統合以外の書き込み・破壊的操作・外部状態変更の許可を推定しない。
- 保存前後を問わず、秘密情報、資格情報、トークン、個人情報をプロンプト本文へ転記しない。必要な場合は「環境に既に存在する設定を読む」と書き、値そのものは書かない。

## フロー

### 1. 深掘り(棚卸し駆動面談、親)

Claude 親は step 1 開始時に plan mode 外であれば `EnterPlanMode` を呼んで plan mode へ入る。step 1-5 の read-only 契約は plan mode と整合する。

最初のラウンドでタスク型(実装 / 調査 / 状態確認 / 文書化 / 整理)と暫定実行形態(同席 / 現セッション自律実行 / 起動プロンプト提示)を確定し、未知棚卸しのシードにする。選択肢付き質問を繰り返し、ユーザーの**要求**(目的、成功条件、非対象、優先度、好み)を聞き出す。

毎ラウンド冒頭に次の形式の未知棚卸し表を提示し、前ラウンドから更新して差分が見える形にする。

| 未知 | 影響 | 扱い |
|------|------|------|
| <未確定事項> | <成功条件・安全性・設計への影響> | 質問する / 仮定で進める / 確定済み |

- 扱いは「質問する」「仮定で進める」「確定済み」の 3 値だけを使う。
- 「質問する」行がゼロになったら深掘りを終了し、要件サマリー(目的 / 成功条件 / 非対象 / 採用した仮定)で締める。固定ラウンド数はなく、深さは可変とする。
- 必ず聞く最低ライン: データ構造、既存互換性、外部連携、保存・ログ、権限、テスト合否基準、UI フロー、業務判断、後戻りが大きい設計判断。これらを棚卸しのシードとして維持し、追加観点はカタログ化せず親が対象に応じて推定する。
- 1 ラウンド最大 4 問、必ず選択肢付きで聞く。設計判断を聞く場合は親の推奨を付ける。命名、軽微な文言、内部実装の細部など小さい未知は仮定を明示して進め、採用した仮定を計画へ記載する。
- 暫定実行形態が現セッション自律実行または起動プロンプト提示の場合、停止条件 3 種(達成停止 / 上限停止 / 行き詰まり停止。上限停止は省略禁止)、破壊的操作の可否、外部状態変更の具体的な対象・操作と可否、write_scope、進捗の残し方を必ず「質問する」行として棚卸しへ載せる。無回答・曖昧な回答から許可を推定しない。
- 統合方法は質問しない。実装系の既定は PR 経由であり、step 2 の調査で自動確定する。

ハーネス別の質問手段:

- Claude 親: AskUserQuestion を使う。
- Codex 親 plan mode: `request_user_input` を使う(1 呼び出し最大 3 問)。
- Codex 親通常 mode: `/plan` での再実行を 1 回だけ案内した上で、選択肢を箇条書き提示して自由文回答を求める。
- 判定不能: 選択肢を箇条書き提示して自由文回答を求める。

### 2. 調査 + 計画(親)

対象 repo やファイルを read-only で調査し、decision-complete な計画を作る。

実装系の計画に必ず含める:

- write_scope: 変更するファイルの一覧
- 各ファイルの具体的な変更内容
- 検証コマンド(テスト・リンタ)
- 非対象(やらないこと)
- 作業ブランチ名(`<type>/<slug>`)
- 統合方法: 既定は PR 経由(提出 + CI green 確認 + merge)。`command -v gh` が通らない場合、origin なし repo、または `git remote get-url origin` の URL ホスト名が非 GitHub ホストの場合は直接統合へ自動フォールバックし、その旨を計画に明記する。GitHub ホストの origin で `command -v gh` は通るのに `gh repo view` 等が認証切れ・API 障害・ネットワーク断などで失敗する場合は、直接統合へフォールバックせず停止・報告する。ユーザーが直接統合または統合しないを明示した場合のみそれに従う。自動フォールバックは計画作成時の確定であり、実行中の統合方法切り替えではない
- PR 経由では repo 内 CI 設定ファイルと GitHub 側設定(`gh api` で取得できる branch ルール・required status checks 等)を調査し、CI 有無・チェック 0 件の扱い・CI 待機上限(既定 30 分)を記載する。CI なし判定でも PR 作成後の登録猶予内に checks が観測されたら、観測を優先して CI ありへ切り替える
- 最終 commit メッセージ案
- 計画レビュー / 実装 / diff レビューそれぞれの backend。モデル / effort は適用可能な場合だけ追記し、非対応経路は「適用なし」と記す

非実装の計画に必ず含める:

- read_scope: 読み取る repo・ファイル・外部情報の範囲
- 成功条件と検証方法
- 非対象と外部状態変更可否
- 実行形態
- ブランチ / commit / 統合 / 実装 backend: 適用なし
- 現セッション自律実行または起動プロンプト提示では、停止条件 3 種、具体的な上限、`.claude/goal-runs/` のゴールファイル・進捗ログ・完了レポートを必須とする
- 同席 read-only は通常の最終報告で終了し、ゴール本文・worktree・`.claude/goal-runs/` 成果物を作らない

### 3. backend 選択(選択肢付き質問)

計画承認の前に、計画レビュー用 / 実装用 / diff レビュー用の backend のうち適用するものだけを選択肢で確認し、結果を計画に明記する。実行形態は step 1 で暫定確定済みなので、ここでは backend だけを選ぶ。親はタスク規模に応じた推奨を各問 1 つ付ける。現セッション自律実行では diff レビュー backend の質問を出さない。ゴール本文の実装後レビュー要件が担う。非実装では実装 backend は適用なしとする。この時点で実行形態を変更する場合は step 1 の未知棚卸しを再開し、「質問する」行がゼロになるまで step 3 以降へ進まない。


#### Claude 親の選択肢

codex 経路は Claude 親限定でモデル / effort を固定する: モデルは `gpt-5.6-sol` を `-m` で明示し、effort(`model_reasoning_effort`)は `medium` に固定する。effort の選択質問は行わない。

実装 backend:

| 選択肢 | 実行方法 |
|--------|----------|
| codex — gpt-5.6-sol medium | `codex exec` + `-m gpt-5.6-sol -c model_reasoning_effort="medium"`。標準の実装(既定) |
| cursor-agent — Composer 2.5 | cursor-agent -p + --model composer-2.5。軽い〜標準実装の高速レーン(Cursor 自社モデルプール) |
| Claude サブエージェント — Sonnet | Agent(general-purpose, model=sonnet)。世代非依存 alias で常に最新 Sonnet |

計画レビュー / diff レビュー backend(選択肢は共用。計画レビューの実行方法は step 4、diff レビューは step 7 を参照):

| 選択肢 | diff レビューの実行方法 |
|--------|----------|
| codex review — gpt-5.6-sol medium | `codex -a never exec -m gpt-5.6-sol -c model_reasoning_effort="medium" review --base origin/<default> < /dev/null`(origin なし repo は `--base <default>`)。標準の計画レビュー / diff レビュー(既定) |
| Claude サブエージェント — Opus | Agent(general-purpose, model=opus)に diff と計画を渡してレビュー |
| 親のみ / スキップ | セカンドオピニオンなし。軽微な変更向け(diff レビューでリポジトリルールが独立レビュー必須の場合は提示しない) |

- Codex のモデルは `gpt-5.6-sol` を `-m` で明示する。世代追従は catch-up スキルと `premises.json` で管理する(ユーザーが別モデルを明示指定した場合はそれに従う)
- Max は対応 surface の最深推論、Ultra は並列オーケストレーションを表す。この skill では説明にだけ用い、backend 選択肢、CLI の effort、config 値にはしない
- 並列化の判断はモデル / effort と独立に行い、step 6 の実装委譲の並列化契約に従う
- `command -v codex` が通らない場合は codex の選択肢を除外し、残りの選択肢(cursor-agent・Claude サブエージェント)を提示する
- Claude 親では Codex の実装 backend を提示する前に `command -v python3` も確認する。通らない場合は thread_id 抽出に必要な prerequisite 不足としてユーザーへ報告し、Codex の実装 backend だけを除外する。python3 を使わない Codex の計画レビュー / diff レビュー選択肢は残し、黙って別 backend へ fallback しない
- cursor-agent は --model composer-2.5 を明示する(auto はサードパーティモデルへルーティングされうるため使わない)。Composer の新版が出たら SKILL.md のモデル名を更新する
- `command -v cursor-agent` が通らない場合は cursor-agent の選択肢を除外する(codex ゲートと同形式。Claude 親・Codex 親の両テーブルに適用)

#### Codex 親の選択肢

`codex exec` 子プロセスの入れ子と `claude` CLI への逆委譲は選択肢に入れない。
Codex 親の `spawn_agent` では子 agent ごとの effort を選択・指定しない。並列数や役割分担は実装戦略として扱い、effort 選択と混同しない。

| 役割 | 選択肢 | 実行方法 |
|------|--------|----------|
| 実装 | `spawn_agent` worker | 実装指示 1 ブロック(write_scope / 受け入れ条件 / 検証 / commit 禁止)を渡し、`wait_agent` で回収する。修正ループで `send_input` を使うため `close_agent` は指摘解消まで遅延する |
| 実装 | cursor-agent (Composer 2.5) | shell で cursor-agent -p を起動し、実装指示 1 ブロックを渡す。spawn_agent 系統とは独立した shell 実行系統。修正ループは --resume <chatId>(実行方法は step 6/8 の Claude 親 + cursor-agent と同じコマンド形) |
| 実装 | 親実装 | 軽微な変更向け。この場合も diff レビューは必ず独立 agent に出す |
| 計画レビュー | `spawn_agent` explorer | read-only 指示を明記し、計画全文を審査させる |
| 計画レビュー | スキップ | 軽微な計画向け |
| diff レビュー | `spawn_agent` explorer | read-only 指示を明記し、diff 全文と計画を審査させる |
| diff レビュー | スキップ | リポジトリルールが独立レビュー必須でない軽微な変更向け |

Codex 親で `spawn_agent` / `wait_agent` が使えない場合は、選択肢を再提示する。実装 backend に cursor-agent が選択済みで `command -v cursor-agent` が通る場合は、spawn_agent 不在でも shell 経由の実装委譲を継続できる。いずれの実装委譲も使えない場合は、承認を得て親実装にフォールバックする。

### 4. 計画レビュー(選択 backend)

計画全文を渡し、decision-complete か・矛盾や見落としがないかを審査させ、指摘を計画に反映してから承認に進む。「スキップ」選択時はこの step を省略してそのまま承認へ進む(軽微な計画向け)。

ハーネス別の実行方法:

- Claude 親 + codex: `codex -a never exec --sandbox read-only -m gpt-5.6-sol -c model_reasoning_effort="medium" "<計画レビュー指示>" < /dev/null` を Bash `run_in_background` で起動し、完了自動通知で回収する
- Claude 親 + Claude サブエージェント: Agent(general-purpose、選択モデル)に計画全文と背景を渡す
- Codex 親: `spawn_agent`(explorer) に read-only 指示と計画全文を渡し、`wait_agent` で回収する

### 5. 計画承認

計画レビューを経た(skip 選択時は未実施の)、backend と、適用可能な場合だけモデル / effort が明記された計画で承認を得る。モデル / effort 非対応の経路は「適用なし」と記す。codex のモデル / effort 欄は `gpt-5.6-sol` / `medium` 固定と記す。同席実装では計画レビュー / 実装 / diff レビューの 3 役を明記する。現セッション自律実行では diff レビュー backend を明記せず、ゴール本文に実装後レビュー要件を焼き込む旨を計画へ明記する。承認なしで実装・実行移行に進まない。`ExitPlanMode` による承認前は step 6(実装・実行移行)へ進まない。

ハーネス別の承認手段:

- Claude 親: step 1 で入った plan mode から `ExitPlanMode` で承認を得ることに一本化する。
- Claude 親で `EnterPlanMode` が利用できないハーネスの縮退経路に限り、通常 mode で計画全文を提示して明示承認を得る。
- Codex 親 plan mode: 計画全文を提示し、`request_user_input` で承認確認する。
- Codex 親通常 mode / 判定不能: 計画全文を提示し、自由文で明示承認を得る。

`ExitPlanMode` 承認後は plan mode を抜け、以後は承認済み計画の write_scope に従う書き込み契約を適用する。

## 同席実装パス(step 6-9)

同席実装を選んだ場合は、承認済み計画に従って次の step 6-9 を実行する。同席 read-only の非実装タスクはこのパスへ入らず、通常の最終報告で終了する。

## worktree 運用と統合

この節は同席実装パス(diff を作る)だけに適用する。非 git repo、現セッション自律実行、調査のみの同席実行は対象外。自律実行ではゴール本文の実行戦略が worktree 運用を持ち、実行側が作成する。

### 作成

計画承認後・実装委譲前に親が実行する。

1. `git symbolic-ref --short refs/remotes/origin/HEAD` の結果から `origin/` プレフィックスを取り除いた名前を `<default>` とする。取得できなければ `main`、`main` も無ければ現在のブランチを基点にする。
2. `git -C "<repo>" fetch origin` を実行する(origin が無ければ省略)。fetch 失敗は警告を報告して続行し、統合前に再試行する。
3. `WT_DIR=$(mktemp -d "${TMPDIR:-/tmp}/devkit-dig-goal-wt.XXXXXX") && echo "WT_DIR=$WT_DIR"` を実行し、親が echo されたパスを記録する。
4. `git -C "<repo>" worktree add -b <type>/<slug> "$WT_DIR/wt" origin/<default>` を実行する。`origin/<default>` が無ければ `HEAD` を基点にする。ブランチ名が既存なら `-2` から連番を付ける。
5. worktree add 直後の `git -C "<worktree>" rev-parse HEAD` を、worktree add に使った起点の `<base-commit>` として親が記録する。
6. worktree add 失敗時は mktemp ディレクトリを削除し、main ツリー実装へ黙って戻らず、失敗を報告して指示を仰ぐ。

以後の実装・検証・レビュー・修正はすべて worktree 内で行う。委譲コマンドの `-C`、cursor-agent の `--workspace`、検証コマンドの cwd、review の実行場所はすべて worktree とし、main の作業ツリーでは実装しない。

### 節目 commit 契約

実装 backend は従来どおり commit 禁止。親が作業ブランチへ次の節目ごとに commit する。

- 並列ジョブ 1 件を回収し、diff を確認した後
- 修正ループ 1 周の修正確認後
- 親のドキュメント同期後

add は必ずパス限定(`git add <そのジョブの write_scope>`)で行い、実行中の別ジョブの未完了変更を巻き込まない。`git add .` と `git add -A` は使わない。commit メッセージは Conventional Commits・日本語とする。

pre-commit hook(prek 等)が unstaged 変更を stash してから検査を走らせる構成の repo では、並列ジョブが実行中の間は節目 commit を保留する。全ジョブ回収後に、ジョブ単位で順にパス限定 commit する。

### 統合(step 9、終了条件達成後)

1. `git fetch origin` を再試行し、`origin/<default>` が進んでいれば worktree 内で rebase して検証を再実行する。rebase conflict のうち、repo のルール(AGENTS.md 等)に標準解消手順が定義されている衝突クラスはその手順で解消して rebase を続行してよい(解消後は検証を再実行する)。それ以外の衝突は `git rebase --abort` して停止・報告する。
2. その後、repo の release 規則が version bump 等の単調増加値を要求する場合、origin の現行値から再計算して更新し、親がパス限定で commit する。
3. 直接統合(PR 不可時の自動フォールバック、またはユーザー明示時): 主 worktree(repo 本体)で行う。主 worktree が clean・`<default>` ブランチ上・origin と diverged していないことを確認する。behind は ff で取り込み、dirty / diverged / 別ブランチなら停止・報告する。その後 `git -C "<repo>" merge --ff-only <branch>`(rebase 直後のため常に ff 可能)→ `git -C "<repo>" push origin <default>` を実行する。push reject は fetch して手順 1 からやり直し、version の再計算もやり直す。hook 失敗は停止・報告する。
4. PR 経由(既定): 次の状態機械を順に実行する。
   1. 提出: `git -C "<worktree>" push -u origin <branch>` → `gh pr create --base <default> --head <branch> --title "<title>" --body "<body>"` のように非対話で実行できるフラグをすべて明示し、出力から PR URL / 番号を記録する。以降の `gh` コマンドは記録した PR 番号を明示し、現在ブランチの推測に依存しない。
   2. CI 待機: watch モードは使わず、進捗可視化契約の間隔(数分おき)でポーリングする。各回で `gh pr view <PR番号> --json headRefOid` によりポーリング前の head SHA を取得 → `gh pr checks <PR番号> --json bucket,name` を取得 → 同じ `gh pr view <PR番号> --json headRefOid` でポーリング後の head SHA を取得し、前後の SHA が一致する場合だけ checks と head SHA を同じ判定対象として扱う。前後で不一致ならその checks 結果を破棄して期限内で次のポーリングへ進む。親が開始時刻を記録し、開始時刻からの経過時間を待機上限(計画に記載した値、既定 30 分)と照合して期限を管理する。期限超過時点で merge せず停止・報告する。PR 作成直後に check が未登録で `no checks reported` エラーになった場合は、数分の猶予を置いて再試行する。
   3. green 判定: CI 待機ポーリングの同じ判定対象にある `bucket` を明示判定する。全件 `pass`(`skipping` は許容)のときだけ、その時点の安定した head SHA を「検証済み SHA」として記録して merge 可とする。`fail` / `cancel` があれば赤、`pending` があれば期限内でポーリングを継続する。`gh` の API・認証エラーをチェック 0 件の成功と混同せず、エラーなら停止・報告する。チェック 0 件の扱いは計画作成時に repo 内 CI 設定ファイルと GitHub 側設定(`gh api` で取得できる branch ルール・required status checks 等)を調査して対象 repo の CI 有無を計画へ記載して決める。CI なし repo でも PR 作成後は `no checks reported` と同じ数分の登録猶予を待ち、その間に checks が観測されたら計画記載より観測を優先して CI ありへ切り替え、通常の green 判定を行う。登録猶予を過ぎても checks 0 件のときだけ、その時点の安定した head SHA を検証済み SHA として記録して merge 可とする。CI あり repo で 0 件が続く場合は停止・報告する。
   4. merge: state 変更コマンドを実行する前に merge queue preflight を行う。`gh api repos/<owner>/<repo>/rules/branches/<default>` の結果に `type` が `merge_queue` の rule が含まれないこと、`gh api graphql -f query='query($owner:String!,$repo:String!,$number:Int!){repository(owner:$owner,name:$repo){pullRequest(number:$number){mergeQueueEntry{id}}}}' -f owner=<owner> -f repo=<repo> -F number=<PR番号>` の `mergeQueueEntry` が空で queue 未投入であること、`gh pr view <PR番号> --json autoMergeRequest` で auto-merge 未有効化であることを確認する。いずれかに該当する場合、または preflight の API・認証エラー時は `gh pr merge` を実行せず停止・報告する。preflight 通過後、merge 直前に `gh pr view <PR番号> --json headRefOid` を再取得し、検証済み SHA と一致することを確認する。不一致なら green だった checks は旧 head のものなので merge せず停止・報告する。一致時だけ `gh pr merge <PR番号> --merge --match-head-commit <検証済みSHA>` を実行する。方式フラグは必ず明示し、repo のルールが squash 等の方式を定める場合はそれを優先する。`--delete-branch` は使わない。merge コマンド失敗時に別方式へ自動で切り替えない。
   5. 完了確認: `gh pr view <PR番号> --json state,mergedAt` で `MERGED` を確認して初めて統合完了とする。
   6. 後始末(順序固定): 共通で `MERGED` 確認 → `git fetch origin` → ローカルの作業 branch tip を記録 → `git ls-remote --heads origin refs/heads/<branch>` で完全refを指定して remote branch の存在と現在 tip を確認する。成功時の結果は0件(remote不在)または厳密1件(remote存在)だけを受け入れ、複数件は確認不能として扱う。`ls-remote` 自体の失敗(API・認証・通信エラー等)を空結果と混同せず、「統合成功・cleanup 未完了」として停止・報告する。
      - remote branch が存在しない(`ls-remote` が成功かつ空結果)場合: `gh pr view <PR番号> --json state,mergedAt,headRefOid` で `state` が `MERGED`、`mergedAt` が非空、`headRefOid` が記録したローカル branch tip(検証済み SHA)と一致することを確認する。一致時は「remote 削除は GitHub 側で完了済み」としてremote削除を成功扱いにし、cleanup 未完了にはせず、後述のmerge方式別ローカルcleanupを続行する。不一致または確認不能なら削除へ進まず、「統合成功・cleanup 未完了」として報告する。
      - remote branch が存在する場合: `ls-remote` で得たremote tipが検証済み SHA(merge した head)と一致することを確認する。不一致なら削除へ進まず、「統合成功・cleanup 未完了」として remote に新 commit が残っている旨を報告する。一致時だけremote削除が必要と記録し、後述のローカルcleanupへ進む。
      - merge方式別ローカルcleanup: merge commit 方式では `git merge-base --is-ancestor <branch-tip> origin/<default>` で ancestor と確認してから、`git worktree remove <worktree>` → `git branch -d <branch>` の順に削除する。repo ルールが squash / rebase 方式を定める場合は ancestor 前提を使わず、`gh pr view <PR番号> --json state,mergedAt,headRefOid` で `state` が `MERGED`、`mergedAt` が非空、`headRefOid` が記録したローカル branch tip と一致することを確認し、その削除許可の根拠を記録してから `git worktree remove <worktree>` → `git branch -D <branch>` の順に削除する。
      - remote削除: remote branch存在時はローカルcleanup完了後に `git push --force-with-lease=refs/heads/<branch>:<検証済みSHA> origin :refs/heads/<branch>` で期待 tip を明示してremote branchを削除する。GitHub側で削除済みの場合はremote削除コマンドを省略する。
      - 必要な確認が取れない場合またはremote tipが不一致の場合は、remote branchを削除せず「統合成功・cleanup 未完了」とする。lease 失敗時は remote branch を削除せず「統合成功・cleanup 未完了」とする。remote に新 commit が残っている場合はその旨と残存物のパス・ブランチ名を報告する。cleanup 途中の失敗も同区分で報告する(merge 失敗と区別する)。
   7. CI 赤・merge 失敗時: PR を open のまま残し、worktree・ローカル / remote ブランチ・commit を破棄せず、失敗チェック名・PR URL・再開コマンドを報告して停止する。step 8(修正ループ)へ自動では戻らない。
5. 後始末: 統合完了(直接統合の push 成功、または PR の `MERGED` 確認)後に行う。直接統合では `git worktree remove` と統合済み確認後の `git branch -d <branch>` を使う。PR 経路では手順 4.6 の固定順序に従う。worktree remove が未追跡ファイル等で拒否された場合は `--force` せず、パスを報告する。

origin なし repo では fetch / push / PR 経路を省略する。直接統合は主 worktree での `merge --ff-only` までで統合完了と扱い(push なし)、報告にその旨を明記する。

### 失敗時の共通契約

変更を破棄しない。統合完了前の失敗では worktree・ブランチ・commit をそのまま残し、ブランチ名 / worktree パス / 止まった操作 / 再開コマンドを報告して停止する。cleanup 途中の失敗では完了済みの cleanup 操作を巻き戻さず、未完了の残存物と再開コマンドを報告する。PR 経路では、CI 赤は PR を open のまま merge せず停止、merge 失敗は別方式へ切り替えず PR を open のまま停止、cleanup 失敗は「統合成功・cleanup 未完了」として残存物を報告、の 3 区分を明示する。

### 6. 実装委譲(backend)

計画を実装指示 1 ブロックに変換して委譲する。指示ブロックに必ず含める:
目的 / write_scope(これ以外のファイルに触らない) / 具体的な変更内容 / 受け入れ条件 / 検証コマンド / commit 禁止。

ハーネス別の実行方法:

- Claude 親 + codex:
  1. `JOB_DIR=$(mktemp -d "${TMPDIR:-/tmp}/devkit-codex-job.XXXXXX") && echo "JOB_DIR=$JOB_DIR"` でジョブ専用領域を作り、echo された JOB_DIR を親が記録する。
  2. `JOB_DIR=<echo された記録済みのパス> && set -o pipefail && codex -a never exec -C "<worktree>" --sandbox workspace-write -m gpt-5.6-sol -c model_reasoning_effort="medium" --json "<実装指示>" < /dev/null | tee "$JOB_DIR/codex-events.jsonl"` を Bash `run_in_background` で起動する。`tee` により JSONL stdout を TaskOutput へ可視化しながらジョブ専用 event log に保存し、`pipefail` で codex / tee いずれの失敗も検出する。
  3. 完了自動通知後、記録済みパスを使い `JOB_DIR=<echo された記録済みのパス> && python3 -c 'import json,sys; ids=[event.get("thread_id") for line in open(sys.argv[1], encoding="utf-8") if line.strip() for event in [json.loads(line)] if event.get("type") == "thread.started"]; (len(ids) == 1 and isinstance(ids[0], str) and ids[0]) or sys.exit("expected exactly one non-empty thread.started thread_id"); print(ids[0])' "$JOB_DIR/codex-events.jsonl" > "$JOB_DIR/thread-id.txt" && test -s "$JOB_DIR/thread-id.txt"` を実行する。全 event を保持せず `thread.started` の ID だけを収集し、厳密に 1 件で thread_id が非空の場合だけ保存する。失敗時は resume せず委譲失敗として報告する。
- Claude 親 + cursor-agent: `JOB_DIR=$(mktemp -d "${TMPDIR:-/tmp}/devkit-dig-goal-job.XXXXXX") && CHAT_ID="$(cursor-agent create-chat | tr -d '\r\n')" && test -n "$CHAT_ID" && printf '%s\n' "$CHAT_ID" > "$JOB_DIR/chat-id.txt" && echo "JOB_DIR=$JOB_DIR"` で chatId を保存してから `JOB_DIR=<echo された記録済みのパス> && cursor-agent -p --resume "$(cat "$JOB_DIR/chat-id.txt")" --trust --force --model composer-2.5 --workspace "<worktree>" --output-format text "<実装指示>"` を Bash `run_in_background` で起動し、完了自動通知で回収する(echo された JOB_DIR のパスを親が記録し、step 8 の修正ループでは記録済みのパスを使う。シェル変数はツール呼び出し間で失われるため。test -n 失敗 = create-chat 失敗として委譲を中止し親が報告する。Claude 親では出力を TaskOutput で確認するためログリダイレクトは付けない)
- Claude 親 + Claude サブエージェント: Agent(general-purpose、選択モデル)に同じ指示ブロックを渡す
- Codex 親: `spawn_agent`(worker) に同じ指示ブロックを渡し、`wait_agent` で回収する。`close_agent` は修正ループ完了まで遅延する
- Codex 親 + cursor-agent: shell 経由で同じコマンドを実行する。ただし Codex 親には TaskOutput がないため `> "$JOB_DIR/cursor-agent.log" 2>&1` のログリダイレクトを付けて実行し、進捗提示はログ増分で行う

実装委譲の並列化:

- 計画の write_scope を互いに素なジョブに分割できる場合、依存のないジョブは並列に委譲する。
- Claude 親: 複数の `codex exec` / `cursor-agent -p` を Bash `run_in_background` で同時起動する。Codex ジョブは JOB_DIR / `codex-events.jsonl` / `thread-id.txt` をジョブごとに発行・分離し、cursor-agent も JOB_DIR / chatId をジョブごとに分離する。出力は各バックグラウンドタスクの TaskOutput で確認する。Codex 親もジョブごとのログ分離を維持する。または複数 Agent に委譲する。
- Codex 親: 複数の `spawn_agent` worker に同時委譲する。
- 並列ジョブには「担当 write_scope 外に触らない」「テスト・リンタは走らせない(親が統合後に一括実行)」を明記する。
- 並列ジョブは同一 worktree・同一ブランチ内で write_scope を互いに素とし、親は回収したジョブから順に diff を確認してパス限定の節目 commit を行う。ただし「節目 commit 契約」の pre-commit hook 例外に従い、stash 構成では全ジョブ回収まで commit を保留する。
- 依存があるジョブは前段完了後に直列で流す。

委譲中の回収・停滞検知は「進捗可視化」節に従う。調査のみの委譲は read-only で行う。

### 7. 自レビュー(親)

`git diff <記録した基点>...HEAD` を全文読み、計画と突き合わせる。計画からの逸脱(write_scope 追加、方式変更など)が見つかったら、逸脱ごとに理由・リスク・要確認点を記録し、採用するか差し戻すかを親が判断する。プロジェクトのテスト・リンタを実行する。

step 3 で選択した diff レビュー backend でセカンドオピニオンを取る(「親のみ」を選択した場合は省略)。実装 worker と同一 agent にレビューさせず、独立した reviewer / explorer に出す。節目 commit 済みでも `--base origin/<default>`(origin なし repo はローカル `<default>`)によりブランチ全体が審査対象になる。

ハーネス別のレビュー手段:

- Claude 親 + codex review: worktree 内で `codex -a never exec -m gpt-5.6-sol -c model_reasoning_effort="medium" review --base origin/<default> < /dev/null`(origin なし repo は `--base <default>`)を Bash `run_in_background` で起動し、完了自動通知で回収する
- Claude 親 + Claude サブエージェント: Agent(general-purpose、選択モデル)に diff 全文と計画を渡す
- Codex 親: `spawn_agent`(explorer) に read-only 指示、diff 全文、計画を渡し、`wait_agent` で回収する

### 8. 修正ループ

指摘があれば再委譲する:

- Claude 親 + codex: 初回の対象 worktree、workspace-write sandbox、approval policy、固定のモデル / effort、step 6 で記録したジョブ固有 thread_id を維持し、`JOB_DIR=<step 6 で記録したパス> && test -s "$JOB_DIR/thread-id.txt" && codex -a never -C "<worktree>" --sandbox workspace-write exec resume -m gpt-5.6-sol -c model_reasoning_effort="medium" "$(cat "$JOB_DIR/thread-id.txt")" "<指摘と修正指示>" < /dev/null` を Bash `run_in_background` で起動して完了自動通知で回収する
- Claude 親 + cursor-agent: `JOB_DIR=<step 6 で記録したパス> && cursor-agent -p --resume "$(cat "$JOB_DIR/chat-id.txt")" --trust --force --model composer-2.5 --workspace "<worktree>" --output-format text "<指摘と修正指示>"` を Bash `run_in_background` で起動し、リダイレクトなしで TaskOutput を確認する(step 6 で保存した chat-id.txt を読む)
- Codex 親 + cursor-agent: `JOB_DIR=<step 6 で記録したパス> && cursor-agent -p --resume "$(cat "$JOB_DIR/chat-id.txt")" --trust --force --model composer-2.5 --workspace "<worktree>" --output-format text "<指摘と修正指示>" > "$JOB_DIR/cursor-agent.log" 2>&1` を shell 経由で実行し、ログ増分で進捗を確認する(step 6 で保存した chat-id.txt を読む)
- Claude 親 + Claude サブエージェント: 指摘と修正指示を添えて新しいサブエージェントに委譲
- Codex 親 + 生存中 worker: `send_input` で指摘と修正指示を渡し、`wait_agent` で回収する
- Codex 親 + close 済み worker: 新しい `spawn_agent` worker に計画、diff、指摘、修正指示を渡す

終了条件: diff が計画と一致し、テストが green で、指摘がゼロ。3 周しても収束しない場合は停止してユーザーに判断を仰ぐ。

各周の修正確認後、親がその修正の write_scope だけを add して節目 commit を行う。

### 9. 統合・後始末・完了報告

終了条件達成後、計画に明記した統合方法だけを「worktree 運用と統合」節の手順で実行する。別の統合方法へ黙って切り替えない。統合完了後に同節の後始末を行い、変更サマリー・テスト結果・計画からの逸脱と採用した仮定・残課題・統合結果・commit 一覧・PR URL・CI 判定結果・merge 結果(`MERGED` 確認)・cleanup 状態を報告する。

### 同席実装の注意

- 秘密情報(`.env` / credentials / `*.pem` 等)を実装指示に含めない
- sandbox の緩和や write_scope 外の変更はユーザー確認の上でのみ行う
- 実装 backend が使えない場合は報告し、承認を得て親実装にフォールバックする。レビュー backend が使えない場合は他の選択肢を再提示する
- cursor-agent はヘッドレスで承認プロンプトを出せないため --force 前提で運用する。sandbox なし(封じ込めなし)で動作するため、実装指示の write_scope 制約と commit 禁止を必ず明記する
- codex exec をバックグラウンド・非対話で起動する場合は stdin を `< /dev/null` で閉じる(閉じないと追加入力待ちで無期限ハングする)
- 非 git repo では worktree・commit・統合をスキップし、従来どおり diff 提示 + 報告で終了する

## 現セッション自律実行 / 起動プロンプト提示パス(step 6-9)

現セッション自律実行または起動プロンプト提示を選んだ場合は、承認済み計画から目的 / write_scope または read_scope / 成功条件 / 検証方法 / 非対象 / 停止条件 3 種 / 外部状態変更可否 / 進捗管理 / 実装戦略 / 統合方法をゴール本文へ転記する。常に、計画にない項目だけの差分確認を選択肢付きで 1 ラウンド行い、未知棚卸し表の「質問する」行がゼロであることを再確認してから組み立てる。計画承認が実行許可の出所であり、承認質問を二重化しない。

commit / push の扱いは承認済み計画の統合方法に従い、統合しないが明示された場合は禁止する。repo ルールが独立レビューを必須とする場合の実装後レビュー要件、どの停止種別でも書き出す完了レポート要件、worktree 運用・節目 commit・統合契約・version bump は転記必須項目とする。

## 排除する失敗モード

1. 停止条件欠落: 全プロンプトに達成停止、上限停止、行き詰まり停止の 3 種を必須化する。上限停止は省略禁止。
2. ゴール誤解釈・スコープドリフト: 成功条件は機械検証(コマンド + exit code)を第一候補にする。検証コマンドがない調査・文書化系は「成果物の存在 + 客観的な手動確認手順(チェックリスト)」へ fallback する。エージェント自己申告のみの成功条件は禁止。見せかけ完了(動いて見えるだけのダミー・モック)の禁止を本文へ明記する。
3. 変更範囲の膨張: 非対象、変更禁止領域、破壊的操作の扱いを本文へ明記する。
4. 無限待機: 「実行中は質問不可。曖昧な点は保守的解釈 + 判断を進捗ログに記録」と本文に焼き込む。
5. 受け渡し失敗: 既定は受け渡し自体を排除し、作成した親がそのまま実行へ移行する。例外形態では本文全文を含むインライン 1 ブロック(4,000 字以内)を既定とし、超過時だけ `.claude/goal-runs/` へのファイル保存 + 参照型へ fallback する。中途半端な要約だけを渡さない。
6. blocker 即停止による不在時間の空転: 停止前の blocker プロトコル(記録 → 代替 2 案 → 最有力で続行。ただし既存制約の内側に限り、権限・外部入力・破壊的操作が絡む blocker は即停止)を本文へ焼き込む。
7. 確認待ち停止: 実行エージェントが「進めてよいか」「OK なら OK と返答してほしい」等の確認・承認求めを出力してターンを終え、不在のユーザーを待ち続ける。ゴール本文冒頭の不在自律実行宣言で確認・承認求めの出力を禁止し、迷ったら保守的解釈 + 判断ログ記録で続行と焼き込む。

## プロンプトテンプレート

生成するゴールプロンプトは次の節をこの順序で持つ。

````markdown
# Goal Prompt: <短い名前>

## 実行モード: 不在自律実行
- このゴールの実行中、ユーザーは不在で、いかなる出力にも応答しない。
- 質問・確認・承認求め(「進めてよいですか」「OK なら OK と返答してください」「この理解で合っていますか」を含む)を出力して停止しない。
- ハーネスが出すツール実行の許可プロンプトへの応答待ちは、ここで禁止する質問・確認には該当しない(許可はユーザーまたはハーネス設定が与える。待機してよい)。
- 途中経過の報告だけを出力してターンを終えない。停止してよいのは停止条件(3 種)のいずれかを満たしたときだけ。
- 判断が必要になったら、制約・非対象の内側で最も保守的な解釈を採用し、判断と理由を進捗ログへ記録して続行する。
- ただし停止条件(3 種)と即停止条件が常に優先する。外部入力が必須、権限が不足、秘密情報が必要、またはゴール本文に具体的な対象と操作が許可として書かれていない破壊的操作・外部状態変更が必要な判断は、質問せず行き詰まり停止する(続行しない)。

## 目的
<何を達成するか。背景は必要最小限>

## 成功条件(検証可能)
- <機械検証できる条件、または成果物 + 客観的な手動確認手順>

## 検証コマンド
```bash
<実行する検証コマンド。ない場合は手動確認手順を書く>
```

## 制約・非対象
- write_scope(実装系では必須。これ以外への変更禁止): <変更を許可するファイルまたはディレクトリ>
- <やらない作業、権限の境界>
- <破壊的操作の扱い>
- ダミー実装・ハードコードの見せかけ結果・動いて見えるだけのモックで成功条件を満たしたことにしない(実装系)。

## 停止条件(3 種)
- 達成停止: <成功条件を満たしたら停止>
- 上限停止: <最大ターン数、最大時間、最大ループ回数など。省略禁止>
- 行き詰まり停止: <同じ blocker が続く、検証不能など>。停止の前に blocker プロトコルを 1 回実行する: blocker と試行内容を進捗ログへ記録 → 代替アプローチを 2 案検討 → 最有力の案で続行を試みる。代替でも解消しない場合に停止する。
- 代替試行は write_scope・非対象・権限・破壊的操作の既存制約の内側の手段に限る。
- 外部入力が必須、権限が不足、秘密情報が必要、またはゴール本文に具体的な対象と操作が許可として書かれていない破壊的操作・外部状態変更が必要な blocker は代替試行せず即停止する。

## 実行戦略(実装系のみ)
- 実装労働の委譲先: <codex exec / Claude サブエージェント / 親実装など>
- 並列方針: <分割可能な場合だけ並列化し、write_scope を互いに素にする>
- モデル / effort: <codex 経路は `-m gpt-5.6-sol` + `model_reasoning_effort="medium"` 固定。spawn_agent など非対応経路は適用なし>
- トークン効率方針: <重い思考は統括のみ、作業は安いレーンへ寄せる>
- worktree 運用と節目 commit: <git repo では作業 worktree を作成し、節目ごとにパス限定 commit。承認済み計画・step 1 回答から転記>
- 統合方法: <既定は PR 経由(提出 + CI green 確認 + merge まで)。gh 不在 / origin なし / origin が非 GitHub ホストの repo は直接統合へ自動フォールバック。GitHub ホストで gh が認証・API 障害等により使えない場合はフォールバックせず停止・報告。統合しない(diff を残して停止)はユーザー明示時のみ。統合しないが明示された場合のみ commit / push を行わない>
- PR 経由の統合契約: <対象 repo の CI 有無とチェック 0 件の扱い、CI なし判定でも PR 作成後の登録猶予内に checks が観測されたら計画より観測を優先して CI ありへ切り替える契約、数分おきの期限管理付きポーリングと CI 待機上限(既定 30 分)、`bucket` 判定(`pass`・`skipping` のみ merge 可)、green 判定時点で束縛した検証済み SHA を `--match-head-commit` に使い merge 直前の head SHA 再確認で不一致なら停止、merge queue / auto-merge 状態を merge 実行前に検出して state 変更コマンドを実行せず停止、remote branch存在確認は `git ls-remote --heads origin refs/heads/<branch>` の成功かつ空結果だけをGitHub側削除済みと扱いAPI・認証・通信エラーや複数結果はcleanup未完了で停止、remote branch 存在時は期待 tip と検証済み SHA の一致確認 + lease 付き削除とし不一致・lease 失敗なら cleanup 未完了として停止、remote branch が GitHub 側で削除済みなら PR の `headRefOid` と検証済み SHA の一致確認後に remote 削除完了扱いでローカルcleanupを続行、`gh pr view` の `MERGED` 確認、CI 赤・merge 失敗時は PR を open のまま停止して完了レポートへ PR URL・失敗チェック・残存状態を記載する契約を焼き込む。PR 経由以外では適用なし>
- 直接統合の統合契約: <主 worktree が clean・`<default>` ブランチ上・origin と diverged していないことを確認し、`merge --ff-only` → push を実行する。push reject は fetch + rebase + 検証再実行 + version 再計算からやり直す。origin なし repo は `merge --ff-only` までで統合完了(push なし)とし完了レポートへ明記する。統合成功後に worktree remove とローカル branch 削除を行う。失敗時は別の統合方法へ切り替えず、diff・worktree・ブランチ・commit を保持して停止する。直接統合以外では適用なし>
- 書くのは戦略と契約のみで、逐一の手順は書かない。
- 戦略から逸脱が必要なら理由を進捗ログに記録して保守的に判断する。

## 進捗管理
- TaskCreate / TaskUpdate が使える場合はステップを登録し、開始時 in_progress、完了時 completed に更新する。
- 進捗ログ: <起動元 checkout 基準で確定した `.claude/goal-runs/` 内の具体的な保存先、更新頻度、判断・blocker・検証結果の書き方>
- 進捗ログ・完了レポートの保存先は起動元 checkout の `.claude/goal-runs/` に固定し、作業 worktree 内に置かない。
- 進捗ログの冒頭に「次にやること / 直近で決めた方針」の節を置き、節目ごとに毎回上書きする。コンテキスト圧縮後は、まず保存済みゴールファイル(<組み立て時に確定した起動元 checkout 基準の具体パス>)を読み直し、次に進捗ログ冒頭の復帰点を読んで復帰する。

## 実装後レビュー
- 実装系では、実装と別系統の独立レビュー(codex review 等)を実施し、指摘ゼロまで修正する。

## 完了レポート
- 完了レポートを書く前に、ゴール本文と進捗ログ全体を読み返し、成功条件の未達・やり残しがないかを確認する。
- 達成停止・上限停止・行き詰まり停止のどの停止種別でも、終了時に起動元 checkout 基準で組み立て時に確定した `.claude/goal-runs/<具体的なレポート名>` の具体パスへ完了レポートを書き出す。作業 worktree の相対パスへ置き換えない。
- 保存済みゴールではゴールファイルの末尾の `-goal` サフィックスを除いた basename に `.md` を付け、未保存の貼り付け実行ではゴールプロンプトの短い名前を英小文字・数字・ハイフンへスラッグ化した `YYYY-MM-DD-<slug>.md` をレポート名にする。step 6 の組み立て時に該当する具体名をこの節へ焼き込み、実行エージェント任せの未定義部分を残さない。
- ゴール本文を連番付きファイル名(`<slug>-N-goal.md`)で保存・自己保存した場合は、この節に焼き込まれた名前ではなく、実際に保存したファイル名の連番を反映した `<slug>-N.md` をレポート名として優先する(実ファイル名が正)。
- 記載項目: 停止種別 / 成功条件ごとの達成状況 / 検証コマンド結果 / commit・統合の実施状況(統合しない明示時は「commit / push なし」) / 逸脱と判断ログ要約 / 残課題 / 変更ファイル一覧。
- `.claude/goal-runs/**` は「制約・非対象」や `write_scope` より優先する運用メタデータ領域として常に書き込みを許可する。read-only 調査ゴールでも完了レポートだけは書き込める。
- 実行エージェントが起動元 checkout 基準の確定済み `.claude/goal-runs/` と `.claude/goal-runs/.gitignore` を作成する。`.gitignore` が無ければ `*` 1 行で新規作成し、既存なら内容を触らない。
- 書き出し後に、git 管理下では起動元 checkout 基準の確定済みパスを `git check-ignore` で検証し、ignore が効いていなければレポート末尾と停止報告へ警告を書く。非 git ディレクトリでは検証不能のため `git check-ignore` を行わず skip する。
- 既定経路では step 8 で本文へ反映した確定済みレポートパスを使う。例外形態の自己保存で起動元 checkout 基準のレポートと同名のファイルがある場合は上書きせず、`<basename>-2.md` からの連番にする。
- 権限不足や read-only 実行環境で書き込み不能な場合は、レポート全文を進捗ログと最終出力へ出し、保存できなかった旨を明記する。

## 実行前提
- 実行中は質問不可。曖昧な点は保守的解釈 + 判断を進捗ログに記録する。
- 確認・承認求め(「OK なら OK と返答してください」型を含む)も不可。冒頭の「実行モード: 不在自律実行」節に従う。
- 秘密情報は本文に含めない。
````

## セルフチェック

step 6 で、提示前に 10 項目を必ず確認する。

1. 検証可能性: 成功条件がコマンド + exit code、または成果物 + 客観的な手動確認手順になっている。
2. 上限停止必須: 達成停止、上限停止、行き詰まり停止の 3 種があり、上限停止は省略禁止になっている。
3. 非対象・破壊的操作明記: 触らない範囲と破壊的操作の可否が明記されている。
4. 実行形態との無矛盾: 現セッション自律実行、現セッション `/goal`、別ターミナル `claude --bg`、`/loop`、`/schedule`、Codex 貼付けの制約と矛盾しない。
5. 秘密情報なし: 値そのものではなく参照方法だけを書いている。
6. 例外形態の受け渡し制約への適合: インライン `/goal` 提示では objective 全文が Unicode 文字数で 4,000 字以内であり、4,001 字以上なら `.claude/goal-runs/` へのファイル保存 + 参照型へ fallback している。Codex 貼付けは字数に関わらず全文 1 ブロックのままである。ファイル形態では参照パスが具体化済みである。既定の自動実行では受け渡しなし(親保存のみ)。
7. 実装系ゴール: `実行戦略(実装系のみ)` と `実装後レビュー` の節があり、逸脱時ログ記録の 1 行が入っている。
8. 完了レポート: 保存先と記載項目と goal-runs 書き込み許可が焼き込まれ、どの停止種別でも書き出す指示になっている。
9. 不在実行 3 点: blocker プロトコル(安全境界付き)、進捗ログ冒頭の復帰点上書き、終了前読み返しがテンプレート本文に入っている。
10. 不在自律実行宣言: テンプレート冒頭に「実行モード: 不在自律実行」節があり、質問・確認・承認求めの禁止と、即停止条件優先の保守的続行 + 判断ログ記録が焼き込まれている。Codex 貼付け形態では起動ヘッダーにも同じ宣言と自己保存指示が入り、未展開のプレースホルダが残っていない。

### 6. 組み立て + セルフチェック

プロンプトテンプレートへ回答を統合し、セルフチェック 10 項目を満たすまで修正する。PR 経由の実装系ゴールでは、対象 repo の CI 有無とチェック 0 件の扱い / CI なし判定でも PR 作成後の登録猶予内に checks が観測されたら計画より観測を優先して CI ありへ切り替える契約 / 数分おきの期限管理付きポーリングと CI 待機上限(既定 30 分) / `bucket` の `pass`・`skipping` のみ merge 可とする判定 / green 判定時点で束縛した検証済み SHA を `--match-head-commit` に使い merge 直前の head SHA 再確認で不一致なら停止 / merge queue・auto-merge 状態を merge 実行前に検出して state 変更コマンドを実行せず停止 / remote branch存在確認は `git ls-remote --heads origin refs/heads/<branch>` の成功かつ空結果だけをGitHub側削除済みと扱いAPI・認証・通信エラーや複数結果はcleanup未完了で停止 / remote branch 存在時は期待 tip と検証済み SHA の一致確認 + lease 付き削除とし不一致・lease 失敗なら cleanup 未完了として停止 / remote branch が GitHub 側で削除済みなら PR の `headRefOid` と検証済み SHA の一致確認後に remote 削除完了扱いでローカルcleanupを続行 / `gh pr view` の `MERGED` 確認で統合完了 / CI 赤・merge 失敗時は PR を open のまま停止して完了レポートへ PR URL・失敗チェック・残存状態を記載、の統合契約を「実行戦略」へ焼き込む。直接統合では、主 worktree の clean・default branch・origin 非 diverged 確認 / `merge --ff-only` → push / push reject 時の fetch + rebase + 検証再実行 + version 再計算 / origin なし repo の push なし完了 / 統合成功後の worktree・ローカル branch cleanup / 失敗時は別の統合方法へ切り替えず差分と作業状態を保持して停止、の直接統合の統合契約を「実行戦略」へ焼き込む。既定経路では、起動元 checkout(非 git ではスキル起動時の cwd)の `.claude/goal-runs/` にある既存ファイルを組み立て時に確認し、衝突しない最終 basename(必要なら連番込み)を先に確定する。その basename からゴールファイル・進捗ログ・完了レポートの 3 パスを基準ディレクトリ内の具体パスへ解決してテンプレート本文へ焼き込む。完了レポート名は、保存済みゴールならゴールファイルの末尾の `-goal` サフィックスを除いた basename、未保存なら短い名前から作る `YYYY-MM-DD-<slug>.md` として具体名をテンプレート本文へ焼き込む。例外形態の現セッション `/goal` では、親が objective 全文(ヘッダー・空行・本文込み、`/goal` プレフィックスを除く)を Unicode 文字数で数え、4,000 字以内ならインライン、4,001 字以上なら fallback と確定する。Codex 貼付けは字数に関わらず常に全文 1 ブロックとし、ファイル fallback へ分岐しない。既定の現セッション自律実行では字数による受け渡し判定を行わない。

### 7. ゴールプロンプト独立レビュー

完成案を独立 reviewer に渡し、成功条件・停止条件・write_scope・権限・実装戦略・レビュー要件の抜け漏れを確認する。指摘があれば step 6 に戻り、指摘ゼロになるまで修正する。

ハーネス別のレビュー手段:

- Claude 親 + codex review(第一候補):
  ```bash
  JOB_DIR=$(mktemp -d "${TMPDIR:-/tmp}/devkit-goal-review.XXXXXX") && echo "JOB_DIR=$JOB_DIR"
  JOB_DIR=<echo された記録済みのパス> && codex -a never exec -C "<対象repo>" --sandbox read-only -m gpt-5.6-sol -c model_reasoning_effort="medium" "<ゴール本文レビュー指示>" < /dev/null > "$JOB_DIR/review.log" 2>&1
  ```
  1 行目で echo されたパスを親が記録し、2 行目に埋め込んでから Bash `run_in_background` で起動する(シェル変数はツール呼び出し間で失われるため)。
  完了通知後に記録済み `JOB_DIR` の `review.log` を必ず読み、指摘ゼロを確認してから step 8 へ進む。指摘があれば step 6 に戻る。
- Claude 親 + codex 不在: Agent(Claude サブエージェント)へ read-only 指示、完成案、レビュー観点を渡して代替する。
- Codex 親: `spawn_agent`(explorer) に read-only 指示・完成案・レビュー観点を渡し、`wait_agent` で回収する。`spawn_agent` が使えない場合は、独立レビューを実施できないため step 8 へ進まない。完成案の全文は提示した上で、保存はせず、Claude 親での /dig-goal 再実行、または `spawn_agent` が使える環境での再実行を案内して停止する(未レビューのままの保存・提示完了扱いはしない)。

### 8. 実行移行(既定) / 例外形態の最終確認

既定では、独立レビュー反映後の完成プロンプト全文を通知として提示し、承認待ちなしで進む。親がゴール本文全文を step 6 で確定した具体パスへ保存し、ディレクトリと `*` 1 行の `.gitignore` を ensure する。git 管理下では `git check-ignore` 検証を行い、非 git では基準ディレクトリをスキル起動時の cwd として検証不能のため `git check-ignore` を行わず skip する。保存時に組み立て後の新たな衝突を検出した場合は、黙って連番保存へ逃げず、衝突しない最終 basename とゴールファイル・進捗ログ・完了レポートの 3 パスを確定し直して本文へ反映してから保存・実行する。ゴールファイルの保存はコンテキスト圧縮後の復帰点であり、保存に失敗した場合は実行を開始せず停止・報告する。保存成功後、「実行モード: 不在自律実行」宣言を自分に適用して直ちに実行を開始する。実行開始の宣言に保存済みゴールファイルの具体パスを明記し、コンテキスト圧縮後はまずそのファイルを読み直してから進捗ログ冒頭の復帰点を読む、という順序を実行契約として自分に課す。ハーネスが出すツール実行の許可プロンプトへの応答待ちは、実行エージェントによる質問・確認には該当せず待機してよい。不在運用を想定する場合は、事前にハーネス側の許可設定を整えることを推奨する。実行直前の全文提示は通知手段であり、安全ゲートは、承認済み計画経由では承認済み計画、直起動の書き込み・破壊的操作・外部状態変更では step 1 の明示回答から転記した操作別の許可と停止条件、commit・統合では goal 本文に記載された統合方法(既定は PR 経由)が担う。

例外形態では、独立レビュー反映後の完成プロンプト全文と起動ブロックを提示して最終確認する。ファイルが必要な形態の場合は保存予定パスも示し、保存してよいか確認する。step 1 で Codex 貼付けを選択した場合は、不在自律実行ヘッダー付きの Codex 貼付け起動文を必ず含める。修正があれば step 6 に戻る。

### 9. 実行と完了報告(既定) / 例外形態の成果物提示

既定では、ゴール本文の契約(停止条件 3 種・blocker プロトコル・進捗ログ復帰点・終了前読み返し)に従い完走する。達成停止・上限停止・行き詰まり停止のどの停止種別でも、起動元 checkout 基準で確定済みの `.claude/goal-runs/<レポート名>` の具体パスへ完了レポートを書き、作業 worktree 内には置かない。停止種別 / 成功条件ごとの達成状況 / 検証コマンド結果 / commit・統合の実施状況(統合しない明示時は「commit / push なし」)を最終報告する。

例外形態では従来どおり、親保存が必要な形態(`/loop`・`/schedule`・別ターミナルの背景起動)または 4,000 字超 fallback だけ、ユーザー確認後に `.claude/goal-runs/` へ Write でゴールファイルを新規保存する。インライン `/goal` と Codex 貼付けでは親はゴールファイルを作らず、実行側の自己保存(best-effort)に委ねる。具体化済み起動プロンプト + 検収チェックリストを 1 ブロックで提示して終了する。step 1 で Codex 貼付けを選択した場合は、不在自律実行ヘッダー付きの Codex 貼付け起動文を必ず含める。

## 起動プロンプトの手引き

既定は現セッション自律実行で、起動プロンプトの受け渡し自体を行わず step 8 で実行へ移行する。以下の表はユーザーが明示したときだけ使う例外形態で、全行とも提示のみとする。4,000 字判定と fallback も例外形態だけに適用する。

| 形態 | 提示する起動プロンプト | 扱い |
|------|------------------------|------|
| 現セッション `/goal`(インライン自己完結型) | `/goal 以下のゴール本文の成功条件を満たす or stop after <N> turns。開始時に本文全文を .claude/goal-runs/<slug>-goal.md へ保存し(ディレクトリと * 1 行の .gitignore が無ければ作成)、コンテキスト圧縮後はまずそれを読み直せ。同名ファイルが既にある場合は上書きせず <slug>-2-goal.md からの連番で保存し、完了レポート名も同じ連番の basename に合わせよ。自己保存に失敗しても停止せず、失敗を進捗ログへ記録して続行せよ。` + 空行 + ゴール本文全文 | 提示のみ。白紙コンテキストで実行したい場合(ユーザーが `/new` した後に貼る)、または後で実行したい場合の受け皿。`/goal` プレフィックスを除いた objective 全文(ヘッダー・空行・本文込み)が Unicode 文字数で 4,000 字以内の場合だけ使う |
| 現セッション `/goal`(4,000 字超 fallback) | `/goal .claude/goal-runs/YYYY-MM-DD-<slug>-goal.md の成功条件を満たす or stop after <N> turns。まず .claude/goal-runs/YYYY-MM-DD-<slug>-goal.md を読め` | 提示のみ。親がゴール本文を保存してから repo 相対パスで参照する |
| 別ターミナル `claude --bg` | `cd "<対象repo>" && claude --bg --permission-mode acceptEdits --allowedTools "..." "/goal <保存したゴールファイルの絶対パス> の成功条件を満たす or stop after <N> turns。まず <保存したゴールファイルの絶対パス> を読め" < /dev/null` | 提示のみ。親が `.claude/goal-runs/<slug>-goal.md` へ保存し、同じマシン・同じ checkout から絶対パスで参照する。実装系では検証コマンドと委譲用 `Bash(codex:*)` を、全タスクで完了レポート書き出し用の `Write` を `--allowedTools` に含めることを推奨する |
| `/loop` | `/loop <interval> .claude/goal-runs/<file>-goal.md を読み、進捗管理の指示に従って条件を確認する` | 提示のみ。セッション依存の巡回向け |
| `/schedule` | `/schedule <trigger> .claude/goal-runs/<file>-goal.md を読む` | 提示のみ。登録はユーザーの 1 アクションで行う |
| Codex 貼付け(App / CLI 対話) | 不在自律実行ヘッダー + ゴール本文全文を 1 ブロックで提示 | 提示のみ。`/goal` と Claude 系のターン上限句は付けない。ヘッダー例: 「以下のゴールプロンプトを不在自律実行せよ。ユーザーは不在で応答しない。質問・確認・承認求めを出力せず、停止条件のいずれかを満たすまで自走せよ。上限停止: <step 1 で確定した具体値>。開始時に本文全文を `.claude/goal-runs/<slug>-goal.md` へ保存し、ディレクトリと `*` 1 行の `.gitignore` が無ければ作成せよ。同名ファイルが既にある場合は上書きせず `<slug>-2-goal.md` からの連番で保存し、完了レポート名も同じ連番の basename に合わせよ。自己保存に失敗しても停止せず、失敗を進捗ログへ記録して続行せよ。」常に本文全文を続け、ファイル参照へ分岐しない |

`.claude/goal-runs/` は gitignore 領域のため別 checkout・別 PC へ伝播しない。ファイル参照型(`/loop`・`/schedule`・別ターミナルの背景起動・fallback)は同じマシン・同じ checkout で実行する前提とする。loop 停止・schedule 解除までゴールファイルを削除しない。

例外形態の起動プロンプトと一緒に、次の回収手順を 1 ブロックで提示する。既定では step 9 の最終報告に統合する。

```text
実行終了後の検収チェックリスト:
1. `.claude/goal-runs/<レポート名>.md` の完了レポートを確認する
2. `git diff` と成功条件を突き合わせる
3. 検証コマンドを再実行する
4. 独立レビューの指摘がゼロであることを確認する
5. commit・統合はゴール本文の統合方法(既定は PR 経由)に従う(統合しないが明示された場合のみ commit / push なし)
6. loop 停止・schedule 解除までゴールファイルを削除しない
```

## 注意

- 裸の `/goal` をトリガーとして扱わない。組み込み `/goal` との誤発火を避ける。
- `/goal` を付けるのは Claude 系の起動プロンプトだけ。委譲先 codex exec には素の実装指示を渡す。
- 非対話のコマンド例を書く場合は、stdin を `< /dev/null` で閉じる。
- codex コマンド例は `-m gpt-5.6-sol` + `model_reasoning_effort="medium"` の固定値で書く。世代追従は catch-up スキルと `premises.json` で管理し、ユーザーが別モデルを明示指定した場合はそれに従う。
- cron 登録・`/schedule` 登録は行わない。実行開始は既定の step 8 実行移行としてのみ行い、commit / push・統合は goal 本文に記載された統合方法(既定は PR 経由)に従う。統合しないが明示された場合のみ commit / push を行わない。
- その場で対話しながら完成させる場合も、判断を前倒しして自律実行する場合も `dig-goal` の対応する実行形態を使う。
