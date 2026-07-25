from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "plugins" / "devkit" / "scripts"


def bash_path() -> str:
    bash = shutil.which("bash")
    if not bash:
        raise AssertionError("bash が見つからない: PATH で bash を解決できません")
    return str(Path(bash).resolve())


def shell_function(name: str, next_name: str) -> str:
    shell = (SCRIPTS / "update-ccx.sh").read_text(encoding="utf-8")
    body = shell.split(name + "()", 1)[1].split("\n}\n\n" + next_name + "()", 1)[0]
    return name + "()" + body + "\n}\n"


def run_section_probe(
    tmp_path: Path, scenario: str
) -> subprocess.CompletedProcess[str]:
    section = shell_function("section_claude_mem", "windows_path_from_posix")
    probe = (
        section
        + r"""
WARNINGS=()
claude_mem_plugin_state() {
    local count=0
    [[ -f "$CLAUDE_MEM_CALLS" ]] && count="$(<"$CLAUDE_MEM_CALLS")"
    count=$((count + 1)); printf '%s\n' "$count" >"$CLAUDE_MEM_CALLS"
    printf 'state:%s\n' "$count" >>"$CLAUDE_MEM_EVENTS"
    case "$CLAUDE_MEM_SCENARIO:$count" in
        missing:*) printf '%s\n' missing ;;
        disabled:*) printf '%s\n' disabled ;;
        list-failure:1) return 1 ;;
        initial-state-failure:1|post-state-failure:2) return 2 ;;
        *) printf 'enabled\t13.12.4\tC:\\Plugin Files\\claude-mem\\13.12.4\n' ;;
    esac
}
claude_mem_resolve_install() {
    local count=0
    [[ -f "$CLAUDE_MEM_RESOLVE_CALLS" ]] && count="$(<"$CLAUDE_MEM_RESOLVE_CALLS")"
    count=$((count + 1)); printf '%s\n' "$count" >"$CLAUDE_MEM_RESOLVE_CALLS"
    printf 'resolve:%s\n' "$1" >>"$CLAUDE_MEM_EVENTS"
    [[ "$CLAUDE_MEM_SCENARIO" == missing-scripts ]] && return 1
    [[ "$CLAUDE_MEM_SCENARIO:$count" == post-missing-scripts:2 ]] && return 1
    printf '%s\n' '/plugin path'
}
run_claude_mem_worker() {
    printf 'worker:%s\n' "$2" >>"$CLAUDE_MEM_EVENTS"
    case "$CLAUDE_MEM_SCENARIO:$2" in
        stop-failure:stop) return 1 ;;
        port-busy:status) printf '%s\n' 'Worker is running on port 37777' ;;
        restart-failure:restart) return 1 ;;
        status-failure:status) return 1 ;;
        *:status) printf 'Worker is not running\r\n' ;;
    esac
}
claude() {
    printf 'claude:%s\n' "$*" >>"$CLAUDE_MEM_EVENTS"
    [[ "$CLAUDE_MEM_SCENARIO" == update-failure ]] && return 1
    return 0
}
command() {
    [[ "$CLAUDE_MEM_SCENARIO:$1:$2" == node-missing:-v:node ]] && return 1
    builtin command "$@"
}
node() { return 0; }
section_claude_mem
printf 'warnings:%s\n' "${#WARNINGS[@]}"
"""
    )
    return subprocess.run(
        [bash_path(), "-c", probe],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={
            **os.environ,
            "CLAUDE_MEM_SCENARIO": scenario,
            "CLAUDE_MEM_EVENTS": (tmp_path / "events").as_posix(),
            "CLAUDE_MEM_CALLS": (tmp_path / "calls").as_posix(),
            "CLAUDE_MEM_RESOLVE_CALLS": (tmp_path / "resolve-calls").as_posix(),
        },
    )


