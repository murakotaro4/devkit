---
description: "Codex --searchでウェブ検索を実行。「調べて」「最新の〜」「〜を比較」「〜の仕様」で起動"
argument-hint: "[topic]"
allowed-tools: ["Bash", "Read", "Grep", "Glob", "Task"]
---

# /codex-search - ウェブ検索スキル

Codex CLIの`--search`フラグを活用したウェブ検索特化スキル。
並列検索で高速に情報収集し、出典付きのサマリーレポートを生成する。

## 使い方

```
/codex-search "topic"
```

例：
- `/codex-search "React 19の新機能"`
- `/codex-search "Next.js vs Remix 2025"`
- `/codex-search "Claude API rate limit"`

---

## トピック
$ARGUMENTS

## 実行フロー

### Phase 0: 意図分類

クエリの種類を判定する:

| 種類 | トリガー例 | 検索戦略 |
|------|-----------|----------|
| 調査 | 「〜について調べて」 | 広く情報収集 |
| 比較 | 「〜 vs 〜」「〜を比較」 | 両者の特徴を並列検索 |
| トラブルシュート | 「エラー」「動かない」 | エラーメッセージ + 解決策 |
| 最新 | 「最新の〜」「2025年の〜」 | 日付フィルター付き検索 |
| 仕様確認 | 「〜の仕様」「〜の使い方」 | 公式ドキュメント優先 |

### Phase 1: 文脈収集（オプション）

リポ内実装との照合が必要な場合のみ実行:

```
収集対象（ドキュメント情報のみ）:
- package.json / requirements.txt（技術スタック）
- README.md / docs/（プロジェクト概要）

除外（絶対に読まない）:
- .env, .env.*
- credentials.json, secrets.*
- *.pem, *.key, id_rsa
```

### Phase 2: クエリ生成・最適化

意図に基づいてクエリを複数に分解:

```
例: "React 19の新機能"
→ "React 19 new features official 2025"
→ "React 19 migration guide"
→ "React 19 performance improvements"
```

ソース優先順位:
1. 公式ドキュメント
2. 一次情報（ベンダー発表）
3. 信頼性の高い技術メディア

**安全ルール**: 検索クエリに固有名詞・社内URL・コード片を入れない

### Phase 3: 並列検索実行

各クエリを **シェルレベルで並列実行** する。

**実行方法**:
シェルの `&` と `wait` で並列実行し、結果をファイルに出力:

```bash
# 一時ディレクトリ作成
TMPDIR=$(mktemp -d)

# 並列実行（バックグラウンド）
codex --search exec -m o3 -s read-only "クエリ1" > "$TMPDIR/result1.txt" 2>&1 &
codex --search exec -m o3 -s read-only "クエリ2" > "$TMPDIR/result2.txt" 2>&1 &
codex --search exec -m o3 -s read-only "クエリ3" > "$TMPDIR/result3.txt" 2>&1 &

# 全プロセスの完了を待機
wait

# 結果を読み込み
cat "$TMPDIR"/*.txt
rm -rf "$TMPDIR"
```

- 各クエリの結果は別ファイルに出力して混在を防ぐ
- `wait` で全プロセスの完了を待機
- 全ての結果が返ってきたら Phase 4 へ

**上限設定**:
- 最大並列数: 6
- 最大クエリ数: 10
- タイムアウト: 10分（全体）

**エラーハンドリング**:
- 429/timeout: 指数バックオフ（5s→15s+ジッタ）でリトライ（最大2回）
- 429が続く場合: 段階的縮退（並列数 6→3→1）で再試行
- 失敗したクエリは明示的に報告して継続
- 全て失敗した場合はエラーを報告して終了
- 全体10分を超えたら部分結果で返答

### Phase 4: 結果統合・要約

全結果を収集し、以下のフォーマットで出力:

```markdown
## 結論
[要点を簡潔に]

## 根拠
- [箇条書きで根拠を列挙]
- [複数の情報源からの裏付け]

## 出典
| URL | 発行元 | 日付 |
|-----|--------|------|
| https://... | React公式 | 2025-01-15 |
| https://... | Vercel Blog | 2025-01-10 |

※検索を使用した場合、出典は必須

## 不確実性・未確認点
- [確認が必要な事項]
- [情報の鮮度に関する注意]

## 次のアクション
- [推奨されるアクション]
```

## 使用例

```
/codex-search "React 19の新機能"
/codex-search "2025年のLLMベンチマーク比較"
/codex-search "Next.js vs Remix 2025"
/codex-search "TypeError: Cannot read property of undefined 解決策"
/codex-search "Claude API rate limit"
```

## 重要

- **出典必須**: 検索を使ったなら出典は必須。未検索なら「出典なし（未検索）」と明示
- **秘密情報除外**: .env, credentials等は絶対に検索クエリに含めない
- **並列実行**: シェルの `&` と `wait` で並列実行、結果はファイル出力
- **タイムアウト**: 全体で10分を超えたら部分結果で返答
