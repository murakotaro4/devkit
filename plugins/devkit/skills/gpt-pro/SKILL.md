---
name: "gpt-pro"
description: "Chrome Default profileでChatGPT Proを自動操作し、Web検索・調査を委譲する"
argument-hint: "[topic]"
allowed-tools: ["Bash", "Read"]
---

# Chrome Default Profile + ChatGPT Pro

## 使い方

```text
/devkit:gpt-pro [質問内容]
```

Codex 同期後の公開名は `$gpt-pro`。`$computer-use-chatgpt-pro` は ChatGPT デスクトップアプリ専用で、この skill とは別用途。

## 正本と対象範囲

- repo 管理下のブラウザ経路の正本はこの `gpt-pro`
- Chrome の通常 `Default` profile を使う。専用 profile や API-first 経路へは切り替えない
- `computer-use-chatgpt-pro` は ChatGPT アプリ専用
- `~/.codex/skills/agent-browser-chatgpt` のようなローカル個別 skill は repo 管理対象外。残っていても stale の可能性があるため、この skill を優先する

## 実行契約

Cloudflare 対策と既存ログイン状態の再利用のため、実 Chrome の `Default` profile に CDP で接続して ChatGPT Pro に質問する。
通常起動中の Chrome が CDP なしの場合は、必要に応じて Chrome の再起動まで許可する。

backend 優先順:

1. `agent-browser --auto-connect` または明示 CDP port
2. Playwright `connectOverCDP` による同じ Default profile Chrome への接続
3. runtime の Chrome 拡張経路

Chrome 拡張経路では tab listing と page operation を別々に確認する。tab が見えてもページ操作が失敗する場合は接続成功扱いにしない。

## 前提条件

- Google Chrome がインストール済み
- ChatGPT へ手動ログインできる GUI セッションがあること
- `agent-browser` 0.26.x 以降が入っていること
- Playwright fallback を使う環境では Node.js と `playwright` が利用可能であること
- `localhost,127.0.0.1,::1` が proxy bypass されること

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

相談を送信する。

```bash
py -3 plugins/devkit/scripts/chrome_chatgpt_runner.py --restart-chrome gpt-pro "$ARGUMENTS"
```

長時間処理の完了待ちと最新返信の取得:

```bash
py -3 plugins/devkit/scripts/chrome_chatgpt_runner.py wait-gpt-pro --timeout-minutes 60 --interval 30
```

## 操作ルール

- 過去コンテキスト混入を避けるため、runner は ChatGPT を新規タブで開く
- Pro モデルや検索モードの UI 表記は変わるため、必要なら Default profile Chrome 上で手動確認する
- CDP endpoint は `127.0.0.1` のみに限定する
- proxy 環境では `NO_PROXY` / `no_proxy` に `localhost,127.0.0.1,::1` を含める
- 認証情報、パスワード、リカバリコードはチャットや repo ファイルに貼らない

## 失敗時の切り分け

- `diagnose` で Chrome 実体、Default profile path、CDP port、proxy bypass、agent-browser、Playwright CDP を確認する
- Chrome が起動中で CDP がない場合は、通常 Chrome を終了して Default profile を CDP 付きで再起動する
- `agent-browser` が失敗しても CDP が LISTEN している場合は、同じ Default profile に Playwright CDP fallback で接続可否を確認する
- agent-browser / Playwright の両方が失敗する場合のみ、runtime の Chrome 拡張経路へ handoff する
