---
name: "computer-use-chatgpt-pro"
description: "macOS の Codex Desktop Computer Use で ChatGPT Pro に単発相談する明示依頼で使用する。「Computer UseでChatGPT Proに質問」「Codex DesktopでGPT Proに相談」など。汎用のChatGPT Pro検索・調査は既存のgpt-proを使う。agent-browser/CDP/headless/DOM eval は使わない。"
argument-hint: "[question]"
allowed-tools: ["Bash", "Read", "mcp__computer_use__*"]
---

# Computer Use + ChatGPT Pro (macOS)

## 使い方

Codex Desktop:

```bash
$computer-use-chatgpt-pro [質問内容]
```

Claude Code plugin command:

```bash
/devkit:computer-use-chatgpt-pro [質問内容]
```

Codex Desktop の Computer Use で ChatGPT Pro に相談する。
回答は外部アドバイスとして扱い、Codex 側で検証・要約してユーザーに返す。

## 適用条件

- macOS の Codex Desktop で、Computer Use plugin が使えること。
- ユーザー本人の ChatGPT アカウントで、Pro モデルが利用可能であること。
- Computer Use が対象ブラウザを操作できること。

macOS 以外、Computer Use が使えない環境、またはログイン操作をユーザーが完了できない場合は停止する。

## 禁止境界

- `agent-browser`、CDP、headless Chrome、Playwright DOM eval、ChatGPT DOM の直接取得を使わない。
- cookie、localStorage、sessionStorage、ブラウザプロファイル、パスワード、トークンを読まない・保存しない・共有しない。
- rate limit、アクセス制御、CAPTCHA、利用制限、安全対策を回避しない。
- ChatGPT Pro を第三者サービスの裏側に組み込む、アカウントを共有する、再販売する形で使わない。
- 「20 分間隔で対話し続ける」などの自律ループをデフォルトにしない。追加相談はユーザーが求めた範囲だけ行う。
- 高リスク領域の自動判断に使わない。法務・医療・金融などは一次情報と専門家確認を必須にする。

参考: OpenAI Help の ChatGPT Pro 説明では、自動/プログラム的なデータ抽出、認証情報共有、第三者サービス化が制限対象として示されている。OpenAI Usage Policies と ChatGPT agent policy でも、制限・安全対策の回避や高リスク領域の自動判断を避ける必要がある。

- https://help.openai.com/en/articles/9793128-what-is-chatgpt-pro
- https://openai.com/policies/usage-policies/
- https://openai.com/policies/using-chatgpt-agent-in-line-with-our-policies/

## 推奨フロー

### 1) macOS と Computer Use を確認

```bash
test "$(uname -s)" = "Darwin"
```

Computer Use tool が未ロードなら、`tool_search` で `computer use` を探してロードする。
操作前には必ず対象ブラウザで `mcp__computer_use__.get_app_state` を呼び、画面とアクセシビリティツリーを確認する。
基本操作は `mcp__computer_use__.click`、`mcp__computer_use__.type_text`、`mcp__computer_use__.set_value`、`mcp__computer_use__.scroll` を使う。

### 2) ブラウザで ChatGPT を開く

既定は Google Chrome。必要なら Safari を使う。

```bash
open -a "Google Chrome" "https://chatgpt.com/"
```

ブラウザ操作は Computer Use で行う。ログイン画面が出た場合はユーザーに手動ログインを依頼し、認証情報を入力・保存・取得しない。

### 3) 新規チャットを開始

過去コンテキスト混入を避けるため、新しいチャットを開く。
UI 表記は変わるため、ボタン名に固定せず `get_app_state` のアクセシビリティツリーで確認してからクリックする。

### 4) Pro モデルを選ぶ

モデルセレクターが見える場合だけ、Computer Use で開いて `Pro` と表示されるモデルを選ぶ。
UI に表示されないモデル名を主張しない。Pro が使えない、制限中、または選択できない場合はその状態をユーザーに報告して停止する。

### 5) 相談プロンプトを送る

送信する前に、秘密情報・未公開コード・個人情報・顧客データが含まれていないか確認する。
必要ならユーザーに確認してから送る。

推奨プロンプト:

```text
あなたは Codex が相談している外部アドバイザーです。
回答は根拠、前提、不確実性、検証すべき点を分けてください。
秘密情報、ログイン情報、cookie、token、アクセス制限回避は求めないでください。

相談内容:
[ユーザーの質問]
```

### 6) 完了まで待つ

回答生成中は 30〜60 秒程度の間隔で `get_app_state` を確認する。
停止ボタン、生成中表示、入力欄の状態を見て、途中で回答を打ち切らない。
長時間になった場合でも自動ループ化せず、必要ならユーザーに継続可否を確認する。

### 7) 回答を取得して返す

短い回答はアクセシビリティツリーから読み取る。
長い回答は、画面上の Copy ボタンを Computer Use で押し、`pbpaste` で取得してよい。ただしクリップボードから読む対象は ChatGPT の回答だけに限定し、認証情報やブラウザ内部状態は読まない。

最終回答では、ユーザーが求めていない限り内部の実行手段は説明しない。次を簡潔に明示する:

- ChatGPT Pro から得た要点
- Codex 側で妥当と判断した点
- 追加検証が必要な点
- 参照 URL や一次情報が必要な場合はその不足

## 失敗時の扱い

- **Computer Use が使えない**: この skill は使えないと伝え、別手段へ勝手に切り替えない。
- **ログインや 2FA が必要**: ユーザーの手動操作を待つ。認証情報を要求しない。
- **CAPTCHA / 制限 / エラー**: 回避せず停止し、画面に見えている状態を簡潔に報告する。
- **モデルが選べない**: 利用可能な選択肢を報告し、ユーザーの判断を待つ。
- **回答が不完全**: そのまま不完全と明示し、追加で待つか再質問するかをユーザーに確認する。
