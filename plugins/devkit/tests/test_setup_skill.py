"""setup スキル(ルール同期 + Claude Code 環境設定)の契約テスト."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from hashlib import sha256
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SKILL_PATH = REPO_ROOT / "plugins/devkit/skills/setup/SKILL.md"
OPENAI_PATH = REPO_ROOT / "plugins/devkit/skills/setup/agents/openai.yaml"
SCRIPT_PATH = REPO_ROOT / "plugins/devkit/skills/setup/scripts/sync_rules.py"
TEMPLATE_PATH = REPO_ROOT / "plugins/devkit/templates/rules/agents-rules.md"
THOUGHT_SCRIPT_PATH = REPO_ROOT / "plugins/devkit/skills/setup/scripts/sync_thought_db.py"
THOUGHT_TEMPLATE_PATH = REPO_ROOT / "plugins/devkit/templates/rules/thought-db-user.md"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def _run_sync(
    repo: Path,
    template: Path,
    *extra_args: str,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--target",
            str(repo),
            "--template",
            str(template),
            *extra_args,
            "--format",
            "json",
        ],
        check=check,
        capture_output=True,
        text=True,
    )
    return result


def _run_sync_json(repo: Path, template: Path, *extra_args: str) -> dict[str, object]:
    return json.loads(_run_sync(repo, template, *extra_args).stdout)


def test_skill_frontmatter():
    text = SKILL_PATH.read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    assert match, "frontmatter が見つからない"
    frontmatter = match.group(1)

    assert 'name: "setup"' in frontmatter
    assert "description:" in frontmatter
    assert "セットアップして" in frontmatter
    assert "ルール同期して" in frontmatter
    assert "/setup" in frontmatter
    assert 'argument-hint: "[target]"' in frontmatter
    assert "allowed-tools:" in frontmatter
    assert '"Write"' in frontmatter
    assert '"Edit"' in frontmatter
    assert '"request_user_input"' in frontmatter


def test_skill_contract_mentions_markers_idempotency_and_harness():
    text = SKILL_PATH.read_text(encoding="utf-8")

    assert "devkit:rules:start" in text
    assert "devkit:rules:end" in text
    assert "冪等" in text
    assert "no-op" in text
    assert "## ハーネス判定" in text
    assert "Claude 親" in text
    assert "Codex 親" in text


def test_openai_agent_metadata_exists():
    text = OPENAI_PATH.read_text(encoding="utf-8")

    assert 'display_name: "Setup"' in text
    assert "$setup" in text


def test_rules_template_has_no_retired_tokens():
    text = TEMPLATE_PATH.read_text(encoding="utf-8")
    retired_tokens = [
        "devkit-" "init",
        "shared/" "workflow.md",
        "open" "code",
        "devkit:" "workflow",
        "/devkit:" "dig",
        "auto-" "retro",
    ]

    for token in retired_tokens:
        assert token not in text


def test_rules_template_contract():
    text = TEMPLATE_PATH.read_text(encoding="utf-8")

    assert "このセクションは devkit の /setup により自動管理される" in text
    assert "手動編集は上書きされる" in text
    assert "`/dig`" in text
    assert "Conventional Commits" in text
    assert "`summary` は日本語" in text
    assert "独立した review" in text
    assert "再 review" in text
    assert "Release Rules" not in text
    assert "plugin.json" not in text


def test_sync_rules_script_is_idempotent_and_preserves_user_content(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    (repo / "AGENTS.md").write_text("# Project Rules\n\nKeep this line.\n", encoding="utf-8")
    template = tmp_path / "agents-rules.md"
    template.write_text("Managed rules v1\n\n- Use /dig.\n", encoding="utf-8")

    first = _run_sync_json(repo, template)

    assert first["changed"] is True
    agents = (repo / "AGENTS.md").read_text(encoding="utf-8")
    assert "<!-- devkit:rules:start -->" in agents
    assert "<!-- devkit:rules:end -->" in agents
    assert "Managed rules v1" in agents
    assert "Keep this line." in agents
    assert (repo / "CLAUDE.md").read_text(encoding="utf-8").splitlines().count("@./AGENTS.md") == 1
    metadata = json.loads((repo / ".claude/devkit-rules.json").read_text(encoding="utf-8"))
    assert metadata["version"] == "1"
    assert isinstance(metadata["synced_at"], str) and metadata["synced_at"]
    assert metadata["template_sha256"] == sha256(template.read_bytes()).hexdigest()
    assert (repo / ".claude/devkit-rules-backup/AGENTS.md.bak").exists()

    second = _run_sync_json(repo, template)

    assert second == {"actions": [], "changed": False, "skipped": True}

    with (repo / "AGENTS.md").open("a", encoding="utf-8", newline="\n") as handle:
        handle.write("\nUser-owned rule outside markers.\n")
    template.write_text("Managed rules v2\n\n- Keep planning explicit.\n", encoding="utf-8")

    third = _run_sync_json(repo, template)

    assert third["changed"] is True
    updated_agents = (repo / "AGENTS.md").read_text(encoding="utf-8")
    assert "Managed rules v2" in updated_agents
    assert "Managed rules v1" not in updated_agents
    assert "Keep this line." in updated_agents
    assert "User-owned rule outside markers." in updated_agents
    assert (repo / "CLAUDE.md").read_text(encoding="utf-8").splitlines().count("@./AGENTS.md") == 1


def test_sync_rules_dry_run_does_not_write(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    (repo / "AGENTS.md").write_text("# Project Rules\n", encoding="utf-8")
    template = tmp_path / "agents-rules.md"
    template.write_text("Managed rules\n", encoding="utf-8")

    result = json.loads(_run_sync(repo, template, "--dry-run").stdout)

    assert result["changed"] is True
    assert "<!-- devkit:rules:start -->" not in (repo / "AGENTS.md").read_text(encoding="utf-8")
    assert not (repo / "CLAUDE.md").exists()
    assert not (repo / ".claude/devkit-rules.json").exists()


def test_sync_rules_normalizes_duplicate_claude_reference(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    (repo / "CLAUDE.md").write_text("@./AGENTS.md\n\n@./AGENTS.md\n", encoding="utf-8")
    template = tmp_path / "agents-rules.md"
    template.write_text("Managed rules\n", encoding="utf-8")

    result = _run_sync_json(repo, template)

    assert result["changed"] is True
    assert (repo / "CLAUDE.md").read_text(encoding="utf-8").splitlines().count("@./AGENTS.md") == 1


def test_sync_rules_rejects_duplicate_agents_markers(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    (repo / "AGENTS.md").write_text(
        "<!-- devkit:rules:start -->\na\n<!-- devkit:rules:end -->\n"
        "<!-- devkit:rules:start -->\nb\n<!-- devkit:rules:end -->\n",
        encoding="utf-8",
    )
    template = tmp_path / "agents-rules.md"
    template.write_text("Managed rules\n", encoding="utf-8")

    result = _run_sync(repo, template, check=False)

    assert result.returncode != 0
    assert "zero or one devkit rules marker pair" in result.stderr


def _run_thought_sync_raw(
    thought_db: Path,
    claude_file: Path,
    codex_file: Path,
    template: Path,
    *extra_args: str,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(THOUGHT_SCRIPT_PATH),
            "--thought-db",
            str(thought_db),
            "--claude-file",
            str(claude_file),
            "--codex-file",
            str(codex_file),
            "--template",
            str(template),
            *extra_args,
            "--format",
            "json",
        ],
        check=check,
        capture_output=True,
        text=True,
    )


def _run_thought_sync(
    thought_db: Path,
    claude_file: Path,
    codex_file: Path,
    template: Path,
    *extra_args: str,
) -> dict[str, object]:
    return json.loads(_run_thought_sync_raw(thought_db, claude_file, codex_file, template, *extra_args).stdout)


def test_skill_contract_mentions_thought_db_sync():
    text = SKILL_PATH.read_text(encoding="utf-8")

    assert "devkit:thought-db:start" in text
    assert "devkit:thought-db:end" in text
    assert "sync_thought_db.py" in text
    assert "thought-db-user.md" in text


def test_thought_db_template_contract():
    text = THOUGHT_TEMPLATE_PATH.read_text(encoding="utf-8")

    assert "このセクションは devkit の /setup により自動管理される" in text
    assert "overview.md" in text
    assert "topics/" in text
    assert "changelog.md" in text
    assert "非公開" in text


def test_sync_thought_db_creates_blocks_and_is_idempotent(tmp_path):
    thought_db = tmp_path / "thought-db"
    thought_db.mkdir()
    claude_file = tmp_path / "claude/CLAUDE.md"
    codex_file = tmp_path / "codex/AGENTS.md"
    claude_file.parent.mkdir()
    claude_file.write_text("# ユーザーレベル指示\n\nKeep this user line.\n", encoding="utf-8")
    template = tmp_path / "thought-db-user.md"
    template.write_text("Reference block v1\n", encoding="utf-8")

    first = _run_thought_sync(thought_db, claude_file, codex_file, template)

    assert first["changed"] is True
    assert sorted(first["actions"]) == [
        "append_claude_user_block",
        "backup_claude_user",
        "create_codex_user",
    ]
    for path in (claude_file, codex_file):
        text = path.read_text(encoding="utf-8")
        assert "<!-- devkit:thought-db:start -->" in text
        assert "<!-- devkit:thought-db:end -->" in text
        assert "Reference block v1" in text
    assert "Keep this user line." in claude_file.read_text(encoding="utf-8")
    backup = claude_file.parent / "devkit-thought-db-backup/CLAUDE.md.bak"
    assert backup.read_text(encoding="utf-8") == "# ユーザーレベル指示\n\nKeep this user line.\n"

    second = _run_thought_sync(thought_db, claude_file, codex_file, template)

    assert second == {"actions": [], "changed": False, "skipped": True}

    template.write_text("Reference block v2\n", encoding="utf-8")

    third = _run_thought_sync(thought_db, claude_file, codex_file, template)

    assert third["changed"] is True
    assert sorted(third["actions"]) == [
        "backup_claude_user",
        "backup_codex_user",
        "update_claude_user_block",
        "update_codex_user_block",
    ]
    updated = claude_file.read_text(encoding="utf-8")
    assert "Reference block v2" in updated
    assert "Reference block v1" not in updated
    assert "Keep this user line." in updated
    assert "Reference block v1" in backup.read_text(encoding="utf-8")


def test_sync_thought_db_rejects_duplicate_markers(tmp_path):
    thought_db = tmp_path / "thought-db"
    thought_db.mkdir()
    claude_file = tmp_path / "claude/CLAUDE.md"
    claude_file.parent.mkdir()
    claude_file.write_text(
        "<!-- devkit:thought-db:start -->\na\n<!-- devkit:thought-db:end -->\n"
        "<!-- devkit:thought-db:start -->\nb\n<!-- devkit:thought-db:end -->\n",
        encoding="utf-8",
    )
    codex_file = tmp_path / "codex/AGENTS.md"
    template = tmp_path / "thought-db-user.md"
    template.write_text("Reference block\n", encoding="utf-8")

    result = _run_thought_sync_raw(thought_db, claude_file, codex_file, template, check=False)

    assert result.returncode != 0
    assert "zero or one devkit thought-db marker pair" in result.stderr
    assert not codex_file.exists()


def test_sync_thought_db_skips_when_thought_db_missing(tmp_path):
    claude_file = tmp_path / "claude/CLAUDE.md"
    codex_file = tmp_path / "codex/AGENTS.md"
    template = tmp_path / "thought-db-user.md"
    template.write_text("Reference block\n", encoding="utf-8")

    result = _run_thought_sync(tmp_path / "missing-thought-db", claude_file, codex_file, template)

    assert result["skipped"] is True
    assert result["changed"] is False
    assert "thought-db not found" in str(result["reason"])
    assert not claude_file.exists()
    assert not codex_file.exists()


def test_sync_thought_db_dry_run_does_not_write(tmp_path):
    thought_db = tmp_path / "thought-db"
    thought_db.mkdir()
    claude_file = tmp_path / "claude/CLAUDE.md"
    codex_file = tmp_path / "codex/AGENTS.md"
    template = tmp_path / "thought-db-user.md"
    template.write_text("Reference block\n", encoding="utf-8")

    result = _run_thought_sync(thought_db, claude_file, codex_file, template, "--dry-run")

    assert result["changed"] is True
    assert not claude_file.exists()
    assert not codex_file.exists()


def test_sync_rules_rejects_devkit_repository_itself(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    (repo / "plugins/devkit/.claude-plugin").mkdir(parents=True)
    (repo / "plugins/devkit/.claude-plugin/plugin.json").write_text("{}\n", encoding="utf-8")
    template = tmp_path / "agents-rules.md"
    template.write_text("Managed rules\n", encoding="utf-8")

    result = _run_sync(repo, template, check=False)

    assert result.returncode != 0
    assert "DevKit repository itself" in result.stderr
