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
    assert "step 6-9(実装)は承認済み計画の write_scope に従って" in write_contract
    assert "goal-prompt 引き継ぎ時の" in write_contract
    assert "`.claude/plans/` への計画保存" in write_contract


def test_inventory_driven_interview_contract():
    interview = _section(_skill_text(), "### 1. 深掘り(棚卸し駆動面談、親)")
    assert "最初のラウンドでタスク型(実装 / 調査 / 状態確認 / 文書化 / 整理)" in interview
    assert "read-only 終了または goal-prompt 引き継ぎがユーザーから明示された場合は" in interview
    assert "| 未知 | 影響 | 扱い |" in interview
    for value in ("質問する", "仮定で進める", "確定済み"):
        assert value in interview
    assert "「質問する」行がゼロになったら深掘りを終了" in interview
    assert "固定ラウンド数はなく、深さは可変" in interview
    assert "1 ラウンド最大 4 問" in interview


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
        "read-only タスクは通常の最終報告で終了し、worktree を作らない",
    ):
        assert phrase in planning


def test_backend_change_reopens_inventory():
    backend = _section(_skill_text(), "### 3. backend 選択(選択肢付き質問)")
    assert (
        "この時点で read-only 終了や goal-prompt 引き継ぎへ切り替える場合は step 1 の未知棚卸しを再開"
        in backend
    )
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
    assert "実装系では計画レビュー / 実装 / diff レビューの 3 役を明記" in approval
    assert "承認なしで実装に進まない" in approval
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
    assert "`ExitPlanMode` による承認前は step 6(実装)へ進まない" in approval
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
    assert 'devkit-dig-wt.XXXXXX' in worktree
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
    assert "ユーザーが「Goal プロンプトにして」「/goal で動かしたい」「後で実行したい」等を明示した場合だけ" in handoff
    assert "`.claude/plans/YYYY-MM-DD-<slug>.md` へ保存して終了する" in handoff
    assert "独立レビュー" in handoff
    assert "追加承認は行わない" in handoff
    assert "dig 自身は組み込み `/goal` を自動発動しない" in handoff


def test_readme_lists_dig_command():
    assert "`/dig`" in _read("README.md")


def test_openai_yaml_surface():
    metadata_path = SKILL_PATH.parent / "agents" / "openai.yaml"
    assert metadata_path.exists()
    metadata = metadata_path.read_text(encoding="utf-8")
    assert 'display_name: "Dig"' in metadata
    assert "$dig" in metadata
