---
name: "repo-maintainer-init"
description: "各リポジトリに nightly maintainer 用の scaffold を生成する。`.devkit/repo-maintainer.toml`、MEMORY.md、logs/skills、reviews、PowerShell/POSIX wrapper、scheduler template を作る。'repo maintainer initして' 'nightly maintainer を入れて' で起動。"
allowed-tools: ["Read", "Grep", "Glob", "Bash", "Write", "Edit"]
---

# /repo-maintainer-init - Nightly Maintainer Scaffold

各 repo に nightly maintainer の最小構成を入れる。
shared skill 本体は DevKit 側を参照し、repo 側には **config / wrappers / scheduler templates だけ** を置く。

## トピック

$ARGUMENTS

## 生成対象

- `.devkit/repo-maintainer.toml`
- `MEMORY.md`
- `logs/skills/.gitkeep`
- `reviews/daily/.gitkeep`
- `reviews/weekly/.gitkeep`
- `.devkit/bin/repo-maintainer.ps1`
- `.devkit/bin/repo-maintainer.sh`
- `.devkit/scheduler/windows/register-task.ps1`
- `.devkit/scheduler/macos/*.plist`
- `.devkit/scheduler/linux/repo-maintainer.{service,timer,cron}`

## 実行ルール

1. 対象が Git repo か確認する。
1. 既存の `.devkit/repo-maintainer.toml` がある場合は内容を読んで、必要なら `--force` 再生成か手動追記かを判断する。
1. scaffold 生成は次の script を使う。

```bash
python plugins/devkit/scripts/repo_maintainer.py init-scaffold --repo <target-repo>
```

4. 既定値:
   - phase は `1`
   - nightly 時刻は `02:30`
   - forge は `github`
   - auto-merge は `true` だが `check_commands` 未設定なら実質 PR 止まり
1. scheduler 登録そのものは OS ごとの差が大きいので、まず template / wrapper を生成し、必要ならその場で登録スクリプトを実行する。

## 重要

- `repo-maintainer` skill 自体を repo に複製しない。
- repo 固有の allowed paths や check commands は `.devkit/repo-maintainer.toml` に寄せる。
- 既存 repo の commit/push は勝手に行わない。初期化後の確認はユーザーに見える差分として残す。
