---
name: "memory-review"
description: "AI メモリ棚卸し・前提監査。CLAUDE.md / AGENTS.md / rules / commands / skills / memory files / auto-memory を監査し、古い前提・矛盾・危険な自動化ルールを人間レビュー可能な形で整理する。「メモリを棚卸しして」「メモリ監査して」「前提を点検して」「/memory-review」で起動"
argument-hint: "[scope]"
allowed-tools: ["Read", "Grep", "Glob", "Bash", "AskUserQuestion", "request_user_input", "TaskCreate", "TaskUpdate", "Skill", "Agent", "spawn_agent", "wait_agent", "Write", "Edit"]
---

# /memory-review - AI メモリ棚卸し・前提監査

親エージェント = スコープ確認・read-only 監査・分類・監査レポート作成・承認済み軽微修正の適用・dig への引き継ぎ。監査は read-only とし、書き込みは「レポート保存」と「承認済み軽微修正の適用」の 2 つに限定する。自動削除・commit・push は行わない。

## 対象

$ARGUMENTS

## ハーネス判定

正本は devkit リポジトリの `AGENTS.md`「スキル共通契約」。この SKILL.md は Claude 親 / Codex 親の二層構成で実行する。要点:

- `AskUserQuestion` が使える -> Claude 親。
- なければ `spawn_agent` が使える -> Codex 親。
- どちらでもない -> 判定不能として扱い、選択肢を箇条書きで提示して自由文回答を求める。
- `request_user_input` は plan mode 依存で不安定なため、判定キーに使わない(Codex 親 plan mode の質問手段としてのみ使う)。

## タスクリスト連動

正本は devkit リポジトリの `AGENTS.md`「スキル共通契約 > タスクリスト連動」。memory-review 開始時に step 1-7 をタスクリストへ登録し、各 step の開始時に `in_progress`、完了時に `completed` へ更新する(Claude 親: TaskCreate / TaskUpdate、利用不可なら省略可。Codex 親: 組み込み plan 機能または通常の進捗報告で同等の進捗提示)。

## 監査対象と除外

対象(repo 内):

- `CLAUDE.md`、`AGENTS.md`、`README`。
- `docs/` 配下の設計方針、運用手順、TODO、進捗メモ。
- `.claude/rules`、`.claude/commands`、`.claude/skills`。
- `.claude/memory/` の `decisions.md`、`patterns.md`、`archive`。
- プロジェクト固有の開発ルール、テスト・lint・format・build・review の実行手順、過去の判断履歴。

対象(repo 外の AI 記憶ファイル、既定で含める):

- Claude auto-memory: 対象 repo の絶対パスの `/` を `-` に置換した slug で `~/.claude/projects/<slug>/memory/` を探す。例: `/Users/x/repos/foo` -> `~/.claude/projects/-Users-x-repos-foo/memory/` の `MEMORY.md` と個別メモリ。存在しなければ「auto-memory なし」としてレポートに記録する。
- Codex メモリ: `~/.codex/memories/MEMORY.md` と `~/.codex/AGENTS.md` が存在する場合に確認する。対象 repo に言及している記述だけを監査対象とし、他プロジェクトの記述には触れない。
- 思想 DB: `~/repos/thought-db/` が存在する場合、`overview.md`(総論)・`topics/`(個別 DB)・`changelog.md`(更新履歴) を監査対象に含める(古い前提・矛盾・更新履歴とのペア漏れの検出)。存在しなければ「思想 DB なし」として記録する。思想 DB は非公開前提のため、内容をレポートへ転記するときは公開範囲に注意する。

除外(既定で除外し、ユーザーが明示的に指定した場合のみ対象に加える):

- `.claude/state`、`.claude/sessions`、`.claude/logs`、`~/.codex/sessions`。
- transcript、キャッシュ、生成物、ビルド成果物。
- 過去セッションの会話ログは読まない。判断品質に影響するのは毎セッション注入される記憶ファイルの方であり、セッションログは範囲が広く、秘密情報転記や文脈の誤採用リスクが高いため。

## 書き込み契約

- step 1-4(スコープ確認・正本特定・監査・分類)は read-only。Bash は `git log`、`git ls-files`、`rg` 相当の読み取り用途だけに使う。
- step 5 は、保存先をユーザーに確認した後の監査レポートファイルの新規作成のみ Write 可。`docs/reviews/` が存在しない場合は、レポート保存のためのディレクトリ作成だけ許可する。監査対象ファイルには触らない。
- step 6 は、ユーザーが承認した軽微修正の適用のみ Edit / Write 可。
- 上記以外の書き込み、メモリの削除・上書き・移動・commit・push を行わない。delete candidate は提示のみで、自動削除しない。
- 軽微修正でも、差分の意図、対象ファイル、戻し方を提示して承認を得てから適用する。

## 基本方針

