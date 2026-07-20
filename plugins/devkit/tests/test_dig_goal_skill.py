"""dig-goal スキルの深掘り・実行オーケストレーション契約テスト。"""

from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SKILL_PATH = REPO_ROOT / "plugins" / "devkit" / "skills" / "dig-goal" / "SKILL.md"


def _read(relpath: str) -> str:
    return (REPO_ROOT / relpath).read_text(encoding="utf-8")


def _skill_text() -> str:
    return SKILL_PATH.read_text(encoding="utf-8")


def _frontmatter() -> str:
    match = re.match(r"^---\n(.*?)\n---\n", _skill_text(), re.DOTALL)
    assert match, "frontmatter が見つからない"
    return match.group(1)


def _section(text: str, heading: str) -> str:
    start = text.index(heading)
    level = len(heading) - len(heading.lstrip("#"))
    match = re.search(rf"^#{{1,{level}}} (?!#)", text[start + len(heading) :], re.MULTILINE)
    return text[start:] if match is None else text[start : start + len(heading) + match.start()]


def _between(text: str, start: str, end: str) -> str:
    start_index = text.index(start)
    end_index = text.index(end, start_index + len(start))
    return text[start_index:end_index]


def test_skill_exists_and_frontmatter_contract():
    assert SKILL_PATH.exists()
    frontmatter = _frontmatter()
    assert 'name: "dig-goal"' in frontmatter
    assert "description:" in frontmatter
    assert 'argument-hint: "[task]"' in frontmatter
    for trigger in (
        "深掘りして",
        "実装して",
        "ゴールプロンプトを作って",
        "夜間実行の指示書を作って",
        "/dig-goal",
    ):
        assert trigger in frontmatter


def test_frontmatter_does_not_limit_allowed_tools():
    frontmatter = _frontmatter()
    assert "allowed-tools" not in frontmatter
    assert "allowed-tools" in _skill_text(), "本文の設計理由まで消えている"


def test_three_execution_modes_are_present():
    text = _skill_text()
    execution_modes = _section(text, "## 実行形態")
    for mode in ("同席実装", "現セッション自律実行", "起動プロンプト提示"):
        assert mode in execution_modes
    assert "軸はタスク規模ではなく自律度" in execution_modes


def test_harness_task_list_and_progress_contract():
    text = _skill_text()
    assert "`AskUserQuestion` が使える -> Claude 親" in text
    assert "`spawn_agent` が使える -> Codex 親" in text
    assert "Codex 親 plan mode: `request_user_input` を使う(1 呼び出し最大 3 問)" in text
    assert "step 1-9 をタスクリストへ登録" in text
    assert "1 ジョブ = 1 タスク" in text
    assert "`wait_agent` で黙って待たず" in text
    assert "`git status` / `git diff` で確認" in text


def test_write_contract_phase_boundaries():
    write_contract = _section(_skill_text(), "## 書き込み契約")
    assert "step 1-5" in write_contract
    assert "対象 repo に対して read-only" in write_contract
    assert "同席実装の step 6-9 と現セッション自律実行への移行後" in write_contract
    assert "承認済み計画またはゴール本文の契約" in write_contract


def test_inventory_driven_interview_contract():
    interview = _section(_skill_text(), "### 1. 深掘り(棚卸し駆動面談、親)")
    assert "最初のラウンドでタスク型(実装 / 調査 / 状態確認 / 文書化 / 整理)" in interview
    assert "暫定実行形態(同席 / 現セッション自律実行 / 起動プロンプト提示)を確定" in interview
    assert "| 未知 | 影響 | 扱い |" in interview
    for value in ("質問する", "仮定で進める", "確定済み"):
        assert value in interview
    assert "「質問する」行がゼロになったら深掘りを終了" in interview
    assert "固定ラウンド数はなく、深さは可変" in interview
    assert "1 ラウンド最大 4 問" in interview


def test_autonomous_inventory_requires_safety_and_progress_topics():
    interview = _section(_skill_text(), "### 1. 深掘り(棚卸し駆動面談、親)")
    required = (
        "停止条件 3 種(達成停止 / 上限停止 / 行き詰まり停止。上限停止は省略禁止)",
        "破壊的操作の可否",
        "外部状態変更の具体的な対象・操作と可否",
        "write_scope",
        "進捗の残し方",
        "必ず「質問する」行として棚卸しへ載せる",
    )
    for phrase in required:
        assert phrase in interview


