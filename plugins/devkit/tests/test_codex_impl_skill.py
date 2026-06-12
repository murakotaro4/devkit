"""codex-impl スキルの契約テスト."""

from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SKILL_PATH = REPO_ROOT / "plugins" / "devkit" / "skills" / "codex-impl" / "SKILL.md"


def _read(relpath: str) -> str:
    return (REPO_ROOT / relpath).read_text(encoding="utf-8")


# ── 1. SKILL.md が存在し BOM なし ─────────────────────────────────


def test_skill_exists_without_bom():
    assert SKILL_PATH.exists(), "codex-impl の SKILL.md が存在しない"
    buf = SKILL_PATH.read_bytes()
    assert buf[:3] != b"\xef\xbb\xbf", "codex-impl の SKILL.md に UTF-8 BOM がある"


# ── 2. frontmatter の必須フィールド ───────────────────────────────


def test_skill_frontmatter():
    text = SKILL_PATH.read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    assert match, "frontmatter が見つからない"
    frontmatter = match.group(1)
    assert 'name: "codex-impl"' in frontmatter
    assert "description:" in frontmatter
    assert "argument-hint:" in frontmatter
    assert "allowed-tools:" in frontmatter and '"Bash"' in frontmatter


# ── 3. 委譲コマンドの契約 ─────────────────────────────────────────


def test_delegation_command_contract():
    text = SKILL_PATH.read_text(encoding="utf-8")
    assert "--sandbox workspace-write" in text, "実装委譲の sandbox が workspace-write でない"
    assert "-a never" in text, "approval policy never の指定がない"
    assert "codex exec resume --last" in text, "修正再委譲（resume --last）の記述がない"
    assert "review --uncommitted" in text, "セカンドオピニオン review の記述がない"


# ── 4. モデルを焼き込まない（config.toml の既定に従う） ─────────────


def test_no_hardcoded_model():
    text = SKILL_PATH.read_text(encoding="utf-8")
    assert "config.toml" in text, "モデルが config 既定に従う旨の記述がない"
    assert not re.search(r"-m\s+gpt-", text), "委譲コマンドにモデルが焼き込まれている"
    assert "spark" not in text, "旧モデル（spark）への言及が残っている"


# ── 5. README にコマンドが掲載されている ──────────────────────────


def test_readme_lists_command():
    readme = _read("README.md")
    assert "/devkit:codex-impl" in readme, "README に /devkit:codex-impl が載っていない"
