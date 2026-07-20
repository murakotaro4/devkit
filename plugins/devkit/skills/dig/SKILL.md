---
name: "dig"
description: "要求を深掘りし、調査・計画・独立レビュー・worktree 実装から PR 統合まで完遂する主ワークフロー。「深掘りして」「実装して」「相談したい」「/dig」で起動"
argument-hint: "[task]"
---

# /dig - 深掘り + 実装完遂

**dig の既定は実装完遂**。開始時に実行形態を質問しない。

ユーザーが明示した場合だけ、次の例外分岐へ切り替える。

- (a) 「計画だけ」「調査だけ」「相談だけ」「実装しない」等の明示 → read-only で終了する
- (b) 「Goal プロンプトにして」「/goal で動かしたい」「後で実行したい」等の明示 → 「goal-prompt への引き継ぎ」節に従う

## 対象

$ARGUMENTS

## ハーネス判定

正本は devkit リポジトリの `AGENTS.md`「スキル共通契約」。この SKILL.md は Claude 親 / Codex 親の二層構成で実行する。要点:

- `AskUserQuestion` が使える -> Claude 親。
- なければ `spawn_agent` が使える -> Codex 親。
- どちらでもない -> 判定不能として扱い、選択肢を箇条書きで提示して自由文回答を求める。
- `request_user_input` は plan mode 依存で不安定なため、判定キーに使わない(Codex 親 plan mode の質問手段としてのみ使う)。

## タスクリスト連動

正本は devkit リポジトリの `AGENTS.md`「スキル共通契約 > タスクリスト連動」。dig 開始時に step 1-9 をタスクリストへ登録し、各 step の開始時に `in_progress`、完了時に `completed` へ更新する(Claude 親: TaskCreate / TaskUpdate、利用不可なら省略可。Codex 親: 組み込み plan 機能または通常の進捗報告で同等の進捗提示)。

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

深掘り・調査・計画・承認までの step 1-5 は対象 repo に対して read-only とする。例外は 2 つだけ。

1. step 4 / step 7 の独立レビュー用 `mktemp` JOB_DIR 作成とレビューログ書き込み
2. goal-prompt 引き継ぎ時の `.claude/plans/` への計画保存

step 6-9(実装)は承認済み計画の write_scope に従って書き込み・委譲を行う。

実行フェーズのツール面を事前制限しないため、frontmatter には `allowed-tools: ["TaskCreate", "TaskUpdate", "TaskOutput"]` のような許可リストを置かない。作成フェーズでは、実行環境に存在する `AskUserQuestion`、`spawn_agent`、`request_user_input` なども以下の read-only 契約に従って使う。

- 作成・計画フェーズは対象 repo に対して read-only。Bash は `command -v`、`git status`、`rg`、`ls`、`find`、テスト・lint コマンドの存在確認など読み取り用途だけに使う。対象 repo への Bash 書き込み、mkdir、touch、ファイル編集は行わない。
- 秘密情報、資格情報、トークン、個人情報をプロンプト本文へ転記しない。必要な場合は「環境に既に存在する設定を読む」と書き、値そのものは書かない。

## フロー

### 1. 深掘り(棚卸し駆動面談、親)

Claude 親は step 1 開始時に plan mode 外であれば `EnterPlanMode` を呼んで plan mode へ入る。step 1-5 の read-only 契約は plan mode と整合する。

最初のラウンドでタスク型(実装 / 調査 / 状態確認 / 文書化 / 整理)を確定し、未知棚卸しのシードにする。選択肢付き質問を繰り返し、ユーザーの**要求**(目的、成功条件、非対象、優先度、好み)を聞き出す。read-only 終了または goal-prompt 引き継ぎがユーザーから明示された場合は、その旨をタスク型と一緒に記録する。

毎ラウンド冒頭に次の形式の未知棚卸し表を提示し、前ラウンドから更新して差分が見える形にする。

