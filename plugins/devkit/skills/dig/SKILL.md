---
name: "dig"
description: "要求の深掘りと実装オーケストレーション。親エージェントが深掘りインタビュー・調査・計画・統括を担当し、計画レビュー・実装・diff レビューは選択した backend に委譲する。「深掘りして」「/dig」「実装して」「Codexに実装させて」で起動"
argument-hint: "[task]"
allowed-tools: ["AskUserQuestion", "ExitPlanMode", "Bash", "Read", "Grep", "Glob", "Agent", "request_user_input", "spawn_agent", "wait_agent", "send_input", "close_agent", "TaskCreate", "TaskUpdate", "TaskOutput", "Skill"]
---

# /dig - 深掘り + 実装委譲オーケストレーション

親エージェント = 深掘り・調査・計画・統括・報告。計画レビュー / 実装 / diff レビューは step 3 で選択した backend に委譲する(実装 backend は commit 禁止)。commit は親が作業ブランチへ節目ごとにパス限定で行い、統合(merge + push、または PR 提出)まで dig が完遂する。

## タスク

$ARGUMENTS

## dig / goal-prompt 使い分け

配布先には devkit リポジトリの `AGENTS.md` が同梱されないため、この SKILL.md も使い分けの要点を保持する。軸はタスク規模ではなく自律度。

- `dig` はその場で完成させる工程。成果物は実装済み diff。ユーザーが同席し、判断をリアルタイムに供給する。
- `goal-prompt` は不在実行に耐える指示書を作る工程。成果物はレビュー済みゴールファイル + 起動プロンプト。実行はユーザーの 1 アクションに分離する。
- 実装系で計画がまだ無い場合の正道は `dig` で調査・write_scope・受け入れ条件を確定し、必要なら「ゴール化して自律実行」で `goal-prompt` へ引き継ぐ。
- ゴール化を選んだ dig は、goal-prompt が作るゴールファイル + 起動プロンプトを提示して終了する。実装後レビューはゴール本文の要件として焼き込む。

## ハーネス判定

正本は devkit リポジトリの `AGENTS.md`「スキル共通契約」。フロー開始前に、利用可能なツール名で親ハーネスを判定する。要点:

- `AskUserQuestion` が使える → Claude 親。
- なければ `spawn_agent` が使える → Codex 親。
- どちらでもない → 判定不能。Claude 親の手順を基本にし、選択肢付き質問は自由文の箇条書きで代替する。
- `request_user_input` は plan mode 依存で不安定なため、判定キーに使わない(Codex 親 plan mode の質問手段としてのみ使う)。

## タスクリスト連動

正本は devkit リポジトリの `AGENTS.md`「スキル共通契約 > タスクリスト連動」。dig 開始時に step 1-9 をタスクリストへ登録し、各 step の開始時に `in_progress`、完了時に `completed` へ更新する(Claude 親: TaskCreate / TaskUpdate、利用不可なら省略可。Codex 親: 組み込み plan 機能で同等の進捗提示)。

## worktree 運用と統合

この節は実装系 dig(diff を作る)だけに適用する。非 git repo、実装 backend が「ゴール化して自律実行」の場合、調査のみの dig は対象外。

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

1. `git fetch origin` を再試行し、`origin/<default>` が進んでいれば worktree 内で rebase して検証を再実行する。rebase conflict は `git rebase --abort` して停止・報告する。
2. その後、repo の release 規則が version bump 等の単調増加値を要求する場合、origin の現行値から再計算して更新し、親がパス限定で commit する。
3. 直接統合(既定): 主 worktree(repo 本体)で行う。主 worktree が clean・`<default>` ブランチ上・origin と diverged していないことを確認する。behind は ff で取り込み、dirty / diverged / 別ブランチなら停止・報告する。その後 `git -C "<repo>" merge --ff-only <branch>`(rebase 直後のため常に ff 可能)→ `git -C "<repo>" push origin <default>` を実行する。push reject は fetch して手順 1 からやり直し、version の再計算もやり直す。hook 失敗は停止・報告する。
4. PR 経路: `git -C "<worktree>" push -u origin <branch>` → `gh pr create` → CI 確認まで行う。merge は人間が行い、dig は `gh pr merge` しない。remote ブランチが正となるため、ローカル worktree とローカルブランチは削除してよい。PR URL と CI 状態を報告する。
5. 後始末: 統合完了(直接統合の push 成功、または PR 提出完了)後に `git worktree remove` とローカル作業ブランチ削除を行う。直接統合では統合済み確認後に `git branch -d <branch>` を使う。worktree remove が未追跡ファイル等で拒否された場合は `--force` せず、パスを報告する。

