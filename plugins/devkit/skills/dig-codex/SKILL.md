---
name: "dig-codex"
description: "dig の Codex adapter。Plan Mode 必須で request_user_input を使い dig-core 契約を実行する。"
argument-hint: "[topic]"
allowed-tools: ["Read", "Grep", "Glob", "Bash"]
---

# /dig-codex - Codex Adapter

## 実行契約

- Plan Mode 必須
- 質問: `request_user_input`
- レビュー実行コマンド（REVIEW_GATE_PLAN 用・サニタイズ済みファイル経由）:
  - `REVIEW_PRIMARY_CMD: codex exec -m gpt-5.3-codex-spark -c model_reasoning_effort="medium"`
  - `REVIEW_FALLBACK_CMD: codex exec -m gpt-5.4 -c model_reasoning_effort="medium"`
  - サニタイズ手順: `dig_sanitize $PLAN_FILE /tmp/dig_codex_plan_review_$$.md` → サニタイズ済みファイルでレビュー → `rm -f`
  - dig_sanitize が非0を返した場合（return 1: HIGH_ENTROPY、return 2: cp/sed失敗）は `cancel_all` → `STOP(DIG_CODEX_PLAN_SANITIZE_BLOCKED)`
- タイムアウト/リトライ:
  - `REVIEW_TIMEOUT_SECONDS: 180`
  - `REVIEW_BACKOFF_SECONDS: 5`
  - `REVIEW_RETRY_POLICY: no_same_model_retry_one_fallback_hop`

## 共通サニタイズ関数

```bash
dig_sanitize() {
  local src="$1" dst="$2"
  cp "$src" "$dst" || { echo "SANITIZE_CP_FAILED"; return 2; }
  sed -i -E 's/(api[_-]?key|secret|token|password|credential|private[_-]?key)\s*[=:]\s*\S+/\1=***REDACTED***/gi' "$dst" || { echo "SANITIZE_SED_FAILED"; return 2; }
  sed -i -E 's/(Bearer\s+)\S+/\1***REDACTED***/gi' "$dst" || { echo "SANITIZE_SED_FAILED"; return 2; }
  sed -i -E 's/(Authorization\s*[: ]+)(Basic|Bearer|Token|Digest)?\s*\S+/\1***REDACTED***/gi' "$dst" || { echo "SANITIZE_SED_FAILED"; return 2; }
  sed -i '/-----BEGIN.*PRIVATE KEY-----/,/-----END.*PRIVATE KEY-----/c\***PEM_REDACTED***' "$dst" || { echo "SANITIZE_SED_FAILED"; return 2; }
  sed -i -E 's/("(api[_-]?key|secret|token|password)"\s*:\s*")[^"]+"/\1***REDACTED***"/gi' "$dst" || { echo "SANITIZE_SED_FAILED"; return 2; }
  sed -i -E 's/([?&](token|key|secret|api_key)=)[^&\s]+/\1***REDACTED***/gi' "$dst" || { echo "SANITIZE_SED_FAILED"; return 2; }
  [ -s "$dst" ] || { echo "SANITIZE_OUTPUT_EMPTY"; return 2; }
  if grep -qE '[A-Za-z0-9+/=]{64,}' "$dst"; then
    echo "HIGH_ENTROPY_DETECTED"
    return 1
  fi
  return 0
}
```

## タスク管理: Bash経由テキスト追跡

Codex の allowed-tools は `["Read", "Grep", "Glob", "Bash"]` のため、TaskCreate/Write/Edit は使用不可。Bash 経由でプランファイルにタスク追跡セクションを追記。

**プランファイル所在規約**: Plan Mode が明示的に渡したパスのみを `$PLAN_FILE` として使用する。パスが得られない場合は `STOP(DIG_CODEX_PLAN_REQUIRED)` で停止する（自動生成しない）。

**冪等性**: 追記前に既存セクションの有無を確認し、重複を防止:

```bash
PLAN_FILE="<Plan Mode が提供するパス>"

# 冪等追記: 既存の「## タスク追跡」がなければ追加
if ! grep -q "^## タスク追跡" "$PLAN_FILE" 2>/dev/null; then
  cat >> "$PLAN_FILE" << 'EOF'

## タスク追跡
EOF
fi

# タスク追加: 番号ベースで重複チェック
add_task() {
  local num="$1" desc="$2" deps="$3"
  if ! grep -q "\[Task $num\]" "$PLAN_FILE"; then
    echo "- [ ] [Task $num] $desc${deps:+ (blocked by: $deps)}" >> "$PLAN_FILE"
  fi
}

# 完了マーク: 番号で一意指定
mark_done() {
  local num="$1"
  sed -i "s/- \[ \] \[Task $num\]/- [x] [Task $num]/" "$PLAN_FILE"
}

# 停止時の全タスク取消
cancel_all() {
  sed -i 's/- \[ \]/- [x] CANCELLED/g' "$PLAN_FILE"
}
```

## 状態遷移

```
INIT -> PLAN_CHECK -> INTERVIEW -> REVIEW_DECOMP? -> REVIEW_PRIMARY -> REVIEW_FALLBACK? -> REVIEW_PARSE -> REVIEW_GATE -> DONE
```

- Plan Mode true: 上記フロー
- Plan Mode false: `PLAN_CHECK -> STOP(DIG_CODEX_PLAN_REQUIRED)`
- `REVIEW_DECOMP` は Step 3 実行時のみ遷移（スキップ時は INTERVIEW → REVIEW_PRIMARY）
- Step 3 スキップ時（単純タスク）:
  1. Step 2 完了後（dig-core 契約のタスク登録タイミング）に `## タスク追跡` セクションを `$PLAN_FILE` に冪等追記
  2. 最小限のプラン内容（Step 1-2 の要約 + 実装手順）を `$PLAN_FILE` に `cat >>` で追記し、`REVIEW_PRIMARY` の入力を保証
  3. REVIEW_GATE 通過後に計画完了として DONE 遷移（Codex は計画専用。実行は dig-claude に委譲）
- `REVIEW_PRIMARY` が unavailable の場合は 5 秒待機後 `REVIEW_FALLBACK` を 1 回だけ実行
- `REVIEW_PRIMARY/REVIEW_FALLBACK` とも unavailable の場合は `cancel_all` → `STOP(DIG_CODEX_PLAN_REVIEW_UNAVAILABLE)`
- `REVIEW_PARSE` で `REVIEW_COUNTS` が読めない場合は `cancel_all` → `STOP(DIG_CODEX_PLAN_REVIEW_UNAVAILABLE)`
- `REVIEW_GATE` で `critical>0 || high>0` の場合は `cancel_all` → `STOP(DIG_CODEX_PLAN_REVIEW_BLOCKED)`
- **停止時 cleanup 契約**: タスク追跡セクション追記済みの STOP 遷移の直前に `cancel_all` を実行し、プランファイルの全チェックボックスを `[x] CANCELLED` に更新する（dig-core 停止時タスク cleanup 契約準拠）。早期退出パス（`DIG_CODEX_PLAN_REQUIRED`: Plan Mode 無効で追跡セクション未作成）は cleanup 対象外

### REVIEW_DECOMP 専用状態遷移

`codex -a never exec review --uncommitted` は git diff 用なので分解テキストレビューには不適切。REVIEW_DECOMP は `codex exec` 専用経路を使用:

```
REVIEW_DECOMP 状態遷移:
  INTERVIEW -> REVIEW_DECOMP_PRIMARY -> REVIEW_DECOMP_FALLBACK? -> REVIEW_DECOMP_PARSE -> REVIEW_DECOMP_GATE -> REVIEW_PRIMARY

コマンド:
  REVIEW_DECOMP_PRIMARY_CMD: codex exec -m gpt-5.3-codex-spark -c model_reasoning_effort="medium"
  REVIEW_DECOMP_FALLBACK_CMD: codex exec -m gpt-5.4 -c model_reasoning_effort="medium"
  REVIEW_DECOMP_TIMEOUT_SECONDS: 180
  REVIEW_DECOMP_RETRY_POLICY: no_same_model_retry_one_fallback_hop
```

