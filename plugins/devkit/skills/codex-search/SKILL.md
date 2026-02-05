---
description: "Codex --searchでウェブ検索を実行。「調べて」「最新の〜」「〜を比較」「〜の仕様」で起動"
argument-hint: "[topic]"
allowed-tools: ["Bash", "Read", "Grep", "Glob"]
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

Python asyncio スクリプトで並列実行する。

**実行方法**:
```bash
python3 scripts/parallel_search.py \
  --queries '["クエリ1", "クエリ2", "クエリ3"]' \
  --model gpt-5.2 \
  --max-concurrent 5
```

**オプション**:
- `--queries, -q`: JSON配列形式のクエリ（必須）
- `--model, -m`: 使用モデル（デフォルト: gpt-5.2）
- `--max-concurrent, -c`: 最大同時実行数（デフォルト: 5）

**エラーハンドリング**:
- 各クエリは独立して実行され、失敗しても他に影響しない
- 失敗したクエリは結果に `[✗]` マークで表示
- 全体タイムアウト: 10分（Bash ツールのデフォルト）

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

- **出典必須**: 検索結果には必ず出典を含める
- **秘密情報除外**: .env, credentials等は検索クエリに含めない
- **並列実行**: asyncio スクリプト（`scripts/parallel_search.py`）で確実に並列化
- **モデル**: `gpt-5.2` を使用