| 未知 | 影響 | 扱い |
|------|------|------|
| <未確定事項> | <成功条件・安全性・設計への影響> | 質問する / 仮定で進める / 確定済み |

- 扱いは「質問する」「仮定で進める」「確定済み」の3値だけを使う。
- 「質問する」行がゼロになったら深掘りを終了し、要件サマリー(目的 / 成功条件 / 非対象 / 採用した仮定)で締める。固定ラウンド数はなく、深さは可変とする。
- 必ず聞く最低ライン: データ構造、既存互換性、外部連携、保存・ログ、権限、テスト合否基準、UI フロー、業務判断、後戻りが大きい設計判断。これらを棚卸しのシードとして維持し、追加観点はカタログ化せず親が対象に応じて推定する。
- 1 ラウンド最大 4 問、必ず選択肢付きで聞く。設計判断を聞く場合は親の推奨を付ける。命名、軽微な文言、内部実装の細部など小さい未知は仮定を明示して進め、採用した仮定を計画へ記載する。
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
- read-only タスクは通常の最終報告で終了し、worktree を作らない

### 3. backend 選択(選択肢付き質問)

計画承認の前に、計画レビュー用 / 実装用 / diff レビュー用の backend のうち適用するものだけを選択肢で確認し、結果を計画に明記する。親はタスク規模に応じた推奨を各問 1 つ付ける。非実装では実装 backend は適用なしとする。この時点で read-only 終了や goal-prompt 引き継ぎへ切り替える場合は step 1 の未知棚卸しを再開し、「質問する」行がゼロになるまで step 3 以降へ進まない。

#### Claude 親の選択肢

codex 経路は Claude 親限定でモデル / effort を固定する: モデルは `gpt-5.6-sol` を `-m` で明示し、effort(`model_reasoning_effort`)は `medium` に固定する。effort の選択質問は行わない。

実装 backend:

| 選択肢 | 実行方法 |
|--------|----------|
| codex — gpt-5.6-sol medium | `codex exec` + `-m gpt-5.6-sol -c model_reasoning_effort="medium"`。標準の実装(既定) |
| cursor-agent — Cursor Grok 4.5 | cursor-agent -p + --model cursor-grok-4.5-high。軽い〜標準実装の高速レーン(Cursor 配信の Grok モデル) |
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
- Claude 親では Codex の実装 backend を提示する前に `command -v uv` も確認する。通らない場合は thread_id 抽出に必要な prerequisite 不足としてユーザーへ報告し、Codex の実装 backend だけを除外する。uv を使わない Codex の計画レビュー / diff レビュー選択肢は残し、黙って別 backend へ fallback しない
- cursor-agent は --model cursor-grok-4.5-high を明示する(auto はサードパーティモデルへルーティングされうるため使わない)。Grok の新版が出たら SKILL.md のモデル名を更新する
- `command -v cursor-agent` が通らない場合は cursor-agent の選択肢を除外する(codex ゲートと同形式。Claude 親・Codex 親の両テーブルに適用)

#### Codex 親の選択肢

`codex exec` 子プロセスの入れ子と `claude` CLI への逆委譲は選択肢に入れない。
Codex 親の `spawn_agent` では子 agent ごとの effort を選択・指定しない。並列数や役割分担は実装戦略として扱い、effort 選択と混同しない。

| 役割 | 選択肢 | 実行方法 |
|------|--------|----------|
| 実装 | `spawn_agent` worker | 実装指示 1 ブロック(write_scope / 受け入れ条件 / 検証 / commit 禁止)を渡し、`wait_agent` で回収する。修正ループで `send_input` を使うため `close_agent` は指摘解消まで遅延する |
| 実装 | cursor-agent (Cursor Grok 4.5) | shell で cursor-agent -p を起動し、実装指示 1 ブロックを渡す。spawn_agent 系統とは独立した shell 実行系統。修正ループは --resume <chatId>(実行方法は step 6/8 の Claude 親 + cursor-agent と同じコマンド形) |
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