def test_contract_is_safe_and_runs_in_expected_modes():
    shell = (SCRIPTS / "update-ccx.sh").read_text(encoding="utf-8")
    section = shell.split("section_claude_mem()", 1)[1].split(
        "windows_path_from_posix()", 1
    )[0]
    ordered = (
        'run_claude_mem_worker "$resolved_install" stop',
        'run_claude_mem_worker "$resolved_install" status',
        "claude plugin update --scope user claude-mem@thedotmack",
        'plugin_state="$(claude_mem_plugin_state)"',
        'run_claude_mem_worker "$resolved_install" restart',
    )
    positions = [section.index(marker) for marker in ordered[:3]]
    positions.append(section.index(ordered[3], positions[-1]))
    positions.append(section.index(ordered[4]))

    assert positions == sorted(positions)
    assert '"$status_output" != "Worker is not running"' in section
    assert all(token not in section.lower() for token in ("taskkill", "kill -", "rm -"))

    main = shell.split("main()", 1)[1]
    devkit_block = main.split('if [[ "$DEVKIT_ONLY" != true ]]; then', 1)[1].split(
        "\n    fi", 1
    )[0]
    assert main.count("section_claude_mem") == 1
    assert main.index("section_update") < main.index("section_claude_mem")
    assert "section_claude_mem" in devkit_block
    assert "if [[ ${#ERRORS[@]} -eq 0 ]]; then" in main
    assert 'echo "OK All done"' in main
    assert 'echo "Errors occurred:"' in main
    assert "exit 1" in main
    assert (
        "section_claude_mem" not in main.split('if [[ "$CLI_ONLY" != true ]]; then')[-1]
    )


@pytest.mark.parametrize(
    ("payload", "expected", "returncode"),
    [
        ([], "missing\n", 0),
        (
            [
                {
                    "id": "claude-mem@thedotmack",
                    "scope": "project",
                    "enabled": True,
                    "version": "99.0.0",
                    "installPath": "/project",
                },
                {
                    "id": "claude-mem@thedotmack",
                    "scope": "user",
                    "enabled": False,
                    "version": "13.12.4",
                    "installPath": "/user",
                },
            ],
            "disabled\n",
            0,
        ),
        (
            [
                {
                    "id": "claude-mem@thedotmack",
                    "scope": scope,
                    "enabled": True,
                    "version": "99.0.0",
                    "installPath": "/duplicate",
                }
                for scope in ("project", "local")
            ],
            "missing\n",
            0,
        ),
        ({"unexpected": "object"}, "", 2),
    ],
)
def test_json_reader_handles_missing_disabled_and_malformed(
    payload, expected, returncode
):
    reader = shell_function("claude_mem_plugin_state", "claude_mem_resolve_install")
    probe = reader + "\nclaude() { printf '%s\n' \"$CLAUDE_MEM_JSON\"; }\n"
    probe += "claude_mem_plugin_state\n"
    result = subprocess.run(
        [bash_path(), "-c", probe],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, "CLAUDE_MEM_JSON": json.dumps(payload)},
    )
    assert result.returncode == returncode
    assert result.stdout == expected


def test_json_reader_preserves_windows_install_path_with_spaces():
    reader = shell_function("claude_mem_plugin_state", "claude_mem_resolve_install")
    payload = [
        {
            "id": "claude-mem@thedotmack",
            "scope": "project",
            "enabled": True,
            "version": "99.0.0",
            "installPath": "/duplicate",
        },
        {
            "id": "claude-mem@thedotmack",
            "scope": "user",
            "enabled": True,
            "version": "13.12.4",
            "installPath": r"C:\Plugin Files\claude-mem\13.12.4",
        },
    ]
    probe = reader + "\nclaude() { printf '%s\n' \"$CLAUDE_MEM_JSON\"; }\n"
    probe += "claude_mem_plugin_state\n"
    result = subprocess.run(
        [bash_path(), "-c", probe],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, "CLAUDE_MEM_JSON": json.dumps(payload)},
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "enabled\t13.12.4\tC:\\Plugin Files\\claude-mem\\13.12.4\n"


