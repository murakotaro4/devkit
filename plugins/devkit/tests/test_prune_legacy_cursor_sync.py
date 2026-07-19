from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from hashlib import sha256
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
PLUGIN_ROOT = ROOT / "plugins/devkit"
SCRIPT = PLUGIN_ROOT / "skills/setup/scripts/prune_legacy_cursor_sync.py"
STUB = PLUGIN_ROOT / "skills/setup/scripts/sync_cursor_skills.py"
MANIFEST_NAME = ".devkit-sync-manifest.json"


def _probe_symlink_support() -> bool:
    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            probe_dir = Path(tmp_dir)
            target = probe_dir / "target"
            target.mkdir()
            (probe_dir / "link").symlink_to(target, target_is_directory=True)
    except (OSError, NotImplementedError):
        return False
    return True


def write_manifest(target: Path, files: dict[str, str]) -> Path:
    path = target / MANIFEST_NAME
    path.write_text(json.dumps({"version": 1, "files": files}), encoding="utf-8")
    return path


def add_managed(target: Path, relpath: str, content: bytes = b"managed\n") -> Path:
    path = target / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def run_cli(target: Path, *extra: str, script: Path = SCRIPT) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(script), "--target", str(target), "--format", "json", *extra],
        check=False,
        capture_output=True,
        text=True,
    )


def run_json(target: Path, *extra: str, script: Path = SCRIPT) -> dict[str, object]:
    result = run_cli(target, *extra, script=script)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_prunes_all_matching_files_empty_dirs_and_manifest(tmp_path):
    target = tmp_path / ".cursor"
    target.mkdir()
    files = {
        relpath: sha256(add_managed(target, relpath, content).read_bytes()).hexdigest()
        for relpath, content in {
            "skills/setup/SKILL.md": b"skill\n",
            "templates/rules/rule.md": b"rule\n",
            "scripts/update.sh": b"script\n",
            "statusline/statusline.js": b"statusline\n",
        }.items()
    }
    write_manifest(target, files)

    result = run_json(target)

    assert result["changed"] is True
    assert result["skipped"] is False
    assert sorted(action for action in result["actions"] if action.startswith("prune:")) == [
        f"prune:{relpath}" for relpath in sorted(files)
    ]
    assert not (target / MANIFEST_NAME).exists()
    assert list(target.iterdir()) == []


def test_second_run_without_manifest_is_noop(tmp_path):
    target = tmp_path / ".cursor"
    target.mkdir()
    result = run_json(target)
    assert result == {
        "actions": [],
        "changed": False,
        "reason": "legacy Cursor sync manifest does not exist",
        "skipped": True,
    }


def test_missing_target_is_noop_without_creation(tmp_path):
    target = tmp_path / ".cursor"
    result = run_json(target)
    assert result["changed"] is False
    assert result["skipped"] is True
    assert not target.exists()


def test_modified_file_is_preserved_and_manifest_is_reduced(tmp_path):
    target = tmp_path / ".cursor"
    target.mkdir()
    removed = add_managed(target, "skills/setup/SKILL.md")
    modified = add_managed(target, "scripts/update.sh")
    files = {
        "skills/setup/SKILL.md": sha256(removed.read_bytes()).hexdigest(),
        "scripts/update.sh": sha256(modified.read_bytes()).hexdigest(),
    }
    write_manifest(target, files)
    modified.write_bytes(b"user change\n")

    result = run_json(target)

    assert "prune:skills/setup/SKILL.md" in result["actions"]
    assert "skip_prune_modified:scripts/update.sh" in result["actions"]
    assert not removed.exists()
    assert modified.read_bytes() == b"user change\n"
    payload = json.loads((target / MANIFEST_NAME).read_text(encoding="utf-8"))
    assert payload["files"] == {"scripts/update.sh": files["scripts/update.sh"]}


def test_unlisted_user_assets_are_untouched(tmp_path):
    target = tmp_path / ".cursor"
    target.mkdir()
    managed = add_managed(target, "skills/setup/SKILL.md")
    user_file = add_managed(target, "skills/custom/notes.md", b"user\n")
    write_manifest(target, {"skills/setup/SKILL.md": sha256(managed.read_bytes()).hexdigest()})

    run_json(target)

    assert user_file.read_bytes() == b"user\n"
    assert user_file.parent.is_dir()


def test_symlink_entry_is_preserved_as_irregular(tmp_path):
    if not _probe_symlink_support():
        pytest.skip("symlink unavailable")
    target = tmp_path / ".cursor"
    target.mkdir()
    external = tmp_path / "external.txt"
    external.write_bytes(b"external\n")
    destination = target / "skills/setup/SKILL.md"
    destination.parent.mkdir(parents=True)
    destination.symlink_to(external)
    digest = sha256(external.read_bytes()).hexdigest()
    write_manifest(target, {"skills/setup/SKILL.md": digest})

    result = run_json(target)

    assert result["changed"] is False
    assert result["actions"] == ["skip_irregular:skills/setup/SKILL.md"]
    assert destination.is_symlink()
    assert external.read_bytes() == b"external\n"


