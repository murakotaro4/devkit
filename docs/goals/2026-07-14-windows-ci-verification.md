# Goal Prompt: Windows 検証の CI 化（pwsh スモーク + winget フォント実験）

## 目的

対象 repo: `~/repos/devkit`（実装は worktree 分離）。長年の残課題「Windows 実機検証」のうち CI で担保可能な 3 点を GitHub Actions（windows-latest）へ移し、実機が必要な範囲を Claude Code まわりの一度きりの確認だけに縮める。

1. **pwsh スモーク**: `update-ccx.ps1` / `devkit-lib.ps1` の自己更新経路を実 PowerShell で毎 PR 検証する（v8.0.0 で大改修したのに pwsh 実機テストが未実施というギャップの解消）。
2. **sync_updater.py の Windows 実実行**: tmp_path シミュレーションでなく runner の実 USERPROFILE に対する `--check` → 本実行 → 冪等 no-op を検証する。
3. **winget フォント実験**: 「`winget install DEVCOM.JetBrainsMonoNerdFont` 後のレジストリ登録名が `setup_terminal_font.py` の検出述語（`font_is_registered` / FONT_FACE = "JetBrainsMono NF"）と一致するか」への答えを CI 上で出す。

## 確定済み設計

- 既存 `devkit-checks.yml` の 2 job（ubuntu / windows の verify-full）は変更しない。新規 job の追加のみ。新規 workflow ファイルは作らず `devkit-checks.yml` へ追加する。
- pwsh スモーク job（windows-latest、PR ごとに実行）。job 名は `devkit-checks-windows-updater-smoke` に固定する（既存 job は `devkit-checks` / `devkit-checks-windows`。名前を変える場合は逸脱として進捗ログへ記録し、検証 jq も同時に更新する）。branch protection / ruleset は変更せず、required check の設定もしない。merge ゲートは「親が merge 前に `gh pr checks` の JSON 出力から下記 3 job の名前集合を固定 assert する」契約とする。検証フェーズと状態遷移を workflow / スクリプトに明示する:
  - **フェーズ A（sync_updater.py 実実行）**: クリーンな USERPROFILE に対し、(1) stale 状態を仕込む — `$env:USERPROFILE\.codex\bin` に旧内容のダミー update-ccx.ps1 と update-devkit.{sh,ps1,cmd} 残骸、`~/.local/bin` に update-devkit 残骸を配置 → (2) `--check` が `changed=true` + copy/prune の actions を予告し、かつ書き込みしない（配置物が不変）→ (3) 本実行が `changed=true` で同期・prune を実施 → (4) 再実行が `changed=false` / `actions=[]` の no-op、を JSON 出力の assert で検証する。
  - **フェーズ B（update-ccx.ps1 自己更新経路）**: (0) source root の pull 経路を排除する — job は pull_request イベントで実行し（actions/checkout は PR で detached HEAD を作る）、スモークスクリプトの冒頭で source root（checkout）が detached HEAD であることを assert する（detached でなければ即 fail。`Get-DevKitRepoRoot` は通常ブランチの source root でのみ `git pull --ff-only` を実行するため、detached なら pull は走らない）。`.git` を除いた一時コピーを source root にする案は不可（`DEVKIT_SOURCE_ROOT` の解決は git repo を要求し、非 git の非空ディレクトリは `DEVKIT_SOURCE_ROOT_NOT_EMPTY` で fail する）。(1) 起動元を明示する — 初回は source root の `plugins/devkit/scripts/update-ccx.ps1` を `--devkit-only` で実行し、managed copy（update-ccx.ps1 / update-ccx.cmd / devkit-lib.ps1 / devkit-setup.ps1 / devkit-codex-config.ps1 → `$env:USERPROFILE\.codex\bin`）と `~/.local/bin` の update-ccx.cmd shim、事前に仕込んだ update-devkit 残骸の prune を assert する → (2) 2 回目は**インストール済みの** `$env:USERPROFILE\.codex\bin\update-ccx.ps1` から `--devkit-only` で再実行し、インストール済み updater からの自己更新経路が成立すること・結果が冪等であることを assert する。git clone・追加ネットワークアクセスを前提にしない。codex CLI 不在の runner でも devkit-only 経路が成立すること。
  - フェーズ A と B は USERPROFILE の状態を共有しないよう、フェーズ境界で対象パス（`.codex\bin`・`~/.local/bin` の管理対象）を初期化してから次フェーズの前提状態を仕込む。
  - 検証ロジックは `scripts/ci/` 配下のスクリプト（pwsh または Python）に置き、workflow からは呼ぶだけにする。assert 失敗は非ゼロ exit で job を fail させる。
