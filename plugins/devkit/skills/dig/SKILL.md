---
name: "dig"
description: "深掘り質問の共通入口。runtime=claude|codex|opencode を解決し、dig-core と各 adapter に委譲する。"
argument-hint: "[runtime=<claude|codex|opencode>] [topic]"
allowed-tools: ["Read", "Grep", "Glob", "Bash"]
---

# /dig - Runtime Orchestrator

`/dig` は入口のみを担当する。実行ロジックは `dig-core` と runtime adapter に委譲する。

## 入力契約

優先順位:
1. 先頭メタ行 `runtime=<claude|codex|opencode>`
2. 入口既定値
   - Claude `/devkit:dig` -> `claude`
   - Codex `/prompts:devkit-dig` -> `codex`
   - OpenCode `/dig` template -> `opencode`

解決不能時は停止し、`DIG_RUNTIME_UNRESOLVED` を返す。

不正ヘッダ時は停止し、`DIG_RUNTIME_HEADER_INVALID` を返す。

## 実行手順

1. runtime を解決する。
2. `dig-core` の共通契約を読み込む。
3. runtime ごとに adapter を呼ぶ。
   - `claude` -> `dig-claude`
   - `codex` -> `dig-codex`
   - `opencode` -> `dig-opencode`
4. adapter が返した停止コードまたは完了状態をそのままユーザーへ返す。

## 停止時の出力契約

停止時は必ず以下を含める:
- `ERROR_CODE`
- 1行の再実行コマンド
- 1行の診断コマンド

## 重要

- 入口名 `/dig` と `$dig` は維持する。
- 実行フローそのものは `dig-core` に集約し、ここで重複定義しない。
