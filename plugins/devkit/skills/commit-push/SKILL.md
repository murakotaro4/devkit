---
name: "commit-push"
description: "未コミット変更を論理グループに分割し、グループごとに日本語 Conventional Commits で commit して、最後に upstream へ安全に push する。「コミットして push して」「変更をコミットして push して」「/commit-push」で起動"
argument-hint: "[scope]"
allowed-tools: ["Read", "Grep", "Glob", "Bash", "AskUserQuestion", "request_user_input", "TaskCreate", "TaskUpdate"]
---

# /commit-push - 論理分割 commit + upstream push

親エージェント = 未コミット変更の棚卸し、論理グループへの分割、安全検査、承認済みグループの commit、承認済み upstream への push、結果報告。各 commit は Conventional Commits の `<type>(<scope>): <summary>` を基本形とし、summary と本文は日本語で書く。レビュアー機能は持たず、コードレビューや独立レビューをこのスキル内では実施しない。

## 対象

$ARGUMENTS

## 共通契約

共通動作の正本として devkit リポジトリの `AGENTS.md`「スキル共通契約」を参照する。配布先に同ファイルがない場合でも実行できるよう、必要な要点を以下に自己完結で記す。

## ハーネス判定

- `AskUserQuestion` が使える → Claude 親。
- `AskUserQuestion` がなく `spawn_agent` が使える → Codex 親。
- どちらでもない場合は判定不能として扱う。
- `request_user_input` は plan mode 依存のため、ハーネスの判定キーには使わない。

## 質問手段

- Claude 親: `AskUserQuestion`
- Codex 親 plan mode: `request_user_input`
- Codex 親通常 mode / 判定不能: 選択肢を箇条書きで提示して自由文回答を求める

質問は分割案の承認に使う。承認後に対象ファイル、commit メッセージ、push 先のいずれかが変わった場合は、変更後の案を再提示して承認を取り直す。

## タスクリスト連動

Claude 親: `TaskCreate` / `TaskUpdate` が利用可能なら、workflow の step を登録し開始時 `in_progress`・完了時 `completed` に更新する。

Codex 親: 組み込み plan 機能または通常の進捗報告で同等の進捗提示を行う。

commit-push 開始時に step 1-7 を登録し、停止した step は未完了のまま停止理由を報告する。

## 安全契約

### commit

- 論理グループは最大 5 個とする。
- commit 前に、分割案（論理グループ・対象ファイル・コミットメッセージ案・解決済み push 先）を提示し、ユーザー承認を得る。
- バイナリ・巨大ファイルは内容検査不能として、承認前に明示する。
- `git add -A` / `git add .` / `git commit -a` を禁止する。
- add は `git --literal-pathspecs add -- <paths>` のみを使う。
- `--literal-pathspecs` は pathspec magic と glob 展開を無効化する。
- `--` はオプション終端であり path を literal 化しないため、`--literal-pathspecs` を必須とする。
- `--no-verify` などによる hook 迂回を禁止する。
- 開始時に既存の staged 変更があれば停止する。
- グループ単位で、index 空確認 → literal add → `git diff --cached --name-only` の完全一致確認 → commit → `git show --name-only --format= HEAD` で照合、という 5 段階検証を行う。

### secret 2 層検査

- パス層では secret-like path を対象から外して報告する。
- 内容層では commit 直前に staged diff へ既知パターン検査を行う。
- 内容層で secret を検出した場合は、自動除外して続行せず停止する。

secret-like path には `.env`、credentials、secrets、秘密鍵、証明書秘密鍵、token を示す名前などを含める。内容層では API key、access token、private key、password 代入などの既知パターンを検査する。検出内容の値をチャットやログへ転載せず、ファイルパスとパターン種別だけを報告する。バイナリ・巨大ファイルは内容層で安全を証明できないため、通常ファイルと同じ扱いで黙って commit しない。

### push

- push 前に `git rev-parse --abbrev-ref --symbolic-full-name @{u}` で upstream を解決し、承認提示に含める。
- push は `git push <remote> HEAD:<branch>` の明示単一 refspec のみを使う。
- force push・`--tags`・複数 ref を禁止する。
- upstream 不在・detached HEAD・origin なしでは push せず停止して報告する。
- push reject 時は fetch して状況を報告し、自動 rebase しない。

承認済みの remote と branch 以外へ push しない。push 直前の再解決結果が承認済み push 先と異なる場合も停止し、新しい分割案として再承認を得る。

## フロー

### 1. 開始時チェック

対象が git repo であること、現在の branch、remote 一覧、作業ツリーの状態を読み取る。`git diff --cached --quiet` 相当で index が空であることを確認する。既存 staged 変更が 1 件でもあれば、そのパスを報告して commit、unstage、push を行わず停止する。detached HEAD、upstream 不在、origin なしもここで検出し、完遂不能として変更を commit せず停止する。

### 2. 変更棚卸しとグループ分割