def test_integration_method_is_investigated_not_asked():
    text = _skill_text()
    interview = _section(text, "### 1. 深掘り(棚卸し駆動面談、親)")
    planning = _section(text, "### 2. 調査 + 計画(親)")
    assert "統合方法は質問しない" in interview
    assert "既定は PR 経由" in interview
    assert "統合方法: 既定は PR 経由(提出 + CI green 確認 + merge)" in planning
    assert "`command -v gh` が通らない場合、origin なし repo" in planning
    assert "非 GitHub ホストの場合は直接統合へ自動フォールバック" in planning
    assert "認証切れ・API 障害・ネットワーク断などで失敗する場合は、直接統合へフォールバックせず停止・報告" in planning


def test_non_implementation_plan_schema():
    planning = _section(_skill_text(), "### 2. 調査 + 計画(親)")
    for phrase in (
        "read_scope: 読み取る repo・ファイル・外部情報の範囲",
        "成功条件と検証方法",
        "非対象と外部状態変更可否",
        "実行形態",
        "ブランチ / commit / 統合 / 実装 backend: 適用なし",
        "停止条件 3 種、具体的な上限",
        "`.claude/goal-runs/` のゴールファイル・進捗ログ・完了レポートを必須",
        "同席 read-only は通常の最終報告で終了",
        "ゴール本文・worktree・`.claude/goal-runs/` 成果物を作らない",
    ):
        assert phrase in planning


def test_backend_change_reopens_inventory():
    backend = _section(_skill_text(), "### 3. backend 選択(選択肢付き質問)")
    assert "ここでは backend だけを選ぶ" in backend
    assert "実行形態を変更する場合は step 1 の未知棚卸しを再開" in backend
    assert "「質問する」行がゼロになるまで step 3 以降へ進まない" in backend


def test_backend_selection_and_python_gate_contract():
    text = _skill_text()
    claude_parent = _between(text, "#### Claude 親の選択肢", "#### Codex 親の選択肢")
    assert claude_parent.count("| codex — gpt-5.6-sol medium") == 1
    assert claude_parent.count("| codex review — gpt-5.6-sol medium") == 1
    assert "標準の実装(既定)" in claude_parent
    assert "標準の計画レビュー / diff レビュー(既定)" in claude_parent
    assert "`command -v uv`" in claude_parent
    assert "thread_id 抽出に必要な prerequisite 不足としてユーザーへ報告" in claude_parent
    assert "Codex の実装 backend だけを除外" in claude_parent
    assert "Codex の計画レビュー / diff レビュー選択肢は残し" in claude_parent
    assert "黙って別 backend へ fallback しない" in claude_parent
    assert "`command -v codex` が通らない場合は codex の選択肢を除外" in claude_parent
    assert "command -v cursor-agent" in claude_parent
    assert "model=sonnet" in claude_parent
    assert "model=opus" in claude_parent


def test_codex_parent_has_three_roles_without_effort_selection():
    text = _skill_text()
    codex_parent = _between(text, "#### Codex 親の選択肢", "### 4. 計画レビュー")
    for role in ("| 実装 |", "| 計画レビュー |", "| diff レビュー |"):
        assert role in codex_parent
    assert "子 agent ごとの effort を選択・指定しない" in codex_parent
    assert "model_reasoning_effort" not in codex_parent


def test_pinned_model_effort_and_stdin_contract():
    text = _skill_text()
    assert "Codex のモデルは `gpt-5.6-sol` を `-m` で明示" in text
    assert "catch-up スキルと `premises.json` で管理" in text
    assert set(re.findall(r"-m\s+(gpt-[\w.\-]+)", text)) == {"gpt-5.6-sol"}
    assert set(re.findall(r'model_reasoning_effort="([^"<>]+)"', text)) == {"medium"}
    offenders = [
        line
        for line in text.splitlines()
        if re.search(r"\bcodex\s+-a\s+never\b.*\bexec\b", line)
        and "< /dev/null" not in line
    ]
    assert not offenders


