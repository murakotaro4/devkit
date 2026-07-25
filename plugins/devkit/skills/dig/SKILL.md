---
name: "dig"
description: "要求を深掘りし、調査・計画・独立レビュー・worktree 実装から PR 統合まで完遂する主ワークフロー。「深掘りして」「実装して」「相談したい」「/dig」で起動"
argument-hint: "[task]"
---

# /dig - 深掘り + 実装完遂

**dig の既定は実装完遂**。開始時に実行形態を質問しない。ユーザーが明示した場合だけ次へ分岐する。

- 「計画だけ」「調査だけ」「相談だけ」「実装しない」等: read-only で終了
- 「Goal プロンプトにして」「/goal で動かしたい」「後で実行したい」等: 「goal-prompt への引き継ぎ」へ

## 対象

$ARGUMENTS

## ハーネス判定と実行差分

| 条件 | 親 | 質問 / 承認 |
|------|----|-------------|
| `AskUserQuestion` が使える | Claude 親 | 質問は AskUserQuestion。step 1 で `EnterPlanMode`、承認は `ExitPlanMode`。利用不能時だけ計画全文への明示承認 |
| AskUserQuestion がなく `spawn_agent` が使える | Codex 親 | plan mode は `request_user_input`、通常 mode は選択肢を提示して自由文回答 / 明示承認 |
| どちらもない | 判定不能 | 選択肢を提示して自由文回答 / 明示承認 |

`request_user_input` はハーネス判定に使わない。step 1-5 は read-only のため plan mode と整合する。承認前に step 6 へ進まない。

工程ごとの委譲差分は次の表を正本とし、各 step では再掲しない。

| 工程 | Claude 親 + codex | Claude 親 + Claude agent | Codex 親 | cursor-agent |
|------|--------------------|--------------------------|------------|--------------|
| 調査 | 適用なし | read-only の Agent | `spawn_agent` explorer | 適用なし |
| 計画レビュー | read-only sandbox の非対話実行 | 計画全文を Agent へ | `spawn_agent` explorer | 適用なし |
| 実装 | worktree-write の非対話実行 | 実装指示を Agent へ | `spawn_agent` worker | shell で worktree を指定 |
| diff レビュー | `review --base` | diff と計画を Agent へ | `spawn_agent` explorer | 適用なし |
| 修正 | 同じ thread_id で resume | 新しい Agent | 生存中 worker へ `send_input`、close 済みなら新規 worker | 同じ chatId で resume |

Claude 親の CLI 委譲は `run_in_background` と完了通知で回収する。Codex 親は `wait_agent` で黙って待たず進捗を提示し、指摘解消まで `close_agent` を遅らせる。実体の進捗は `git status` / `git diff` とジョブログで確認し、resume は進捗確認に使わない。

## 共通契約

### タスクと進捗

- step 1-9 と各委譲・長時間ジョブをタスクリストへ登録し、開始 / 完了状態を更新する。Codex 親は plan または進捗報告で同等に示す。
- 1 ジョブ = 1 タスク。Claude 親は通知駆動で回収し、出力増分が数分止まった場合だけ停滞時間と推定原因を報告する。Codex 親は定期的に進捗を示す。

### Codex モデル / effort

- Codex のモデルは `gpt-5.6-sol` を `-m` で明示し、`model_reasoning_effort="medium"` に固定する。ユーザーが別モデルを明示した場合だけ従う。世代追従は catch-up と `premises.json` で管理する。
- Max は対応 surface の最深推論、Ultra は並列オーケストレーションの説明にだけ使う。並列化はモデルと独立に、依存関係と write_scope で判断する。
- Codex 親の `spawn_agent` では子ごとの effort を選ばない。

非対話実行の基本形:

```bash
codex -a never exec -m gpt-5.6-sol -c model_reasoning_effort="medium" "<内容>" < /dev/null
```

### 書き込み契約

step 1-5 は対象 repo に対して read-only、step 6-9 は承認済み write_scope 内だけを書き込む。前半の例外は次の 2 つだけ。

1. step 4 / 7 の独立レビュー用 `mktemp` JOB_DIR とログ
2. goal-prompt 引き継ぎ時の `.claude/plans/` への計画保存

frontmatter に `allowed-tools` を置かず、利用可能なツールもこの境界に従う。秘密情報・資格情報・個人情報はプロンプトへ転記しない。

## フロー

### 1. 深掘り(棚卸し駆動面談、親)

タスク型と要求（目的、成功条件、非対象、優先度、好み）を確定する。毎ラウンド、更新した表を提示する。

