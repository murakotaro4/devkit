# Goal Prompt: update-ccx 一本化と setup 同期 step 追加

## 目的

対象 repo: `~/repos/devkit`（実装は worktree 分離）。

1. `/setup` 実行時に、インストール済み updater（update-ccx）が plugin 同梱の最新版へ同期されるようにする（新 step 追加）。
2. update-devkit 名義を全廃し、update-ccx を唯一の updater コマンドにする。配布物から削除し、インストール済み環境の残骸も prune する。`devkit-lib` はライブラリとして維持する。

背景: インストール済み updater は自分を実行したときしか自己更新されず、古い updater が壊れたまま残る事故（v7.0.1 未満の update-ccx.ps1）が既知。また update-devkit / update-ccx の二重名義は保守面積を増やしている。

## 確定済み設計

- 新規 `plugins/devkit/skills/setup/scripts/sync_updater.py`（cross-platform Python、`sync_rules.py` と同じ「冪等 + `--format json`（`changed` / `skipped` / `actions`）」様式、`--check` の dry-run を持つ）。
  - 同期ソースは plugin 同梱 `$SKILL_DIR/../../scripts/`。git clone・ネットワークアクセスは追加しない。
  - POSIX: `update-ccx.sh` / `devkit-lib.sh` を `~/.codex/bin/` へ（update-ccx.sh は実行権付与）、`~/.local/bin/update-ccx` に shell shim。shim 内容は `devkit-lib.sh` の `install_devkit_shell_shim` と同形式。
  - Windows: `update-ccx.ps1` / `update-ccx.cmd` / `devkit-lib.ps1` / `devkit-setup.ps1` / `devkit-codex-config.ps1` を `~/.codex/bin/` へ、`~/.local/bin/update-ccx.cmd` に cmd shim（`Install-DevKitCommandShim` と同形式）。
  - prune: `~/.codex/bin/update-devkit.{sh,ps1,cmd}`、`~/.local/bin/update-devkit`、`~/.local/bin/update-devkit.cmd` が存在すれば削除し actions に記録。
  - `~/.codex/devkit/source-root.txt` は変更しない。
- setup の `SKILL.md` に、thought-db 同期の後・statusline の前へ「updater 同期」step を追加する（ユーザー環境 step、Claude 親 / Codex 親どちらでも実行、承認ゲートなし、結果 JSON を報告）。「同期対象」「再実行時の動作」「検証とレポート」節も同期する。
- update-ccx 自身の自己更新も一本化に追従する:
  - `update-ccx.sh`: `section_managed_copy` の対象を update-ccx.sh + devkit-lib.sh に縮小し、shim も update-ccx のみ。update-devkit 残骸の prune を追加。usage・コメントから update-devkit を除去。
  - `devkit-lib.ps1`: `Install-DevKitManagedFiles` の対象から update-devkit.ps1 / update-devkit.cmd を除去し、shim も update-ccx.cmd のみ。legacy prune へ update-devkit 残骸を追加。
  - `update-ccx.ps1` / `update-ccx.cmd` の usage 文言も update-ccx へ統一。
- `plugins/devkit/scripts/update-devkit.sh` / `update-devkit.ps1` / `update-devkit.cmd` を削除する。
- ドキュメント同期: `README.md`（「update-devkit が主名称」節を「update-ccx が唯一の updater」へ再構成、トラブルシュートも update-ccx 名義へ）、`plugins/devkit/scripts/README.md`、`AGENTS.md`（言及があれば）。旧名称への言及は「廃止・移行注記」としてのみ残してよい。
- テスト: 新規 pytest（`sync_updater.py` 対象）を追加し、`test_update_bootstrap.py` 等の update-devkit 前提を更新する。
- `plugins/devkit/.claude-plugin/plugin.json` の version を major bump（origin/main の最新値から一度だけ適用。現時点想定 8.0.0）。

## 成功条件(検証可能)

