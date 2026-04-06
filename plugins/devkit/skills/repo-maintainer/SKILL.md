---
name: "repo-maintainer"
description: "各リポジトリの夜間メンテナンスを行う。`.devkit/repo-maintainer.toml` を読み、lane/phase/allowed_paths を守って docs・設定・コードの安全な保全更新を行う。scheduler や nightly maintenance、drift audit、weekly consolidation で起動。"
allowed-tools: ["Read", "Grep", "Glob", "Bash", "Write", "Edit"]
---

# /repo-maintainer - Cross-Repo Nightly Maintainer

共有 skill。各 repo の `.devkit/repo-maintainer.toml` を正本として、nightly maintenance を実行する。
Git branch / PR / auto-merge / review gate は runner が担当する。この skill は **repo の内容更新だけ** を担う。

## トピック

$ARGUMENTS

## 必須ルール

1. 最初に `.devkit/repo-maintainer.toml` を読む。
1. `REPO_MAINTAINER_LANE` `REPO_MAINTAINER_PHASE` `REPO_MAINTAINER_ALLOWED_PATHS` が渡されていれば、それを runner からの強制条件として扱う。
1. `allowed_paths` と phase の外へ変更を広げない。
1. Git 操作は禁止。`git commit` `git push` `gh pr *` は実行しない。
1. `logs/skills` と `reviews/` の更新は runner が後段で整える前提とし、この skill は repo の実体更新に集中する。
1. 変更が不要なら worktree を汚さずに終える。

## Lane 指針

### `daily`

- 最近の差分・運用文書・README・設計メモのズレを見て、即日直す価値がある軽量な保全更新を行う。
- 代表例: `AGENTS.md` / `CLAUDE.md` / `MEMORY.md` / `docs/` の追従、古い記述の整理、FAQ 追記。

### `drift`

- 実装と文書・設定・ディレクトリ構成の drift を重点的に監査する。
- 代表例: 使われない文書の統合、obsolete な説明の削除、phase 内で許可された設定の追従。

### `weekly`

- 重複ルールの統合、死文化したノートの整理、週次でまとめて直す方がよい保全項目を扱う。
- 代表例: docs の章立て整理、冗長な運用記述の圧縮、repeated rationale の統合。

## Phase ガード

### Phase 1

- 対象は docs / knowledge / cleanup。
- `AGENTS.md` `CLAUDE.md` `MEMORY.md` `docs/` と、allowed paths 内の文書・記録系だけを触る。
- アプリコードや実行スクリプトの変更はしない。

### Phase 2

- Phase 1 に加えて config / template / CI を扱ってよい。
- `.github/`、template、設定ファイル更新は可。実装コードはまだ触らない。

### Phase 3

- allowed paths 内ならコードやスクリプトまで対象にしてよい。
- ただし大きい変更でも、今回の lane の目的に直接必要な範囲に留める。

## 実行フロー

1. `.devkit/repo-maintainer.toml` と、lane に関係するファイルだけを読む。
1. 変更候補を allowed paths と phase に照らして絞る。
1. 安全で根拠のある更新だけ実施する。
1. 最後に次の情報を返す。
   - `goal`
   - `summary`
   - `successes`
   - `gaps`
   - `update_targets`

## 重要

- root cause のないルール追加はしない。
- 「ついで修正」で scope を広げない。
- repo 固有の commit 規約や review 規約があっても、この skill 自体は commit しない。