| 未知 | 影響 | 扱い |
|------|------|------|
| <未確定事項> | <成功条件・安全性・設計への影響> | 質問する / 仮定で進める / 確定済み |

- 扱いは表の 3 値だけ。「質問する」行がゼロで終了し、目的 / 成功条件 / 非対象 / 採用した仮定をまとめる。
- 成功条件や後戻りの大きさに効く未知を質問し、小さい未知は仮定で進める。1 ラウンド最大 4 問、選択肢と推奨を付ける。
- 統合方法は質問せず、step 2 の調査で確定する。

### 2. 調査 + 計画(親)

対象を read-only で調べ、decision-complete な計画を作る。調査は read-only agent へ並列委譲できるが、計画は親が統合する。

計画は「## 承認用サマリー」「## 詳細」の 2 層にする。第 1 層だけで承認判断できるよう次の 7 カテゴリを欠かさない。

1. 何を / なぜ
2. 判断してほしい点（推奨付き、最大 3 件程度。なければ「なし」）
3. 既定からの逸脱・採用した仮定（なければ「既定どおり」）
4. 後戻りしにくい操作・外部影響
5. 計画レビュー / 実装 / diff レビューの backend（不能なら「適用なし」）
6. green とする検証
7. 独立レビュー状態（`実施済み(指摘 N 件反映)` / `skip(理由)` / `適用なし`）

カテゴリ 5-7 は次の工程表へ統合し、承認の現在地を強調する。

| 工程 | 状態 | backend |
|------|------|---------|
| 調査 | ✓ | 親 / agent |
| 計画 | ✓ | 親 |
| 計画レビュー | 実施済み(指摘 0 件反映) | 選択 backend |
| **承認** | **← 今ここ** | ユーザー |
| 実装 | — | 選択 backend |
| diff レビュー | — | 選択 backend |
| 検証 | — | green 条件 |
| 統合 | — | 計画した方法 |

散文部（カテゴリ 1-4）は約 1,000 字を目標とし、表は行数で管理する。約 1,000 字は hard limit ではない。第 2 層へ送るのは根拠・経緯・選択肢の詳細・手順だけとし、字数と完全性が衝突したら完全性を優先する。

詳細には次を含める。

| タスク | 必須項目 |
|--------|----------|
| 実装 | write_scope、ファイル別変更、検証、非対象、ブランチ、統合方法、commit 案、3 backend |
| 非実装 | read_scope、成功条件と検証、非対象と外部状態変更、実行形態。branch / commit / 統合 / 実装 backend は適用なし |

統合は PR 提出 + CI green 確認 + merge が既定。origin なし、非 GitHub origin、または `gh` 不在なら計画時に直接統合へ決める。GitHub origin で API・認証・通信が失敗した場合は直接統合へ切り替えず停止する。PR 計画では repo 内 CI と GitHub 側設定を調べ、チェック 0 件の扱いと待機上限（既定 30 分）を明記する。

### 3. backend 選択

承認前に適用する計画レビュー / 実装 / diff レビュー backend を選び、推奨を付ける。read-only への変更または goal-prompt 引き継ぎへの変更で要件が動いたら step 1 に戻り、「質問する」行をゼロにする。

| 親 | 役割 | 選択肢 |
|----|------|--------|
| Claude | 実装 | codex（既定） / cursor-agent / Claude サブエージェント `Agent(general-purpose, model=sonnet)` |
| Claude | 計画・diff レビュー | codex review（既定） / Claude サブエージェント `Agent(general-purpose, model=opus)` / skip（repo が独立レビュー必須なら不可） |
| Codex | 実装 | `spawn_agent` worker / cursor-agent / 親実装 |
| Codex | 計画・diff レビュー | `spawn_agent` explorer / skip（repo が独立レビュー必須なら不可） |

Codex 親では `codex exec` の入れ子と `claude` CLI への逆委譲を選ばない。`command -v codex` / `command -v cursor-agent` が失敗した選択肢は除く。Claude 親の codex 実装は `command -v uv` も必須で、不足時は thread_id 抽出不能として実装選択肢だけを除く。cursor-agent は `cursor-grok-4.5-high` を明示する。利用不能な backend から別 backend へ黙って fallback しない。

### 4. 計画レビュー

選択 backend に計画全文を渡し、decision-complete 性・矛盾・見落としを審査する。指摘を反映してから承認へ進む。skip 選択時だけ省略する。

codex の例:

```bash
codex -a never exec --sandbox read-only -m gpt-5.6-sol -c model_reasoning_effort="medium" "<計画レビュー指示>" < /dev/null
```

