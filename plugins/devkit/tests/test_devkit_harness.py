from __future__ import annotations

from pathlib import Path
import subprocess

import devkit_harness


def test_full_checks_are_fast_checks_plus_version_gate():
    assert devkit_harness.CHECKS_FULL[:-1] == devkit_harness.CHECKS_FAST
    assert devkit_harness.CHECKS_FULL[-1][-1].endswith("check_plugin_version_bump.py")


def test_fast_checks_order():
    names = [Path(command[1]).name if len(command) > 1 else "" for command in devkit_harness.CHECKS_FAST]

    assert names[:3] == [
        "check_utf8_bom.py",
        "check_skill_surface.py",
        "check_legacy_migration.py",
    ]
    assert devkit_harness.CHECKS_FAST[0] == [
        devkit_harness.sys.executable,
        devkit_harness.script("check_utf8_bom.py"),
    ]


def test_run_steps_stops_at_first_failure(monkeypatch):
    calls: list[list[str]] = []

    def fake_run(cmd, cwd):  # noqa: ANN001
        calls.append(cmd)
        code = 7 if len(calls) == 2 else 0
        return subprocess.CompletedProcess(cmd, code)

    monkeypatch.setattr(devkit_harness.subprocess, "run", fake_run)

    assert devkit_harness.run_steps([["first"], ["second"], ["third"]]) == 7
    assert calls == [["first"], ["second"]]


def test_secret_snapshot_keeps_index_and_worktree_versions_for_unstaged_edits(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)

    tracked = repo / "tracked.txt"
    tracked.write_text("index secret candidate\n", encoding="utf-8")
    subprocess.run(["git", "add", "tracked.txt"], cwd=repo, check=True)
    tracked.write_text("worktree secret candidate\n", encoding="utf-8")

    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    monkeypatch.setattr(devkit_harness, "REPO_ROOT", Path(repo))

    assert devkit_harness.materialize_secret_scan_snapshot(snapshot) == [
        ".devkit-worktree/tracked.txt",
        "tracked.txt",
    ]
    assert (snapshot / "tracked.txt").read_text(encoding="utf-8") == "index secret candidate\n"
    assert (
        snapshot / ".devkit-worktree" / "tracked.txt"
    ).read_text(encoding="utf-8") == "worktree secret candidate\n"


def test_secret_snapshot_keeps_staged_version_when_worktree_file_is_deleted(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)

    tracked = repo / "tracked.txt"
    tracked.write_text("staged secret candidate\n", encoding="utf-8")
    subprocess.run(["git", "add", "tracked.txt"], cwd=repo, check=True)
    tracked.unlink()

    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    monkeypatch.setattr(devkit_harness, "REPO_ROOT", Path(repo))

    assert devkit_harness.materialize_secret_scan_snapshot(snapshot) == ["tracked.txt"]
    assert (snapshot / "tracked.txt").read_text(encoding="utf-8") == "staged secret candidate\n"


def test_secret_snapshot_omits_staged_deletions(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)

    tracked = repo / "tracked.txt"
    tracked.write_text("removed secret candidate\n", encoding="utf-8")
    subprocess.run(["git", "add", "tracked.txt"], cwd=repo, check=True)
    subprocess.run(["git", "rm", "-f", "tracked.txt"], cwd=repo, check=True, capture_output=True)

    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    monkeypatch.setattr(devkit_harness, "REPO_ROOT", Path(repo))

    assert devkit_harness.materialize_secret_scan_snapshot(snapshot) == []


def test_secret_snapshot_path_normalization_maps_worktree_alias_to_repo_path():
    assert devkit_harness.repo_path_from_secret_snapshot_path(".devkit-worktree/a/b.txt") == "a/b.txt"