計画レビューを経た(skip 選択時は未実施の)、backend と、適用可能な場合だけモデル / effort が明記された計画で承認を得る。モデル / effort 非対応の経路は「適用なし」と記す。codex のモデル / effort 欄は `gpt-5.6-sol` / `medium` 固定と記す。実装系では計画レビュー / 実装 / diff レビューの 3 役を明記する。承認なしで実装に進まない。`ExitPlanMode` による承認前は step 6(実装)へ進まない。

ハーネス別の承認手段:

- Claude 親: step 1 で入った plan mode から `ExitPlanMode` で承認を得ることに一本化する。
- Claude 親で `EnterPlanMode` が利用できないハーネスの縮退経路に限り、通常 mode で計画全文を提示して明示承認を得る。
- Codex 親 plan mode: 計画全文を提示し、`request_user_input` で承認確認する。
- Codex 親通常 mode / 判定不能: 計画全文を提示し、自由文で明示承認を得る。

`ExitPlanMode` 承認後は plan mode を抜け、以後は承認済み計画の write_scope に従う書き込み契約を適用する。

## goal-prompt への引き継ぎ(ユーザー明示時のみ)

- ユーザーが「Goal プロンプトにして」「/goal で動かしたい」「後で実行したい」等を明示した場合だけ、dig は実装せず、レビュー済み計画の全文を `.claude/plans/YYYY-MM-DD-<slug>.md` へ保存して終了する(ディレクトリがなければ作成する)。
- 保存後、`/goal-prompt` の起動を案内する(goal-prompt がこの計画を読んで Goal プロンプトを生成・保存し、起動プロンプトを出力する)。
- Goal プロンプト自体の独立レビューや追加承認は行わない。レビュー済み計画が正本であり、goal-prompt は意味を変えずに実行形式へ変換するだけ。
- dig 自身は組み込み `/goal` を自動発動しない。

## worktree 運用と統合

この節は実装タスク(diff を作る)に適用する。非 git repo と read-only タスクは対象外。

### 作成

計画承認後・実装委譲前に親が実行する。

1. `git symbolic-ref --short refs/remotes/origin/HEAD` の結果から `origin/` プレフィックスを取り除いた名前を `<default>` とする。取得できなければ `main`、`main` も無ければ現在のブランチを基点にする。
2. `git -C "<repo>" fetch origin` を実行する(origin が無ければ省略)。fetch 失敗は警告を報告して続行し、統合前に再試行する。
3. `WT_DIR=$(mktemp -d "${TMPDIR:-/tmp}/devkit-dig-wt.XXXXXX") && echo "WT_DIR=$WT_DIR"` を実行し、親が echo されたパスを記録する。
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
  3. 完了自動通知後、記録済みパスを使い `JOB_DIR=<echo された記録済みのパス> && uv run --no-project --python ">=3.10" python -c 'import json,sys; ids=[event.get("thread_id") for line in open(sys.argv[1], encoding="utf-8") if line.strip() for event in [json.loads(line)] if event.get("type") == "thread.started"]; (len(ids) == 1 and isinstance(ids[0], str) and ids[0]) or sys.exit("expected exactly one non-empty thread.started thread_id"); print(ids[0])' "$JOB_DIR/codex-events.jsonl" > "$JOB_DIR/thread-id.txt" && test -s "$JOB_DIR/thread-id.txt"` を実行する。全 event を保持せず `thread.started` の ID だけを収集し、厳密に 1 件で thread_id が非空の場合だけ保存する。失敗時は resume せず委譲失敗として報告する。
