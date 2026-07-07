# AGENTS.md

このファイルを、このリポジトリ直下のエージェント向け指示の正本とする。`CLAUDE.md` は参照入口として扱い、実質的なルールはここへ集約する。

## Repo Context

- このリポジトリは DevKit のセットアップ/更新スクリプト、skills、templates を管理する
- v7 の配布 skill は `plugins/devkit/skills/dig/`、`plugins/devkit/skills/improve-skill/`、`plugins/devkit/skills/setup/`、`plugins/devkit/skills/refactor/`、`plugins/devkit/skills/memory-review/`、`plugins/devkit/skills/goal-prompt/`、`plugins/devkit/skills/handoff/` の 7 つとする
- statusline 配布物は `plugins/devkit/statusline/` に同梱し、適用は setup workflow から行う
- Codex 側の配布は plugin marketplace を正本にし、独自の skill 同期経路は復活させない
- 振る舞いを変える変更では、コードだけでなく対応するドキュメントも同じ変更で揃える
- ルートの正規ファイル名は `AGENTS.md` と `CLAUDE.md` を使う

## Workflow

開発フローの基本形は次のとおり。実装オーケストレーションのスキル実体は `plugins/devkit/skills/dig/SKILL.md`。

1. 深掘り: 要求が曖昧なら、未知を棚卸しして影響が大きい未知だけ質問し、ユーザーの要求(目的・成功条件・非対象)を聞き出す。小さい未知は仮定を明示して進める(質問ポリシーの正本は dig スキルの SKILL.md)
2. 計画: コードベースを調査し、decision-complete な計画を作る
3. 承認: 計画レビュー・実装・diff レビューの backend を選択し、計画レビュー(skip 可)を経た計画をユーザーに提示して、承認を得てから実装に進む
4. 実装: 計画に沿って差分を作る。計画から逸脱する場合は理由・リスク・要確認点を記録する(実装を外部 backend に委譲する場合は dig スキルの契約に従う)
5. 自レビュー: diff 全文を計画と突き合わせ、テスト・リンタを実行する
6. 修正ループ: 指摘が解消するまで修正を繰り返す
7. 報告とコミット: 変更サマリーを報告し、コミット・プッシュはユーザー指示に従う

## Maintenance Rules

- ルートのエージェント向けルールを変更するときは、まずこのファイルを更新する
- スクリプトの仕様変更時は `README.md` と `plugins/devkit/scripts/README.md` を同期する
- スキル契約を変える場合は対応する `SKILL.md` と必要な templates / scripts を同期する
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

### タスクリスト連動

- Claude 親: TaskCreate / TaskUpdate が利用可能なら、workflow の step を登録し開始時 `in_progress`・完了時 `completed` に更新する。利用不可なら省略してよい
- Codex 親: 組み込み plan 機能または通常の進捗報告で同等の進捗提示を行う

### 委譲・長時間ジョブの進捗可視化

- 委譲ジョブ・長時間ジョブは 1 ジョブ = 1 タスクとしてタスクリストへ登録し、開始・完了で状態を更新する(親 step のタスクに blockedBy で紐付ける)
- Claude 親: 外部 CLI への委譲(codex exec / cursor-agent 等)は Bash の `run_in_background` で起動する。ジョブは UI に実行中タスクとして表示され、完了時に親へ自動通知が届く。完了待ちは通知駆動とし、定期ハートビートの逐次表示は行わない
- Claude 親の停滞検知: 待機中は数分おき(目安 2〜5 分)に TaskOutput またはジョブのログファイルで出力増分を確認し、増分ゼロが続く場合のみ停滞の継続時間と推定原因(内部レビュー待ち / 長考 / ハング)をユーザーへ報告する
- Claude サブエージェント委譲(Agent)は元々バックグラウンド実行 + 完了自動通知のため追加の起動処置は不要。停滞検知の考え方は同じ
- Codex 親: run_in_background / TaskOutput は使えない。`wait_agent` で黙って待たず、定期的に進捗をユーザーへ提示する
- 実体の進捗確認は `git status` / `git diff` で行う(resume を進捗確認に使わない)
- codex exec をバックグラウンド起動する場合も stdin を `< /dev/null` で閉じる

### codex exec 実行形

```bash
codex -a never exec -c model_reasoning_effort="<effort>" "<内容>" < /dev/null
```

- モデルは `-m` で焼き込まず、config 既定（最新モデル）に従う
- 非対話実行では必ず末尾に `< /dev/null` を付ける（stdin 待ちで無期限ハングするため）
- `-a never` などの top-level オプションは `exec` より前に置く

## Key Paths

- `README.md`: リポジトリ全体の導入・運用説明
- `plugins/devkit/scripts/`: setup / update 系スクリプト
- `plugins/devkit/skills/dig/SKILL.md`: 深掘り・計画・実装委譲 workflow の正本
- `plugins/devkit/skills/improve-skill/SKILL.md`: skill 改善 workflow の正本
- `plugins/devkit/skills/setup/SKILL.md`: 対象リポジトリへの DevKit ルール同期・thought-db 接続同期・statusline 適用 workflow の正本
- `plugins/devkit/skills/refactor/SKILL.md`: 負債棚卸し・優先順位付け・計画作成 workflow の正本
- `plugins/devkit/skills/memory-review/SKILL.md`: AI メモリ棚卸し・前提監査 workflow の正本
- `plugins/devkit/skills/goal-prompt/SKILL.md`: 自律実行・ループ・大タスク完走向けゴールプロンプト作成 workflow の正本
- `plugins/devkit/skills/handoff/SKILL.md`: セッション引継ぎドキュメント書き出し workflow の正本
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
codex -a never exec -c model_reasoning_effort="medium" "<相談内容>" < /dev/null
```

- 実行形は「スキル共通契約 > codex exec 実行形」に従う（モデルは `-m` で焼き込まず config 既定に従う）
- 技術的判断に迷った場合、設計の妥当性を確認したい場合に使用する
- 結果は参考意見として扱い、最終判断は親エージェントが行う
