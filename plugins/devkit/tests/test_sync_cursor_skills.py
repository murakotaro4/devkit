from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from hashlib import sha256
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "plugins/devkit/skills/setup/scripts/sync_cursor_skills.py"
PLUGIN_ROOT = ROOT / "plugins/devkit"
SURFACE_CHECK = PLUGIN_ROOT / "scripts/check_skill_surface.py"


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SYNC = load_module(SCRIPT, "sync_cursor_skills_test")


def make_source(tmp_path: Path) -> Path:
    source = tmp_path / "plugin"
    for skill_name in SYNC.EXPECTED_SKILLS:
        skill_dir = source / "skills" / skill_name
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_bytes(f"---\nname: {skill_name}\n---\n本文\n".encode())
    nested = source / "skills/setup/scripts"
    nested.mkdir(parents=True)
    for script_name in ("sync_rules.py", "sync_updater.py", "sync_cursor_skills.py"):
        shutil.copy2(PLUGIN_ROOT / "skills/setup/scripts" / script_name, nested / script_name)

    for template_name in ("rules", "codex"):
        template_dir = source / "templates" / template_name
        template_dir.mkdir(parents=True)
        (template_dir / f"{template_name}.txt").write_text(f"{template_name}\n", encoding="utf-8")
    shutil.copy2(
        PLUGIN_ROOT / "templates/rules/agents-rules.md",
        source / "templates/rules/agents-rules.md",
    )

    scripts = source / "scripts"
    scripts.mkdir(parents=True)
    for file_name in SYNC.UPDATER_FILES:
        shutil.copy2(PLUGIN_ROOT / "scripts" / file_name, scripts / file_name)

    statusline = source / "statusline"
    statusline.mkdir(parents=True)
    for file_name in ("install.js", "statusline.js"):
        shutil.copy2(PLUGIN_ROOT / "statusline" / file_name, statusline / file_name)
    return source


def run_cli(target: Path, source: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--target",
            str(target),
            "--source",
            str(source),
            "--format",
            "json",
            *extra,
        ],
        check=False,
        capture_output=True,
        text=True,
    )


def sync(target: Path, source: Path, *extra: str) -> dict[str, object]:
    result = run_cli(target, source, *extra)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def manifest(target: Path) -> dict[str, object]:
    return json.loads((target / SYNC.MANIFEST_NAME).read_text(encoding="utf-8"))


def test_initial_sync_and_second_run_is_noop(tmp_path):
    source = make_source(tmp_path)
    target = tmp_path / ".cursor"
    target.mkdir()

    first = sync(target, source)
    assert first["changed"] is True
    assert first["skipped"] is False
    assert (target / "skills/setup/SKILL.md").is_file()
    assert {path.name for path in (target / "skills").iterdir()} == SYNC.EXPECTED_SKILLS
    assert (target / "templates/rules/agents-rules.md").is_file()
    assert all((target / "scripts" / name).is_file() for name in SYNC.UPDATER_FILES)
    assert (target / "statusline/install.js").is_file()
    assert manifest(target)["version"] == 1

    second = sync(target, source)
    assert second == {"actions": [], "changed": False, "skipped": True}


def test_missing_target_is_skipped_without_creation(tmp_path):
    source = make_source(tmp_path)
    target = tmp_path / ".cursor"

    result = sync(target, source)

    assert result["changed"] is False
    assert result["skipped"] is True
    assert "reason" in result
    assert not target.exists()


def test_check_reports_changes_without_writing(tmp_path):
    source = make_source(tmp_path)
    target = tmp_path / ".cursor"
    target.mkdir()

    result = sync(target, source, "--check")

    assert result["changed"] is True
    assert any(str(action).startswith("copy:") for action in result["actions"])
    assert list(target.iterdir()) == []


def test_skill_markdown_is_copied_without_transformation(tmp_path):
    source = make_source(tmp_path)
    target = tmp_path / ".cursor"
    target.mkdir()
    sync(target, source)

    for skill_name in SYNC.EXPECTED_SKILLS:
        assert (target / "skills" / skill_name / "SKILL.md").read_bytes() == (
            source / "skills" / skill_name / "SKILL.md"
        ).read_bytes()


