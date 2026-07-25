"""ドキュメント間の整合性テスト."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
DISTRIBUTED_SKILLS = (
    "dig",
    "goal-prompt",
    "improve-skill",
    "setup",
    "refactor",
    "memory-review",
    "handoff",
    "backlog",
    "catch-up",
    "commit-push",
    "repo-loop",
)
DELEGATING_SKILLS = ("dig", "improve-skill", "memory-review", "catch-up", "repo-loop")
LAYERED_OUTPUT_SKILLS = ("dig", "refactor", "backlog", "catch-up", "memory-review")
PLUGIN_DESCRIPTION_SURFACES = (
    "/dig",
    "/goal-prompt",
    "skill 改善",
    "setup",
    "refactor",
    "memory-review",
    "handoff",
    "/catch-up",
    "commit-push",
    "repo-loop",
)


def _read(relpath: str) -> str:
    return (REPO_ROOT / relpath).read_text(encoding="utf-8")


def _markdown_section(text: str, heading: str) -> str:
    heading_match = re.search(
        rf"^(?P<marks>#+) {re.escape(heading)}$",
        text,
        re.MULTILINE,
    )
    assert heading_match, f"見出しがない: {heading}"
    level = len(heading_match.group("marks"))
    section_start = heading_match.end()
    next_heading = re.search(
        rf"^#{{1,{level}}} ",
        text[section_start:],
        re.MULTILINE,
    )
    section_end = (
        section_start + next_heading.start()
        if next_heading
        else len(text)
    )
    return text[section_start:section_end]


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
            rf'^\s*"{retired_updater_pattern}\.sh",$',
            rf'^\s*"{retired_updater_pattern}\.ps1",$',
            rf'^\s*"{retired_updater_pattern}\.cmd",$',
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
                    rf'\s*"{retired_updater_pattern}\.cmd",?',
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


# ── 8. AGENTS.md / dig の非対話 CLI stdin 閉鎖契約 ───────────────


def test_agents_and_dig_noninteractive_stdin_guard():
    documents = {
        "AGENTS.md": _read("AGENTS.md"),
        "plugins/devkit/skills/dig/SKILL.md": _read("plugins/devkit/skills/dig/SKILL.md"),
    }
    offenders: list[str] = []
    for relpath, text in documents.items():
        for line in text.splitlines():
            runnable = (
                "codex -a never exec" in line
                or "$(cursor-agent create-chat" in line
                or 'cursor-agent -p --resume "' in line
            )
            if runnable and "< /dev/null" not in line:
                offenders.append(f"{relpath}:{line.strip()}")
    assert not offenders, f"stdin 閉鎖(< /dev/null)がない非対話コマンド行: {offenders}"


def test_bash_blocks_assign_every_shell_variable_they_use():
    """コマンド例の bash ブロックは、参照するシェル変数を同じブロック内で代入する。

    シェル変数はツール呼び出し間で失われるため、別ブロックでの代入に依存すると
    空文字へ展開して誤ったパスを対象にする。2026-07-25 の圧縮で setup が
    `$SKILL_DIR` / `$TARGET_REPO` の代入を落としていた(codex の diff レビューが
    [P2] として検出)。環境が与える変数だけ例外とする。
    """
    env_provided = {"TMPDIR", "HOME", "PATH", "PWD", "SHELL", "USER"}
    offenders: list[str] = []
    for path in sorted((REPO_ROOT / "plugins" / "devkit" / "skills").glob("*/SKILL.md")):
        text = path.read_text(encoding="utf-8")
        for block in re.findall(r"```bash\n(.*?)```", text, re.DOTALL):
            used = set(re.findall(r"\$\{?([A-Z][A-Z0-9_]*)\}?", block))
            assigned = set(
                re.findall(r"(?:^|[\s;&(])([A-Z][A-Z0-9_]*)=", block, re.MULTILINE)
            )
            missing = used - assigned - env_provided
            if missing:
                head = block.strip().splitlines()[0][:60]
                offenders.append(
                    f"{path.relative_to(REPO_ROOT)}: {sorted(missing)} ({head})"
                )
    assert not offenders, f"未代入のシェル変数を参照する bash ブロック: {offenders}"


def test_codex_review_scope_flag_and_prompt_are_not_combined():
    """`codex exec review` は scope フラグと positional PROMPT を併用できない。

    2026-07-25 に実測で確認（`error: the argument '--base <BRANCH>' cannot be used
    with '[PROMPT]'`。`--uncommitted` も同じ）。repo-loop がこの併用形を記載しており、
    そのまま実行すると必ず失敗していた。同じ逸脱を再発させないための検査。
    """
    offenders: list[str] = []
    for path in sorted(Path(REPO_ROOT).rglob("*.md")):
        relpath = str(path.relative_to(REPO_ROOT))
        if relpath.startswith((".git/", ".claude/", "docs/reviews/")):
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if "codex" not in line or " review " not in line:
                continue
            if "--base" not in line and "--uncommitted" not in line:
                continue
            after_scope = re.split(r"--base\s+\S+|--uncommitted", line, maxsplit=1)[-1]
            if '"' in after_scope.split("< /dev/null")[0]:
                offenders.append(f"{relpath}:{line.strip()}")
    assert not offenders, (
        "codex exec review に scope フラグと positional PROMPT を併用している"
        f"(実行時に必ず失敗する): {offenders}"
    )


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
    assert "各 SKILL.md は実行に必要な要点を自己完結で保持" in agents

    for skill_name in DISTRIBUTED_SKILLS:
        text = _read(f"plugins/devkit/skills/{skill_name}/SKILL.md")
        harness_heading = re.search(
            r"^## (?P<title>ハーネス(?:判定(?:と実行差分)?|・進捗))$",
            text,
            re.MULTILINE,
        )
        assert harness_heading, (
            f"{skill_name} の SKILL.md に自己完結したハーネス契約がない"
        )
        harness = _markdown_section(text, harness_heading.group("title"))
        harness_lines = harness.splitlines()
        assert any(
            "AskUserQuestion" in line
            and "Claude 親" in line
            and ("使える" in line or "使えれば" in line)
            for line in harness_lines
        ), f"{skill_name} の Claude 親判定が AskUserQuestion に束縛されていない"
        assert any(
            "spawn_agent" in line
            and "Codex 親" in line
            and ("なく" in line or "なければ" in line)
            for line in harness_lines
        ), f"{skill_name} の Codex 親判定が AskUserQuestion 不在に束縛されていない"
        assert "判定不能" in harness, f"{skill_name} に判定不能の分岐がない"
        if skill_name == "goal-prompt":
            assert "質問は Claude 親が AskUserQuestion、Codex 親 plan mode が `request_user_input`" in harness
        else:
            assert re.search(
                r"`request_user_input` は(?:ハーネス)?判定(?:キー)?に(?:使わない|しない)",
                harness,
            ), f"{skill_name} が request_user_input をハーネス判定から除外していない"


def test_delegating_skills_have_progress_visibility_contract():
    agents_progress = _markdown_section(_read("AGENTS.md"), "タスクと進捗")
    for canonical_term in ("継続時間", "推定原因"):
        assert canonical_term in agents_progress, (
            f"AGENTS.md の進捗正本に停滞報告の要素がない: {canonical_term}"
        )

    progress_headings = {
        "dig": "タスクと進捗",
        "improve-skill": "ハーネス判定",
        "memory-review": "ハーネス判定",
        "catch-up": "ハーネス・進捗",
        "repo-loop": "ハーネス判定",
    }
    positive_progress_terms = {
        "dig": "Codex 親は定期的に進捗を示す",
        "improve-skill": "Codex 親は待機中も進捗を示し",
        "memory-review": "Codex 親は待機中も進捗を示す",
        "catch-up": "Codex 親は `wait_agent` で黙って待たない",
        "repo-loop": "黙って待たず定期報告",
    }
    for skill_name in DELEGATING_SKILLS:
        text = _read(f"plugins/devkit/skills/{skill_name}/SKILL.md")
        progress = _markdown_section(text, progress_headings[skill_name])
        assert re.search(
            r"(?:1 ジョブ = 1 タスク|委譲ジョブはタスクリスト)",
            progress,
        ), f"{skill_name} の SKILL.md に委譲ジョブのタスク化契約がない"
        assert positive_progress_terms[skill_name] in progress, (
            f"{skill_name} の SKILL.md に Codex 親の肯定的な進捗提示契約がない"
        )
        assert "停滞" in progress, (
            f"{skill_name} の SKILL.md に停滞時の報告契約がない"
        )
        if skill_name in ("dig", "improve-skill", "memory-review"):
            for detailed_term in ("時間", "推定原因"):
                assert detailed_term in progress, (
                    f"{skill_name} の停滞報告契約に要素がない: {detailed_term}"
                )

        if skill_name in ("dig", "repo-loop"):
            frontmatter = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
            assert frontmatter
            assert "allowed-tools" not in frontmatter.group(1)
            continue

        allowed_tools_match = re.search(r'allowed-tools:\s*\[(.*?)\]', text)
        assert allowed_tools_match, f"{skill_name} の SKILL.md に allowed-tools がない"
        allowed_tools = re.findall(r'"([^"]+)"', allowed_tools_match.group(1))
        for tool_name in ("TaskCreate", "TaskUpdate", "TaskOutput"):
            assert tool_name in allowed_tools, (
                f"{skill_name} の SKILL.md の allowed-tools に {tool_name} がない"
            )


def test_layered_output_contract_is_canonical_and_referenced():
    agents = _read("AGENTS.md")
    assert "### 計画・レポートの 2 層提示" in agents, (
        "AGENTS.md に計画・レポートの 2 層提示契約がない"
    )

    layer_sections = {
        "dig": "2. 調査 + 計画(親)",
        "refactor": "3. 優先順位付け",
        "backlog": "4. ダッシュボード提示",
        "catch-up": "4. 更新計画と承認",
        "memory-review": "5. 監査レポート出力",
    }
    category_terms = {
        1: ("何を / なぜ",),
        2: ("判断してほしい点",),
        3: ("既定からの逸脱",),
        4: ("後戻りしにくい操作・外部影響",),
        5: ("backend",),
        6: ("検証", "green"),
        7: ("独立レビュー状態",),
    }
    sections = {
        "AGENTS.md": _markdown_section(agents, "計画・レポートの 2 層提示")
    }
    sections.update(
        {
            skill_name: _markdown_section(
                _read(f"plugins/devkit/skills/{skill_name}/SKILL.md"),
                heading,
            )
            for skill_name, heading in layer_sections.items()
        }
    )

    for doc_name, section in sections.items():
        category_lines = {
            int(number): body
            for number, body in re.findall(r"^([1-7])\. (.+)$", section, re.MULTILINE)
        }
        assert set(category_lines) == set(range(1, 8)), (
            f"{doc_name} の第 1 層カテゴリ番号が不完全: {set(category_lines)}"
        )
        for category_number, accepted_terms in category_terms.items():
            assert any(
                term in category_lines[category_number]
                for term in accepted_terms
            ), (
                f"{doc_name} の第 1 層カテゴリ {category_number} が正本ラベルと不一致: "
                f"{category_lines[category_number]}"
            )

    for skill_name in LAYERED_OUTPUT_SKILLS:
        section = sections[skill_name]
        assert "第 1 層" in section, f"{skill_name} に第 1 層の契約がない"
        assert "第 2 層" in section or "レポート全体は次の 11 見出し" in section, (
            f"{skill_name} に第 1 層より後段の詳細構造がない"
        )
        review_states = {
            state
            for state in ("実施済み(指摘 N 件反映)", "skip(理由)", "適用なし")
            if state in section
        }
        assert review_states == {
            "実施済み(指摘 N 件反映)",
            "skip(理由)",
            "適用なし",
        }, f"{skill_name} の独立レビュー状態 enum が不完全: {review_states}"


def test_layer1_size_target_and_completeness_priority():
    agents = _read("AGENTS.md")
    assert "字数と完全性が衝突した場合は完全性を優先する" in agents
    assert "見出し行を除く本文文字数" in agents
    assert "工程表形式" in agents
    assert "docs/reviews/2026-07-25-cognitive-load-metrics.md" in agents


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
        "plugins/devkit/skills/dig/SKILL.md": _read(
            "plugins/devkit/skills/dig/SKILL.md"
        ),
    }
    for doc_name, text in documents.items():
        assert "gpt-5.6-sol" in text, f"{doc_name} に固定モデル(gpt-5.6-sol)の記載がない"
        assert "catch-up" in text and "premises.json" in text, (
            f"{doc_name} に世代追従(catch-up + premises.json)の記載がない"
        )
        assert "推薦既定" not in text, f"{doc_name} に旧モデル非固定契約が残っている"
        concrete_efforts = set(
            re.findall(r'model_reasoning_effort="([^"<>]+)"', text)
        )
        assert concrete_efforts == {"medium"}, (
            f"{doc_name} に medium 以外の effort が残っている: {concrete_efforts}"
        )


def test_dig_default_completion_terms_stay_in_sync():
    documents = {
        "AGENTS.md": _read("AGENTS.md"),
        "README.md": _read("README.md"),
        "plugins/devkit/skills/dig/SKILL.md": _read(
            "plugins/devkit/skills/dig/SKILL.md"
        ),
    }
    for doc_name, text in documents.items():
        assert "既定は実装完遂" in text, f"{doc_name} に既定は実装完遂の記載がない"

    readme_without_migration_notice = re.sub(
        r"## Migration Notice\n.*?(?=\n## )",
        "",
        documents["README.md"],
        count=1,
        flags=re.DOTALL,
    )
    retired_check_documents = {
        "AGENTS.md": documents["AGENTS.md"],
        "README.md": readme_without_migration_notice,
        "plugins/devkit/skills/dig/SKILL.md": documents["plugins/devkit/skills/dig/SKILL.md"],
    }
    for doc_name, text in retired_check_documents.items():
        assert "現セッション自律実行" not in text, f"{doc_name} に旧実行形態名が残っている: 現セッション自律実行"
        assert "起動プロンプト提示" not in text, f"{doc_name} に旧実行形態名が残っている: 起動プロンプト提示"


def test_pr_merge_completion_contract_stays_in_sync():
    documents = {
        "AGENTS.md": _read("AGENTS.md"),
        "README.md": _read("README.md"),
        "plugins/devkit/skills/dig/SKILL.md": _read(
            "plugins/devkit/skills/dig/SKILL.md"
        ),
    }
    retired_contracts = (
        "merge は人間",
        "PR 提出まで",
        "PR 提出完了",
        "既定推奨は「直接統合」",
        "統合方法も 1 問で確認",
        "統合の明示回答がなければ",
        "commit 判断をユーザーへ戻す",
    )

    for doc_name, text in documents.items():
        assert "PR" in text, f"{doc_name} に PR 経路の記載がない"
        assert "CI green" in text, f"{doc_name} に CI green 判定の記載がない"
        assert "merge" in text, f"{doc_name} に PR merge 完遂の記載がない"
        assert re.search(
            r"(?:既定は PR(?: 経由| の提出| 提出)|PR 提出.*が既定)",
            text,
        ), (
            f"{doc_name} に PR 経路を既定とする契約がない"
        )
        for retired in retired_contracts:
            assert retired not in text, f"{doc_name} に旧 PR 統合契約が残っている: {retired}"

    dig = documents["plugins/devkit/skills/dig/SKILL.md"]
    integration = dig.split("### 9. 統合・後始末・完了報告", 1)[1].split(
        "\n## ", 1
    )[0]
    for invariant in (
        "同じ SHA に束縛された checks",
        "merge queue / auto-merge",
        "--match-head-commit",
        "--json state,mergedAt",
        "`MERGED`",
        "CI 赤・merge 失敗では PR を open のまま",
    ):
        assert invariant in integration, f"dig の PR 統合不変条件がない: {invariant}"
    assert "計画時に直接統合へ決める" in dig
    assert "計画した統合方法だけを実行する" in integration


def test_goal_prompt_save_contract_stays_in_sync():
    documents = {
        "AGENTS.md": _read("AGENTS.md"),
        "README.md": _read("README.md"),
    }
    for doc_name, text in documents.items():
        assert ".claude/goal-runs/" in text, f"{doc_name} に goal-prompt の保存先(.claude/goal-runs/)の記載がない"

    agents = documents["AGENTS.md"]
    agents_context = _markdown_section(agents, "Repo Context")
    for invariant in (
        ".claude/goal-runs/",
        "連番保存",
        "commit も premises.json 登録もしない",
    ):
        assert invariant in agents_context, (
            f"AGENTS.md の goal-prompt 高水準契約がない: {invariant}"
        )
    usage_heading = "## dig と goal-prompt の使い分け"
    assert usage_heading in agents, "AGENTS.md に dig と goal-prompt の使い分け節がない"

    readme = documents["README.md"]
    for invariant in ("上書きせず連番", "コード変更・commit / push・PR 作成はしない"):
        assert invariant in readme, f"README の goal-prompt 高水準契約がない: {invariant}"

    goal_prompt_skill = _read("plugins/devkit/skills/goal-prompt/SKILL.md")
    save_contract = goal_prompt_skill.split("## 保存契約", 1)[1].split("\n## ", 1)[0]
    for invariant in (
        ".claude/goal-runs/YYYY-MM-DD-<slug>-goal.md",
        "上書きせず",
        "YYYY-MM-DD-<slug>-2-goal.md",
        "commit せず",
        "premises.json` へ登録しない",
    ):
        assert invariant in save_contract, f"goal-prompt の保存契約がない: {invariant}"
    limit_contract = goal_prompt_skill.split("## 上限停止の自動算出", 1)[1].split(
        "\n## ", 1
    )[0]
    assert "明示値がある場合だけ上書きする" in limit_contract
    for scale in ("小規模", "標準", "大規模"):
        assert scale in limit_contract, f"goal-prompt の上限停止規模がない: {scale}"


def test_rebase_conflict_resolution_contract_stays_in_sync():
    agents = _read("AGENTS.md")
    heading = "### 統合時 rebase 衝突の標準解消手順"
    assert heading in agents, "AGENTS.md に rebase 衝突の標準解消手順がない"

    contract = agents.split(heading, 1)[1].split("\n## ", 1)[0]
    for keyword in ("追加のみ", "和集合", "削除", "停止", "git rebase --abort", "verify-full", "片側"):
        assert keyword in contract, f"rebase 衝突の標準解消手順に契約キーワードがない: {keyword}"

    dig = _read("plugins/devkit/skills/dig/SKILL.md")
    integration = dig.split("### 9. 統合・後始末・完了報告", 1)[1].split(
        "\n## ", 1
    )[0]
    assert "標準解消規則" in integration, "dig の統合手順が標準解消規則を参照していない"
    assert "conflict は abort して停止" in integration, (
        "dig の統合手順に未知の衝突時の abort fallback がない"
    )