- winget フォント実験 job（windows-latest、`continue-on-error: true`、required にしない）:
  - `workflow_dispatch` はデフォルトブランチに定義がないと起動できないため、PR トリガーでも実行される形にして PR 上で答えを出し、merge 後は `workflow_dispatch` でも再実行できるようにする。
  - 実験スクリプトは判定を明示的な状態値で出力する。分類は決定論的に次で定義する: `WINGET_UNAVAILABLE` =`Get-Command winget` が不在、または `winget --version` が非ゼロ exit / `INSTALL_FAILED` = `winget --version` は成功したが install コマンドが非ゼロ exit（exit code とエラー出力を添付）/ `REGISTERED_MATCH` = install 成功かつ `font_is_registered` が True / `REGISTERED_MISMATCH` = install 成功だが述語が False（実測レジストリ値名一覧を添付）。
  - 実験スクリプトは機械照合用の単一行 `FONT_EXPERIMENT_RESULT=<状態値>` を stdout（run ログ）へ必ず出力し、step summary は `if: always()` で必ず生成して、状態値・実測レジストリ値名・runner image 情報（`ImageOS` / `ImageVersion` / pwsh バージョン / winget バージョン）を書く。
  - 「答えが出た」= 上記 4 状態のいずれかが summary に記録されたこと。スクリプト自体の不具合による fail（状態値が出ない）は答えとして扱わず修正する。
- pwsh スモークで `update-ccx.ps1` / `devkit-lib.ps1` / `sync_updater.py` のバグが見つかった場合は修正もスコープに含める。挙動修正時は `plugins/devkit/scripts/README.md`、sync_updater の契約（フラグ・JSON 形式）が変わる場合は `plugins/devkit/skills/setup/SKILL.md` も同期する（repo のドキュメント同期ルール）。
- 本ゴールファイルを commit するため、`plugins/devkit/premises.json` の各 premise occurrences へ本ファイルの出現を登録する（docs/goals は exact count 対象。scan 除外は使わない）。
- version bump: `plugins/devkit/**`（premises.json 含む）に変更が入るため Release Rules に従い bump する（CI 追加のみなら patch、ps1 の挙動修正が入っても patch〜minor を保守的に判断）。bump の直前に `git fetch origin` を再実行し、origin/main が進んでいれば先に rebase で取り込み（衝突は AGENTS.md「統合時 rebase 衝突の標準解消手順」のクラスのみ機械解消、それ以外は停止・報告）、最新 origin 値から一度だけ bump する。

## 成功条件(検証可能)

1. worktree で `uv run --project plugins/devkit python plugins/devkit/scripts/devkit_harness.py verify-full` が exit 0。
2. PR が作成され、`gh pr checks <PR番号> --json name,bucket` の出力で、`devkit-checks` / `devkit-checks-windows` / `devkit-checks-windows-updater-smoke` の 3 job がそれぞれちょうど 1 件存在し、いずれも bucket が `pass`（下記 jq で assert。winget 実験 job には green を要求しない）。
3. pwsh スモークのフェーズ A/B の検証内容（状態仕込み / JSON 遷移 changed=true→true→false / 起動元 2 種 / managed copy 集合 / shim / 残骸 prune / 冪等性）が workflow と `scripts/ci/` のスクリプトに実在し、PR 上の run ログで実際に実行・assert されたことが確認できる。
4. winget 実験 job が PR 上で 1 回以上実行され、run ログから `FONT_EXPERIMENT_RESULT=<状態値>` が 4 状態の列挙に限定した抽出でちょうど 1 種類得られ（検証コマンドの grep + count assert で機械確認）、step summary に状態値・実測レジストリ値名（取得できた場合）・runner image 情報が記録され、その結論が完了レポートへ転記されている。
5. PR が merge され、`git fetch origin` 後に `git merge-base --is-ancestor <PR head SHA> origin/main` が真（merge commit 経由で origin/main に到達可能）。
6. `plugins/devkit/**` に変更が入った場合、plugin version が Release Rules に従い bump されている（pre-push gate と CI の version gate が検証する）。
7. 独立レビューの客観的証跡: 最終ラウンドのレビューログが `.claude/goal-runs/2026-07-14-windows-ci-verification-review-<n>.log` に保存され、指摘ゼロであり、レビュー対象 commit SHA が merge 時点の PR head SHA（`gh pr view <PR番号> --json headRefOid`）と一致し、その SHA と最終結果が完了レポートに転記されている。

## 検証コマンド

