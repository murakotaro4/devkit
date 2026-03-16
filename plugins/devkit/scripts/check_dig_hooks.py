#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path


ROOT = Path.cwd()
WORKFLOW_DIR = ROOT / "plugins/devkit/scripts/workflow"
HOOKS_JSON = ROOT / "plugins/devkit/.claude-plugin/hooks.json"


def run_hook(script: str, payload: dict[str, object], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python3", str(WORKFLOW_DIR / script)],
        input=json.dumps(payload, ensure_ascii=False),
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def load_state(home: str, session_id: str) -> dict[str, object]:
    path = Path(home) / ".claude" / f"devkit-workflow-{session_id}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def load_hooks_manifest() -> dict[str, object]:
    return json.loads(HOOKS_JSON.read_text(encoding="utf-8"))


def write_task(home: str, session_id: str, task_id: str, subject: str) -> None:
    task_dir = Path(home) / ".claude" / "tasks" / session_id
    task_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "id": task_id,
        "subject": subject,
        "description": "",
        "activeForm": "",
        "status": "pending",
        "blocks": [],
        "blockedBy": [],
        "metadata": {"phase": "implementation_completed"},
    }
    (task_dir / f"{task_id}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def touch_old_task(home: str, session_id: str, task_id: str, subject: str) -> None:
    write_task(home, session_id, task_id, subject)
    task_path = Path(home) / ".claude" / "tasks" / session_id / f"{task_id}.json"
    os.utime(task_path, (1, 1))


def main() -> int:
    hooks = load_hooks_manifest()
    hooks_root = hooks.get("hooks", {}) if isinstance(hooks, dict) else {}
    if not isinstance(hooks_root, dict):
        raise RuntimeError("hooks.json missing hooks object")

    expected = {
        "UserPromptSubmit": "user_prompt_submit.py",
        "Stop": "stop_dig_session.py",
        "PreToolUse": "pre_tool_gate.py",
        "PostToolUse": "post_task_tracker.py",
    }
    # Also verify AskUserQuestion PostToolUse binding
    post_hooks = hooks_root.get("PostToolUse", [])
    post_serialized = json.dumps(post_hooks, ensure_ascii=False) if isinstance(post_hooks, list) else ""
    if "post_ask_user.py" not in post_serialized:
        raise RuntimeError("hooks.json missing PostToolUse -> post_ask_user.py binding for AskUserQuestion")
    for event_name, script_name in expected.items():
        event_hooks = hooks_root.get(event_name)
        if not isinstance(event_hooks, list) or not event_hooks:
            raise RuntimeError(f"hooks.json missing event: {event_name}")
        serialized = json.dumps(event_hooks, ensure_ascii=False)
        if script_name not in serialized:
            raise RuntimeError(f"hooks.json missing script binding: {event_name} -> {script_name}")

    with tempfile.TemporaryDirectory(prefix="dig-hooks-") as home:
        env = os.environ.copy()
        env["HOME"] = home
        session_id = "dig-hook-test"

        user_prompt = run_hook(
            "user_prompt_submit.py",
            {"session_id": session_id, "prompt": "/dig implement sample"},
            env,
        )
        if user_prompt.returncode != 0:
            raise RuntimeError(f"user_prompt_submit failed: {user_prompt.stderr}")

        state = load_state(home, session_id)
        dig = state.get("dig", {})
        if not isinstance(dig, dict) or not dig.get("active"):
            raise RuntimeError("user_prompt_submit did not activate dig state")

        plan_review = run_hook(
            "post_task_tracker.py",
            {
                "session_id": session_id,
                "tool_name": "Bash",
                "tool_input": {"status": "completed", "command": "codex exec -m gpt-5.3-codex-spark /tmp/dig_plan_review_123.md"},
                "tool_response": "REVIEW_RESULT_MARKER=REVIEW_COUNTS\nREVIEW_COUNTS critical=0 high=0",
            },
            env,
        )
        if plan_review.returncode != 0:
            raise RuntimeError(f"post_task_tracker failed: {plan_review.stderr}")

        blocked = run_hook(
            "pre_tool_gate.py",
            {"session_id": session_id, "tool_name": "Edit", "tool_input": {"file_path": "src/app.ts"}},
            env,
        )
        blocked_payload = json.loads(blocked.stdout or "{}")
        decision = blocked_payload.get("hookSpecificOutput", {}).get("permissionDecision")
        if decision != "block":
            raise RuntimeError(f"pre_tool_gate should block before Phase 5 tasks: {blocked.stdout}")

        blocked_bash = run_hook(
            "pre_tool_gate.py",
            {
                "session_id": session_id,
                "tool_name": "Bash",
                "tool_input": {"command": "codex exec -m gpt-5.3-codex-spark 'review this' && touch should_not_run"},
            },
            env,
        )
        blocked_bash_payload = json.loads(blocked_bash.stdout or "{}")
        if blocked_bash_payload.get("hookSpecificOutput", {}).get("permissionDecision") != "block":
            raise RuntimeError(f"pre_tool_gate should block mutating Bash chained after codex exec: {blocked_bash.stdout}")

        write_task(home, session_id, "2", "[Task 1] sample task")

        allowed = run_hook(
            "pre_tool_gate.py",
            {"session_id": session_id, "tool_name": "Edit", "tool_input": {"file_path": "src/app.ts"}},
            env,
        )
        allowed_payload = json.loads(allowed.stdout or "{}")
        decision = allowed_payload.get("hookSpecificOutput", {}).get("permissionDecision")
        if decision != "pass":
            raise RuntimeError(f"pre_tool_gate should pass after Phase 5 tasks: {allowed.stdout}")

        stale_session_id = "dig-stale-task-test"
        touch_old_task(home, stale_session_id, "2", "[Task 1] stale task")
        stale_prompt = run_hook(
            "user_prompt_submit.py",
            {"session_id": stale_session_id, "prompt": "/dig implement fresh"},
            env,
        )
        if stale_prompt.returncode != 0:
            raise RuntimeError(f"user_prompt_submit for stale session failed: {stale_prompt.stderr}")
        stale_plan_review = run_hook(
            "post_task_tracker.py",
            {
                "session_id": stale_session_id,
                "tool_name": "Bash",
                "tool_input": {"status": "completed", "command": "codex exec -m gpt-5.3-codex-spark /tmp/dig_plan_review_456.md"},
                "tool_response": "REVIEW_RESULT_MARKER=REVIEW_COUNTS\nREVIEW_COUNTS critical=0 high=0",
            },
            env,
        )
        if stale_plan_review.returncode != 0:
            raise RuntimeError(f"post_task_tracker stale session failed: {stale_plan_review.stderr}")
        stale_blocked = run_hook(
            "pre_tool_gate.py",
            {"session_id": stale_session_id, "tool_name": "Edit", "tool_input": {"file_path": "src/app.ts"}},
            env,
        )
        stale_payload = json.loads(stale_blocked.stdout or "{}")
        if stale_payload.get("hookSpecificOutput", {}).get("permissionDecision") != "block":
            raise RuntimeError(f"stale tasks should not satisfy Phase 5 registration: {stale_blocked.stdout}")

        # --- Phase 2 gate tests ---
        phase2_session = "dig-phase2-gate-test"
        run_hook("user_prompt_submit.py", {"session_id": phase2_session, "prompt": "/dig phase2 test"}, env)

        # Write to plan file without requirements_confirmed → ask
        plan_write_blocked = run_hook(
            "pre_tool_gate.py",
            {
                "session_id": phase2_session,
                "tool_name": "Write",
                "tool_input": {"file_path": "/home/user/.claude/plans/test-plan.md", "content": "# Plan"},
            },
            env,
        )
        plan_write_payload = json.loads(plan_write_blocked.stdout or "{}")
        plan_write_decision = plan_write_payload.get("hookSpecificOutput", {}).get("permissionDecision")
        if plan_write_decision != "ask":
            raise RuntimeError(f"Phase 2 gate: plan Write without requirements_confirmed should ask, got: {plan_write_decision}")

        # Simulate AskUserQuestion completion → requirements_confirmed = True
        ask_user = run_hook(
            "post_ask_user.py",
            {"session_id": phase2_session, "tool_name": "AskUserQuestion", "tool_input": {}},
            env,
        )
        if ask_user.returncode != 0:
            raise RuntimeError(f"post_ask_user failed: {ask_user.stderr}")

        phase2_state = load_state(home, phase2_session)
        phase2_dig = phase2_state.get("dig", {})
        if not isinstance(phase2_dig, dict) or not phase2_dig.get("requirements_confirmed"):
            raise RuntimeError("post_ask_user did not set requirements_confirmed")

        # Write to plan file with requirements_confirmed → pass
        plan_write_allowed = run_hook(
            "pre_tool_gate.py",
            {
                "session_id": phase2_session,
                "tool_name": "Write",
                "tool_input": {"file_path": "/home/user/.claude/plans/test-plan.md", "content": "# Plan"},
            },
            env,
        )
        plan_write_allowed_payload = json.loads(plan_write_allowed.stdout or "{}")
        plan_write_allowed_decision = plan_write_allowed_payload.get("hookSpecificOutput", {}).get("permissionDecision")
        if plan_write_allowed_decision != "pass":
            raise RuntimeError(f"Phase 2 gate: plan Write with requirements_confirmed should pass, got: {plan_write_allowed_decision}")

        stop = run_hook("stop_dig_session.py", {"session_id": session_id}, env)
        if stop.returncode != 0:
            raise RuntimeError(f"stop_dig_session failed: {stop.stderr}")

        state = load_state(home, session_id)
        dig = state.get("dig", {})
        if not isinstance(dig, dict) or dig.get("active"):
            raise RuntimeError("stop_dig_session did not clear dig state")

    print(json.dumps({"ok": True}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
