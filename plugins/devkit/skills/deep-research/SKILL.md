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
手順は「CDPでChrome起動 → agent-browser接続 → 手動ログイン（初回のみ） → 新規チャット → Deep Researchで送信 → 長時間待機 → CDP WebSocket経由で結果取得」。

## 前提条件

- `agent-browser` をグローバルにインストール済み（`npm install -g agent-browser`）
- Google Chrome がインストール済み
- 初回ログイン用のGUIセッションがある
- ChatGPT側で Deep Research が利用可能である
- Python 3 + `websockets` ライブラリ（結果取得に使用）

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

> **重要**: `agent-browser click` はChatGPTのReact SPA上でタイムアウトしやすい。
> JS evalによるクリックの方が安定する。

```bash
# まずスナップショットでUI状態を確認
agent-browser --cdp 9222 snapshot -i --compact
```

サイドバーに "Deep research" リンクが見える場合、JS evalでクリック:

```bash
agent-browser --cdp 9222 eval "(function(){var links=document.querySelectorAll('a');for(var i=0;i<links.length;i++){if(links[i].textContent.indexOf('Deep research')!==-1){links[i].click();return 'ok'}}return 'not found'})()"
```

> **fallback**: リンクが見つからない場合はスナップショットを再確認し、
> モデルセレクターを JS eval でクリック:
> `agent-browser --cdp 9222 eval "document.querySelector('button[aria-label*=\"モデル\"]')?.click()"`

Deep Researchモード切替後、3秒待ってからスナップショットで確認:
```bash
agent-browser --cdp 9222 wait 3000
agent-browser --cdp 9222 snapshot -i --compact
```

プロンプト入力欄付近に「Deep Research」ボタンが表示されていればOK。

### 5) 調査プロンプトを送信

> **重要**: `agent-browser type` は複数行テキストで**改行が消失する**問題がある。
> CDP `Input.insertText` を使うことで改行を保持しつつ、React stateも正しく更新される。

```bash
# プロンプトテキストをファイルに書き出す
cat > /tmp/dr-prompt.txt << 'EOF'
$ARGUMENTS
EOF

# テキストエリアにフォーカス
agent-browser --cdp 9222 click "#prompt-textarea"

# CDP Input.insertText で改行を保持したまま安全にテキスト挿入
python3 << 'PYEOF'
import asyncio, json, websockets, urllib.request

async def insert_text():
    targets = json.loads(urllib.request.urlopen("http://127.0.0.1:9222/json").read())
    main = next(t for t in targets if "chatgpt.com" in t.get("url", "") and t.get("type") == "page")
    ws_url = main["webSocketDebuggerUrl"]

    async with websockets.connect(ws_url) as ws:
        with open("/tmp/dr-prompt.txt") as f:
            text = f.read().strip()

        # フォーカスを当てる
        await ws.send(json.dumps({
            "id": 1,
            "method": "Runtime.evaluate",
            "params": {"expression": "document.querySelector('#prompt-textarea')?.focus()"}
        }))
        await asyncio.wait_for(ws.recv(), timeout=5)

        # CDP Input.insertText: React SyntheticEvent互換、改行保持
        await ws.send(json.dumps({
            "id": 2,
            "method": "Input.insertText",
            "params": {"text": text}
        }))
        await asyncio.wait_for(ws.recv(), timeout=5)
        print("Text inserted via CDP Input.insertText")

asyncio.run(insert_text())
PYEOF

# 送信
agent-browser --cdp 9222 press Enter
```

> **短いテキスト（1行）の場合**: `agent-browser type` でも問題なく動作する。
> 複数行テキストの場合のみ上記CDP方式を使用する。

### 6) 長時間待機（30秒間隔、最大30分）

Deep Researchの応答はcross-origin sandboxed iframe内にレンダリングされるため、
親ページのDOM監視では完了を検知できない。
**CDP WebSocket経由でiframe内のコンテンツ長を監視する**方式を使う。

**完了の判定基準**:
- iframeターゲット内の `[class*="report"]` のテキスト長が **500文字以上**
- fallback: スナップショットで「良い回答です」ボタンの出現

```python
import asyncio, json, websockets, urllib.request, time

async def poll_completion(max_minutes=30, interval=30):
    for i in range(max_minutes * 60 // interval):
        try:
            # iframeターゲットを探す
            targets = json.loads(urllib.request.urlopen("http://127.0.0.1:9222/json").read())
            iframe_target = next((t for t in targets if "deep_research" in t.get("url", "")), None)

            if iframe_target:
                ws_url = iframe_target["webSocketDebuggerUrl"]
                async with websockets.connect(ws_url) as ws:
                    await ws.send(json.dumps({"id": 1, "method": "Runtime.enable"}))
                    contexts = []
                    while True:
                        try:
                            resp = await asyncio.wait_for(ws.recv(), timeout=3)
                            data = json.loads(resp)
                            if data.get("method") == "Runtime.executionContextCreated":
                                ctx = data["params"]["context"]
                                if "oaiusercontent" in ctx.get("origin", ""):
                                    contexts.append(ctx)
                        except asyncio.TimeoutError:
                            break

                    for ctx in contexts:
                        msg = json.dumps({
                            "id": 10,
                            "method": "Runtime.evaluate",
                            "params": {
                                "expression": '(document.querySelector("[class*=\\"report\\"]")||{}).innerText?.length||0',
                                "contextId": ctx["id"],
                                "returnByValue": True
                            }
                        })
                        await ws.send(msg)
                        resp = await asyncio.wait_for(ws.recv(), timeout=10)
                        length = json.loads(resp).get("result",{}).get("result",{}).get("value",0)
                        if length > 500:
                            print(f"DONE: Report has {length} chars (iteration {i+1})")
                            return True
        except Exception as e:
            pass  # 接続失敗は許容（iframe未生成等）

        print(f"[{time.strftime('%H:%M:%S')}] Waiting... ({i+1}/{max_minutes*60//interval})")
        await asyncio.sleep(interval)

    print("TIMEOUT: Please check manually with screenshot")
    return False

asyncio.run(poll_completion())
```