1. メモリは正本ではなく判断補助として扱う。
2. 正本は README、設計ドキュメント、テスト、CI、実装、最新の意思決定記録から判断する。
3. メモリを勝手に削除しない。削除候補は delete candidate として提示する。
4. すべての項目を keep / update / merge / move / archive / delete candidate / needs human decision に分類する。
5. 影響小の不明点は仮定を明示して進め、危険な不明点だけ人間確認する。
6. CLAUDE.md や AGENTS.md に詰め込みすぎず、必要なら Skill、rules、commands、memory files へ分離する。
7. 正本と参照先を明確化し、曖昧な「前回どおり」「いつもの」だけで運用しない。
8. 秘密情報、資格情報、個人情報はレポートへ転記せず、存在とリスクだけを指摘する。
9. 自動化ルールは破壊的操作、外部送信、権限昇格、commit / push を特に警戒して確認する。
10. 最終書換は差分提案と承認後に限る。大きい変更は memory-review 内で抱えず dig へ引き継ぐ。

## フロー

### 1. スコープ確認

最初に選択肢付き質問で、監査範囲と優先軸を確定する。1 ラウンド最大 4 問とし、回答不足があれば追加で確認する。Codex 親 plan mode で `request_user_input` を使う場合は 1 呼び出し最大 3 問に分ける。

- 対象範囲: repo 全体 / 指定ディレクトリ / メモリ系のみ
- repo 外記憶: auto-memory を含める(既定) / repo 内だけ / Codex メモリだけ追加
- 除外対象: 既定除外のまま / セッションログを明示 opt-in / 生成物も確認
- 監査のきっかけ: 同じ間違いの繰り返し / 前提変更 / 肥大化 / 定期点検

ハーネス別の質問手段:

- Claude 親: AskUserQuestion を使う。
- Codex 親 plan mode: `request_user_input` を使う。
- Codex 親通常 mode / 判定不能: 選択肢を箇条書きで提示して自由文回答を求める。

締めに、目的 / 成功条件 / 非対象 / 採用した仮定を短く提示して認識を合わせる。

### 2. 正本特定 + 対象読み込み

親が read-only で対象ファイル一覧を列挙し、現在の正本を特定する。正本候補は README、設計ドキュメント、テスト、CI 設定、実装、最新の意思決定記録を優先する。メモリと正本を突き合わせる準備として、対象ごとに「何の判断を補助している記憶か」を短くラベル付けする。

Claude auto-memory は、対象 repo の絶対パスから導出した slug で `~/.claude/projects/<slug>/memory/` を探す。Codex メモリは `~/.codex/memories/MEMORY.md` と `~/.codex/AGENTS.md` から対象 repo に言及する行だけを抽出する。どちらも存在しない場合は、欠落を問題扱いせず「対象なし」と記録する。

### 3. 監査

7 観点で確認し、根拠はできる限り `file:line` 形式で示す。行番号を取れない統計値はコマンド名と集計条件を明記する。

- 矛盾: 正本同士、正本とメモリ、メモリ同士、現在の実装と古い運用記述が食い違っていないか。
- 古い前提: 旧バージョン、退役済みツール、古いブランチ、廃止した配布経路、過去の一時対応が残っていないか。
- 曖昧な指示: 主語、対象範囲、成功条件、禁止事項、承認条件が曖昧で、AI が勝手に補完しそうな記述がないか。
- 重複: 同じルールが複数箇所にあり、片方だけ更新されるリスクがないか。
- 危険な自動化: 削除、上書き、外部送信、権限昇格、課金、commit、push、公開操作を自動実行する指示が安全確認なしで残っていないか。
- 参照設計: 正本、派生メモリ、Skill、rules、commands の役割が分かれ、参照先が追えるか。
- テスト・検証: 重要ルールが lint / format / validation / test / CI で検出可能か。prose だけで守らせている危険な契約がないか。

サブエージェントが使え、対象が大きい場合は 4 役(監査役 / 矛盾検出役 / 安全性レビュー役 / 修正案作成役)に分割する。Claude 親は Agent、Codex 親は spawn_agent / wait_agent を使い、いずれも read-only 指示(監査対象の読み取りのみ、ファイル変更禁止)を明記して委譲する。小規模なら親単独で実施する。最終判断は親が統合し、重複のない指摘にする。

委譲時は 1 役 = 1 タスクとしてタスクリストへ登録し、開始・完了で状態を更新する。Claude 親の Agent 委譲はバックグラウンド実行され完了時に自動通知が届くため通知駆動で回収し、長時間出力増分がない場合のみ停滞状況(継続時間・推定原因)を報告する。Codex 親は `wait_agent` で黙って待たず定期的に進捗を提示する。正本は devkit リポジトリの `AGENTS.md`「スキル共通契約 > 委譲・長時間ジョブの進捗可視化」。

監査結果のメモ形式:

```markdown
### 指摘: <短い名前>
- 根拠: `path/to/file.ext:123` ...
- 観点: 矛盾 / 古い前提 / 曖昧な指示 / 重複 / 危険な自動化 / 参照設計 / テスト・検証
- 影響: ...
- 推奨: ...
```

