"""dig スキル(深掘り + 実装委譲オーケストレーション)の契約テスト."""

from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SKILL_PATH = REPO_ROOT / "plugins" / "devkit" / "skills" / "dig" / "SKILL.md"


def _read(relpath: str) -> str:
    return (REPO_ROOT / relpath).read_text(encoding="utf-8")


def _between(text: str, start: str, end: str) -> str:
    start_index = text.index(start)
    end_index = text.index(end, start_index + len(start))
    return text[start_index:end_index]


# ── 1. SKILL.md が存在する(BOM 検査は check_utf8_bom.py が担当) ──


def test_skill_exists():
    assert SKILL_PATH.exists(), "dig の SKILL.md が存在しない"


# ── 2. frontmatter の必須フィールド ───────────────────────────────


def test_skill_frontmatter():
    text = SKILL_PATH.read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    assert match, "frontmatter が見つからない"
    frontmatter = match.group(1)
    assert 'name: "dig"' in frontmatter
    assert "description:" in frontmatter
    assert "argument-hint:" in frontmatter
    assert "allowed-tools:" in frontmatter and '"Bash"' in frontmatter
    assert '"AskUserQuestion"' in frontmatter, "深掘りに必要な AskUserQuestion がない"
    assert '"ExitPlanMode"' in frontmatter, "計画承認に必要な ExitPlanMode がない"
    assert '"Skill"' in frontmatter, "goal-prompt 引き継ぎに必要な Skill がない"


# ── 3. 深掘りインタビューと計画承認の契約 ─────────────────────────


def test_interview_and_approval_contract():
    text = SKILL_PATH.read_text(encoding="utf-8")
    assert "AskUserQuestion" in text, "深掘りインタビューの記述がない"
    assert "ExitPlanMode" in text, "plan mode での計画承認の記述がない"
    assert "承認なしで実装に進まない" in text, "計画承認ゲートの記述がない"
    assert "通常実装では計画レビュー / 実装 / diff レビューの 3 役を明記" in text
    assert "実装 backend が「ゴール化して自律実行」の場合は diff レビュー backend を明記せず" in text
    assert "goal-prompt のゴール本文に実装後レビュー要件を焼き込む" in text
    assert "モデル / effort は選択した backend で適用可能な場合だけ追記" in text
    assert "モデル / effort 非対応の経路は「適用なし」" in text
    assert "Codex のモデル欄は固定名ではなく当該 runtime / account の推薦既定" in text


# ── 4. backend 選択の契約 ─────────────────────────────────────────


def test_backend_selection_contract():
    text = SKILL_PATH.read_text(encoding="utf-8")
    claude_parent = _between(text, "#### Claude 親の選択肢", "#### Codex 親の選択肢")
    implementation = _between(claude_parent, "実装 backend:", "計画レビュー / diff レビュー backend")
    review = _between(
        claude_parent,
        "計画レビュー / diff レビュー backend",
        "- Codex のモデルは指定せず",
    )

    implementation_efforts = ["effort low", "effort medium", "effort high", "effort xhigh"]
    implementation_positions = [implementation.index(value) for value in implementation_efforts]
    assert implementation_positions == sorted(implementation_positions)
    assert implementation.count("| codex — effort") == 4
    assert "標準の実装(既定)" in implementation
    assert "決定論的・低リスクな実装だけ" in implementation
    assert "複雑・高リスクな実装" in implementation
    assert "ユーザー明示、または代表タスクの実測で品質向上を確認できた例外" in implementation

    review_efforts = ["effort medium", "effort high", "effort xhigh"]
    review_positions = [review.index(value) for value in review_efforts]
    assert review_positions == sorted(review_positions)
    assert review.count("| codex review — effort") == 3
    assert "effort low" not in review, "計画 / diff レビューに Low が混入している"
    assert "標準の計画レビュー / diff レビュー(既定)" in review

    assert not re.search(r'model_reasoning_effort="(?:max|ultra)"', text, re.IGNORECASE)
    assert not re.search(r"\beffort (?:max|ultra)\b", claude_parent, re.IGNORECASE)
    assert "Max は対応 surface の最深推論" in claude_parent
    assert "Ultra は並列オーケストレーション" in claude_parent
    assert "backend 選択肢、CLI の effort、config 値にはしない" in claude_parent
    assert "sonnet" in text.lower(), "Claude サブエージェント(Sonnet)の選択肢がない"
    assert "ゴール化して自律実行" in text, "goal-prompt へ引き継ぐ実装 backend 選択肢がない"
    assert "レビュー済みゴールファイル + 起動プロンプト" in text
    assert "diff レビュー backend の質問を出さない" in text
    assert "haiku" not in text.lower(), "Haiku が選択肢として残っている(v5.1.0 で廃止済み)"
    assert "command -v codex" in text, "codex 不在時のフォールバック判定がない"