def test_plan_review_and_approval_contract():
    text = _skill_text()
    assert "### 4. 計画レビュー(選択 backend)" in text
    assert "--sandbox read-only" in text
    assert (
        'codex -a never exec -m gpt-5.6-sol -c model_reasoning_effort="medium" '
        'review --base origin/<default> < /dev/null'
    ) in text
    assert "origin なし repo は `--base <default>`" in text
    approval = _section(text, "### 5. 計画承認")
    assert "同席実装では計画レビュー / 実装 / diff レビューの 3 役を明記" in approval
    assert "承認なしで実装・実行移行に進まない" in approval
    assert "モデル / effort 非対応の経路は「適用なし」" in approval
    assert "### 9. 統合・後始末・完了報告" in text


def test_claude_parent_plan_mode_approval_boundaries():
    text = _skill_text()
    interview = _section(text, "### 1. 深掘り(棚卸し駆動面談、親)")
    approval = _section(text, "### 5. 計画承認")
    assert "Claude 親は step 1 開始時に plan mode 外であれば `EnterPlanMode` を呼んで plan mode へ入る" in interview
    assert "step 1-5 の read-only 契約は plan mode と整合する" in interview
    assert "`ExitPlanMode` で承認を得ることに一本化する" in approval
    assert "`EnterPlanMode` が利用できないハーネスの縮退経路に限り" in approval
    assert "通常 mode で計画全文を提示して明示承認を得る" in approval
    assert "`ExitPlanMode` による承認前は step 6(実装・実行移行)へ進まない" in approval
    assert "`ExitPlanMode` 承認後は plan mode を抜け" in approval


def test_delegation_records_explicit_thread_id_and_resumes_it():
    text = _skill_text()
    delegation = _section(text, "### 6. 実装委譲(backend)")
    repair = _section(text, "### 8. 修正ループ")
    assert "--sandbox workspace-write" in delegation
    assert 'devkit-codex-job.XXXXXX' in delegation
    assert 'echo "JOB_DIR=$JOB_DIR"' in delegation
    assert "echo された JOB_DIR を親が記録" in delegation
    assert "set -o pipefail" in delegation
    assert (
        'codex -a never exec -C "<worktree>" --sandbox workspace-write '
        '-m gpt-5.6-sol -c model_reasoning_effort="medium" --json "<実装指示>" '
        '< /dev/null | tee "$JOB_DIR/codex-events.jsonl"'
    ) in delegation
    assert 'uv run --no-project --python ">=3.10" python -c' in delegation
    assert "python3 -c" not in delegation
    assert 'event.get("type") == "thread.started"' in delegation
    assert "len(ids) == 1" in delegation
    assert "isinstance(ids[0], str)" in delegation
    assert "events=[" not in delegation
    assert 'event.get("thread_id")' in delegation
    assert 'test -s "$JOB_DIR/thread-id.txt"' in delegation
    assert "resume せず委譲失敗として報告" in delegation
    assert "JOB_DIR / `codex-events.jsonl` / `thread-id.txt` をジョブごとに発行・分離" in delegation
    assert '"$(cat "$JOB_DIR/thread-id.txt")"' in repair
    assert "ジョブ固有 thread_id" in repair
    assert (
        'codex -a never -C "<worktree>" --sandbox workspace-write exec resume '
        '-m gpt-5.6-sol -c model_reasoning_effort="medium" '
        '"$(cat "$JOB_DIR/thread-id.txt")" "<指摘と修正指示>" < /dev/null'
    ) in repair
    assert "--last" not in text


def test_cursor_and_worktree_delegation_contract():
    text = _skill_text()
    delegation = _section(text, "### 6. 実装委譲(backend)")
    repair = _section(text, "### 8. 修正ループ")
    for token in ("--model cursor-grok-4.5-high", "--trust", "--force", "chat-id.txt"):
        assert token in delegation
    assert 'codex -a never exec -C "<worktree>"' in delegation
    assert '--workspace "<worktree>"' in delegation + repair
    assert (
        'cursor-agent -p --resume "$(cat "$JOB_DIR/chat-id.txt")" --trust --force '
        '--model cursor-grok-4.5-high --workspace "<worktree>" --output-format text "<実装指示>"'
    ) in delegation
    assert (
        'cursor-agent -p --resume "$(cat "$JOB_DIR/chat-id.txt")" --trust --force '
        '--model cursor-grok-4.5-high --workspace "<worktree>" --output-format text "<指摘と修正指示>"'
    ) in repair
    assert "sandbox なし" in text
    assert "commit 禁止" in delegation


