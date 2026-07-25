---
name: "commit-push"
description: "未コミット変更を論理グループに分割し、グループごとに日本語 Conventional Commits で commit して、最後に upstream へ安全に push する。「コミットして push して」「変更をコミットして push して」「/commit-push」で起動"
argument-hint: "[scope]"
allowed-tools: ["Read", "Grep", "Glob", "Bash", "AskUserQuestion", "request_user_input", "TaskCreate", "TaskUpdate"]
---

# /commit-push - 論理分割 commit + upstream push

未コミット変更を論理グループへ分け、承認済み範囲だけ commit し、解決済み upstream へ安全に push する。各 commit は `<type>(<scope>): <summary>` 形式の Conventional Commits、summary と本文は日本語とする。レビュー・修正・テスト・lint・format は責務外。

## 対象

$ARGUMENTS

## ハーネス判定

`request_user_input` は判定キーに使わない。

| 判定 | 分割案の質問・承認 | 進捗 |
|---|---|---|
| `AskUserQuestion` が使える Claude 親 | `AskUserQuestion` | TaskCreate / TaskUpdate |
| 上記がなく `spawn_agent` が使える Codex 親 | plan mode は `request_user_input`、通常 mode は選択肢 + 自由文 | plan または進捗報告 |
| 判定不能 | 選択肢 + 自由文 | 進捗報告 |

step 1-7 をタスク化する。承認後に対象ファイル、メッセージ、push 先が変われば全案を再承認する。

## 安全契約

### commit

- 開始時に既存 staged 変更があれば、commit / unstage / push せず停止する。
- 論理グループは最大 5 個。ファイルを重複させず、目的・理由・検証単位から分割はエージェントが判断する。6 個以上なら範囲縮小か安全な統合案を確認する。
- commit 前に、各グループの目的・対象ファイル・差分概要・日本語 Conventional Commits 案、解決済み push 先、内容検査不能なバイナリ・巨大ファイルを提示して承認を得る。
- add は承認済み path だけを `git --literal-pathspecs add -- <paths>` で行う。`git add -A` / `git add .` / `git commit -a`、hook を迂回する `--no-verify` は禁止。
- 各グループで `index 空 → literal add → staged path 完全一致 + 内容 secret 検査 → commit → commit path 完全一致 + index 空` を満たす。不一致や失敗では後続 commit と push を止める。

### secret 2 層検査

| 層 | 不変条件 |
|---|---|
| path | `.env`、credentials、secrets、秘密鍵、token 等の secret-like path を対象外にして報告 |
| staged 内容 | commit 直前に API key、access token、private key、password 代入等の既知パターンを検査 |

値は表示しない。内容層で検出したら自動除外せず停止する。バイナリ・巨大ファイルは安全を証明できないものとして承認前に明示する。

### push

- `git rev-parse --abbrev-ref --symbolic-full-name @{u}` で upstream を解決し、承認時と push 直前の remote / branch が完全一致する場合だけ進む。
- push は承認済み先への `git push <remote> HEAD:<branch>` という明示単一 refspec を 1 回だけ使う。force push、`--tags`、複数 ref は禁止。
- upstream 不在、detached HEAD、origin なしは push しない。自動で upstream を設定しない。
- reject 時は対象 remote を fetch して ahead / behind / diverged と理由を報告し、自動 rebase / merge / force push / 別 branch push はしない。

## フロー

### 1. 開始時チェック

git repo、branch、remote、作業ツリー、index を確認する。push 不可条件は記録するが、既存 staged 変更以外は commit 自体を妨げない。

### 2. 変更棚卸しと分割

指定 scope 内の tracked / untracked / delete / rename と差分を読み、安全契約に従って最大 5 グループの案を作る。upstream を解決し、解決不能なら「push なし」とする。

### 3. secret path 検査

secret-like path を全グループから除外し、値を出さず報告する。空になったグループは削除して案を更新する。

### 4. ユーザー承認

全グループと push 先を提示し、承認まで add / commit / push しない。

### 5. commit

承認順に安全契約の検証列を実行する。path 一覧は `git diff --cached --name-only` と `git show --name-only --format= HEAD` で照合する。secret、path 不一致、hook・commit 失敗時は index と作成済み commit を勝手に戻さず停止する。

### 6. push

全 commit の照合後、upstream と remote を再解決する。承認済み先と一致したときだけ明示単一 refspecで push する。「push なし」承認なら commit のみで終了する。

### 7. 結果報告

commit hash・メッセージ・対象ファイル、グループ別成否、secret-like path 除外と内容検査不能ファイルの有無、upstream と単一 refspec、push 結果を報告する。失敗時は停止地点と、ユーザー判断が必要な次の操作を示す。

## 境界

承認外の変更を add / commit / discard / stash しない。commit 前レビューが必要なら、このスキル開始前に別工程で完了させる。