def test_python3_gate_only_removes_claude_codex_implementation():
    text = SKILL_PATH.read_text(encoding="utf-8")
    claude_parent = _between(text, "#### Claude 親の選択肢", "#### Codex 親の選択肢")

    assert "`command -v python3`" in claude_parent
    assert "thread_id 抽出に必要な prerequisite 不足としてユーザーへ報告" in claude_parent
    assert "Codex の実装 backend だけを除外" in claude_parent
    assert "Codex の計画レビュー / diff レビュー選択肢は残し" in claude_parent
    assert "黙って別 backend へ fallback しない" in claude_parent
    assert "`command -v codex` が通らない場合は codex の選択肢を除外" in claude_parent


# ── 5. 委譲コマンドの契約 ─────────────────────────────────────────


def test_delegation_command_contract():
    text = SKILL_PATH.read_text(encoding="utf-8")
    assert "--sandbox workspace-write" in text, "実装委譲の sandbox が workspace-write でない"
    assert "-a never" in text, "approval policy never の指定がない"
    assert "--last" not in text, "並列ジョブを誤選択し得る resume --last が残っている"
    assert not re.search(r"codex exec .*-a never", text), (
        "-a never が codex exec より後ろに置かれた旧語順が残っている"
    )
    assert "review --base origin/<default>" in text, "remote の default を基点にする review の記述がない"
    assert "commit 禁止" in text, "backend への commit 禁止の記述がない"


def test_codex_job_records_and_resumes_explicit_thread_id():
    text = SKILL_PATH.read_text(encoding="utf-8")
    delegation = _between(text, "### 6. 実装委譲", "### 7. 自レビュー")
    repair = _between(text, "### 8. 修正ループ", "### 9. 統合・後始末・完了報告")

    assert 'devkit-codex-job.XXXXXX' in delegation
    assert 'echo "JOB_DIR=$JOB_DIR"' in delegation
    assert "echo された JOB_DIR を親が記録" in delegation
    assert "set -o pipefail" in delegation
    assert (
        'codex -a never exec -C "<worktree>" --sandbox workspace-write '
        '-c model_reasoning_effort="<選択>" --json "<実装指示>" < /dev/null '
        '| tee "$JOB_DIR/codex-events.jsonl"'
    ) in delegation
    assert 'event.get("type") == "thread.started"' in delegation
    assert "events=[" not in delegation, "thread ID 抽出で全 event を保持している"
    assert "len(ids) == 1" in delegation
    assert "isinstance(ids[0], str)" in delegation
    assert 'event.get("thread_id")' in delegation
    assert '> "$JOB_DIR/thread-id.txt"' in delegation
    assert 'test -s "$JOB_DIR/thread-id.txt"' in delegation
    assert "resume せず委譲失敗として報告" in delegation
    assert "JOB_DIR / `codex-events.jsonl` / `thread-id.txt` をジョブごとに発行・分離" in delegation

    assert "初回の対象 worktree" in repair
    assert "workspace-write sandbox" in repair
    assert "approval policy" in repair
    assert "選択 effort" in repair
    assert "ジョブ固有 thread_id" in repair
    assert (
        'codex -a never -C "<worktree>" --sandbox workspace-write exec resume '
        '-c model_reasoning_effort="<選択>" '
        '"$(cat "$JOB_DIR/thread-id.txt")" "<指摘と修正指示>" < /dev/null'
    ) in repair


