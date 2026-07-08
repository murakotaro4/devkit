"""dig スキル(深掘り + 実装委譲オーケストレーション)の契約テスト."""

from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SKILL_PATH = REPO_ROOT / "plugins" / "devkit" / "skills" / "dig" / "SKILL.md"


def _read(relpath: str) -> str:
    return (REPO_ROOT / relpath).read_text(encoding="utf-8")


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


# ── 4. backend 選択の契約 ─────────────────────────────────────────


def test_backend_selection_contract():
    text = SKILL_PATH.read_text(encoding="utf-8")
    assert "effort xhigh" in text, "codex の effort xhigh 選択肢がない"
    assert "effort high" in text, "codex の effort high 選択肢がない"
    assert "effort medium" in text, "codex の effort medium 選択肢がない"
    assert "sonnet" in text.lower(), "Claude サブエージェント(Sonnet)の選択肢がない"
    assert "ゴール化して自律実行" in text, "goal-prompt へ引き継ぐ実装 backend 選択肢がない"
    assert "レビュー済みゴールファイル + 起動プロンプト" in text
    assert "diff レビュー backend の質問を出さない" in text
    assert "haiku" not in text.lower(), "Haiku が選択肢として残っている(v5.1.0 で廃止済み)"
    assert "command -v codex" in text, "codex 不在時のフォールバック判定がない"


# ── 5. 委譲コマンドの契約 ─────────────────────────────────────────


def test_delegation_command_contract():
    text = SKILL_PATH.read_text(encoding="utf-8")
    assert "--sandbox workspace-write" in text, "実装委譲の sandbox が workspace-write でない"
    assert "-a never" in text, "approval policy never の指定がない"
    assert "codex -a never exec resume --last" in text, "修正再委譲（-a never exec resume --last）の記述がない"
    assert not re.search(r"codex exec .*-a never", text), (
        "-a never が codex exec より後ろに置かれた旧語順が残っている"
    )
    assert "review --uncommitted" in text, "セカンドオピニオン review の記述がない"
    assert "commit 禁止" in text, "backend への commit 禁止の記述がない"


# ── 6. モデルを焼き込まない（config 既定に従う） ─────────────────────


def test_no_hardcoded_model():
    text = SKILL_PATH.read_text(encoding="utf-8")
    assert "config 既定" in text, "モデルが config 既定に従う旨の記述がない"
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


# ── 8. 9 step フロー(完了報告 step まで揃っている) ─────────────────


def test_nine_step_flow_contract():
    text = SKILL_PATH.read_text(encoding="utf-8")
    assert "### 9. 完了報告" in text, "9 step 目の完了報告見出しがない"


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


# ── 12. codex exec の stdin 閉鎖契約 ──────────────────────────────


def test_codex_stdin_guard():
    text = SKILL_PATH.read_text(encoding="utf-8")
    offenders = [
        line for line in text.splitlines()
        if "codex -a never exec" in line and "< /dev/null" not in line
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