```bash
cd <worktree>
set -o pipefail
uv run --project plugins/devkit python plugins/devkit/scripts/devkit_harness.py verify-full
gh pr checks <PR番号> --json name,bucket \
  | jq -e 'def ok($n): [.[] | select(.name == $n)] | length == 1 and .[0].bucket == "pass";
           ok("devkit-checks") and ok("devkit-checks-windows") and ok("devkit-checks-windows-updater-smoke")'    # 3 job の固定名 assert
gh pr view <PR番号> --json state,headRefOid   # merge 後 state=MERGED、headRefOid=レビュー済み SHA
git fetch origin && git merge-base --is-ancestor <PR head SHA> origin/main && echo "in main"
RESULT=$(gh run view <winget実験のrun-id> --log \
  | grep -Eo 'FONT_EXPERIMENT_RESULT=(WINGET_UNAVAILABLE|INSTALL_FAILED|REGISTERED_MATCH|REGISTERED_MISMATCH)' \
  | sort -u) && [ "$(printf '%s\n' "$RESULT" | grep -c .)" -eq 1 ] && echo "$RESULT"   # 4 状態限定・ちょうど 1 種類を assert し完了レポートへ転記
```

## 制約・非対象

- 既存 job（ubuntu / windows の verify-full）の step を変更しない。追加のみ。branch protection / ruleset を変更しない。
- runner 上の実書き込みは USERPROFILE 配下と一時領域に限る。secrets を追加しない。スモーク job に winget / 追加の外部ネットワーク前提を持ち込まない（winget は実験 job のみ）。
- Claude Code 実機の credential / statusline 検証はやらない（CI 化の対象外として残す）。
- `plugins/devkit/scripts/*.ps1` / `sync_updater.py` の変更は「CI で発見されたバグの修正」に限る。機能追加・リファクタはしない。
- 破壊的操作: force push・main の履歴改変・既存ブランチ削除は禁止。PR merge は repo 慣行どおり merge commit（`gh pr merge --merge`）で行う。
- ダミー実装・ハードコードの見せかけ結果・動いて見えるだけのモックで成功条件を満たしたことにしない（assert を持たない「常に green」の形骸 job を作らない。実験 job も状態値の出力を必須とする）。

## 停止条件(3 種)

- 達成停止: 成功条件 1-7 をすべて満たしたら停止する。
- 上限停止: 50 ターン。超過時は現状と残作業を完了レポートへ書いて停止する。
- 行き詰まり停止: 同じ blocker が続く、検証不能など。停止の前に blocker プロトコルを 1 回実行する: blocker と試行内容を進捗ログへ記録 → 代替アプローチを 2 案検討 → 最有力の案で続行を試みる。代替でも解消しない場合に停止する。
- 代替試行は write_scope・非対象・権限・破壊的操作の既存制約の内側の手段に限る。
- 外部入力が必須、権限が不足、秘密情報が必要、想定外の破壊的操作が必要な blocker は代替試行せず即停止する。
- CI 待ちはターン消費を抑えるため通知駆動・バックグラウンド監視で行い、空ポーリングの連打をしない。

## write_scope

- `.github/workflows/devkit-checks.yml`
- `scripts/ci/**`
- `plugins/devkit/scripts/update-ccx.ps1` / `devkit-lib.ps1`、`plugins/devkit/skills/setup/scripts/sync_updater.py`（バグ修正時のみ）
- `plugins/devkit/scripts/README.md`（ps1 / sync_updater の挙動修正時のみ同期）
- `plugins/devkit/skills/setup/SKILL.md`（sync_updater の契約変更時のみ同期）
- `plugins/devkit/tests/**`（バグ修正に伴う回帰テスト追加時のみ）
- `plugins/devkit/premises.json`(本ゴールファイルの出現登録 + check 失敗時の最小追従)
- `plugins/devkit/.claude-plugin/plugin.json`(version)
- `README.md`（CI の説明追従、およびスクリプト仕様変更時は `plugins/devkit/scripts/README.md` と両方を同期する — AGENTS.md の同期ルール）
- `docs/goals/2026-07-14-windows-ci-verification.md`（本ファイル。commit に含める）
- `.claude/goal-runs/**`（運用メタデータ。「制約・非対象」より常に優先して書き込み可）

## 実行戦略(実装系のみ)