# ── 6. モデルを焼き込まない（config 既定に従う） ─────────────────────


def test_no_hardcoded_model():
    text = SKILL_PATH.read_text(encoding="utf-8")
    assert "当該 runtime / account で利用可能な推薦既定" in text
    assert "ユーザーがモデルを明示指定した場合に限り `-m` を付ける" in text
    assert not re.search(r"-m\s+gpt-", text), "委譲コマンドにモデルが焼き込まれている"
    assert "spark" not in text, "旧モデル（spark）への言及が残っている"


# 旧 dig 契約トークンの残存検査は check_legacy_migration.py --mode=repo が repo 全体で担当する。


# ── 7. 3 役 backend 選択(計画レビュー / 実装 / diff レビュー) ─────


def test_three_role_backend_selection_contract():
    text = SKILL_PATH.read_text(encoding="utf-8")
    assert "計画レビュー" in text, "計画レビュー役の記述がない"
    assert "backend 選択" in text, "backend 選択 step の記述がない"
    assert "実装 backend で「ゴール化して自律実行」を選ぶ場合" in text
    assert "実装後レビューは goal-prompt が作るゴール本文の要件が担う" in text
    assert "model=opus" in text, "diff レビュー用 Claude サブエージェント(Opus)の記述がない"
    assert "model=sonnet" in text, "実装用 Claude サブエージェント(Sonnet)の記述がない"


def test_codex_parent_spawn_agent_does_not_select_effort():
    text = SKILL_PATH.read_text(encoding="utf-8")
    codex_parent = _between(text, "#### Codex 親の選択肢", "### 4. 計画レビュー")
    assert "子 agent ごとの effort を選択・指定しない" in codex_parent
    assert "並列数や役割分担は実装戦略" in codex_parent
    assert "model_reasoning_effort" not in codex_parent


# ── 8. 9 step フロー(完了報告 step まで揃っている) ─────────────────


def test_nine_step_flow_contract():
    text = SKILL_PATH.read_text(encoding="utf-8")
    assert "### 9. 統合・後始末・完了報告" in text, "9 step 目の統合・完了報告見出しがない"


# ── 9. 計画レビュー step の記述(read-only sandbox) ──────────────


def test_plan_review_step_contract():
    text = SKILL_PATH.read_text(encoding="utf-8")
    assert "### 4. 計画レビュー" in text, "計画レビュー step の見出しがない"
    assert "--sandbox read-only" in text, "計画レビューの read-only sandbox 指定がない"


# ── 10. README にコマンドが掲載されている ──────────────────────────


def test_readme_lists_command():
    readme = _read("README.md")
    assert "`/dig`" in readme, "README に /dig が載っていない"


# ── 11. cursor-agent 実装 backend の契約 ──────────────────────────


def test_cursor_backend_contract():
    text = SKILL_PATH.read_text(encoding="utf-8")
    assert "--model composer-2.5" in text, "cursor-agent のモデル明示(composer-2.5)がない"
    assert "Composer 2.5" in text, "Composer 2.5 の選択肢ラベルがない"
    assert "cursor-agent -p" in text, "cursor-agent のヘッドレス実行(-p)の記述がない"
    assert "--trust" in text, "cursor-agent の workspace 信頼(--trust)の記述がない"
    assert "command -v cursor-agent" in text, "cursor-agent 不在時のフォールバック判定がない"
    assert "--resume" in text, "cursor-agent の修正ループ(--resume)の記述がない"
    assert "--force" in text, "cursor-agent のヘッドレス自動許可(--force)の記述がない"
    assert "chat-id.txt" in text, "chatId の保存先契約がない"
    assert "[--sandbox enabled]" not in text, "sandbox 有無が未確定のまま placeholder が残っている"
    assert "sandbox なし" in text, "sandbox なし運用の警告がない"
    assert "--sandbox enabled" not in text, "sandbox なし契約と矛盾する記述がある"


