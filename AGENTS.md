# AGENTS.md

このファイルを、このリポジトリ直下のエージェント向け指示の正本とする。`CLAUDE.md` は参照入口として扱い、実質的なルールはここへ集約する。

## Repo Context

- このリポジトリは DevKit のセットアップ/更新スクリプト、skills、templates を管理する
- 配布 skill は `plugins/devkit/skills/dig/`、`plugins/devkit/skills/goal-prompt/`、`plugins/devkit/skills/improve-skill/`、`plugins/devkit/skills/setup/`、`plugins/devkit/skills/refactor/`、`plugins/devkit/skills/memory-review/`、`plugins/devkit/skills/handoff/`、`plugins/devkit/skills/backlog/`、`plugins/devkit/skills/catch-up/`、`plugins/devkit/skills/commit-push/`、`plugins/devkit/skills/repo-loop/` の 11 本とする
- repo-loop は trigger(手動・定期・イベント)起点で改善課題を自分で選ぶ自律ループであり、非対話実行では質問せず、low/medium risk は事前承認なしで Draft PR まで(auto-merge・ready 化はしない)、high risk は提案 Issue へ降格する。dig(ユーザー要求起点・計画承認・統合完遂)とは起点と出口で分離し、repo-loop から dig を自動呼び出さない
- statusline 配布物は `plugins/devkit/statusline/` に同梱し、適用は setup workflow から行う
- Codex 側の配布は plugin marketplace を正本にし、独自の skill 同期経路は復活させない
- 振る舞いを変える変更では、コードだけでなく対応するドキュメントも同じ変更で揃える
- ルートの正規ファイル名は `AGENTS.md` と `CLAUDE.md` を使う
- goal-prompt は Goal プロンプト本文を gitignore 済みの `.claude/goal-runs/` へ保存する(上書きせず連番)。commit も premises.json への出現登録もしない。dig がユーザー明示で goal-prompt へ引き継ぐ場合はレビュー済み計画を `.claude/plans/` へ保存する

## Workflow

開発フローの基本形は次のとおり。実行オーケストレーションのスキル実体は `plugins/devkit/skills/dig/SKILL.md`。

1. 深掘り: 要求が曖昧なら、未知を棚卸しして影響が大きい未知だけ質問し、ユーザーの要求(目的・成功条件・非対象)を聞き出す。未知棚卸し表(質問する / 仮定で進める / 確定済み)で終了判定を可視化し、小さい未知は仮定を明示して進める(質問ポリシーの正本は dig スキルの SKILL.md)
2. 計画: コードベースを調査し、decision-complete な計画を作る
3. 承認: 計画レビュー・実装・diff レビューの backend を選択し、計画レビュー(skip 可)を経た計画をユーザーに提示して、承認を得てから実装に進む。Claude 親は plan mode / ExitPlanMode を既定とする
4. 実装: worktree 上の作業ブランチで計画に沿って差分を作り、親が節目ごとにパス限定で commit する。計画から逸脱する場合は理由・リスク・要確認点を記録する(実装を外部 backend に委譲する場合は dig スキルの契約に従う)
5. 自レビュー: diff 全文を計画と突き合わせ、テスト・リンタを実行する
6. 修正ループ: 指摘が解消するまで修正を繰り返す
7. 報告と統合: 変更サマリーを報告し、統合(既定は PR の提出 + CI green 確認 + merge。PR 不可 repo では直接統合の merge / push)まで dig が完遂する。承認は計画承認に一本化し、計画に明記した統合方法以外は実行しない

## 並行開発と worktree

- 並行して進める開発は `git worktree` で分離する。main の作業ツリー上で複数機能を同時に進めない(1 ブランチ = 1 worktree)
- 複数機能・複数ブランチの並行開発は worktree を分離する。単一機能内の並列実装委譲は dig 契約に従い、同一 worktree で write_scope を互いに素にし、節目 commit はパス限定で行う
- dig の実装系は常に worktree を使う(正本は `plugins/devkit/skills/dig/SKILL.md`)
- `plugins/devkit/**` に触る作業の開始時と version bump 直前に `git fetch origin` で origin/main との差を確認し、遅れていれば先に取り込む(v7.5.0 の version 衝突・rebase コンフリクトの再発予防)
- 他セッション由来の worktree・ブランチ・open PR は常に存在しうる進行中の正常な作業として扱う。削除・checkout・rebase・「残骸がある」等の報告の対象にしない。後始末は自セッションが作成した worktree・ブランチ・PR に限り、他 worktree の調査・掃除はユーザーが明示依頼した場合のみ行う
- origin/main は他 worktree の PR が順に merge されて進む前提で運用する。統合前の fetch + rebase・version 再計算・push reject からのやり直し・rebase 標準解消手順は、この前提での通常運転であり異常として扱わない(標準解消手順の対象外の衝突のみ従来どおり停止・報告)

