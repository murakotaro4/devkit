# 実行経路

この文書は dig の step 3、6、7、8 を実行する直前だけ読む。

## backend 固定とフォールバック

| 役割 | 既定 |
|---|---|
| 実装 | cursor-agent `cursor-grok-4.6-high` |
| 計画レビュー | codex `gpt-5.6-sol` / medium |
| diff レビュー | codex `gpt-5.6-sol` / medium |

| 親 | 実装 lane | レビュー lane（計画 / diff 共通） |
|---|---|---|
| Claude 親 | cursor-agent → codex CLI → `Agent(general-purpose, model=sonnet)` → 停止 | codex CLI → `Agent(general-purpose, model=opus)` → 終端処理 |
| Codex 親 | cursor-agent → `spawn_agent` worker → 親実装 → 停止 | `spawn_agent` explorer → 終端処理 |
| 判定不能 | cursor-agent → codex CLI → 停止 | codex CLI → 終端処理 |

上から順に利用可能かつ降格条件に当たらない最初の段を使い、降格は前進だけとする。Codex 親は `codex exec` 入れ子と `claude` CLI 逆委譲を禁じるため codex CLI 段を飛ばす。実装 lane の降格前に前段ジョブの終了を確認し、同一 worktree に 2 つの実装 actor を同時に走らせない。実装 lane が尽きたら停止する。独立レビュー必須 repo でレビュー lane が尽きたら自動 skip せず停止する。必須でない repo だけ未実施を明記できる。降格先と理由を工程表と完了報告へ記し、**報告なしに fallback しない。**

降格条件は、可用性判定の失敗、起動失敗、レート制限の 3 分類。レート制限は非ゼロ終了かつ CLI 終了時エラーが `rate limit` / `rate_limit` / `ratelimit` / `quota` / `usage limit` / `too many requests` / `429` に一致する場合だけ。曖昧ならレート制限に分類せず降格しない。

- cursor-agent: `command -v cursor-agent`。chat 作成が非ゼロ終了 / `CHAT_ID` 空、または agent 起動前に失敗した場合を起動失敗とする。
- codex CLI: `command -v codex`。実装 / resume は `command -v uv` も必要。実装 / resume は非ゼロ終了で thread_id を採れない場合、レビューは起動そのものに失敗した場合だけ起動失敗とする。レビュー実行後の非ゼロは降格せず停止する。
- サブエージェント: 起動不能または応答不能を降格条件とする。

3 分類以外の非ゼロ終了は降格しない。実装 lane は通常の実装失敗として修正ループへ、レビュー lane は停止して報告する。

## Codex モデルと推論強度

Codex のモデルは `gpt-5.6-sol` を `-m` で明示し、`model_reasoning_effort="medium"` に固定する。ユーザーが別モデルを明示した場合だけ従う。Max は対応 surface の最深推論、Ultra は並列オーケストレーションの説明にだけ使う。世代追従は catch-up と `premises.json` で管理する。Codex 親の `spawn_agent` では子ごとの effort を選ばない。

## worktree 作成と実装委譲

git repo の実装系は必ず worktree を使う。非 git repo には worktree / commit / 統合を適用せず、diff と結果を報告する。

親が既定 branch を origin/HEAD、main、現在 branch の順で決める。origin があれば fetch し、無ければ fetch を省略して基点を `HEAD` にする。remote 名は `origin` 固定とし、`upstream` 等の別名だけの repo は origin なし扱いにする。一時 worktree と `<type>/<slug>` branch を作り、開始 commit を記録する。作業 branch が既存なら `-2` から連番を付ける。作成失敗時は主 worktree へ移らず停止する。

委譲指示は目的 / write_scope / 変更内容 / 受け入れ条件 / 検証 / commit 禁止を 1 ブロックにする。依存がなく write_scope が互いに素なジョブだけ並列化し、各担当は担当外変更とテスト実行を行わない。

codex はジョブごとの JOB_DIR に JSONL を保存し、`thread.started` の非空 thread_id が厳密に 1 件の場合だけ保存する。

