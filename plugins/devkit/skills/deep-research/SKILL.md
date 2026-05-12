---
name: "deep-research"
description: "Chrome Default profileでChatGPT Deep Researchを実行し、長時間調査の結果を取得する"
argument-hint: "[topic]"
allowed-tools: ["Bash", "Read"]
---

# Chrome Default Profile + ChatGPT Deep Research

## 使い方

```bash
/devkit:deep-research [質問内容]
```

`$ARGUMENTS` に渡された質問内容を ChatGPT UI の Deep Research に送信し、調査結果を取得する。API-first 経路は使わない。

## 実行契約

Chrome の通常 `Default` profile を正本にする。
専用 profile は作らず、ChatGPT の既存ログイン状態を使う。
通常 Chrome が CDP なしで起動中の場合は、必要に応じて Chrome の再起動まで許可する。

backend 優先順:

1. `agent-browser --auto-connect` または明示 CDP port
2. Playwright `connectOverCDP` による同じ Default profile Chrome への接続
3. runtime の Chrome 拡張経路

Deep Research の結果は sandboxed iframe に出ることがあるため、完了待ちと抽出は共通 runner に寄せる。

## 前提条件

- Google Chrome がインストール済み
- ChatGPT 側で Deep Research が利用可能である
- ChatGPT へ手動ログインできる GUI セッションがある
- `agent-browser` 0.26.x 以降が入っている
- 結果抽出には Python 3 と `websockets` package が利用可能である
- `localhost,127.0.0.1,::1` が proxy bypass される

## 標準フロー

Windows PowerShell / cmd では `py -3`、macOS / Linux / WSL / Git Bash では `python3` を使う。

まず診断する。

```bash
py -3 plugins/devkit/scripts/chrome_chatgpt_runner.py diagnose
```

CDP が無効な通常 Chrome しかない場合は、Default profile Chrome の再起動を許可して復旧する。

```bash
py -3 plugins/devkit/scripts/chrome_chatgpt_runner.py --restart-chrome diagnose
```

Deep Research を開き、プロンプトを送信する。

```bash
py -3 plugins/devkit/scripts/chrome_chatgpt_runner.py --restart-chrome deep-research "$ARGUMENTS"
```

調査完了後に結果を抽出する。

```bash
py -3 plugins/devkit/scripts/chrome_chatgpt_runner.py extract-deep-research
```

## 操作ルール

- runner は ChatGPT を新規タブで開き、Deep Research の UI 要素を探してクリックする
- UI 表記が変わって自動選択できない場合は、Default profile Chrome 上で Deep Research を手動選択してから続行する
- iframe target はセッションごとに変わるため、抽出時は毎回 CDP `/json` から再取得する
- CDP endpoint は `127.0.0.1` のみに限定する
- proxy 環境では `NO_PROXY` / `no_proxy` に `localhost,127.0.0.1,::1` を含める
- 認証情報、パスワード、リカバリコードはチャットや repo ファイルに貼らない
- `agent-browser snapshot` の生出力を会話・Markdown・コミットへ貼り付けない

## 失敗時の切り分け

- `diagnose` で Chrome 実体、Default profile path、CDP port、proxy bypass、agent-browser、Playwright CDP を確認する
- Chrome が起動中で CDP がない場合は、通常 Chrome を終了して Default profile を CDP 付きで再起動する
- `agent-browser` が失敗しても CDP が LISTEN している場合は、同じ Default profile に Playwright CDP fallback で接続可否を確認する
- agent-browser / Playwright の両方が失敗する場合のみ、runtime の Chrome 拡張経路へ handoff する
- iframe が見つからない場合は、Deep Research の report 表示がまだ未完了か UI が変わっているため、Chrome 画面で進行状態を確認する
