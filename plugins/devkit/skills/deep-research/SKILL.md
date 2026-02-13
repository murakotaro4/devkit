---
name: "deep-research"
description: "agent-browserでChatGPT Deep Researchを実行し、長時間調査の結果を取得する"
argument-hint: "[topic]"
allowed-tools: ["Bash", "Read"]
---

# Agent-Browser + ChatGPT Deep Research (CDP)

## 使い方

```bash
/devkit:deep-research [質問内容]
```

`$ARGUMENTS` に渡された質問内容を ChatGPT Deep Research に送信し、調査結果を取得する。

## 目的

Cloudflare対策として、実ChromeのCDP接続でChatGPTを操作する。  
手順は「CDPでChrome起動 → agent-browser接続 → 手動ログイン（初回のみ） → 新規チャット → Deep Researchで送信 → 長時間待機 → 最新返信取得」。

## 前提条件

- `agent-browser` をグローバルにインストール済み（`npm install -g agent-browser`）
- Google Chrome がインストール済み
- 初回ログイン用のGUIセッションがある
- ChatGPT側で Deep Research が利用可能である

## 推奨フロー

### 1) CDP付きでChrome起動

```bash
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
  --remote-debugging-port=9222 \
  --user-data-dir="$HOME/.chrome-cdp-profile"
```

### 2) CDPがLISTENしているか確認

```bash
curl -sS http://127.0.0.1:9222/json/version
```

### 3) ChatGPTを開き、新規チャットを開始

```bash
agent-browser --cdp 9222 tab new
agent-browser --cdp 9222 open "https://chatgpt.com/"
```

初回のみ、開いたChromeで手動ログインする。

### 4) Deep Researchモードを選択

UI表記は変わるため、まずスナップショットで確認する:

```bash
agent-browser --cdp 9222 snapshot -i --compact
```

モデル/ツール切替から Deep Research（または同等の調査モード）を選ぶ。  
必要に応じて再度 `snapshot` で選択状態を確認する。

### 5) 調査プロンプトを送信

```bash
agent-browser --cdp 9222 click "#prompt-textarea"
agent-browser --cdp 9222 type "#prompt-textarea" "$ARGUMENTS"
agent-browser --cdp 9222 press Enter
```

### 6) 長時間待機（30秒間隔、最大120分）

Deep Researchは応答まで時間がかかるため、返信が更新されるまでポーリングする。

```bash
initial_count=$(agent-browser --cdp 9222 eval "(()=>document.querySelectorAll('[data-message-author-role=\"assistant\"]').length)()")
initial_text=$(agent-browser --cdp 9222 eval "(()=>{const els=[...document.querySelectorAll('[data-message-author-role=\"assistant\"]')]; return els.length?els[els.length-1].innerText:null;})()")

for i in {1..240}; do
  curr_count=$(agent-browser --cdp 9222 eval "(()=>document.querySelectorAll('[data-message-author-role=\"assistant\"]').length)()")
  latest_text=$(agent-browser --cdp 9222 eval "(()=>{const els=[...document.querySelectorAll('[data-message-author-role=\"assistant\"]')]; return els.length?els[els.length-1].innerText:null;})()")
  busy=$(agent-browser --cdp 9222 eval "(()=>{const t=[...document.querySelectorAll('button,[role=button],span,div')].map(e=>e.textContent||'').join('\\n'); return /(Deep Research|調査中|思考中|停止|今すぐ回答|Researching|Stop)/i.test(t) ? 1 : 0;})()")

  if [ "$busy" -eq "0" ] && { [ "$curr_count" -gt "$initial_count" ] || [ "$latest_text" != "$initial_text" ]; }; then
    echo "$latest_text"
    break
  fi

  agent-browser --cdp 9222 wait 30000
done
```

### 7) 最新返信を取得（最終確認）

```bash
agent-browser --cdp 9222 eval "(()=>{const els=[...document.querySelectorAll('[data-message-author-role=\"assistant\"]')]; return els.length?els[els.length-1].innerText:null;})()"
```

## 返信が更新されない場合

- `snapshot -i --compact` で進行中表示（調査中/停止等）を確認する
- 進行中表示が残る場合は待機を継続する
- 失敗時は新規チャットで同じプロンプトを再送する

## セーフティ

- パスワード/トークン/リカバリコードはチャットやファイルに貼らない
- `agent-browser snapshot` の生出力を会話・Markdown・コミットへ貼り付けない
- ログイン情報は手動入力のみ。自動化スクリプトに認証情報をハードコードしない