def test_prunes_retired_skill_files_and_empty_directory(tmp_path):
    source = make_source(tmp_path)
    target = tmp_path / ".cursor"
    target.mkdir()
    sync(target, source)
    retired = target / "skills/retired/SKILL.md"
    retired.parent.mkdir()
    retired.write_bytes(b"retired\n")
    payload = manifest(target)
    payload["files"]["skills/retired/SKILL.md"] = sha256(retired.read_bytes()).hexdigest()
    (target / SYNC.MANIFEST_NAME).write_text(json.dumps(payload), encoding="utf-8")

    result = sync(target, source)

    assert "prune:skills/retired/SKILL.md" in result["actions"]
    assert not retired.parent.exists()


@pytest.mark.parametrize(
    ("relpath", "content"),
    [
        ("skills/setup/scripts/retired.py", b"old nested\n"),
        ("templates/rules/retired.md", b"old template\n"),
        ("scripts/retired.sh", b"old script\n"),
        ("statusline/retired.js", b"old statusline\n"),
    ],
)
def test_prunes_retired_files_from_all_managed_surfaces(tmp_path, relpath, content):
    source = make_source(tmp_path)
    target = tmp_path / ".cursor"
    target.mkdir()
    sync(target, source)
    retired = target / relpath
    retired.parent.mkdir(parents=True, exist_ok=True)
    retired.write_bytes(content)
    payload = manifest(target)
    payload["files"][relpath] = sha256(content).hexdigest()
    (target / SYNC.MANIFEST_NAME).write_text(json.dumps(payload), encoding="utf-8")

    result = sync(target, source)

    assert f"prune:{relpath}" in result["actions"]
    assert not retired.exists()


def test_modified_retired_file_is_preserved(tmp_path):
    source = make_source(tmp_path)
    target = tmp_path / ".cursor"
    target.mkdir()
    sync(target, source)
    retired = target / "skills/retired/SKILL.md"
    retired.parent.mkdir()
    retired.write_bytes(b"managed\n")
    payload = manifest(target)
    payload["files"]["skills/retired/SKILL.md"] = sha256(retired.read_bytes()).hexdigest()
    (target / SYNC.MANIFEST_NAME).write_text(json.dumps(payload), encoding="utf-8")
    retired.write_bytes(b"user modified\n")

    result = sync(target, source)

    assert "skip_prune_modified:skills/retired/SKILL.md" in result["actions"]
    assert retired.read_bytes() == b"user modified\n"


def test_user_file_in_retired_skill_directory_is_preserved(tmp_path):
    source = make_source(tmp_path)
    target = tmp_path / ".cursor"
    target.mkdir()
    sync(target, source)
    retired = target / "skills/retired/SKILL.md"
    retired.parent.mkdir()
    retired.write_bytes(b"managed\n")
    user_file = retired.parent / "notes.md"
    user_file.write_text("user\n", encoding="utf-8")
    payload = manifest(target)
    payload["files"]["skills/retired/SKILL.md"] = sha256(retired.read_bytes()).hexdigest()
    (target / SYNC.MANIFEST_NAME).write_text(json.dumps(payload), encoding="utf-8")

    sync(target, source)

    assert not retired.exists()
    assert user_file.is_file()
    assert retired.parent.is_dir()


def test_missing_manifest_adopts_exact_files_and_preserves_custom_skill(tmp_path):
    source = make_source(tmp_path)
    target = tmp_path / ".cursor"
    target.mkdir()
    sync(target, source)
    (target / SYNC.MANIFEST_NAME).unlink()
    custom = target / "skills/custom/SKILL.md"
    custom.parent.mkdir()
    custom.write_text("custom\n", encoding="utf-8")

    result = sync(target, source)

    assert not any(str(action).startswith("copy:") for action in result["actions"])
    assert result["actions"] == [f"write_manifest:{SYNC.MANIFEST_NAME}"]
    assert custom.read_text(encoding="utf-8") == "custom\n"