def test_worktree_delegation_commands():
    text = SKILL_PATH.read_text(encoding="utf-8")
    delegation = _between(text, "### 6. 実装委譲", "### 7. 自レビュー")
    repair = _between(text, "### 8. 修正ループ", "### 9. 統合・後始末・完了報告")

    assert 'codex -a never exec -C "<worktree>"' in delegation
    assert (
        'JOB_DIR=<echo された記録済みのパス> && cursor-agent -p --resume '
        '"$(cat "$JOB_DIR/chat-id.txt")" --trust --force --model composer-2.5 '
        '--workspace "<worktree>" --output-format text "<実装指示>"'
    ) in delegation
    assert 'codex -a never -C "<worktree>"' in repair
    assert (
        'JOB_DIR=<step 6 で記録したパス> && cursor-agent -p --resume '
        '"$(cat "$JOB_DIR/chat-id.txt")" --trust --force --model composer-2.5 '
        '--workspace "<worktree>" --output-format text "<指摘と修正指示>"` を Bash '
        '`run_in_background` で起動し、リダイレクトなしで TaskOutput を確認する'
    ) in repair
    assert (
        'JOB_DIR=<step 6 で記録したパス> && cursor-agent -p --resume '
        '"$(cat "$JOB_DIR/chat-id.txt")" --trust --force --model composer-2.5 '
        '--workspace "<worktree>" --output-format text "<指摘と修正指示>" > '
        '"$JOB_DIR/cursor-agent.log" 2>&1` を shell 経由で実行し、ログ増分で進捗を確認する'
    ) in repair
    assert '-C "<repo>" --sandbox workspace-write' not in delegation
    assert '--workspace "<repo>"' not in delegation + repair


# ── 12. codex exec の stdin 閉鎖契約 ──────────────────────────────


def test_codex_stdin_guard():
    text = SKILL_PATH.read_text(encoding="utf-8")
    offenders = [
        line for line in text.splitlines()
        if re.search(r"\bcodex\s+-a\s+never\b.*\bexec\b", line)
        and "< /dev/null" not in line
    ]
    assert not offenders, f"stdin 閉鎖(< /dev/null)がない codex コマンド行: {offenders}"
    assert "< /dev/null" in text, "codex exec の stdin 閉鎖(< /dev/null)の記述がない"


def test_goal_handoff_contract():
    text = SKILL_PATH.read_text(encoding="utf-8")
    assert "## dig / goal-prompt 使い分け" in text
    assert "自律度" in text
    assert "ゴール化して自律実行" in text
    assert "ゴール化引き継ぎ" in text
    assert 'Skill(skill: "devkit:goal-prompt"' in text
    assert "commit・push 禁止 / 実装後の独立レビュー要件" in text
    assert "目的 / write_scope / 受け入れ条件 / 検証コマンド / 非対象" in text
    assert "commit / push 禁止" in text
    assert "実装後の独立レビュー要件" in text
    assert "レビュー済みゴールファイル + 起動プロンプトを作成" in text
    assert "dig もそこで終了し、step 7-9 は実行しない" in text
    assert "diff レビュー backend の質問を出さない" in text
    assert "実装と別系統の独立レビュー(codex review 等)を実施し指摘ゼロ" in text
    assert "commit / push 禁止と合わせて転記必須項目" in text
    assert "監視または引き渡し" not in text
    assert "step 7(自レビュー)以降を続行" not in text
    assert ".claude/worktrees/" not in text