### 統合時 rebase 衝突の標準解消手順

worktree 統合の rebase で発生する既知の機械的衝突は、以下の手順で解消して rebase を続行してよい（dig の統合契約から参照される）。機械解消の対象はここに列挙したクラスに限定する。

- `plugins/devkit/.claude-plugin/plugin.json` の `version` の衝突: origin 側の値を一時採用して rebase を続行し、rebase 完了後に Release Rules に従い最新 origin 値から bump 種別を一度だけ再適用する。rebase 中に version 変更だけの commit が空になった場合は `git rebase --skip` する（version 以外の変更を含む commit は skip しない）
- `plugin.json` の `description` の衝突: base と比べて片側だけが変更している場合はその側を採用する。両側が変更している場合は機械解消せず停止・報告する（version と一括りに origin 側を採用しない）
- スキル一覧の識別子集合（`check_skill_surface.py` の EXPECTED_SKILLS、`test_document_consistency.py` の DISTRIBUTED_SKILLS）の衝突: base / origin / branch の三者比較で両側とも追加のみと確認できた場合に限り和集合で解消する。削除・rename・同一項目の両側変更を含む場合は停止・報告する。AGENTS.md / README.md / plugin description など文章中のスキル列挙・個数は和集合の対象にせず、確定した識別子集合に合わせて再構成する
- 標準解消で rebase を完了した後は verify-full を再実行し、失敗時は push せず停止・報告する
- 上記以外の衝突は従来どおり `git rebase --abort` して停止・報告する

## dig と goal-prompt の使い分け

dig はユーザーの主開発ワークフローで、深掘りから実装・検証・統合まで完遂する。**既定は実装完遂**で、開始時に実行形態を質問しない。ユーザーが明示した場合だけ、次のいずれかへ分岐する。

- read-only 終了: 計画だけ・調査だけ・相談だけをユーザーが明示した場合、実装せず提示のみで終了する
- goal-prompt への引き継ぎ: ユーザーが別ターン・後続セッション・不在実行への引き継ぎを明示した場合、レビュー済み計画を `.claude/plans/YYYY-MM-DD-<slug>.md` へ保存し goal-prompt へ渡す

goal-prompt は会話・仕様・計画から Goal プロンプトを `.claude/goal-runs/` へ保存生成し(上書きせず連番)、`/goal` 起動プロンプトを出力する軽量スキルとする。コード変更・commit / push・PR 作成・Goal 独立レビューは行わず、`/goal` の実行はユーザーが行う。上限停止は goal-prompt が自動算出する。固定済み Goal ファイルの反復巡回はユーザーが `/loop` で登録する運用とし、課題を毎回自選する定期改善は repo-loop(envelope の `trigger.type: schedule`)を使う

## Maintenance Rules

- ルートのエージェント向けルールを変更するときは、まずこのファイルを更新する
- スクリプトの仕様変更時は `README.md` と `plugins/devkit/scripts/README.md` を同期する
- スキル契約を変える場合は対応する `SKILL.md` と必要な templates / scripts を同期する
- 外部世界由来の値（モデル名・CLI フラグ・marketplace 名等）を docs へ追加・変更するときは `plugins/devkit/premises.json` に登録・更新する（`check_external_premises.py` が同期を強制する）
- スキル契約や user-visible workflow を刷新するときは、ユーザーが明示しない限り fallback や後方互換の維持を要件にしない。新しい正本の挙動を明確化し、旧経路を半端に残さない
- この repo では、ファイル変更を伴うタスクごとに必ず独立したサブエージェント review を 1 回以上実施する
- review で指摘が出た場合は修正後に再 review を回し、追加 findings がなくなるまで繰り返す
- 品質ルールは prose より決定論的ツールを優先し、lint / format / validation / test で強制する。バグや逸脱が出たら、同じ失敗を次回自動検出できる check を追加する