def test_missing_manifest_preserves_conflicting_file(tmp_path):
    source = make_source(tmp_path)
    target = tmp_path / ".cursor"
    target.mkdir()
    conflict = target / "skills/setup/SKILL.md"
    conflict.parent.mkdir(parents=True)
    conflict.write_bytes(b"user fork\n")

    result = sync(target, source)

    assert "skip_conflict:skills/setup/SKILL.md" in result["actions"]
    assert conflict.read_bytes() == b"user fork\n"
    assert "skills/setup/SKILL.md" not in manifest(target)["files"]

    second = sync(target, source)
    assert "skip_conflict:skills/setup/SKILL.md" in second["actions"]
    assert conflict.read_bytes() == b"user fork\n"
    assert "skills/setup/SKILL.md" not in manifest(target)["files"]


def test_irregular_target_is_preserved(tmp_path):
    if not hasattr(os, "symlink"):
        pytest.skip("symlink is unavailable")
    source = make_source(tmp_path)
    target = tmp_path / ".cursor"
    target.mkdir()
    external = tmp_path / "external.md"
    external.write_text("external\n", encoding="utf-8")
    destination = target / "skills/setup/SKILL.md"
    destination.parent.mkdir(parents=True)
    destination.symlink_to(external)

    result = sync(target, source)

    assert "skip_irregular:skills/setup/SKILL.md" in result["actions"]
    assert destination.is_symlink()
    assert external.read_text(encoding="utf-8") == "external\n"


def test_invalid_manifest_path_is_rejected_without_touching_external_file(tmp_path):
    source = make_source(tmp_path)
    target = tmp_path / ".cursor"
    target.mkdir()
    external = tmp_path / "external.txt"
    external.write_text("keep\n", encoding="utf-8")
    payload = {
        "version": 1,
        "files": {"../external.txt": sha256(external.read_bytes()).hexdigest()},
    }
    (target / SYNC.MANIFEST_NAME).write_text(json.dumps(payload), encoding="utf-8")

    result = sync(target, source)

    assert result["changed"] is False
    assert result["reason"] == "manifest is not a valid regular file"
    assert external.read_text(encoding="utf-8") == "keep\n"
    assert not (target / "skills").exists()


def test_manifest_path_aliases_are_rejected_before_prune(tmp_path):
    source = make_source(tmp_path)
    target = tmp_path / ".cursor"
    target.mkdir()
    retired = target / "skills/retired/old.txt"
    retired.parent.mkdir(parents=True)
    retired.write_text("keep\n", encoding="utf-8")
    digest = sha256(retired.read_bytes()).hexdigest()
    payload = {
        "version": 1,
        "files": {
            "skills/retired/old.txt": digest,
            "skills/retired/./old.txt": digest,
        },
    }
    original_manifest = json.dumps(payload)
    (target / SYNC.MANIFEST_NAME).write_text(original_manifest, encoding="utf-8")

    result = sync(target, source)

    assert result["changed"] is False
    assert result["reason"] == "manifest is not a valid regular file"
    assert retired.read_text(encoding="utf-8") == "keep\n"
    assert (target / SYNC.MANIFEST_NAME).read_text(encoding="utf-8") == original_manifest


@pytest.mark.parametrize("damage", ["skill", "asset"])
def test_source_validation_is_fail_closed(tmp_path, damage):
    source = make_source(tmp_path)
    target = tmp_path / ".cursor"
    target.mkdir()
    sentinel = target / "sentinel"
    sentinel.write_text("keep\n", encoding="utf-8")
    if damage == "skill":
        shutil.rmtree(source / "skills/backlog")
    else:
        (source / "statusline/install.js").unlink()

    result = run_cli(target, source)

    assert result.returncode != 0
    assert list(target.iterdir()) == [sentinel]


def test_source_and_target_overlap_is_rejected_without_writes(tmp_path):
    source = make_source(tmp_path)
    before = sorted(path.relative_to(source) for path in source.rglob("*"))

    result = run_cli(source, source)

    assert result.returncode != 0
    assert sorted(path.relative_to(source) for path in source.rglob("*")) == before


def test_expected_skills_matches_distribution_check():
    surface = load_module(SURFACE_CHECK, "check_skill_surface_contract")
    assert SYNC.EXPECTED_SKILLS == surface.EXPECTED_SKILLS


