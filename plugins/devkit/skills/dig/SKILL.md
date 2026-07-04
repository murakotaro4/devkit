---
name: "dig"
description: "要求の深掘りと実装オーケストレーション。親 Claude が深掘りインタビュー・計画・レビューを担当し、実装は backend(codex exec または Claude サブエージェント)に委譲する。「深掘りして」「/dig」「実装して」「Codexに実装させて」で起動"
argument-hint: "[task]"
allowed-tools: ["AskUserQuestion", "ExitPlanMode", "Bash", "Read", "Grep", "Glob", "Agent"]
---

# /dig - 深掘り + 実装委譲オーケストレーション

親 Claude = 深掘り・調査・計画・diff レビュー・テスト・報告。backend = 実装のみ(commit 禁止)。

## タスク

$ARGUMENTS

## フロー

### 1. 深掘りインタビュー(親)

AskUserQuestion を繰り返し、ユーザーの**要求**を聞き出す。

- 1 ラウンド最大 4 問、必ず選択肢付きで聞く
- 聞くのは要求そのもの: 目的、成功条件、非対象、優先度、ユーザーの好み
- 実装方式・技術選定の細部はユーザーに聞かず親が判断する。判断が要求に影響する場合だけ、推奨付きの選択肢で確認する
- 固定ラウンド数はない。追加の質問が要求を変えなくなったと判断するまで深掘りする
- 締めに要件サマリー(目的 / 成功条件 / 非対象)を提示して認識を合わせる

### 2. 調査 + 計画(親)

コードベースを調査し、decision-complete な計画を作る。計画に必ず含める:

- write_scope: 変更するファイルの一覧
- 各ファイルの具体的な変更内容
- 検証コマンド(テスト・リンタ)
- 非対象(やらないこと)

### 3. 計画承認

plan mode 中なら ExitPlanMode で承認を得る。通常モードなら計画を提示して承認を得る。承認なしで実装に進まない。

### 4. backend 選択(AskUserQuestion 1 問)

委譲直前に選択肢で確認する:

| 選択肢 | 実行方法 |
|--------|----------|
| codex — effort 既定(推奨) | `codex exec`、モデル・effort とも `~/.codex/config.toml` の既定に従う |
| codex — effort medium | 軽いタスク向け。`-c model_reasoning_effort="medium"` を付与 |
| Claude サブエージェント — Sonnet | Agent(general-purpose, model=sonnet) |
| Claude サブエージェント — Haiku | 機械的な小変更向け。Agent(general-purpose, model=haiku) |

- codex のモデルは指定しない(config 既定=最新モデルに従う。旧モデルを `-m` で焼き込まない)
- `command -v codex` が通らない場合は Claude サブエージェントの選択肢のみ提示する

### 5. 実装委譲(backend)

計画を実装指示 1 ブロックに変換して委譲する。指示ブロックに必ず含める:
目的 / write_scope(これ以外のファイルに触らない) / 具体的な変更内容 / 受け入れ条件 / 検証コマンド / commit 禁止。

```bash
codex exec -C "<repo>" --sandbox workspace-write -a never "<実装指示>"
```

- Claude backend の場合は Agent(general-purpose、選択されたモデル)に同じ指示ブロックを渡す
- 5 分超見込みのタスクは Bash `run_in_background` で起動し、進捗は `git status` / `git diff` で確認する(resume を進捗確認に使わない)
- 調査のみの委譲は `--sandbox read-only`(ウェブ検索が必要なら `--search` を追加)

### 6. 自レビュー(親)

`git diff` を全文読み、計画と突き合わせる。プロジェクトのテスト・リンタを実行する。
変更が大きい場合は任意で `codex -a never exec review --uncommitted` のセカンドオピニオンを取ってよい。

### 7. 修正ループ

指摘があれば再委譲する:

- codex: `codex exec resume --last "<指摘と修正指示>"`
- claude: 指摘と修正指示を添えて新しいサブエージェントに委譲

終了条件: diff が計画と一致し、テストが green で、指摘がゼロ。3 周しても収束しない場合は停止してユーザーに判断を仰ぐ。

### 8. 完了報告

変更サマリー・テスト結果・残課題を報告する。commit / push はユーザー指示があった場合のみ行う(Conventional Commits、日本語)。

## 注意

- 秘密情報(`.env` / credentials / `*.pem` 等)を実装指示に含めない
- sandbox の緩和や write_scope 外の変更はユーザー確認の上でのみ行う
- backend が使えない場合は報告し、承認を得て親 Claude 実装にフォールバックする