1. `uv run --project plugins/devkit python plugins/devkit/scripts/devkit_harness.py verify-full` が exit 0。
2. `sync_updater.py` の新設 pytest が pass し、少なくとも次を検証している: 2 回目実行が no-op になる冪等性 / POSIX・Windows の同期対象集合 / shim 内容が devkit-lib 実装と同形式 / update-devkit 残骸の prune / `--check` が書き込みしないこと。
3. `/setup` への組み込みが決定論的に検査されている: `test_setup_skill.py`（または新設テスト）が「setup の `SKILL.md` に updater 同期 step が thought-db 同期の後・statusline の前に存在する」「`sync_updater.py` を参照している」「承認ゲートなしで JSON 結果（`changed` / `skipped` / `actions`）を報告する記載がある」を検査して pass する。
4. 自己更新経路の回帰テストが pass する: `test_update_bootstrap.py`（または新設テスト）が「`update-ccx.sh` の managed copy 対象と `devkit-lib.ps1` の `Install-DevKitManagedFiles` が update-devkit.* を配布しない」「update-devkit 残骸（`~/.codex/bin/update-devkit.{sh,ps1,cmd}`・`~/.local/bin/update-devkit{,.cmd}`）の prune 定義がある」を検査する。
5. `! ls plugins/devkit/scripts | grep -q update-devkit` が真（配布から削除済み）。
6. update-devkit 言及の残存が決定論的に検査されている: pytest（`test_document_consistency.py` への追加または新設テスト）が、repo 内の `update-devkit` 出現箇所を「旧名称の廃止・移行注記」と「prune 対象の文字列定義」の allowlist（ファイル単位または行パターン単位でテスト内に明記）に限定して検査し pass する。`templates/codex/config.shared.toml` のコメント等も追従する。
7. plugin version が major bump 済みで、本変更が origin/main へ統合されている（`git log origin/main --oneline` に本変更の commit がある）。
8. 独立レビューの客観的証跡がある: 最終ラウンドのレビューログが `.claude/goal-runs/2026-07-14-update-ccx-setup-sync-review-<n>.log` に保存され、指摘ゼロであり、レビュー対象の commit SHA と最終結果が完了レポートに転記されている。

## 検証コマンド

```bash
cd <worktree>
uv run --project plugins/devkit python plugins/devkit/scripts/devkit_harness.py verify-full
! ls plugins/devkit/scripts | grep -q update-devkit
rg -n "update-devkit" README.md AGENTS.md plugins/devkit -g '!plugins/devkit/tests/**'   # 補助的な目視用。pass/fail の判定は成功条件 6 の allowlist テストで行う
```

手動確認（ユーザー検収向け）: 統合後に `/setup` を他 repo で実行し、updater 同期 step の JSON 報告と `~/.codex/bin` / `~/.local/bin` の実体を確認する。

## write_scope

- `plugins/devkit/scripts/**`（update-devkit.{sh,ps1,cmd} の削除を含む）
- `plugins/devkit/skills/setup/**`
- `plugins/devkit/templates/**`（update-devkit 言及コメントの追従のみ。設定値は変えない）
- `plugins/devkit/tests/**`
- `README.md`、`AGENTS.md`、`plugins/devkit/scripts/README.md`
- `plugins/devkit/.claude-plugin/plugin.json`（version）
- `docs/goals/2026-07-14-update-ccx-setup-sync.md`（本ファイル。統合 commit に含めてよい）
- `.claude/goal-runs/**`（運用メタデータ。「制約・非対象」より常に優先して書き込み可）

## 制約・非対象

- setup から CLI（claude / codex）の更新、Codex marketplace / plugin 登録は行わない（update-ccx 本体の役割のまま）。
- setup の新 step に承認ゲートは置かない（ルール同期と同じ扱い）。
- 既存 step（ルール同期 / thought-db / statusline / フォント）の挙動を変えない。
- `plugins/devkit/premises.json` は原則変更不要（update-ccx は外部前提ではない）。check が失敗した場合のみ最小限で追従する。
- 削除してよいのは update-devkit 名義のファイル群とその言及だけ。互換 shim・fallback・後方互換経路は残さない（repo 方針）。
- 破壊的操作: update-devkit の配布削除と既存環境 prune は許可（本要件そのもの）。それ以外のファイル削除、force push、main の履歴改変、`~/.codex/config.toml` の変更は禁止。
- ダミー実装・ハードコードの見せかけ結果・動いて見えるだけのモックで成功条件を満たしたことにしない。

