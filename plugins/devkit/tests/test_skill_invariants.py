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
    # 環境変数前置は小文字も正当。大文字だけを見ていると、前置を小文字へ
    # 変えるだけでコマンドが inline 抽出から外れる。
    runnable = re.compile(
        r"^(?:[A-Za-z_][A-Za-z0-9_]*=[^ ]*\s+)*(?:codex|cursor-agent|git|node|"
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
    """非対話 CLI の command は stdin を閉じる。

    行全体ではなく委譲コマンド自身の segment を見る。行のどこかに
    `< /dev/null` があればよいとすると、別コマンドのリダイレクトで
    委譲側の未閉鎖が隠れてハングする。
    """
    return [
        f"{path}: stdin が閉じられていない: {command}"
        for path, command in _noninteractive_commands(docs)
        if "< /dev/null" not in _delegated_segment(command)
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
    # 複合行は segment ごとに切り出す。行全体を 1 つとして見ると、
    # 片方の呼び出しにある `-a never` が、もう片方の欠落を隠してしまう。
    commands: list[tuple[str, str]] = []
    for path, command in fenced + inline:
        for segment in re.split(r"\s*(?:&&|\|\||[|;])\s*", command):
            if re.match("^" + ENV_PREFIX + r"codex\s", segment.strip()):
                commands.append((path, segment.strip()))
    return commands


def check_codex_execution_shape(docs: Docs) -> list[str]:
    """codex command の approval、model、effort を検査する。

    値の誤りだけでなく**欠落**も拒否する。値だけを見ると、フラグごと消えた
    ときに正規表現が何も拾わず「問題なし」になり、固定契約が空洞化する。
    """
    problems: list[str] = []
    for path, command in _codex_commands(docs):
        if not re.search(r"(?:^|\s)-a\s+never(?:\s|$)", command):
            problems.append(f"{path}: codex に -a never がない: {command}")
        # 最初の 1 つだけを見ると `-m gpt-5.6-sol -m other` のように後勝ちの
        # 重複指定で実際の値を差し替えられる。全出現を検査する。
        models = re.findall(r"(?:^|\s)-m\s+(\S+)", command)
        if not models:
            problems.append(f"{path}: codex に -m の指定がない: {command}")
        for value in models:
            if value != "gpt-5.6-sol":
                problems.append(f"{path}: codex model が不正: {value}")
        # effort は `-c` 経由でしか渡らない。`-c` の無い記述は設定として
        # 効かないので、値が正しく見えても契約を満たさない。
        efforts = re.findall(r'-c\s+model_reasoning_effort="([^"]+)"', command)
        if not efforts and re.search(r'model_reasoning_effort="', command):
            problems.append(f"{path}: model_reasoning_effort に -c がない: {command}")
        if not efforts:
            problems.append(f"{path}: codex に model_reasoning_effort の指定がない: {command}")
        for value in efforts:
            if value != "medium":
                problems.append(f"{path}: codex effort が不正: {value}")
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


def review_combines_scope_and_prompt(command: str) -> bool:
    """`codex review` が scope flag と positional prompt を併用しているか。

    scope flag の後ろだけを見ると `review "<prompt>" --base main` のように
    prompt を前置するだけで回避できる。review 以降の引数列全体を見る。
    `cd <worktree> && codex ... review ...` のように前段があるため、
    先頭 segment ではなく review を含む segment を選ぶ。
    """
    segments = re.split(r"\s*(?:&&|\|\||[|;])\s*", command)
    segment = next((part for part in segments if "review" in part.split()), segments[0])
    # リダイレクト演算子は独立したトークンとして書かれる（`< /dev/null`、`2>&1`）。
    # 演算子の直後に空白を要求しないと、`<remote>/<default>` のような
    # placeholder をリダイレクトと誤認して引数ごと消してしまう。
    without_redirects = re.sub(r"(?:^|\s)\d*(?:>>?|<)(?:\s+\S+|&\d+)", " ", segment)
    tokens = without_redirects.split()
    if "review" not in tokens:
        return False
    expecting_value = False
    for token in tokens[tokens.index("review") + 1 :]:
        if token.startswith("-"):
            expecting_value = "=" not in token and token in _VALUE_FLAGS
            continue
        if expecting_value:
            expecting_value = False
            continue
        return True
    return False


def check_review_scope_without_prompt(docs: Docs) -> list[str]:
    """codex review は scope flag と positional prompt を併用しない。"""
    return [
        f"{path}: review scope と prompt を併用: {command}"
        for path, command in _scoped_review_commands(docs)
        if review_combines_scope_and_prompt(command)
    ]


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
        # コメント行は実行されないので、使用も代入も数えない。
        scannable = "\n".join(
            line for line in block.splitlines() if not line.lstrip().startswith("#")
        )
        # shell 変数は case-sensitive で小文字も正当。大文字だけを見ていると
        # 変数名を小文字へ rename するだけで未代入の検査が外れる。
        used = set(re.findall(r"\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?", scannable))
        # 永続代入だけを数える。`FOO=x cmd` の前置代入は cmd 限りで、
        # 後続行の `$FOO` は空へ展開する。代入文(値の直後がコマンド終端)に限る。
        # 判定は「前置代入を除外する」向きで書く。値は `$(...)` を含みうるため
        # 値の終端を正しく取るのは難しいが、前置代入は値が単純トークンで、
        # その直後にコマンド語が続く、という形に限られる。
        statement = re.compile(
            r"(?:^|(?<=[;&(])|(?<=&&\s)|(?<=\|\|\s))\s*([A-Za-z_][A-Za-z0-9_]*)="
            # 前置代入はコマンドと同じ行にある。`\s` だと改行を跨いで
            # 次行の代入をコマンド語と誤認する。水平空白に限る。
            # 無引用の値パターンから引用符を除く。含めると、引用された値の
            # 先頭部分だけを無引用値として拾い、続く語をコマンドと誤認する。
            r"(?!(?:\"[^\"]*\"|'[^']*'|[^\s;&|()$\"']*)[ \t]+[A-Za-z_./])",
            re.MULTILINE,
        )
        # 代入は「最初の使用より前」でなければ意味がない。block 内のどこかに
        # 代入があればよい、とすると使用後に代入する例が通ってしまう。
        assigned = set()
        for match in statement.finditer(scannable):
            name = match.group(1)
            first_use = re.search(rf"\$\{{?{name}\}}?", scannable)
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


PROHIBITION = re.compile(r"(?:使わない|使用しない|禁止|してはならない|避ける)")


def _shell_surfaces(docs: Docs) -> list[tuple[str, str]]:
    """fenced block と、禁止文脈にない inline span。

    inline span を丸ごと除くと、そこへ書くだけで検査を回避できる。丸ごと含めると
    「`git add .` / `git add -A` は使わない」という**禁止文中の引用**まで違反に
    なる。span が現れる文に禁止語があるかで、指示と引用を分ける。
    """
    surfaces = [
        (path, block) for path, text in docs.items() for block in _bash_blocks(text)
    ]
    for path, text in docs.items():
        for match in re.finditer(r"`([^`\n]+)`", text):
            span = match.group(1).strip()
            if not re.match("^" + ENV_PREFIX + r"(?:git|codex|cursor-agent)\b", span):
                continue
            sentence_start = max(
                text.rfind("。", 0, match.start()), text.rfind("\n", 0, match.start())
            )
            sentence_end = text.find("。", match.end())
            sentence = text[
                sentence_start + 1 : sentence_end if sentence_end >= 0 else len(text)
            ]
            if PROHIBITION.search(sentence):
                continue
            surfaces.append((path, span))
    return surfaces


def check_no_broad_git_add(docs: Docs) -> list[str]:
    """実行例に broad git add を許さない。"""
    problems: list[str] = []
    for path, block in _shell_surfaces(docs):
        # 行末 `\` で `git add \` / `.` と折り返すと物理行では検出できない。
        for line in _join_continuations(block):
            # `&&` だけでなく `;` `||` `|` の後ろも見る。区切りを変えるだけで
            # 禁止しているはずの broad staging が素通りしてしまう。
            # `git -C "<worktree>" add .` のように global option を挟む形も拾う。
            if re.search(
                # `-A` の別名 `--all`、および option 終端 `--` の後ろの `.` も
                # broad staging。`git add -- .` は全体を stage する。
                _git_subcommand_pattern("add")
                + r"(?:\s+--)?\s+(?:\.|-A|--all)(?:\s|$)",
                line,
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


def mutate_no_broad_git_add_with_global_option(docs: Docs) -> Docs:
    """`git -C ... add -A` のように global option を挟んだ形。"""
    path = "plugins/devkit/skills/dig/SKILL.md"
    old = "```bash\ncodex -a never exec --sandbox read-only"
    new = (
        '```bash\ngit -C "<worktree>" add -A\n'
        "codex -a never exec --sandbox read-only"
    )
    return _replace_once(docs, path, old, new)


# shell の区切りと環境変数前置。判定ごとに書き分けると片方だけ緩くなり、
# 区切りや前置を変えるだけで検査から外れる穴ができる。1 箇所に集約する。
SEPARATOR = r"(?:^|&&|\|\||[|;]|\()\s*"
ENV_PREFIX = r"(?:[A-Za-z_][A-Za-z0-9_]*=(?:\"[^\"]*\"|'[^']*'|\S*)\s+)*"


def _git_subcommand_pattern(subcommand: str) -> str:
    """`git [global options] <subcommand>` に一致する正規表現。

    `git -C "<worktree>" push ...` のように global option を挟むだけで
    検査から外れないよう、option 列を跨いで subcommand を見る。
    """
    return (
        r"(?:^|&&|\|\||[|;]|\()\s*git\s+"
        r"(?:(?:-[A-Za-z]|--[\w-]+)(?:=\S+|\s+(?:\"[^\"]*\"|'[^']*'|\S+))?\s+)*"
        rf"{subcommand}\b"
    )


def _is_scoped_review(command: str) -> bool:
    """scope 付き review command。`--base` と `--uncommitted` の両方を見る。

    片方だけを見ると、scope を切り替えたときに worktree 固定の検査から
    黙って外れ、通常 checkout をレビューする退行が素通りする。
    """
    return " review " in command and (
        "--base" in command or "--uncommitted" in command
    )


def _deleted_refs(command: str) -> set[str]:
    """1 コマンドが削除する branch をすべて集める。

    `--delete <remote> <a> <b>` と `:<ref>` の両形式に対応する。
    """
    refs = {_strip_ref_prefix(ref) for ref in re.findall(r"\s:(\S+)", command)}
    if not re.search(r"\s(?:--delete|-d)\b", command):
        return refs
    # remote は `--delete` の前後どちらにも書ける
    # (`push origin --delete a` / `push --delete origin a`)。
    # フラグを除いた位置引数のうち、先頭が remote、残りが branch。
    tokens = command.split()
    positional: list[str] = []
    expecting_value = False
    for token in tokens[tokens.index("push") + 1 :] if "push" in tokens else []:
        if token.startswith("-"):
            expecting_value = "=" not in token and token in _VALUE_FLAGS
            continue
        if expecting_value:
            expecting_value = False
            continue
        positional.append(token)
    refs.update(_strip_ref_prefix(token) for token in positional[1:])
    return refs


def _strip_ref_prefix(ref: str) -> str:
    """`refs/heads/x` と `x` を同じ branch として比べられるようにする。"""
    return ref.removeprefix("refs/heads/")


def _remote_delete_commands(docs: Docs) -> list[tuple[str, str]]:
    """削除 refspec（source が空の `:refs/heads/...`）を持つ push だけを拾う。

    `HEAD:refs/heads/topic` のような通常の明示 push を削除と誤認して
    lease を要求すると、正しいコマンドを書けなくなる。
    """
    return [
        (path, command)
        for path, command in _command_lines(docs)
        # `--delete` の短縮形 `-d` も削除。
        if re.search(
            _git_subcommand_pattern("push") + r".*(?:\s(?:--delete|-d)\b|\s:\S)",
            command,
        )
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
        # 削除は `:refs/heads/x`、`:x`、`--delete <remote> <branch>` のいずれでも
        # 書ける。1 形式しか見ないと、書き方を変えるだけで lease 要求から外れる。
        # `--delete` の直後は remote 名なので、branch はその次のトークン。
        deleted = _deleted_refs(command)
        leases = {
            _strip_ref_prefix(ref)
            for ref in re.findall(r"--force-with-lease=(\S+?):", command)
        }
        if not leases:
            problems.append(f"{path}: lease なし remote delete: {command}")
            continue
        # 1 回の push で複数 branch を消せる。1 つ目だけ見ると、lease の無い
        # 2 つ目の branch へ並行 push された commit を捨てうる。
        unleased = sorted(ref for ref in deleted if ref not in leases)
        if unleased:
            problems.append(
                f"{path}: lease の無い削除対象がある {unleased} "
                f"(lease={sorted(leases)}): {command}"
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


# worktree 内で実行される工程の節。ここに現れる委譲コマンドは worktree 固定が要る。
# 計画レビュー(step 4)は worktree 作成より前なので含めない。
WORKTREE_SECTIONS = {
    "plugins/devkit/skills/dig/SKILL.md": (
        "### 6. worktree 作成と実装委譲",
        "### 7. 自レビューと独立 diff レビュー",
        "### 8. 修正ループ",
    ),
    "plugins/devkit/skills/repo-loop/SKILL.md": (
        "### worktree・実装・検証",
        "### 独立レビュー",
    ),
}


def _section_body(text: str, heading: str) -> str:
    start = text.find(heading)
    if start < 0:
        return ""
    level = len(heading) - len(heading.lstrip("#"))
    match = re.search(
        rf"^#{{1,{level}}} (?!#)", text[start + len(heading) :], re.MULTILINE
    )
    return text[start:] if match is None else text[start : start + len(heading) + match.start()]


def _worktree_commands(docs: Docs) -> list[tuple[str, str]]:
    """worktree 内で走る工程の委譲コマンド。

    membership を `--sandbox workspace-write` のようなフラグで決めると、
    そのフラグごと落ちたコマンドが検査対象から消えて退行が素通りする。
    節の構造(どの工程に書かれているか)で決め、フラグとは独立させる。
    """
    commands: list[tuple[str, str]] = []
    for path, headings in WORKTREE_SECTIONS.items():
        text = docs.get(path, "")
        for heading in headings:
            body = _section_body(text, heading)
            if not body:
                continue
            for _, command in _command_lines({path: body}):
                if not re.search(
                    SEPARATOR + ENV_PREFIX + r"(?:codex|cursor-agent)\s", command
                ):
                    continue
                # create-chat は chatId を発行するだけでファイルを触らない。
                # workspace 指定は後続の -p 呼び出し側の契約。
                if re.search(r"\bcursor-agent\s+create-chat\b", _delegated_segment(command)):
                    continue
                commands.append((path, command))
    # scope 付き review はどこに書かれていても worktree 内で走る。
    for path, command in _command_lines(docs):
        if path in WORKTREE_SECTIONS and _is_scoped_review(command):
            if (path, command) not in commands:
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
        if re.match("^" + ENV_PREFIX + r"(?:codex|cursor-agent)\b", segment):
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
        # 変数参照を無条件に許すと `-C "$HOME"` や `-C "$MAIN_CHECKOUT"` が通り、
        # 通常 checkout をレビューする失敗モードがそのまま素通りする。
        # placeholder でも変数でも、名前が worktree を指していることを要求する。
        if "worktree" not in target.lower() and "wt_dir" not in target.lower():
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


# step 番号の有無は文書自身から導かない。番号と宣言を同時に消すと「番号なし」に
# 化けて検査対象から外れるため、対象モードは外から明示する。
NUMBERED_STEP_DOCS = frozenset(
    {
        "plugins/devkit/skills/dig/SKILL.md",
        "plugins/devkit/skills/catch-up/SKILL.md",
        "plugins/devkit/skills/commit-push/SKILL.md",
        "plugins/devkit/skills/memory-review/SKILL.md",
        "plugins/devkit/skills/backlog/SKILL.md",
        "plugins/devkit/skills/refactor/SKILL.md",
        "plugins/devkit/skills/handoff/SKILL.md",
    }
)
UNNUMBERED_STEP_DOCS = frozenset(
    {
        "AGENTS.md",
        "plugins/devkit/skills/setup/SKILL.md",
        "plugins/devkit/skills/goal-prompt/SKILL.md",
        "plugins/devkit/skills/improve-skill/SKILL.md",
        "plugins/devkit/skills/repo-loop/SKILL.md",
    }
)
NUMBERED_HEADING = re.compile(r"^(#{2,6}) (\d+)\. ", re.MULTILINE)
STEP_RANGE = re.compile(r"step (\d+)-(\d+)")


def _numbered_heading_groups(docs: Docs) -> dict[tuple[str, int], list[int]]:
    """(path, 見出しレベル) -> 文書順の番号列。

    fenced code block 内の見出し風テキストは手順ではないので除外する。
    レベル別に分けることで、memory-review のレポート雛形 (`## 1.`〜) と
    工程見出し (`### 1.`〜) が混ざって欠番扱いになるのを防ぐ。
    """
    groups: dict[tuple[str, int], list[int]] = {}
    for path, text in docs.items():
        body = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
        for match in NUMBERED_HEADING.finditer(body):
            level = len(match.group(1))
            groups.setdefault((path, level), []).append(int(match.group(2)))
    return groups


def _step_range_declarations(docs: Docs) -> list[tuple[str, int, int]]:
    return [
        (path, int(match.group(1)), int(match.group(2)))
        for path, text in docs.items()
        for match in STEP_RANGE.finditer(text)
    ]


def check_step_numbering_and_declared_range(docs: Docs) -> list[str]:
    """numbered ### 見出しは 1..N 連番で、宣言範囲もその N に収める。

    検査対象かどうかはレジストリで決める。文書内容から導くと、番号と宣言を
    同時に消したときに unnumbered へ化けて素通りする。
    """
    problems: list[str] = []
    groups = _numbered_heading_groups(docs)
    declarations = _step_range_declarations(docs)
    decls_by_path: dict[str, list[tuple[int, int]]] = {}
    for path, start, end in declarations:
        decls_by_path.setdefault(path, []).append((start, end))

    # 性質 1: 各 (path, レベル) グループは文書順で厳密に 1..N。
    # 集合だけ合っていても順序が違えば fail にする。
    for (path, level), numbers in sorted(groups.items()):
        expected = list(range(1, len(numbers) + 1))
        if numbers != expected:
            problems.append(
                f"{path}: 見出しレベル {level} の番号が "
                f"1..{len(numbers)} の連番でない: {numbers}"
            )

    # 性質 2: numbered 文書は ### グループと完全範囲 step 1-N を持つ。
    for path in sorted(NUMBERED_STEP_DOCS):
        if path not in docs:
            problems.append(f"{path}: 対象文書が存在しない")
            continue
        h3 = groups.get((path, 3))
        if not h3:
            problems.append(f"{path}: numbered ### 見出しがない")
            continue
        n = max(h3)
        if not any(start == 1 and end == n for start, end in decls_by_path.get(path, [])):
            problems.append(f"{path}: 完全範囲の step 1-{n} 宣言がない")

    # 性質 3: 全 step A-B は 1 <= A <= B <= N。部分範囲 (例: dig の 6-9) は正当。
    # 性質 2 だけでは上限超過や A>B を検出できないため、独立に検査する。
    for path, start, end in declarations:
        h3 = groups.get((path, 3))
        if not h3:
            continue
        n = max(h3)
        if not (1 <= start <= end <= n):
            problems.append(f"{path}: step {start}-{end} が 1..{n} の範囲外")

    # 性質 4: unnumbered 文書は numbered ### も step 宣言も持たない。
    for path in sorted(UNNUMBERED_STEP_DOCS):
        if path not in docs:
            problems.append(f"{path}: 対象文書が存在しない")
            continue
        if groups.get((path, 3)):
            problems.append(f"{path}: unnumbered 文書に numbered ### 見出しがある")
        if decls_by_path.get(path):
            problems.append(f"{path}: unnumbered 文書に step A-B 宣言がある")

    return problems


def targets_step_numbering_and_declared_range(docs: Docs) -> int:
    return (
        len(_numbered_heading_groups(docs))
        + len(_step_range_declarations(docs))
        + len(NUMBERED_STEP_DOCS)
        + len(UNNUMBERED_STEP_DOCS)
    )


def mutate_step_numbering_gap_and_duplicate(docs: Docs) -> Docs:
    """欠番と重複を同時に作る。"""
    return _replace_once(
        docs,
        DIG,
        "### 4. 計画レビュー",
        "### 5. 計画レビュー",
    )


def mutate_step_numbering_drops_heading_number(docs: Docs) -> Docs:
    """見出しから番号だけが消える。"""
    return _replace_once(
        docs,
        DIG,
        "### 3. backend 選択",
        "### backend 選択",
    )


def mutate_step_numbering_swaps_order(docs: Docs) -> Docs:
    """見出し番号の文書順が逆転する。"""
    return _swap_once(
        docs,
        "plugins/devkit/skills/backlog/SKILL.md",
        "### 1. スコープ確認",
        "### 2. 情報源スキャン",
    )


def mutate_step_numbering_stale_full_range(docs: Docs) -> Docs:
    """完全範囲宣言だけが古くなる。"""
    return _replace_once(
        docs,
        "plugins/devkit/skills/catch-up/SKILL.md",
        "step 1-8",
        "step 1-7",
    )


def mutate_step_numbering_injects_declaration_into_unnumbered(docs: Docs) -> Docs:
    """unnumbered 文書へ step 宣言が残る / 混入する。"""
    return _replace_once(
        docs,
        "plugins/devkit/skills/repo-loop/SKILL.md",
        "非対話実行では質問しない。",
        "非対話実行では質問しない。step 1-5 を参照。",
    )


def mutate_step_numbering_strips_all_numbers_and_declarations(docs: Docs) -> Docs:
    """番号と宣言を同時に消す。内容から対象を導くと素通りするため、レジストリ必須。"""
    mutated = _copy(docs)
    text = mutated[DIG]
    stripped = re.sub(r"^### \d+\. ", "### ", text, flags=re.MULTILINE)
    stripped = re.sub(r"step \d+-\d+", "step", stripped)
    assert stripped != text, f"mutation が空振りした: {DIG}"
    mutated[DIG] = stripped
    return mutated


def mutate_step_numbering_declaration_exceeds_max(docs: Docs) -> Docs:
    """宣言の上限だけが N を超える。完全範囲 step 1-9 は残るので性質 3 専用。"""
    return _replace_once(docs, DIG, "step 6-9", "step 6-10")


def mutate_step_numbering_declaration_reversed(docs: Docs) -> Docs:
    """宣言の A>B。完全範囲 step 1-9 は残るので性質 3 専用。"""
    return _replace_once(docs, DIG, "step 6-9", "step 9-6")


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


def _missing_order_markers(
    docs: Docs,
    before: re.Pattern[str],
    after: re.Pattern[str],
    required: tuple[str, ...],
) -> list[str]:
    """必ず両 marker を持つべき文書から marker が消えたことを検出する。

    marker が無い文書を黙って skip すると、見出しごと消したときに検査対象が
    ゼロになって check が沈黙する。工程そのものの消失を見逃すため、
    対象文書を明示して不在を fail にする。
    """
    problems: list[str] = []
    for path in required:
        text = docs.get(path)
        if text is None:
            problems.append(f"{path}: 対象文書が存在しない")
            continue
        if before.search(text) is None:
            problems.append(f"{path}: 前段 marker が消えている ({before.pattern})")
        if after.search(text) is None:
            problems.append(f"{path}: 後段 marker が消えている ({after.pattern})")
    return problems


DIG = "plugins/devkit/skills/dig/SKILL.md"


COMMIT_MARKER = re.compile(r"^#### 節目 commit$", re.MULTILINE)
REVIEW_MARKER = re.compile(r"^### \d+\. 自レビューと独立 diff レビュー$", re.MULTILINE)


def check_commit_before_independent_review(docs: Docs) -> list[str]:
    """節目 commit の工程は独立 diff review より前に置き、実際に commit を指示する。

    見出しの順序だけを見ると、節の中身が消えても「commit しない」に反転しても
    通ってしまう。`review --base` が空 diff を見て「指摘なし」と誤報する退行は
    まさにそれなので、肯定形の commit 指示が review より前にあることまで見る。
    """
    problems = _missing_order_markers(docs, COMMIT_MARKER, REVIEW_MARKER, (DIG,))
    for path, commit, review in _docs_with_order_markers(
        docs, COMMIT_MARKER, REVIEW_MARKER
    ):
        if commit.start() >= review.start():
            problems.append(f"{path}: 節目 commit が独立 review より後")
            continue
        body = docs[path][commit.end() : review.start()]
        # 肯定形の指示を含む**文**を取り、その文が否定されていないことまで見る。
        # 「実装 backend は commit しない」は正当な条件節なので、文単位で判定する。
        affirmative = re.search(r"[^。\n]*commit する[^。\n]*", body)
        if affirmative is None:
            problems.append(f"{path}: review 前に commit を指示する記述がない")
        elif re.search(r"(?:必要はない|しなくてよい|は不要)", affirmative.group(0)):
            problems.append(
                f"{path}: 節目 commit の指示が否定されている: {affirmative.group(0)}"
            )
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
    problems = _missing_order_markers(
        docs, APPROVAL_MARKER, IMPLEMENTATION_MARKER, (DIG,)
    )
    for path, approval, implementation in _docs_with_order_markers(
        docs, APPROVAL_MARKER, IMPLEMENTATION_MARKER
    ):
        if approval.start() >= implementation.start():
            problems.append(f"{path}: 計画承認が実装委譲より後")
            continue
        body = docs[path][approval.end() : implementation.start()]
        if "明示承認" not in body:
            problems.append(f"{path}: 承認節に明示承認の要求がない")
        # 肯定形の接頭辞に一致しても、その後ろで否定されれば契約は反転する。
        # 文末までを取って否定語の有無まで見る。
        activation = re.search(r"承認後だけ[^。\n]*write_scope[^。\n]*有効[^。\n]*", body)
        if activation is None:
            problems.append(f"{path}: 承認と write_scope 有効化が結ばれていない")
        elif re.search(r"(?:必要はない|しない|されない|とは限らない)", activation.group(0)):
            problems.append(
                f"{path}: write_scope 有効化が否定されている: {activation.group(0)}"
            )
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
        # merge 側は「否定の禁止」では検査できない。CI 赤なら merge しない、は
        # 正当な条件節だから。代わりに**肯定形の merge 指示**の存在を要求する。
        # これが消えれば、工程そのものが失われたことを検出できる。
        affirmative_merge = re.search(
            r"[^。\n]*(?:merge (?:まで完遂|を実行|する)|`gh pr merge|ff-only merge)[^。\n]*",
            section,
        )
        if negated:
            problems.append(f"{path}: CI green の要求が否定されている: {negated.group(0)}")
        elif affirmative_merge is None:
            problems.append(f"{path}: merge を実行する肯定形の指示がない")
        elif re.search(r"(?:必要はない|しなくてよい|は不要)", affirmative_merge.group(0)):
            # 否定は肯定文の中だけで判定する。「CI 赤なら merge しない」は正当。
            problems.append(
                f"{path}: merge 指示が否定されている: {affirmative_merge.group(0)}"
            )
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
        extra_mutations=(mutate_no_broad_git_add_with_global_option,),
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
    "step_numbering_and_declared_range": Check(
        run=check_step_numbering_and_declared_range,
        mutate=mutate_step_numbering_gap_and_duplicate,
        extra_mutations=(
            mutate_step_numbering_drops_heading_number,
            mutate_step_numbering_swaps_order,
            mutate_step_numbering_stale_full_range,
            mutate_step_numbering_injects_declaration_into_unnumbered,
            mutate_step_numbering_strips_all_numbers_and_declarations,
            mutate_step_numbering_declaration_exceeds_max,
            mutate_step_numbering_declaration_reversed,
        ),
        targets=targets_step_numbering_and_declared_range,
        category="B2",
        why="step 見出しの欠番・重複・宣言範囲の逸脱を防ぐ",
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
    "B2",
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


def test_step_numbering_registry_covers_all_targets():
    """番号付き / 番号なしのレジストリが TARGET_PATHS を漏れなく分割する。

    新しいスキルを足したときに登録漏れが fail になり、レジストリが黙って
    古くなる経路を塞ぐ。互いに素であることも要求し、両集合への二重登録を防ぐ。
    """
    numbered = set(NUMBERED_STEP_DOCS)
    unnumbered = set(UNNUMBERED_STEP_DOCS)
    assert numbered.isdisjoint(unnumbered), (
        f"レジストリが重複: {sorted(numbered & unnumbered)}"
    )
    assert numbered | unnumbered == set(TARGET_PATHS), (
        "レジストリが TARGET_PATHS を覆っていない: "
        f"missing={sorted(set(TARGET_PATHS) - (numbered | unnumbered))}, "
        f"extra={sorted((numbered | unnumbered) - set(TARGET_PATHS))}"
    )
