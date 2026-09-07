# AGENTS.md

このファイルを、このリポジトリ直下のエージェント向け指示の正本とする。`CLAUDE.md` は参照入口として扱い、実質的なルールはここへ集約する。

## Repo Context

- このリポジトリは DevKit のセットアップ/更新スクリプト、skills、templates を管理する
- 配布 skill は `plugins/devkit/skills/dig/`、`plugins/devkit/skills/goal-prompt/`、`plugins/devkit/skills/improve-skill/`、`plugins/devkit/skills/setup/`、`plugins/devkit/skills/refactor/`、`plugins/devkit/skills/memory-review/`、`plugins/devkit/skills/handoff/`、`plugins/devkit/skills/backlog/`、`plugins/devkit/skills/catch-up/`、`plugins/devkit/skills/commit-push/`、`plugins/devkit/skills/repo-loop/` の 11 本とする
- repo-loop は trigger(手動・定期・イベント)起点で改善課題を自分で選ぶ自律ループであり、非対話実行では質問せず、low/medium risk は事前承認なしで Draft PR まで(auto-merge・ready 化はしない)、high risk は提案 Issue へ降格する。dig(ユーザー要求起点・計画承認・統合完遂)とは起点と出口で分離し、repo-loop から dig を自動呼び出さない
- statusline 配布物は `plugins/devkit/statusline/` に同梱し、適用は setup workflow から行う
- Codex 側の配布は `murakotaro4/devkit` marketplace を正本にし、独自の skill 同期経路は復活させない
- 振る舞いを変える変更では、コードだけでなく対応するドキュメントも同じ変更で揃える
- ルートの正規ファイル名は `AGENTS.md` と `CLAUDE.md` を使う
- goal-prompt は本文を gitignore 済みの `.claude/goal-runs/` へ連番保存し、commit も premises.json 登録もしない。dig から明示的に引き継ぐレビュー済み計画だけ `.claude/plans/` へ保存する

## Workflow

実行オーケストレーションの正本は `plugins/devkit/skills/dig/SKILL.md`。ここでは骨格だけを定める。

1. 深掘り: 目的・成功条件・非対象と、影響の大きい未知を確定する
2. 計画: 調査結果から decision-complete な計画を作る
3. 承認: 独立した計画レビューを反映し、ユーザー承認を得る
4. 実装: 承認済み write_scope と統合方法に従う
5. 自レビュー: 計画との diff、テスト、リンタを確認する
6. 修正ループ: findings がなくなるまで直す
7. 報告と統合: 既定は PR 提出、CI green、merge まで完遂する

## 並行開発と worktree

- dig の実装は 1 ブランチ = 1 worktree とし、複数機能を main 作業ツリーで並行しない。Claude 親・判定不能の場合だけ実装を委譲でき、同一 worktree の並列委譲は write_scope を互いに素にする
- `plugins/devkit/**` に触る作業の開始時と version bump 直前に `git fetch origin` し、origin/main に遅れていれば取り込む
- 他セッション由来の worktree・ブランチ・open PR は常に存在しうる進行中の正常な作業として扱う。削除・checkout・rebase・「残骸がある」等の報告の対象にしない。後始末は自セッションが作成した worktree・ブランチ・PR に限り、他 worktree の調査・掃除はユーザーが明示依頼した場合のみ行う
- origin/main の進行を通常運転とし、統合前に fetch + rebase と version 再計算を行う

### 統合時 rebase 衝突の標準解消手順

機械解消してよいのは次のクラスだけ。

- `plugin.json` の `version`: origin 値で rebase し、完了後に最新 origin 値へ bump を 1 回適用する。version だけの空 commit は skip できる
- `plugin.json` の `description`: base 比で片側だけの変更ならその側を採用する
- スキル識別子集合: base / origin / branch の両側が追加のみなら和集合にする。文章中の列挙は確定集合から再構成する

それ以外（両側の description 変更、識別子の削除・rename・同一項目変更を含む）は `git rebase --abort` して停止・報告する。機械解消後は verify-full を再実行し、失敗時は push しない。

## dig と goal-prompt の使い分け

dig の既定は実装完遂で、開始時に実行形態を質問しない。ユーザーが明示した場合だけ分岐する。

- 計画・調査・相談だけ: read-only で終了
- 別ターン・不在実行: レビュー済み計画を `.claude/plans/YYYY-MM-DD-<slug>.md` に保存し goal-prompt へ渡す

goal-prompt は Goal プロンプトの保存と `/goal` 起動文の出力だけを行い、コード変更・commit・push・PR・独立レビュー・実行はしない。反復巡回は `/loop`、課題を自選する定期改善は repo-loop の `trigger.type: schedule` を使う。

## Maintenance Rules

