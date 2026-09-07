"""dig スキルの深掘り・実装完遂契約テスト。"""

from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SKILL_PATH = REPO_ROOT / "plugins" / "devkit" / "skills" / "dig" / "SKILL.md"
REFERENCE_DIR = SKILL_PATH.parent / "references"


def _read(relpath: str) -> str:
    return (REPO_ROOT / relpath).read_text(encoding="utf-8")


def _skill_text() -> str:
    parts = [SKILL_PATH.read_text(encoding="utf-8")]
    parts.extend(path.read_text(encoding="utf-8") for path in sorted(REFERENCE_DIR.glob("*.md")))
    return "\n".join(parts)


def _frontmatter() -> str:
    match = re.match(r"^---\n(.*?)\n---\n", _skill_text(), re.DOTALL)
    assert match, "frontmatter が見つからない"
    return match.group(1)


def _section(text: str, heading: str) -> str:
    routed = {
        "### 書き込み契約": (SKILL_PATH, "## ハーネス判定と実行差分"),
        "### 1. 深掘り(棚卸し駆動面談、親)": (REFERENCE_DIR / "planning.md", "## 深掘り"),
        "### 2. 調査 + 計画(親)": (REFERENCE_DIR / "planning.md", "## 調査と計画"),
        "### 3. backend 固定とフォールバック": (REFERENCE_DIR / "execution.md", "## backend 固定とフォールバック"),
        "### 4. 計画レビュー": (REFERENCE_DIR / "planning.md", "## 計画レビュー"),
        "### 6. worktree 作成と実装委譲": (REFERENCE_DIR / "execution.md", "## worktree 作成と実装委譲"),
        "### 7. 自レビューと独立 diff レビュー": (REFERENCE_DIR / "execution.md", "## 自レビューと独立 diff レビュー"),
        "### 8. 修正ループ": (REFERENCE_DIR / "execution.md", "## 修正ループ"),
        "### 9. 統合・後始末・完了報告": (REFERENCE_DIR / "integration.md", "# 統合と完了"),
    }
    if heading in routed:
        path, routed_heading = routed[heading]
        return _section(path.read_text(encoding="utf-8"), routed_heading)
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
    assert 'name: "dig"' in frontmatter
    assert "description:" in frontmatter
    assert 'argument-hint: "[task]"' in frontmatter
    for trigger in (
        "深掘りして",
        "実装して",
        "相談したい",
        "/dig",
    ):
        assert trigger in frontmatter
    assert "開発要求を深掘り" in frontmatter
    assert "曖昧な開発要求" not in frontmatter
    assert len(re.search(r'^description: "(.*)"$', frontmatter, re.MULTILINE).group(1)) <= 100


def test_progressive_references_are_reachable_and_loaded_just_in_time():
    main = SKILL_PATH.read_text(encoding="utf-8")
    for name in ("planning.md", "execution.md", "integration.md"):
        assert (REFERENCE_DIR / name).is_file()
        assert f"references/{name}" in main
    assert all(term in main for term in ("直前に", "始める直前に", "統合開始直前に"))


def test_frontmatter_does_not_limit_allowed_tools():
    frontmatter = _frontmatter()
    assert "allowed-tools" not in frontmatter
    assert "allowed-tools" in _skill_text(), "本文の設計理由まで消えている"


def test_default_is_implementation_completion_without_asking_mode():
    text = _skill_text()
    assert "実行形態を質問しない" in text


def test_write_contract_phase_boundaries():
    write_contract = _section(_skill_text(), "### 書き込み契約")
    assert "step 1-5" in write_contract
    assert "sandbox の緩和や write_scope 外の変更" in write_contract
    assert "実行前にユーザー確認を得る" in write_contract


def test_inventory_driven_interview_contract():
    interview = _section(_skill_text(), "### 1. 深掘り(棚卸し駆動面談、親)")
    assert "タスク型と要求" in interview
    assert "| 未知 | 影響 | 扱い |" in interview
    # セルの許容値集合は test_skill_invariants.py::enum_table_cells に統合。
    for value in ("質問する", "仮定で進める", "確定済み"):
        assert value in interview


def test_integration_method_is_investigated_not_asked():
    text = _skill_text()
    interview = _section(text, "### 1. 深掘り(棚卸し駆動面談、親)")
    assert "統合方法は質問せず" in interview
    # CI green → merge の順序は test_skill_invariants.py::ci_green_before_merge に統合。


def test_non_implementation_plan_schema():
    planning = _section(_skill_text(), "### 2. 調査 + 計画(親)")
    non_implementation_rows = [
        line for line in planning.splitlines() if line.startswith("| 非実装 |")
    ]
    assert len(non_implementation_rows) == 1
    for field in (
        "read_scope",
        "成功条件と検証",
        "非対象と外部状態変更",
        "実行形態",
        "branch / commit / 統合 / 実装 backend は適用なし",
    ):
        assert field in non_implementation_rows[0]