def test_resolver_uses_real_path_conversion_for_scripts_with_spaces(tmp_path):
    plugin_root = tmp_path / "Plugin Files" / "claude-mem" / "13.12.4"
    scripts = plugin_root / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "bun-runner.js").write_text("", encoding="utf-8")
    (scripts / "worker-service.cjs").write_text("", encoding="utf-8")

    converter = shell_function("windows_path_to_posix", "source_root_path_for_shell")
    resolver = shell_function("claude_mem_resolve_install", "run_claude_mem_worker")
    probe = converter + resolver
    probe += '\nclaude_mem_resolve_install "$CLAUDE_MEM_INSTALL"\n'
    result = subprocess.run(
        [bash_path(), "-c", probe],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, "CLAUDE_MEM_INSTALL": str(plugin_root)},
    )

    assert result.returncode == 0, result.stderr
    assert (
        result.stdout.strip()
        .replace("\\", "/")
        .endswith("/Plugin Files/claude-mem/13.12.4")
    )


@pytest.mark.parametrize(
    ("scenario", "expected", "warnings"),
    [
        (
            "success",
            [
                "state:1",
                "resolve:C:\\Plugin Files\\claude-mem\\13.12.4",
                "worker:stop",
                "worker:status",
                "claude:plugin update --scope user claude-mem@thedotmack",
                "state:2",
                "resolve:C:\\Plugin Files\\claude-mem\\13.12.4",
                "worker:restart",
            ],
            0,
        ),
        ("missing", ["state:1"], 0),
        ("disabled", ["state:1"], 0),
        ("node-missing", [], 1),
        ("list-failure", ["state:1"], 1),
        ("initial-state-failure", ["state:1"], 1),
        (
            "missing-scripts",
            ["state:1", "resolve:C:\\Plugin Files\\claude-mem\\13.12.4"],
            1,
        ),
        (
            "stop-failure",
            ["state:1", "resolve:C:\\Plugin Files\\claude-mem\\13.12.4", "worker:stop"],
            1,
        ),
        (
            "port-busy",
            [
                "state:1",
                "resolve:C:\\Plugin Files\\claude-mem\\13.12.4",
                "worker:stop",
                "worker:status",
            ],
            1,
        ),
        (
            "status-failure",
            [
                "state:1",
                "resolve:C:\\Plugin Files\\claude-mem\\13.12.4",
                "worker:stop",
                "worker:status",
            ],
            1,
        ),
        (
            "update-failure",
            [
                "state:1",
                "resolve:C:\\Plugin Files\\claude-mem\\13.12.4",
                "worker:stop",
                "worker:status",
                "claude:plugin update --scope user claude-mem@thedotmack",
                "state:2",
                "resolve:C:\\Plugin Files\\claude-mem\\13.12.4",
                "worker:restart",
            ],
            1,
        ),
        (
            "post-state-failure",
            [
                "state:1",
                "resolve:C:\\Plugin Files\\claude-mem\\13.12.4",
                "worker:stop",
                "worker:status",
                "claude:plugin update --scope user claude-mem@thedotmack",
                "state:2",
            ],
            1,
        ),
        (
            "post-missing-scripts",
            [
                "state:1",
                "resolve:C:\\Plugin Files\\claude-mem\\13.12.4",
                "worker:stop",
                "worker:status",
                "claude:plugin update --scope user claude-mem@thedotmack",
                "state:2",
                "resolve:C:\\Plugin Files\\claude-mem\\13.12.4",
            ],
            1,
        ),
        (
            "restart-failure",
            [
                "state:1",
                "resolve:C:\\Plugin Files\\claude-mem\\13.12.4",
                "worker:stop",
                "worker:status",
                "claude:plugin update --scope user claude-mem@thedotmack",
                "state:2",
                "resolve:C:\\Plugin Files\\claude-mem\\13.12.4",
                "worker:restart",
            ],
            1,
        ),
    ],
)
def test_maintenance_scenarios(tmp_path, scenario, expected, warnings):
    result = run_section_probe(tmp_path, scenario)
    assert result.returncode == 0, result.stderr + result.stdout
    event_path = tmp_path / "events"
    actual = (
        event_path.read_text(encoding="utf-8").splitlines()
        if event_path.exists()
        else []
    )
    assert actual == expected
    assert f"warnings:{warnings}" in result.stdout


def test_external_contract_is_documented():
    phrase = "bun-runner.js + worker-service.cjs + worker restart"
    assert phrase in (ROOT / "README.md").read_text(encoding="utf-8")
    assert phrase in (SCRIPTS / "README.md").read_text(encoding="utf-8")