- ルートのエージェント向けルールを変更するときは、まずこのファイルを更新する
- スクリプトの仕様変更時は `README.md` と `plugins/devkit/scripts/README.md` を同期する
- スキル契約を変える場合は対応する `SKILL.md` と必要な templates / scripts を同期する
- 外部世界由来の値（モデル名・CLI フラグ・marketplace 名等）を docs へ追加・変更するときは `plugins/devkit/premises.json` に登録・更新する（`check_external_premises.py` が同期を強制する）
- user-visible workflow を刷新するときは、明示要件でない fallback や後方互換を残さない
- この repo では、ファイル変更を伴うタスクごとに必ず独立したサブエージェント review を 1 回以上実施する
- review で指摘が出た場合は修正後に再 review を回し、追加 findings がなくなるまで繰り返す
- 品質ルールは prose より決定論的ツールを優先し、lint / format / validation / test で強制する。バグや逸脱が出たら、同じ失敗を次回自動検出できる check を追加する
- 配布ドキュメントのサイズは gate ではなく計測値として扱う。`report_doc_size.py` が `cc2cd36` 基点の baseline 比を verify で出す

## スキル採用基準

新しいスキル・ルール・自動化の採否はこの基準で判断する。工程マップの空白を埋めるため（gap-push）の追加はしない。

1. 起点は demand-pull: 観測された反復する痛みから起案する
2. 証拠テスト: 同じ痛みを 2 つ以上の repo またはセッションで実際に観測してから起案する
3. 最小手段の梯子: ルール 1 行 → check スクリプト → 既存スキルへの 1 観点追加 → それでも足りない場合のみ新スキル
4. 5 テスト: 反復性 / 即興リスク（即興でやると事故る既知の失敗モードがあるか）/ ハーネス非重複（Claude Code / Codex 組み込み機能と被らないか）/ 監査可能性（再現できる出力があるか）/ 撤退性（安全に廃止できるか）をすべて満たす

根拠: スキル 1 本ごとに保守・ドリフト・監査面積が増える（2026-07-05 の memory-review で実測。`docs/reviews/2026-07-05-memory-review.md`）。improve-skill の create モードは、この基準への照合結果を提案に含める。

## スキル共通契約

配布スキル（`plugins/devkit/skills/*/SKILL.md`）の共有契約の正本。配布先には AGENTS.md が同梱されないため、各 SKILL.md は実行に必要な要点を自己完結で保持し、本節を独自定義で上書きしない。

### ハーネス判定

`request_user_input` は判定キーに使わない。

| 種別 | 判定 | 質問 | 承認 |
|---|---|---|---|
| Claude 親 | `AskUserQuestion` が使える | `AskUserQuestion` | `EnterPlanMode` で入り `ExitPlanMode`。利用不能時だけ計画全文への明示承認 |
| Codex 親 | 上記がなく `spawn_agent` が使える | plan mode は `request_user_input`、通常 mode は選択肢 + 自由文 | 同じ手段で計画全文への明示承認 |
| 判定不能 | どちらもない | 選択肢 + 自由文 | 計画全文への自由文明示承認 |

### 計画・レポートの 2 層提示

dig / refactor / backlog / catch-up / memory-review の長文は、承認用サマリーを冒頭、詳細を後段に置く。第 1 層だけで判断できるよう、次の 7 カテゴリを含める。

1. 何を / なぜ: 1〜2 文
2. 判断してほしい点: 推奨付き、最大 3 件。なければ「なし」
3. 既定からの逸脱・仮定: なければ「既定どおり」
4. 後戻りしにくい操作・外部影響: 該当分だけ
5. backend 表: 計画レビュー / 実装 / diff レビュー。適用不能は「適用なし」
6. 検証: 成功条件を 1 行
7. 独立レビュー状態: backend と `実施済み(指摘 N 件反映)` / `skip(理由)` / `適用なし`

字数基準の正本は `docs/reviews/2026-07-25-cognitive-load-metrics.md`。

- 目標は散文部(カテゴリ 1〜4)で約 1,000 字。字数は見出し行を除く本文文字数で数える
- 約 1,000 字は hard limit ではなく目標とする。7 カテゴリと承認判断に必要な結論は、超過してでも第 1 層に残す
- 第 2 層へ送ってよいのは根拠・経緯・選択肢の詳細・手順だけとする
- 字数と完全性が衝突した場合は完全性を優先する
- 表は逐次読解でなく走査で読むため、字数ではなく行数で管理する

dig に限り、カテゴリ 5〜7(backend 表 / 検証 / 独立レビュー状態)を「工程 / 状態 / backend」の 3 列表へ統合してよい(工程表形式)。統合しても各カテゴリの情報は省略しない。他スキルは現行の散文形式を維持し、横展開は dig での運用結果を見て別途判断する。

既定事項は「既定どおり」に畳み、第 2 層へ write_scope、変更内容、検証、統合手順を置く。各 SKILL.md は 7 カテゴリとレビュー状態の 3 値を自己完結で保持する。

### タスクと進捗

- workflow と委譲・長時間ジョブはタスク化し、開始・完了を更新する。利用可能な組み込みタスク機能を使い、なければ進捗報告で代替する
- Claude 親の外部 CLI は background 起動し、通知とログ増分で回収する。Codex 親は待機中も定期的に進捗を示す
- 実体の進捗確認は `git status` / `git diff` で行う(resume を進捗確認に使わない)
- 停滞は出力増分がない継続時間と推定原因を報告する

