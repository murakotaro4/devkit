---
name: "gpt-pro"
description: "agent-browser 0.26系でChatGPT Proを自動操作し、Web検索・調査を委譲する"
argument-hint: "[topic]"
allowed-tools: ["Bash", "Read"]
---

# Agent-Browser + ChatGPT Pro

## 使い方

```text
/devkit:gpt-pro [質問内容]
```

`$ARGUMENTS` に渡された質問内容を ChatGPT Pro に送信し、Web検索・調査を委譲する。
Codex 同期後の公開名は `$gpt-pro`。`$computer-use-chatgpt-pro` は ChatGPT デスクトップアプリ専用で、この skill とは別用途。

## 正本と対象範囲

- repo 管理下のブラウザ経路の正本はこの `gpt-pro`
- `computer-use-chatgpt-pro` は ChatGPT アプリ専用
- `~/.codex/skills/agent-browser-chatgpt` のようなローカル個別 skill は repo 管理対象外。残っていても stale の可能性があるため、この skill を優先する

## 目的

Cloudflare 対策と既存ログイン状態の再利用のため、`agent-browser` 0.26 系で実 Chrome を操作して ChatGPT Pro に質問する。
この skill は `--auto-connect` 専用とし、別経路へは切り替えない。

## 前提条件

- `agent-browser` 0.26.x 以降が入っていること
- Google Chrome がインストール済み
- ChatGPT へ手動ログインできる GUI セッションがあること

## 接続フロー

### 1) `agent-browser` の version を確認

```bash
agent-browser --version
```

`0.26.x` 未満なら先に更新する。

### 2) `--auto-connect` を確認する

まず既存 Chrome へ attach できるか確認する。

```bash
agent-browser --auto-connect get url
```

成功したら、この turn では以降の各コマンドを `agent-browser --auto-connect ...` の完全形で実行する。

重要: `--auto-connect` は Chrome プロセスが動いているだけでは不十分。接続可能なデバッグ対象が必要。通常の Chrome が開いているだけで attach できない場合は、この skill では停止する。

`agent-browser 0.26` は daemon 経由でセッションを維持するため、以降は `agent-browser --auto-connect ...` の完全形をそのまま繰り返す。

### 3) ChatGPT を開いてログイン状態を確認

```bash
agent-browser --auto-connect open https://chatgpt.com/
agent-browser --auto-connect snapshot -i --compact
```

未ログインならこの時点で手動ログインする。

### 4) 新しいチャットで開始

過去コンテキスト混入を避けるため、検索・調査は新規チャットで実行する。

```bash
agent-browser --auto-connect tab new
agent-browser --auto-connect open https://chatgpt.com/
```

必要なら UI から新しいチャットを押す。

```bash
agent-browser --auto-connect click "text=新しいチャット"
# agent-browser --auto-connect click "text=New chat"
```

### 5) Pro モデルと検索モードを確認

Thinking ではなく Pro を使う。検索系の依頼は必ず Pro で実行する。

```bash
agent-browser --auto-connect snapshot -i --compact
```

最初のモデル切替は日本語 `aria-label` に固定しない。snapshot で見えている現在モデル名のボタンを押してメニューを開く。例:

```bash
agent-browser --auto-connect click "text=Thinking"
# agent-browser --auto-connect click "text=Auto"
# agent-browser --auto-connect click "text=Pro"
```

メニューが開いたら「Pro」を選び、その後に「検索」/「Search」/「Web」を含む項目を有効化する。表記は変わるため、必要に応じて再度 snapshot で確認する。

```bash
agent-browser --auto-connect snapshot -i --compact
```

### 6) メッセージ送信

入力欄は通常 `#prompt-textarea`。

```bash
agent-browser --auto-connect click "#prompt-textarea"
agent-browser --auto-connect type "#prompt-textarea" "$ARGUMENTS"
agent-browser --auto-connect press Enter
```

### 7) 最新のアシスタント返信を取得

```bash
agent-browser --auto-connect eval "(function(){const els=[...document.querySelectorAll('[data-message-author-role=\"assistant\"]')]; return els.length?els[els.length-1].innerText:null;})()"
```

### 8) 長時間処理の待機

Pro の調査は時間がかかるため、30〜60 秒間隔でポーリングする。以下は 30 秒ごとに最大 60 分待つ例。

```bash
initial_count=$(agent-browser --auto-connect eval "(()=>document.querySelectorAll('[data-message-author-role=\"assistant\"]').length)()")
initial_text=$(agent-browser --auto-connect eval "(()=>{const els=[...document.querySelectorAll('[data-message-author-role=\"assistant\"]')]; return els.length?els[els.length-1].innerText:null;})()")
prev_text="$initial_text"
stable_hits=0
for i in {1..120}; do
  curr_count=$(agent-browser --auto-connect eval "(()=>document.querySelectorAll('[data-message-author-role=\"assistant\"]').length)()")
  busy=$(agent-browser --auto-connect eval "(()=>{const text=[...document.querySelectorAll('button,[role=\"status\"],[aria-live]')].map(el=>el.innerText||'').join('\n'); const ariaBusy=document.querySelectorAll('[aria-busy=\"true\"]').length; return (ariaBusy>0 || /思考中|停止|今すぐ回答|Thinking|Stop|Stop generating|Respond now|Searching/.test(text)) ? 1 : 0;})()")
  latest_text=$(agent-browser --auto-connect eval "(()=>{const els=[...document.querySelectorAll('[data-message-author-role=\"assistant\"]')]; return els.length?els[els.length-1].innerText:null;})()")
  if [ "$busy" -eq "0" ] && { [ "$curr_count" -gt "$initial_count" ] || [ "$latest_text" != "$initial_text" ]; }; then
    if [ "$latest_text" = "$prev_text" ]; then
      stable_hits=$((stable_hits + 1))
    else
      stable_hits=0
    fi
  else
    stable_hits=0
  fi
  if [ "$stable_hits" -ge 1 ]; then
    echo "$latest_text"
    break
  fi
  prev_text="$latest_text"
  agent-browser --auto-connect wait 30000
done
```

### 9) 返信が古いままに見えるとき

直近の返信が未更新に見える場合は、まだ思考中の可能性がある。

```bash
agent-browser --auto-connect snapshot -i --compact
```

「Pro が思考中」「今すぐ回答」などの状態を確認し、必要なら UI で短縮する。

## 追加相談テンプレ

```text
追加調査お願いします。
条件： [条件A / 条件B / 条件C]
出力形式：候補を3〜5件、項目（モデル名/主要スペック/入出力/注意点/価格帯・入手性）で表形式または箇条書きで。
妥協点があれば提示してください。
```

```text
目的： [購入/比較/選定/リスク確認]
優先度： [1位/2位/3位]
制約： [地域/予算/互換性/必須条件]
```

## トラブルシュート

### `--auto-connect` が失敗する

- `agent-browser --auto-connect get url` が失敗したら、その Chrome は attach 対象ではない
- Chrome プロセスが動いていても、接続可能なデバッグ対象がなければ失敗する
- attach できる Chrome を用意できないなら、この skill は使わず停止する

## セーフティ

- パスワードやトークンをチャットや repo ファイルに貼らない
- ログイン情報は手動入力のみ。自動化スクリプトに認証情報を埋め込まない
- ブラウザプロファイルを別管理するならユーザー専用ディレクトリを使い、repo 配下へ入れない