- Claude 親 + cursor-agent: `JOB_DIR=$(mktemp -d "${TMPDIR:-/tmp}/devkit-dig-job.XXXXXX") && CHAT_ID="$(cursor-agent create-chat | tr -d '\r\n')" && test -n "$CHAT_ID" && printf '%s\n' "$CHAT_ID" > "$JOB_DIR/chat-id.txt" && echo "JOB_DIR=$JOB_DIR"` で chatId を保存してから `JOB_DIR=<echo された記録済みのパス> && cursor-agent -p --resume "$(cat "$JOB_DIR/chat-id.txt")" --trust --force --model cursor-grok-4.5-high --workspace "<worktree>" --output-format text "<実装指示>"` を Bash `run_in_background` で起動し、完了自動通知で回収する(echo された JOB_DIR のパスを親が記録し、step 8 の修正ループでは記録済みのパスを使う。シェル変数はツール呼び出し間で失われるため。test -n 失敗 = create-chat 失敗として委譲を中止し親が報告する。Claude 親では出力を TaskOutput で確認するためログリダイレクトは付けない)
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
- Claude 親 + cursor-agent: `JOB_DIR=<step 6 で記録したパス> && cursor-agent -p --resume "$(cat "$JOB_DIR/chat-id.txt")" --trust --force --model cursor-grok-4.5-high --workspace "<worktree>" --output-format text "<指摘と修正指示>"` を Bash `run_in_background` で起動し、リダイレクトなしで TaskOutput を確認する(step 6 で保存した chat-id.txt を読む)
- Codex 親 + cursor-agent: `JOB_DIR=<step 6 で記録したパス> && cursor-agent -p --resume "$(cat "$JOB_DIR/chat-id.txt")" --trust --force --model cursor-grok-4.5-high --workspace "<worktree>" --output-format text "<指摘と修正指示>" > "$JOB_DIR/cursor-agent.log" 2>&1` を shell 経由で実行し、ログ増分で進捗を確認する(step 6 で保存した chat-id.txt を読む)
- Claude 親 + Claude サブエージェント: 指摘と修正指示を添えて新しいサブエージェントに委譲
- Codex 親 + 生存中 worker: `send_input` で指摘と修正指示を渡し、`wait_agent` で回収する
- Codex 親 + close 済み worker: 新しい `spawn_agent` worker に計画、diff、指摘、修正指示を渡す

終了条件: diff が計画と一致し、テストが green で、指摘がゼロ。3 周しても収束しない場合は停止してユーザーに判断を仰ぐ。

各周の修正確認後、親がその修正の write_scope だけを add して節目 commit を行う。

### 9. 統合・後始末・完了報告

終了条件達成後、計画に明記した統合方法だけを「worktree 運用と統合」節の手順で実行する。別の統合方法へ黙って切り替えない。統合完了後に同節の後始末を行い、変更サマリー・テスト結果・計画からの逸脱と採用した仮定・残課題・統合結果・commit 一覧・PR URL・CI 判定結果・merge 結果(`MERGED` 確認)・cleanup 状態を報告する。

## 実装の注意

- 秘密情報(`.env` / credentials / `*.pem` 等)を実装指示に含めない
- sandbox の緩和や write_scope 外の変更はユーザー確認の上でのみ行う
- 実装 backend が使えない場合は報告し、承認を得て親実装にフォールバックする。レビュー backend が使えない場合は他の選択肢を再提示する
- cursor-agent はヘッドレスで承認プロンプトを出せないため --force 前提で運用する。sandbox なし(封じ込めなし)で動作するため、実装指示の write_scope 制約と commit 禁止を必ず明記する
- codex exec をバックグラウンド・非対話で起動する場合は stdin を `< /dev/null` で閉じる(閉じないと追加入力待ちで無期限ハングする)
- 非 git repo では worktree・commit・統合をスキップし、従来どおり diff 提示 + 報告で終了する
- codex コマンド例は `-m gpt-5.6-sol` + `model_reasoning_effort="medium"` の固定値で書く。世代追従は catch-up スキルと `premises.json` で管理し、ユーザーが別モデルを明示指定した場合はそれに従う