def test_planning_has_layered_approval_summary_schema():
    planning = _section(_skill_text(), "### 2. 調査 + 計画(親)")
    for phrase in (
        "## 承認用サマリー",
        "判断してほしい点",
        "既定からの逸脱",
        "後戻りしにくい操作",
        "工程表",
        "検証",
        "独立レビュー状態",
        "実施済み(指摘 N 件反映)",
        "適用なし",
    ):
        assert phrase in planning


def test_planning_defines_process_table():
    planning = _section(_skill_text(), "### 2. 調査 + 計画(親)")
    assert "| 工程 | 状態 | backend |" in planning
    for row in ("計画レビュー", "実装", "diff レビュー", "検証"):
        assert row in planning
    # 行ごと検査する。marker だけを見ると実装行やレビュー行へ移動しても通り、
    # 承認時に誤った工程を「今ここ」と示してしまう。
    # backend 列まで検査する。承認の主体がエージェントへ変わると、
    # 明示承認という境界そのものが委譲されてしまう。
    assert "| **承認** | **← 今ここ** | ユーザー |" in planning
    assert planning.count("← 今ここ") == 1


def test_process_table_example_uses_review_state_schema():
    planning = _section(_skill_text(), "### 2. 調査 + 計画(親)")
    review_rows = [
        line for line in planning.splitlines() if line.startswith("| 計画レビュー |")
    ]
    assert len(review_rows) == 1
    state = review_rows[0].split("|")[2].strip()
    assert state.startswith(("実施済み(", "skip(", "適用なし"))


def test_planning_self_contains_size_target():
    planning = _section(_skill_text(), "### 2. 調査 + 計画(親)")
    assert "約 1,000 字" in planning


def test_approval_puts_summary_first():
    approval = _section(_skill_text(), "### 5. 計画承認")
    assert "レビュー済み計画" in approval
    assert "第 1 層から提示" in approval


def test_fixed_backend_assignment_and_python_gate_contract():
    backend = _section(_skill_text(), "### 3. backend 固定とフォールバック")
    assert "| 実装 | cursor-agent `cursor-grok-4.6-high` |" in backend
    assert "| 計画レビュー | codex `gpt-5.6-sol` / medium |" in backend
    assert "| diff レビュー | codex `gpt-5.6-sol` / medium |" in backend
    assert "| Claude 親 |" in backend
    assert "| Codex 親 |" in backend
    assert "| 判定不能 |" in backend
    # 表示名ではなく Agent へ実際に渡す alias を書くこと。
    # 2026-07-25 の圧縮で alias が表示名へ置き換わり、委譲時に何を指定するか
    # 分からなくなっていた([P2])。
    assert "`Agent(general-purpose, model=sonnet)`" in backend
    assert "`Agent(general-purpose, model=opus)`" in backend
    assert "cursor-grok-4.6-high" in backend
    assert "可用性判定の失敗" in backend
    assert "chat 作成が非ゼロ終了" in backend
    assert "agent 起動前に失敗" in backend
    assert "thread_id を採れない" in backend
    assert "起動そのものに失敗" in backend
    assert "起動不能または応答不能" in backend
    assert "rate limit" in backend
    assert "曖昧ならレート制限に分類せず降格しない" in backend
    assert "報告なしに fallback しない" in backend
    assert "2 つの実装 actor" in backend
    assert "レビュー lane は停止して報告する" in backend
    assert all(
        command in backend
        for command in ("command -v codex", "command -v cursor-agent", "command -v uv")
    )


def test_codex_parent_fallback_lanes_without_effort_selection():
    text = _skill_text()
    backend = _section(text, "### 3. backend 固定とフォールバック")
    assert "| Codex 親 |" in backend
    assert "| Codex 親 | 親実装 | `spawn_agent` reviewer → 終端処理 |" in backend
    assert "`spawn_agent` worker" not in text
    assert "子には再レビューだけ" in text
    assert "調査・実装・修正を委譲しない" in SKILL_PATH.read_text(encoding="utf-8")
    assert "`spawn_agent` reviewer → 終端処理" in backend
    assert "model_reasoning_effort" not in backend
    environment = _read("plugins/devkit/skills/setup/references/environment.md")
    for cli in ("codex", "cursor-agent"):
        row = next(line for line in environment.splitlines() if line.startswith(f"| `{cli}` |"))
        assert "Claude 親・判定不能" in row
        assert "Codex 親" in row and "不要" in row