## 停止条件(3 種)

- 達成停止: 成功条件 1-8 をすべて満たし、origin/main への統合を確認したら停止する。
- 上限停止: 40 ターン。超過時は現状と残作業を完了レポートへ書いて停止する。
- 行き詰まり停止: 同じ blocker が続く、検証不能など。停止の前に blocker プロトコルを 1 回実行する: blocker と試行内容を進捗ログへ記録 → 代替アプローチを 2 案検討 → 最有力の案で続行を試みる。代替でも解消しない場合に停止する。
- 代替試行は write_scope・非対象・権限・破壊的操作の既存制約の内側の手段に限る。
- 外部入力が必須、権限が不足、秘密情報が必要、想定外の破壊的操作が必要な blocker は代替試行せず即停止する。

## 実行戦略(実装系のみ)

- 作業場所: 開始時に `git fetch origin` で origin/main との差を確認し、`git worktree` + 作業ブランチ（例: `feat/update-ccx-only-setup-sync`）で実装する。worktree 作成後、本ゴールファイル（`docs/goals/2026-07-14-update-ccx-setup-sync.md`）を worktree 側へコピーし、最初の節目 commit に含める（main 作業ツリー側の未追跡コピーは統合手順で処理する）。
- 実装労働の委譲先: すべて codex exec へ委譲する。実行形: `codex -a never exec -C <worktree> --sandbox workspace-write -m gpt-5.6-sol -c model_reasoning_effort="medium" "<指示>" < /dev/null`。バックグラウンド起動時はジョブごとのログファイル（`.claude/goal-runs/2026-07-14-update-ccx-setup-sync-codex-<n>.log`）へ出力し stdin を閉じる。1 ジョブ = 1 タスクとしてタスクリストへ登録し、待機中は 2〜5 分おきにログ増分を確認して停滞（増分ゼロ継続）を進捗ログへ記録する。ジョブが失敗・中断した場合は進捗ログへ記録し、指示を絞って再委譲する。
- 役割分担: 親（goal 実行エージェント）が統括・検証実行・commit を担う。codex（実装 backend）は commit しない（diff 作成まで）。
- 並列方針: write_scope が互いに素に分割できる場合のみ並列化する（例: scripts 刷新と tests / docs）。この規模は基本直列でよい。
- モデル / effort: codex 経路は `-m gpt-5.6-sol` + `model_reasoning_effort="medium"` 固定。
- 節目 commit: 親がパス限定で行い、Conventional Commits（日本語 summary）に従う。
- 統合手順（この順で実行し、逸脱は blocker 扱い。`<branch>` は作業ブランチ名、main 作業ツリーは `~/repos/devkit`）:
  1. `git fetch origin` → 作業ブランチを origin/main 最新へ rebase（衝突は devkit の `AGENTS.md`「統合時 rebase 衝突の標準解消手順」に列挙されたクラスのみ機械解消。version は rebase 完了後に最新 origin 値から major を一度だけ再適用）。
  2. worktree で verify-full を再実行し、pass を確認する。
  2b. rebase・version 再適用でブランチの diff（`git diff origin/main...<branch>`）が独立レビュー済みの内容から変化していないかを確認する。変化が `plugin.json` の version 行のみなら先へ進んでよい。それ以外の変化（衝突の機械解消による変化を含む）がある場合は、独立レビューを再実行して指摘ゼロを確認してから先へ進む。
  3. main 作業ツリーの状態を確認する: `git branch --show-current` が main、`git rev-parse main origin/main` が一致、`git status --porcelain` の残りが「本ゴールファイルの未追跡コピーのみ」であること。そのコピーがブランチ版と `cmp` で同一内容なら削除してから進む（内容が異なる、または他の dirty がある場合は外部要因として即停止し報告する）。
  4. main 作業ツリーで `git merge --ff-only <branch>` を実行し、`git push origin main` する（pre-push gate が version を検証する）。
  5. push が reject された場合の復旧（1 回だけ）: `git fetch origin` → main を `git reset --hard origin/main` で最新 origin へ戻す（未 push の ff 統合の取り消しであり、公開履歴の改変ではない）→ 作業ブランチを再度 rebase → version 再適用 → verify-full → 手順 2b（diff 変化の確認と必要なら再レビュー）→ 手順 3-4 を再実行する。それでも失敗したら停止・報告する。
  6. 成功後に worktree と作業ブランチを削除する。失敗停止時はブランチと worktree を残し、再開手順を完了レポートへ書く。
