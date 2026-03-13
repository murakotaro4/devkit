# devkit 統一開発ワークフロー（agent team 運用契約）

この文書は全 runtime 共通の**運用契約**を定義する。原則すべてのタスクを agent team 前提で進める。軽微なタスクでも reviewer は必須とし、必要なら役割兼務で縮退する。

## 契約と強制

- この文書は人間と agent が従う共通運用契約である
- runtime ごとの hook / automation はこの契約の一部だけを機械強制してよい
- `team_shape`、`role_assignment`、`write_scope` は plan または task note に明示する運用義務とする
- 上記 3 項目は、現時点では全 runtime 共通に機械検証される前提ではない

## Workflow State Tokens

runtime-specific hook / state が phase を記録する場合、canonical token は次を使う:

- `intake_declared`
- `requirements_confirmed`
- `research_completed`
- `plan_drafted`
- `plan_review_completed`
- `implementation_completed`
- `implementation_review_completed`
- `commit_review_completed`

## Review Gate Prerequisites

- Codex CLI は標準 review gate として**推奨**する
- Codex CLI が使えない runtime / 環境でも、通常フェーズは進めてよい
- Codex CLI が使えない場合は、独立した別 agent reviewer で代替する
- `dig-codex` の Phase 5 だけは例外で fail-close を維持する

## Team Shape

| team_shape | 用途 | 最小構成 |
|-----------|------|----------|
| `micro_team` | 1 ファイル中心の小変更、軽微な文書修正、局所修正 | `Coordinator/Planner/Reviewer` + `Implementer` |
| `standard_team` | 通常の機能追加、通常の不具合修正 | `Coordinator` + `Planner` + `Implementer` + `Reviewer` |
| `expanded_team` | 中規模以上、または高リスク変更 | `Coordinator` + `Planner` + `Implementer`(2+) + `Reviewer` + (`Researcher` または追加 `Reviewer`) |

## Role Rules

- `Coordinator` は責務として常に必須。スコープ管理、役割割当、統合、昇格判断を担当する
- `Implementer` は自分の差分の唯一の承認者になれない
- 独立 reviewer とは **Implementer と別 agent** であることを意味する
- `micro_team` では `Planner` と `Reviewer` は同一 agent でよいが、`Implementer` は必ず分離する
- `standard_team` と `expanded_team` では `Planner` と `Reviewer` を分離する
- 複数 implementer がいる場合は `write_scope` を分けて plan に明記する
- 別モデル review は常時必須ではない。中規模以上または高リスク変更で昇格手段として使う
- runtime 制約で `expanded_team` の構造要件（Implementer(2+)）を満たせない場合（例: 並列実行不可で Implementer が1人に制限される場合）、ユーザー承認のうえ `standard_team` で実行してよい。承認なしでの暗黙降格は禁止

## Sizing Policy

規模判定は `変更種別` を先に見て、その後に `ファイル数` と `変更行数` で引き上げる。最終ランクは最も高いものを採用する。

### 種別による最低ランク

以下は最低でも `medium` とする:

- `shared/workflow.md`
- 共通 template
- setup / update script
- hook / gate
- skill contract
- 権限、認証、secret、migration、削除系

### 閾値

- `small`
  - 1 ファイル
  - 変更行数 30 行以内
  - 上記の `medium` 起点に当たらない
- `medium`
  - 2〜5 ファイル
  - または 31〜200 行
  - または上記の `medium` 起点に当たる
- `large`
  - 6 ファイル以上
  - または 200 行超
  - または複数サブシステムへ跨る

`Coordinator` は必要に応じてランクを引き上げてよいが、最低ランクを下げてはいけない。

## Review Gate Strategy

### 標準ゲート

| 優先度 | 手段 | 条件 |
|--------|------|------|
| 1st | `codex -a never exec review --uncommitted -m gpt-5.3-codex-spark` | Codex CLI が利用可能な場合の標準ゲート |
| 2nd | `codex -a never exec review --uncommitted -m gpt-5.4 -c 'model_reasoning_effort="medium"'` | Spark unavailable / rate limit / timeout / parse failure |
| 3rd | 独立した別 agent reviewer + ユーザー通知 | Codex CLI が unavailable または未導入の場合 |