def test_intermediate_symlink_is_preserved_as_irregular(tmp_path):
    if not _probe_symlink_support():
        pytest.skip("symlink unavailable")
    target = tmp_path / ".cursor"
    target.mkdir()
    external = tmp_path / "external"
    external.mkdir()
    external_file = external / "SKILL.md"
    external_file.write_bytes(b"external\n")
    (target / "skills").mkdir()
    (target / "skills/setup").symlink_to(external, target_is_directory=True)
    relpath = "skills/setup/SKILL.md"
    write_manifest(target, {relpath: sha256(external_file.read_bytes()).hexdigest()})

    result = run_json(target)

    assert result["actions"] == [f"skip_irregular:{relpath}"]
    assert external_file.read_bytes() == b"external\n"


def test_manifest_symlink_is_rejected_without_touching_external_file(tmp_path):
    if not _probe_symlink_support():
        pytest.skip("symlink unavailable")
    target = tmp_path / ".cursor"
    target.mkdir()
    external = tmp_path / "manifest.json"
    original = '{"version": 1, "files": {}}\n'
    external.write_text(original, encoding="utf-8")
    (target / MANIFEST_NAME).symlink_to(external)

    result = run_cli(target)

    assert result.returncode != 0
    assert "invalid Cursor sync manifest" in result.stderr
    assert external.read_text(encoding="utf-8") == original


def test_manifest_directory_is_rejected_without_removal(tmp_path):
    target = tmp_path / ".cursor"
    target.mkdir()
    manifest = target / MANIFEST_NAME
    manifest.mkdir()

    result = run_cli(target)

    assert result.returncode != 0
    assert "invalid Cursor sync manifest" in result.stderr
    assert manifest.is_dir()


def test_target_root_symlink_is_noop(tmp_path):
    if not _probe_symlink_support():
        pytest.skip("symlink unavailable")
    external = tmp_path / "external"
    external.mkdir()
    manifest = external / MANIFEST_NAME
    manifest.write_text('{"version": 1, "files": {}}', encoding="utf-8")
    target = tmp_path / ".cursor"
    target.symlink_to(external, target_is_directory=True)

    result = run_json(target)

    assert result["changed"] is False
    assert result["reason"] == "cursor target is not a regular directory"
    assert manifest.is_file()


def test_target_root_regular_file_is_noop(tmp_path):
    target = tmp_path / ".cursor"
    target.write_bytes(b"user file\n")

    result = run_json(target)

    assert result["changed"] is False
    assert result["reason"] == "cursor target is not a regular directory"
    assert target.read_bytes() == b"user file\n"


def test_intermediate_regular_file_is_preserved_as_irregular(tmp_path):
    target = tmp_path / ".cursor"
    target.mkdir()
    intermediate = target / "skills/setup"
    intermediate.parent.mkdir()
    intermediate.write_bytes(b"user file\n")
    relpath = "skills/setup/SKILL.md"
    write_manifest(target, {relpath: sha256(b"managed\n").hexdigest()})

    result = run_json(target)

    assert result["actions"] == [f"skip_irregular:{relpath}"]
    assert intermediate.read_bytes() == b"user file\n"


@pytest.mark.parametrize(
    "relpath",
    [
        "../external.txt",
        "/tmp/external.txt",
        r"skills\\setup\\SKILL.md",
        "skills/setup/./SKILL.md",
        "outside/file.txt",
        "skills",
    ],
)
def test_manifest_path_aliases_and_unmanaged_roots_are_rejected(tmp_path, relpath):
    target = tmp_path / ".cursor"
    target.mkdir()
    external = tmp_path / "external.txt"
    external.write_bytes(b"keep\n")
    original = json.dumps({"version": 1, "files": {relpath: sha256(external.read_bytes()).hexdigest()}})
    (target / MANIFEST_NAME).write_text(original, encoding="utf-8")

    result = run_cli(target)

    assert result.returncode != 0
    assert "invalid Cursor sync manifest" in result.stderr
    assert external.read_bytes() == b"keep\n"
    assert (target / MANIFEST_NAME).read_text(encoding="utf-8") == original


@pytest.mark.parametrize("manifest_text", ["{not-json", json.dumps({"version": 999, "files": {}})])
def test_invalid_manifest_is_nonzero(tmp_path, manifest_text):
    target = tmp_path / ".cursor"
    target.mkdir()
    (target / MANIFEST_NAME).write_text(manifest_text, encoding="utf-8")
    result = run_cli(target)
    assert result.returncode != 0
    assert "delete the manifest" in result.stderr


def test_check_reports_without_writing(tmp_path):
    target = tmp_path / ".cursor"
    target.mkdir()
    managed = add_managed(target, "skills/setup/SKILL.md")
    manifest = write_manifest(target, {"skills/setup/SKILL.md": sha256(managed.read_bytes()).hexdigest()})

    result = run_json(target, "--check")

    assert result["changed"] is True
    assert "prune:skills/setup/SKILL.md" in result["actions"]
    assert managed.is_file()
    assert manifest.is_file()


