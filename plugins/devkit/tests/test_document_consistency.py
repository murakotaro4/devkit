"""ドキュメント間の整合性テスト."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
DISTRIBUTED_SKILLS = (
    "dig",
    "improve-skill",
    "setup",
    "refactor",
    "memory-review",
    "goal-prompt",
    "handoff",
    "backlog",
    "catch-up",
    "commit-push",
)
DELEGATING_SKILLS = ("dig", "improve-skill", "memory-review", "goal-prompt", "catch-up")
PLUGIN_DESCRIPTION_SURFACES = (
    "/dig",
    "skill 改善",
    "setup",
    "refactor",
    "memory-review",
    "goal-prompt",
    "handoff",
    "/catch-up",
    "commit-push",
)


def _read(relpath: str) -> str:
    return (REPO_ROOT / relpath).read_text(encoding="utf-8")


def _backtick_fence(line: str) -> tuple[int, str] | None:
    match = re.match(r"^(`{3,})(.*)$", line)
    if not match:
        return None
    return len(match.group(1)), match.group(2).strip()


def _line_patterns_in_blocks(
    lines: list[str], block_patterns: tuple[tuple[str, str, tuple[str, ...]], ...]
) -> dict[int, tuple[str, ...]]:
    allowed: dict[int, tuple[str, ...]] = {}
    end_pattern: str | None = None
    entry_patterns: tuple[str, ...] = ()
    for line_no, line in enumerate(lines, start=1):
        if end_pattern is not None:
            if re.fullmatch(end_pattern, line):
                end_pattern = None
                entry_patterns = ()
            else:
                allowed[line_no] = entry_patterns
            continue
        for start_pattern, candidate_end_pattern, candidate_entry_patterns in block_patterns:
            if re.fullmatch(start_pattern, line):
                end_pattern = candidate_end_pattern
                entry_patterns = candidate_entry_patterns
                break
    assert end_pattern is None, "旧 updater allowlist の構造ブロックが閉じていない"
    return allowed


def test_retired_update_devkit_mentions_are_allowlisted():
    retired_updater_name = "update-" + "devkit"
    retired_updater_pattern = re.escape(retired_updater_name)
    allowed_line_patterns = {
        "README.md": (
            rf"(?=.*{retired_updater_pattern})(?=.*(?:廃止|旧名称|残骸|prune|削除))",
        ),
        "plugins/devkit/scripts/README.md": (
            rf"(?=.*{retired_updater_pattern})(?=.*(?:廃止|旧名称|残骸|prune|削除))",
        ),
        "plugins/devkit/scripts/devkit-lib.ps1": (
            rf'^\s*foreach \(\$fileName in \$legacyLocalBinFileNames\) \{{$',
        ),
        "plugins/devkit/skills/setup/scripts/sync_updater.py": (
            rf'^LEGACY_CODEX_BIN_FILES = \("{retired_updater_pattern}\.sh", '
            rf'"{retired_updater_pattern}\.ps1", "{retired_updater_pattern}\.cmd"\)$',
            rf'^LEGACY_LOCAL_BIN_FILES = \("{retired_updater_pattern}", '
            rf'"{retired_updater_pattern}\.cmd"\)$',
        ),
        "plugins/devkit/tests/test_update_bootstrap.py": (
            rf'^\s*assert "{retired_updater_pattern}" not in managed_names$',
            rf'^\s*for name in \("{retired_updater_pattern}\.sh", '
            rf'"{retired_updater_pattern}\.ps1", "{retired_updater_pattern}\.cmd"\):$',
            rf'^\s*assert [\'\']"\$local_bin/{retired_updater_pattern}"[\'\'] in shell$',
            rf'^\s*assert [\'\']"\$local_bin/{retired_updater_pattern}\.cmd"[\'\'] in shell$',
            rf'^\s*assert [\'\']\(Join-Path \$localBin "{retired_updater_pattern}"\)'
            rf"[\'\'] in powershell$",
            rf'^\s*assert [\'\']\(Join-Path \$localBin "{retired_updater_pattern}\.cmd"\)'
            rf"[\'\'] in powershell$",
        ),
    }
    allowed_block_patterns = {
        "plugins/devkit/scripts/update-ccx.sh": (
            (
                r"\s*local -a legacy_updater_paths=\(",
                r"\s*\)",
                (
                    rf'\s*"\$codex_bin/{retired_updater_pattern}\.sh"',
                    rf'\s*"\$codex_bin/{retired_updater_pattern}\.ps1"',
                    rf'\s*"\$codex_bin/{retired_updater_pattern}\.cmd"',
                    rf'\s*"\$local_bin/{retired_updater_pattern}"',
                    rf'\s*"\$local_bin/{retired_updater_pattern}\.cmd"',
                ),
            ),
        ),
        "plugins/devkit/scripts/devkit-lib.sh": (
            (
                r"\s*local -a legacy_updater_paths=\(",
                r"\s*\)",
                (
                    rf'\s*"\$codex_bin/{retired_updater_pattern}\.sh"',
                    rf'\s*"\$codex_bin/{retired_updater_pattern}\.ps1"',
                    rf'\s*"\$codex_bin/{retired_updater_pattern}\.cmd"',
                    rf'\s*"\$user_home/\.local/bin/{retired_updater_pattern}"',
                    rf'\s*"\$user_home/\.local/bin/{retired_updater_pattern}\.cmd"',
                ),
            ),
        ),
        "plugins/devkit/scripts/devkit-lib.ps1": (
            (
                r"\s*\$legacyUpdaterPaths = @\(",
                r"\s*\)",
                (
                    rf'\s*\(Join-Path \$codexBin "{retired_updater_pattern}\.sh"\),',
                    rf'\s*\(Join-Path \$codexBin "{retired_updater_pattern}\.ps1"\),',
                    rf'\s*\(Join-Path \$codexBin "{retired_updater_pattern}\.cmd"\),',
                    rf'\s*\(Join-Path \$localBin "{retired_updater_pattern}"\),',
                    rf'\s*\(Join-Path \$localBin "{retired_updater_pattern}\.cmd"\)',
                ),
            ),
            (
                r"\s*\$legacyCodexBinFileNames = @\(",
                r"\s*\)",
                (
                    rf'\s*"{retired_updater_pattern}\.sh",',
                    rf'\s*"{retired_updater_pattern}\.ps1",',
                    rf'\s*"{retired_updater_pattern}\.cmd"',
                ),
            ),
            (
                r"\s*\$legacyLocalBinFileNames = @\(",
                r"\s*\)",
                (
                    rf'\s*"{retired_updater_pattern}",',
                    rf'\s*"{retired_updater_pattern}\.cmd"',
                ),
            ),
        ),
        "scripts/ci/windows-updater-smoke.ps1": (
            (
                r"\s*\$legacyCodexBinRemnantNames = @\(",
                r"\s*\)",
                (
                    rf'\s*"{retired_updater_pattern}\.sh",',
                    rf'\s*"{retired_updater_pattern}\.ps1",',
                    rf'\s*"{retired_updater_pattern}\.cmd"',
                ),
            ),
            (
                r"\s*\$legacyLocalBinRemnantNames = @\(",
                r"\s*\)",
                (
                    rf'\s*"{retired_updater_pattern}",',
                    rf'\s*"{retired_updater_pattern}\.cmd"',
                ),
            ),
        ),
    }
    tracked_and_untracked = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    offenders: list[str] = []
    for relpath in tracked_and_untracked:
        path = REPO_ROOT / relpath
        if not path.is_file():
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            continue
        allowed_block_line_patterns = _line_patterns_in_blocks(
            lines, allowed_block_patterns.get(relpath, ())
        )
        for line_no, line in enumerate(lines, start=1):
            if retired_updater_name not in line:
                continue
            block_line_patterns = allowed_block_line_patterns.get(line_no, ())
            if any(re.fullmatch(pattern, line) for pattern in block_line_patterns):
                continue
            patterns = allowed_line_patterns.get(relpath, ())
            if not any(re.search(pattern, line) for pattern in patterns):
                offenders.append(f"{relpath}:{line_no}:{line.strip()}")

    assert not offenders, "旧 updater 名の非許可言及が残っている:\n" + "\n".join(offenders)


# ── 1. CLAUDE.md が AGENTS.md を正本として参照している ─────────────


def test_claude_md_imports_agents_md():
    text = _read("CLAUDE.md")
    assert "@./AGENTS.md" in text, "CLAUDE.md が AGENTS.md を import していない"


# ── 2. AGENTS.md に repo 固有ルールが揃っている ────────────────────


def test_agents_md_core_rules():
    text = _read("AGENTS.md")
    assert "Conventional Commits" in text, "AGENTS.md にコミット規約がない"
    assert "Codex Exec 相談ルール" in text, "AGENTS.md に codex exec 相談ルールがない"
    assert "version" in text, "AGENTS.md に version bump ルールがない"
    for skill_name in DISTRIBUTED_SKILLS:
        assert skill_name in text, f"AGENTS.md に v7 の配布 skill がない: {skill_name}"


# ── 3. AGENTS.md に旧ワークフロー契約が残っていない ────────────────


def test_agents_md_no_legacy_contract():
    # 旧契約の個別トークンは check_legacy_migration.py が repo 全体で検査する。
    # ここでは AGENTS.md 固有の旧構造(埋め込み共有ワークフロー)の残存だけを見る。
    text = _read("AGENTS.md")
    for legacy in (
        "Workflow State Tokens",
        "7フェーズ必須フロー",
        "devkit:workflow:start",
    ):
        assert legacy not in text, f"AGENTS.md に旧ワークフロー契約が残っている: {legacy}"


# ── 4. marketplace description は plugin.json と一致している ───────


def test_marketplace_descriptions_match_plugin_json():
    plugin = json.loads(_read("plugins/devkit/.claude-plugin/plugin.json"))
    expected = plugin["description"]
    market = json.loads(_read(".claude-plugin/marketplace.json"))
    assert market["plugins"][0]["description"] == expected, "ルート marketplace の description が不一致"
    assert not (REPO_ROOT / "plugins/devkit/.claude-plugin/marketplace.json").exists(), (
        "重複 marketplace manifest が残っている"
    )


def test_distributed_skill_mentions_stay_in_sync():
    plugin = json.loads(_read("plugins/devkit/.claude-plugin/plugin.json"))
    documents = {
        "README.md": _read("README.md"),
        "plugins/devkit/scripts/README.md": _read("plugins/devkit/scripts/README.md"),
    }

    for doc_name, text in documents.items():
        for skill_name in DISTRIBUTED_SKILLS:
            assert skill_name in text, f"{doc_name} に配布 skill がない: {skill_name}"

    for surface in PLUGIN_DESCRIPTION_SURFACES:
        assert surface in plugin["description"], f"plugin description に配布 surface がない: {surface}"


# ── 5. pyproject の pythonpath は存在するディレクトリだけを指す ─────


def test_pyproject_pythonpath_entries_exist():
    text = _read("plugins/devkit/pyproject.toml")
    match = re.search(r"^pythonpath\s*=\s*\[(.*?)\]", text, re.MULTILINE)
    assert match, "pyproject.toml に pythonpath がない"
    entries = re.findall(r'"([^"]+)"', match.group(1))
    for entry in entries:
        assert (REPO_ROOT / "plugins" / "devkit" / entry).is_dir(), f"pythonpath が不存在: {entry}"


# ── 6. skill frontmatter name はディレクトリ名と一致する ─────────────


def test_skill_frontmatter_name_matches_directory():
    skills_dir = REPO_ROOT / "plugins" / "devkit" / "skills"
    for skill_path in sorted(skills_dir.glob("*/SKILL.md")):
        text = skill_path.read_text(encoding="utf-8")
        match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
        assert match, f"{skill_path} に frontmatter がない"
        name_match = re.search(r'^name:\s*"([^"]+)"\s*$', match.group(1), re.MULTILINE)
        assert name_match, f"{skill_path} に name がない"
        assert name_match.group(1) == skill_path.parent.name, f"{skill_path} の name とディレクトリ名が不一致"


# ── 7. skill Markdown のコードフェンスは壊れていない ───────────────


def test_skill_markdown_fences_are_balanced():
    for skill_name in DISTRIBUTED_SKILLS:
        relpath = f"plugins/devkit/skills/{skill_name}/SKILL.md"
        open_fence: tuple[int, int] | None = None

        for line_no, line in enumerate(_read(relpath).splitlines(), start=1):
            fence = _backtick_fence(line)
            if fence is None:
                continue

            fence_len, info = fence
            if open_fence is None:
                open_fence = (fence_len, line_no)
                continue

            open_len, open_line_no = open_fence
            if fence_len < open_len:
                continue
            if not info:
                open_fence = None
                continue

            raise AssertionError(
                f"{relpath}:{line_no} に未エスケープの入れ子コードフェンスがある: "
                f"{line!r} (外側開始: {open_line_no} 行目、{open_len} バッククォート)"
            )

        assert open_fence is None, f"{relpath}:{open_fence[1]} のコードフェンスが閉じていない"


# ── 8. AGENTS.md の codex exec stdin 閉鎖契約 ─────────────────────


def test_agents_codex_stdin_guard():
    text = _read("AGENTS.md")
    offenders = [
        line for line in text.splitlines()
        if "codex -a never exec" in line and "< /dev/null" not in line
    ]
    assert not offenders, f"stdin 閉鎖(< /dev/null)がない codex コマンド行: {offenders}"


# ── 9. Release Rules の正本は AGENTS.md、README は参照 ─────────────


def test_release_rules_canonical_in_agents_md():
    agents = _read("AGENTS.md")
    readme = _read("README.md")
    assert "この節が version 運用ルールの正本" in agents, "AGENTS.md に Release Rules の正本宣言がない"
    assert "正本は `AGENTS.md` の「Release Rules」" in readme, "README が Release Rules の正本を参照していない"
    for doc_name, text in (("AGENTS.md", agents), ("README.md", readme)):
        assert "以下なら push を block" in text, (
            f"{doc_name} の pre-push gate 文言が実装(compare_semver <= 0 で block)と不一致"
        )


# ── 10. スキル共通契約・採用基準の正本化と参照 ─────────────────────


def test_shared_skill_contract_canonical_and_referenced():
    agents = _read("AGENTS.md")
    assert "## スキル共通契約" in agents, "AGENTS.md にスキル共通契約の節がない"
    assert "## スキル採用基準" in agents, "AGENTS.md にスキル採用基準の節がない"

    for skill_name in DISTRIBUTED_SKILLS:
        text = _read(f"plugins/devkit/skills/{skill_name}/SKILL.md")
        assert "スキル共通契約" in text, f"{skill_name} の SKILL.md が共通契約を参照していない"


def test_delegating_skills_have_progress_visibility_contract():
    for skill_name in DELEGATING_SKILLS:
        text = _read(f"plugins/devkit/skills/{skill_name}/SKILL.md")
        assert "## 進捗可視化" in text, f"{skill_name} の SKILL.md に進捗可視化の見出しがない"
        assert "1 ジョブ = 1 タスク" in text, f"{skill_name} の SKILL.md にジョブのタスク化契約がない"
        assert "委譲・長時間ジョブの進捗可視化" in text, (
            f"{skill_name} の SKILL.md が AGENTS.md の進捗可視化契約を参照していない"
        )

        allowed_tools_match = re.search(r'allowed-tools:\s*\[(.*?)\]', text)
        assert allowed_tools_match, f"{skill_name} の SKILL.md に allowed-tools がない"
        allowed_tools = re.findall(r'"([^"]+)"', allowed_tools_match.group(1))
        for tool_name in ("TaskCreate", "TaskUpdate", "TaskOutput"):
            assert tool_name in allowed_tools, (
                f"{skill_name} の SKILL.md の allowed-tools に {tool_name} がない"
            )


def test_codex_model_pinned_to_current_generation():
    # モデルは gpt-5.6-sol に固定する。世代追従は catch-up + premises.json が担う。
    documents = ["AGENTS.md"] + [
        f"plugins/devkit/skills/{skill_name}/SKILL.md" for skill_name in DISTRIBUTED_SKILLS
    ]
    for relpath in documents:
        text = _read(relpath)
        offenders = [
            line for line in text.splitlines()
            if re.search(r"codex[^\n]*\s-m\s+(?!gpt-5\.6-sol\b)\S+", line, re.IGNORECASE)
            or "gpt-5.3-codex-spark" in line
        ]
        assert not offenders, f"{relpath} に gpt-5.6-sol 以外の codex モデル焼き込みがある: {offenders}"


def test_codex_model_and_effort_contract_stays_in_sync():
    documents = {
        "AGENTS.md": _read("AGENTS.md"),
        "plugins/devkit/skills/dig/SKILL.md": _read("plugins/devkit/skills/dig/SKILL.md"),
        "plugins/devkit/skills/goal-prompt/SKILL.md": _read(
            "plugins/devkit/skills/goal-prompt/SKILL.md"
        ),
    }
    for doc_name, text in documents.items():
        assert "gpt-5.6-sol" in text, f"{doc_name} に固定モデル(gpt-5.6-sol)の記載がない"
        assert "catch-up" in text and "premises.json" in text, (
            f"{doc_name} に世代追従(catch-up + premises.json)の記載がない"
        )
        assert "推薦既定" not in text, f"{doc_name} に旧モデル非固定契約が残っている"
        assert "Max は対応 surface の最深推論" in text
        assert "Ultra は並列オーケストレーション" in text
        concrete_efforts = set(
            re.findall(r'model_reasoning_effort="([^"<>]+)"', text)
        )
        assert concrete_efforts <= {"medium"}, (
            f"{doc_name} に medium 以外の effort が残っている: {concrete_efforts}"
        )


def test_dig_goal_prompt_switching_terms_stay_in_sync():
    documents = {
        "AGENTS.md": _read("AGENTS.md"),
        "README.md": _read("README.md"),
        "plugins/devkit/skills/dig/SKILL.md": _read("plugins/devkit/skills/dig/SKILL.md"),
        "plugins/devkit/skills/goal-prompt/SKILL.md": _read(
            "plugins/devkit/skills/goal-prompt/SKILL.md"
        ),
    }
    for doc_name, text in documents.items():
        assert "自律度" in text, f"{doc_name} に使い分け軸(自律度)がない"
        assert "ゴール化" in text, f"{doc_name} に dig 連携語(ゴール化)がない"
        assert "起動プロンプト" in text, f"{doc_name} に goal-prompt 境界語(起動プロンプト)がない"


def test_goal_prompt_auto_execution_contract_stays_in_sync():
    documents = {
        "AGENTS.md": _read("AGENTS.md"),
        "README.md": _read("README.md"),
        "plugins/devkit/skills/dig/SKILL.md": _read("plugins/devkit/skills/dig/SKILL.md"),
        "plugins/devkit/skills/goal-prompt/SKILL.md": _read(
            "plugins/devkit/skills/goal-prompt/SKILL.md"
        ),
    }
    for doc_name, text in documents.items():
        assert any(
            all(token in line for token in ("既定", "同一セッション", "自律実行", "完遂"))
            for line in text.splitlines()
        ), (
            f"{doc_name} に既定の同一セッション自律実行契約がない"
        )
        assert any(
            all(token in line for token in ("起動プロンプト提示", "例外形態"))
            for line in text.splitlines()
        ), (
            f"{doc_name} に起動プロンプト提示を例外形態へ限定する契約がない"
        )
        for retired in (
            "実行はユーザーの 1 アクションに分離",
            "作成側はゴールファイルを保存しないのが既定",
            "既定成果物は本文全文を含むインライン 1 ブロック",
            "起動プロンプトと回収手順を提示して終了",
            "成果物はレビュー済みの `/goal` 自己完結起動ブロック 1 個(既定)",
        ):
            assert retired not in text, f"{doc_name} に旧既定契約が残っている: {retired}"


def test_rebase_conflict_resolution_contract_stays_in_sync():
    agents = _read("AGENTS.md")
    heading = "### 統合時 rebase 衝突の標準解消手順"
    assert heading in agents, "AGENTS.md に rebase 衝突の標準解消手順がない"

    contract = agents.split(heading, 1)[1].split("\n## ", 1)[0]
    for keyword in ("追加のみ", "和集合", "削除", "停止", "git rebase --abort", "verify-full", "片側"):
        assert keyword in contract, f"rebase 衝突の標準解消手順に契約キーワードがない: {keyword}"

    dig = _read("plugins/devkit/skills/dig/SKILL.md")
    integration = dig.split("### 統合(step 9、終了条件達成後)", 1)[1].split("\n### ", 1)[0]
    assert "標準解消手順" in integration, "dig の統合手順が標準解消手順を参照していない"
    assert "git rebase --abort" in integration, "dig の統合手順に未知の衝突時の abort fallback がない"