> **fallback**: iframe が見つからない場合（UIリグレッション等）は
> `agent-browser --cdp 9222 snapshot -i --compact` で「良い回答です」ボタンを探す従来方式に切り替える。
>
> **タイムアウト時**: `agent-browser --cdp 9222 screenshot /tmp/dr-status.png` で手動確認。

### 7) 結果取得（CDP WebSocket直接接続）

> **重要**: Deep Researchの結果はcross-originのsandboxed iframe
> (`connector_openai_deep_research.web-sandbox.oaiusercontent.com`) 内にレンダリングされる。
> 親ページのDOMからは直接アクセスできないため、CDP WebSocketで iframe のターゲットに直接接続する。

#### Step 7a: iframeターゲットのIDを取得

```bash
curl -sS http://127.0.0.1:9222/json | python3 -c "
import json, sys
data = json.load(sys.stdin)
for d in data:
    if 'deep_research' in d.get('url', ''):
        print(d['webSocketDebuggerUrl'])
        break
"
```

#### Step 7b: Python WebSocketでレポート全文を取得

```python
import asyncio, json, websockets

async def extract_report(ws_url):
    async with websockets.connect(ws_url) as ws:
        # Runtime.enable で execution context を列挙
        await ws.send(json.dumps({"id": 1, "method": "Runtime.enable"}))
        contexts = []
        while True:
            try:
                resp = await asyncio.wait_for(ws.recv(), timeout=3)
                data = json.loads(resp)
                if data.get("method") == "Runtime.executionContextCreated":
                    ctx = data["params"]["context"]
                    if "oaiusercontent" in ctx.get("origin", ""):
                        contexts.append(ctx)
            except asyncio.TimeoutError:
                break

        # oaiusercontent origin の context でレポート本文を取得
        for ctx in contexts:
            msg = json.dumps({
                "id": 10,
                "method": "Runtime.evaluate",
                "params": {
                    "expression": 'document.querySelector("[class*=\\"report\\"]") ? document.querySelector("[class*=\\"report\\"]").innerText : document.body.innerText',
                    "contextId": ctx["id"],
                    "returnByValue": True
                }
            })
            await ws.send(msg)
            resp = await asyncio.wait_for(ws.recv(), timeout=10)
            result = json.loads(resp)
            val = result.get("result", {}).get("result", {}).get("value", "")
            if val and len(val) > 200:
                print(val)
                return
    print("ERROR: Could not extract report")

# ws_url は Step 7a で取得した webSocketDebuggerUrl
asyncio.run(extract_report("ws://127.0.0.1:9222/devtools/page/TARGET_ID"))
```

> **セレクタのfallback**: `[class*="report"]` が見つからない場合、
> `document.body.innerText` で全文を取得する（UIノイズを含む可能性あり）。

## フォローアップ調査（既存チャットの再利用）

既存のDeep Researchチャットに追加質問を送る場合:

```bash
# タブ一覧からチャットタイトルで特定
curl -sS http://127.0.0.1:9222/json | python3 -c "
import json, sys
data = json.load(sys.stdin)
for d in data:
    if 'chatgpt.com' in d.get('url', '') and 'CHAT_TITLE' in d.get('title', ''):
        print(d['id'])
        break
"

# そのタブにフォーカスしてフォローアップを送信
agent-browser --cdp 9222 open "CHAT_URL"
```

## 返信が更新されない場合

- `snapshot -i --compact` で進行中表示（調査中/停止等）を確認する
- `screenshot /tmp/dr-debug.png` でスクリーンショットを撮って視覚的に確認する
- 進行中表示が残る場合は待機を継続する
- 失敗時は新規チャットで同じプロンプトを再送する

## セーフティ

- パスワード/トークン/リカバリコードはチャットやファイルに貼らない
- `agent-browser snapshot` の生出力を会話・Markdown・コミットへ貼り付けない
- ログイン情報は手動入力のみ。自動化スクリプトに認証情報をハードコードしない
- CDP WebSocket接続はローカル（127.0.0.1）のみに限定すること
- iframe targetのIDはセッションごとに変わるため、毎回 `/json` で再取得すること