サニタイズ手順:
1. `dig_sanitize $PLAN_FILE /tmp/dig_codex_decomp_review_$$.md`
2. dig_sanitize が非0を返した場合は `cancel_all` → 即停止:
   - return 1 (HIGH_ENTROPY_DETECTED): `cancel_all` → `STOP(DIG_CODEX_DECOMP_SANITIZE_BLOCKED)`
   - return 2 (cp/sed失敗・空出力): `cancel_all` → `STOP(DIG_CODEX_DECOMP_SANITIZE_BLOCKED)`
   - Codex は AskUserQuestion 不可のため、非0は全て即停止
3. サニタイズ済みファイルでレビュー実行:
   ```bash
   $REVIEW_DECOMP_PRIMARY_CMD "以下のファイルのタスク分解セクションをレビューしてください: /tmp/dig_codex_decomp_review_$$.md。
     観点: 網羅性・粒度・依存関係の矛盾を確認。
     最終行に REVIEW_RESULT_MARKER=REVIEW_COUNTS と REVIEW_COUNTS critical=<int> high=<int> を出力"
   ```
4. `rm -f /tmp/dig_codex_decomp_review_$$.md`

unavailable 判定: 既存ルールと同一（非0終了コード、429、transport切断、認証エラー、タイムアウト）。

REVIEW_DECOMP 停止時 cleanup:
- REVIEW_DECOMP_PRIMARY + FALLBACK 両方 unavailable: `cancel_all` → `STOP(DIG_CODEX_DECOMP_REVIEW_UNAVAILABLE)`
- REVIEW_DECOMP_PARSE 失敗: `cancel_all` → `STOP(DIG_CODEX_DECOMP_REVIEW_UNAVAILABLE)`
- REVIEW_DECOMP_GATE で critical/high 未解消: `cancel_all` → `STOP(DIG_CODEX_DECOMP_REVIEW_BLOCKED)`

## unavailable 判定

- 以下は unavailable として扱う:
  - プロセス終了コードが非 0
  - rate limit (`429`)
  - transport 切断（websocket/http disconnected）
  - 認証エラー
  - タイムアウト（180 秒）

## 非Plan時の停止文

- `ERROR_CODE: DIG_CODEX_PLAN_REQUIRED`
- `RERUN_COMMAND: $dig <topic>`
- `DIAGNOSTIC_COMMAND: echo current_mode_is_plan`

## 停止コード

| コード | 条件 |
|--------|------|
| `DIG_CODEX_PLAN_REQUIRED` | Plan Mode が無効 |
| `DIG_CODEX_PLAN_REVIEW_UNAVAILABLE` | 計画レビューで codex primary + fallback 両方 unavailable |
| `DIG_CODEX_PLAN_REVIEW_BLOCKED` | 計画レビューで critical/high 未解消 |
| `DIG_CODEX_DECOMP_REVIEW_BLOCKED` | 分解レビューで critical/high 未解消 |
| `DIG_CODEX_DECOMP_REVIEW_UNAVAILABLE` | 分解レビューで codex exec primary + fallback 両方 unavailable |
| `DIG_CODEX_DECOMP_SANITIZE_BLOCKED` | 分解レビューでサニタイズ失敗（高エントロピー or cp/sed失敗）、ユーザー確認不可 |
| `DIG_CODEX_PLAN_SANITIZE_BLOCKED` | 計画レビューでサニタイズ失敗（高エントロピー or cp/sed失敗）、ユーザー確認不可 |

## 停止文テンプレート

- レビュー不能時:
  - `ERROR_CODE: DIG_CODEX_PLAN_REVIEW_UNAVAILABLE`
  - `RERUN_COMMAND: $dig <topic>`
  - `DIAGNOSTIC_COMMAND: codex --version`
