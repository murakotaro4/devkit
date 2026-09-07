---
name: "dig"
description: "開発要求を深掘りし、計画承認後に実装・検証・統合まで完遂する。『深掘りして』『実装して』『相談したい』『/dig』で起動"
argument-hint: "[task]"
---

# /dig - 深掘り + 実装完遂

**dig の既定は実装完遂**。開始時に実行形態を質問しない。ユーザーが「計画だけ」「調査だけ」「相談だけ」「実装しない」と明示した場合は read-only で終了する。「Goal プロンプトにして」「/goal で動かしたい」「後で実行したい」と明示した場合は goal-prompt へ引き継ぐ。

## 対象

$ARGUMENTS

## ハーネス判定と実行差分

| 条件 | 親 | 質問 / 承認 |
|---|---|---|
| `AskUserQuestion` が使える | Claude 親 | 質問は AskUserQuestion。step 1 で `EnterPlanMode`、承認は `ExitPlanMode`。利用不能時だけ計画全文への明示承認 |
| AskUserQuestion がなく `spawn_agent` が使える | Codex 親 | plan mode は `request_user_input`、通常 mode は選択肢を提示して自由文回答 / 明示承認 |
| どちらもない | 判定不能 | 選択肢を提示して自由文回答 / 明示承認 |

`request_user_input` はハーネス判定に使わない。step 1-5 は対象 repo に対して read-only とし、承認前に step 6 へ進まない。前半の書き込み例外は独立レビュー用の一時領域・ログと、ユーザー明示による goal-prompt 引き継ぎ時の `.claude/plans/` だけ。step 6-9 は承認済み write_scope 内だけを書き込む。sandbox の緩和や write_scope 外の変更が必要なら、実行前にユーザー確認を得る。frontmatter に `allowed-tools` を置かず、秘密情報・資格情報・個人情報は委譲プロンプトへ転記しない。

### Codex 親の作業分担

Codex 親（Astra を含む）は調査・設計・実装・検証・修正・最終判断を一貫して担当する。サブエージェントへの委譲は読み取り専用の独立レビューに限定し、調査・実装・修正を委譲しない。レビュー担当はファイル編集、Git の変更操作、外部への書き込み、追加のサブエージェント起動を行わず、指摘と根拠を親へ返す。 親のモデルと effort は現在の設定を維持し、レビュー担当も原則として引き継ぐ。ユーザー指定があれば従う。外部 CLI への実装委譲も行わない。

### タスクと進捗

step 1-9 と各委譲・長時間ジョブをタスク化し、1 ジョブ = 1 タスクとする。Claude 親の外部 CLI は `run_in_background` と完了通知で回収する。Codex 親は定期的に進捗を示す。`wait_agent` で黙って待たず、指摘解消まで `close_agent` を遅らせる。実体の進捗は `git status` / `git diff` とジョブログで確認し、resume を進捗確認に使わない。出力増分が数分止まった場合だけ、停滞の継続時間と推定原因を報告する。

## フロー

### 1. 深掘り(棚卸し駆動面談、親)

タスク型と要求を確定する。質問対象、表の形式、終了条件は、この工程を始める直前に [計画と承認](references/planning.md) の「深掘り」を読む。統合方法は質問せず step 2 の調査で確定する。

### 2. 調査 + 計画(親)

対象を read-only で調べ、decision-complete な計画を親が統合する。計画を作る直前に [計画と承認](references/planning.md) の「調査と計画」を読み、承認用サマリー、工程表、write_scope、検証、統合方法を欠かさない。

### 3. backend 固定とフォールバック

backend を起動する直前に [実行経路](references/execution.md) の「backend 固定とフォールバック」を読む。モデル、effort、親別 lane、降格条件、停止・報告条件を変更せず適用する。backend は質問せず、ユーザー明示指定はフォールバック禁止の固定指定として扱う。

### 4. 計画レビュー

計画全文を独立 backend へ渡し、decision-complete 性・矛盾・見落としを審査する。起動直前に [計画と承認](references/planning.md) の「計画レビュー」を読み、指摘を反映してから承認へ進む。

### 5. 計画承認

レビュー済み計画を第 1 層から提示して明示承認を得る。承認後だけ plan mode を抜け、承認済み write_scope を有効にする。提示直前に [計画と承認](references/planning.md) の「計画承認」を読む。

### 6. worktree 作成と実装委譲

git repo の実装系は必ず worktree を使う。非 git repo には worktree / commit / 統合を適用せず、diff と結果を報告する。作成・委譲直前に [実行経路](references/execution.md) の「worktree 作成と実装委譲」を読み、origin なし・branch 衝突の分岐、stdin、ジョブ識別子、write_scope、commit 禁止を適用する。

#### 節目 commit

Codex 親は自身の実装を確認し、write_scope をパス限定で add して commit する。Claude 親・判定不能の場合、実装 backend は commit しない。親がジョブ回収後、そのジョブの write_scope をパス限定で add して commit する。`git add .` / `git add -A` は使わない。詳細は [実行経路](references/execution.md) の同名節を読む。

### 7. 自レビューと独立 diff レビュー

レビュー前に実装を作業 branch へ commit する。自レビューと独立レビューを始める直前に [実行経路](references/execution.md) の「自レビューと独立 diff レビュー」を読む。

### 8. 修正ループ

指摘がゼロになるまで修正・再検証・独立レビューを繰り返す。Codex 親は自身で修正し、子には再レビューだけを依頼する。以下の thread / chat 再開は Claude 親・判定不能の場合だけ適用する。再開直前に [実行経路](references/execution.md) の「修正ループ」を読み、同じ thread / chat、降格後の新規ジョブ、収束停止条件を適用する。

### 9. 統合・後始末・完了報告

計画した統合方法だけを実行する。統合開始直前に [統合と完了](references/integration.md) を読み、標準解消規則に沿う fetch / rebase、再検証、PR、CI green、head SHA、merge、削除の安全条件、失敗時の保存、完了報告を順に適用する。

## goal-prompt への引き継ぎ(ユーザー明示時のみ)

レビュー済み計画を `.claude/plans/YYYY-MM-DD-<slug>.md` へ保存して実装せず終了し、`/goal-prompt` を案内する。goal-prompt は意味を変えず Goal プロンプトへ変換するだけで、追加承認や独立レビューを行わない。dig は組み込み `/goal` を自動発動しない。詳細は [統合と完了](references/integration.md) の「goal-prompt への引き継ぎ」を読む。