## スキル採用基準

新しいスキル・ルール・自動化の採否はこの基準で判断する。工程マップの空白を埋めるため（gap-push）の追加はしない。

1. 起点は demand-pull: 観測された反復する痛みから起案する
2. 証拠テスト: 同じ痛みを 2 つ以上の repo またはセッションで実際に観測してから起案する
3. 最小手段の梯子: ルール 1 行 → check スクリプト → 既存スキルへの 1 観点追加 → それでも足りない場合のみ新スキル
4. 5 テスト: 反復性 / 即興リスク（即興でやると事故る既知の失敗モードがあるか）/ ハーネス非重複（Claude Code / Codex 組み込み機能と被らないか）/ 監査可能性（再現できる出力があるか）/ 撤退性（安全に廃止できるか）をすべて満たす

根拠: スキル 1 本ごとに保守・ドリフト・監査面積が増える（2026-07-05 の memory-review で実測。`docs/reviews/2026-07-05-memory-review.md`）。improve-skill の create モードは、この基準への照合結果を提案に含める。

## スキル共通契約

配布スキル（`plugins/devkit/skills/*/SKILL.md`）が共有する契約の正本。各 SKILL.md は要点と本節への参照だけを持ち、独自の定義でこの契約を上書きしない。配布先には repo ルートの AGENTS.md が同梱されないため、各 SKILL.md は実行に必要な要点を自己完結で保持する（本節への参照はメンテナンス時の正本を示すためのもの）。

### ハーネス判定

- `AskUserQuestion` が使える → Claude 親
- `AskUserQuestion` がなく `spawn_agent` が使える → Codex 親
- どちらでもない → 判定不能として扱う
- `request_user_input` は plan mode 依存で不安定なため判定キーに使わない。Codex 親 plan mode での質問手段としてのみ使う

### 質問手段

- Claude 親: AskUserQuestion
- Codex 親 plan mode: `request_user_input`
- Codex 親通常 mode / 判定不能: 選択肢を箇条書きで提示して自由文回答を求める

### 承認手段

- Claude 親: plan mode + `ExitPlanMode` を既定とし、step 1 開始時に plan mode 外であれば `EnterPlanMode` で入る。`EnterPlanMode` を利用できない場合だけ、計画全文を提示して明示承認を得る
- Codex 親 plan mode: `request_user_input` で承認を得る
- Codex 親通常 mode / 判定不能: 計画全文を提示して自由文で明示承認を得る

### タスクリスト連動

- Claude 親: TaskCreate / TaskUpdate が利用可能なら、workflow の step を登録し開始時 `in_progress`・完了時 `completed` に更新する。利用不可なら省略してよい
- Codex 親: 組み込み plan 機能または通常の進捗報告で同等の進捗提示を行う

### 委譲・長時間ジョブの進捗可視化

- 委譲ジョブ・長時間ジョブは 1 ジョブ = 1 タスクとしてタスクリストへ登録し、開始・完了で状態を更新する(親 step のタスクに blockedBy で紐付ける)
- Claude 親: 外部 CLI への委譲(codex exec / cursor-agent 等)は Bash の `run_in_background` で起動する。ジョブは UI に実行中タスクとして表示され、完了時に親へ自動通知が届く。完了待ちは通知駆動とし、定期ハートビートの逐次表示は行わない
- Claude 親の停滞検知: 待機中は数分おき(目安 2〜5 分)に TaskOutput またはジョブのログファイルで出力増分を確認し、増分ゼロが続く場合のみ停滞の継続時間と推定原因(内部レビュー待ち / 長考 / ハング)をユーザーへ報告する
- Claude サブエージェント委譲(Agent)も 1 委譲 = 1 タスクとしてタスクリストへ登録し、開始時 `in_progress`・完了時 `completed` へ更新する。Agent は元々バックグラウンド実行 + 完了自動通知のため追加の起動処置は不要。停滞検知の考え方は同じ
- Codex 親: run_in_background / TaskOutput は使えない。`wait_agent` で黙って待たず、定期的に進捗をユーザーへ提示する
- 実体の進捗確認は `git status` / `git diff` で行う(resume を進捗確認に使わない)
- codex exec をバックグラウンド起動する場合も stdin を `< /dev/null` で閉じる