### 5. 計画承認

レビュー済み計画（skip 時はその状態を明記）を第 1 層から提示し、明示承認を得る。工程表に計画レビュー / 実装 / diff レビューと、適用可能なモデル / effort を記す。承認後だけ plan mode を抜け、承認済み write_scope を有効にする。

### 6. worktree 作成と実装委譲

実装系は必ず worktree を使う。親が既定 branch を origin/HEAD、main、現在 branch の順で決める。origin があれば fetch し、無ければ fetch を省略して基点を `HEAD` にする(origin なし repo とリモート名が origin でない repo も対象)。一時 worktree と `<type>/<slug>` branch を作り、開始 commit を記録する。作成失敗時は主 worktree へ移らず停止する。以後の実装・検証・レビューは worktree 内だけで行う。

委譲指示は目的 / write_scope / 変更内容 / 受け入れ条件 / 検証 / commit 禁止を 1 ブロックにする。実装 backend は commit しない。

#### CLI 起動形

codex はジョブごとの JOB_DIR に JSONL を保存し、`thread.started` の非空 thread_id が厳密に 1 件の場合だけ `thread-id.txt` へ保存する。

```bash
JOB_DIR=$(mktemp -d "${TMPDIR:-/tmp}/devkit-codex-job.XXXXXX") && echo "JOB_DIR=$JOB_DIR"
JOB_DIR=<記録済みパス> && set -o pipefail && codex -a never exec -C "<worktree>" --sandbox workspace-write -m gpt-5.6-sol -c model_reasoning_effort="medium" --json "<実装指示>" < /dev/null | tee "$JOB_DIR/codex-events.jsonl"
JOB_DIR=<記録済みパス> && uv run --no-project --python ">=3.10" python -c 'import json,sys; ids=[event.get("thread_id") for line in open(sys.argv[1], encoding="utf-8") if line.strip() for event in [json.loads(line)] if event.get("type") == "thread.started"]; (len(ids) == 1 and isinstance(ids[0], str) and ids[0]) or sys.exit("expected exactly one non-empty thread.started thread_id"); print(ids[0])' "$JOB_DIR/codex-events.jsonl" > "$JOB_DIR/thread-id.txt" && test -s "$JOB_DIR/thread-id.txt"
```

cursor-agent はジョブごとに chatId を保存する。

```bash
JOB_DIR=$(mktemp -d "${TMPDIR:-/tmp}/devkit-dig-job.XXXXXX") && CHAT_ID="$(cursor-agent create-chat < /dev/null | tr -d '\r\n')" && test -n "$CHAT_ID" && printf '%s\n' "$CHAT_ID" > "$JOB_DIR/chat-id.txt" && echo "JOB_DIR=$JOB_DIR"
JOB_DIR=<記録済みパス> && cursor-agent -p --resume "$(cat "$JOB_DIR/chat-id.txt")" --trust --force --model cursor-grok-4.5-high --workspace "<worktree>" --output-format text "<実装指示>" < /dev/null
```

Codex 親で cursor-agent を使う場合だけ末尾に `> "$JOB_DIR/cursor-agent.log" 2>&1` を加え、ログ増分で進捗を示す。cursor-agent は sandbox なしで動くため write_scope と commit 禁止を指示する。すべての非対話 codex / cursor-agent コマンドで stdin を `< /dev/null` に閉じる。

依存がなく write_scope が互いに素なジョブだけを並列化する。同一 worktree 内でも担当外変更と各ジョブ内のテスト実行を禁じ、親が統合後に一括検証する。

#### 節目 commit

実装 backend は commit しない。親がジョブを回収して diff を確認するたびに、そのジョブの write_scope をパス限定で add して commit する。`git add .` / `git add -A` は使わない。pre-commit が unstaged 変更を stash する repo では、並列ジョブ実行中は保留し、全ジョブ回収後にジョブ単位で順に commit する。

### 7. 自レビューと独立 diff レビュー

**レビュー前に実装を作業 branch へ commit しておく。** `review --base` は commit 済み差分だけを対象とするため、未 commit のままだと空 diff を「指摘なし」と誤報し、必須の独立レビューが空振りする。

親が基点からの diff 全文を計画と照合し、逸脱の理由・リスク・要確認点を判断する。プロジェクトのテスト・lint を実行し、実装 worker と別の reviewer にブランチ全体をレビューさせる。

codex review の例（origin なしは `--base <default>`）:

```bash
codex -a never exec -m gpt-5.6-sol -c model_reasoning_effort="medium" review --base origin/<default> < /dev/null
```

