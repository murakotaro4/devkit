from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "repo_maintainer.py"
MODULE_SPEC = importlib.util.spec_from_file_location("repo_maintainer", MODULE_PATH)
assert MODULE_SPEC and MODULE_SPEC.loader
repo_maintainer = importlib.util.module_from_spec(MODULE_SPEC)
sys.modules[MODULE_SPEC.name] = repo_maintainer
MODULE_SPEC.loader.exec_module(repo_maintainer)


def run_git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=str(repo),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    return result.stdout.strip()


def write_text(path: Path, content: str, *, executable: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    if executable:
        path.chmod(path.stat().st_mode | 0o111)



def toml_array(values: list[str]) -> str:
    return "[" + ", ".join(json.dumps(value) for value in values) + "]"


class RepoMaintainerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="repo-maintainer-tests-")
        self.root = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def init_repo(self) -> Path:
        repo = Path(tempfile.mkdtemp(prefix="repo-", dir=self.root))
        repo.mkdir(parents=True, exist_ok=True)
        run_git(repo, "init", "-b", "main")
        run_git(repo, "config", "user.name", "Repo Maintainer Test")
        run_git(repo, "config", "user.email", "repo-maintainer@example.com")
        write_text(repo / "AGENTS.md", "# AGENTS.md\n")
        write_text(repo / "CLAUDE.md", "# CLAUDE.md\n")
        write_text(repo / "README.md", "# Test Repo\n")
        run_git(repo, "add", ".")
        run_git(repo, "commit", "-m", "chore: initial")

        bare = Path(tempfile.mkdtemp(prefix="remote-", dir=self.root)).with_suffix(".git")
        run_git(self.root, "init", "--bare", str(bare))
        run_git(repo, "remote", "add", "origin", str(bare))
        run_git(repo, "push", "-u", "origin", "main")
        return repo

    def add_fake_codex(self) -> Path:
        script = self.root / "fake_codex.py"
        write_text(
            script,
            textwrap.dedent(
                """
                import json
                import os
                import sys
                from pathlib import Path

                def main():
                    args = sys.argv[1:]
                    output_path = None
                    while args:
                        token = args.pop(0)
                        if token in {"-o", "--output-last-message"}:
                            output_path = args.pop(0)
                        elif token == "--output-schema":
                            args.pop(0)
                        elif token in {"-m", "-s", "-a"}:
                            args.pop(0)
                        elif token.startswith("-"):
                            continue

                    behavior = os.environ.get("FAKE_CODEX_BEHAVIOR", "noop")
                    cwd = Path.cwd()
                    if behavior == "docs":
                        target = cwd / "docs" / "nightly.md"
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_text("# Nightly\\n", encoding="utf-8")
                    elif behavior == "config":
                        target = cwd / ".github" / "workflows" / "nightly.yml"
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_text("name: nightly\\n", encoding="utf-8")
                    elif behavior == "code":
                        target = cwd / "src" / "app.py"
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_text("print('nightly')\\n", encoding="utf-8")

                    payload = {
                        "goal": os.environ.get("REPO_MAINTAINER_LANE", "daily"),
                        "summary": f"behavior={behavior}",
                        "successes": [f"applied {behavior} change"] if behavior != "noop" else ["no-op scan"],
                        "gaps": [],
                        "update_targets": ["docs/nightly.md"] if behavior == "docs" else [],
                    }
                    if output_path:
                        Path(output_path).write_text(json.dumps(payload), encoding="utf-8")
                    print(json.dumps(payload))

                if __name__ == "__main__":
                    main()
                """
            ).strip()
            + "\n",
        )
        return script

    def add_fake_gh(self) -> tuple[Path, Path, Path]:
        bin_dir = Path(tempfile.mkdtemp(prefix="fake-gh-bin-", dir=self.root))
        state_path = self.root / f"gh-state-{bin_dir.name}.json"
        script = bin_dir / "fake_gh.py"
        write_text(
            script,
            textwrap.dedent(
                f"""
                import json
                import sys
                from pathlib import Path

                STATE_PATH = Path({json.dumps(state_path.as_posix())})

                def load_state():
                    if not STATE_PATH.exists():
                        return {{"create_calls": [], "merge_calls": []}}
                    return json.loads(STATE_PATH.read_text(encoding="utf-8"))

                def save_state(state):
                    STATE_PATH.write_text(json.dumps(state), encoding="utf-8")

                def main():
                    args = sys.argv[1:]
                    state = load_state()
                    if args[:2] == ["pr", "create"]:
                        head = ""
                        title = ""
                        body_file = ""
                        for index, token in enumerate(args):
                            if token == "--head":
                                head = args[index + 1]
                            elif token == "--title":
                                title = args[index + 1]
                            elif token == "--body-file":
                                body_file = args[index + 1]
                        for entry in state["create_calls"]:
                            if entry["head"] == head:
                                print("already exists", file=sys.stderr)
                                raise SystemExit(1)
                        url = f"https://example.test/{{head or 'branch'}}"
                        state["create_calls"].append({{"head": head, "title": title, "body_file": body_file, "url": url}})
                        save_state(state)
                        print(url)
                        return
                    if args[:2] == ["pr", "list"]:
                        head = ""
                        for index, token in enumerate(args):
                            if token == "--head":
                                head = args[index + 1]
                        for entry in state["create_calls"]:
                            if entry["head"] == head:
                                print(json.dumps([{{"url": entry["url"]}}]))
                                return
                        raise SystemExit(1)
                    if args[:2] == ["pr", "merge"]:
                        state["merge_calls"].append({{"args": args[2:]}})
                        save_state(state)
                        print("auto-merge enabled")
                        return
                    raise SystemExit(2)

                if __name__ == "__main__":
                    main()
                """
            ).strip()
            + "\n",
        )
        write_text(
            bin_dir / "gh.cmd",
            f'@echo off\r\n"{sys.executable}" "{script.as_posix()}" %*\r\n',
            executable=True,
        )
        write_text(
            bin_dir / "gh",
            f'#!/bin/sh\nexec "{sys.executable}" "{script.as_posix()}" "$@"\n',
            executable=True,
        )
        gh_path = bin_dir / ("gh.cmd" if os.name == "nt" else "gh")
        return bin_dir, state_path, gh_path

    def add_command_script(self, name: str, exit_code: int) -> Path:
        script = self.root / f"{name}.py"
        write_text(
            script,
            textwrap.dedent(
                f"""
                import sys
                print({json.dumps(name)})
                raise SystemExit({exit_code})
                """
            ).strip()
            + "\n",
        )
        return script

    def write_config(
        self,
        repo: Path,
        *,
        codex_script: Path,
        phase: int,
        allowed_paths: list[str],
        review_commands: list[str] | None = None,
        check_commands: list[str] | None = None,
        auto_merge: bool = True,
    ) -> Path:
        config = repo / ".devkit" / "repo-maintainer.toml"
        config.parent.mkdir(parents=True, exist_ok=True)
        content = "\n".join(
            [
                'forge = "github"',
                f"phase = {phase}",
                f"allowed_paths = {toml_array(allowed_paths)}",
                f"review_commands = {toml_array(review_commands or [])}",
                f"check_commands = {toml_array(check_commands or [])}",
                "",
                "[lanes.daily]",
                "enabled = true",
                'goal = "Daily review"',
                "",
                "[lanes.drift]",
                "enabled = true",
                "interval_days = 3",
                'goal = "Drift review"',
                "",
                "[lanes.weekly]",
                "enabled = true",
                'weekday = "sun"',
                'goal = "Weekly review"',
                "",
                "[git]",
                'remote = "origin"',
                'base_branch = "main"',
                f"auto_merge = {'true' if auto_merge else 'false'}",
                'commit_template = "chore(repo-maintainer): テスト ({lane})"',
                'pr_title_prefix = "[repo-maintainer]"',
                "",
                "[codex]",
                f"command = {toml_array([sys.executable.replace('\\\\', '/'), codex_script.as_posix(), 'exec'])}",
                'model = "fake"',
                "search = false",
                "extra_args = []",
                "",
                'prompt_appendix = ""',
                "",
            ]
        )
        write_text(config, content)
        return config

    def test_lane_selection_and_naming(self) -> None:
        repo = self.init_repo()
        codex_script = self.add_fake_codex()
        config_path = self.write_config(
            repo,
            codex_script=codex_script,
            phase=1,
            allowed_paths=["docs", "logs/skills", "reviews", ".devkit"],
        )
        config = repo_maintainer.load_config(config_path)
        now = repo_maintainer.parse_datetime("2026-04-05T02:30:00+09:00")
        self.assertEqual(repo_maintainer.select_due_lanes(config, now), ["daily", "weekly"])
        drift_now = now
        for _ in range(7):
            if "drift" in repo_maintainer.select_due_lanes(config, drift_now):
                break
            drift_now = drift_now + repo_maintainer.dt.timedelta(days=1)
        self.assertIn("drift", repo_maintainer.select_due_lanes(config, drift_now))
        self.assertEqual(repo_maintainer.branch_name_for(now, "daily"), "codex/maint/20260405-daily")
        self.assertEqual(repo_maintainer.pr_title_for(config, now, "daily"), "[repo-maintainer] 2026-04-05 daily")

    def test_validate_changes_blocks_phase1_code_and_checks_rename(self) -> None:
        config = repo_maintainer.MaintainerConfig(
            forge="github",
            phase=1,
            allowed_paths=("src", "docs"),
            review_commands=(),
            check_commands=(),
            lanes={},
            git=repo_maintainer.GitConfig("origin", "main", True, "", "[repo-maintainer]"),
            codex=repo_maintainer.CodexConfig(("codex", "exec"), (), None, False),
            prompt_appendix="",
        )
        violations = repo_maintainer.validate_changes(
            config,
            [
                {"status": "M", "path": "src/app.py"},
                {"status": "R", "old": "docs/old.md", "new": "src/new.py"},
            ],
        )
        self.assertIn("phase 1 blocks change: src/app.py", violations)
        self.assertIn("phase 1 blocks change: src/new.py", violations)

    def test_init_scaffold_creates_expected_files(self) -> None:
        repo = self.init_repo()
        result = repo_maintainer.init_scaffold(repo=repo, task_time="02:45", force=True)
        self.assertEqual(result["task_time"], "02:45")
        self.assertTrue((repo / ".devkit" / "repo-maintainer.toml").exists())
        self.assertTrue((repo / "MEMORY.md").exists())
        self.assertTrue((repo / ".devkit" / "bin" / "repo-maintainer.ps1").exists())
        self.assertTrue((repo / ".devkit" / "bin" / "repo-maintainer.sh").exists())
        self.assertTrue((repo / ".devkit" / "scheduler" / "windows" / "register-task.ps1").exists())
        loaded = repo_maintainer.load_config(repo / ".devkit" / "repo-maintainer.toml")
        self.assertEqual(loaded.phase, 1)
        self.assertEqual(loaded.git.base_branch, "main")

    def test_run_daily_creates_log_pr_and_auto_merge(self) -> None:
        repo = self.init_repo()
        codex_script = self.add_fake_codex()
        review_script = self.add_command_script("review-pass", 0)
        check_script = self.add_command_script("check-pass", 0)
        self.write_config(
            repo,
            codex_script=codex_script,
            phase=1,
            allowed_paths=["docs", "logs/skills", "reviews", ".devkit"],
            review_commands=[f'"{sys.executable.replace("\\\\", "/")}" "{review_script.as_posix()}"'],
            check_commands=[f'"{sys.executable.replace("\\\\", "/")}" "{check_script.as_posix()}"'],
            auto_merge=True,
        )
        fake_gh_dir, state_path, gh_path = self.add_fake_gh()
        original_path = os.environ.get("PATH", "")
        original_behavior = os.environ.get("FAKE_CODEX_BEHAVIOR")
        original_gh = os.environ.get("REPO_MAINTAINER_GH_PATH")
        os.environ["PATH"] = str(fake_gh_dir) + os.pathsep + original_path
        os.environ["FAKE_CODEX_BEHAVIOR"] = "docs"
        os.environ["REPO_MAINTAINER_GH_PATH"] = str(gh_path)
        try:
            result = repo_maintainer.run_maintainer(
                repo=repo,
                forced_lanes=["daily"],
                now=repo_maintainer.parse_datetime("2026-04-05T02:30:00+09:00"),
                keep_worktree=True,
            )
        finally:
            os.environ["PATH"] = original_path
            if original_gh is None:
                os.environ.pop("REPO_MAINTAINER_GH_PATH", None)
            else:
                os.environ["REPO_MAINTAINER_GH_PATH"] = original_gh
            if original_behavior is None:
                os.environ.pop("FAKE_CODEX_BEHAVIOR", None)
            else:
                os.environ["FAKE_CODEX_BEHAVIOR"] = original_behavior

        lane_result = result["results"][0]
        self.assertEqual(lane_result["status"], "ok")
        self.assertTrue(lane_result["auto_merge_triggered"])
        worktree = Path(lane_result["worktree"])
        self.assertTrue((worktree / "docs" / "nightly.md").exists())
        self.assertTrue((worktree / "logs" / "skills" / "2026" / "04" / "05.jsonl").exists())
        self.assertTrue((worktree / "reviews" / "daily" / "2026-04-05.md").exists())
        state = json.loads(state_path.read_text(encoding="utf-8"))
        self.assertEqual(len(state["create_calls"]), 1)
        self.assertEqual(len(state["merge_calls"]), 1)
        repo_maintainer.remove_temp_worktree(repo, worktree)

    def test_noop_run_does_not_create_review_artifacts_or_pr(self) -> None:
        repo = self.init_repo()
        codex_script = self.add_fake_codex()
        self.write_config(
            repo,
            codex_script=codex_script,
            phase=1,
            allowed_paths=["docs", "logs/skills", "reviews", ".devkit"],
            review_commands=[],
            check_commands=[],
            auto_merge=False,
        )
        fake_gh_dir, state_path, gh_path = self.add_fake_gh()
        original_path = os.environ.get("PATH", "")
        original_behavior = os.environ.get("FAKE_CODEX_BEHAVIOR")
        original_gh = os.environ.get("REPO_MAINTAINER_GH_PATH")
        os.environ["PATH"] = str(fake_gh_dir) + os.pathsep + original_path
        os.environ["FAKE_CODEX_BEHAVIOR"] = "noop"
        os.environ["REPO_MAINTAINER_GH_PATH"] = str(gh_path)
        try:
            result = repo_maintainer.run_maintainer(
                repo=repo,
                forced_lanes=["daily"],
                now=repo_maintainer.parse_datetime("2026-04-05T02:30:00+09:00"),
                keep_worktree=True,
            )
        finally:
            os.environ["PATH"] = original_path
            if original_gh is None:
                os.environ.pop("REPO_MAINTAINER_GH_PATH", None)
            else:
                os.environ["REPO_MAINTAINER_GH_PATH"] = original_gh
            if original_behavior is None:
                os.environ.pop("FAKE_CODEX_BEHAVIOR", None)
            else:
                os.environ["FAKE_CODEX_BEHAVIOR"] = original_behavior

        lane_result = result["results"][0]
        self.assertEqual(lane_result["status"], "noop")
        worktree = Path(lane_result["worktree"])
        self.assertFalse((worktree / "logs" / "skills").exists())
        self.assertFalse((worktree / "reviews").exists())
        self.assertFalse(state_path.exists())
        repo_maintainer.remove_temp_worktree(repo, worktree)

    def test_rerun_reuses_existing_pr_branch(self) -> None:
        repo = self.init_repo()
        codex_script = self.add_fake_codex()
        self.write_config(
            repo,
            codex_script=codex_script,
            phase=1,
            allowed_paths=["docs", "logs/skills", "reviews", ".devkit"],
            review_commands=[],
            check_commands=[],
            auto_merge=False,
        )
        fake_gh_dir, state_path, gh_path = self.add_fake_gh()
        original_path = os.environ.get("PATH", "")
        original_behavior = os.environ.get("FAKE_CODEX_BEHAVIOR")
        original_gh = os.environ.get("REPO_MAINTAINER_GH_PATH")
        os.environ["PATH"] = str(fake_gh_dir) + os.pathsep + original_path
        os.environ["FAKE_CODEX_BEHAVIOR"] = "docs"
        os.environ["REPO_MAINTAINER_GH_PATH"] = str(gh_path)
        try:
            first = repo_maintainer.run_maintainer(
                repo=repo,
                forced_lanes=["daily"],
                now=repo_maintainer.parse_datetime("2026-04-05T02:30:00+09:00"),
                keep_worktree=False,
            )
            second = repo_maintainer.run_maintainer(
                repo=repo,
                forced_lanes=["daily"],
                now=repo_maintainer.parse_datetime("2026-04-05T02:30:00+09:00"),
                keep_worktree=False,
            )
        finally:
            os.environ["PATH"] = original_path
            if original_gh is None:
                os.environ.pop("REPO_MAINTAINER_GH_PATH", None)
            else:
                os.environ["REPO_MAINTAINER_GH_PATH"] = original_gh
            if original_behavior is None:
                os.environ.pop("FAKE_CODEX_BEHAVIOR", None)
            else:
                os.environ["FAKE_CODEX_BEHAVIOR"] = original_behavior

        first_lane = first["results"][0]
        second_lane = second["results"][0]
        self.assertEqual(first_lane["status"], "ok")
        self.assertEqual(second_lane["status"], "ok")
        self.assertEqual(first_lane["pr_url"], second_lane["pr_url"])
        state = json.loads(state_path.read_text(encoding="utf-8"))
        self.assertEqual(len(state["create_calls"]), 1)

    def test_phase1_blocks_code_change(self) -> None:
        repo = self.init_repo()
        codex_script = self.add_fake_codex()
        self.write_config(
            repo,
            codex_script=codex_script,
            phase=1,
            allowed_paths=["src", "logs/skills", "reviews", ".devkit"],
            review_commands=[],
            check_commands=[],
        )
        fake_gh_dir, state_path, gh_path = self.add_fake_gh()
        original_path = os.environ.get("PATH", "")
        original_behavior = os.environ.get("FAKE_CODEX_BEHAVIOR")
        original_gh = os.environ.get("REPO_MAINTAINER_GH_PATH")
        os.environ["PATH"] = str(fake_gh_dir) + os.pathsep + original_path
        os.environ["FAKE_CODEX_BEHAVIOR"] = "code"
        os.environ["REPO_MAINTAINER_GH_PATH"] = str(gh_path)
        try:
            result = repo_maintainer.run_maintainer(
                repo=repo,
                forced_lanes=["daily"],
                now=repo_maintainer.parse_datetime("2026-04-05T02:30:00+09:00"),
                keep_worktree=True,
            )
        finally:
            os.environ["PATH"] = original_path
            if original_gh is None:
                os.environ.pop("REPO_MAINTAINER_GH_PATH", None)
            else:
                os.environ["REPO_MAINTAINER_GH_PATH"] = original_gh
            if original_behavior is None:
                os.environ.pop("FAKE_CODEX_BEHAVIOR", None)
            else:
                os.environ["FAKE_CODEX_BEHAVIOR"] = original_behavior

        lane_result = result["results"][0]
        self.assertEqual(lane_result["status"], "blocked")
        self.assertIn("phase 1 blocks change: src/app.py", lane_result["violations"])
        self.assertFalse(state_path.exists())
        repo_maintainer.remove_temp_worktree(repo, Path(lane_result["worktree"]))

    def test_phase2_and_phase3_allow_expected_changes(self) -> None:
        for phase, behavior, allowed in (
            (2, "config", [".github", "logs/skills", "reviews", ".devkit"]),
            (3, "code", ["src", "logs/skills", "reviews", ".devkit"]),
        ):
            with self.subTest(phase=phase, behavior=behavior):
                repo = self.init_repo()
                codex_script = self.add_fake_codex()
                self.write_config(
                    repo,
                    codex_script=codex_script,
                    phase=phase,
                    allowed_paths=allowed,
                    review_commands=[],
                    check_commands=[],
                    auto_merge=False,
                )
                fake_gh_dir, state_path, gh_path = self.add_fake_gh()
                original_path = os.environ.get("PATH", "")
                original_behavior = os.environ.get("FAKE_CODEX_BEHAVIOR")
                original_gh = os.environ.get("REPO_MAINTAINER_GH_PATH")
                os.environ["PATH"] = str(fake_gh_dir) + os.pathsep + original_path
                os.environ["FAKE_CODEX_BEHAVIOR"] = behavior
                os.environ["REPO_MAINTAINER_GH_PATH"] = str(gh_path)
                try:
                    result = repo_maintainer.run_maintainer(
                        repo=repo,
                        forced_lanes=["daily"],
                        now=repo_maintainer.parse_datetime("2026-04-05T02:30:00+09:00"),
                        keep_worktree=True,
                    )
                finally:
                    os.environ["PATH"] = original_path
                    if original_gh is None:
                        os.environ.pop("REPO_MAINTAINER_GH_PATH", None)
                    else:
                        os.environ["REPO_MAINTAINER_GH_PATH"] = original_gh
                    if original_behavior is None:
                        os.environ.pop("FAKE_CODEX_BEHAVIOR", None)
                    else:
                        os.environ["FAKE_CODEX_BEHAVIOR"] = original_behavior

                lane_result = result["results"][0]
                self.assertEqual(lane_result["status"], "ok")
                self.assertFalse(lane_result["auto_merge_triggered"])
                state = json.loads(state_path.read_text(encoding="utf-8"))
                self.assertEqual(len(state["create_calls"]), 1)
                repo_maintainer.remove_temp_worktree(repo, Path(lane_result["worktree"]))

if __name__ == "__main__":
    unittest.main()