def test_pinned_model_effort_and_stdin_contract():
    text = _skill_text()
    # approval/model/effort は test_skill_invariants.py::codex_execution_shape に統合。
    assert set(re.findall(r"-m\s+(gpt-[\w.\-]+)", text)) == {"gpt-5.6-sol"}
    assert set(re.findall(r'model_reasoning_effort="([^"<>]+)"', text)) == {"medium"}
    offenders = [
        line
        for line in text.splitlines()
        if re.search(r"\bcodex\s+-a\s+never\b.*\bexec\b", line)
        and "< /dev/null" not in line
    ]
    assert not offenders
    cursor_offenders = [
        line
        for line in text.splitlines()
        if ("$(cursor-agent create-chat" in line or 'cursor-agent -p --resume "' in line)
        and "< /dev/null" not in line
    ]
    assert not cursor_offenders


def test_plan_review_and_approval_contract():
    text = _skill_text()
    assert "### 4. 計画レビュー" in text
    assert "--sandbox read-only" in text
    assert "review --base origin/<default>" in text
    # approval/model/effort/stdin/worktree の形は stdin_closed /
    # codex_execution_shape / worktree_commands_pin_directory に統合。
    assert "--base <default>" in text
    assert "### 9. 統合・後始末・完了報告" in text


def test_claude_parent_plan_mode_approval_boundaries():
    text = _skill_text()
    harness = _section(text, "## ハーネス判定と実行差分")
    assert "`EnterPlanMode`" in harness
    assert "`ExitPlanMode`" in harness
    # 承認→実装の順序は test_skill_invariants.py::approval_before_implementation に統合。


def test_worktree_creation_keeps_its_exception_paths():
    """worktree 作成の 2 つの例外分岐。どちらも汎用 check が覆えない。

    どちらも 2026-07-25 の圧縮で消え、独立レビューが [P2] として検出した。
    平常系だけ読むと冗長に見えるが、例外系では唯一の防御になる型。

    - origin なし repo: fetch を無条件にすると worktree 作成前に失敗する
    - branch 名衝突: 他セッションの branch は正常に存在するため、固定名だと
      同じ slug の run が以後すべて停止する
    """
    creation = _section(_skill_text(), "### 6. worktree 作成と実装委譲")
    assert "fetch を省略" in creation
    assert "`-2` から連番" in creation


def test_non_git_repo_skips_git_only_lifecycle():
    creation = _section(_skill_text(), "### 6. worktree 作成と実装委譲")
    assert "git repo の実装系は必ず worktree" in creation
    assert "非 git repo には worktree / commit / 統合を適用せず" in creation
    assert "diff と結果を報告" in creation


def test_delegation_records_explicit_thread_id_and_resumes_it():
    text = _skill_text()
    delegation = _section(text, "### 6. worktree 作成と実装委譲")
    repair = _section(text, "### 8. 修正ループ")
    assert "--sandbox workspace-write" in delegation
    assert 'devkit-codex-job.XXXXXX' in delegation
    assert 'echo "JOB_DIR=$JOB_DIR"' in delegation
    assert "set -o pipefail" in delegation
    assert 'exec -C "<worktree>" --sandbox workspace-write' in delegation
    # command 全体の形は stdin_closed / codex_execution_shape /
    # worktree_commands_pin_directory に統合。
    assert 'uv run --no-project --python ">=3.10" python -c' in delegation
    assert "python3 -c" not in delegation
    assert 'event.get("type") == "thread.started"' in delegation
    assert "len(ids) == 1" in delegation
    assert "isinstance(ids[0], str)" in delegation
    assert "events=[" not in delegation
    assert 'event.get("thread_id")' in delegation
    assert 'test -s "$JOB_DIR/thread-id.txt"' in delegation
    assert '"$(cat "$JOB_DIR/thread-id.txt")"' in repair
    assert "exec resume" in repair
    assert "--last" not in text


def test_repair_loop_converges_by_findings_not_fixed_rounds():
    repair = _section(_skill_text(), "### 8. 修正ループ")
    assert "指摘がゼロで終了する" in repair
    assert "第 1 巡は最初の独立レビュー" in repair
    assert "件数が前巡以上の状態が 2 巡連続した" in repair
    assert "同一 finding" in repair
    assert "文言一致ではない" in repair
    assert "20 巡に達した" in repair
    assert "5 周" not in repair


def test_cursor_and_worktree_delegation_contract():
    text = _skill_text()
    delegation = _section(text, "### 6. worktree 作成と実装委譲")
    repair = _section(text, "### 8. 修正ループ")
    for token in ("--model cursor-grok-4.6-high", "--trust", "--force", "chat-id.txt"):
        assert token in delegation
    assert 'codex -a never exec -C "<worktree>"' in delegation
    assert '--workspace "<worktree>"' in delegation + repair
    assert "cursor-agent -p --resume" in delegation
    assert "cursor-agent.log" in delegation
    assert "set -o pipefail" in delegation
    # cursor command の形は stdin_closed / worktree_commands_pin_directory に統合。
    assert "sandbox なし" in text
    assert "commit 禁止" in delegation


