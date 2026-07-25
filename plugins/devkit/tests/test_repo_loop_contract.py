"""repo-loop スキルの不変条件を検査する."""

from __future__ import annotations

import json
import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SKILL_PATH = REPO_ROOT / "plugins/devkit/skills/repo-loop/SKILL.md"
OPENAI_YAML_PATH = REPO_ROOT / "plugins/devkit/skills/repo-loop/agents/openai.yaml"

EXPECTED_FRONTMATTER = """name: "repo-loop"
description: "手動・定期・イベント起点でリポジトリの目的と状態を調査し、価値が高く安全で検証可能な改善を1件だけ選び、実装・検証・独立レビューを経てDraft PRまたは提案Issueまで完遂する。『リポジトリを自動改善して』『定期メンテナンスして』『CI failureを直して』『/repo-loop』で起動"
argument-hint: "[objective or repo-loop/v1 trigger envelope]\""""


def _skill_text() -> str:
    return SKILL_PATH.read_text(encoding="utf-8")


def _frontmatter_and_body() -> tuple[str, str]:
    match = re.match(r"^---\n(.*?)\n---\n\n(.*)$", _skill_text(), re.DOTALL)
    assert match, "frontmatter が見つからない"
    return match.group(1), match.group(2)


def _json_blocks() -> list[dict[str, object]]:
    return [
        json.loads(block)
        for block in re.findall(r"```json\n(.*?)\n```", _skill_text(), re.DOTALL)
    ]


def test_immutable_metadata_and_heading():
    frontmatter, body = _frontmatter_and_body()
    assert frontmatter == EXPECTED_FRONTMATTER
    assert body.startswith("# /repo-loop - リポジトリ自律改善ループ\n")
    assert "allowed-tools" not in frontmatter


def test_agent_metadata_exists():
    assert OPENAI_YAML_PATH.is_file()
    assert "display_name" in OPENAI_YAML_PATH.read_text(encoding="utf-8")


def test_trigger_envelope_and_noninteractive_contract():
    envelope = _json_blocks()[0]
    assert envelope["schema"] == "repo-loop/v1"
    assert envelope["trigger"]["type"] == "manual | schedule | event"
    assert set(envelope) == {"schema", "trigger", "objective", "scope", "proposal_only"}
    text = _skill_text()
    assert {"manual", "schedule", "event"} <= set(
        re.findall(r"^\| `(\w+)` \|", text, re.MULTILINE)
    )
    # 非対話 trigger では質問しない。この契約が消えると、自律実行が
    # 誰も見ていない場所で確認待ちのまま止まる。汎用 check の対象外なので
    # ここで肯定形の禁止と、非対話判定の対象を保持する。
    assert "非対話実行では質問しない" in text
    assert "`schedule` / `event`" in text


def test_harness_detection_is_centralized():
    text = _skill_text()
    section = text.split("## ハーネス判定", 1)[1].split("## dig", 1)[0]
    for token in ("AskUserQuestion", "spawn_agent", "request_user_input"):
        assert token in section
    assert text.count("## ハーネス判定") == 1


def test_single_task_risk_and_exit_matrix():
    text = _skill_text()
    risk_rows = dict(
        re.findall(r"^\| (low|medium|high|none) \|.*?\| (.*?) \|$", text, re.MULTILINE)
    )
    assert set(risk_rows) == {"low", "medium", "high", "none"}
    assert "Draft PR" in risk_rows["low"]
    assert "Draft PR" in risk_rows["medium"]
    assert "提案 Issue" in risk_rows["high"]
    assert ".github/workflows/" in text
    assert "CI/config 変更" not in text


def test_outcomes_are_closed_enum_and_all_paths_record():
    result = _json_blocks()[1]
    assert result["outcome"].split(" | ") == [
        "noop",
        "draft_pr",
        "proposal",
        "blocked",
        "failed",
    ]
    assert result["risk"].split(" | ") == ["low", "medium", "high", "none"]
    text = _skill_text()
    assert re.search(r"\w+ -->\|候補なし\| R\[RECORD\]", text)
    assert "R --> S[DONE]" in text
    assert "G -->|2回目も未解消| X" in text
    assert "変更なしの正常系" in text


def test_scope_worktree_and_attempt_invariants():
    text = _skill_text()
    assert "git fetch <remote>" in text
    assert "<remote>/<default>" in text
    # event 起点実行では hook / CI wrapper の GIT_* が継承され、別 repo や別 index を
    # 操作しうる。2026-07-25 の圧縮でこの遮断が消えていた([P1])。
    for var in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"):
        assert var in text


def test_independent_review_and_downgrade_contract():
    text = _skill_text()
    assert "review --base <remote>/<default>" in text
    # review command は review_scope_without_prompt / stdin_closed /
    # codex_execution_shape / worktree_commands_pin_directory に統合。
    # レビューは専用 worktree 内で実行する。通常 checkout で走らせると
    # commit 済み branch ではなくそちらを対象にし、空 diff や無関係な diff を
    # レビューして Draft PR を出しうる。2026-07-25 の圧縮で消えていた([P1])。
    assert text.count('-C "<worktree>"') >= 2


def test_security_and_publication_guardrails():
    text = _skill_text()
    for required in (
        "untrusted input",
        "secret 検査",
        "staged diff",
        "private vulnerability reporting",
        "<!-- repo-loop-run:<run_key> -->",
    ):
        assert required in text
    for forbidden in (
        "merge・auto-merge・ready 化",
        "force push",
        "default branch への直接 push",
    ):
        assert forbidden in text


def test_duplicate_marker_is_checked_before_implementation():
    """marker 検索は publish 直前ではなく実装前に行う。

    2026-07-25 の圧縮で「実装前に」が「publish 前に」へ弱まり、重複 run が
    worktree 作成・編集・検証・commit まで走り切ってから noop になる状態だった
    (codex の diff レビューが [P2] として検出)。未 merge branch も残る。
    """
    text = _skill_text()
    assert "**実装前に**" in text
    assert "publish 前に open" not in text


def test_dedup_cleanup_and_non_goals():
    text = _skill_text()
    assert all(token in text for token in ("trigger.name", "trigger.url", "trigger.summary"))
    assert "git worktree remove" in text
    assert "`--force` は使わない" in text
    assert "`git branch -d`" in text
    assert "`-D` は使わない" in text
    for token in (
        "LangGraph",
        "Temporal",
        "状態の永続化",
        "repo_maintainer.py",
        ".devkit/repo-maintainer.toml",
    ):
        assert token in text