### 8. 修正ループ

指摘を実装 backend へ戻し、親の確認・検証・独立レビューを繰り返す。CLI の共通引数は step 6 の起動形を維持し、resume 側の差分だけ次に示す。

| backend | resume 差分 |
|---------|-------------|
| codex | `exec resume` + `"$(cat "$JOB_DIR/thread-id.txt")"` + `"<指摘と修正指示>"` |
| cursor-agent | `--resume "$(cat "$JOB_DIR/chat-id.txt")"` + `"<指摘と修正指示>"` |
| Codex 親 worker | 生存中は `send_input`、close 済みは新しい `spawn_agent` worker |

codex の resume 完全形（非対話 stdin 契約の確認用）:

```bash
JOB_DIR=<記録済みパス> && test -s "$JOB_DIR/thread-id.txt" && codex -a never -C "<worktree>" --sandbox workspace-write exec resume -m gpt-5.6-sol -c model_reasoning_effort="medium" "$(cat "$JOB_DIR/thread-id.txt")" "<指摘と修正指示>" < /dev/null
```

cursor-agent は step 6 の完全形の最終引数だけ `"<指摘と修正指示>"` に替える。Codex 親では同じログリダイレクトを維持する。diff が計画と一致し、テストが green、指摘がゼロで終了する。3 周で収束しなければ停止して判断を求める。

### 9. 統合・後始末・完了報告

計画した統合方法だけを実行する。PR 経路の骨格は提出 → CI 待機 → green 判定 → merge → 完了確認 → cleanup。

- 統合直前に fetch / rebase し、必要な単調増加値を origin から再計算して再検証する。repo に標準解消規則のない conflict は abort して停止する。
- checks の取得前後に head SHA を取得し、同じ SHA に束縛された checks だけを判定する。SHA が動いた checks は破棄する。
- `gh` の API・認証・通信エラーをチェック 0 件の成功と混同しない。0 件の扱いは計画した CI 有無と登録猶予に従い、観測した checks を優先する。
- green は全 checks が pass（skipping は許容）のときだけ。赤・pending・期限超過は merge しない。
- merge queue / auto-merge が有効、または preflight が確認不能なら merge せず停止・報告する。
- merge 直前の head が検証済み SHA と同じ場合だけ `gh pr merge <PR番号> --merge --match-head-commit <検証済みSHA>` を実行する。repo 規則の方式フラグを必ず明示し、`--delete-branch` は使わず、失敗時に別方式へ切り替えない。
- `gh pr view <PR番号> --json state,mergedAt` で `MERGED` を確認するまで統合完了としない。
- cleanup は remote tip が検証済み SHA と一致することを確認してから行う。不在時も PR の headRefOid で同一性を確認する。remote branch の削除は期待 tip を束縛した `git push --force-with-lease=refs/heads/<branch>:<検証済みSHA> origin :refs/heads/<branch>` で行う（束縛なしで消すと、確認後に他者が push した commit を捨てうる）。確認不能・不一致・lease 失敗は remote を削除せず「統合成功・cleanup 未完了」として残存物を報告する。
- CI 赤・merge 失敗では PR を open のまま残し、worktree・branch・commit を破棄せず停止する。

直接統合は主 worktree が clean、既定 branch 上、非 diverged のときだけ ff-only merge / push する。push reject は fetch / rebase / 再検証からやり直す。origin なしは ff-only merge で完了とする。

cleanup は統合確認後だけ行い、未追跡ファイル等で worktree remove が拒否されたら `--force` を使わない。節目 commit は親だけが行い、ジョブの write_scope をパス限定で add する。`git add .` / `git add -A` は使わない。

失敗時は変更を破棄せず、branch、worktree、停止操作、再開方法を報告する。完了報告には変更、検証、逸脱・仮定、残課題、commit、PR、CI、merge の `MERGED` 確認、cleanup 状態を含める。

## goal-prompt への引き継ぎ(ユーザー明示時のみ)

レビュー済み計画を `.claude/plans/YYYY-MM-DD-<slug>.md` へ保存して実装せず終了し、`/goal-prompt` を案内する。goal-prompt は意味を変えず Goal プロンプトへ変換するだけで、追加承認や独立レビューを行わない。dig は組み込み `/goal` を自動発動しない。

## 実装の注意

- sandbox 緩和や write_scope 外の変更はユーザー確認を得る。
- backend が使えなければ報告し、別選択肢または承認済みの親実装へ切り替える。
- 非 git repo は worktree / commit / 統合を適用せず、diff と結果を報告する。