- 戦略から逸脱が必要なら理由を進捗ログに記録して保守的に判断する。

## 進捗管理

- TaskCreate / TaskUpdate が使える場合はステップを登録し、開始時 in_progress、完了時 completed に更新する。
- 本ゴールで `.claude/goal-runs/` と書いたパスはすべて main 作業ツリー側の絶対パス（`~/repos/devkit/.claude/goal-runs/`）を指す。worktree 側には作らない（worktree 削除で進捗ログ・レビュー証跡・完了レポートを失わないため）。
- 進捗ログ: `.claude/goal-runs/2026-07-14-update-ccx-setup-sync-progress.md`。節目（委譲開始・完了、commit、検証、レビュー、統合）ごとに追記し、判断・blocker・検証結果を記録する。
- 進捗ログの冒頭に「次にやること / 直近で決めた方針」の節を置き、節目ごとに毎回上書きする（コンテキスト圧縮後はまずここを読み直して復帰する）。

## 実装後レビュー

- 実装と別インスタンスの codex exec（read-only sandbox、gpt-5.6-sol / medium）へ diff 全文と本ゴールの成功条件を渡してレビューさせ、指摘ゼロになるまで修正 → 再レビューを繰り返す（repo ルールの独立レビュー必須要件）。
- 各ラウンドのレビューログを `.claude/goal-runs/2026-07-14-update-ccx-setup-sync-review-<n>.log` へ保存し、レビュー対象の commit SHA・ラウンド数・最終結果（指摘ゼロ）を進捗ログと完了レポートへ転記する。
- レビュー通過後に verify-full を最終再実行してから統合する。

## 完了レポート

- 完了レポートを書く前に、ゴール本文と進捗ログ全体を読み返し、成功条件の未達・やり残しがないかを確認する。
- 達成停止・上限停止・行き詰まり停止のどの停止種別でも、終了時に対象 repo の `.claude/goal-runs/2026-07-14-update-ccx-setup-sync.md` へ完了レポートを書き出す。
- 記載項目: 停止種別 / 成功条件ごとの達成状況 / 検証コマンド結果 / 独立レビューの最終ログパス・対象 commit SHA・ラウンド数 / 逸脱と判断ログ要約 / 残課題 / 変更ファイル一覧。
- `.claude/goal-runs/**` は「制約・非対象」や write_scope より優先する運用メタデータ領域として常に書き込みを許可する。
- 実行エージェントが `.claude/goal-runs/` と `.claude/goal-runs/.gitignore` を作成する。`.gitignore` が無ければ `*` 1 行で新規作成し、既存なら内容を触らない。
- 書き出し後に `git check-ignore` で検証し、ignore が効いていなければレポート末尾と停止報告へ警告を書く。
- 同名レポートは上書きせず、`2026-07-14-update-ccx-setup-sync-2.md` からの連番にする。
- 権限不足や read-only 実行環境で書き込み不能な場合は、レポート全文を進捗ログと最終出力へ出し、保存できなかった旨を明記する。

## 実行前提

- 実行中は質問不可。曖昧な点は保守的解釈 + 判断を進捗ログに記録する。
- 秘密情報・資格情報・トークンを本文・ログへ転記しない。必要な場合は環境に既に存在する設定を読む。
