"""setup スキル(ルール同期 + Claude Code 環境設定)の契約テスト."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from hashlib import sha256
from pathlib import Path

import pytest

from conftest import require_symlink_support


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
REFERENCE_DIR = SKILL_PATH.parent / "references"


def _skill_text() -> str:
    parts = [SKILL_PATH.read_text(encoding="utf-8")]
    parts.extend(path.read_text(encoding="utf-8") for path in sorted(REFERENCE_DIR.glob("*.md")))
    return "\n".join(parts)


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
    text = _skill_text()
    match = re.match(r"^---\n(.*?)\n---\n\n(.*)$", text, re.DOTALL)
    assert match, "frontmatter が見つからない"
    frontmatter = match.group(1)
    assert frontmatter == (
        'name: "setup"\n'
        'description: "DevKitのルールを対象リポジトリへ、利用資産をユーザー環境へ同期する。『セットアップして』『ルール同期して』『/setup』で起動"\n'
        'argument-hint: "[target]"\n'
        'allowed-tools: ["Read", "Grep", "Glob", "Bash", "Write", "Edit", '
        '"AskUserQuestion", "request_user_input", "TaskCreate", "TaskUpdate"]'
    )
    assert match.group(2).startswith("# /setup\n")


def test_harness_matrix_and_approval_boundary():
    text = _skill_text()
    harness = text.split("## ハーネス判定", 1)[1].split("## 実行前提", 1)[0]
    assert "request_user_input` は判定キーに使わない" in harness
    assert "通常の同期・prune に差分承認ゲートは置かない" in text
    assert "承認が必要なのは statusline と Windows Terminal font だけ" in text


def test_progressive_references_are_reachable():
    main = SKILL_PATH.read_text(encoding="utf-8")
    for name in ("environment.md", "sync-matrix.md"):
        assert (REFERENCE_DIR / name).is_file()
        assert f"references/{name}" in main
    assert "直前に" in main


def test_environment_prerequisite_matrix():
    text = (REFERENCE_DIR / "environment.md").read_text(encoding="utf-8")
    section = text.split("## 環境前提チェック", 1)[1].split("## statusline 適用", 1)[0]
    for cmd in ("claude", "codex", "cursor-agent", "node", "uv"):
        assert f"`{cmd}`" in section
    assert "tmux" not in section
    assert "`uv` | 必須同期と Windows font を実行できないため、同期前に停止" in section
    assert "`node` | statusline だけ skip。他の同期と font は継続" in section
    assert "`brew install uv`" in section
    assert "`winget install --id astral-sh.uv`" in section
    assert "インストール自体は行わない" in section


def test_sync_target_matrix_is_complete():
    sync = (REFERENCE_DIR / "sync-matrix.md").read_text(encoding="utf-8")
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
    text = _skill_text()
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
    text = _skill_text()
    assert "CLAUDE_CODE_AUTO_COMPACT_WINDOW=1000000" in text
    assert "CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=50" in text
    assert "project / local / managed scope" in text
    assert "新規セッション" in text


def test_windows_font_approval_and_failure_boundary():
    text = (REFERENCE_DIR / "environment.md").read_text(encoding="utf-8")
    section = text.split("## ターミナルフォント適用(Windows のみ)", 1)[1]
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
    metadata = json.loads((repo / ".agents/devkit-rules.json").read_text(encoding="utf-8"))
    assert metadata["version"] == "2"
    assert isinstance(metadata["synced_at"], str) and metadata["synced_at"]
    normalized_template = template.read_text(encoding="utf-8").encode("utf-8")
    expected_template_sha256 = sha256(normalized_template).hexdigest()
    assert metadata["template_sha256"] == expected_template_sha256
    assert (repo / ".agents/devkit-rules-backup/AGENTS.md.bak").exists()

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
    assert not (repo / ".agents/devkit-rules.json").exists()


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
    text = _skill_text()

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


CONFIG_REL = ".agents/devkit-rules-config.json"


def _configured_repo(tmp_path, harness="codex-only", policy="repo-local"):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    (repo / ".agents").mkdir()
    (repo / CONFIG_REL).write_text(
        json.dumps({"version": 1, "harness": harness, "policy": policy}), encoding="utf-8"
    )
    return repo


def _snapshot(root):
    # Include directories, content and mtimes: no-op must not rewrite identical data.
    return {
        str(path.relative_to(root)): (
            "dir" if path.is_dir() else path.read_bytes(), path.stat().st_mtime_ns
        )
        for path in root.rglob("*")
    }


def _protected_home():
    home = Path(os.environ["HOME"])
    assert home == Path(os.environ["USERPROFILE"])
    for name in (".claude/settings.json", ".codex/AGENTS.md", ".local/bin/update-ccx", "font.ttf"):
        path = home / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("protected user environment", encoding="utf-8")
    return home


@pytest.mark.parametrize("harness", ["dual", "codex-only"])
@pytest.mark.parametrize("policy", ["devkit", "repo-local"])
def test_rules_harness_and_authority_are_independent(tmp_path, harness, policy):
    repo = _configured_repo(tmp_path, harness, policy)
    home = _protected_home()
    home_before = _snapshot(home)
    config_before = (repo / CONFIG_REL).read_bytes()
    assert _run_sync_json(repo, TEMPLATE_PATH)["changed"]
    text = (repo / "AGENTS.md").read_text(encoding="utf-8")
    assert (repo / "CLAUDE.md").exists() == (harness == "dual")
    assert not (repo / ".claude").exists()
    assert "devkit:policy:" not in text
    assert ("## Review Rules" in text) == (policy == "devkit")
    assert ("ユーザーの明示指示なしで commit / push" in text) == (policy == "devkit")
    assert "管理節外" in text
    metadata = json.loads((repo / ".agents/devkit-rules.json").read_text())
    assert metadata["harness"] == harness
    assert metadata["policy"] == policy
    before = _snapshot(repo)
    assert _run_sync_json(repo, TEMPLATE_PATH) == {"actions": [], "changed": False, "skipped": True}
    assert _snapshot(repo) == before
    assert (repo / CONFIG_REL).read_bytes() == config_before
    assert _snapshot(home) == home_before


def test_codex_only_preserves_legacy_and_outside_bytes_and_removes_old_authority(tmp_path):
    repo = _configured_repo(tmp_path)
    legacy_paths = (
        "CLAUDE.md", ".claude/devkit-rules.json",
        ".claude/devkit-rules-backup/AGENTS.md.bak", ".claude/state/protected.json",
    )
    for name in legacy_paths:
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"protected\r\ninvalid json too\r\n")
    legacy_before = {name: ((repo / name).read_bytes(), (repo / name).stat().st_mtime_ns) for name in legacy_paths}
    prefix = "# Repo authority\r\n承認済み範囲は継続。レビューは条件付き。stage/commit/pushは禁止。\r\n".encode()
    suffix = "\r\n## 固有規則\r\n保護データは変更しない。\r\n".encode()
    old = prefix + (
        "<!-- devkit:rules:start -->\r\n"
        "実装前に計画を提示し、ユーザー承認を得る。\r\n"
        "独立した review を 1 回以上実施する。\r\n"
        "ユーザーの明示指示なしで commit / push まで自動で行う。\r\n"
        "<!-- devkit:rules:end -->\r\n"
    ).encode() + suffix
    (repo / "AGENTS.md").write_bytes(old)
    assert _run_sync_json(repo, TEMPLATE_PATH)["changed"]
    current = (repo / "AGENTS.md").read_bytes()
    assert current.startswith(prefix) and current.endswith(suffix)
    block = current.decode().split("<!-- devkit:rules:start -->")[1].split("<!-- devkit:rules:end -->")[0]
    for unwanted in ("## Commit Rules", "## Review Rules", "ユーザー承認を得る", "独立した review", "自動で行う", "`/dig`"):
        assert unwanted not in block
    assert (repo / ".agents/devkit-rules-backup/AGENTS.md.bak").read_bytes() == old
    before = _snapshot(repo)
    assert not _run_sync_json(repo, TEMPLATE_PATH)["changed"]
    assert _snapshot(repo) == before
    assert {name: ((repo / name).read_bytes(), (repo / name).stat().st_mtime_ns) for name in legacy_paths} == legacy_before


@pytest.mark.parametrize("config", [
    "{", "[]", "null", '{}',
    '{"version":1,"harness":"codex-only"}',
    '{"version":true,"harness":"codex-only","policy":"repo-local"}',
    '{"version":2,"harness":"codex-only","policy":"repo-local"}',
    '{"version":1,"harness":"codex","policy":"repo-local"}',
    '{"version":1,"harness":"codex-only","policy":"unknown"}',
    '{"version":1,"harness":[],"policy":"repo-local"}',
    '{"version":1,"harness":"codex-only","policy":"repo-local","extra":1}',
    '{"version":1,"harness":"dual","harness":"codex-only","policy":"repo-local"}',
])
@pytest.mark.parametrize("dry_args", [(), ("--dry-run",)])
def test_invalid_rules_config_has_no_partial_writes(tmp_path, config, dry_args):
    repo = _configured_repo(tmp_path)
    (repo / CONFIG_REL).write_text(config)
    (repo / "AGENTS.md").write_text("unchanged")
    home = _protected_home()
    before, home_before = _snapshot(repo), _snapshot(home)
    result = _run_sync(repo, TEMPLATE_PATH, *dry_args, check=False)
    assert result.returncode != 0
    assert "invalid rules config" in result.stderr
    assert _snapshot(repo) == before
    assert _snapshot(home) == home_before


@pytest.mark.parametrize("markers", [
    "<!-- devkit:rules:start -->\n",
    "<!-- devkit:rules:end -->\n",
    "<!-- devkit:rules:end -->\n<!-- devkit:rules:start -->\n",
    "<!-- devkit:rules:start -->\n<!-- devkit:rules:end -->\n" * 2,
    "<!-- devkit:rules:start ->\n<!-- devkit:rules:end -->\n",
    "prefix <!-- devkit:rules:start -->\n<!-- devkit:rules:end -->\n",
])
def test_invalid_rules_markers_preflight_all_writes(tmp_path, markers):
    repo = _configured_repo(tmp_path)
    (repo / "AGENTS.md").write_text(markers)
    before = _snapshot(repo)
    assert _run_sync(repo, TEMPLATE_PATH, check=False).returncode != 0
    assert _snapshot(repo) == before


@pytest.mark.parametrize("existing", [False, True])
@pytest.mark.parametrize("harness", ["dual", "codex-only"])
def test_repo_rules_dry_run_preserves_all_surfaces(tmp_path, existing, harness):
    repo = _configured_repo(tmp_path, harness)
    home = _protected_home()
    (repo / "AGENTS.md").write_text("# local authority\n")
    if existing:
        _run_sync_json(repo, TEMPLATE_PATH)
        # Force a planned AGENTS/backup/metadata update on the next run.
        with (repo / "AGENTS.md").open("a") as handle:
            handle.write("\n<!-- no managed edit -->\n")
        template = tmp_path / "template.md"
        template.write_text(TEMPLATE_PATH.read_text() + "\nUpdated shared text.\n")
    else:
        template = TEMPLATE_PATH
    before, home_before = _snapshot(repo), _snapshot(home)
    assert _run_sync_json(repo, template, "--dry-run")["changed"]
    assert _snapshot(repo) == before
    assert _snapshot(home) == home_before


@pytest.mark.parametrize("relative", [
    "AGENTS.md", CONFIG_REL, ".agents/devkit-rules.json",
    ".agents/devkit-rules-backup/AGENTS.md.bak", ".agents", ".agents/devkit-rules-backup",
])
def test_rules_rejects_symlink_write_paths_before_partial_update(tmp_path, relative):
    require_symlink_support()
    repo = _configured_repo(tmp_path)
    external = tmp_path / "external"
    external.mkdir()
    path = repo / relative
    if path.is_dir():
        path.rename(external / "saved")
        path.symlink_to(external / "saved", target_is_directory=True)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            path.rename(external / "saved")
        else:
            (external / "saved").write_text("protected")
        path.symlink_to(external / "saved")
    before, external_before = _snapshot(repo), _snapshot(external)
    result = _run_sync(repo, TEMPLATE_PATH, check=False)
    assert result.returncode != 0
    assert "unsafe" in result.stderr
    assert _snapshot(repo) == before
    assert _snapshot(external) == external_before


def test_repo_local_rejects_unscoped_custom_template(tmp_path):
    repo = _configured_repo(tmp_path)
    template = tmp_path / "custom.md"
    template.write_text("Automatically commit and push")
    before = _snapshot(repo)
    assert _run_sync(repo, template, check=False).returncode != 0
    assert _snapshot(repo) == before


def test_repo_only_skill_routes_before_user_environment_checks():
    text = SKILL_PATH.read_text()
    section = text.split("## 同期範囲", 1)[1].split("## 実行前提", 1)[0]
    assert "--repo-only" in section and "sync_rules.py" in section
    assert "だけを実行して検証・報告後に終了" in section
    for target in ("thought-db", "updater", "prune", "Claude 環境変数", "shim", "statusline", "font"):
        assert target in section
    assert "ユーザー環境用の環境前提チェックも実行しない" in section


def test_default_dual_then_explicit_codex_only_keeps_legacy_metadata(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    legacy = repo / ".claude"
    legacy.mkdir()
    (legacy / "devkit-rules.json").write_text('{"version":"1"}')
    (legacy / "devkit-rules-backup").mkdir()
    (legacy / "devkit-rules-backup/AGENTS.md.bak").write_text("protected old backup")
    old = _snapshot(legacy)
    _run_sync_json(repo, TEMPLATE_PATH)
    assert (repo / "CLAUDE.md").is_file()
    assert "## DevKit Workflow" in (repo / "AGENTS.md").read_text()
    assert not _run_sync_json(repo, TEMPLATE_PATH)["changed"]
    assert _snapshot(legacy) == old
    claude_before = (repo / "CLAUDE.md").read_bytes()
    (repo / CONFIG_REL).write_text(json.dumps({"version": 1, "harness": "codex-only", "policy": "repo-local"}))
    _run_sync_json(repo, TEMPLATE_PATH)
    assert "## DevKit Workflow" not in (repo / "AGENTS.md").read_text()
    assert _snapshot(legacy) == old
    assert (repo / "CLAUDE.md").read_bytes() == claude_before
    assert not _run_sync_json(repo, TEMPLATE_PATH)["changed"]


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "nested", "managed"])
def test_invalid_policy_template_does_not_partially_write(tmp_path, mutation):
    repo = _configured_repo(tmp_path)
    text = TEMPLATE_PATH.read_text()
    marker = "<!-- devkit:policy:repo-local:end -->"
    if mutation == "missing":
        text = text.replace(marker, "")
    elif mutation == "duplicate":
        text += marker
    elif mutation == "nested":
        text = text.replace(marker, "<!-- devkit:policy:unknown:start -->" + marker)
    else:
        text += "<!-- devkit:rules:start -->"
    template = tmp_path / "template.md"
    template.write_text(text)
    before = _snapshot(repo)
    assert _run_sync(repo, template, check=False).returncode != 0
    assert _snapshot(repo) == before


def test_codex_only_does_not_follow_protected_claude_links(tmp_path):
    require_symlink_support()
    repo = _configured_repo(tmp_path)
    external = tmp_path / "protected"
    external.mkdir()
    (external / "entry.md").write_text("protected")
    (repo / ".claude").symlink_to(external, target_is_directory=True)
    (repo / "CLAUDE.md").symlink_to(external / "entry.md")
    before = _snapshot(external)
    assert _run_sync_json(repo, TEMPLATE_PATH)["changed"]
    assert not _run_sync_json(repo, TEMPLATE_PATH)["changed"]
    assert _snapshot(external) == before
    assert (repo / ".claude").is_symlink()
    assert (repo / "CLAUDE.md").is_symlink()
