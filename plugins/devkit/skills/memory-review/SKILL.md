---
name: "memory-review"
description: "AI メモリ棚卸し・前提監査。CLAUDE.md / AGENTS.md / rules / commands / skills / memory files / auto-memory を監査し、古い前提・矛盾・危険な自動化ルールを人間レビュー可能な形で整理する。「メモリを棚卸しして」「メモリ監査して」「前提を点検して」「/memory-review」で起動"
argument-hint: "[scope]"
allowed-tools: ["Read", "Grep", "Glob", "Bash", "AskUserQuestion", "request_user_input", "TaskCreate", "TaskUpdate", "TaskOutput", "Skill", "Agent", "spawn_agent", "wait_agent", "Write", "Edit"]
---

# /memory-review - AI メモリ棚卸し・前提監査

メモリを正本ではなく判断補助として監査し、レポートを書き出す。監査は read-only だが、ユーザー承認後は軽微修正も適用できる。自動削除・commit・push はしない。

## 対象

$ARGUMENTS

## ハーネス判定

`request_user_input` は判定キーに使わない。

| 判定 | 質問・承認 | 委譲 |
|---|---|---|
| `AskUserQuestion` が使える Claude 親 | `AskUserQuestion` | Agent |
| 上記がなく `spawn_agent` が使える Codex 親 | plan mode は `request_user_input`、通常 mode は選択肢 + 自由文 | `spawn_agent` / `wait_agent` |
| 判定不能 | 選択肢 + 自由文 | 親が実施 |

step 1-7 をタスク化する。委譲も 1 ジョブ = 1 タスクとし、Codex 親は待機中も進捗を示す。停滞時だけ継続時間と推定原因を報告する。

## 範囲と不変条件

- repo 内: `CLAUDE.md` / `AGENTS.md` / README / docs、rules / commands / skills / memory files、実装・テスト・CI・意思決定記録。
- repo 外(既定で含む): Claude auto-memory、対象 repo に言及する `~/.codex/memories/MEMORY.md` と `~/.codex/AGENTS.md`、存在する場合の `~/repos/thought-db/`。思想 DB の非公開内容は公開レポートへ転記しない。
- Claude auto-memory は repo 絶対パスの `/` を `-` にした slug の `~/.claude/projects/<slug>/memory/`。欠落は「auto-memory なし」と記録する。
- auto-memory は repo 外かつ git 管理外であることをレポートに明記する。
- 既定除外: `.claude/state` / `.claude/sessions` / `.claude/logs` / `~/.codex/sessions`、transcript、キャッシュ、生成物、ビルド成果物。過去セッションの会話ログは読まない。明示 opt-in 時だけ加える。
- 正本は README、設計文書、テスト、CI、実装、最新の意思決定記録から判断する。秘密情報・資格情報・個人情報は値を転記せず、存在とリスクだけを示す。
- 全項目を `keep / update / merge / move / archive / delete candidate / needs human decision` のいずれか、影響度を `高 / 中 / 低` のいずれかに分類する。`delete candidate` は提示のみ。

## 書き込み契約

| step | 許可 |
|---|---|
| 1-4 | read-only |
| 5 | 保存先確認後、監査レポートを新規作成。必要なら `docs/reviews/` を作成 |
| 6 | 差分の意図・対象・戻し方を提示し、承認された軽微修正だけ Edit / Write |
| 7 | 報告のみ |

メモリの削除・上書き・移動は行わない。大きい変更は適用せず dig へ渡す。

## 監査対象 × 観点

各セルを必要な範囲で確認し、根拠は `file:line`、行番号を出せない集計はコマンドと条件で示す。大規模監査は表の役割を 4 役(監査役 / 矛盾検出役 / 安全性レビュー役 / 修正案作成役)へ read-only 委譲できる。小規模なら親が実施し、親が重複を除いて統合する。

