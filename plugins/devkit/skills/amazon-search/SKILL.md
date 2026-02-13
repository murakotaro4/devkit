---
name: "amazon-search"
description: "Amazon.co.jpで検索→候補をJSON抽出（ASIN/価格/★/レビュー数）。「Amazonで◯◯を検索して一覧化」「ASIN/価格/★を表にして」「dpも見て要点抽出」などで起動。"
argument-hint: "[search|dp] ...args"
allowed-tools: ["Bash", "Read"]
---

# /devkit:amazon-search - Amazon検索（JSON抽出 / CDP）

Amazon.co.jp の検索結果 / 商品ページから、個人情報が混ざらない範囲の最小情報だけを抽出して JSON にします。

## 重要（安全）

- `agent-browser snapshot` の出力は **会話・Markdown・コミットへ貼り付けない**（個人情報が混ざり得る）。
- 保存するログは **最小限のJSON** のみ（HTML全量、Cookie、配送先、アカウント情報等は保存しない）。
- Amazonリンクは追跡クエリを落として `https://www.amazon.co.jp/dp/<ASIN>` に正規化する。

## 前提（推奨フロー）

1) CDP付きChromeを起動（macOS）

```bash
open "$HOME/Applications/Chrome CDP.app"
curl -sS http://127.0.0.1:9222/json/version
```

2) Amazonを開いて必要なら手動ログイン（初回のみ）

```bash
agent-browser --cdp 9222 open "https://www.amazon.co.jp/"
```

## 使い方

### 検索結果の抽出（search）

```bash
/devkit:amazon-search search --query "モニター台 幅 100cm" --pages 2 --out /tmp/amazon-search.json
```

クエリは複数指定できます:

```bash
/devkit:amazon-search search --query "モニター台 幅 100cm" --query "机上ラック 幅 100cm" --pages 2 --out /tmp/amazon-search.json
```

### 商品ページの抽出（dp）

```bash
/devkit:amazon-search dp --in /tmp/amazon-search.json --cap 60 --out /tmp/amazon-dp.json
```

## 実行（同梱スクリプト）

原則として同梱スクリプトを呼び出すだけにする。

```bash
SCRIPT1="$HOME/.agent/skills/amazon-search/scripts/amazon-search.sh"
SCRIPT2="$HOME/.claude/plugins/marketplaces/murakotaro4/plugins/devkit/skills/amazon-search/scripts/amazon-search.sh"

if [ -x "$SCRIPT1" ]; then
  bash "$SCRIPT1" $ARGUMENTS
elif [ -x "$SCRIPT2" ]; then
  bash "$SCRIPT2" $ARGUMENTS
else
  echo "error: amazon-search.sh が見つかりません。OpenSkillsで devkit を install するか、Claude Codeプラグインの配置を確認してください。" >&2
  exit 1
fi
```

## 出力（概要）

- `search`: `items[]` に `asin/title/url/price/rating/reviewCount` など（検索結果カード由来）
- `dp`: `items[]` に `bullets/tech/details` など（商品ページ由来）

## トラブルシュート（最小）

- CDPが繋がらない: `curl http://127.0.0.1:9222/json/version` が返るか確認。
- CAPTCHA/Robot Check: GUI上で解いてから再実行（dpは途中まで出力して止まります）。
