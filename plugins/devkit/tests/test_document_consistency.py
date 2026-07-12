"""ドキュメント間の整合性テスト."""

from __future__ import annotations

import json
import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
DISTRIBUTED_SKILLS = (
    "dig",
    "improve-skill",
    "setup",
    "refactor",
    "memory-review",
    "goal-prompt",
    "handoff",
    "backlog",
    "catch-up",
)
PLUGIN_DESCRIPTION_SURFACES = (
    "/dig",
    "skill 改善",
    "setup",
    "refactor",
    "memory-review",
    "goal-prompt",
    "handoff",
    "/catch-up",
)


def _read(relpath: str) -> str:
    return (REPO_ROOT / relpath).read_text(encoding="utf-8")


def _backtick_fence(line: str) -> tuple[int, str] | None:
    match = re.match(r"^(`{3,})(.*)$", line)
    if not match:
        return None
    return len(match.group(1)), match.group(2).strip()


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


# ── 7. skill Markdown のコードフェンスは壊れていない ───────────────


def test_skill_markdown_fences_are_balanced():
    for skill_name in DISTRIBUTED_SKILLS:
        relpath = f"plugins/devkit/skills/{skill_name}/SKILL.md"
        open_fence: tuple[int, int] | None = None

        for line_no, line in enumerate(_read(relpath).splitlines(), start=1):
            fence = _backtick_fence(line)
            if fence is None:
                continue

            fence_len, info = fence
            if open_fence is None:
                open_fence = (fence_len, line_no)
                continue

            open_len, open_line_no = open_fence
            if fence_len < open_len:
                continue
            if not info:
                open_fence = None
                continue

            raise AssertionError(
                f"{relpath}:{line_no} に未エスケープの入れ子コードフェンスがある: "
                f"{line!r} (外側開始: {open_line_no} 行目、{open_len} バッククォート)"
            )

        assert open_fence is None, f"{relpath}:{open_fence[1]} のコードフェンスが閉じていない"


# ── 8. AGENTS.md の codex exec stdin 閉鎖契約 ─────────────────────


def test_agents_codex_stdin_guard():
    text = _read("AGENTS.md")
    offenders = [
        line for line in text.splitlines()
        if "codex -a never exec" in line and "< /dev/null" not in line
    ]
    assert not offenders, f"stdin 閉鎖(< /dev/null)がない codex コマンド行: {offenders}"


# ── 9. Release Rules の正本は AGENTS.md、README は参照 ─────────────


def test_release_rules_canonical_in_agents_md():
    agents = _read("AGENTS.md")
    readme = _read("README.md")
    assert "この節が version 運用ルールの正本" in agents, "AGENTS.md に Release Rules の正本宣言がない"
    assert "正本は `AGENTS.md` の「Release Rules」" in readme, "README が Release Rules の正本を参照していない"
    for doc_name, text in (("AGENTS.md", agents), ("README.md", readme)):
        assert "以下なら push を block" in text, (
            f"{doc_name} の pre-push gate 文言が実装(compare_semver <= 0 で block)と不一致"
        )


# ── 10. スキル共通契約・採用基準の正本化と参照 ─────────────────────


def test_shared_skill_contract_canonical_and_referenced():
    agents = _read("AGENTS.md")
    assert "## スキル共通契約" in agents, "AGENTS.md にスキル共通契約の節がない"
    assert "## スキル採用基準" in agents, "AGENTS.md にスキル採用基準の節がない"

    for skill_name in DISTRIBUTED_SKILLS:
        text = _read(f"plugins/devkit/skills/{skill_name}/SKILL.md")
        assert "スキル共通契約" in text, f"{skill_name} の SKILL.md が共通契約を参照していない"


def test_codex_model_pinned_to_current_generation():
    # モデルは gpt-5.6-sol に固定する。世代追従は catch-up + premises.json が担う。
    documents = ["AGENTS.md"] + [
        f"plugins/devkit/skills/{skill_name}/SKILL.md" for skill_name in DISTRIBUTED_SKILLS
    ]
    for relpath in documents:
        text = _read(relpath)
        offenders = [
            line for line in text.splitlines()
            if re.search(r"codex[^\n]*\s-m\s+(?!gpt-5\.6-sol\b)\S+", line, re.IGNORECASE)
            or "gpt-5.3-codex-spark" in line
        ]
        assert not offenders, f"{relpath} に gpt-5.6-sol 以外の codex モデル焼き込みがある: {offenders}"


def test_codex_model_and_effort_contract_stays_in_sync():
    documents = {
        "AGENTS.md": _read("AGENTS.md"),
        "plugins/devkit/skills/dig/SKILL.md": _read("plugins/devkit/skills/dig/SKILL.md"),
        "plugins/devkit/skills/goal-prompt/SKILL.md": _read(
            "plugins/devkit/skills/goal-prompt/SKILL.md"
        ),
    }
    for doc_name, text in documents.items():
        assert "gpt-5.6-sol" in text, f"{doc_name} に固定モデル(gpt-5.6-sol)の記載がない"
        assert "catch-up" in text and "premises.json" in text, (
            f"{doc_name} に世代追従(catch-up + premises.json)の記載がない"
        )
        assert "推薦既定" not in text, f"{doc_name} に旧モデル非固定契約が残っている"
        assert "Max は対応 surface の最深推論" in text
        assert "Ultra は並列オーケストレーション" in text
        concrete_efforts = set(
            re.findall(r'model_reasoning_effort="([^"<>]+)"', text)
        )
        assert concrete_efforts <= {"medium"}, (
            f"{doc_name} に medium 以外の effort が残っている: {concrete_efforts}"
        )


def test_dig_goal_prompt_switching_terms_stay_in_sync():
    documents = {
        "AGENTS.md": _read("AGENTS.md"),
        "README.md": _read("README.md"),
        "plugins/devkit/skills/dig/SKILL.md": _read("plugins/devkit/skills/dig/SKILL.md"),
        "plugins/devkit/skills/goal-prompt/SKILL.md": _read(
            "plugins/devkit/skills/goal-prompt/SKILL.md"
        ),
    }
    for doc_name, text in documents.items():
        assert "自律度" in text, f"{doc_name} に使い分け軸(自律度)がない"
        assert "ゴール化" in text, f"{doc_name} に dig 連携語(ゴール化)がない"
        assert "起動プロンプト" in text, f"{doc_name} に goal-prompt 境界語(起動プロンプト)がない"


def test_rebase_conflict_resolution_contract_stays_in_sync():
    agents = _read("AGENTS.md")
    heading = "### 統合時 rebase 衝突の標準解消手順"
    assert heading in agents, "AGENTS.md に rebase 衝突の標準解消手順がない"

    contract = agents.split(heading, 1)[1].split("\n## ", 1)[0]
    for keyword in ("追加のみ", "和集合", "削除", "停止", "git rebase --abort", "verify-full", "片側"):
        assert keyword in contract, f"rebase 衝突の標準解消手順に契約キーワードがない: {keyword}"

    dig = _read("plugins/devkit/skills/dig/SKILL.md")
    integration = dig.split("### 統合(step 9、終了条件達成後)", 1)[1].split("\n### ", 1)[0]
    assert "標準解消手順" in integration, "dig の統合手順が標準解消手順を参照していない"
    assert "git rebase --abort" in integration, "dig の統合手順に未知の衝突時の abort fallback がない"