def test_v101_compatibility_stub_accepts_old_cli_and_prunes(tmp_path):
    target = tmp_path / ".cursor"
    target.mkdir()
    managed = add_managed(target, "skills/setup/SKILL.md")
    write_manifest(target, {"skills/setup/SKILL.md": sha256(managed.read_bytes()).hexdigest()})

    result = run_cli(target, "--source", str(tmp_path / "ignored-plugin"), script=STUB)

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["changed"] is True
    assert not managed.exists()
    assert not (target / MANIFEST_NAME).exists()


def make_fake_codex(bin_dir: Path) -> None:
    codex = bin_dir / "codex"
    codex.write_text("#!/bin/bash\nprintf '{}\\n'\n", encoding="utf-8")
    codex.chmod(0o755)


def make_fake_python3(bin_dir: Path) -> None:
    python3 = bin_dir / "python3"
    python3.write_text(
        f'#!/bin/bash\nexec "{Path(sys.executable).as_posix()}" "$@"\n',
        encoding="utf-8",
    )
    python3.chmod(0o755)


def make_fake_claude(bin_dir: Path) -> None:
    claude = bin_dir / "claude"
    claude.write_text(
        """#!/bin/bash
if [ "$1" = "plugin" ] && [ "$2" = "marketplace" ] && [ "$3" = "list" ] && [ "$4" = "--json" ]; then
  printf '[{"name":"murakotaro4","source":"github","repo":"murakotaro4/devkit"}]\\n'
  exit 0
fi
if [ "$1" = "plugin" ] && [ "$2" = "list" ] && [ "$3" = "--json" ]; then
  printf '[{"id":"devkit@murakotaro4","scope":"user"}]\\n'
  exit 0
fi
exit 0
""",
        encoding="utf-8",
    )
    claude.chmod(0o755)


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


def test_posix_wrapper_prunes_manifest_assets(tmp_path):
    home = tmp_path / "home"
    target = home / ".cursor"
    target.mkdir(parents=True)
    managed = add_managed(target, "skills/setup/SKILL.md")
    write_manifest(target, {"skills/setup/SKILL.md": sha256(managed.read_bytes()).hexdigest()})
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    make_fake_codex(bin_dir)
    make_fake_python3(bin_dir)
    make_fake_claude(bin_dir)

    result = run_update_wrapper(home, ROOT, bin_dir)

    assert result.returncode == 0, result.stderr + result.stdout
    assert not managed.exists()
    assert not (target / MANIFEST_NAME).exists()


def _section_body() -> str:
    text = (PLUGIN_ROOT / "scripts/update-ccx.sh").read_text(encoding="utf-8")
    return text.split("section_prune_cursor_sync()", 1)[1].split("main()", 1)[0]


def test_posix_wrapper_manifest_missing_skips_before_python_gate(tmp_path):
    home = tmp_path / "home"
    (home / ".cursor").mkdir(parents=True)
    empty_bin = tmp_path / "empty-bin"
    empty_bin.mkdir()
    env = os.environ.copy()
    env["HOME"] = str(home)
    env["PATH"] = str(empty_bin)
    probe = subprocess.run(
        [shutil.which("bash") or "/bin/bash", "-c", f"declare -a ERRORS=(); declare -a WARNINGS=(); section_prune_cursor_sync(){{{_section_body()}}}; section_prune_cursor_sync; printf 'warnings=%s\\n' \"${{#WARNINGS[@]}}\""],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    assert probe.returncode == 0
    assert "SKIP legacy Cursor sync manifest is not available" in probe.stdout
    assert "warnings=0" in probe.stdout


@pytest.mark.parametrize("python_body", [None, "#!/bin/bash\nexit 1\n"])
def test_posix_wrapper_python_unavailable_or_old_warns_and_skips(tmp_path, python_body):
    home = tmp_path / "home"
    target = home / ".cursor"
    target.mkdir(parents=True)
    write_manifest(target, {})
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    if python_body is not None:
        python = fake_bin / "python3"
        python.write_text(python_body, encoding="utf-8")
        python.chmod(0o755)
    env = os.environ.copy()
    env["HOME"] = str(home)
    env["PATH"] = str(fake_bin)
    probe = subprocess.run(
        [shutil.which("bash") or "/bin/bash", "-c", f"declare -a ERRORS=(); declare -a WARNINGS=(); section_prune_cursor_sync(){{{_section_body()}}}; section_prune_cursor_sync; printf 'warnings=%s\\n' \"${{#WARNINGS[@]}}\""],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    assert probe.returncode == 0
    assert "skipping legacy Cursor sync prune" in probe.stdout
    assert "warnings=1" in probe.stdout


def test_posix_wrapper_collects_prune_failure_and_continues(tmp_path):
    home = tmp_path / "home"
    target = home / ".cursor"
    target.mkdir(parents=True)
    (target / MANIFEST_NAME).write_text("{invalid", encoding="utf-8")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    make_fake_codex(bin_dir)
    make_fake_python3(bin_dir)
    make_fake_claude(bin_dir)

    result = run_update_wrapper(home, ROOT, bin_dir)

    assert result.returncode == 1
    assert "Cursor legacy sync: prune failed" in result.stdout
    assert "=== [Codex Plugin] ===" in result.stdout