def test_worktree_and_pr_integration_contract():
    text = _skill_text()
    worktree = _between(text, "## worktree 運用と統合", "### 6. 実装委譲")
    assert 'devkit-dig-goal-wt.XXXXXX' in worktree
    assert 'git symbolic-ref --short refs/remotes/origin/HEAD' in worktree
    assert "結果から `origin/` プレフィックスを取り除いた名前を `<default>`" in worktree
    assert "取得できなければ `main`、`main` も無ければ現在のブランチ" in worktree
    assert "fetch 失敗は警告を報告して続行し、統合前に再試行" in worktree
    assert 'worktree add -b <type>/<slug> "$WT_DIR/wt" origin/<default>' in worktree
    assert "main ツリー実装へ黙って戻らず" in worktree
    assert 'git -C "<worktree>" rev-parse HEAD' in worktree
    assert "worktree add に使った起点の `<base-commit>` として親が記録" in worktree
    assert "git add <そのジョブの write_scope>" in worktree
    assert "`git add .` と `git add -A` は使わない" in worktree
    assert "PR 経由(既定)" in worktree
    for phrase in (
        "gh pr checks <PR番号> --json bucket,name",
        "ポーリング前の head SHA",
        "ポーリング後の head SHA",
        "前後の SHA が一致する場合だけ checks と head SHA を同じ判定対象",
        "全件 `pass`(`skipping` は許容)",
        "安定した head SHA を「検証済み SHA」として記録",
        "API・認証エラーをチェック 0 件の成功と混同せず",
        "CI なし repo でも PR 作成後は `no checks reported` と同じ数分の登録猶予",
        "checks が観測されたら計画記載より観測を優先して CI ありへ切り替え",
        "--match-head-commit <検証済みSHA>",
        "merge queue preflight",
        "autoMergeRequest",
        "git ls-remote --heads origin refs/heads/<branch>",
        "remote tipが検証済み SHA(merge した head)と一致",
        "--force-with-lease=refs/heads/<branch>:<検証済みSHA>",
        "headRefOid` が記録したローカル branch tip(検証済み SHA)と一致",
        "`MERGED` 確認 → `git fetch origin` → ローカルの作業 branch tip を記録",
        "git worktree remove <worktree>` → `git branch -d <branch>",
        "git worktree remove <worktree>` → `git branch -D <branch>",
        "`MERGED` を確認して初めて統合完了",
        "PR を open のまま残し",
    ):
        assert phrase in worktree


def test_direct_integration_contract():
    worktree = _between(_skill_text(), "## worktree 運用と統合", "### 6. 実装委譲")
    assert "直接統合(PR 不可時の自動フォールバック、またはユーザー明示時)" in worktree
    assert 'merge --ff-only <branch>' in worktree
    assert 'push origin <default>' in worktree
    assert "push reject は fetch して手順 1 からやり直し" in worktree
    assert "origin なし repo" in worktree and "push なし" in worktree
    failure = _section(_skill_text(), "### 失敗時の共通契約")
    assert "変更を破棄しない" in failure
    assert "worktree・ブランチ・commit をそのまま残し" in failure
    assert "再開コマンドを報告" in failure
    assert "統合成功・cleanup 未完了" in failure


def test_autonomous_path_and_failure_modes_contract():
    text = _skill_text()
    path = _section(text, "## 現セッション自律実行 / 起動プロンプト提示パス(step 6-9)")
    assert "停止条件 3 種 / 外部状態変更可否 / 進捗管理 / 実装戦略 / 統合方法" in path
    assert "計画にない項目だけの差分確認を選択肢付きで 1 ラウンド" in path
    assert "承認質問を二重化しない" in path
    failure_modes = _section(text, "## 排除する失敗モード")
    for phrase in (
        "停止条件欠落",
        "ゴール誤解釈・スコープドリフト",
        "変更範囲の膨張",
        "無限待機",
        "受け渡し失敗",
        "blocker 即停止による不在時間の空転",
        "確認待ち停止",
    ):
        assert phrase in failure_modes
    assert "記録 → 代替 2 案 → 最有力で続行" in failure_modes
    assert "権限・外部入力・破壊的操作が絡む blocker は即停止" in failure_modes