origin なし repo では fetch / push / PR 経路を省略する。直接統合は主 worktree での `merge --ff-only` までで統合完了と扱い(push なし)、報告にその旨を明記する。

### 失敗時の共通契約

変更を破棄しない。どの失敗でも worktree・ブランチ・commit をそのまま残し、ブランチ名 / worktree パス / 止まった操作 / 再開コマンドを報告して停止する。

## フロー

### 1. 深掘りインタビュー(親)

選択肢付き質問を繰り返し、ユーザーの**要求**(目的、成功条件、非対象、優先度、好み)を聞き出す。深掘りは未知の棚卸しとして行う: 仕様上未確定と分かっている点(known unknowns)を列挙し、既存コード・業務制約・権限・保存先・性能・例外処理の観点から見落としやすいリスク(unknown unknowns)を推定する。影響が大きい未知だけを質問し、小さい未知は仮定を明示して進める。

- 必ず聞く: データ構造、既存互換性、外部連携、保存・ログ、権限、テスト合否基準、UI フロー、業務判断、後戻りが大きい設計判断
- 仮定して進める: 命名、軽微な文言、内部実装の細部。採用した仮定は計画に明示する
- 1 ラウンド最大 4 問、必ず選択肢付きで聞く。設計判断を聞く場合は親の推奨を付ける
- 固定ラウンド数はない。「必ず聞く」に該当する未知が残らなくなるまで深掘りする
- 締めに要件サマリー(目的 / 成功条件 / 非対象 / 採用した仮定)を提示して認識を合わせる

ハーネス別の質問手段:

- Claude 親: AskUserQuestion を使う。
- Codex 親 plan mode: `request_user_input` を使う。
- Codex 親通常 mode: `/plan` での再実行を 1 回だけ案内した上で、選択肢を箇条書き提示して自由文回答を求める。
- 判定不能: 選択肢を箇条書き提示して自由文回答を求める。

### 2. 調査 + 計画(親)

コードベースを調査し、decision-complete な計画を作る。計画に必ず含める:

- write_scope: 変更するファイルの一覧
- 各ファイルの具体的な変更内容
- 検証コマンド(テスト・リンタ)
- 非対象(やらないこと)
- 作業ブランチ名(`<type>/<slug>`) / 統合方法(直接統合 or PR 提出) / 最終 commit メッセージ案
- 計画レビュー / 実装 / diff レビューそれぞれの backend。モデル / effort は選択した backend で適用可能な場合だけ追記し、非対応経路は「適用なし」と記す(step 3 の選択後、承認前に確定させる。codex は `gpt-5.6-sol` / `medium` 固定と記す)

### 3. backend 選択(選択肢付き質問)

計画承認の前に、計画レビュー用 / 実装用 / diff レビュー用の backend を選択肢で確認し、結果を計画に明記する。親はタスク規模に応じた推奨を各問 1 つ付ける。ただし実装 backend で「ゴール化して自律実行」を選ぶ場合は、diff レビュー backend の質問を出さない。実装後レビューは goal-prompt が作るゴール本文の要件が担う。

実装系 dig では統合方法も 1 問で確認する。既定推奨は「直接統合」、もう一方は「PR 提出」。`command -v gh` が通らない場合、または origin なし repo では PR 選択肢を出さない。実装 backend が「ゴール化して自律実行」の場合と非 git repo では、この質問を出さない。

#### Claude 親の選択肢

codex 経路は Claude 親限定でモデル / effort を固定する: モデルは `gpt-5.6-sol` を `-m` で明示し、effort(`model_reasoning_effort`)は `medium` に固定する。effort の選択質問は行わない。

実装 backend:

| 選択肢 | 実行方法 |
|--------|----------|
| codex — gpt-5.6-sol medium | `codex exec` + `-m gpt-5.6-sol -c model_reasoning_effort="medium"`。標準の実装(既定) |
| cursor-agent — Composer 2.5 | cursor-agent -p + --model composer-2.5。軽い〜標準実装の高速レーン(Cursor 自社モデルプール) |
| Claude サブエージェント — Sonnet | Agent(general-purpose, model=sonnet)。世代非依存 alias で常に最新 Sonnet |
| ゴール化して自律実行 | 承認済み計画を `goal-prompt` へ引き継ぎ、step 6 の「ゴール化引き継ぎ」でレビュー済みゴールファイル + 起動プロンプトに変換する。dig は起動プロンプト提示で終了し、実装済み diff は作らない |

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
| 実装 | ゴール化して自律実行 | 承認済み計画を `goal-prompt` の契約に従って親がそのまま続行し、レビュー済みゴールファイル + 起動プロンプトに変換する。dig は起動プロンプト提示で終了し、実装済み diff は作らない |
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

計画レビューを経た(skip 選択時は未実施の)、backend と、適用可能な場合だけモデル / effort が明記された計画で承認を得る。モデル / effort 非対応の経路は「適用なし」と記す。codex のモデル / effort 欄は `gpt-5.6-sol` / `medium` 固定と記す。通常実装では計画レビュー / 実装 / diff レビューの 3 役を明記する。実装 backend が「ゴール化して自律実行」の場合は diff レビュー backend を明記せず、goal-prompt のゴール本文に実装後レビュー要件を焼き込む旨を計画へ明記する。承認なしで実装に進まない。

ハーネス別の承認手段:

- Claude 親 plan mode: ExitPlanMode で承認を得る。
- Claude 親通常 mode: 計画を提示して明示承認を得る。
- Codex 親 plan mode: 計画全文を提示し、`request_user_input` で承認確認する。
- Codex 親通常 mode / 判定不能: 計画全文を提示し、自由文で明示承認を得る。

### 6. 実装委譲(backend)

計画を実装指示 1 ブロックに変換して委譲する。指示ブロックに必ず含める:
目的 / write_scope(これ以外のファイルに触らない) / 具体的な変更内容 / 受け入れ条件 / 検証コマンド / commit 禁止。

実装 backend で「ゴール化して自律実行」を選んだ場合は、通常の実装委譲の代わりにゴール化引き継ぎを実行する。承認済み計画から目的 / write_scope / 受け入れ条件 / 検証コマンド / 非対象を抜き出し、commit / push 禁止と実装後の独立レビュー要件を必ずゴールプロンプト本文へ焼き込む。

ゴール化引き継ぎ:

- Claude 親: `Skill(skill: "devkit:goal-prompt", args: "<dig からの計画引き継ぎである旨 + 目的 / write_scope / 受け入れ条件 / 検証コマンド / 非対象 / commit・push 禁止 / 実装後の独立レビュー要件>")` で起動する。
- Codex 親: `goal-prompt` スキルの契約に従い、親がそのままゴールプロンプト組み立てへ続行する。
- `goal-prompt` はレビュー済みゴールファイル + 起動プロンプトを作成し、提示したところで終了する。dig もそこで終了し、step 7-9 は実行しない。
- ゴールプロンプト本文の成功条件に「repo ルールが独立レビューを必須とする場合は、実装と別系統の独立レビュー(codex review 等)を実施し指摘ゼロであること」を焼き込む。これは commit / push 禁止と合わせて転記必須項目とする。
- ゴール化は実行中に質問へ答えられない前提のため、停止条件・上限・非対象が確定していない場合は step 1 に戻って深掘りする。

ハーネス別の実行方法:

