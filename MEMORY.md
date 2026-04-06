# MEMORY.md

## Stable Facts

- `plugins/devkit/skills/*/SKILL.md` の YAML frontmatter は Codex の skill loader 前提なので、`mdformat` に直接通さない
- ローカルで skill を検証するときは `~/.codex/skills/*` の symlink が実在パスを向いていることを確認する
- この repo では、ファイル変更を伴う作業ごとに独立したサブエージェント review を必須とする
- 実装と運用がずれたら根拠を添えて更新する

## Decisions

- `repo-maintainer` 系の `SKILL.md` は `mdformat` 対象から外し、frontmatter は harness 側で別検査する

## Open Threads

- 他の `SKILL.md` も frontmatter 検査を共通化するかは次回見直す