def test_synced_layout_resolves_setup_scripts_and_statusline(tmp_path):
    source = make_source(tmp_path)
    home = tmp_path / "home"
    target = home / ".cursor"
    target.mkdir(parents=True)
    sync(target, source)
    env = os.environ.copy()
    env["HOME"] = str(home)
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)

    rules = subprocess.run(
        [
            sys.executable,
            str(target / "skills/setup/scripts/sync_rules.py"),
            "--target",
            str(repo),
            "--template",
            str(target / "templates/rules/agents-rules.md"),
            "--dry-run",
            "--format",
            "json",
        ],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    assert rules.returncode == 0, rules.stderr

    updater = subprocess.run(
        [sys.executable, str(target / "skills/setup/scripts/sync_updater.py"), "--check", "--format", "json"],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    assert updater.returncode == 0, updater.stderr

    node = shutil.which("node")
    if node:
        statusline = subprocess.run(
            [node, str(target / "statusline/install.js"), "--check"],
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )
        assert statusline.returncode == 0, statusline.stderr + statusline.stdout


def make_fake_codex(bin_dir: Path) -> None:
    codex = bin_dir / "codex"
    codex.write_text('#!/bin/bash\nprintf \'{}\\n\'\n', encoding="utf-8")
    codex.chmod(0o755)


def run_update_wrapper(home: Path, source_root: Path, bin_dir: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["HOME"] = str(home)
    env["DEVKIT_SOURCE_ROOT"] = str(source_root)
    env["PATH"] = f"{bin_dir}{os.pathsep}{env['PATH']}"
    return subprocess.run(
        [shutil.which("bash") or "/bin/bash", str(PLUGIN_ROOT / "scripts/update-ccx.sh"), "--devkit-only"],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )


def test_posix_update_wrapper_syncs_cursor_and_second_run_is_noop(tmp_path):
    home = tmp_path / "home"
    (home / ".cursor").mkdir(parents=True)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    make_fake_codex(bin_dir)

    first = run_update_wrapper(home, ROOT, bin_dir)
    assert first.returncode == 0, first.stderr + first.stdout
    assert (home / ".cursor/skills/setup/SKILL.md").is_file()

    second = run_update_wrapper(home, ROOT, bin_dir)
    assert second.returncode == 0, second.stderr + second.stdout
    assert '"changed": false' in second.stdout
    assert '"actions": []' in second.stdout


def test_posix_update_wrapper_python_missing_contract_is_warn_and_skip(tmp_path):
    text = (PLUGIN_ROOT / "scripts/update-ccx.sh").read_text(encoding="utf-8")
    section_body = text.split("section_cursor_skills()", 1)[1].split("main()", 1)[0]
    python_command = "python" + "3"
    home = tmp_path / "home"
    (home / ".cursor").mkdir(parents=True)
    empty_bin = tmp_path / "empty-bin"
    empty_bin.mkdir()
    env = os.environ.copy()
    env["HOME"] = str(home)
    env["PATH"] = str(empty_bin)

    probe = subprocess.run(
        [
            shutil.which("bash") or "/bin/bash",
            "-c",
            "declare -a ERRORS=(); declare -a WARNINGS=(); "
            f"section_cursor_skills(){section_body}"
            "section_cursor_skills; printf 'warning_count=%s\\n' \"${#WARNINGS[@]}\"",
        ],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )

    assert probe.returncode == 0, probe.stderr + probe.stdout
    assert f"WARN {python_command} is not available; skipping Cursor skills sync" in probe.stdout
    assert "warning_count=1" in probe.stdout


def test_posix_update_wrapper_collects_sync_failure_and_exits_one(tmp_path):
    home = tmp_path / "home"
    (home / ".cursor").mkdir(parents=True)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    make_fake_codex(bin_dir)
    damaged_root = tmp_path / "damaged-root"
    shutil.copytree(PLUGIN_ROOT, damaged_root / "plugins/devkit")
    shutil.rmtree(damaged_root / "plugins/devkit/skills/backlog")

    result = run_update_wrapper(home, damaged_root, bin_dir)

    assert result.returncode == 1
    assert "Cursor skills: sync failed" in result.stdout
    assert "=== [Codex Plugin] ===" in result.stdout
