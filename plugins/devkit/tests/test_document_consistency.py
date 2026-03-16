"""ドキュメント間の整合性テスト."""

from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


def _read(relpath: str) -> str:
    return (REPO_ROOT / relpath).read_text(encoding="utf-8")


# ── 1. workflow.md に 7 フェーズが定義されている ──────────────────


def test_workflow_7_phases():
    text = _read("plugins/devkit/shared/workflow.md")
    assert "7フェーズ必須フロー" in text

    # Phase 1〜7 の見出しが存在する
    for i in range(1, 8):
        assert f"### Phase {i}:" in text, f"Phase {i} heading missing"

    # Phase 8 は存在しない
    assert "### Phase 8:" not in text


# ── 2. AGENTS.md 内の workflow セクションが workflow.md と一致 ──────


def test_agents_md_synced_with_workflow():
    workflow = _read("plugins/devkit/shared/workflow.md")
    agents = _read("AGENTS.md")

    # workflow.md の Review Gate Strategy テーブルからモデル名を抽出
    workflow_models = set(re.findall(r"gpt-[\w.-]+", workflow))
    agents_models = set(re.findall(r"gpt-[\w.-]+", agents))

    # AGENTS.md が workflow.md と同じモデル名を含んでいる
    assert workflow_models, "workflow.md にモデル名が見つからない"
    assert workflow_models <= agents_models, (
        f"AGENTS.md に不足しているモデル名: {workflow_models - agents_models}"
    )

    # 7フェーズの定義が AGENTS.md にも存在する
    assert "7フェーズ必須フロー" in agents or "8フェーズ必須フロー" in agents


# ── 3. dig-core の共通フェーズが workflow.md と一致 ─────────────


def test_dig_core_phases_match_workflow():
    workflow = _read("plugins/devkit/shared/workflow.md")
    dig_core = _read("plugins/devkit/skills/dig-core/SKILL.md")

    # workflow.md から Phase N の名称を抽出
    workflow_phases = re.findall(r"### Phase (\d+): (.+)", workflow)
    # dig-core の「共通フェーズ」セクションから番号付きリストを抽出
    core_phases = re.findall(r"^\d+\.\s+Phase (\d+): (.+)$", dig_core, re.MULTILINE)

    assert len(workflow_phases) == 7, f"workflow.md phases: {workflow_phases}"
    assert len(core_phases) == 7, f"dig-core phases: {core_phases}"

    for (wnum, wname), (cnum, cname) in zip(workflow_phases, core_phases):
        assert wnum == cnum, f"Phase number mismatch: {wnum} != {cnum}"
        assert wname.strip() == cname.strip(), (
            f"Phase {wnum} name mismatch: '{wname.strip()}' != '{cname.strip()}'"
        )


# ── 4. dig-claude の 7 フェーズ一覧が正しい ──────────────────────


def test_dig_claude_phases_match_workflow():
    dig_claude = _read("plugins/devkit/skills/dig-claude/SKILL.md")

    # Phase 1〜7 が言及されている
    for i in range(1, 8):
        assert f"Phase {i}:" in dig_claude, f"dig-claude に Phase {i} が見つからない"

    # Phase 8 は存在しない
    assert "Phase 8:" not in dig_claude


# ── 5. workflow.md の Workflow State Tokens ─────────────────────


def test_workflow_state_tokens_documented():
    text = _read("plugins/devkit/shared/workflow.md")

    # Workflow State Tokens セクションを抽出
    section_match = re.search(
        r"## Workflow State Tokens\s*\n(.*?)(?=\n##|\Z)", text, re.DOTALL
    )
    assert section_match, "Workflow State Tokens セクションが見つからない"
    section = section_match.group(1)

    # 必須トークンが含まれている
    required_tokens = [
        "requirements_confirmed",
        "research_completed",
        "plan_drafted",
        "plan_review_completed",
        "implementation_completed",
        "implementation_review_completed",
        "commit_review_completed",
    ]
    for token in required_tokens:
        assert token in section, f"トークン {token} が Workflow State Tokens に見つからない"

    # intake_declared は含まれない
    assert "intake_declared" not in section, "intake_declared が Workflow State Tokens に残っている"


# ── 6. レビューコマンドの同期 ──────────────────────────────────


def test_review_commands_synced():
    workflow = _read("plugins/devkit/shared/workflow.md")
    dig_claude = _read("plugins/devkit/skills/dig-claude/SKILL.md")
    dig_codex = _read("plugins/devkit/skills/dig-codex/SKILL.md")

    models = ["gpt-5.3-codex-spark", "gpt-5.4"]
    for model in models:
        assert model in workflow, f"workflow.md に {model} が見つからない"
        assert model in dig_claude, f"dig-claude に {model} が見つからない"
        assert model in dig_codex, f"dig-codex に {model} が見つからない"


# ── 7. 全 SKILL.md で "8フェーズ" や "Phase 8" が残っていない ────


def test_no_stale_phase_references():
    skills_dir = REPO_ROOT / "plugins" / "devkit" / "skills"
    stale_files: list[str] = []

    for skill_md in skills_dir.rglob("SKILL.md"):
        text = skill_md.read_text(encoding="utf-8")
        if "8フェーズ" in text or "Phase 8" in text:
            stale_files.append(str(skill_md.relative_to(REPO_ROOT)))

    assert not stale_files, f"古い 8 フェーズ参照が残っている: {stale_files}"
