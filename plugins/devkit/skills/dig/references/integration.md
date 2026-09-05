# 統合と完了

この文書は dig の step 9 または goal-prompt 引き継ぎを実行する直前だけ読む。

計画で確定した統合方法だけを実行する。

## PR 統合

PR 経路は提出 → CI 待機 → green 判定 → merge → 完了確認 → cleanup の順に行う。

- 統合直前に fetch / rebase し、必要な単調増加値を origin から再計算して再検証する。標準解消規則のない conflict は abort して停止する。
- checks の取得前後に head SHA を取得し、同じ SHA に束縛された checks だけを判定する。API・認証・通信エラーをチェック 0 件の成功と混同しない。0 件の扱いは計画した CI 有無と登録猶予に従い、観測した checks を優先する。
- green は全 checks が pass（skipping は許容）の場合だけ。赤・pending・期限超過では merge しない。merge queue / auto-merge が有効、または preflight が確認不能なら merge せず停止する。
- merge 直前の head が検証済み SHA と同じ場合だけ `gh pr merge <PR番号> --merge --match-head-commit <検証済みSHA>` を実行する。repo 規則の方式を明示し、`--delete-branch` は使わず、失敗時に別方式へ切り替えない。
- `gh pr view <PR番号> --json state,mergedAt` で `MERGED` を確認するまで統合完了としない。

cleanup は remote tip が検証済み SHA と一致することを確認してから行う。不在時も PR の headRefOid で同一性を確認する。remote branch は `git push --force-with-lease=refs/heads/<branch>:<検証済みSHA> origin :refs/heads/<branch>` で削除する。確認不能・不一致・lease 失敗は remote を削除せず「統合成功・cleanup 未完了」として報告する。

CI 赤・merge 失敗では PR を open のまま残し、worktree・branch・commit を破棄しない。

## 直接統合とローカル cleanup

直接統合は主 worktree が clean、既定 branch 上、非 diverged の場合だけ ff-only merge / push する。push reject は fetch / rebase / 再検証からやり直す。origin なしは ff-only merge で完了とする。

統合確認後だけ `git worktree remove <worktree>` を実行し、ローカル branch を削除する。merge commit 方式は `git merge-base --is-ancestor` で取り込み済みを確認して `git branch -d <branch>`、squash / rebase 方式は PR の state / mergedAt / headRefOid 一致を記録してから `git branch -D <branch>` を使う。worktree remove が拒否されたら `--force` を使わない。ジョブの write_scope をパス限定で add し、`git add .` / `git add -A` は使わない。

## 停止と完了報告

失敗時は変更を破棄せず、branch、worktree、停止操作、再開方法を報告する。完了報告には変更、検証、逸脱・仮定、残課題、commit、PR、CI、merge の `MERGED` 確認、cleanup 状態を含める。

## goal-prompt への引き継ぎ

ユーザーが明示した場合だけ、レビュー済み計画を `.claude/plans/YYYY-MM-DD-<slug>.md` へ保存して実装せず終了する。goal-prompt は追加承認や独立レビューをせず、意味を変えずに変換する。
