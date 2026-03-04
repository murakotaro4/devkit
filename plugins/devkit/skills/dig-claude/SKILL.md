---
name: "dig-claude"
description: "dig の Claude adapter。AskUserQuestionTool と EnterPlanMode/ExitPlanMode を使って dig-core 契約を実行する。"
argument-hint: "[topic]"
allowed-tools: ["Read", "Grep", "Glob", "Bash"]
---

# /dig-claude - Claude Adapter

## 実行契約

- 質問: `AskUserQuestionTool`
- 計画: `EnterPlanMode` -> `ExitPlanMode`

## 手順

1. EnterPlanMode を呼ぶ。
2. `dig-core` 契約に沿って深掘り質問を進める。
3. 必要なら `decomposition` を実行する。
4. クロスモデルレビュー後に ExitPlanMode する。
5. 実行へ進む。