def test_worktree_integration_contract():
    text = SKILL_PATH.read_text(encoding="utf-8")
    worktree = _between(text, "## worktree 運用と統合", "## フロー")

    assert "非 git repo" in worktree
    assert "ゴール化して自律実行" in worktree
    assert "調査のみの dig" in worktree
    assert 'git symbolic-ref --short refs/remotes/origin/HEAD' in worktree
    assert "結果から `origin/` プレフィックスを取り除いた名前を `<default>`" in worktree
    assert "取得できなければ `main`" in worktree
    assert "`main` も無ければ現在のブランチ" in worktree
    assert "fetch 失敗は警告を報告して続行し、統合前に再試行" in worktree
    assert 'WT_DIR=$(mktemp -d "${TMPDIR:-/tmp}/devkit-dig-wt.XXXXXX")' in worktree
    assert 'worktree add -b <type>/<slug> "$WT_DIR/wt" origin/<default>' in worktree
    assert 'git -C "<worktree>" rev-parse HEAD' in worktree
    assert "worktree add に使った起点の `<base-commit>` として親が記録" in worktree
    assert "ブランチ名が既存なら `-2` から連番" in worktree
    assert "mktemp ディレクトリを削除" in worktree
    assert "main ツリー実装へ黙って戻らず" in worktree
    assert "実装 backend は従来どおり commit 禁止" in worktree
    assert "git add <そのジョブの write_scope>" in worktree
    assert "`git add .` と `git add -A` は使わない" in worktree
    assert "pre-commit hook(prek 等)が unstaged 変更を stash" in worktree
    assert "並列ジョブが実行中の間は節目 commit を保留" in worktree
    assert "全ジョブ回収後に、ジョブ単位で順にパス限定 commit" in worktree
    assert "review --base origin/<default>" in text
    assert "origin なし repo は `--base <default>`" in text
    assert "worktree 内で `codex" in text
    assert "`git diff <記録した基点>...HEAD` を全文読み" in text
    assert 'merge --ff-only <branch>' in worktree
    assert 'push origin <default>' in worktree
    assert "PR 経路" in worktree
    assert "gh pr create" in worktree
    assert "CI 確認まで" in worktree
    assert "PR 提出完了" in worktree
    assert "merge は人間が行い" in worktree
    assert "変更を破棄しない" in worktree
    assert "git rebase --abort" in worktree
    assert "`--force` せず" in worktree
    assert "git worktree remove" in worktree
    assert "git branch -d <branch>" in worktree
    assert "origin なし repo では fetch / push / PR 経路を省略" in worktree
    assert "`merge --ff-only` までで統合完了と扱い(push なし)" in worktree
    assert "報告にその旨を明記" in worktree
    assert "push reject は fetch して手順 1 からやり直し、version の再計算もやり直す" in worktree
    assert "commit / push はユーザー指示があった場合のみ" not in text

    integration = _between(worktree, "### 統合(step 9、終了条件達成後)", "### 失敗時の共通契約")
    fetch_position = integration.index("1. `git fetch origin` を再試行")
    version_position = integration.index("2. その後、repo の release 規則")
    assert fetch_position < version_position

    backend_selection = _between(text, "### 3. backend 選択", "### 4. 計画レビュー")
    assert "統合方法も 1 問で確認" in backend_selection
    assert "既定推奨は「直接統合」" in backend_selection
    assert "`command -v gh` が通らない場合" in backend_selection
    assert "「ゴール化して自律実行」の場合と非 git repo" in backend_selection
    assert "または origin なし repo では PR 選択肢を出さない" in backend_selection

    claude_parent = _between(text, "#### Claude 親の選択肢", "#### Codex 親の選択肢")
    review_table = _between(
        claude_parent,
        "計画レビュー / diff レビュー backend",
        "- Codex のモデルは指定せず",
    )
    for effort in ("medium", "high", "xhigh"):
        assert (
            f'codex -a never exec -c model_reasoning_effort="{effort}" '
            'review --base origin/<default> < /dev/null'
        ) in review_table
    assert review_table.count("origin なし repo は `--base <default>`") == 3

    self_review = _between(text, "### 7. 自レビュー", "### 8. 修正ループ")
    assert (
        'codex -a never exec -c model_reasoning_effort="<選択>" '
        'review --base origin/<default> < /dev/null'
    ) in self_review
    assert "origin なし repo は `--base <default>`" in self_review