- レビューNG時:
  - `ERROR_CODE: DIG_CODEX_PLAN_REVIEW_BLOCKED`
  - `RERUN_COMMAND: $dig <topic>`
  - `DIAGNOSTIC_COMMAND: echo REVIEW_COUNTS critical=<n> high=<n>`
- 分解レビュー不能時:
  - `ERROR_CODE: DIG_CODEX_DECOMP_REVIEW_UNAVAILABLE`
  - `RERUN_COMMAND: $dig <topic>`
  - `DIAGNOSTIC_COMMAND: codex --version`
- 分解レビューNG時:
  - `ERROR_CODE: DIG_CODEX_DECOMP_REVIEW_BLOCKED`
  - `RERUN_COMMAND: $dig <topic>`
  - `DIAGNOSTIC_COMMAND: echo REVIEW_COUNTS critical=<n> high=<n>`
- 分解サニタイズブロック時:
  - `ERROR_CODE: DIG_CODEX_DECOMP_SANITIZE_BLOCKED`
  - `RERUN_COMMAND: $dig <topic>`
  - `DIAGNOSTIC_COMMAND: grep -cE '[A-Za-z0-9+/=]{64,}' $PLAN_FILE`
- 計画サニタイズブロック時:
  - `ERROR_CODE: DIG_CODEX_PLAN_SANITIZE_BLOCKED`
  - `RERUN_COMMAND: $dig <topic>`
  - `DIAGNOSTIC_COMMAND: grep -cE '[A-Za-z0-9+/=]{64,}' $PLAN_FILE`

## Step 3 分解経路（Codex 固有）

Codex では `decomposition` スキルの TaskCreate/TaskUpdate が使用不可のため、分解はテキストベースで実行:

1. `## タスク追跡` セクションを `$PLAN_FILE` に冪等追記（Step 2 完了後、dig-core 契約のタスク登録タイミング準拠。cancel_all の前提条件も保証）
2. Codex 自身がプランファイルのタスク分解セクションを Bash (`cat >>`) で追記
3. タスクを `add_task` 関数でチェックリスト形式で追記（TaskCreate の代替）
4. REVIEW_GATE_DECOMPOSITION を実行（上記 REVIEW_DECOMP 状態遷移）

### 複合タスクの完了（Codex は計画フェーズのみ）

Codex は実行フェーズ（Step 5）を持たないため、タスク完了は将来対応。計画フェーズ完了時:
- 全タスクの分解 + REVIEW_GATE_DECOMPOSITION 通過 + REVIEW_GATE_PLAN 通過後に DONE 遷移
- 実行フェーズを含む場合: dig-claude に切り替えて使用

### セッション振り返り（計画完了後）

計画完了後に `devkit:improve-skill` を実行する。
dig-core 契約の「セッション振り返り」に従う。
ただし dig-codex は計画専用のため、Step 3（編集・コミット）は実行せず修正提案の提示のみ。

> decomposition スキルは呼び出さない。dig-codex が分解ロジックを直接実行し、テキストチェックリストで管理する。

## Codex 側の機能制約（明示）

| 機能 | Claude | Codex | 理由 |
|------|--------|-------|------|
| タスク登録 | TaskCreate | Bash+テキスト | TaskCreate 非対応 |
| サブタスク登録 | decomposition (TaskCreate) | テキストチェックリスト | 同上 |
| 並列実行 | agent-parallel / tool-parallel | 非対応（計画フェーズのみ） | Step 5 非対応 |
| REVIEW_GATE_DECOMPOSITION | 対応 | 対応 | codex exec 共通 |
| REVIEW_GATE_PLAN | 対応 | 対応（既存） | 既存機能 |
| REVIEW_GATE_SUBTASK | 対応 | 非対応（Step 5 非対応） | dig-core 契約により適用外 |
| REVIEW_GATE_INTEGRATION | 対応 | 非対応（Step 5 非対応） | 同上 |