def test_prompt_template_and_self_check_contract():
    text = _skill_text()
    strategy = _between(text, "## プロンプトテンプレート", "## セルフチェック")
    headings = (
        "## 実行モード: 不在自律実行",
        "## 目的",
        "## 成功条件(検証可能)",
        "## 検証コマンド",
        "## 制約・非対象",
        "## 停止条件(3 種)",
        "## 実行戦略(実装系のみ)",
        "## 進捗管理",
        "## 実装後レビュー",
        "## 完了レポート",
        "## 実行前提",
    )
    positions = [strategy.index(heading) for heading in headings]
    assert positions == sorted(positions)
    assert "上限停止" in strategy and "省略禁止" in strategy
    assert "次にやること / 直近で決めた方針" in strategy
    assert "終了時に起動元 checkout 基準" in strategy
    completion_report = _section(strategy, "## 完了レポート")
    for phrase in (
        "停止種別",
        "成功条件ごとの達成状況",
        "検証コマンド結果",
        "逸脱と判断ログ要約",
        "残課題",
        "変更ファイル一覧",
        "実際に保存したファイル名の連番を反映した `<slug>-N.md`",
        "末尾の `-goal` サフィックスを除いた basename",
        "英小文字・数字・ハイフンへスラッグ化",
        "`<basename>-2.md` からの連番",
        "`.gitignore` が無ければ `*` 1 行で新規作成",
        "既存なら内容を触らない",
        "`git check-ignore`",
    ):
        assert phrase in completion_report
    self_check = _section(text, "## セルフチェック")
    assert len(re.findall(r"^\d+\. ", self_check, re.MULTILINE)) == 10


def test_launch_guide_and_review_execution_flow():
    text = _skill_text()
    guide = _section(text, "## 起動プロンプトの手引き")
    for surface in ("現セッション `/goal`", "別ターミナル `claude --bg`", "`/loop`", "`/schedule`", "Codex 貼付け"):
        assert surface in guide
    assert guide.count("提示のみ") >= 5
    assert "現セッション `/goal`(インライン自己完結型)" in guide
    assert "現セッション `/goal`(4,000 字超 fallback)" in guide
    assert 'claude --bg --permission-mode acceptEdits --allowedTools "..."' in guide
    assert (
        'cd "<対象repo>" && claude --bg --permission-mode acceptEdits --allowedTools "..." '
        '"/goal <保存したゴールファイルの絶対パス> の成功条件を満たす or stop after '
        '<N> turns。まず <保存したゴールファイルの絶対パス> を読め" < /dev/null'
    ) in guide
    assert "or stop after <N> turns" in guide
    assert "同じマシン・同じ checkout から絶対パスで参照" in guide
    assert "/loop <interval> .claude/goal-runs/<file>-goal.md" in guide
    assert "/schedule <trigger> .claude/goal-runs/<file>-goal.md" in guide
    codex_row = next(line for line in guide.splitlines() if line.startswith("| Codex 貼付け"))
    assert "ゴール本文全文を 1 ブロックで提示" in codex_row
    assert "ファイル参照へ分岐しない" in codex_row
    assert "stop after" not in codex_row
    assert "codex exec" not in guide
    assert "claude -p" not in guide
    assert "4,000 字判定と fallback も例外形態だけ" in guide
    assert "Codex 貼付けは字数に関わらず常に全文 1 ブロック" in text
    review = _section(text, "### 7. ゴールプロンプト独立レビュー")
    assert "--sandbox read-only" in review
    assert 'JOB_DIR=$(mktemp -d "${TMPDIR:-/tmp}/devkit-goal-review.XXXXXX")' in review
    assert 'echo "JOB_DIR=$JOB_DIR"' in review
    assert 'JOB_DIR=<echo された記録済みのパス>' in review
    assert '-C "<対象repo>"' in review
    assert '> "$JOB_DIR/review.log" 2>&1' in review
    assert "run_in_background" in review
    assert "完了通知後に記録済み `JOB_DIR` の `review.log` を必ず読み" in review
    assert "Agent(Claude サブエージェント)" in review
    assert "`spawn_agent`(explorer)" in review
    assert "`wait_agent`" in review
    assert "独立レビューを実施できないため step 8 へ進まない" in review
    assert "保存はせず" in review
    assert "再実行を案内して停止" in review
    assert "指摘ゼロを確認してから step 8 へ進む" in review
    step8 = _section(text, "### 8. 実行移行(既定) / 例外形態の最終確認")
    assert "承認待ちなし" in step8
    assert "直ちに実行を開始する" in step8
    assert "保存に失敗した場合は実行を開始せず停止・報告" in step8
    codex_goal_offenders = [
        line
        for line in text.splitlines()
        if "codex -a never exec" in line
        and re.search(r"(?<![A-Za-z0-9_.-])/goal\b", line)
    ]
    assert not codex_goal_offenders


