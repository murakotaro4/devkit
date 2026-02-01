---
name: gpt-pro
description: "agent-browserでChatGPT Proを自動操作し、Web検索・調査を委譲する"
argument-hint: "[topic]"
allowed-tools: ["Bash", "Read"]
---

# Agent-Browser + ChatGPT Pro (CDP)

## 使い方

```
/devkit:gpt-pro [質問内容]
```

`$ARGUMENTS` に渡された質問内容を ChatGPT Pro に送信し、Web検索・調査を委譲する。

## 目的

Cloudflare対策として、実ChromeのCDP接続でChatGPT Proを自動操作する。
手順は「CDPでChrome起動 → agent-browser接続 → 手動ログイン（初回のみ） → Proモデル選択 → 検索モード有効化 → 送信 → 返信取得」。

## 前提条件

- `agent-browser` をグローバルにインストール済み（`npm install -g agent-browser`）
- Google Chrome がインストール済み
- 初回ログイン用のGUIセッションがある

## 推奨フロー

### 1) CDP付きでChrome起動

プロファイルロック回避のため専用プロファイル推奨:

```bash
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
  --remote-debugging-port=9222 \
  --user-data-dir="$HOME/.chrome-cdp-profile"
```

既存セッションを使う場合は通常起動→CDP付きで再起動。ただしポリシーやプロファイルロックで失敗する可能性あり。

### 2) CDPがLISTENしているか確認

```bash
curl -s http://127.0.0.1:9222/json/version
```

### 3) 接続してChatGPTを開く

```bash
agent-browser --cdp 9222 open https://chatgpt.com/
```

### 4) 手動ログイン（初回のみ）

開いたChromeでログイン。ログイン後は最小化してOK。

### 5) 新しいチャットで開始

過去コンテキスト混入を避けるため、検索・調査は新しいタブ/新規チャットで実行する。

```bash
agent-browser --cdp 9222 tab new
agent-browser --cdp 9222 open https://chatgpt.com/
```

または「新しいチャット」リンクをクリック:

```bash
agent-browser --cdp 9222 click "text=新しいチャット"
# 英語UIの場合:
# agent-browser --cdp 9222 click "text=New chat"
```

### 6) スナップショットでUI確認

```bash
agent-browser --cdp 9222 snapshot -i --compact
```

### 7) Proモデルに切り替え、検索モードを有効化

原則としてThinkingは使わず、Proをデフォルトにする。検索系の依頼は必ずProで実行する。

モデルセレクターをクリック:

```bash
agent-browser --cdp 9222 click "button[aria-label*='モデル セレクター']"
```

「Pro」を選択後、「検索」/「Search」/「Web」を含む項目を選ぶ。
表記は変わるため再スナップショットで確認:

```bash
agent-browser --cdp 9222 snapshot -i --compact
```

### 8) メッセージ送信

入力欄は `#prompt-textarea`（contenteditable）:

```bash
agent-browser --cdp 9222 click "#prompt-textarea"
agent-browser --cdp 9222 type "#prompt-textarea" "$ARGUMENTS"
agent-browser --cdp 9222 press Enter
```

### 9) 最新のアシスタント返信を取得

```bash
agent-browser --cdp 9222 eval "(function(){const els=[...document.querySelectorAll('[data-message-author-role=\"assistant\"]')]; return els.length?els[els.length-1].innerText:null;})()"
```

### 10) 長時間処理の待機（ポーリング）

Proの調査は時間がかかるため、**30〜60秒間隔でポーリング**する。
以下は「30秒ごとに最大60分待つ」例（返信が出たら終了）:

```bash
initial_count=$(agent-browser --cdp 9222 eval "(()=>document.querySelectorAll('[data-message-author-role=\"assistant\"]').length)()")
initial_text=$(agent-browser --cdp 9222 eval "(()=>{const els=[...document.querySelectorAll('[data-message-author-role=\"assistant\"]')]; return els.length?els[els.length-1].innerText:null;})()")
for i in {1..120}; do
  curr_count=$(agent-browser --cdp 9222 eval "(()=>document.querySelectorAll('[data-message-author-role=\"assistant\"]').length)()")
  busy=$(agent-browser --cdp 9222 eval "(()=>[...document.querySelectorAll('button')].map(b=>b.innerText).filter(t=>/思考中|停止|今すぐ回答/.test(t)).length)()")
  latest_text=$(agent-browser --cdp 9222 eval "(()=>{const els=[...document.querySelectorAll('[data-message-author-role=\"assistant\"]')]; return els.length?els[els.length-1].innerText:null;})()")
  if [ "$busy" -eq "0" ] && { [ "$curr_count" -gt "$initial_count" ] || [ "$latest_text" != "$initial_text" ]; }; then
    echo "$latest_text"
    break
  fi
  agent-browser --cdp 9222 wait 30000
done
```

### 11) 返信が古い/未更新のときの確認

直近の返信が「以前の内容」のままに見える場合は、Proがまだ思考中の可能性がある。
スナップショットで「Pro が思考中」「今すぐ回答」などが出ていないか確認:

```bash
agent-browser --cdp 9222 snapshot -i --compact
```

必要に応じて「今すぐ回答」ボタンをクリックして短縮する。

### 12) 相談を継続する（同じチャットで深掘り）

同じチャットで追加要件や比較条件を追記して相談を続ける。

#### 汎用の追加相談テンプレ

```
追加調査お願いします。
条件： [条件A / 条件B / 条件C]
出力形式：候補を3〜5件、項目（モデル名/主要スペック/入出力/注意点/価格帯・入手性）で表形式または箇条書きで。
妥協点があれば提示してください。
```

#### 目的別テンプレ（例）

```
目的： [購入/比較/選定/リスク確認]
優先度： [1位/2位/3位]
制約： [地域/予算/互換性/必須条件]
```

## ヘッドレス注意点

- ChatGPTはヘッドレスを弾くことが多い。実ChromeのCDP接続が最も安定。
- どうしてもヘッドレスなら `--headless=new --remote-debugging-port=9222` で起動するが失敗しやすい。

## トラブルシュート

- **CDPポートが開かない**: Chromeを完全終了→CDP付きで再起動。
- **`agent-browser` が接続できない**: `curl http://127.0.0.1:9222/json/version` がJSONを返すか確認。
- **Cloudflareに弾かれる**: Playwrightヘッドレスではなく実ChromeのCDP接続を使う。

## セーフティ

- パスワード/トークンはチャットやファイルに貼らない。
- クッキーやプロファイルを扱う場合は `credentials/` 配下に置く。
  - `credentials/` は必ず `.gitignore` に追加し、外部共有禁止。
  - CDPプロファイルディレクトリはユーザー専用ディレクトリ（`$HOME/.chrome-cdp-profile` など）を推奨。
- ログイン情報は手動入力のみ。自動化スクリプトに認証情報をハードコードしない。
