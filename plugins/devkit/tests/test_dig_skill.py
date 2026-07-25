"""dig スキルの深掘り・実装完遂契約テスト。"""

from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SKILL_PATH = REPO_ROOT / "plugins" / "devkit" / "skills" / "dig" / "SKILL.md"


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


def test_frontmatter_does_not_limit_allowed_tools():
    frontmatter = _frontmatter()
    assert "allowed-tools" not in frontmatter
    assert "allowed-tools" in _skill_text(), "本文の設計理由まで消えている"


def test_default_is_implementation_completion_without_asking_mode():
    text = _skill_text()
    assert "**dig の既定は実装完遂**" in text
    assert "実行形態を質問しない" in text


def test_harness_task_list_and_progress_contract():
    text = _skill_text()
    assert "`AskUserQuestion` が使える" in text
    assert "AskUserQuestion がなく `spawn_agent` が使える" in text
    assert "plan mode は `request_user_input`" in text
    assert "step 1-9 と各委譲・長時間ジョブをタスクリストへ登録" in text
    assert "1 ジョブ = 1 タスク" in text
    assert "`wait_agent` で黙って待たず" in text
    assert "`git status` / `git diff` とジョブログで確認" in text


def test_write_contract_phase_boundaries():
    write_contract = _section(_skill_text(), "### 書き込み契約")
    assert "step 1-5" in write_contract
    assert "対象 repo に対して read-only" in write_contract
    assert "step 6-9 は承認済み write_scope 内だけを書き込む" in write_contract
    assert "goal-prompt 引き継ぎ時の" in write_contract
    assert "`.claude/plans/` への計画保存" in write_contract


def test_inventory_driven_interview_contract():
    interview = _section(_skill_text(), "### 1. 深掘り(棚卸し駆動面談、親)")
    assert "タスク型と要求" in interview
    assert "| 未知 | 影響 | 扱い |" in interview
    for value in ("質問する", "仮定で進める", "確定済み"):
        assert value in interview
    assert "「質問する」行がゼロで終了" in interview
    assert "1 ラウンド最大 4 問" in interview


def test_integration_method_is_investigated_not_asked():
    text = _skill_text()
    interview = _section(text, "### 1. 深掘り(棚卸し駆動面談、親)")
    planning = _section(text, "### 2. 調査 + 計画(親)")
    assert "統合方法は質問せず" in interview
    assert "PR 提出 + CI green 確認 + merge が既定" in planning
    assert "origin なし、非 GitHub origin、または `gh` 不在" in planning
    assert "計画時に直接統合へ決める" in planning
    assert "API・認証・通信が失敗した場合は直接統合へ切り替えず停止" in planning


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
    assert "| **承認** | **← 今ここ** | ユーザー |" in planning


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
    assert "字数と完全性が衝突したら完全性を優先する" in planning


def test_planning_absorbs_plan_role_into_investigation():
    planning = _section(_skill_text(), "### 2. 調査 + 計画(親)")
    assert "調査は read-only agent へ並列委譲できるが、計画は親が統合する" in planning


def test_approval_puts_summary_first():
    approval = _section(_skill_text(), "### 5. 計画承認")
    assert "レビュー済み計画" in approval
    assert "第 1 層から提示" in approval


def test_backend_change_reopens_inventory():
    backend = _section(_skill_text(), "### 3. backend 選択")
    assert "要件が動いたら step 1 に戻り、「質問する」行をゼロにする" in backend


def test_backend_selection_and_python_gate_contract():
    backend = _section(_skill_text(), "### 3. backend 選択")
    for option in (
        "codex（既定）",
        "cursor-agent",
        "codex review（既定）",
        "`spawn_agent` worker",
        "`spawn_agent` explorer",
    ):
        assert option in backend
    # 表示名ではなく Agent へ実際に渡す alias を書くこと。
    # 2026-07-25 の圧縮で alias が表示名へ置き換わり、委譲時に何を指定するか
    # 分からなくなっていた([P2])。
    assert "`Agent(general-purpose, model=sonnet)`" in backend
    assert "`Agent(general-purpose, model=opus)`" in backend
    assert all(command in backend for command in ("command -v codex", "command -v cursor-agent", "command -v uv"))
    assert "失敗した選択肢は除く" in backend
    assert "thread_id 抽出不能として実装選択肢だけを除く" in backend
    assert "cursor-grok-4.5-high" in backend
    assert "別 backend へ黙って fallback しない" in backend


def test_codex_parent_has_three_roles_without_effort_selection():
    text = _skill_text()
    backend = _section(text, "### 3. backend 選択")
    assert "| Codex | 実装 |" in backend
    assert "| Codex | 計画・diff レビュー |" in backend
    assert "子ごとの effort を選ばない" in text
    assert "model_reasoning_effort" not in backend


def test_pinned_model_effort_and_stdin_contract():
    text = _skill_text()
    assert "Codex のモデルは `gpt-5.6-sol` を `-m` で明示" in text
    assert "世代追従は catch-up と `premises.json` で管理" in text
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
    assert (
        'codex -a never exec -C "<worktree>" -m gpt-5.6-sol '
        '-c model_reasoning_effort="medium" review --base origin/<default> < /dev/null'
    ) in text
    assert "origin なしは `--base <default>`" in text
    approval = _section(text, "### 5. 計画承認")
    assert "計画レビュー / 実装 / diff レビュー" in approval
    assert "承認後だけ plan mode を抜け、承認済み write_scope を有効にする" in approval
    assert "適用可能なモデル / effort" in approval
    assert "### 9. 統合・後始末・完了報告" in text