tracked、untracked、削除、rename を含む未コミット変更を読み取り、各ファイルの差分と役割を確認する。ユーザーが scope を指定した場合はその範囲だけを候補にする。1 ファイルを複数グループへ重複させず、同じ目的・理由・検証単位を持つ変更を 1 グループにまとめる。

論理グループは最大 5 個とする。6 個以上が必要なら勝手に統合せず、今回扱う範囲を絞る案または安全にまとめられる案を提示して確認する。各グループについて、目的、対象ファイル、差分概要、日本語 Conventional Commits のメッセージ案を作る。

承認案の準備として、`git rev-parse --abbrev-ref --symbolic-full-name @{u}` を実行し、出力を `<remote>/<branch>` に分解する。解決した remote と origin が remote 一覧に存在することを確認し、解決済み push 先を記録する。バイナリ・巨大ファイルは内容検査不能として、承認前に明示する。

### 3. secret パス層検査

候補ファイルのパスを secret-like path の既知パターンと照合する。パス層では secret-like path を対象から外して報告する。対象外にしたファイルはどのグループにも含めず、値や内容は表示しない。除外後にグループが空になった場合はそのグループを削除し、最大 5 グループの範囲で分割案を更新する。

### 4. 分割案のユーザー承認

commit 前に、分割案（論理グループ・対象ファイル・コミットメッセージ案・解決済み push 先）を提示し、ユーザー承認を得る。質問には「質問手段」のハーネス別手段を使う。承認されるまで add、commit、push を行わない。修正指定があれば分割、対象ファイル、メッセージ、push 先を更新し、全体を再提示する。

### 5. グループ単位の commit

承認された順に、各グループを次の 5 段階で処理する。途中で不一致、secret、hook 失敗、commit 失敗が起きたら後続グループへ進まず停止する。

1. **index 空確認**: `git diff --cached --quiet` 相当で index が空であることを確認する。空でなければ想定外の staged パスを報告して停止する。
2. **literal add**: 承認済みグループのパスだけを、add は `git --literal-pathspecs add -- <paths>` のみを使う。各 path はシェル引数として安全に引用し、承認されていない path を渡さない。
3. **staged 完全一致・内容層 secret 検査**: `git diff --cached --name-only` の結果が承認済みパス一覧と完全一致することを確認する。不一致なら commit せず停止する。続けて、内容層では commit 直前に staged diff へ既知パターン検査を行う。内容層で secret を検出した場合は、自動除外して続行せず停止する。
4. **commit**: 承認済みの日本語 Conventional Commits メッセージで commit する。hook は通常どおり実行させ、迂回オプションを付けない。
5. **commit 照合**: `git show --name-only --format= HEAD` の結果を承認済みパス一覧と照合する。不一致なら後続 commit と push を行わず停止する。照合後、次グループに進む前に index が空であることも確認する。

グループ単位で、index 空確認 → literal add → `git diff --cached --name-only` の完全一致確認 → commit → `git show --name-only --format= HEAD` で照合、という 5 段階検証を行う。

### 6. upstream 解決と push

全グループの commit と照合が完了した後、upstream、解決した remote、origin の存在を再確認する。push 前に `git rev-parse --abbrev-ref --symbolic-full-name @{u}` で upstream を解決し、承認提示に含める。再解決した `<remote>/<branch>` が承認済み push 先と完全一致する場合だけ次へ進む。

push は `git push <remote> HEAD:<branch>` の明示単一 refspec のみを使う。force push・`--tags`・複数 ref を禁止する。upstream 不在・detached HEAD・origin なしでは push せず停止して報告する。

push が reject された場合は、対象 remote を fetch して ahead / behind / diverged、reject 理由、現在の branch と upstream を読み取り、状況を報告して停止する。push reject 時は fetch して状況を報告し、自動 rebase しない。merge、rebase、force push、別 branch への push は行わない。

### 7. 結果報告

次を簡潔に報告する。

- 作成した commit の hash、メッセージ、対象ファイル
- 論理グループ数と各グループの成否
- secret-like path として対象外にしたパスの有無（秘密の値は記載しない）
- 内容検査不能として明示したバイナリ・巨大ファイルの有無
- 解決した upstream と実行した単一 refspec
- push の成否。失敗時は停止地点、reject 後の fetch 結果、ユーザーが判断すべき次の操作

## 禁止事項と境界

- レビュー、修正提案、テスト、lint、format はこのスキルの責務に含めない。ユーザーが commit 前レビューを求める場合は、このスキルを開始せず別工程で完了させる。
- `git add -A` / `git add .` / `git commit -a` を禁止する。
- `--no-verify` などによる hook 迂回を禁止する。
- force push・`--tags`・複数 ref を禁止する。
- secret 検出、対象パス不一致、hook 失敗、upstream 異常、push reject を自動修復して続行しない。
- ユーザー承認の範囲外にある変更を add、commit、discard、stash しない。