- 作業場所: `git fetch origin` 後、origin/main 基点の worktree + 作業ブランチ（例: `feat/windows-ci-verification`）。本ゴールファイルを worktree へコピーし、premises 登録とセットで最初の節目 commit に含める。
- 実装労働の委譲先: codex exec。実行形: `codex -a never exec -C <worktree> --sandbox workspace-write -m gpt-5.6-sol -c model_reasoning_effort="medium" "<指示>" < /dev/null`。バックグラウンド起動時は `.claude/goal-runs/2026-07-14-windows-ci-verification-codex-<n>.log` へ出力し stdin を閉じる。1 ジョブ = 1 タスク登録、2〜5 分おきにログ増分を確認。
- 役割分担: 親が統括・検証・commit・push・PR 操作を担う。codex は commit しない（diff 作成まで）。
- 並列方針: この規模は直列でよい。
- CI 実走ループ: ブランチを push → `gh pr create` → checks 完了をバックグラウンドで待つ（`gh pr checks <PR番号> --watch` を run_in_background、または通知駆動）。fail したら `gh run view --log-failed` でログを取得して修正ループ。
- 最終順序の固定: 実装 → CI 修正ループで green + winget 実験の答え確認 → `git fetch origin` を再実行し、origin/main が進んでいれば rebase で取り込み → version bump を最新 origin 値から適用して push（CI が新 SHA で再実行されるので green を再確認）→ 最終 diff（`origin/main...HEAD`）に対する独立レビュー最終ラウンドで指摘ゼロ → レビュー対象 SHA = `gh pr view --json headRefOid` の PR head SHA と一致することを確認 → 以後 merge まで差分を変更しない → worktree で verify-full を最終再実行（ローカル実行のみで SHA は変わらない）→ `gh pr merge --merge`。レビュー後に差分が変わった場合（rebase・bump 含む）は必ず再レビューする。
- モデル / effort: codex 経路は `-m gpt-5.6-sol` + `model_reasoning_effort="medium"` 固定。
- 節目 commit: 親がパス限定で行い、Conventional Commits（日本語 summary）に従う。
- 戦略から逸脱が必要なら理由を進捗ログに記録して保守的に判断する。

## 進捗管理

- TaskCreate / TaskUpdate が使える場合はステップを登録し、開始時 in_progress、完了時 completed に更新する。
- 本ゴールで `.claude/goal-runs/` と書いたパスは main 作業ツリー側の絶対パス（`~/repos/devkit/.claude/goal-runs/`）を指す。worktree 側には作らない。
- 進捗ログ: `.claude/goal-runs/2026-07-14-windows-ci-verification-progress.md`。節目（委譲開始・完了、commit、push、CI 結果、レビュー、merge）ごとに追記する。
- 進捗ログの冒頭に「次にやること / 直近で決めた方針」の節を置き、節目ごとに毎回上書きする（コンテキスト圧縮後はまずここを読み直して復帰する）。

## 実装後レビュー

- 実装と別インスタンスの codex exec（read-only sandbox、gpt-5.6-sol / medium）へ diff 全文と本ゴールの成功条件を渡してレビューさせ、指摘ゼロになるまで修正 → 再レビューを繰り返す（repo ルールの独立レビュー必須要件）。
- 各ラウンドのログを `.claude/goal-runs/2026-07-14-windows-ci-verification-review-<n>.log` へ保存し、対象 commit SHA・ラウンド数・最終結果を進捗ログと完了レポートへ転記する。
- 最終ラウンドのレビュー対象 SHA は merge する PR head SHA と一致させる（レビュー後の変更は再レビュー）。レビュー通過後に verify-full を最終再実行してから merge する。

## 完了レポート

- 完了レポートを書く前に、ゴール本文と進捗ログ全体を読み返し、成功条件の未達・やり残しがないかを確認する。
- どの停止種別でも、終了時に `~/repos/devkit/.claude/goal-runs/2026-07-14-windows-ci-verification.md` へ完了レポートを書き出す。
- 記載項目: 停止種別 / 成功条件ごとの達成状況 / 検証コマンド結果 / winget 実験の答え（状態値・実測レジストリ値名・runner image 情報）/ 独立レビューの最終ログパス・対象 commit SHA（= PR head SHA）・ラウンド数 / 逸脱と判断ログ要約 / 残課題 / 変更ファイル一覧。
- `.claude/goal-runs/**` は write_scope より優先する運用メタデータ領域として常に書き込みを許可する。`.gitignore` が無ければ `*` 1 行で新規作成し、既存なら触らない。書き出し後に `git check-ignore` で検証する。
- 同名レポートは上書きせず `-2` からの連番にする。書き込み不能時はレポート全文を最終出力へ出す。

## 実行前提

- 実行中は質問不可。曖昧な点は保守的解釈 + 判断を進捗ログに記録する。
- 秘密情報・資格情報・トークンを本文・ログへ転記しない。gh の認証は環境の既存設定を使う。
