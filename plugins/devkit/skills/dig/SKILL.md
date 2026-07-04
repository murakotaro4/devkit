---
name: "dig"
description: "要求の深掘りと実装オーケストレーション。親 Claude が深掘りインタビュー・調査・計画・統括を担当し、計画レビュー・実装・diff レビューは選択した backend(codex exec または Claude サブエージェント)に委譲する。「深掘りして」「/dig」「実装して」「Codexに実装させて」で起動"
argument-hint: "[task]"
allowed-tools: ["AskUserQuestion", "ExitPlanMode", "Bash", "Read", "Grep", "Glob", "Agent"]
---

# /dig - 深掘り + 実装委譲オーケストレーション

親 Claude = 深掘り・調査・計画・統括・報告。計画レビュー / 実装 / diff レビューは step 3 で選択した backend に委譲する(実装 backend は commit 禁止)。

## タスク

$ARGUMENTS

## フロー

### 1. 深掘りインタビュー(親)

AskUserQuestion を繰り返し、ユーザーの**要求**(目的、成功条件、非対象、優先度、好み)を聞き出す。深掘りは未知の棚卸しとして行う: 仕様上未確定と分かっている点(known unknowns)を列挙し、既存コード・業務制約・権限・保存先・性能・例外処理の観点から見落としやすいリスク(unknown unknowns)を推定する。影響が大きい未知だけを質問し、小さい未知は仮定を明示して進める。

- 必ず聞く: データ構造、既存互換性、外部連携、保存・ログ、権限、テスト合否基準、UI フロー、業務判断、後戻りが大きい設計判断
- 仮定して進める: 命名、軽微な文言、内部実装の細部。採用した仮定は計画に明示する
- 1 ラウンド最大 4 問、必ず選択肢付きで聞く。設計判断を聞く場合は親の推奨を付ける
- 固定ラウンド数はない。「必ず聞く」に該当する未知が残らなくなるまで深掘りする
- 締めに要件サマリー(目的 / 成功条件 / 非対象 / 採用した仮定)を提示して認識を合わせる

### 2. 調査 + 計画(親)

コードベースを調査し、decision-complete な計画を作る。計画に必ず含める:

- write_scope: 変更するファイルの一覧
- 各ファイルの具体的な変更内容
- 検証コマンド(テスト・リンタ)
- 非対象(やらないこと)
- 計画レビュー / 実装 / diff レビューそれぞれの backend / モデル(step 3 の選択後に計画へ追記し、承認前に確定させる)

### 3. backend 選択(AskUserQuestion 1 ラウンド 3 問)

計画承認の前に、計画レビュー用 / 実装用 / diff レビュー用の backend を選択肢で確認し、結果を計画に明記する。親はタスク規模に応じた推奨を各問 1 つ付ける(effort の目安: 基本は xhigh 寄り、簡単・機械的な作業は high / medium に落とす)。

実装 backend:

| 選択肢 | 実行方法 |
|--------|----------|
| codex — effort xhigh | `codex exec` + `-c model_reasoning_effort="xhigh"`。設計を含む重めの実装 |
| codex — effort high | 標準的な実装 |
| codex — effort medium | 軽い機械的変更 |
| Claude サブエージェント — Sonnet | Agent(general-purpose, model=sonnet)。世代非依存 alias で常に最新 Sonnet |

計画レビュー / diff レビュー backend(選択肢は共用。計画レビューの実行方法は step 4、diff レビューは step 7 を参照):

| 選択肢 | diff レビューの実行方法 |
|--------|----------|
| codex review — effort xhigh | `codex -a never exec -c model_reasoning_effort="xhigh" review --uncommitted`。重い変更・設計変更向け |
| codex review — effort high | 標準的なレビュー |
| Claude サブエージェント — Opus | Agent(general-purpose, model=opus)に diff と計画を渡してレビュー |
| 親のみ / スキップ | セカンドオピニオンなし。軽微な変更向け(diff レビューでリポジトリルールが独立レビュー必須の場合は提示しない) |

- codex のモデルは指定しない(config 既定=最新モデルに従う。旧モデルを `-m` で焼き込まない。ユーザー指定があるときのみ `-m` を付ける)
- `command -v codex` が通らない場合は codex の選択肢を除外し、Claude サブエージェントの選択肢のみ提示する

### 4. 計画レビュー(選択 backend)

計画全文を渡し、decision-complete か・矛盾や見落としがないかを審査させ、指摘を計画に反映してから承認に進む。「スキップ」選択時はこの step を省略してそのまま承認へ進む(軽微な計画向け)。

- codex: `codex -a never exec --sandbox read-only -c model_reasoning_effort="<選択>" "<計画レビュー指示>"`
- Claude: Agent(general-purpose、選択モデル)に計画全文と背景を渡す

### 5. 計画承認

plan mode 中なら ExitPlanMode で承認を得る。通常モードなら計画を提示して承認を得る。計画レビューを経た(skip 選択時は未実施の)、3 役の backend / モデルが明記された計画で承認を得る。承認なしで実装に進まない。

### 6. 実装委譲(backend)

計画を実装指示 1 ブロックに変換して委譲する。指示ブロックに必ず含める:
目的 / write_scope(これ以外のファイルに触らない) / 具体的な変更内容 / 受け入れ条件 / 検証コマンド / commit 禁止。

```bash
codex -a never exec -C "<repo>" --sandbox workspace-write -c model_reasoning_effort="<選択>" "<実装指示>"
```

- Claude backend の場合は Agent(general-purpose、選択されたモデル)に同じ指示ブロックを渡す
- 5 分超見込みのタスクは Bash `run_in_background` で起動し、進捗は `git status` / `git diff` で確認する(resume を進捗確認に使わない)
- 調査のみの委譲は `codex -a never exec --sandbox read-only`(ウェブ検索が必要なら `--search` を `exec` より前に置く: `codex -a never --search exec --sandbox read-only`)

### 7. 自レビュー(親)

`git diff` を全文読み、計画と突き合わせる。計画からの逸脱(write_scope 追加、方式変更など)が見つかったら、逸脱ごとに理由・リスク・要確認点を記録し、採用するか差し戻すかを親が判断する。プロジェクトのテスト・リンタを実行する。
step 3 で選択した diff レビュー backend でセカンドオピニオンを取る(「親のみ」を選択した場合は省略)。

### 8. 修正ループ

指摘があれば再委譲する:

- codex: `codex -a never exec resume --last "<指摘と修正指示>"`
- claude: 指摘と修正指示を添えて新しいサブエージェントに委譲

終了条件: diff が計画と一致し、テストが green で、指摘がゼロ。3 周しても収束しない場合は停止してユーザーに判断を仰ぐ。

### 9. 完了報告

変更サマリー・テスト結果・計画からの逸脱と採用した仮定・残課題を報告する。commit / push はユーザー指示があった場合のみ行う(Conventional Commits、日本語)。

## 注意

- 秘密情報(`.env` / credentials / `*.pem` 等)を実装指示に含めない
- sandbox の緩和や write_scope 外の変更はユーザー確認の上でのみ行う
- 実装 backend が使えない場合は報告し、承認を得て親 Claude 実装にフォールバックする。レビュー backend が使えない場合は他の選択肢を再提示する
