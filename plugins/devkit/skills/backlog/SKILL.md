---
name: "backlog"
description: "残課題を横断的に棚卸しし、鮮度を判定して次アクションを提示する read-only スキル。「残りの作業は?」「残課題を棚卸しして」「やり残しを確認して」「/backlog」で起動"
argument-hint: "[topic]"
allowed-tools: ["Read", "Grep", "Glob", "Bash", "AskUserQuestion", "request_user_input", "TaskCreate", "TaskUpdate", "Skill"]
---

# /backlog - 残課題の横断棚卸し + dig 引き継ぎ

repo に散在する残課題を read-only で統合・鮮度判定し、次アクションまたは dig 用草案を提示する。ファイル変更や実装は行わない。

## 対象

$ARGUMENTS

## ハーネス・進捗

| 判定 | 質問 |
|---|---|
| `AskUserQuestion` が使える Claude 親 | AskUserQuestion |
| それがなく `spawn_agent` が使える Codex 親 | plan mode は `request_user_input`、通常 mode は選択肢付き自由文 |
| 判定不能 | 選択肢付き自由文 |

`request_user_input` は判定キーにしない。step 1-5 は利用可能なタスクリストまたは通常の進捗報告で開始・完了を示す。委譲・長時間ジョブは個別タスク化し、実体は `git status` / `git diff` で確認して、停滞時だけ状況を報告する。タスクリストはセッション内進捗であり、残課題の正本ではない。

## read-only 契約と境界

- allowed-tools に Write / Edit を含めず、生成・編集・format・lint・test・依存更新を行わない。Bash は `git`、`rg`、`gh` 等の読み取りだけに使う。
- 結果はチャットへ提示し、ダッシュボードやレポートをファイルへ保存しない。
- backlog は handoff / plan / goal run / git / GitHub に残る作業を読む。コード負債と TODO / FIXME は refactor、handoff の新規作成・更新は handoff が担う。

## フロー

### 1. スコープ確認

現在の repo を既定とし、`$ARGUMENTS` はトピック・期間・ブランチ等の絞り込みに使う。結果を大きく左右する未知だけ質問し、対象 / 除外 / 仮定を示す。

### 2. 情報源スキャン

存在しない情報源や該当ゼロも黙って省略しない。

| 情報源 | 確認対象 |
|---|---|
| `.claude/handoff/*.md` | 残作業、次アクション、保留 |
| `.claude/plans/*.md` | 未実装、未承認、未検証 |
| `.claude/goal-runs/*.md` | 未検収、停止条件、残作業 |
| git | 未コミット、upstream 差分、未 push commit、未マージブランチ、`git stash list` |
| GitHub | open PR、未解決レビューコメント、失敗中の CI |

GitHub は `gh` が利用・認証可能な場合だけ確認し、不可なら「gh 不在のため未確認」等の理由を記す。各候補には根拠パス、branch、PR、または確認コマンドを付ける。

### 3. 統合と鮮度判定

同じ作業を統合し、日付、commit、branch、PR 更新時刻、CI 状態を比較する。古い記述だけで未完了と断定しない。

| 状態 | 判断基準 |
|---|---|
| 未完了 | 現在差分、open PR、失敗中 CI、明示された残作業など新しい根拠がある |
| 要確認 | 根拠が古い、完了済みの可能性、矛盾、外部状態の取得不能がある |
| 完了済み | merge、検収、レビュー解消など、より新しい完了根拠がある |

完了の可能性が高い項目は未完了へ混ぜず、確認方法付きの要確認にする。完了済みは重複提案を防ぐ根拠として短く残す。

### 4. ダッシュボード提示

第 1 層「結論 + 推奨次アクション(3 件以内)」を先頭提示し、第 2 層に詳細を置く。第 1 層は次の 7 カテゴリを持つ。

1. 何を / なぜ
2. 判断してほしい点(推奨付き)
3. 既定からの逸脱・採用した仮定
4. 後戻りしにくい操作・外部影響
5. backend 表(計画レビュー / 実装 / diff レビューはすべて「適用なし」)
6. 検証
7. 独立レビュー状態(`適用なし`、backend も `適用なし`)

一般形の状態は `実施済み(指摘 N 件反映)` / `skip(理由)` / `適用なし`。詳細は未コミット / branch・未 push / PR・レビュー / CI / handoff・plan・goal run / 要確認に分け、空欄も「該当なし」または「未確認」とする。各項目へ状態・根拠・具体的な次アクションを付ける。

### 5. dig への引き継ぎで終了

ユーザーが実装対象を選んだ場合だけ、目的 / write_scope / 実装手順 / 検証 / 非対象 / backlog 由来の根拠を持つ `dig の step 2` 計画草案へ整形する。詳細契約は `plugins/devkit/skills/dig/SKILL.md` を参照し、backlog は実装・backend 選択・レビューを行わない。利用可能なら Skill ツールで dig を起動し、それ以外は `$dig` または `/dig` へ渡すよう案内する。ダッシュボードのみで終了してよい。

秘密情報、資格情報、トークン、個人情報は転記しない。取得不能は「なし」ではなく「未確認」と報告する。
