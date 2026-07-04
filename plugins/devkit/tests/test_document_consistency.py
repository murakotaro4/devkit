"""ドキュメント間の整合性テスト."""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


def _read(relpath: str) -> str:
    return (REPO_ROOT / relpath).read_text(encoding="utf-8")


# ── 1. CLAUDE.md が AGENTS.md を正本として参照している ─────────────


def test_claude_md_imports_agents_md():
    text = _read("CLAUDE.md")
    assert "@./AGENTS.md" in text, "CLAUDE.md が AGENTS.md を import していない"


# ── 2. AGENTS.md に repo 固有ルールが揃っている ────────────────────


def test_agents_md_core_rules():
    text = _read("AGENTS.md")
    assert "Conventional Commits" in text, "AGENTS.md にコミット規約がない"
    assert "Codex Exec 相談ルール" in text, "AGENTS.md に codex exec 相談ルールがない"
    assert "version" in text, "AGENTS.md に version bump ルールがない"


# ── 3. AGENTS.md に旧ワークフロー契約が残っていない ────────────────


def test_agents_md_no_legacy_contract():
    # 旧契約の個別トークンは check_legacy_migration.py が repo 全体で検査する。
    # ここでは AGENTS.md 固有の旧構造(埋め込み共有ワークフロー)の残存だけを見る。
    text = _read("AGENTS.md")
    for legacy in (
        "Workflow State Tokens",
        "7フェーズ必須フロー",
        "devkit:workflow:start",
    ):
        assert legacy not in text, f"AGENTS.md に旧ワークフロー契約が残っている: {legacy}"