```bash
JOB_DIR=$(mktemp -d "${TMPDIR:-/tmp}/devkit-codex-job.XXXXXX") && echo "JOB_DIR=$JOB_DIR"
JOB_DIR=<記録済みパス> && set -o pipefail && codex -a never exec -C "<worktree>" --sandbox workspace-write -m gpt-5.6-sol -c model_reasoning_effort="medium" --json "<実装指示>" < /dev/null | tee "$JOB_DIR/codex-events.jsonl"
JOB_DIR=<記録済みパス> && uv run --no-project --python ">=3.10" python -c 'import json,sys; ids=[event.get("thread_id") for line in open(sys.argv[1], encoding="utf-8") if line.strip() for event in [json.loads(line)] if event.get("type") == "thread.started"]; (len(ids) == 1 and isinstance(ids[0], str) and ids[0]) or sys.exit("expected exactly one non-empty thread.started thread_id"); print(ids[0])' "$JOB_DIR/codex-events.jsonl" > "$JOB_DIR/thread-id.txt" && test -s "$JOB_DIR/thread-id.txt"
```

cursor-agent は chatId と stdout / stderr を JOB_DIR に保存する。sandbox なしで動くため write_scope と commit 禁止を明記する。

```bash
JOB_DIR=$(mktemp -d "${TMPDIR:-/tmp}/devkit-dig-job.XXXXXX") && set -o pipefail && CHAT_ID="$(cursor-agent create-chat < /dev/null | tr -d '\r\n')" && test -n "$CHAT_ID" && printf '%s\n' "$CHAT_ID" > "$JOB_DIR/chat-id.txt" && echo "JOB_DIR=$JOB_DIR"
JOB_DIR=<記録済みパス> && set -o pipefail && cursor-agent -p --resume "$(cat "$JOB_DIR/chat-id.txt")" --trust --force --model cursor-grok-4.6-high --workspace "<worktree>" --output-format text "<実装指示>" < /dev/null 2>&1 | tee "$JOB_DIR/cursor-agent.log"
```

すべての非対話 codex / cursor-agent コマンドで stdin を `< /dev/null` に閉じる。

### 節目 commit

実装 backend は commit しない。親がジョブを回収し、そのジョブの write_scope をパス限定で add して commit する。pre-commit が unstaged 変更を stash する repo では全ジョブ回収後にジョブ単位で順に commit する。

## 自レビューと独立 diff レビュー

親が基点からの diff 全文を計画と照合し、テスト・lint を実行する。**レビュー前に実装を作業 branch へ commit しておく。** `review --base` は commit 済み差分だけを対象とする。独立 backend は実装 worker と同じ agent を使わない。

```bash
codex -a never exec -C "<worktree>" -m gpt-5.6-sol -c model_reasoning_effort="medium" review --base origin/<default> < /dev/null
```

origin なしは `--base <default>`。必須 repo でレビュー lane が尽きたら停止する。

## 修正ループ

| backend | resume 差分 |
|---|---|
| codex | `exec resume` + `"$(cat "$JOB_DIR/thread-id.txt")"` + `"<指摘と修正指示>"` |
| cursor-agent | `--resume "$(cat "$JOB_DIR/chat-id.txt")"` + `"<指摘と修正指示>"` |
| Codex 親 worker | 生存中は `send_input`、close 済みは新しい `spawn_agent` worker |

修正中に降格条件へ当たった場合は次段へ進み、chat / thread の文脈を引き継がず現在の diff と未解消 findings を渡す。以後は前段へ戻らない。

```bash
JOB_DIR=<記録済みパス> && test -s "$JOB_DIR/thread-id.txt" && codex -a never -C "<worktree>" --sandbox workspace-write exec resume -m gpt-5.6-sol -c model_reasoning_effort="medium" "$(cat "$JOB_DIR/thread-id.txt")" "<指摘と修正指示>" < /dev/null
```

cursor-agent は worktree 作成節の完全形を使い、最終引数だけ修正指示へ替える。指摘がゼロで終了する。第 1 巡は最初の独立レビュー。件数は重複除去後の actionable findings 総数。件数が前巡以上の状態が 2 巡連続した / 同一 finding（同じファイル・箇所・根本原因。文言一致ではない）が 2 巡連続で再出した / 20 巡に達した場合は停止して判断を求める。
