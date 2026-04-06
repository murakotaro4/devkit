#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_CONFIG_REL = ".devkit/repo-maintainer.toml"
DEFAULT_ALLOWED_PATHS = [
    "AGENTS.md",
    "CLAUDE.md",
    "MEMORY.md",
    "docs",
    "logs/skills",
    "reviews",
    ".devkit",
]
MANDATORY_ALLOWED_PATHS = ("logs/skills", "reviews", ".devkit")
DEFAULT_LANE_GOALS = {
    "daily": "Review recent maintenance signals, keep operational docs aligned, and capture durable updates.",
    "drift": "Audit implementation-to-document drift and reconcile safe mismatches within the current phase.",
    "weekly": "Consolidate repeated rules, prune stale notes, and refresh the weekly review summary.",
}
PHASE_LABELS = {
    1: "docs-knowledge-cleanup",
    2: "config-template-ci",
    3: "code-and-scripts",
}
PHASE1_ROOT_FILES = {"AGENTS.md", "CLAUDE.md", "MEMORY.md"}
PHASE1_EXTENSIONS = {".adoc", ".jsonl", ".md", ".rst", ".txt"}
PHASE2_EXTENSIONS = {".cfg", ".editorconfig", ".ini", ".json", ".toml", ".yaml", ".yml"}
TRANSIENT_REVIEW_MARKERS = (
    "timed out",
    "timeout",
    "rate limit",
    "unavailable",
    "not found",
    "command not found",
    "no such file",
    "429",
    "temporarily",
)
WEEKDAY_MAP = {
    "mon": 0,
    "monday": 0,
    "tue": 1,
    "tues": 1,
    "tuesday": 1,
    "wed": 2,
    "wednesday": 2,
    "thu": 3,
    "thur": 3,
    "thurs": 3,
    "thursday": 3,
    "fri": 4,
    "friday": 4,
    "sat": 5,
    "saturday": 5,
    "sun": 6,
    "sunday": 6,
}
RESULT_SCHEMA = {
    "type": "object",
    "properties": {
        "goal": {"type": "string"},
        "summary": {"type": "string"},
        "successes": {"type": "array", "items": {"type": "string"}},
        "gaps": {"type": "array", "items": {"type": "string"}},
        "update_targets": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["goal", "summary", "successes", "gaps", "update_targets"],
    "additionalProperties": False,
}


@dataclass(frozen=True)
class LaneConfig:
    enabled: bool
    goal: str
    interval_days: int | None = None
    weekday: int | None = None


@dataclass(frozen=True)
class GitConfig:
    remote: str
    base_branch: str
    auto_merge: bool
    commit_template: str
    pr_title_prefix: str


@dataclass(frozen=True)
class CodexConfig:
    command: tuple[str, ...]
    extra_args: tuple[str, ...]
    model: str | None
    search: bool


@dataclass(frozen=True)
class MaintainerConfig:
    forge: str
    phase: int
    allowed_paths: tuple[str, ...]
    review_commands: tuple[str, ...]
    check_commands: tuple[str, ...]
    lanes: dict[str, LaneConfig]
    git: GitConfig
    codex: CodexConfig
    prompt_appendix: str


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    output: str


def normalize_rel_path(path: str) -> str:
    normalized = path.replace("\\", "/").strip()
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized.strip("/")


def ensure_string_list(value: Any, *, field_name: str) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be a string or array of strings")
    result: list[str] = []
    for entry in value:
        if not isinstance(entry, str) or not entry.strip():
            raise ValueError(f"{field_name} must contain non-empty strings")
        result.append(entry.strip())
    return result


def ensure_command_prefix(value: Any, *, default: list[str]) -> tuple[str, ...]:
    if value is None:
        return tuple(default)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            raise ValueError("codex.command must not be empty")
        return (stripped,)
    if not isinstance(value, list):
        raise ValueError("codex.command must be a string or array of strings")
    result: list[str] = []
    for entry in value:
        if not isinstance(entry, str) or not entry.strip():
            raise ValueError("codex.command entries must be non-empty strings")
        result.append(entry.strip())
    if not result:
        raise ValueError("codex.command must not be empty")
    return tuple(result)


def parse_bool(value: Any, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    raise ValueError("expected boolean value")


def parse_weekday(value: Any) -> int:
    if isinstance(value, int):
        if 0 <= value <= 6:
            return value
        raise ValueError("weekly weekday must be between 0 and 6")
    if isinstance(value, str):
        key = value.strip().lower()
        if key in WEEKDAY_MAP:
            return WEEKDAY_MAP[key]
    raise ValueError("weekly weekday must be an integer 0-6 or weekday name")


def load_config(path: Path) -> MaintainerConfig:
    raw = tomllib.loads(path.read_text(encoding="utf-8"))

    phase = int(raw.get("phase", 1))
    if phase not in PHASE_LABELS:
        raise ValueError("phase must be one of 1, 2, or 3")

    forge = str(raw.get("forge", "github")).strip().lower()
    if forge != "github":
        raise ValueError("forge must be github for v1")

    allowed_paths = ensure_string_list(raw.get("allowed_paths"), field_name="allowed_paths") or DEFAULT_ALLOWED_PATHS
    merged_allowed = [normalize_rel_path(entry) for entry in allowed_paths]
    for required in MANDATORY_ALLOWED_PATHS:
        normalized = normalize_rel_path(required)
        if normalized not in merged_allowed:
            merged_allowed.append(normalized)

    review_commands = ensure_string_list(raw.get("review_commands"), field_name="review_commands")
    check_commands = ensure_string_list(raw.get("check_commands"), field_name="check_commands")

    lanes_raw = raw.get("lanes")
    if lanes_raw is None:
        lanes_raw = {}
    if not isinstance(lanes_raw, dict):
        raise ValueError("lanes must be a table")

    lanes: dict[str, LaneConfig] = {}
    for lane_name in ("daily", "drift", "weekly"):
        lane_value = lanes_raw.get(lane_name, {})
        if lane_value is None:
            lane_value = {}
        if not isinstance(lane_value, dict):
            raise ValueError(f"lanes.{lane_name} must be a table")
        enabled = parse_bool(lane_value.get("enabled"), default=True)
        goal = str(lane_value.get("goal", DEFAULT_LANE_GOALS[lane_name])).strip()
        if not goal:
            raise ValueError(f"lanes.{lane_name}.goal must not be empty")
        interval_days = None
        weekday = None
        if lane_name == "drift":
            interval_days = int(lane_value.get("interval_days", 3))
            if interval_days <= 0:
                raise ValueError("lanes.drift.interval_days must be positive")
        if lane_name == "weekly":
            weekday = parse_weekday(lane_value.get("weekday", "sun"))
        lanes[lane_name] = LaneConfig(
            enabled=enabled,
            goal=goal,
            interval_days=interval_days,
            weekday=weekday,
        )

    git_raw = raw.get("git")
    if git_raw is None:
        git_raw = {}
    if not isinstance(git_raw, dict):
        raise ValueError("git must be a table")
    git_config = GitConfig(
        remote=str(git_raw.get("remote", "origin")).strip() or "origin",
        base_branch=str(git_raw.get("base_branch", "main")).strip() or "main",
        auto_merge=parse_bool(git_raw.get("auto_merge"), default=True),
        commit_template=(
            str(git_raw.get("commit_template", "chore(repo-maintainer): 夜間メンテナンス更新 ({lane})")).strip()
            or "chore(repo-maintainer): 夜間メンテナンス更新 ({lane})"
        ),
        pr_title_prefix=(str(git_raw.get("pr_title_prefix", "[repo-maintainer]")).strip() or "[repo-maintainer]"),
    )

    codex_raw = raw.get("codex")
    if codex_raw is None:
        codex_raw = {}
    if not isinstance(codex_raw, dict):
        raise ValueError("codex must be a table")
    codex_config = CodexConfig(
        command=ensure_command_prefix(codex_raw.get("command"), default=["codex", "exec"]),
        extra_args=tuple(ensure_string_list(codex_raw.get("extra_args"), field_name="codex.extra_args")),
        model=str(codex_raw.get("model")).strip() if codex_raw.get("model") else None,
        search=parse_bool(codex_raw.get("search"), default=False),
    )

    prompt_appendix = str(raw.get("prompt_appendix", "")).strip()

    return MaintainerConfig(
        forge=forge,
        phase=phase,
        allowed_paths=tuple(merged_allowed),
        review_commands=tuple(review_commands),
        check_commands=tuple(check_commands),
        lanes=lanes,
        git=git_config,
        codex=codex_config,
        prompt_appendix=prompt_appendix,
    )


def git(args: list[str], *, cwd: Path, check: bool = True) -> CommandResult:
    result = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    output = "\n".join(part for part in (result.stdout.strip(), result.stderr.strip()) if part)
    if check and result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {output or f'exit={result.returncode}'}")
    return CommandResult(returncode=result.returncode, output=output)


def run_shell(command: str, *, cwd: Path) -> CommandResult:
    result = subprocess.run(
        command,
        cwd=str(cwd),
        shell=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    output = "\n".join(part for part in (result.stdout.strip(), result.stderr.strip()) if part)
    return CommandResult(returncode=result.returncode, output=output)


def run_command(args: list[str], *, cwd: Path, stdin_text: str | None = None, env: dict[str, str] | None = None) -> CommandResult:
    result = subprocess.run(
        args,
        cwd=str(cwd),
        input=stdin_text,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
    )
    output = "\n".join(part for part in (result.stdout.strip(), result.stderr.strip()) if part)
    return CommandResult(returncode=result.returncode, output=output)


def ensure_repo_root(repo: Path) -> Path:
    resolved = repo.resolve()
    result = git(["rev-parse", "--show-toplevel"], cwd=resolved)
    return Path(result.output.strip()).resolve()


def select_due_lanes(config: MaintainerConfig, now: dt.datetime, forced_lanes: list[str] | None = None) -> list[str]:
    order = ("daily", "drift", "weekly")
    if forced_lanes:
        normalized = []
        for lane in forced_lanes:
            key = lane.strip().lower()
            if key not in config.lanes:
                raise ValueError(f"unknown lane: {lane}")
            if key not in normalized:
                normalized.append(key)
        return normalized

    due: list[str] = []
    for lane_name in order:
        lane = config.lanes[lane_name]
        if not lane.enabled:
            continue
        if lane_name == "daily":
            due.append(lane_name)
            continue
        if lane_name == "drift" and lane.interval_days and now.toordinal() % lane.interval_days == 0:
            due.append(lane_name)
            continue
        if lane_name == "weekly" and lane.weekday is not None and now.weekday() == lane.weekday:
            due.append(lane_name)
    return due


def branch_name_for(now: dt.datetime, lane: str) -> str:
    return f"codex/maint/{now:%Y%m%d}-{lane}"


def pr_title_for(config: MaintainerConfig, now: dt.datetime, lane: str) -> str:
    return f"{config.git.pr_title_prefix} {now:%Y-%m-%d} {lane}"


def resolve_base_ref(repo_root: Path, config: MaintainerConfig) -> str:
    remote_branch = f"{config.git.remote}/{config.git.base_branch}"
    git(["fetch", config.git.remote, config.git.base_branch], cwd=repo_root, check=False)
    probe = git(["rev-parse", "--verify", remote_branch], cwd=repo_root, check=False)
    if probe.returncode == 0:
        return remote_branch
    return config.git.base_branch


def create_temp_worktree(repo_root: Path, base_ref: str) -> Path:
    temp_dir = Path(tempfile.mkdtemp(prefix="repo-maintainer-")).resolve()
    git(["worktree", "add", "--detach", str(temp_dir), base_ref], cwd=repo_root)
    return temp_dir


def remove_temp_worktree(repo_root: Path, temp_dir: Path) -> None:
    git(["worktree", "remove", "--force", str(temp_dir)], cwd=repo_root, check=False)
    if temp_dir.exists():
        shutil.rmtree(temp_dir, ignore_errors=True)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_prompt(config: MaintainerConfig, lane: str, now: dt.datetime) -> str:
    appendix = ""
    if config.prompt_appendix:
        appendix = "\nAdditional repo-specific guidance:\n" + config.prompt_appendix.strip()
    return textwrap.dedent(
        f"""
        Use $repo-maintainer in this repository.

        Lane:
        - name: {lane}
        - goal: {config.lanes[lane].goal}
        - local_datetime: {now.isoformat()}

        Guardrails:
        - phase: {config.phase} ({PHASE_LABELS[config.phase]})
        - allowed_paths: {", ".join(config.allowed_paths)}
        - forge: {config.forge}
        - config_path: {DEFAULT_CONFIG_REL}
        - do not commit, push, create branches, or open PRs
        - leave the worktree untouched if no safe improvement is needed
        - keep edits bounded to the current phase and allowed paths
        - prefer deterministic cleanup over speculative refactors

        Required final response fields:
        - goal
        - summary
        - successes
        - gaps
        - update_targets
        {appendix}
        """
    ).strip()


def invoke_codex(config: MaintainerConfig, *, worktree: Path, lane: str, now: dt.datetime) -> tuple[dict[str, Any], CommandResult]:
    temp_root = Path(tempfile.mkdtemp(prefix=f"repo-maintainer-codex-{lane}-"))
    try:
        schema_path = temp_root / "schema.json"
        output_path = temp_root / "result.json"
        write_json(schema_path, RESULT_SCHEMA)

        cmd = list(config.codex.command)
        if config.codex.model:
            cmd.extend(["-m", config.codex.model])
        if config.codex.search:
            cmd.append("--search")
        cmd.extend(["-a", "never", "-s", "workspace-write"])
        cmd.extend(config.codex.extra_args)
        cmd.extend(["--output-schema", str(schema_path), "-o", str(output_path), "-"])

        env = os.environ.copy()
        env.update(
            {
                "REPO_MAINTAINER_LANE": lane,
                "REPO_MAINTAINER_PHASE": str(config.phase),
                "REPO_MAINTAINER_ALLOWED_PATHS": json.dumps(list(config.allowed_paths), ensure_ascii=False),
                "REPO_MAINTAINER_CONFIG": str(worktree / DEFAULT_CONFIG_REL),
            }
        )
        prompt = build_prompt(config, lane, now)
        result = run_command(cmd, cwd=worktree, stdin_text=prompt, env=env)

        if result.returncode != 0:
            raise RuntimeError(f"codex execution failed: {result.output or f'exit={result.returncode}'}")
        if not output_path.exists():
            raise RuntimeError("codex did not produce an output message file")
        payload = json.loads(output_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise RuntimeError("codex output must be a JSON object")
        normalized = {
            "goal": str(payload.get("goal", config.lanes[lane].goal)).strip() or config.lanes[lane].goal,
            "summary": str(payload.get("summary", "")).strip(),
            "successes": [str(entry).strip() for entry in payload.get("successes", []) if str(entry).strip()],
            "gaps": [str(entry).strip() for entry in payload.get("gaps", []) if str(entry).strip()],
            "update_targets": [str(entry).strip() for entry in payload.get("update_targets", []) if str(entry).strip()],
        }
        return normalized, result
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def parse_name_status(raw: str) -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        status_token = parts[0]
        status = "".join(ch for ch in status_token if ch.isalpha()) or status_token
        if status.startswith("R") or status == "R":
            if len(parts) < 3:
                continue
            changes.append({"status": "R", "old": normalize_rel_path(parts[1]), "new": normalize_rel_path(parts[2])})
            continue
        if status.startswith("C") or status == "C":
            if len(parts) < 3:
                continue
            changes.append({"status": "C", "old": normalize_rel_path(parts[1]), "new": normalize_rel_path(parts[2])})
            continue
        if len(parts) < 2:
            continue
        changes.append({"status": status[:1], "path": normalize_rel_path(parts[1])})
    return changes


def collect_staged_changes(worktree: Path) -> list[dict[str, Any]]:
    diff = git(["diff", "--cached", "--name-status", "--find-renames"], cwd=worktree)
    return parse_name_status(diff.output)


def flatten_changed_paths(changes: list[dict[str, Any]]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for entry in changes:
        for key in ("old", "new", "path"):
            value = entry.get(key)
            if isinstance(value, str) and value and value not in seen:
                seen.add(value)
                ordered.append(value)
    return ordered


def path_allowed(path: str, allowed_paths: tuple[str, ...]) -> bool:
    rel = normalize_rel_path(path)
    for allowed in allowed_paths:
        target = normalize_rel_path(allowed)
        if rel == target or rel.startswith(target + "/"):
            return True
    return False


def phase_allows_path(phase: int, path: str) -> bool:
    rel = normalize_rel_path(path)
    name = Path(rel).name
    suffix = Path(rel).suffix.lower()

    if phase >= 3:
        return True
    if rel.startswith(".devkit/"):
        return True
    if rel.startswith("docs/") or rel.startswith("logs/skills/") or rel.startswith("reviews/"):
        return True
    if name in PHASE1_ROOT_FILES:
        return True
    if suffix in PHASE1_EXTENSIONS:
        return True
    if phase >= 2:
        if rel.startswith(".github/") or rel.startswith("templates/"):
            return True
        if suffix in PHASE2_EXTENSIONS:
            return True
    return False


def validate_changes(config: MaintainerConfig, changes: list[dict[str, Any]]) -> list[str]:
    violations: list[str] = []
    for entry in changes:
        paths = []
        if "path" in entry:
            paths.append(str(entry["path"]))
        if "old" in entry:
            paths.append(str(entry["old"]))
        if "new" in entry:
            paths.append(str(entry["new"]))
        for path in paths:
            if not path_allowed(path, config.allowed_paths):
                violations.append(f"path outside allowed_paths: {path}")
                continue
            if not phase_allows_path(config.phase, path):
                violations.append(f"phase {config.phase} blocks change: {path}")
    return violations


def append_log_record(repo_root: Path, now: dt.datetime, record: dict[str, Any]) -> Path:
    log_path = repo_root / "logs" / "skills" / f"{now:%Y}" / f"{now:%m}" / f"{now:%d}.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    return log_path


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if not path.exists():
        return records
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        if isinstance(payload, dict):
            records.append(payload)
    return records


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    lines = [json.dumps(entry, ensure_ascii=False) for entry in records]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def replace_last_log_record(log_path: Path, lane: str, branch: str, updated: dict[str, Any]) -> None:
    records = load_jsonl(log_path)
    for index in range(len(records) - 1, -1, -1):
        if records[index].get("lane") == lane and records[index].get("branch") == branch:
            records[index] = updated
            write_jsonl(log_path, records)
            return
    records.append(updated)
    write_jsonl(log_path, records)


def render_daily_review(repo_root: Path, day: dt.date) -> Path:
    log_path = repo_root / "logs" / "skills" / f"{day:%Y}" / f"{day:%m}" / f"{day:%d}.jsonl"
    records = load_jsonl(log_path)
    review_path = repo_root / "reviews" / "daily" / f"{day:%Y-%m-%d}.md"
    review_path.parent.mkdir(parents=True, exist_ok=True)

    lines = [f"# Daily Review - {day:%Y-%m-%d}", "", f"- Runs: {len(records)}", ""]
    if not records:
        lines.extend(["## Summary", "- No maintainer runs recorded.", ""])
    else:
        lines.extend(["## Runs"])
        for record in records:
            changed_count = len(record.get("changed_paths", [])) if isinstance(record.get("changed_paths"), list) else 0
            lines.append(
                "- "
                + " | ".join(
                    [
                        str(record.get("timestamp", "")),
                        f"lane={record.get('lane', '')}",
                        f"review={record.get('review_status', '')}",
                        f"checks={record.get('checks_status', '')}",
                        f"changed={changed_count}",
                    ]
                )
            )
        lines.extend(["", "## Gaps"])
        gaps = [gap for record in records for gap in record.get("gaps", []) if isinstance(gap, str)]
        if gaps:
            for gap in gaps:
                lines.append(f"- {gap}")
        else:
            lines.append("- No open gaps recorded.")
        lines.extend(["", "## Update Targets"])
        targets = [target for record in records for target in record.get("update_targets", []) if isinstance(target, str)]
        if targets:
            for target in targets:
                lines.append(f"- {target}")
        else:
            lines.append("- No update targets recorded.")
        lines.extend(["", "## Changed Paths"])
        paths = [path for record in records for path in record.get("changed_paths", []) if isinstance(path, str)]
        if paths:
            for path in dict.fromkeys(paths):
                lines.append(f"- `{path}`")
        else:
            lines.append("- No repository changes recorded.")

    review_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return review_path


def render_weekly_review(repo_root: Path, day: dt.date) -> Path:
    iso_year, iso_week, _ = day.isocalendar()
    monday = day - dt.timedelta(days=day.weekday())
    records: list[dict[str, Any]] = []
    for offset in range(7):
        current = monday + dt.timedelta(days=offset)
        log_path = repo_root / "logs" / "skills" / f"{current:%Y}" / f"{current:%m}" / f"{current:%d}.jsonl"
        records.extend(load_jsonl(log_path))

    review_path = repo_root / "reviews" / "weekly" / f"{iso_year}-W{iso_week:02d}.md"
    review_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# Weekly Review - {iso_year}-W{iso_week:02d}",
        "",
        f"- Days covered: {monday:%Y-%m-%d} to {(monday + dt.timedelta(days=6)):%Y-%m-%d}",
        f"- Runs: {len(records)}",
        "",
        "## Lane Totals",
    ]
    lane_totals = {lane: 0 for lane in ("daily", "drift", "weekly")}
    for record in records:
        lane = record.get("lane")
        if isinstance(lane, str) and lane in lane_totals:
            lane_totals[lane] += 1
    for lane, count in lane_totals.items():
        lines.append(f"- {lane}: {count}")

    lines.extend(["", "## Recurring Gaps"])
    gap_totals: dict[str, int] = {}
    for record in records:
        for gap in record.get("gaps", []):
            if isinstance(gap, str) and gap:
                gap_totals[gap] = gap_totals.get(gap, 0) + 1
    if gap_totals:
        for gap, count in sorted(gap_totals.items(), key=lambda item: (-item[1], item[0])):
            lines.append(f"- ({count}x) {gap}")
    else:
        lines.append("- No recurring gaps recorded.")

    lines.extend(["", "## Most Touched Paths"])
    path_totals: dict[str, int] = {}
    for record in records:
        for path in record.get("changed_paths", []):
            if isinstance(path, str) and path:
                path_totals[path] = path_totals.get(path, 0) + 1
    if path_totals:
        for path, count in sorted(path_totals.items(), key=lambda item: (-item[1], item[0]))[:20]:
            lines.append(f"- ({count}x) `{path}`")
    else:
        lines.append("- No repository changes recorded.")

    review_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return review_path


def write_review_files(repo_root: Path, now: dt.datetime) -> tuple[Path, Path]:
    return (render_daily_review(repo_root, now.date()), render_weekly_review(repo_root, now.date()))


def format_commit_message(template: str, *, lane: str, now: dt.datetime) -> str:
    try:
        return template.format(lane=lane, date=now.strftime("%Y-%m-%d"), yyyymmdd=now.strftime("%Y%m%d"))
    except KeyError:
        return f"chore(repo-maintainer): 夜間メンテナンス更新 ({lane})"


def run_review_commands(commands: tuple[str, ...], *, cwd: Path) -> tuple[str, list[dict[str, Any]], bool]:
    if not commands:
        return ("skipped", [], False)
    details: list[dict[str, Any]] = []
    for index, command in enumerate(commands):
        result = run_shell(command, cwd=cwd)
        details.append({"command": command, "returncode": result.returncode, "output": result.output})
        if result.returncode == 0:
            return ("passed", details, True)
        output_lower = result.output.lower()
        has_fallback = index < len(commands) - 1
        if not has_fallback or not any(marker in output_lower for marker in TRANSIENT_REVIEW_MARKERS):
            return ("failed", details, False)
    return ("failed", details, False)


def run_check_commands(commands: tuple[str, ...], *, cwd: Path) -> tuple[str, list[dict[str, Any]], bool]:
    if not commands:
        return ("skipped", [], False)
    details: list[dict[str, Any]] = []
    success = True
    for command in commands:
        result = run_shell(command, cwd=cwd)
        details.append({"command": command, "returncode": result.returncode, "output": result.output})
        if result.returncode != 0:
            success = False
    return ("passed" if success else "failed", details, success)


def create_pr_body(
    *,
    lane: str,
    phase: int,
    codex_result: dict[str, Any],
    changed_paths: list[str],
    review_status: str,
    checks_status: str,
) -> str:
    lines = [
        f"# Repo Maintainer ({lane})",
        "",
        f"- Phase: {phase} ({PHASE_LABELS[phase]})",
        f"- Review: {review_status}",
        f"- Checks: {checks_status}",
        "",
        "## Goal",
        codex_result.get("goal", ""),
        "",
        "## Summary",
        codex_result.get("summary", ""),
        "",
        "## Successes",
    ]
    successes = codex_result.get("successes", [])
    if successes:
        for entry in successes:
            lines.append(f"- {entry}")
    else:
        lines.append("- No explicit successes recorded.")

    lines.extend(["", "## Gaps"])
    gaps = codex_result.get("gaps", [])
    if gaps:
        for entry in gaps:
            lines.append(f"- {entry}")
    else:
        lines.append("- No open gaps recorded.")

    lines.extend(["", "## Update Targets"])
    targets = codex_result.get("update_targets", [])
    if targets:
        for entry in targets:
            lines.append(f"- {entry}")
    else:
        lines.append("- No update targets recorded.")

    lines.extend(["", "## Changed Paths"])
    if changed_paths:
        for path in changed_paths:
            lines.append(f"- `{path}`")
    else:
        lines.append("- No repository changes.")
    return "\n".join(lines).rstrip() + "\n"


def gh(args: list[str], *, cwd: Path, check: bool = True) -> CommandResult:
    executable = os.environ.get("REPO_MAINTAINER_GH_PATH", "gh")
    result = run_command([executable, *args], cwd=cwd)
    if check and result.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args)} failed: {result.output or f'exit={result.returncode}'}")
    return result


def create_pull_request(
    *,
    worktree: Path,
    config: MaintainerConfig,
    branch: str,
    title: str,
    body: str,
) -> str:
    body_path = worktree / ".devkit" / "tmp" / "repo-maintainer-pr-body.md"
    body_path.parent.mkdir(parents=True, exist_ok=True)
    body_path.write_text(body, encoding="utf-8")
    result = gh(
        [
            "pr",
            "create",
            "--base",
            config.git.base_branch,
            "--head",
            branch,
            "--title",
            title,
            "--body-file",
            str(body_path),
        ],
        cwd=worktree,
        check=False,
    )
    if result.returncode == 0:
        return result.output.strip()

    existing = gh(["pr", "list", "--head", branch, "--state", "open", "--json", "url"], cwd=worktree, check=False)
    if existing.returncode == 0 and existing.output.strip():
        try:
            payload = json.loads(existing.output)
        except json.JSONDecodeError:
            return existing.output.strip()
        if isinstance(payload, list):
            for entry in payload:
                if isinstance(entry, dict) and isinstance(entry.get("url"), str):
                    return entry["url"]
    raise RuntimeError(f"gh pr create failed: {result.output or f'exit={result.returncode}'}")


def enable_auto_merge(*, worktree: Path, pr_target: str) -> None:
    gh(["pr", "merge", "--auto", "--squash", "--delete-branch", pr_target], cwd=worktree)


def run_lane(repo_root: Path, config: MaintainerConfig, *, lane: str, now: dt.datetime, keep_worktree: bool) -> dict[str, Any]:
    base_ref = resolve_base_ref(repo_root, config)
    branch = branch_name_for(now, lane)
    worktree = create_temp_worktree(repo_root, base_ref)
    cleanup_required = not keep_worktree
    try:
        git(["checkout", "-B", branch], cwd=worktree)

        codex_result, codex_command = invoke_codex(config, worktree=worktree, lane=lane, now=now)
        git(["add", "-A"], cwd=worktree)
        initial_changes = collect_staged_changes(worktree)
        initial_violations = validate_changes(config, initial_changes)
        if initial_violations:
            return {
                "lane": lane,
                "status": "blocked",
                "branch": branch,
                "worktree": str(worktree),
                "reason": "phase/allowed_paths violation",
                "violations": initial_violations,
                "codex_output": codex_command.output,
            }

        initial_paths = flatten_changed_paths(initial_changes)
        if not initial_paths:
            return {
                "lane": lane,
                "status": "noop",
                "branch": branch,
                "worktree": str(worktree),
                "review_status": "skipped",
                "checks_status": "skipped",
            }

        record = {
            "timestamp": now.isoformat(),
            "lane": lane,
            "goal": codex_result["goal"],
            "successes": codex_result["successes"],
            "gaps": codex_result["gaps"],
            "update_targets": codex_result["update_targets"],
            "changed_paths": initial_paths,
            "branch": branch,
            "pr_url": "",
            "review_status": "pending",
            "checks_status": "pending",
            "summary": codex_result["summary"],
        }
        log_path = append_log_record(worktree, now, record)
        daily_path, weekly_path = write_review_files(worktree, now)
        git(["add", "-A"], cwd=worktree)

        review_status, review_details, review_passed = run_review_commands(config.review_commands, cwd=worktree)
        checks_status, check_details, checks_passed = run_check_commands(config.check_commands, cwd=worktree)
        record["review_status"] = review_status
        record["checks_status"] = checks_status
        replace_last_log_record(log_path, lane, branch, record)
        daily_path, weekly_path = write_review_files(worktree, now)
        git(["add", "-A"], cwd=worktree)

        final_changes = collect_staged_changes(worktree)
        final_violations = validate_changes(config, final_changes)
        if final_violations:
            return {
                "lane": lane,
                "status": "blocked",
                "branch": branch,
                "worktree": str(worktree),
                "reason": "phase/allowed_paths violation after logging",
                "violations": final_violations,
            }

        final_paths = flatten_changed_paths(final_changes)

        commit_message = format_commit_message(config.git.commit_template, lane=lane, now=now)
        git(["commit", "-m", commit_message], cwd=worktree)
        git(["push", "-u", config.git.remote, branch, "--force-with-lease"], cwd=worktree)

        pr_title = pr_title_for(config, now, lane)
        pr_body = create_pr_body(
            lane=lane,
            phase=config.phase,
            codex_result=codex_result,
            changed_paths=final_paths,
            review_status=review_status,
            checks_status=checks_status,
        )
        pr_url = create_pull_request(worktree=worktree, config=config, branch=branch, title=pr_title, body=pr_body)

        auto_merge_triggered = False
        if config.git.auto_merge and review_passed and checks_passed and config.check_commands:
            enable_auto_merge(worktree=worktree, pr_target=pr_url or branch)
            auto_merge_triggered = True

        return {
            "lane": lane,
            "status": "ok",
            "branch": branch,
            "pr_url": pr_url,
            "review_status": review_status,
            "checks_status": checks_status,
            "auto_merge_triggered": auto_merge_triggered,
            "changed_paths": final_paths,
            "log_path": str(log_path.relative_to(worktree)),
            "daily_review_path": str(daily_path.relative_to(worktree)),
            "weekly_review_path": str(weekly_path.relative_to(worktree)),
            "review_details": review_details,
            "check_details": check_details,
            "worktree": str(worktree),
        }
    finally:
        if cleanup_required:
            remove_temp_worktree(repo_root, worktree)


def run_maintainer(
    *,
    repo: Path,
    config_path: Path | None = None,
    forced_lanes: list[str] | None = None,
    now: dt.datetime | None = None,
    keep_worktree: bool = False,
) -> dict[str, Any]:
    repo_root = ensure_repo_root(repo)
    config_file = config_path or (repo_root / DEFAULT_CONFIG_REL)
    config = load_config(config_file)
    moment = now or dt.datetime.now().astimezone()
    lanes = select_due_lanes(config, moment, forced_lanes)
    results = [run_lane(repo_root, config, lane=lane, now=moment, keep_worktree=keep_worktree) for lane in lanes]
    return {
        "repo_root": str(repo_root),
        "config_path": str(config_file),
        "lanes": lanes,
        "results": results,
    }


def power_shell_wrapper(repo_root: Path) -> str:
    config_rel = DEFAULT_CONFIG_REL.replace("/", "\\")
    return textwrap.dedent(
        f"""
        [CmdletBinding()]
        param(
          [Parameter(ValueFromRemainingArguments = $true)]
          [string[]]$ArgsList
        )

        $ErrorActionPreference = "Stop"
        $RepoRoot = "{repo_root}"
        $ConfigPath = Join-Path $RepoRoot "{config_rel}"
        $RunnerCandidates = @()
        if (-not [string]::IsNullOrWhiteSpace($env:DEVKIT_SOURCE_ROOT)) {{
          $RunnerCandidates += (Join-Path $env:DEVKIT_SOURCE_ROOT "plugins\\devkit\\scripts\\repo_maintainer.py")
        }}
        $RunnerCandidates += @(
          (Join-Path $HOME ".codex\\devkit\\source\\plugins\\devkit\\scripts\\repo_maintainer.py"),
          (Join-Path $HOME ".config\\opencode\\devkit\\source\\plugins\\devkit\\scripts\\repo_maintainer.py"),
          (Join-Path $HOME ".claude\\plugins\\marketplaces\\murakotaro4\\plugins\\devkit\\scripts\\repo_maintainer.py")
        )

        $RunnerPath = $null
        foreach ($candidate in $RunnerCandidates) {{
          if (Test-Path -LiteralPath $candidate) {{
            $RunnerPath = $candidate
            break
          }}
        }}
        if (-not $RunnerPath) {{
          throw "REPO_MAINTAINER_RUNNER_NOT_FOUND"
        }}

        $Python = $null
        foreach ($name in @("python", "py")) {{
          $command = Get-Command $name -ErrorAction SilentlyContinue
          if ($command) {{
            $Python = $command.Source
            break
          }}
        }}
        if (-not $Python) {{
          throw "PYTHON_NOT_FOUND"
        }}

        $InvocationArgs = @($RunnerPath, "run", "--repo", $RepoRoot, "--config", $ConfigPath)
        if ($ArgsList) {{
          $InvocationArgs += $ArgsList
        }}

        & $Python @InvocationArgs
        exit $LASTEXITCODE
        """
    ).strip() + "\n"


def posix_wrapper(repo_root: Path) -> str:
    return textwrap.dedent(
        f"""
        #!/bin/sh
        set -eu

        REPO_ROOT="{repo_root.as_posix()}"
        CONFIG_PATH="$REPO_ROOT/{DEFAULT_CONFIG_REL}"

        find_runner() {{
          if [ -n "${{DEVKIT_SOURCE_ROOT:-}}" ] && [ -f "$DEVKIT_SOURCE_ROOT/plugins/devkit/scripts/repo_maintainer.py" ]; then
            printf '%s\\n' "$DEVKIT_SOURCE_ROOT/plugins/devkit/scripts/repo_maintainer.py"
            return 0
          fi
          for candidate in \\
            "$HOME/.codex/devkit/source/plugins/devkit/scripts/repo_maintainer.py" \\
            "$HOME/.config/opencode/devkit/source/plugins/devkit/scripts/repo_maintainer.py" \\
            "$HOME/.claude/plugins/marketplaces/murakotaro4/plugins/devkit/scripts/repo_maintainer.py"
          do
            if [ -f "$candidate" ]; then
              printf '%s\\n' "$candidate"
              return 0
            fi
          done
          return 1
        }}

        if command -v python3 >/dev/null 2>&1; then
          PYTHON_BIN=python3
        elif command -v python >/dev/null 2>&1; then
          PYTHON_BIN=python
        else
          printf 'PYTHON_NOT_FOUND\\n' >&2
          exit 1
        fi

        RUNNER_PATH="$(find_runner)" || {{
          printf 'REPO_MAINTAINER_RUNNER_NOT_FOUND\\n' >&2
          exit 1
        }}

        exec "$PYTHON_BIN" "$RUNNER_PATH" run --repo "$REPO_ROOT" --config "$CONFIG_PATH" "$@"
        """
    ).strip() + "\n"


def windows_scheduler_script(repo_root: Path, task_time: str) -> str:
    task_name = f"RepoNightlyMaintainer-{repo_root.name}"
    return textwrap.dedent(
        f"""
        [CmdletBinding()]
        param(
          [string]$TaskName = "{task_name}",
          [string]$TaskTime = "{task_time}"
        )

        $ErrorActionPreference = "Stop"
        $RepoRoot = "{repo_root}"
        $CommandPath = Join-Path $RepoRoot ".devkit\\bin\\repo-maintainer.ps1"
        $Time = [datetime]::ParseExact($TaskTime, "HH:mm", $null)
        $Action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$CommandPath`""
        $Trigger = New-ScheduledTaskTrigger -Daily -At $Time
        Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Description "Nightly repo maintainer for {repo_root.name}" -Force | Out-Null
        """
    ).strip() + "\n"


def macos_launchd_plist(repo_root: Path, hour: int, minute: int) -> str:
    label = f"devkit.repo-maintainer.{repo_root.name}"
    stdout_path = (repo_root / ".devkit" / "logs" / "repo-maintainer.stdout.log").as_posix()
    stderr_path = (repo_root / ".devkit" / "logs" / "repo-maintainer.stderr.log").as_posix()
    wrapper_path = (repo_root / ".devkit" / "bin" / "repo-maintainer.sh").as_posix()
    return textwrap.dedent(
        f"""
        <?xml version="1.0" encoding="UTF-8"?>
        <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
        <plist version="1.0">
        <dict>
          <key>Label</key>
          <string>{label}</string>
          <key>ProgramArguments</key>
          <array>
            <string>{wrapper_path}</string>
          </array>
          <key>StartCalendarInterval</key>
          <dict>
            <key>Hour</key>
            <integer>{hour}</integer>
            <key>Minute</key>
            <integer>{minute}</integer>
          </dict>
          <key>StandardOutPath</key>
          <string>{stdout_path}</string>
          <key>StandardErrorPath</key>
          <string>{stderr_path}</string>
          <key>WorkingDirectory</key>
          <string>{repo_root.as_posix()}</string>
        </dict>
        </plist>
        """
    ).strip() + "\n"


def linux_systemd_service(repo_root: Path) -> str:
    wrapper_path = (repo_root / ".devkit" / "bin" / "repo-maintainer.sh").as_posix()
    return textwrap.dedent(
        f"""
        [Unit]
        Description=Nightly repo maintainer for {repo_root.name}

        [Service]
        Type=oneshot
        WorkingDirectory={repo_root.as_posix()}
        ExecStart={wrapper_path}
        """
    ).strip() + "\n"


def linux_systemd_timer(repo_root: Path, task_time: str) -> str:
    return textwrap.dedent(
        f"""
        [Unit]
        Description=Nightly repo maintainer timer for {repo_root.name}

        [Timer]
        OnCalendar=*-*-* {task_time}:00
        Persistent=true

        [Install]
        WantedBy=timers.target
        """
    ).strip() + "\n"


def linux_cron_entry(repo_root: Path, hour: int, minute: int) -> str:
    wrapper_path = (repo_root / ".devkit" / "bin" / "repo-maintainer.sh").as_posix()
    return f"{minute} {hour} * * * {wrapper_path}\n"


def scaffold_config_text(base_branch: str, auto_merge: bool) -> str:
    auto_merge_text = "true" if auto_merge else "false"
    fallback = "codex -a never exec review --uncommitted -m gpt-5.4 -c 'model_reasoning_effort=\\\"medium\\\"'"
    lines = [
        'forge = "github"',
        "phase = 1",
        'allowed_paths = ["AGENTS.md", "CLAUDE.md", "MEMORY.md", "docs", "logs/skills", "reviews", ".devkit"]',
        "review_commands = [",
        '  "codex -a never exec review --uncommitted -m gpt-5.3-codex-spark",',
        f'  "{fallback}",',
        "]",
        "check_commands = []",
        "",
        "[lanes.daily]",
        "enabled = true",
        f'goal = "{DEFAULT_LANE_GOALS["daily"]}"',
        "",
        "[lanes.drift]",
        "enabled = true",
        "interval_days = 3",
        f'goal = "{DEFAULT_LANE_GOALS["drift"]}"',
        "",
        "[lanes.weekly]",
        "enabled = true",
        'weekday = "sun"',
        f'goal = "{DEFAULT_LANE_GOALS["weekly"]}"',
        "",
        "[git]",
        'remote = "origin"',
        f'base_branch = "{base_branch}"',
        f"auto_merge = {auto_merge_text}",
        'commit_template = "chore(repo-maintainer): 夜間メンテナンス更新 ({lane})"',
        'pr_title_prefix = "[repo-maintainer]"',
        "",
        "[codex]",
        'command = ["codex", "exec"]',
        'model = "gpt-5.4"',
        "search = false",
        "extra_args = []",
        "",
        'prompt_appendix = ""',
        "",
    ]
    return "\n".join(lines)


def memory_template() -> str:
    return textwrap.dedent(
        """
        # MEMORY.md

        ## Stable Facts
        - 長期で有効な前提だけを書く
        - 実装と運用がずれたら根拠を添えて更新する

        ## Decisions
        - 重要判断の理由と影響範囲を残す

        ## Open Threads
        - 継続中の課題や次回見直し点を短く残す
        """
    ).strip() + "\n"


def ensure_text_file(path: Path, content: str, *, force: bool, executable: bool = False) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not force:
        return "skipped"
    path.write_text(content, encoding="utf-8")
    if executable:
        mode = path.stat().st_mode
        path.chmod(mode | 0o111)
    return "written"


def init_scaffold(
    *,
    repo: Path,
    config_path: Path | None = None,
    task_time: str = "02:30",
    phase: int = 1,
    base_branch: str = "main",
    auto_merge: bool = True,
    force: bool = False,
) -> dict[str, Any]:
    if phase != 1:
        raise ValueError("init scaffold starts at phase 1 only")
    repo_root = ensure_repo_root(repo)
    target_config = config_path or (repo_root / DEFAULT_CONFIG_REL)

    hour, minute = [int(part) for part in task_time.split(":", 1)]
    files = {
        target_config: scaffold_config_text(base_branch, auto_merge),
        repo_root / "MEMORY.md": memory_template(),
        repo_root / ".devkit" / "bin" / "repo-maintainer.ps1": power_shell_wrapper(repo_root),
        repo_root / ".devkit" / "bin" / "repo-maintainer.sh": posix_wrapper(repo_root),
        repo_root / ".devkit" / "scheduler" / "windows" / "register-task.ps1": windows_scheduler_script(repo_root, task_time),
        repo_root / ".devkit" / "scheduler" / "macos" / f"devkit.repo-maintainer.{repo_root.name}.plist": macos_launchd_plist(repo_root, hour, minute),
        repo_root / ".devkit" / "scheduler" / "linux" / "repo-maintainer.service": linux_systemd_service(repo_root),
        repo_root / ".devkit" / "scheduler" / "linux" / "repo-maintainer.timer": linux_systemd_timer(repo_root, task_time),
        repo_root / ".devkit" / "scheduler" / "linux" / "repo-maintainer.cron": linux_cron_entry(repo_root, hour, minute),
        repo_root / "logs" / "skills" / ".gitkeep": "",
        repo_root / "reviews" / "daily" / ".gitkeep": "",
        repo_root / "reviews" / "weekly" / ".gitkeep": "",
        repo_root / ".devkit" / "logs" / ".gitkeep": "",
    }

    results: dict[str, str] = {}
    for path, content in files.items():
        executable = path.suffix in {".ps1", ".sh"}
        results[str(path.relative_to(repo_root))] = ensure_text_file(path, content, force=force, executable=executable)

    return {
        "repo_root": str(repo_root),
        "config_path": str(target_config),
        "task_time": task_time,
        "results": results,
    }


def parse_datetime(value: str) -> dt.datetime:
    parsed = dt.datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=dt.datetime.now().astimezone().tzinfo)
    return parsed


def main() -> int:
    parser = argparse.ArgumentParser(prog="repo_maintainer.py")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--repo", default=".")
    run_parser.add_argument("--config")
    run_parser.add_argument("--lane", action="append", dest="lanes")
    run_parser.add_argument("--now")
    run_parser.add_argument("--keep-worktree", action="store_true")

    init_parser = subparsers.add_parser("init-scaffold")
    init_parser.add_argument("--repo", default=".")
    init_parser.add_argument("--config")
    init_parser.add_argument("--task-time", default="02:30")
    init_parser.add_argument("--phase", type=int, default=1)
    init_parser.add_argument("--base-branch", default="main")
    init_parser.add_argument("--auto-merge", choices=("true", "false"), default="true")
    init_parser.add_argument("--force", action="store_true")

    args = parser.parse_args()

    try:
        if args.command == "run":
            payload = run_maintainer(
                repo=Path(args.repo),
                config_path=Path(args.config) if args.config else None,
                forced_lanes=args.lanes,
                now=parse_datetime(args.now) if args.now else None,
                keep_worktree=args.keep_worktree,
            )
        else:
            payload = init_scaffold(
                repo=Path(args.repo),
                config_path=Path(args.config) if args.config else None,
                task_time=args.task_time,
                phase=args.phase,
                base_branch=args.base_branch,
                auto_merge=args.auto_merge == "true",
                force=args.force,
            )
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
