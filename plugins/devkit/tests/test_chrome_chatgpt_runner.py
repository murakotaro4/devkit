from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import chrome_chatgpt_runner as runner


def test_choose_backend_uses_playwright_when_agent_browser_missing(monkeypatch):
    monkeypatch.setattr(runner.shutil, "which", lambda cmd: None if cmd == "agent-browser" else "node")
    monkeypatch.setattr(runner, "probe_playwright", lambda port: {"ok": True, "output": "{}"})

    backend = runner.choose_backend(9222)

    assert backend.name == "playwright"


def test_choose_backend_falls_back_when_agent_browser_probe_fails(monkeypatch):
    monkeypatch.setattr(runner.shutil, "which", lambda cmd: "tool")
    monkeypatch.setattr(runner, "agent_browser_args", lambda port: ["agent-browser", "--cdp", str(port)])
    monkeypatch.setattr(runner, "probe_playwright", lambda port: {"ok": True, "output": "{}"})

    def fake_run_command(args, timeout=30):
        return runner.subprocess.CompletedProcess(args=args, returncode=2, stdout="", stderr="agent-browser failed")

    monkeypatch.setattr(runner, "run_command", fake_run_command)

    backend = runner.choose_backend(9222)

    assert backend.name == "playwright"


def test_agent_browser_args_missing_binary_raises_runtime_error(monkeypatch):
    monkeypatch.setattr(runner.shutil, "which", lambda cmd: None)

    try:
        runner.agent_browser_args(9222)
    except RuntimeError as exc:
        assert "agent-browser is not on PATH" in str(exc)
    else:
        raise AssertionError("expected RuntimeError")


def test_run_command_timeout_returns_completed_process(monkeypatch):
    def fake_run(*args, **kwargs):
        raise runner.subprocess.TimeoutExpired(cmd=args[0], timeout=kwargs.get("timeout", 30))

    monkeypatch.setattr(runner.subprocess, "run", fake_run)

    result = runner.run_command(["agent-browser"], timeout=1)

    assert result.returncode == 124
    assert "timed out" in result.stderr


def test_json_flag_works_before_or_after_diagnose():
    parser = runner.build_parser()

    assert parser.parse_args(["--json", "diagnose"]).json is True
    assert parser.parse_args(["diagnose", "--json"]).json is True


def test_linux_process_checks_do_not_use_broad_f_match(monkeypatch):
    calls: list[list[str]] = []

    monkeypatch.setattr(runner.platform, "system", lambda: "Linux")

    def fake_run(args, **kwargs):
        calls.append(list(args))
        return runner.subprocess.CompletedProcess(args=args, returncode=1, stdout="", stderr="")

    monkeypatch.setattr(runner.subprocess, "run", fake_run)

    assert runner.chrome_running() is False
    runner.stop_chrome()

    assert calls
    assert all("-f" not in call for call in calls)
    assert all(call[1] == "-x" for call in calls if call[0] in {"pgrep", "pkill"})


def test_wait_gpt_pro_requires_change_from_saved_baseline(monkeypatch, capsys):
    states = [
        {"count": 1, "text": "old answer", "busy": False},
        {"count": 2, "text": "new answer", "busy": False},
        {"count": 2, "text": "new answer", "busy": False},
        {"count": 2, "text": "new answer", "busy": False},
    ]

    monkeypatch.setattr(runner, "ensure_cdp", lambda args: None)
    monkeypatch.setattr(runner, "choose_backend", lambda port: runner.BrowserBackend(name="playwright"))
    monkeypatch.setattr(runner, "load_wait_baseline", lambda port: {"count": 1, "text": "old answer", "busy": False})
    monkeypatch.setattr(runner.time, "sleep", lambda seconds: None)

    def fake_eval(args, backend, expression):
        return json.dumps(states.pop(0), ensure_ascii=False)

    monkeypatch.setattr(runner, "backend_eval", fake_eval)

    result = runner.wait_gpt_pro(SimpleNamespace(port=9222, timeout_minutes=1, interval=0))

    assert result == 0
    assert "new answer" in capsys.readouterr().out


def test_deep_research_not_selected_does_not_submit_prompt(monkeypatch):
    args = SimpleNamespace(port=9222, prompt="research prompt")
    backend = runner.BrowserBackend(name="playwright")
    monkeypatch.setattr(runner, "open_chatgpt", lambda args: backend)
    monkeypatch.setattr(runner, "backend_eval", lambda args, backend, expression: "deep research control not found")
    monkeypatch.setattr(
        runner,
        "insert_prompt",
        lambda args, backend, prompt: (_ for _ in ()).throw(AssertionError("prompt should not be submitted")),
    )

    assert runner.run_deep_research(args) == 2


def test_read_cdp_response_skips_interleaved_events():
    class FakeWs:
        def __init__(self):
            self.messages = iter(
                [
                    json.dumps({"method": "Runtime.executionContextCreated"}),
                    json.dumps({"id": 9, "result": {"ignored": True}}),
                    json.dumps({"id": 10, "result": {"result": {"value": "ok"}}}),
                ]
            )

        async def recv(self):
            return next(self.messages)

    response = asyncio.run(runner.read_cdp_response(FakeWs(), 10, timeout=1))

    assert response["result"]["result"]["value"] == "ok"


def test_read_cdp_response_timeout_returns_empty():
    class SlowWs:
        async def recv(self):
            await asyncio.sleep(1)
            return json.dumps({"id": 10})

    response = asyncio.run(runner.read_cdp_response(SlowWs(), 10, timeout=0.01))

    assert response == {}
