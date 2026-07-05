"""ドキュメント間の整合性テスト."""

from __future__ import annotations

import json
import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
DISTRIBUTED_SKILLS = ("dig", "improve-skill", "setup", "refactor", "memory-review")
PLUGIN_DESCRIPTION_SURFACES = ("/dig", "skill 改善", "setup", "refactor", "memory-review")


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
    for skill_name in DISTRIBUTED_SKILLS:
        assert skill_name in text, f"AGENTS.md に v7 の配布 skill がない: {skill_name}"


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


# ── 4. marketplace description は plugin.json と一致している ───────


def test_marketplace_descriptions_match_plugin_json():
    plugin = json.loads(_read("plugins/devkit/.claude-plugin/plugin.json"))
    expected = plugin["description"]
    market = json.loads(_read(".claude-plugin/marketplace.json"))
    assert market["plugins"][0]["description"] == expected, "ルート marketplace の description が不一致"
    assert not (REPO_ROOT / "plugins/devkit/.claude-plugin/marketplace.json").exists(), (
        "重複 marketplace manifest が残っている"
    )


def test_distributed_skill_mentions_stay_in_sync():
    plugin = json.loads(_read("plugins/devkit/.claude-plugin/plugin.json"))
    documents = {
        "README.md": _read("README.md"),
        "plugins/devkit/scripts/README.md": _read("plugins/devkit/scripts/README.md"),
    }

    for doc_name, text in documents.items():
        for skill_name in DISTRIBUTED_SKILLS:
            assert skill_name in text, f"{doc_name} に配布 skill がない: {skill_name}"

    for surface in PLUGIN_DESCRIPTION_SURFACES:
        assert surface in plugin["description"], f"plugin description に配布 surface がない: {surface}"


# ── 5. pyproject の pythonpath は存在するディレクトリだけを指す ─────


def test_pyproject_pythonpath_entries_exist():
    text = _read("plugins/devkit/pyproject.toml")
    match = re.search(r"^pythonpath\s*=\s*\[(.*?)\]", text, re.MULTILINE)
    assert match, "pyproject.toml に pythonpath がない"
    entries = re.findall(r'"([^"]+)"', match.group(1))
    for entry in entries:
        assert (REPO_ROOT / "plugins" / "devkit" / entry).is_dir(), f"pythonpath が不存在: {entry}"


# ── 6. skill frontmatter name はディレクトリ名と一致する ─────────────


def test_skill_frontmatter_name_matches_directory():
    skills_dir = REPO_ROOT / "plugins" / "devkit" / "skills"
    for skill_path in sorted(skills_dir.glob("*/SKILL.md")):
        text = skill_path.read_text(encoding="utf-8")
        match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
        assert match, f"{skill_path} に frontmatter がない"
        name_match = re.search(r'^name:\s*"([^"]+)"\s*$', match.group(1), re.MULTILINE)
        assert name_match, f"{skill_path} に name がない"
        assert name_match.group(1) == skill_path.parent.name, f"{skill_path} の name とディレクトリ名が不一致"


# ── 7. AGENTS.md の codex exec stdin 閉鎖契約 ─────────────────────


def test_agents_codex_stdin_guard():
    text = _read("AGENTS.md")
    offenders = [
        line for line in text.splitlines()
        if "codex -a never exec" in line and "< /dev/null" not in line
    ]
    assert not offenders, f"stdin 閉鎖(< /dev/null)がない codex コマンド行: {offenders}"


# ── 8. Release Rules の正本は AGENTS.md、README は参照 ─────────────


def test_release_rules_canonical_in_agents_md():
    agents = _read("AGENTS.md")
    readme = _read("README.md")
    assert "この節が version 運用ルールの正本" in agents, "AGENTS.md に Release Rules の正本宣言がない"
    assert "正本は `AGENTS.md` の「Release Rules」" in readme, "README が Release Rules の正本を参照していない"
    for doc_name, text in (("AGENTS.md", agents), ("README.md", readme)):
        assert "以下なら push を block" in text, (
            f"{doc_name} の pre-push gate 文言が実装(compare_semver <= 0 で block)と不一致"
        )


# ── 9. スキル共通契約・採用基準の正本化と参照 ──────────────────────


def test_shared_skill_contract_canonical_and_referenced():
    agents = _read("AGENTS.md")
    assert "## スキル共通契約" in agents, "AGENTS.md にスキル共通契約の節がない"
    assert "## スキル採用基準" in agents, "AGENTS.md にスキル採用基準の節がない"

    for skill_name in DISTRIBUTED_SKILLS:
        text = _read(f"plugins/devkit/skills/{skill_name}/SKILL.md")
        assert "スキル共通契約" in text, f"{skill_name} の SKILL.md が共通契約を参照していない"


def test_no_hardcoded_codex_model_in_contracts():
    # モデルは config 既定に従い、契約・ルールへ焼き込まない(dig の設計原則)。
    documents = ["AGENTS.md"] + [
        f"plugins/devkit/skills/{skill_name}/SKILL.md" for skill_name in DISTRIBUTED_SKILLS
    ]
    for relpath in documents:
        text = _read(relpath)
        offenders = [
            line for line in text.splitlines()
            if re.search(r"codex[^\n]*\s-m\s+\S+", line, re.IGNORECASE) or "gpt-5.3-codex-spark" in line
        ]
        assert not offenders, f"{relpath} に codex モデルの焼き込みがある: {offenders}"