### codex exec 実行形

```bash
codex -a never exec -m gpt-5.6-sol -c model_reasoning_effort="medium" "<内容>" < /dev/null
```

- Codex のモデルは `gpt-5.6-sol` を `-m` で明示する。世代追従は catch-up スキルと `premises.json` で管理する（ユーザーが別モデルを明示指定した場合はそれに従う）
- 非対話実行では必ず末尾に `< /dev/null` を付ける（stdin 待ちで無期限ハングするため）
- `-a never` などの top-level オプションは `exec` より前に置く

### Codex モデル / effort

- モデルは `gpt-5.6-sol`、effort は `medium` に固定する。計画レビュー・実装・diff レビューのすべてで同じ値を使い、effort の選択質問は行わない
- Max は対応 surface の最深推論、Ultra は並列オーケストレーションを表す。この repo では説明にだけ用い、backend 選択肢、CLI の effort、config 値にはしない
- Codex 親が `spawn_agent` を使う場合、子 agent ごとの effort 選択は追加しない

## Key Paths

- `README.md`: リポジトリ全体の導入・運用説明
- `plugins/devkit/scripts/`: setup / update 系スクリプト
- `plugins/devkit/skills/dig/SKILL.md`: 深掘り・計画・worktree 実装・統合完遂 workflow の正本
- `plugins/devkit/skills/goal-prompt/SKILL.md`: Goal プロンプト保存生成・起動プロンプト出力 workflow の正本
- `plugins/devkit/skills/improve-skill/SKILL.md`: skill 改善 workflow の正本
- `plugins/devkit/skills/setup/SKILL.md`: 対象リポジトリへの DevKit ルール同期・環境前提チェック(claude / codex / cursor-agent / node / uv)・thought-db 接続同期・updater 同期・旧 updater 名の残骸 prune・statusline 適用・Windows Terminal フォント適用 workflow の正本
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

- コミットメッセージは Conventional Commits を使う
- 基本形は `<type>(<scope>): <summary>` とし、`scope` は必要な場合だけ付ける
- `type` は `feat` `fix` `docs` `refactor` `test` `chore` `ci` `build` `perf` `revert` を優先して使う
- `summary` は必ず日本語で簡潔に書く
- 本文を書く場合も日本語で統一し、変更理由・影響範囲・補足を必要最小限で書く
- 破壊的変更は `type!:` または `type(scope)!:` を使い、必要なら本文に `BREAKING CHANGE:` で日本語説明を付ける
- 英語だけの要約や、Conventional Commits に沿わない自由形式のコミットメッセージは使わない
- Commit 規約はエージェント運用ルールであり、commit-msg hook では強制しない（決定論的強制の対象外と明示的に判断済み）

例:

- `feat(update-ccx): Windows で npm 欠落時の自己修復を追加`
- `docs(agents): コミット規約を AGENTS.md に追記`

## Release Rules

この節が version 運用ルールの正本。`README.md` の Release Rule は要点と本節への参照のみを持つ。

- この repo は Claude Code Marketplace plugin を含む
- Codex 側も `murakotaro4/devkit` marketplace 登録を配布正本にする
- `plugins/devkit/**` または `.claude-plugin/**` を変更した場合、push 前に `plugins/devkit/.claude-plugin/plugin.json` の version を上げる
- pre-push gate は version が `origin/main` の version 以下なら push を block する（厳密に上回る必要がある。誤って下げた場合も block される）
- version の目安:
  - `patch`: docs / bugfix only
  - `minor`: workflow contract / user-visible behavior 変更
  - `major`: breaking change

## Codex Exec 相談ルール

リポジトリ全体のルール: 行き詰まった場合は `codex exec` で外部モデルに相談する。全エージェント作業に適用する。

```bash
codex -a never exec -m gpt-5.6-sol -c model_reasoning_effort="medium" "<相談内容>" < /dev/null
```

- 実行形は「スキル共通契約 > codex exec 実行形」に従う（モデルは `gpt-5.6-sol`、effort は `medium` に固定）
- 技術的判断に迷った場合、設計の妥当性を確認したい場合に使用する
- 結果は参考意見として扱い、最終判断は親エージェントが行う
