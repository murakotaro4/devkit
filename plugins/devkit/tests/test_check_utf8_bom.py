from __future__ import annotations

import subprocess
from pathlib import Path

import check_utf8_bom


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def test_repo_files_collects_target_extensions(monkeypatch, tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    for name in ["a.json", "b.md", "c.yaml", "d.yml", "ignore.txt"]:
        (repo / name).write_text("ok\n", encoding="utf-8")
    _git(repo, "add", ".")

    monkeypatch.setattr(check_utf8_bom, "REPO_ROOT", repo)

    assert set(check_utf8_bom.repo_files()) == {"a.json", "b.md", "c.yaml", "d.yml"}


def test_main_reports_bom_and_returns_one(monkeypatch, tmp_path, capsys):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    (repo / "bad.md").write_bytes(check_utf8_bom.UTF8_BOM + b"# bad\n")
    _git(repo, "add", ".")

    monkeypatch.setattr(check_utf8_bom, "REPO_ROOT", repo)

    assert check_utf8_bom.main() == 1
    captured = capsys.readouterr()
    assert "bad.md contains UTF-8 BOM" in captured.err
    assert "sed -i" in captured.err


def test_main_returns_zero_when_clean(monkeypatch, tmp_path, capsys):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    (repo / "clean.yml").write_text("ok\n", encoding="utf-8")
    _git(repo, "add", ".")

    monkeypatch.setattr(check_utf8_bom, "REPO_ROOT", repo)

    assert check_utf8_bom.main() == 0
    captured = capsys.readouterr()
    assert captured.err == ""


def test_main_detects_bom_staged_in_index_even_when_worktree_is_clean(monkeypatch, tmp_path, capsys):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    target = repo / "staged.md"
    target.write_bytes(check_utf8_bom.UTF8_BOM + b"# staged\n")
    _git(repo, "add", ".")
    target.write_text("# staged\n", encoding="utf-8")

    monkeypatch.setattr(check_utf8_bom, "REPO_ROOT", repo)

    assert check_utf8_bom.main() == 1
    captured = capsys.readouterr()
    assert "staged.md contains UTF-8 BOM" in captured.err


def test_main_skips_missing_worktree_file_when_index_is_clean(monkeypatch, tmp_path, capsys):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    target = repo / "deleted.md"
    target.write_text("# clean\n", encoding="utf-8")
    _git(repo, "add", ".")
    target.unlink()

    monkeypatch.setattr(check_utf8_bom, "REPO_ROOT", repo)

    assert check_utf8_bom.main() == 0
    captured = capsys.readouterr()
    assert captured.err == ""