def test_checkpoint_commit_precedes_independent_review():
    """`review --base` は commit 済み差分しか見ないため、レビュー前 commit は必須契約。

    2026-07-25 の圧縮でこの契約が統合節にしか残らなくなり、実装が未 commit のまま
    独立レビューを起動して空 diff を「指摘なし」と誤報しうる状態になっていた
    (codex の diff レビューが [P1] として検出)。再発防止の検査。
    """
    text = _skill_text()
    delegation = _section(text, "### 6. worktree 作成と実装委譲")
    review = _section(text, "### 7. 自レビューと独立 diff レビュー")

    assert "パス限定で add" in delegation
    # broad add 禁止は test_skill_invariants.py::no_broad_git_add、
    # commit→review 順序は commit_before_independent_review に統合。
    assert "commit 済み差分" in review
    # レビューは worktree 内で実行する。通常 checkout で走らせると commit 済み
    # branch ではなくそちらを対象にし、空 diff を「指摘なし」と誤報する。
    # 2026-07-25 の圧縮で「worktree 内で」の指定が消えていた([P1])。
    assert 'codex -a never exec -C "<worktree>"' in review
    # worktree 固定は test_skill_invariants.py::worktree_commands_pin_directory に統合。


def test_worktree_and_pr_integration_contract():
    text = _skill_text()
    integration = _section(text, "### 9. 統合・後始末・完了報告")
    # worktree command は test_skill_invariants.py::worktree_commands_pin_directory、
    # CI→merge は ci_green_before_merge、remote delete の lease は
    # remote_delete_has_lease に統合。ここには汎用 check が覆わない契約だけを残す。

    # 統合後はローカル作業 branch も消す。2026-07-25 の圧縮で worktree と remote の
    # 削除だけが残り、毎回 stale なローカル branch が残る状態だった([P2])。
    assert "`git branch -d <branch>`" in integration
    assert "`git branch -D <branch>`" in integration
    for invariant in (
        "単調増加値を origin から再計算して再検証",
        "標準解消規則のない conflict は abort して停止",
        "checks の取得前後に head SHA を取得",
        "同じ SHA に束縛された checks だけを判定",
        "API・認証・通信エラーをチェック 0 件の成功と混同しない",
        "0 件の扱いは計画した CI 有無と登録猶予に従い",
        "観測した checks を優先",
        "全 checks が pass（skipping は許容）",
        "merge queue / auto-merge が有効、または preflight が確認不能なら merge せず停止",
        "--match-head-commit <検証済みSHA>",
        "`--delete-branch` は使わず",
        "`MERGED` を確認するまで統合完了としない",
        "remote tip が検証済み SHA と一致",
        "PR の headRefOid で同一性を確認",
        "lease 失敗は remote を削除せず",
        "統合成功・cleanup 未完了",
        "PR を open のまま残し",
        "ジョブの write_scope をパス限定で add",
        "`git add .` / `git add -A` は使わない",
        "worktree remove が拒否されたら `--force` を使わない",
    ):
        assert invariant in integration


def test_direct_integration_contract():
    integration = _section(_skill_text(), "### 9. 統合・後始末・完了報告")
    assert "失敗時は変更を破棄せず" in integration
    for evidence in ("branch", "worktree", "停止操作", "再開方法"):
        assert evidence in integration


def test_retired_skill_tokens_are_absent():
    text = _skill_text()
    retired_patterns = (
        r"dig-goal",
        r"現セッション自律実行",
        r"起動プロンプト提示",
        r"セルフチェック",
        r"ゴールプロンプト",
        r"goal-runs",
    )
    for pattern in retired_patterns:
        assert re.search(pattern, text) is None, pattern


def test_goal_prompt_handoff_contract():
    text = _skill_text()
    handoff = _section(text, "## goal-prompt への引き継ぎ(ユーザー明示時のみ)")
    assert all(
        trigger in text
        for trigger in ("Goal プロンプトにして", "/goal で動かしたい", "後で実行したい")
    )
    assert ".claude/plans/YYYY-MM-DD-<slug>.md" in handoff
    assert "独立レビュー" in handoff


def test_readme_lists_dig_command():
    assert "`/dig`" in _read("README.md")


def test_openai_yaml_surface():
    metadata_path = SKILL_PATH.parent / "agents" / "openai.yaml"
    assert metadata_path.exists()
    metadata = metadata_path.read_text(encoding="utf-8")
    assert 'display_name: "Dig"' in metadata
    assert "$dig" in metadata