def test_pr_contract_is_baked_into_goal_strategy():
    text = _skill_text()
    strategy = _between(text, "## プロンプトテンプレート", "## セルフチェック")
    step6 = _section(text, "### 6. 組み立て + セルフチェック")
    for contract in (strategy, step6):
        assert "CI 待機上限(既定 30 分)" in contract
        assert "`pass`" in contract and "`skipping`" in contract
        assert "merge queue" in contract and "auto-merge" in contract
        assert "state 変更コマンドを実行せず停止" in contract
        assert "`--match-head-commit`" in contract
        assert "merge 直前の head SHA 再確認で不一致なら停止" in contract
        assert "git ls-remote --heads origin refs/heads/<branch>" in contract
        assert "API・認証・通信エラー" in contract
        assert "複数結果はcleanup未完了で停止" in contract
        assert "期待 tip" in contract and "lease" in contract
        assert "`headRefOid`" in contract
        assert "`MERGED` 確認" in contract
        assert "PR を open のまま停止" in contract


def test_autonomous_execution_declaration_and_report_paths():
    text = _skill_text()
    strategy = _between(text, "## プロンプトテンプレート", "## セルフチェック")
    declaration = _section(strategy, "## 実行モード: 不在自律実行")
    assert "質問・確認・承認求め" in declaration
    assert "停止条件(3 種)と即停止条件が常に優先" in declaration
    assert "進捗ログへ記録して続行" in declaration
    assert "行き詰まり停止する(続行しない)" in declaration
    assert "ハーネスが出すツール実行の許可プロンプトへの応答待ち" in declaration
    assert "許可はユーザーまたはハーネス設定が与える。待機してよい" in declaration
    step8 = _section(text, "### 8. 実行移行(既定) / 例外形態の最終確認")
    assert "ゴールファイル・進捗ログ・完了レポートの 3 パス" in text
    assert "使い捨て worktree 内には置かない" in text
    assert "起動元 checkout(スキル起動時の cwd を含む checkout)" in text
    assert "対象が git 管理下にない場合" in text
    assert "検証不能のため `git check-ignore` を行わず skip" in text
    assert "コンテキスト圧縮後はまずそのファイルを読み直してから進捗ログ冒頭の復帰点を読む" in step8


def test_goal_path_collision_contract():
    text = _skill_text()
    step6 = _section(text, "### 6. 組み立て + セルフチェック")
    step8 = _section(text, "### 8. 実行移行(既定) / 例外形態の最終確認")
    assert "衝突しない最終 basename(必要なら連番込み)を先に確定" in step6
    assert "ゴールファイル・進捗ログ・完了レポートの 3 パス" in step6
    assert "黙って連番保存へ逃げず" in step8
    assert "3 パスを確定し直して本文へ反映してから保存・実行" in step8


def test_retired_skill_tokens_are_absent():
    text = _skill_text()
    retired_patterns = (
        r"(?<![\w-])/" r"dig(?!-goal)(?![\w-])",
        r"devkit:" r"dig(?!-goal)(?![\w-])",
        r"\$" r"dig(?!-goal)(?![\w-])",
        r"skills/" r"dig/",
        r"goal-" r"prompt",
        r"devkit-" r"dig-wt",
        r"devkit-" r"dig-job",
    )
    for pattern in retired_patterns:
        assert re.search(pattern, text) is None, pattern


def test_readme_lists_dig_goal_command():
    assert "`/dig-goal`" in _read("README.md")


def test_openai_yaml_surface():
    metadata_path = SKILL_PATH.parent / "agents" / "openai.yaml"
    assert metadata_path.exists()
    metadata = metadata_path.read_text(encoding="utf-8")
    assert "dig-goal" in metadata
    assert "$dig-goal" in metadata