| 対象 | 主な観点 |
|---|---|
| `CLAUDE.md` / `AGENTS.md` / README / docs | 矛盾、古い前提、曖昧な指示、重複、正本と参照先、肥大化 |
| rules / commands / skills | 起動条件、役割重複、禁止・承認条件、危険な自動化、検証可能性 |
| memory files / auto-memory / Codex メモリ / 思想 DB | 正本との差、鮮度、対象 repo 境界、重複、履歴とのペア漏れ、秘密情報 |
| 実装 / test / lint / CI | 文書との一致、重要契約を決定論的に検出できるか |
| 現在セッション | 記憶候補抽出: 修正された好み、反復する運用、コードから導出不能な前提。一度きりのログ・原文で足りる情報・実行中状態は除外 |

危険な自動化では削除、上書き、外部送信、権限昇格、課金、commit、push、公開を重点確認する。記憶候補は report-only とし、保存・注入は step 6 の承認対象にする。

## フロー

### 1. スコープ確認

選択肢付き質問で、対象範囲、repo 外記憶、既定除外への opt-in、監査のきっかけを確定する。影響の小さい不足は仮定を明示し、危険な不足だけ質問する。目的 / 成功条件 / 非対象 / 仮定を短く合意する。

### 2. 正本特定 + 対象読み込み

対象一覧と正本を read-only で特定し、各記憶が補助する判断をラベル付けする。repo 外メモリは対象 repo に関係する記述だけ扱い、欠落は問題にしない。

### 3. 監査

「監査対象 × 観点」表に従う。指摘には短い名前、根拠、観点、影響、推奨を持たせる。

### 4. 分類 + 影響度

定義済みの 7 分類と 3 影響度を付ける。正本だけで確定できない事項は `needs human decision` とする。

### 5. 監査レポート出力

チャットへ全文提示後、保存先を確認し、既存ファイルを上書きせず `docs/reviews/YYYY-MM-DD-memory-review.md`(重複時は連番)へ保存する。

第 1 層の `## 1. 結論(3件以内)` だけで対応判断できるよう、次の 7 カテゴリを残す。

1. 何を / なぜ
2. 判断してほしい点(推奨付き、最大 3 件。なければ「なし」)
3. 既定からの逸脱・仮定(なければ「既定どおり」)
4. 後戻りしにくい操作・外部影響(なければ「なし」)
5. backend 表(計画レビュー / 実装 / diff レビューは `適用なし`)
6. 検証(採用条件を 1 行)
7. 独立レビュー状態(`実施済み(指摘 N 件反映)` / `skip(理由)` / `適用なし`。本レポートは backend とも `適用なし`)

レポート全体は次の 11 見出しを順に使う。必要な表の列は括弧内を満たせばよい。

## 1. 結論(3件以内)
## 2. 全体評価
## 3. 重要な問題点
## 4. 分類結果
## 5. 矛盾リスト
## 6. 古い前提リスト
## 7. AI が勝手に決めると危険な点
## 8. 修正案(文章レベル)
## 9. 推奨する配置
## 10. 記憶候補(report-only)
## 11. 次アクション(3つ以内)

全体評価は最新性 / 一貫性 / 安全性 / 参照しやすさ / CLAUDE.md 肥大化リスク / AI 勝手判断リスクを含む。問題点は根拠・推奨・自動修正可否・人間確認要否、分類結果は分類・根拠・影響度、危険な点は Known unknowns / Unknown unknowns、記憶候補は現在セッションの根拠と未承認状態を示す。

### 6. 修正の承認と適用

`提示のみ / 軽微修正のみ / 軽微修正 + 大きい変更を dig へ引き継ぎ` から確認する。軽微修正は文言、重複、参照先など単一ファイル内で完結する差分だけ。構成変更、分割・移動、スキル化、実装変更は `plugins/devkit/skills/dig/SKILL.md` 用の `dig step 2 計画草案`(目的 / write_scope / 実装手順 / 検証 / 非対象 / 根拠)へ整形する。Claude 親は Skill が使えれば起動し、Codex 親は `$dig` 起動を案内する。

### 7. 完了報告

適用した修正、保存したレポートパス、dig へ渡した項目、残る `needs human decision` を報告する。危険な自動化ルールは監査中に実行しない。commit / push はユーザー明示時のみ。codex exec の非対話コマンド例を書く場合は末尾に `< /dev/null` を付ける。
