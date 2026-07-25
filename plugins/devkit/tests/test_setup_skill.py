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
TERMINAL_FONT_SCRIPT_PATH = REPO_ROOT / "plugins/devkit/skills/setup/scripts/setup_terminal_font.py"
UPDATER_SCRIPT_PATH = REPO_ROOT / "plugins/devkit/skills/setup/scripts/sync_updater.py"
CURSOR_PRUNE_SCRIPT_PATH = REPO_ROOT / "plugins/devkit/skills/setup/scripts/prune_legacy_cursor_sync.py"
CLAUDE_ENV_SCRIPT_PATH = REPO_ROOT / "plugins/devkit/skills/setup/scripts/sync_claude_env.py"
CURSOR_SHIM_SCRIPT_PATH = REPO_ROOT / "plugins/devkit/skills/setup/scripts/sync_cursor_agent_shims.py"


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
    match = re.match(r"^---\n(.*?)\n---\n\n(.*)$", text, re.DOTALL)
    assert match, "frontmatter が見つからない"
    frontmatter = match.group(1)
    assert frontmatter == (
        'name: "setup"\n'
        'description: "対象リポジトリへ DevKit 標準ルールを、ユーザー環境へ updater・compaction env・cursor-agent シムを同期し旧 updater 名と Cursor 同期資産の残骸を prune する。「セットアップして」「ルール同期して」「/setup」で起動"\n'
        'argument-hint: "[target]"\n'
        'allowed-tools: ["Read", "Grep", "Glob", "Bash", "Write", "Edit", '
        '"AskUserQuestion", "request_user_input", "TaskCreate", "TaskUpdate"]'
    )
    assert match.group(2).startswith("# /setup\n")


def test_harness_matrix_and_approval_boundary():
    text = SKILL_PATH.read_text(encoding="utf-8")
    harness = text.split("## ハーネス判定", 1)[1].split("## 実行前提", 1)[0]
    for token in ("AskUserQuestion", "spawn_agent", "request_user_input"):
        assert token in harness
    assert "request_user_input` は判定キーに使わない" in harness
    assert "通常の同期・prune に差分承認ゲートは置かない" in text
    assert "承認が必要なのは statusline と Windows Terminal font だけ" in text


def test_environment_prerequisite_matrix():
    text = SKILL_PATH.read_text(encoding="utf-8")
    section = text.split("### 2. 環境前提チェック", 1)[1].split("## 同期", 1)[0]
    for cmd in ("claude", "codex", "cursor-agent", "node", "uv"):
        assert f"`{cmd}`" in section
    assert "tmux" not in section
    assert "`uv` | 必須同期と Windows font を実行できないため、同期前に停止" in section
    assert "`node` | statusline だけ skip。他の同期と font は継続" in section
    assert "`brew install uv`" in section
    assert "`winget install --id astral-sh.uv`" in section
    assert "インストール自体は行わない" in section


def test_sync_target_matrix_is_complete():
    text = SKILL_PATH.read_text(encoding="utf-8")
    sync = text.split("## 同期", 1)[1].split("## 承認が必要な適用", 1)[0]
    expected = {
        "repo rules": "sync_rules.py",
        "thought-db": "sync_thought_db.py",
        "updater": "sync_updater.py",
        "旧 Cursor 資産": "prune_legacy_cursor_sync.py",
        "compaction env": "sync_claude_env.py",
        "cursor-agent シム": "sync_cursor_agent_shims.py",
    }
    table = re.search(
        r"^\| 対象 \| `<script>` / `<args>` \| 冪等性・保全 \| 失敗時 \|\n"
        r"^\|[-|]+\|\n"
        r"((?:^\|.*\|\n)+)",
        sync,
        re.MULTILINE,
    )
    assert table, "同期対象表が見つからない"
    rows = [[cell.strip() for cell in line.strip("|").split("|")] for line in table.group(1).splitlines()]
    assert len(rows) == len(expected)
    assert {row[0] for row in rows} == set(expected)
    for target, script in expected.items():
        row = next(row for row in rows if row[0] == target)
        assert len(row) == 4
        assert script in row[1]
        assert row[2]
        assert row[3]
    assert sync.count('uv run --no-project --python ">=3.10" python') == 1
    assert all(field in sync for field in ("`changed`", "`skipped`", "`actions`"))
    assert all(
        path.is_file()
        for path in (
            SCRIPT_PATH,
            THOUGHT_SCRIPT_PATH,
            UPDATER_SCRIPT_PATH,
            CURSOR_PRUNE_SCRIPT_PATH,
            CLAUDE_ENV_SCRIPT_PATH,
            CURSOR_SHIM_SCRIPT_PATH,
        )
    )


def test_marker_compaction_and_cursor_safety_invariants():
    text = SKILL_PATH.read_text(encoding="utf-8")
    for marker in (
        "devkit:rules:start",
        "devkit:rules:end",
        "devkit:thought-db:start",
        "devkit:thought-db:end",
    ):
        assert marker in text
    assert "@./AGENTS.md" in text
    assert "`skip_prune_modified` / `skip_irregular` は保持" in text
    assert "manifest がなければ directory を作らず skip" in text
    assert ".cursor/skills" in text


def test_compaction_env_values_are_literal_and_scoped():
    text = SKILL_PATH.read_text(encoding="utf-8")
    assert "CLAUDE_CODE_AUTO_COMPACT_WINDOW=1000000" in text
    assert "CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=50" in text
    assert "project / local / managed scope" in text
    assert "新規セッション" in text


def test_windows_font_approval_and_failure_boundary():
    text = SKILL_PATH.read_text(encoding="utf-8")
    section = text.split("### 9. ターミナルフォント適用(Windows のみ)", 1)[1].split(
        "### 10. 検証とレポート", 1
    )[0]
    assert "UDEV Gothic NF" in text
    assert "setup_terminal_font.py" in section
    assert "--check --format json" in section
    assert "選択肢付き質問で承認後" in section
    assert "ダウンロード失敗" in section
    assert "SHA-256 不一致" in section
    assert TERMINAL_FONT_SCRIPT_PATH.is_file()


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
    template.write_text("Managed rules v1\n\n- Use /dig-goal.\n", encoding="utf-8")

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
    normalized_template = template.read_text(encoding="utf-8").encode("utf-8")
    expected_template_sha256 = sha256(normalized_template).hexdigest()
    assert metadata["template_sha256"] == expected_template_sha256
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