### 4. 分類 + 影響度

各項目を 7 分類し、影響度 3 段階を付ける。

分類:

- keep: 現在も正しく、残す。
- update: 内容は必要だが、前提や文言を更新する。
- merge: 重複を統合する。
- move: 置き場所を移す。例: CLAUDE.md から rules / commands / skills / memory files へ。
- archive: 現行判断には不要だが履歴として保管する。
- delete candidate: 削除候補として提示する。自動削除はしない。
- needs human decision: 正本だけでは判断できず、人間の意思決定が必要。

影響度:

- 高: 誤実装、情報漏えい、破壊的操作、レビュー漏れにつながる。
- 中: 判断ブレ、手戻り、テスト漏れにつながる。
- 低: 重複、軽微な古さ、参照性低下にとどまる。

### 5. 監査レポート出力

監査レポートはチャットに全文提示し、ユーザーに保存先を確認した後、対象 repo の `docs/reviews/YYYY-MM-DD-memory-review.md` に新規保存する。`docs/reviews/` がなければ作成する。既存ファイルがある場合は上書きせず、`YYYY-MM-DD-memory-review-2.md` のように連番を付ける。

出力形式は 10 セクションに固定する。

```markdown
# memory-review: <対象>

## 1. 結論(3件以内)
- ...

## 2. 全体評価
| 観点 | 評価 | 根拠 |
|------|------|------|
| 最新性 | ... | ... |
| 一貫性 | ... | ... |
| 安全性 | ... | ... |
| 参照しやすさ | ... | ... |
| CLAUDE.md 肥大化リスク | ... | ... |
| AI 勝手判断リスク | ... | ... |

## 3. 重要な問題点
| 問題 | 該当箇所 | なぜ問題か | 推奨対応 | 自動修正可否 | 人間確認要否 |
|------|----------|------------|----------|--------------|--------------|
| ... | `path:line` | ... | ... | 可/不可 | 要/不要 |

## 4. 分類結果
| 分類 | 項目 | 根拠 | 影響度 |
|------|------|------|--------|
| keep/update/merge/move/archive/delete candidate/needs human decision | ... | ... | 高/中/低 |

## 5. 矛盾リスト
| ペア | A | B | 判断 |
|------|---|---|------|
| ... | `path:line` | `path:line` | ... |

## 6. 古い前提リスト
| 前提 | 根拠 | 現在の正本 | 推奨 |
|------|------|------------|------|
| ... | ... | ... | ... |

## 7. AI が勝手に決めると危険な点
### Known unknowns
- ...

### Unknown unknowns
- ...

## 8. 修正案(文章レベル)
- ...

## 9. 推奨する配置
| 配置先 | 内容 | 理由 |
|--------|------|------|
| CLAUDE.md / AGENTS.md / rules / commands / skills / memory files | ... | ... |

## 10. 次アクション(3つ以内)
1. ...
```

### 6. 修正の承認と適用

レポート提示後、選択肢付き質問で対応方針を確認する。

- 全て提示のみで終了
- 軽微修正のみ適用
- 軽微適用 + 大きい変更を dig へ引き継ぎ

承認された軽微修正だけを適用する。軽微修正は、文言修正、重複削除、参照先追記など単一ファイル内で完結する差分に限る。構成変更を伴う大きい修正、ファイル分割、移動、スキル化、実装変更は memory-review で実行しない。

大きい変更は、refactor と同じ「dig step 2 計画草案」形式に整形して dig へ引き継ぐ。詳細な実行契約は `plugins/devkit/skills/dig/SKILL.md` を参照する。

引き継ぎ形式:

```markdown
## dig step 2 計画草案

### 目的
...

### write_scope
- ...

### 実装手順
1. ...

### 検証
- ...

### 非対象
- ...

### memory-review 由来の根拠
- `path/to/file.ext:123` ...
```

ハーネス別の終了動作:

- Claude 親: Skill ツールが使える場合は dig を起動し、上記の計画草案を渡す。利用不可なら、ユーザーに `/dig` で計画草案を実行するよう案内する。
- Codex 親: `$dig` を起動し、計画草案を渡すよう案内する。

### 7. 完了報告

適用した修正、保存したレポートパス、dig へ渡した項目、残る needs human decision を報告する。commit / push はユーザー指示時のみ行う。

## 注意

- メモリの自動削除、上書き、移動を行わない。delete candidate は提示のみ。
- 秘密情報をレポートに転記しない。資格情報、トークン、住所、個人情報は存在の指摘とリスクだけを書く。
- auto-memory は repo 外のため git 管理外であることをレポートに明記する。
- 監査中に発見した危険な自動化ルールは実行しない。
- codex exec コマンド例を書く場合は、非対話実行でハングしないよう必ず末尾に `< /dev/null` を付ける。
