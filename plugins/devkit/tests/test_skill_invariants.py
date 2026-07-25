"""配布ドキュメントを文言ではなくカテゴリ単位の不変条件で検査する。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


REPO_ROOT = Path(__file__).resolve().parents[3]
SKILL_GLOB = "plugins/devkit/skills/*/SKILL.md"
TARGET_PATHS = ("AGENTS.md",) + tuple(
    path.relative_to(REPO_ROOT).as_posix()
    for path in sorted(REPO_ROOT.glob(SKILL_GLOB))
)
Docs = dict[str, str]
CheckRun = Callable[[Docs], list[str]]
Mutation = Callable[[Docs], Docs]
TargetCounter = Callable[[Docs], int]


@dataclass(frozen=True)
class Check:
    run: CheckRun
    mutate: Mutation | None
    targets: TargetCounter
    category: str
    why: str
    # 1 つの check が複数の退行を防ぐ場合、退行ごとに mutation を足す。
    # 値の誤りだけを見て欠落を見逃す、といった片肺の検査を防ぐため。
    extra_mutations: tuple[Mutation, ...] = ()

    @property
    def all_mutations(self) -> tuple[Mutation, ...]:
        assert self.mutate is not None
        return (self.mutate, *self.extra_mutations)


def _copy(docs: Docs) -> Docs:
    return dict(docs)


def _replace_once(docs: Docs, path: str, old: str, new: str) -> Docs:
    mutated = _copy(docs)
    assert old in mutated[path], f"mutation の対象が実在しない: {path}: {old!r}"
    mutated[path] = mutated[path].replace(old, new, 1)
    assert mutated[path] != docs[path], f"mutation が空振りした: {path}"
    return mutated


def _swap_once(docs: Docs, path: str, first: str, second: str) -> Docs:
    mutated = _copy(docs)
    text = mutated[path]
    assert text.count(first) == 1, f"swap 対象が一意でない: {path}: {first!r}"
    assert text.count(second) == 1, f"swap 対象が一意でない: {path}: {second!r}"
    placeholder = "\0SKILL_INVARIANT_SWAP\0"
    assert placeholder not in text
    mutated[path] = (
        text.replace(first, placeholder, 1)
        .replace(second, first, 1)
        .replace(placeholder, second, 1)
    )
    assert mutated[path] != text
    return mutated


def _bash_blocks(text: str) -> list[str]:
    return re.findall(r"```(?:bash|sh|shell)\n(.*?)```", text, re.DOTALL)


def _inline_commands(text: str) -> list[str]:
    runnable = re.compile(
        r"^(?:[A-Z][A-Z0-9_]*=[^ ]+\s+)*(?:codex|cursor-agent|git|node|"
        r"python|uv|npx|pwsh|bash|sh)\b"
    )
    return [
        span
        for span in re.findall(r"`([^`\n]+)`", text)
        if runnable.match(span.strip())
    ]


def _join_continuations(block: str) -> list[str]:
    """行末 `\\` の継続を 1 コマンドへ畳む。

    物理行ごとに検査すると、フラグを次行へ折り返しただけの整形で
    「フラグがない」「stdin を閉じていない」と誤検出する。
    """
    joined: list[str] = []
    pending = ""
    for line in block.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.endswith("\\"):
            pending += stripped[:-1].rstrip() + " "
            continue
        joined.append((pending + stripped).strip())
        pending = ""
    if pending:
        joined.append(pending.strip())
    return joined


def _command_lines(docs: Docs, *, include_inline: bool = True) -> list[tuple[str, str]]:
    commands: list[tuple[str, str]] = []
    for path, text in docs.items():
        for block in _bash_blocks(text):
            commands.extend((path, line) for line in _join_continuations(block))
        if include_inline:
            commands.extend((path, command.strip()) for command in _inline_commands(text))
    return commands


# 値を取るフラグ。ここに無いフラグは boolean とみなす。
# 配布ドキュメントに現れる codex / cursor-agent のフラグから起こしている。
_VALUE_FLAGS = frozenset(
    {
        "-C",
        "-c",
        "-m",
        "--base",
        "--model",
        "--output-format",
        "--project",
        "--python",
        "--resume",
        "--sandbox",
        "--workspace",
    }
)


def _is_full_invocation(command: str) -> bool:
    """散文中の言及ではなく、実行できる完全な起動形か。

    inline span には 3 種類が混在する。

    - 完全な起動形（catch-up の review command）: 検査対象
    - 散文中の言及（dig の「`codex exec` の入れ子を選ばない」）: 対象外
    - 形の一部だけを示す短縮（repo-loop の `--sandbox read-only` まで）: 対象外

    判定には**必須フラグを使わない**。`-m` や `< /dev/null` の有無を membership の
    条件にすると、それらが一斉に落ちたコマンドが「起動形ではない」と分類されて
    検査から消え、まさに防ぎたい退行が素通りする。

    代わりに「subcommand の後に位置引数があるか、`review` subcommand を持つか」で
    判定する。どちらもフラグとは独立した構造の特徴。
    """
    tokens = command.split()
    if "review" in tokens:
        return True
    if "exec" not in tokens:
        return False
    rest = tokens[tokens.index("exec") + 1 :]
    expecting_value = False
    for token in rest:
        if token.startswith("-"):
            # boolean flag の次を値と誤認すると、`--json "<prompt>"` の
            # prompt が消えてコマンドごと検査対象から外れる。
            expecting_value = "=" not in token and token in _VALUE_FLAGS
            continue
        if not expecting_value:
            return True  # フラグに属さない位置引数 = prompt
        expecting_value = False
    return False


def _noninteractive_commands(docs: Docs) -> list[tuple[str, str]]:
    """fenced block と、完全な起動形の inline span を見る。

    catch-up のように実行形を inline の code span だけで示すスキルがあり、
    fenced block に限ると契約の一部が検査から外れる。
    """
    fenced = _command_lines(docs, include_inline=False)
    inline = [
        (path, command)
        for path, command in _command_lines(docs)
        if (path, command) not in fenced and _is_full_invocation(command)
    ]
    return [
        (path, command)
        for path, command in fenced + inline
        if re.search(r"\bcodex\b.*\bexec\b", command)
        or re.search(r"\bcursor-agent\s+-p\b", command)
        or re.search(r"\bcursor-agent\s+create-chat\b", command)
    ]


def check_stdin_closed(docs: Docs) -> list[str]:
    """非対話 CLI の fenced command は stdin を閉じる。"""
    return [
        f"{path}: stdin が閉じられていない: {command}"
        for path, command in _noninteractive_commands(docs)
        if "< /dev/null" not in command
    ]


def targets_stdin_closed(docs: Docs) -> int:
    return len(_noninteractive_commands(docs))


def mutate_stdin_closed(docs: Docs) -> Docs:
    path = "AGENTS.md"
    old = (
        'codex -a never exec -m gpt-5.6-sol -c model_reasoning_effort="medium" '
        '"<内容>" < /dev/null'
    )
    return _replace_once(docs, path, old, old.removesuffix(" < /dev/null"))


def _codex_commands(docs: Docs) -> list[tuple[str, str]]:
    """fenced block と、完全な起動形の inline span（catch-up が該当）。"""
    fenced = _command_lines(docs, include_inline=False)
    inline = [
        (path, command)
        for path, command in _command_lines(docs)
        if (path, command) not in fenced and _is_full_invocation(command)
    ]
    return [
        (path, command)
        for path, command in fenced + inline
        # `FOO=x codex exec ...` のような環境変数前置も対象にする。
        # 前置を足すだけで model / effort / approval の検査が外れてしまう。
        if re.search(r"(?:^|&&\s*)(?:[A-Za-z_][A-Za-z0-9_]*=\S*\s+)*codex\s", command)
    ]


def check_codex_execution_shape(docs: Docs) -> list[str]:
    """codex command の approval、model、effort を検査する。

    値の誤りだけでなく**欠落**も拒否する。値だけを見ると、フラグごと消えた
    ときに正規表現が何も拾わず「問題なし」になり、固定契約が空洞化する。
    """
    problems: list[str] = []
    for path, command in _codex_commands(docs):
        if not re.search(r"(?:^|\s)-a\s+never(?:\s|$)", command):
            problems.append(f"{path}: codex に -a never がない: {command}")
        model = re.search(r"(?:^|\s)-m\s+(\S+)", command)
        if model is None:
            problems.append(f"{path}: codex に -m の指定がない: {command}")
        elif model.group(1) != "gpt-5.6-sol":
            problems.append(f"{path}: codex model が不正: {model.group(1)}")
        effort = re.search(r'model_reasoning_effort="([^"]+)"', command)
        if effort is None:
            problems.append(f"{path}: codex に model_reasoning_effort の指定がない: {command}")
        elif effort.group(1) != "medium":
            problems.append(f"{path}: codex effort が不正: {effort.group(1)}")
    return problems


def targets_codex_execution_shape(docs: Docs) -> int:
    return len(_codex_commands(docs))


def mutate_codex_execution_shape(docs: Docs) -> Docs:
    path = "AGENTS.md"
    return _replace_once(docs, path, "codex -a never exec", "codex exec")


def mutate_codex_execution_shape_drops_model(docs: Docs) -> Docs:
    """`-m` ごと落ちた場合（値の誤りではなく欠落）。"""
    return _replace_once(docs, "AGENTS.md", "exec -m gpt-5.6-sol -c", "exec -c")


def mutate_codex_execution_shape_drops_effort(docs: Docs) -> Docs:
    """effort 指定ごと落ちた場合。"""
    return _replace_once(
        docs, "AGENTS.md", ' -c model_reasoning_effort="medium"', ""
    )


def _scoped_review_commands(docs: Docs) -> list[tuple[str, str]]:
    return [
        (path, command)
        for path, command in _command_lines(docs)
        if "codex" in command
        and " review " in command
        and ("--base" in command or "--uncommitted" in command)
    ]


def check_review_scope_without_prompt(docs: Docs) -> list[str]:
    """codex review は scope flag と positional prompt を併用しない。"""
    problems: list[str] = []
    for path, command in _scoped_review_commands(docs):
        # scope flag の後ろだけを見ると `review "<prompt>" --base main` のように
        # prompt を前に置くだけで検査を回避できる。review 以降の引数列全体を見る。
        # `cd <worktree> && codex ... review ...` のように前段があるため、
        # 先頭 segment ではなく review を含む segment を選ぶ。
        segments = re.split(r"\s*(?:&&|\|\||[|;])\s*", command)
        segment = next(
            (part for part in segments if "review" in part.split()), segments[0]
        )
        # リダイレクト演算子は独立したトークンとして書かれる（`< /dev/null`、`2>&1`）。
        # 演算子の直後に空白を要求しないと、`<remote>/<default>` のような
        # placeholder をリダイレクトと誤認して引数ごと消してしまう。
        without_redirects = re.sub(
            r"(?:^|\s)\d*(?:>>?|<)(?:\s+\S+|&\d+)", " ", segment
        )
        tokens = without_redirects.split()
        if "review" not in tokens:
            continue
        rest = tokens[tokens.index("review") + 1 :]
        expecting_value = False
        for token in rest:
            if token.startswith("-"):
                expecting_value = "=" not in token and token in _VALUE_FLAGS
                continue
            if expecting_value:
                expecting_value = False
                continue
            problems.append(f"{path}: review scope と prompt を併用: {command}")
            break
    return problems


def targets_review_scope_without_prompt(docs: Docs) -> int:
    return len(_scoped_review_commands(docs))


def mutate_review_scope_without_prompt(docs: Docs) -> Docs:
    path = "plugins/devkit/skills/repo-loop/SKILL.md"
    old = "review --base <remote>/<default> < /dev/null"
    new = 'review --base <remote>/<default> "<レビュー依頼>" < /dev/null'
    return _replace_once(docs, path, old, new)


ENV_PROVIDED = {
    "ARGUMENTS",
    "HOME",
    "PATH",
    "PWD",
    "SHELL",
    "TMPDIR",
    "USER",
    "USERPROFILE",
}
RUNNABLE_INLINE = re.compile(
    r"^(node|python|uv|codex|cursor-agent|git|npx|pwsh|bash|sh)\b"
)


def _variable_blocks(docs: Docs) -> list[tuple[str, str]]:
    blocks: list[tuple[str, str]] = []
    for path, text in docs.items():
        blocks.extend((path, block) for block in _bash_blocks(text))
        blocks.extend(
            (path, span)
            for span in re.findall(r"`([^`\n]+)`", text)
            if "$" in span and RUNNABLE_INLINE.match(span)
        )
    return blocks


def check_shell_variables_assigned(docs: Docs) -> list[str]:
    """command block が使う shell 変数は同じ block 内で代入する。"""
    problems: list[str] = []
    for path, block in _variable_blocks(docs):
        # shell 変数は case-sensitive で小文字も正当。大文字だけを見ていると
        # 変数名を小文字へ rename するだけで未代入の検査が外れる。
        used = set(re.findall(r"\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?", block))
        # 代入は「最初の使用より前」でなければ意味がない。block 内のどこかに
        # 代入があればよい、とすると使用後に代入する例が通ってしまう。
        assigned = set()
        for match in re.finditer(
            r"(?:^|[\s;&(])([A-Za-z_][A-Za-z0-9_]*)=", block, re.MULTILINE
        ):
            name = match.group(1)
            first_use = re.search(rf"\$\{{?{name}\}}?", block)
            if first_use is None or match.start() < first_use.start():
                assigned.add(name)
        missing = used - assigned - ENV_PROVIDED
        if missing:
            head = block.strip().splitlines()[0][:60]
            problems.append(f"{path}: 未代入 {sorted(missing)} ({head})")
    return problems


def targets_shell_variables_assigned(docs: Docs) -> int:
    return len(_variable_blocks(docs))


def mutate_shell_variables_assigned(docs: Docs) -> Docs:
    path = "plugins/devkit/skills/setup/SKILL.md"
    return _replace_once(
        docs,
        path,
        'SKILL_DIR="<この SKILL.md があるディレクトリの絶対パス>"\n'
        'TARGET_REPO="<対象リポジトリの絶対パス>"\n'
        'uv run --no-project --python ">=3.10" python "$SKILL_DIR/scripts/<script>"',
        'TARGET_REPO="<対象リポジトリの絶対パス>"\n'
        'uv run --no-project --python ">=3.10" python "$SKILL_DIR/scripts/<script>"',
    )


def _shell_surfaces(docs: Docs) -> list[tuple[str, str]]:
    return [
        (path, block)
        for path, text in docs.items()
        for block in _bash_blocks(text)
    ]


def check_no_broad_git_add(docs: Docs) -> list[str]:
    """実行例に broad git add を許さない。"""
    problems: list[str] = []
    for path, block in _shell_surfaces(docs):
        # 行末 `\` で `git add \` / `.` と折り返すと物理行では検出できない。
        for line in _join_continuations(block):
            # `&&` だけでなく `;` `||` `|` の後ろも見る。区切りを変えるだけで
            # 禁止しているはずの broad staging が素通りしてしまう。
            if re.search(
                r"(?:^|&&|\|\||[|;]|\()\s*git\s+add\s+(?:\.|-A)(?:\s|$)", line
            ):
                problems.append(f"{path}: broad git add: {line}")
    return problems


def targets_no_broad_git_add(docs: Docs) -> int:
    return len(_shell_surfaces(docs))


def mutate_no_broad_git_add(docs: Docs) -> Docs:
    path = "plugins/devkit/skills/dig/SKILL.md"
    old = "```bash\ncodex -a never exec --sandbox read-only"
    new = "```bash\ngit add .\ncodex -a never exec --sandbox read-only"
    return _replace_once(docs, path, old, new)


def _is_scoped_review(command: str) -> bool:
    """scope 付き review command。`--base` と `--uncommitted` の両方を見る。

    片方だけを見ると、scope を切り替えたときに worktree 固定の検査から
    黙って外れ、通常 checkout をレビューする退行が素通りする。
    """
    return " review " in command and (
        "--base" in command or "--uncommitted" in command
    )


def _remote_delete_commands(docs: Docs) -> list[tuple[str, str]]:
    """削除 refspec（source が空の `:refs/heads/...`）を持つ push だけを拾う。

    `HEAD:refs/heads/topic` のような通常の明示 push を削除と誤認して
    lease を要求すると、正しいコマンドを書けなくなる。
    """
    return [
        (path, command)
        for path, command in _command_lines(docs)
        if re.search(r"\bgit\s+push\b.*\s:refs/heads/", command)
    ]


def check_remote_delete_has_lease(docs: Docs) -> list[str]:
    """remote branch delete は**削除対象と同じ ref** に lease を束縛する。

    `--force-with-lease=` の有無だけを見ると、無関係な ref への lease
    （`--force-with-lease=refs/heads/other:<sha> ... :refs/heads/<branch>`）
    を通してしまう。それでは削除対象が並行 push から守られず、
    この不変条件が置き換えた失敗そのものが素通りする。
    """
    problems: list[str] = []
    for path, command in _remote_delete_commands(docs):
        deleted = re.search(r"\s:(refs/heads/\S+)", command)
        lease = re.search(r"--force-with-lease=(refs/heads/[^:\s]+):", command)
        if lease is None:
            problems.append(f"{path}: lease なし remote delete: {command}")
        elif deleted is not None and lease.group(1) != deleted.group(1):
            problems.append(
                f"{path}: lease の ref が削除対象と一致しない "
                f"(lease={lease.group(1)} delete={deleted.group(1)}): {command}"
            )
    return problems


def targets_remote_delete_has_lease(docs: Docs) -> int:
    return len(_remote_delete_commands(docs))


def mutate_remote_delete_has_lease(docs: Docs) -> Docs:
    path = "plugins/devkit/skills/dig/SKILL.md"
    old = (
        "git push --force-with-lease=refs/heads/<branch>:<検証済みSHA> "
        "origin :refs/heads/<branch>"
    )
    new = "git push origin :refs/heads/<branch>"
    return _replace_once(docs, path, old, new)


def mutate_remote_delete_lease_targets_other_ref(docs: Docs) -> Docs:
    """lease はあるが束縛先が削除対象と違う場合（無関係な ref への lease）。"""
    path = "plugins/devkit/skills/dig/SKILL.md"
    old = "--force-with-lease=refs/heads/<branch>:<検証済みSHA>"
    new = "--force-with-lease=refs/heads/<other>:<検証済みSHA>"
    return _replace_once(docs, path, old, new)


def _worktree_commands(docs: Docs) -> list[tuple[str, str]]:
    commands: list[tuple[str, str]] = []
    for path, command in _command_lines(docs):
        if path == "plugins/devkit/skills/dig/SKILL.md":
            relevant = (
                _is_scoped_review(command)
                or "--sandbox workspace-write" in command
                or re.search(r"\bcursor-agent\s+-p\b", command)
            )
        elif path == "plugins/devkit/skills/repo-loop/SKILL.md":
            relevant = (
                _is_scoped_review(command)
                or (
                    re.search(r"\bcodex\b", command)
                    and "--sandbox read-only" in command
                )
            )
        else:
            relevant = False
        if relevant:
            commands.append((path, command))
    return commands


def _delegated_segment(command: str) -> str:
    """複合行から codex / cursor-agent の呼び出し部分だけを取り出す。

    `git -C "<worktree>" status && codex ... review --base main` のような行では、
    無関係な git の -C を見て「worktree に固定されている」と誤認しうる。
    誤った directory での review はまさにこの不変条件が防ぐ失敗なので、
    対象コマンド自身のフラグだけを見る。
    """
    segments = re.split(r"\s*(?:&&|\|\||[|;])\s*", command)
    for segment in segments:
        if re.match(r"^(?:[A-Z][A-Z0-9_]*=\S+\s+)*(?:codex|cursor-agent)\b", segment):
            return segment
    return command


def check_worktree_commands_pin_directory(docs: Docs) -> list[str]:
    """worktree 委譲・review command は**専用 worktree**を実行 directory に指定する。

    任意の非オプション引数を許すと `-C "."` や `-C "<main-checkout>"` でも通り、
    通常 checkout に対して review が走って空 diff を「指摘なし」と誤報する。
    指す先が worktree であることまで要求する。
    """
    pinned = re.compile(
        r"(?:^|\s)(?:-C|--workspace)\s+(?:\"([^\"]+)\"|'([^']+)'|((?!-)\S+))"
    )
    problems: list[str] = []
    for path, command in _worktree_commands(docs):
        match = pinned.search(_delegated_segment(command))
        if match is None:
            problems.append(f"{path}: worktree directory 指定なし: {command}")
            continue
        target = next(group for group in match.groups() if group is not None)
        if "worktree" not in target and not target.startswith("$"):
            problems.append(
                f"{path}: 指定先が worktree でない ({target}): {command}"
            )
    return problems


def targets_worktree_commands_pin_directory(docs: Docs) -> int:
    return len(_worktree_commands(docs))


def mutate_worktree_commands_pin_directory(docs: Docs) -> Docs:
    path = "plugins/devkit/skills/repo-loop/SKILL.md"
    return _replace_once(
        docs,
        path,
        'codex -a never exec -C "<worktree>" -m',
        "codex -a never exec -m",
    )


def _skill_docs(docs: Docs) -> list[tuple[str, str]]:
    return [
        (path, text)
        for path, text in docs.items()
        if path.startswith("plugins/devkit/skills/")
    ]


def check_frontmatter_name_matches_directory(docs: Docs) -> list[str]:
    """全 SKILL.md の frontmatter name は親 directory 名と一致する。"""
    problems: list[str] = []
    for path, text in _skill_docs(docs):
        frontmatter = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
        if not frontmatter:
            problems.append(f"{path}: frontmatter がない")
            continue
        name = re.search(
            r'^name:\s*["\']?([^"\'\n]+)["\']?\s*$',
            frontmatter.group(1),
            re.MULTILINE,
        )
        expected = Path(path).parent.name
        if not name or name.group(1) != expected:
            actual = name.group(1) if name else "<missing>"
            problems.append(f"{path}: name={actual!r}, expected={expected!r}")
    return problems


def targets_frontmatter_name_matches_directory(docs: Docs) -> int:
    return len(_skill_docs(docs))


def mutate_frontmatter_name_matches_directory(docs: Docs) -> Docs:
    path = "plugins/devkit/skills/backlog/SKILL.md"
    return _replace_once(docs, path, 'name: "backlog"', 'name: "wrong-name"')


ENUM_TABLES: dict[tuple[str, ...], set[str]] = {
    ("未知", "影響", "扱い"): {"質問する", "仮定で進める", "確定済み"},
    ("trigger", "対話", "主な証拠", "branch 名"): {"manual", "schedule", "event"},
    ("risk", "例", "実装", "出口"): {"low", "medium", "high", "none"},
    ("outcome", "意味"): {"noop", "draft_pr", "proposal", "blocked", "failed"},
}
ENUM_COLUMN = {
    ("未知", "影響", "扱い"): "扱い",
    ("trigger", "対話", "主な証拠", "branch 名"): "trigger",
    ("risk", "例", "実装", "出口"): "risk",
    ("outcome", "意味"): "outcome",
}


def _cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _enum_cells(docs: Docs) -> list[tuple[str, tuple[str, ...], str]]:
    found: list[tuple[str, tuple[str, ...], str]] = []
    for path, text in docs.items():
        lines = text.splitlines()
        for index, line in enumerate(lines):
            if not line.startswith("|"):
                continue
            header = tuple(_cells(line))
            if header not in ENUM_TABLES or index + 1 >= len(lines):
                continue
            column = header.index(ENUM_COLUMN[header])
            for row in lines[index + 2 :]:
                if not row.startswith("|"):
                    break
                row_cells = _cells(row)
                if len(row_cells) <= column:
                    found.append((path, header, "<missing-cell>"))
                    continue
                value = row_cells[column].strip("`")
                for token in re.split(r"\s*/\s*", value):
                    found.append((path, header, token.strip()))
    return found


def check_enum_table_cells(docs: Docs) -> list[str]:
    """既知 enum table の対象 cell は許容値集合内に収める。"""
    return [
        f"{path}: {header} に未知の enum 値 {value!r}"
        for path, header, value in _enum_cells(docs)
        if value not in ENUM_TABLES[header]
    ]


def targets_enum_table_cells(docs: Docs) -> int:
    return len(_enum_cells(docs))


def mutate_enum_table_cells(docs: Docs) -> Docs:
    path = "plugins/devkit/skills/repo-loop/SKILL.md"
    return _replace_once(docs, path, "| `manual` |", "| `unexpected` |")


def _docs_with_order_markers(
    docs: Docs, before: re.Pattern[str], after: re.Pattern[str]
) -> list[tuple[str, re.Match[str], re.Match[str]]]:
    found = []
    for path, text in docs.items():
        before_match = before.search(text)
        after_match = after.search(text)
        if before_match and after_match:
            found.append((path, before_match, after_match))
    return found


COMMIT_MARKER = re.compile(r"^#### 節目 commit$", re.MULTILINE)
REVIEW_MARKER = re.compile(r"^### \d+\. 自レビューと独立 diff レビュー$", re.MULTILINE)


def check_commit_before_independent_review(docs: Docs) -> list[str]:
    """節目 commit の工程は独立 diff review より前に置き、実際に commit を指示する。

    見出しの順序だけを見ると、節の中身が消えても「commit しない」に反転しても
    通ってしまう。`review --base` が空 diff を見て「指摘なし」と誤報する退行は
    まさにそれなので、肯定形の commit 指示が review より前にあることまで見る。
    """
    problems: list[str] = []
    for path, commit, review in _docs_with_order_markers(
        docs, COMMIT_MARKER, REVIEW_MARKER
    ):
        if commit.start() >= review.start():
            problems.append(f"{path}: 節目 commit が独立 review より後")
            continue
        body = docs[path][commit.end() : review.start()]
        if not re.search(r"(?<!しない。)commit する", body):
            problems.append(f"{path}: review 前に commit を指示する記述がない")
        if re.search(r"(?:親|節目)[^。\n]{0,20}commit しない", body):
            problems.append(f"{path}: 節目 commit の指示が否定されている")
    return problems


def targets_commit_before_independent_review(docs: Docs) -> int:
    return len(_docs_with_order_markers(docs, COMMIT_MARKER, REVIEW_MARKER))


def mutate_commit_before_independent_review(docs: Docs) -> Docs:
    path = "plugins/devkit/skills/dig/SKILL.md"
    return _swap_once(
        docs,
        path,
        "#### 節目 commit",
        "### 7. 自レビューと独立 diff レビュー",
    )


APPROVAL_MARKER = re.compile(r"^### \d+\. 計画承認$", re.MULTILINE)
IMPLEMENTATION_MARKER = re.compile(
    r"^### \d+\. worktree 作成と実装委譲$", re.MULTILINE
)


def check_approval_before_implementation(docs: Docs) -> list[str]:
    """計画承認は実装委譲より前に置き、承認が実装の条件だと明記する。

    見出しの順序だけを見ると、承認節が残ったまま本文が「承認なしでも実装してよい」
    に変わっても通る。承認境界の退行を検出するには、承認と write_scope 有効化を
    結ぶ肯定形の記述まで見る必要がある。
    """
    problems: list[str] = []
    for path, approval, implementation in _docs_with_order_markers(
        docs, APPROVAL_MARKER, IMPLEMENTATION_MARKER
    ):
        if approval.start() >= implementation.start():
            problems.append(f"{path}: 計画承認が実装委譲より後")
            continue
        body = docs[path][approval.end() : implementation.start()]
        if "明示承認" not in body:
            problems.append(f"{path}: 承認節に明示承認の要求がない")
        if not re.search(r"承認後だけ[^。\n]*write_scope[^。\n]*有効", body):
            problems.append(f"{path}: 承認と write_scope 有効化が結ばれていない")
        if re.search(r"承認(?:なし|前)[^。\n]{0,20}(?:実装してよい|進んでよい)", body):
            problems.append(f"{path}: 承認境界が否定されている")
    return problems


def targets_approval_before_implementation(docs: Docs) -> int:
    return len(
        _docs_with_order_markers(docs, APPROVAL_MARKER, IMPLEMENTATION_MARKER)
    )


def mutate_approval_before_implementation(docs: Docs) -> Docs:
    path = "plugins/devkit/skills/dig/SKILL.md"
    return _swap_once(
        docs,
        path,
        "### 5. 計画承認",
        "### 6. worktree 作成と実装委譲",
    )


CI_MERGE_SURFACES = {
    "AGENTS.md": ("## Workflow", "## 並行開発と worktree"),
    "plugins/devkit/skills/dig/SKILL.md": (
        "### 9. 統合・後始末・完了報告",
        "## goal-prompt への引き継ぎ",
    ),
}


def _ci_merge_sections(docs: Docs) -> list[tuple[str, str]]:
    sections: list[tuple[str, str]] = []
    for path, (start_marker, end_marker) in CI_MERGE_SURFACES.items():
        text = docs.get(path, "")
        start = text.find(start_marker)
        end = text.find(end_marker, start + len(start_marker)) if start >= 0 else -1
        if start < 0 or end < 0:
            sections.append((path, ""))
        else:
            sections.append((path, text[start:end]))
    return sections


def check_ci_green_before_merge(docs: Docs) -> list[str]:
    """同じ workflow statement では CI green を merge より先に確認する。"""
    problems: list[str] = []
    for path, section in _ci_merge_sections(docs):
        ci = re.search(r"CI (?:green|待機.*?green 判定)", section, re.DOTALL)
        merge = re.search(r"\bmerge\b", section)
        # 順序だけを見ると「CI green を確認しないで merge」のような否定形が
        # 通ってしまう。安全契約の反転を green のままにしない。
        negated = re.search(
            r"CI green[^。\n]{0,20}?(?:確認せず|確認しないで|待たずに|スキップ|無視)", section
        )
        if negated:
            problems.append(f"{path}: CI green の要求が否定されている: {negated.group(0)}")
        elif not ci:
            problems.append(f"{path}: CI green 確認がない")
        elif not merge:
            problems.append(f"{path}: merge 工程がない")
        elif ci.start() >= merge.start():
            problems.append(f"{path}: merge が CI green より前")
    return problems


def targets_ci_green_before_merge(docs: Docs) -> int:
    return len(_ci_merge_sections(docs))


def mutate_ci_green_before_merge(docs: Docs) -> Docs:
    path = "AGENTS.md"
    return _replace_once(
        docs,
        path,
        "PR 提出、CI green、merge",
        "PR 提出、merge",
    )


CHECKS: dict[str, Check] = {
    "stdin_closed": Check(
        run=check_stdin_closed,
        mutate=mutate_stdin_closed,
        targets=targets_stdin_closed,
        category="A1",
        why="非対話起動で stdin を閉じないと CLI がハングする",
    ),
    "codex_execution_shape": Check(
        run=check_codex_execution_shape,
        mutate=mutate_codex_execution_shape,
        extra_mutations=(
            mutate_codex_execution_shape_drops_model,
            mutate_codex_execution_shape_drops_effort,
        ),
        targets=targets_codex_execution_shape,
        category="A2",
        why="approval、model、effort の逸脱または欠落で実行契約が変わる",
    ),
    "review_scope_without_prompt": Check(
        run=check_review_scope_without_prompt,
        mutate=mutate_review_scope_without_prompt,
        targets=targets_review_scope_without_prompt,
        category="A3",
        why="scope flag と positional prompt の併用は codex review が失敗する",
    ),
    "shell_variables_assigned": Check(
        run=check_shell_variables_assigned,
        mutate=mutate_shell_variables_assigned,
        targets=targets_shell_variables_assigned,
        category="A4",
        why="shell 変数は tool 呼び出しを跨ぐと失われ誤 path を操作する",
    ),
    "no_broad_git_add": Check(
        run=check_no_broad_git_add,
        mutate=mutate_no_broad_git_add,
        targets=targets_no_broad_git_add,
        category="A5",
        why="broad add は承認外の変更を staging する",
    ),
    "remote_delete_has_lease": Check(
        run=check_remote_delete_has_lease,
        mutate=mutate_remote_delete_has_lease,
        extra_mutations=(mutate_remote_delete_lease_targets_other_ref,),
        targets=targets_remote_delete_has_lease,
        category="A6",
        why="lease なし・別 ref への lease は確認後の他者 push を捨てうる",
    ),
    "worktree_commands_pin_directory": Check(
        run=check_worktree_commands_pin_directory,
        mutate=mutate_worktree_commands_pin_directory,
        targets=targets_worktree_commands_pin_directory,
        category="A7",
        why="通常 checkout を review すると空 diff を成功と誤判定する",
    ),
    "frontmatter_name_matches_directory": Check(
        run=check_frontmatter_name_matches_directory,
        mutate=mutate_frontmatter_name_matches_directory,
        targets=targets_frontmatter_name_matches_directory,
        category="B1",
        why="skill identity と配布 directory のずれを防ぐ",
    ),
    "enum_table_cells": Check(
        run=check_enum_table_cells,
        mutate=mutate_enum_table_cells,
        targets=targets_enum_table_cells,
        category="B3",
        why="workflow enum への未知値混入を防ぐ",
    ),
    "commit_before_independent_review": Check(
        run=check_commit_before_independent_review,
        mutate=mutate_commit_before_independent_review,
        targets=targets_commit_before_independent_review,
        category="C1",
        why="未 commit diff の review 空振りを防ぐ",
    ),
    "approval_before_implementation": Check(
        run=check_approval_before_implementation,
        mutate=mutate_approval_before_implementation,
        targets=targets_approval_before_implementation,
        category="C2",
        why="承認前の実装委譲を防ぐ",
    ),
    "ci_green_before_merge": Check(
        run=check_ci_green_before_merge,
        mutate=mutate_ci_green_before_merge,
        targets=targets_ci_green_before_merge,
        category="C3",
        why="未確認の head を merge する順序退行を防ぐ",
    ),
}
EXPECTED_CATEGORIES = {
    "A1",
    "A2",
    "A3",
    "A4",
    "A5",
    "A6",
    "A7",
    "B1",
    "B3",
    "C1",
    "C2",
    "C3",
}


REAL_DOCS = {
    path: (REPO_ROOT / path).read_text(encoding="utf-8") for path in TARGET_PATHS
}


def test_all_invariants_hold_on_real_docs():
    """実際の配布ドキュメントが全 check を満たす。"""
    failures = {
        name: problems
        for name, check in CHECKS.items()
        if (problems := check.run(REAL_DOCS))
    }
    assert not failures, failures


def test_every_invariant_fails_on_its_mutation():
    """各 check が登録済み mutation を必ず検出する。"""
    categories = [check.category for check in CHECKS.values()]
    assert len(categories) == len(set(categories)), (
        f"同じカテゴリの check が重複登録されている: {categories}"
    )
    assert set(categories) == EXPECTED_CATEGORIES, (
        "必須カテゴリの check 登録が不完全: "
        f"missing={sorted(EXPECTED_CATEGORIES - set(categories))}, "
        f"extra={sorted(set(categories) - EXPECTED_CATEGORIES)}"
    )
    missing = [name for name, check in CHECKS.items() if check.mutate is None]
    assert not missing, f"mutation 未登録: {missing}"

    escaped: list[str] = []
    unchanged: list[str] = []
    for name, check in CHECKS.items():
        assert check.mutate is not None
        for index, mutate in enumerate(check.all_mutations):
            mutated = mutate(REAL_DOCS)
            if mutated == REAL_DOCS:
                unchanged.append(f"{name}[{index}]")
            if not check.run(mutated):
                escaped.append(f"{name}[{index}]")
    assert not unchanged, f"mutation が docs を変更していない: {unchanged}"
    assert not escaped, f"mutation を検出できない check: {escaped}"


def test_every_invariant_inspects_at_least_one_target():
    """どの check も実文書上の検査対象を 1 件以上見ている。"""
    empty = {
        name: check.targets(REAL_DOCS)
        for name, check in CHECKS.items()
        if check.targets(REAL_DOCS) < 1
    }
    assert not empty, f"検査対象がゼロの check: {empty}"
