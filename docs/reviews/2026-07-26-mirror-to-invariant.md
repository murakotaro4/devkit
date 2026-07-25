# 文字列ミラーから汎用不変条件へ（2026-07-26）

## 1. 動機

[2026-07-25 の圧縮](2026-07-25-context-engineering-claude5.md) では、独立レビューが 9 巡で 17 件の退行を検出した。
そのすべてで**テストは green のまま**だった。

原因は同レポート §7 に記録したとおり、契約テストの大半が
`assert "<SKILL.md の一文>" in text` という**文字列ミラー**だったこと。
本文の文言と assertion が同じ内容を持つため、文言を消せば assertion も一緒に消え、矛盾が生じない。
**テストが本文の写しである限り、本文の劣化は原理的に検出できない。**

## 2. 方針

17 件の内訳を分類すると、すべてが次の 4 カテゴリに収まった。

| カテゴリ | 17 件のうち |
|---|---|
| コマンド形 | `review` の scope フラグ + PROMPT 併用、シェル変数の未代入、lease なし remote 削除、worktree 外実行、`GIT_*` 継承 |
| 構造 | 入力ファイルの未生成、branch 名の連番 |
| 順序 | 節目 commit と独立レビューの前後、marker 検索の位置 |
| 条件節 | 「〜する（ただし X なら省略）」の括弧内消失が 6 件 |

そこで**1 文ずつ書き換えるのではなく、カテゴリ単位の check を全 12 ファイルへ一括適用**し、
どの check にも載らない政策文は削除する方針を採った。

## 3. 実装

### 汎用不変条件モジュール

`plugins/devkit/tests/test_skill_invariants.py` を新設した。対象は `AGENTS.md` と配布 11 スキルの `SKILL.md`。

| check | カテゴリ | 検出対象 | 検査対象数 |
|---|---|---|---:|
| `stdin_closed` | A1 | 非対話 CLI の stdin 未閉鎖 | 10 |
| `codex_execution_shape` | A2 | `-a never` / model / effort の逸脱 | 8 |
| `review_scope_without_prompt` | A3 | scope フラグと positional PROMPT の併用 | 3 |
| `shell_variables_assigned` | A4 | シェル変数の同ブロック内未代入 | 14 |
| `no_broad_git_add` | A5 | `git add .` / `git add -A` | 14 |
| `remote_delete_has_lease` | A6 | lease なし remote branch 削除 | 1 |
| `worktree_commands_pin_directory` | A7 | worktree 委譲・レビューの実行 dir 未指定 | 6 |
| `frontmatter_name_matches_directory` | B1 | frontmatter 欠落・name 不一致 | 11 |
| `enum_table_cells` | B3 | enum 表の未知値・欠損セル | 15 |
| `commit_before_independent_review` | C1 | 節目 commit と独立レビューの順序逆転 | 1 |
| `approval_before_implementation` | C2 | 計画承認と実装委譲の順序逆転 | 1 |
| `ci_green_before_merge` | C3 | CI green 記述の欠落・merge との順序逆転 | 2 |

### mutation fixture — この作業の本体

前回は「追加した check が修正前の文面で実際に落ちること」を手動で確認したが、**その証跡はコードに残らなかった**。
今回は各 check に、その check が検出すべき退行を再現する mutation 関数を必ず添えた。

meta-test は 6 つの空洞化を封じる。

1. 必須カテゴリ集合との完全一致（カテゴリの取りこぼし）
2. 同一カテゴリの重複登録
3. mutation 未登録
4. mutation が docs を変更しない（空振りの mutation）
5. mutation を check が検出できない（空振りの check）
6. 実文書上の検査対象がゼロ（対象なしで自明に通る check）

**check が空洞化したら CI が落ちる。**

## 4. 結果

| ファイル | 本文散文ミラー（前） | （後） |
|---|---:|---:|
| `test_dig_skill.py` | 71 | 6 |
| `test_repo_loop_contract.py` | 18 | 2 |
| `test_document_consistency.py` | 14 | 0 |
| **合計** | **103** | **8** |

テスト総数は 351 で前後不変。ミラーが減った分、汎用 check と構造検査が増えている。

`test_document_consistency.py` は横断整合（AGENTS.md の正本と各 SKILL.md のコピーのドリフト検出）
という固有の役割を持つため、ミラーを消して終わりにせず、
**7 カテゴリの集合比較・enum 比較・条件と操作の同一行検査**といった構造検査へ寄せた。
このファイルからは**契約を 1 件も削除していない**。

## 5. 削除した契約

`test_dig_skill.py` から 50 件、`test_repo_loop_contract.py` から 14 件の政策文を削除した。
いずれも機械検査できる表面を持たない記述（「既定は実装完遂」「承認なしで実装に進まない」
「1 ラウンド最大 4 問」など）で、汎用 check のどのカテゴリにも載らない。

**この削除は検出力の正味の喪失である。** 引き換えに、テストが本文の写しである構造を断った。
mirror は「消えたら一緒に消える」ため元から検出力を持たなかった、というのが今回の判断の根拠だが、
政策文が本文から消えたときに気づく手段は現時点で存在しない。

## 6. 自レビューで見つけた欠陥

委譲した実装が、**assertion を削除しながら「この契約を守る」と説明するコメントだけを残した**箇所が
2 件あった。コメントが実在しない防御を主張する状態で、削除より悪い。

| 契約 | 状態 |
|---|---|
| origin なし repo での fetch 省略 | コメントのみ残存、assertion なし |
| branch 名衝突時の `-2` 連番 | コメントのみ残存、assertion なし |

どちらも 2026-07-25 の圧縮で一度壊れて独立レビューが [P2] として検出した項目であり、
汎用 check のどのカテゴリにも載らない。`test_worktree_creation_keeps_its_exception_paths` として
短い固定トークン（`fetch を省略` / `` `-2` から連番 ``）で復元し、
本文から各トークンを落とすと実際に落ちることを確認した。

**教訓**: 「汎用 check へ統合した」というコメントは、統合先が実在することを機械検査しないと嘘になりうる。
今回は親が全コメントの参照先を `CHECKS` のキー集合と突き合わせて検証した。

## 7. 実装しなかった不変条件

| # | 内容 | 理由 |
|---|---|---|
| B2 | step 見出しの連番に抜け・重複がない | `setup/SKILL.md` が現に満たしていない。2026-07-25 の圧縮で step 3〜7 が `## 同期` の表へ畳まれた際、`### 2.` `### 8.` `### 9.` `### 10.` の番号だけが残った。**本文側の修正が先に必要** |
| D1 | skip 余地と「スキップ不可」の断定が同一ファイルに共存しない | 「承認時点では skip 可、適用後は必須」のような正当な段階差を自然言語だけで安全に区別できない。壊れやすい正規表現を残すより実装しない方を選んだ |

B2 は `EXPECTED_CATEGORIES` に含めていないため、追加するときは集合の更新が必要になる（黙って抜けない）。

## 8. 今回やらなかったこと

- 残り 9 テストファイルの本文散文ミラー 72 件 — 汎用 check の型が固まったので、横展開は別 PR で行う
- `setup/SKILL.md` の step 番号の是正と B2 の実装 — 本文変更を伴うため別案件
- 圧縮そのものの効果測定 — [2026-07-25 のレポート](2026-07-25-context-engineering-claude5.md) §8 と同じ理由で、devkit 側に評価系がない