def test_claude_parent_plan_mode_approval_boundaries():
    text = _skill_text()
    harness = _section(text, "## ハーネス判定と実行差分")
    assert "`EnterPlanMode`" in harness
    assert "`ExitPlanMode`" in harness
    assert "利用不能時だけ計画全文への明示承認" in harness
    assert "step 1-5 は read-only のため plan mode と整合する" in harness
    assert "承認前に step 6 へ進まない" in harness


def test_delegation_records_explicit_thread_id_and_resumes_it():
    text = _skill_text()
    delegation = _section(text, "### 6. worktree 作成と実装委譲")
    repair = _section(text, "### 8. 修正ループ")
    assert "--sandbox workspace-write" in delegation
    assert 'devkit-codex-job.XXXXXX' in delegation
    assert 'echo "JOB_DIR=$JOB_DIR"' in delegation
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
    assert "ジョブごとの JOB_DIR に JSONL を保存" in delegation
    assert '"$(cat "$JOB_DIR/thread-id.txt")"' in repair
    assert (
        'codex -a never -C "<worktree>" --sandbox workspace-write exec resume '
        '-m gpt-5.6-sol -c model_reasoning_effort="medium" '
        '"$(cat "$JOB_DIR/thread-id.txt")" "<指摘と修正指示>" < /dev/null'
    ) in repair
    assert "--last" not in text


def test_cursor_and_worktree_delegation_contract():
    text = _skill_text()
    delegation = _section(text, "### 6. worktree 作成と実装委譲")
    repair = _section(text, "### 8. 修正ループ")
    for token in ("--model cursor-grok-4.5-high", "--trust", "--force", "chat-id.txt"):
        assert token in delegation
    assert 'codex -a never exec -C "<worktree>"' in delegation
    assert '--workspace "<worktree>"' in delegation + repair
    assert (
        'cursor-agent -p --resume "$(cat "$JOB_DIR/chat-id.txt")" --trust --force '
        '--model cursor-grok-4.5-high --workspace "<worktree>" --output-format text "<実装指示>" < /dev/null'
    ) in delegation
    assert '最終引数だけ `"<指摘と修正指示>"` に替える' in repair
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

    assert "実装 backend は commit しない" in delegation
    assert "パス限定で add" in delegation
    assert "`git add .` / `git add -A` は使わない" in delegation

    assert "レビュー前に実装を作業 branch へ commit" in review
    assert "commit 済み差分" in review
    # レビューは worktree 内で実行する。通常 checkout で走らせると commit 済み
    # branch ではなくそちらを対象にし、空 diff を「指摘なし」と誤報する。
    # 2026-07-25 の圧縮で「worktree 内で」の指定が消えていた([P1])。
    assert 'codex -a never exec -C "<worktree>"' in review
    assert "通常 checkout で走らせると" in review
    # 順序保証: 節目 commit の規定が review 節より前にあること
    assert text.index("#### 節目 commit") < text.index(
        "### 7. 自レビューと独立 diff レビュー"
    )


def test_worktree_and_pr_integration_contract():
    text = _skill_text()
    implementation = _section(text, "### 6. worktree 作成と実装委譲")
    integration = _section(text, "### 9. 統合・後始末・完了報告")
    assert "実装系は必ず worktree を使う" in implementation
    assert "origin/HEAD、main、現在 branch の順" in implementation
    # origin なし repo / リモート名が origin でない repo でも worktree を作れること。
    # 2026-07-25 の圧縮で fetch が無条件になり、この経路が壊れていた([P2])。
    assert "origin があれば fetch し、無ければ fetch を省略して基点を `HEAD` にする" in implementation
    assert "remote 名は `origin` 固定で扱う" in implementation
    assert "一時 worktree と `<type>/<slug>` branch を作り" in implementation
    assert "開始 commit を記録" in implementation
    assert "作成失敗時は主 worktree へ移らず停止" in implementation
    assert "実装・検証・レビューは worktree 内だけ" in implementation
    assert "PR 経路の骨格は提出 → CI 待機 → green 判定 → merge → 完了確認 → cleanup" in integration
    # remote branch 削除は期待 tip を束縛する。束縛なしだと確認後に他者が push した
    # commit を捨てうる。2026-07-25 の圧縮で lease の具体形が消えていた([P1])。
    assert "--force-with-lease=refs/heads/<branch>:<検証済みSHA>" in integration
    # 統合後はローカル作業 branch も消す。2026-07-25 の圧縮で worktree と remote の
    # 削除だけが残り、毎回 stale なローカル branch が残る状態だった([P2])。
    assert "`git branch -d <branch>`" in integration
    assert "`git branch -D <branch>`" in integration
    assert "ローカル branch を残したまま完了にしない" in integration
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
    assert "主 worktree が clean、既定 branch 上、非 diverged のときだけ ff-only merge / push" in integration
    assert "push reject は fetch / rebase / 再検証からやり直す" in integration
    assert "origin なしは ff-only merge で完了" in integration
    assert "失敗時は変更を破棄せず" in integration
    for evidence in ("branch", "worktree", "停止操作", "再開方法"):
        assert evidence in integration
    assert "統合成功・cleanup 未完了" in integration


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
    assert "`.claude/plans/YYYY-MM-DD-<slug>.md` へ保存して実装せず終了" in handoff
    assert "独立レビュー" in handoff
    assert "追加承認や独立レビューを行わない" in handoff
    assert "dig は組み込み `/goal` を自動発動しない" in handoff


def test_readme_lists_dig_command():
    assert "`/dig`" in _read("README.md")


def test_openai_yaml_surface():
    metadata_path = SKILL_PATH.parent / "agents" / "openai.yaml"
    assert metadata_path.exists()
    metadata = metadata_path.read_text(encoding="utf-8")
    assert 'display_name: "Dig"' in metadata
    assert "$dig" in metadata
