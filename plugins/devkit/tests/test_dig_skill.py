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


# ── 3. 深掘りインタビューと計画承認の契約 ─────────────────────────


def test_interview_and_approval_contract():
    text = SKILL_PATH.read_text(encoding="utf-8")
    assert "AskUserQuestion" in text, "深掘りインタビューの記述がない"
    assert "ExitPlanMode" in text, "plan mode での計画承認の記述がない"
    assert "承認なしで実装に進まない" in text, "計画承認ゲートの記述がない"


# ── 4. backend 選択の契約 ─────────────────────────────────────────


def test_backend_selection_contract():
    text = SKILL_PATH.read_text(encoding="utf-8")
    assert 'model_reasoning_effort="medium"' in text, "codex の effort 選択肢がない"
    assert "sonnet" in text.lower(), "Claude サブエージェント(Sonnet)の選択肢がない"
    assert "haiku" in text.lower(), "Claude サブエージェント(Haiku)の選択肢がない"
    assert "command -v codex" in text, "codex 不在時のフォールバック判定がない"


# ── 5. 委譲コマンドの契約 ─────────────────────────────────────────


def test_delegation_command_contract():
    text = SKILL_PATH.read_text(encoding="utf-8")
    assert "--sandbox workspace-write" in text, "実装委譲の sandbox が workspace-write でない"
    assert "-a never" in text, "approval policy never の指定がない"
    assert "codex exec resume --last" in text, "修正再委譲（resume --last）の記述がない"
    assert "review --uncommitted" in text, "セカンドオピニオン review の記述がない"
    assert "commit 禁止" in text, "backend への commit 禁止の記述がない"


# ── 6. モデルを焼き込まない（config.toml の既定に従う） ─────────────


def test_no_hardcoded_model():
    text = SKILL_PATH.read_text(encoding="utf-8")
    assert "config.toml" in text, "モデルが config 既定に従う旨の記述がない"
    assert not re.search(r"-m\s+gpt-", text), "委譲コマンドにモデルが焼き込まれている"
    assert "spark" not in text, "旧モデル（spark）への言及が残っている"


# 旧 dig 契約トークンの残存検査は check_legacy_migration.py --mode=repo が repo 全体で担当する。


# ── 7. README にコマンドが掲載されている ──────────────────────────


def test_readme_lists_command():
    readme = _read("README.md")
    assert "`/dig`" in readme, "README に /dig が載っていない"