### 昇格条件

`medium` 以上では、標準 gate に加えて**追加の review 視点**を入れる。

- `medium`
  - 追加の独立 reviewer を 1 つ入れる
  - 別モデル review は推奨だが必須ではない
- `large`
  - 追加の独立 reviewer を 1 つ以上入れる
  - 別モデル review を強く推奨する

規模に関係なく、以下では `medium` 以上として扱う:

- `shared/workflow.md`、共通 template、setup / update script の変更
- 権限、認証、secret、削除、migration を含む変更

`dig-codex` の Phase 5 は fail-close。レビュー不能時は `DIG_CODEX_PLAN_REVIEW_UNAVAILABLE`、レビュー結果が `critical>0` または `high>0` の場合は `DIG_CODEX_PLAN_REVIEW_BLOCKED` で停止する。

## 8フェーズ必須フロー

| # | フェーズ | 完了条件 |
|---|---------|----------|
| 1 | 依頼確認と体制決め | サイズ判定、`team_shape`、役割案が文書化済み |
| 2 | 要件ヒアリング | 成功条件、制約、非対象、承認が確定 |
| 3 | 調査 | コード調査、周辺異常、技術リスクが整理済み |
| 4 | 計画作成 | decision-complete な plan、役割、review 方針が完成 |
| 5 | 計画レビュー | reviewer 観点と review gate が完了 |
| 6 | 実装 | 差分作成と統合が完了 |
| 7 | 実装レビューと検証 | 実装レビュー、検証、必要な昇格 review が完了 |
| 8 | コミットとプッシュ | staging、コミット前確認、commit、push が完了 |

### Phase 1: 依頼確認と体制決め

- `Coordinator` が sizing policy で `small` / `medium` / `large` を決める
- その結果に基づいて `micro_team` / `standard_team` / `expanded_team` を決める
- `team_shape` と `role_assignment` を最初に plan または task note に書く

### Phase 2: 要件ヒアリング

- runtime に応じた質問手段を使う
  - Claude: AskUserQuestion
  - Codex Plan Mode: request_user_input
  - OpenCode: question（不可時はメッセージ質問）
- `Coordinator` または担当 interviewer が目的、成功条件、制約、非対象を固定する

### Phase 3: 調査

- `Coordinator`、`Planner`、または専任 `Researcher` がコードベース調査を行う
- 周辺で見つけた異常や追加修正候補は `Coordinator` が本スコープへ入れるか判断する

### Phase 4: 計画作成

- `Planner` は decision-complete な plan を作る
- plan には少なくとも `team_shape`、`role_assignment`、テスト方針を含める
- implementer が複数なら `write_scope` を plan に含める
- `medium` 以上なら review の昇格方法も書く

### Phase 5: 計画レビュー

- `micro_team` では `Planner=Reviewer` を許可する
- `standard_team` と `expanded_team` では `Reviewer` を `Planner` と分離する
- Codex CLI が使える場合は Spark を標準 gate にする
- Codex CLI が使えない場合は独立した別 agent reviewer で代替する

### Phase 6: 実装

- `Implementer` は自分の担当差分を作る
- implementer が複数なら `write_scope` に従って責務を分ける
- `Coordinator` が最終統合責任を持つ

### Phase 7: 実装レビューと検証

- `Reviewer` は implementer と別 agent であること
- `small` でも独立 reviewer は省略しない
- `medium` 以上では追加の review 視点を入れる

### Phase 8: コミットとプッシュ

1. `git add` でステージング
2. コミット前確認を実施
3. `git commit` + `git push`

コミットメッセージは Conventional Commits を使い、件名・本文とも日本語で書く。

## スキル連携マッピング（任意）

| フェーズ | 加速用スキル |
|---------|-------------|
| Phase 2 | /dig |
| Phase 3 | /codex-search, /deep-research |
| Phase 4-5 | /dig（計画+レビュー部分） |

## 禁止事項

- 要件確認なしの実装開始
- review gate なしの計画承認
- implementer による単独自己レビュー
- 実装レビューなしのコミット
- `Coordinator` の判断なしにスコープを拡張すること
