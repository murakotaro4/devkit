from __future__ import annotations

import subprocess
from pathlib import Path

import check_bash32_compat


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def _make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    return repo


def _add(repo: Path, rel: str, content: str) -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    _git(repo, "add", rel)


def test_scan_lines_detects_bash4_tokens():
    lines = [
        'mapfile -t lines <"$bodies"',
        "readarray rows < file",
        "declare -A table",
        "local -n ref=name",
        "declare -Ar table",
        "local -r -n ref=name",
        "typeset -rn ref=name",
        "pattern) run ;;&",
        'echo "${name^^}"',
        'echo "${name,,}"',
        'echo "${arr[0]^^}"',
        'normalized="/${BASH_REMATCH[1],,}/${BASH_REMATCH[2]}"',
        'echo "${name@Q}"',
    ]
    findings = check_bash32_compat.scan_lines(lines)
    assert [line_no for line_no, _ in findings] == list(range(1, len(lines) + 1))


def test_scan_lines_ignores_safe_constructs():
    lines = [
        'while IFS= read -r line; do body="$line"; done <"$bodies"',
        "declare -a arr",
        "declare -ar arr",
        "local -r name=value",
        "local exit_code=$?",
        'case "$x" in a) run ;; esac',
        'echo "${name:-default}"',
        'echo "${name%/}"',
        'echo "${arr[0]:-fallback}"',
        "my-mapfile-tool --help",
    ]
    assert check_bash32_compat.scan_lines(lines) == []


def test_scan_lines_skips_waiver_and_comment_lines():
    lines = [
        "mapfile -t lines < file  # bash32-allow",
        "# mapfile is documented here",
        "    # readarray in an indented comment",
    ]
    assert check_bash32_compat.scan_lines(lines) == []


def test_main_reports_findings_in_sh_and_test_py(monkeypatch, tmp_path, capsys):
    repo = _make_repo(tmp_path)
    _add(repo, "tool.sh", "#!/bin/bash\nmapfile -t rows < input\n")
    _add(
        repo,
        "plugins/devkit/tests/test_probe.py",
        "CURL = 'mapfile -t lines < bodies'\n",
    )
    _add(repo, "plugins/devkit/tests/helper.py", "VALUE = 'mapfile'\n")
    monkeypatch.setattr(check_bash32_compat, "REPO_ROOT", repo)

    assert check_bash32_compat.main() == 1
    err = capsys.readouterr().err
    assert "tool.sh:2" in err
    assert "plugins/devkit/tests/test_probe.py:1" in err
    assert "plugins/devkit/tests/helper.py:1" in err


def test_main_ignores_untargeted_and_self_files(monkeypatch, tmp_path, capsys):
    repo = _make_repo(tmp_path)
    _add(repo, "notes.md", "mapfile is a bash 4 builtin\n")
    _add(repo, "outside/tool.py", "CMD = 'mapfile -t x < y'\n")
    _add(
        repo,
        "plugins/devkit/scripts/check_bash32_compat.py",
        "TOKEN = 'mapfile'\n",
    )
    _add(
        repo,
        "plugins/devkit/tests/test_check_bash32_compat.py",
        "FIXTURE = 'mapfile -t x < y'\n",
    )
    _add(repo, "clean.sh", "#!/bin/bash\necho ok\n")
    monkeypatch.setattr(check_bash32_compat, "REPO_ROOT", repo)

    assert check_bash32_compat.main() == 0
    assert capsys.readouterr().err == ""