### Codex 契約

- Codex 親（Astra を含む）は調査・設計・実装・検証・修正・最終判断を一貫して担当する。サブエージェントへの委譲は読み取り専用の独立レビューに限定し、調査・実装・修正を委譲しない。レビュー担当はファイル編集、Git の変更操作、外部への書き込み、追加のサブエージェント起動を行わず、指摘と根拠を親へ返す。
- 親のモデルと effort は現在の設定を維持し、レビュー担当も原則として親の設定を引き継ぐ。ユーザーが指定した場合はその指定に従う。

以下の CLI 契約は Claude 親・判定不能の場合だけ適用する。

```bash
codex -a never exec -m gpt-5.6-sol -c model_reasoning_effort="medium" "<内容>" < /dev/null
```

- 実装の既定は cursor-agent `cursor-grok-4.6-high`。codex を使う工程（計画レビュー・diff レビュー、および実装のフォールバック時）は同じモデル / effort とする。backend の選択質問はせず、降格したときは必ず報告する。子 agent ごとの effort も選択しない
- 非対話の codex / cursor-agent は stdin を `< /dev/null` で閉じる。世代追従は catch-up と `premises.json` で管理する

## Key Paths

- `README.md`: リポジトリ全体の導入・運用説明
- `plugins/devkit/scripts/`: setup / update 系スクリプト
- `plugins/devkit/skills/dig/SKILL.md`: 深掘り・計画・worktree 実装・統合完遂 workflow の正本
- `plugins/devkit/skills/goal-prompt/SKILL.md`: Goal プロンプト保存生成・起動プロンプト出力 workflow の正本
- `plugins/devkit/skills/improve-skill/SKILL.md`: skill 改善 workflow の正本
- `plugins/devkit/skills/setup/SKILL.md`: 対象リポジトリへの DevKit ルール同期・環境前提チェック(claude / codex / cursor-agent / node / uv)・thought-db 接続同期・updater 同期・Claude Code compaction env 同期・cursor-agent Git Bash シム同期・旧 updater 名の残骸 prune・statusline 適用・Windows Terminal フォント適用 workflow の正本
- `plugins/devkit/skills/refactor/SKILL.md`: 負債棚卸し・優先順位付け・計画作成 workflow の正本
- `plugins/devkit/skills/memory-review/SKILL.md`: AI メモリ棚卸し・前提監査 workflow の正本
- `plugins/devkit/skills/handoff/SKILL.md`: セッション引継ぎドキュメント書き出し workflow の正本
- `plugins/devkit/skills/backlog/SKILL.md`: 残課題の横断棚卸し(read-only)・dig 引き継ぎ workflow の正本
- `plugins/devkit/skills/catch-up/SKILL.md`: 外部前提の裏取り・影響棚卸し・追従更新 workflow の正本
- `plugins/devkit/skills/commit-push/SKILL.md`: 論理グループ分割 commit + upstream push workflow の正本(secret 2 層検査・literal pathspec・明示単一 refspec)
- `plugins/devkit/skills/repo-loop/SKILL.md`: trigger 起点の自律改善ループ(調査・課題選定・実装・検証・Draft PR / 提案 Issue / no-op)workflow の正本
- `plugins/devkit/premises.json`: モデル名・CLI フラグ・ハーネス機能・marketplace 名の外部前提レジストリ
- `plugins/devkit/statusline/`: plugin 同梱 statusline 実装と適用スクリプト
- `plugins/devkit/templates/codex/`: Codex 設定テンプレート
- `plugins/devkit/templates/rules/`: setup スキルが対象リポジトリへ同期するルールテンプレート

## Commit Rules

- `<type>(<scope>): <summary>` の Conventional Commits を使い、summary と必要な本文は簡潔な日本語にする
- type は `feat` `fix` `docs` `refactor` `test` `chore` `ci` `build` `perf` `revert` を優先する
- 破壊的変更は `!` と、必要なら `BREAKING CHANGE:` で示す
- commit-msg hook では強制しない

## Release Rules

この節が version 運用ルールの正本。

- `plugins/devkit/**` または `.claude-plugin/**` を変更した場合、push 前に `plugins/devkit/.claude-plugin/plugin.json` の version を上げる
- pre-push gate は version が `origin/main` 以下なら push を block する
- bump は `patch` = docs / bugfix、`minor` = workflow contract / user-visible behavior、`major` = breaking change を目安にする

## Codex Exec 相談ルール

Codex 親は外部 CLI へ相談を委譲せず、自身で判断し、必要なら判断案をサブエージェントの独立レビューへ渡す。Claude 親・判定不能の場合、行き詰まりや設計判断の検証には「Codex 契約」の実行形で外部モデルへ相談できる。結果は参考意見とし、最終判断は親エージェントが行う。
