# Claude 5 世代のコンテキスト設計への追従（2026-07-25）

配布ドキュメント圧縮の一次記録。`/catch-up` 起点。

## 1. 契機と外部事実

きっかけは Anthropic の Thariq（[@trq212](https://x.com/trq212/status/2080710971228918066)）の投稿で、
Opus 5 のリリース告知ではなく **コンテキスト設計の原則変更** の紹介だった。

> We removed over 80% of Claude Code's system prompt for models like Claude Opus 5 and Claude Fable 5
> with no measurable loss on our coding evaluations.

一次資料: [The new rules of context engineering for Claude 5 generation models](https://claude.com/blog/the-new-rules-of-context-engineering-for-claude-5-generation-models)

| 旧 | 新 |
|---|---|
| ルールを与える | 判断に任せる |
| 例を提供する | ツールインターフェースを設計する |
| 全情報を事前提供する | 段階的開示 |
| 指示を繰り返す | 重複を排除する |
| CLAUDE.md に何でも書く | 落とし穴だけ書く |
| 単純な仕様書 | 豊富な参照形式 |

記事は CLAUDE.md を「軽量に保ち、重点は落とし穴（暗黙のルール）」、
Skills を「軽量ガイドとして機能させ、過度な制約を避ける」と述べ、
アンチパターンとして「競合する指示の共存」「システムプロンプトとツール説明の重複」
「検証手順を全部前もって盛り込む」を挙げている。

### 裏取り済みの周辺事実

| 項目 | 内容 | 出典 |
|---|---|---|
| Opus 5 | 2026-07-24 GA、model id `claude-opus-5`、1M context、effort に `xhigh` / `max` | [Anthropic](https://www.anthropic.com/news/claude-opus-5) |
| Claude モデル追従 | dig の backend は `model=sonnet` / `model=opus` の世代非依存 alias。**Opus 5 は自動適用済みで値の更新は不要** | `dig/SKILL.md` |
| `claude doctor` | CLI 2.1.220 に存在。ただし CLI 版は install health のみで、skills / CLAUDE.md の rightsize は**セッション内 `/doctor`** 側 | `claude doctor --help` |

## 2. 着手前の実測

### 圧縮対象と、それを固定していた契約テスト

| 対象 | 字数 | 行数 | テスト関数 | assertion |
|---|---:|---:|---:|---:|
| dig | 24,064 | 365 | 29 | 149 |
| repo-loop | 13,888 | 246 | 32 | 139 |
| setup | 12,126 | 209 | 22 | 151 |
| AGENTS.md | 12,121 | 219 | — | — |
| memory-review | 9,134 | 281 | 9 | 52 |
| improve-skill | 6,932 | 221 | 0 | 0 |
| commit-push | 5,798 | 134 | 7 | 9 |
| refactor | 5,241 | 172 | 7 | 61 |
| backlog | 4,773 | 142 | 8 | 45 |
| catch-up | 4,400 | 107 | 6 | 27 |
| handoff | 4,179 | 123 | 10 | 49 |
| goal-prompt | 2,960 | 105 | 9 | 25 |
| **合計** | **105,616** | **2,324** | **139** | **707** |

横断整合の `test_document_consistency.py` が別に 21 テスト / 67 assertion。

### 常時ロード層（対象外だが実測）

| 層 | 字数 | 所見 |
|---|---:|---|
| `~/.claude/CLAUDE.md` | 503 | 既に適正。変更不要 |
| 同期 `templates/rules/agents-rules.md`（他 repo 常時） | 1,487 | 適正 |
| 全 11 スキルの `description` 合計 | 2,079 | 適正 |

### pin 分析: テスト自体が冗長さを固定していた

`test_dig_skill.py` / `test_document_consistency.py` / `check_skill_surface.py` の
全文字列 literal を AST で抽出し、`dig/SKILL.md` の行と突き合わせた。

- pin 済み: **163 / 365 行（84%）**
- 未 pin の非空行: 92 行 / 4,011 字（16%）

つまり「決定論的 check に守られていない prose」は 16% しか無い。
ただし **pin の実体は `assert "<本文の一文>" in text` という文字列ミラーであり、振る舞いを強制していない**。
真の不変条件チェックは、`-m gpt-*` の値集合が `{gpt-5.6-sol}`、`model_reasoning_effort` の値集合が `{medium}`、
`codex -a never exec` を含む行の `< /dev/null` 欠落検出、`--last` / `python3 -c` の不在、
工程表セルの enum 検査など、少数にとどまる。

**結論**: テストが本文の文言をコピーしていたため、テストが冗長さを固定していた。
圧縮と同時にテストを不変条件へ寄せないと、以後の圧縮が毎回 707 assertion と衝突する。

### 横断重複についての切り分け

ハーネス判定ブロックは 11 スキル全部 + AGENTS.md に自己完結コピーされていた。
ただし **1 セッションで発動するスキルは通常 1 本なので、これはコンテキスト負荷ではない**。
ドリフト（保守）の問題であり、記事の論点とは別に扱う。今回は自己完結の構造自体は維持し、各コピーの冗長さだけを削った。

## 3. 圧縮の型

1. **近似重複の削除** — 同一規定の再掲を 1 箇所へ寄せる
2. **ハーネス別分岐の集約** — 各 step に散った Claude 親 / Codex 親 / 判定不能の展開を差分表へ
3. **コマンド literal の差分表記** — 起動形と resume 形の共通部分を 1 回だけ書く
4. **逐語手順 → 不変条件** — 実行順序の描写と場合分けの全展開を落とし、「守らないと事故る条件」だけ残す
5. **判断に委ねる** — 判断で代替できる細則を削る

1〜3 は契約を減らさない。4〜5 は契約そのものを削る。

## 4. 結果

| ファイル | 前 | 後 | 削減 |
|---|---:|---:|---:|
| dig | 24,064 | 11,231 | 53% |
| setup | 12,126 | 5,926 | 51% |
| memory-review | 9,134 | 4,246 | 53% |
| refactor | 5,241 | 2,451 | 53% |
| commit-push | 5,798 | 3,092 | 46% |
| handoff | 4,179 | 2,226 | 46% |
| backlog | 4,773 | 2,610 | 45% |
| improve-skill | 6,932 | 3,878 | 44% |
| repo-loop | 13,888 | 8,261 | 41% |
| goal-prompt | 2,960 | 1,898 | 35% |
| AGENTS.md | 12,121 | 7,935 | 34% |
| catch-up | 4,400 | 2,963 | 32% |
| **合計** | **105,616** | **56,717** | **46%** |

記事の 80% には届かない。devkit の記述には事故履歴に紐づく安全契約が相当量あり、そこは残したため。

## 5. 判断へ委ねた／削除した契約

型 4・5 で契約そのものを変えたもの。実装 backend（codex `gpt-5.6-sol` / `medium`）の自己申告に基づく。

### dig

- 統合の逐語手順（`gh pr checks`、merge queue API、`git ls-remote`、`--force-with-lease`、
  merge 方式別の `-d` / `-D`）を削除し、不変条件の箇条書きへ
- `thread_id` 抽出失敗時の「resume せず委譲失敗として報告」という逐語手順
- fetch 失敗時の警告継続、worktree 作成・基点記録の個別コマンド literal
- タスク型を 5 種類へ固定する列挙、固定ラウンド数を設けない旨の明文化
- write_scope 3 ファイル以上のツリー表記、独立 `Plan` 役の禁止細則

### repo-loop

- trigger ごとの全手順展開 → 共通フロー + 差分表
- envelope 各フィールドの逐語説明 → 必須フィールドとスキーマ検査
- ノード別逐語手順 → 選定 / scope / risk / 検証 / 公開の不変条件
- worktree suffix 長、hook 環境変数処理、`run_key` の hash 長などの生成細則
- VERIFY の固定的な列挙順 → 対象に応じた選択

### setup

- 対象別コマンド展開 → 共通コマンド 1 件 + 6 行の同期対象表
- CLI 不足時の個別案内 → 影響 / 停止範囲 / 導入コマンドの表
- updater の OS 別逐語手順、compaction のモデル別 window 計算説明
- cursor-agent shim の場合分け → 「理由付き skip」という不変条件
- macOS 固有の補足、再実行シナリオ、11 項目の逐語レポート手順

### memory-review

- 質問数の固定上限 → 危険な不足だけ質問する判断
- 監査対象別の反復説明 → 「監査対象 × 観点」表
- 7 分類・3 影響度の逐語定義（enum 契約は保持し、分類判断を委任）
- 指摘メモとレポート表の逐語テンプレート（11 見出し・必須内容・7 カテゴリは固定）

### improve-skill / commit-push / refactor

- improve-skill: refresh / create の重複手順 → 共通抽出コマンド + モード差分表
- improve-skill: retro の個別エラー例と修正方針対応表 → 3 検出系統と最小変更判断
- commit-push: 論理グループ分割の逐語基準 → 目的 / 理由 / 検証単位に基づく判断
- commit-push: path のシェル引用方法などの実装細則（literal pathspec と完全一致検査は不変条件として保持）
- refactor: `multiSelect`、2〜4 件、3+2 分割、番号選択などの UI 細則

### 明示的に残した安全契約

- `commit-push`: secret 2 層検査、literal pathspec、明示単一 refspec
- `repo-loop`: high risk の提案 Issue 降格、独立レビュー不能時の降格
- `dig`: SHA 束縛 merge、`MERGED` 確認、merge queue 検出、CI 赤で PR を open のまま停止、変更を破棄しない
- `setup`: marker、backup、missing 非致命
- 全スキル: `< /dev/null` による stdin 閉鎖、`gpt-5.6-sol` / `medium` 固定

## 6. テストの刷新

文字列ミラーを不変条件へ寄せた。

| ファイル | 削除した assertion | 書き直した assertion |
|---|---:|---:|
| `test_dig_skill.py` | 27 | 62 |
| `test_backlog_skill.py` | 5 | 17 |
| `test_refactor_skill.py` | 5 | 13 |
| `test_handoff_skill.py` | 6 | 9 |
| `test_catch_up_skill.py` | 0 | 4 |
| `test_goal_prompt_skill.py` | 0 | 8 |

`test_repo_loop_contract.py` / `test_setup_skill.py` / `test_memory_review_skill.py` /
`test_commit_push_skill.py` は本文圧縮と同じジョブで追従させた。

あわせて **`test_doc_size_budget.py` を新設**し、全 SKILL.md と AGENTS.md の文字数上限を強制する。
これが圧縮の巻き戻り防止 ratchet であり、今回追加した唯一の「本物の決定論的強制」。

## 7. 測定できないこと

圧縮の効果（判断品質が上がったか、矛盾解消の推論が減ったか）は測定していない。
記事の主張は Anthropic 内部の coding evaluation に基づくもので、devkit 側に同等の評価系は無い。

トークン量としての効果も小さい。dig 24,064 字 ≒ 12k トークンで、Opus 5 の 1M context に対して 1.2%。
**この変更の狙いはコンテキスト節約ではなく、過剰制約と矛盾の除去**である。
その効果は、[2026-07-25 の認知負荷計測](2026-07-25-cognitive-load-metrics.md) と同じ理由で
因果効果としては測れない。測れるのは契約遵守率とサイズ上限だけで、それは効果ではない。

## 8. 今回やらなかったこと

- `~/.claude/CLAUDE.md`（503 字）と `templates/rules/agents-rules.md`（1,487 字）— 既に適正
- `references/` への段階的開示分割 — 今回は移動ではなく削減を選んだ。improve-skill のみ既存の `references/` を維持
- 横断重複（ハーネス判定の 11 コピー）の解消 — 同時ロードされないため負荷ではない
- `xhigh` / `max` effort、Fable backend の追加 — 新 backend 追加は別案件