- Claude 親 + codex:
  1. `JOB_DIR=$(mktemp -d "${TMPDIR:-/tmp}/devkit-codex-job.XXXXXX") && echo "JOB_DIR=$JOB_DIR"` でジョブ専用領域を作り、echo された JOB_DIR を親が記録する。
  2. `JOB_DIR=<echo された記録済みのパス> && set -o pipefail && codex -a never exec -C "<worktree>" --sandbox workspace-write -m gpt-5.6-sol -c model_reasoning_effort="medium" --json "<実装指示>" < /dev/null | tee "$JOB_DIR/codex-events.jsonl"` を Bash `run_in_background` で起動する。`tee` により JSONL stdout を TaskOutput へ可視化しながらジョブ専用 event log に保存し、`pipefail` で codex / tee いずれの失敗も検出する。
  3. 完了自動通知後、記録済みパスを使い `JOB_DIR=<echo された記録済みのパス> && python3 -c 'import json,sys; ids=[event.get("thread_id") for line in open(sys.argv[1], encoding="utf-8") if line.strip() for event in [json.loads(line)] if event.get("type") == "thread.started"]; (len(ids) == 1 and isinstance(ids[0], str) and ids[0]) or sys.exit("expected exactly one non-empty thread.started thread_id"); print(ids[0])' "$JOB_DIR/codex-events.jsonl" > "$JOB_DIR/thread-id.txt" && test -s "$JOB_DIR/thread-id.txt"` を実行する。全 event を保持せず `thread.started` の ID だけを収集し、厳密に 1 件で thread_id が非空の場合だけ保存する。失敗時は resume せず委譲失敗として報告する。
- Claude 親 + cursor-agent: `JOB_DIR=$(mktemp -d "${TMPDIR:-/tmp}/devkit-dig-job.XXXXXX") && CHAT_ID="$(cursor-agent create-chat | tr -d '\r\n')" && test -n "$CHAT_ID" && printf '%s\n' "$CHAT_ID" > "$JOB_DIR/chat-id.txt" && echo "JOB_DIR=$JOB_DIR"` で chatId を保存してから `JOB_DIR=<echo された記録済みのパス> && cursor-agent -p --resume "$(cat "$JOB_DIR/chat-id.txt")" --trust --force --model composer-2.5 --workspace "<worktree>" --output-format text "<実装指示>"` を Bash `run_in_background` で起動し、完了自動通知で回収する(echo された JOB_DIR のパスを親が記録し、step 8 の修正ループでは記録済みのパスを使う。シェル変数はツール呼び出し間で失われるため。test -n 失敗 = create-chat 失敗として委譲を中止し親が報告する。Claude 親では出力を TaskOutput で確認するためログリダイレクトは付けない)
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

委譲中の進捗可視化(必須):

正本は devkit リポジトリの `AGENTS.md`「スキル共通契約 > 委譲・長時間ジョブの進捗可視化」。要点:

- 委譲ジョブは 1 ジョブ = 1 タスクとしてタスクリストへ登録し、開始・完了で状態を更新する(親 step のタスクに blockedBy で紐付け、親子関係を表現する)
- Claude 親の外部 CLI 委譲は所要見込みによらず Bash `run_in_background` で起動する。完了待ちは自動通知駆動とし、ハートビートの逐次表示は行わない。待機中は数分おき(目安 2〜5 分)に TaskOutput で出力増分を確認し、増分ゼロが続く場合のみ停滞の継続時間と推定原因(内部レビュー待ち / 長考 / ハング)をユーザーへ報告する。Codex 親: `wait_agent` で黙って待たず、進捗を定期的にユーザーへ提示する(cursor-agent はログ増分で確認)
- 実体の進捗は `git status` / `git diff` で確認する(resume を進捗確認に使わない)
- 調査のみの委譲は read-only で行う。

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

終了条件達成後、計画に明記した統合方法だけを「worktree 運用と統合」節の手順で実行する。別の統合方法へ黙って切り替えない。統合完了後に同節の後始末を行い、変更サマリー・テスト結果・計画からの逸脱と採用した仮定・残課題・統合結果・commit 一覧・CI / PR 状態を報告する。

## 注意

- 秘密情報(`.env` / credentials / `*.pem` 等)を実装指示に含めない
- sandbox の緩和や write_scope 外の変更はユーザー確認の上でのみ行う
- 実装 backend が使えない場合は報告し、承認を得て親実装にフォールバックする。レビュー backend が使えない場合は他の選択肢を再提示する
- cursor-agent はヘッドレスで承認プロンプトを出せないため --force 前提で運用する。sandbox なし(封じ込めなし)で動作するため、実装指示の write_scope 制約と commit 禁止を必ず明記する
- codex exec をバックグラウンド・非対話で起動する場合は stdin を `< /dev/null` で閉じる(閉じないと追加入力待ちで無期限ハングする)
- 非 git repo では worktree・commit・統合をスキップし、従来どおり diff 提示 + 報告で終了する
