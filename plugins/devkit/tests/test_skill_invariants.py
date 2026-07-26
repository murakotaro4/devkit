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
        "### 3. backend 固定とフォールバック",
        "### backend 固定とフォールバック",
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


ROLE_TABLE_HEADER = ("役割", "既定")
FALLBACK_TABLE_HEADER = ("親", "実装 lane", "レビュー lane（計画 / diff 共通）")
BACKEND_SECTION = "### 3. backend 固定とフォールバック"
CURSOR_MODEL = "cursor-grok-4.5-high"
CODEX_MODEL = "gpt-5.6-sol"
EXPECTED_ROLES = ("実装", "計画レビュー", "diff レビュー")
EXPECTED_FALLBACK_LANES: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "Claude 親": (
        (
            "cursor-agent",
            "codex CLI",
            "`Agent(general-purpose, model=sonnet)`",
            "停止",
        ),
        (
            "codex CLI",
            "`Agent(general-purpose, model=opus)`",
            "終端処理",
        ),
    ),
    "Codex 親": (
        (
            "cursor-agent",
            "`spawn_agent` worker",
            "親実装",
            "停止",
        ),
        (
            "`spawn_agent` explorer",
            "終端処理",
        ),
    ),
    "判定不能": (
        (
            "cursor-agent",
            "codex CLI",
            "停止",
        ),
        (
            "codex CLI",
            "終端処理",
        ),
    ),
}


def _table_rows(body: str, header: tuple[str, ...]) -> list[list[str]]:
    lines = body.splitlines()
    for index, line in enumerate(lines):
        if not line.startswith("|"):
            continue
        if tuple(_cells(line)) != header:
            continue
        rows: list[list[str]] = []
        for row in lines[index + 2 :]:
            if not row.startswith("|"):
                break
            rows.append(_cells(row))
        return rows
    return []


def _lane_stages(cell: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in cell.split("→") if part.strip())


def _fixed_backend_rows(docs: Docs) -> tuple[list[list[str]], list[list[str]]]:
    body = _section_body(docs.get(DIG, ""), BACKEND_SECTION)
    return _table_rows(body, ROLE_TABLE_HEADER), _table_rows(body, FALLBACK_TABLE_HEADER)


def check_fixed_backend_assignment(docs: Docs) -> list[str]:
    """dig の backend 固定割り当てとフォールバック順序を検査する。

    対象特定は節見出しと表ヘッダの構造で行い、モデル名を membership 判定に使わない。
    """
    body = _section_body(docs.get(DIG, ""), BACKEND_SECTION)
    if not body:
        return [f"{DIG}: {BACKEND_SECTION} がない"]

    role_rows, fallback_rows = _fixed_backend_rows(docs)
    problems: list[str] = []
    role_names = [row[0] for row in role_rows if row]
    role_counts = {role: role_names.count(role) for role in set(role_names)}
    for role in EXPECTED_ROLES:
        count = role_counts.get(role, 0)
        if count == 0:
            problems.append(f"{DIG}: 役割表に {role} 行がない")
        elif count > 1:
            problems.append(f"{DIG}: 役割表に {role} 行が重複している")
    for role in sorted(set(role_names) - set(EXPECTED_ROLES)):
        problems.append(f"{DIG}: 役割表に未知の役割行 {role}")

    by_role = {row[0]: row[1] for row in role_rows if len(row) >= 2}

    impl = by_role.get("実装", "")
    if CURSOR_MODEL not in impl:
        problems.append(f"{DIG}: 実装の既定に {CURSOR_MODEL} がない")
    if CODEX_MODEL in impl:
        problems.append(f"{DIG}: 実装の既定に {CODEX_MODEL} が混入している")

    for role in ("計画レビュー", "diff レビュー"):
        cell = by_role.get(role, "")
        if CODEX_MODEL not in cell:
            problems.append(f"{DIG}: {role} の既定に {CODEX_MODEL} がない")
        if CURSOR_MODEL in cell:
            problems.append(f"{DIG}: {role} の既定に {CURSOR_MODEL} が混入している")

    parent_names = [row[0] for row in fallback_rows if row]
    parent_counts = {
        parent: parent_names.count(parent) for parent in set(parent_names)
    }
    expected_parents = tuple(EXPECTED_FALLBACK_LANES)
    for parent in expected_parents:
        count = parent_counts.get(parent, 0)
        if count == 0:
            problems.append(f"{DIG}: フォールバック表に {parent} 行がない")
        elif count > 1:
            problems.append(f"{DIG}: フォールバック表に {parent} 行が重複している")
    for parent in sorted(set(parent_names) - set(expected_parents)):
        problems.append(f"{DIG}: フォールバック表に未知の親行 {parent}")

    by_parent = {row[0]: row for row in fallback_rows if row}

    for parent, (expected_impl, expected_review) in EXPECTED_FALLBACK_LANES.items():
        row = by_parent.get(parent)
        if row is None:
            continue
        if len(row) < 3:
            problems.append(f"{DIG}: {parent} のフォールバック行が不足: {row}")
            continue
        actual_impl = _lane_stages(row[1])
        actual_review = _lane_stages(row[2])
        if actual_impl != expected_impl:
            problems.append(
                f"{DIG}: {parent} の実装 lane が期待と不一致: "
                f"{actual_impl!r} != {expected_impl!r}"
            )
        if actual_review != expected_review:
            problems.append(
                f"{DIG}: {parent} のレビュー lane が期待と不一致: "
                f"{actual_review!r} != {expected_review!r}"
            )
    return problems


def targets_fixed_backend_assignment(docs: Docs) -> int:
    role_rows, fallback_rows = _fixed_backend_rows(docs)
    return len(role_rows) + len(fallback_rows)


def mutate_fixed_backend_assignment(docs: Docs) -> Docs:
    return _replace_once(
        docs,
        DIG,
        f"| 実装 | cursor-agent `{CURSOR_MODEL}` |",
        f"| 実装 | cursor-agent `{CODEX_MODEL}` |",
    )


def mutate_fixed_backend_assignment_swaps_review(docs: Docs) -> Docs:
    return _replace_once(
        docs,
        DIG,
        f"| 計画レビュー | codex `{CODEX_MODEL}` / medium |",
        f"| 計画レビュー | cursor-agent `{CURSOR_MODEL}` |",
    )


def mutate_fixed_backend_assignment_drops_fallback(docs: Docs) -> Docs:
    return _replace_once(
        docs,
        DIG,
        "| Claude 親 | cursor-agent → codex CLI → "
        "`Agent(general-purpose, model=sonnet)` → 停止 |",
        "| Claude 親 | cursor-agent |",
    )


def mutate_fixed_backend_assignment_drops_review_lane(docs: Docs) -> Docs:
    return _replace_once(
        docs,
        DIG,
        "codex CLI → `Agent(general-purpose, model=opus)` → 終端処理",
        "codex CLI → 終端処理",
    )


def mutate_fixed_backend_assignment_duplicates_role(docs: Docs) -> Docs:
    return _replace_once(
        docs,
        DIG,
        f"| 実装 | cursor-agent `{CURSOR_MODEL}` |",
        f"| 実装 | codex `{CODEX_MODEL}` / medium |\n"
        f"| 実装 | cursor-agent `{CURSOR_MODEL}` |",
    )


def mutate_fixed_backend_assignment_duplicates_parent(docs: Docs) -> Docs:
    return _replace_once(
        docs,
        DIG,
        "| Codex 親 | cursor-agent → `spawn_agent` worker → 親実装 → 停止 | "
        "`spawn_agent` explorer → 終端処理 |",
        "| Codex 親 | cursor-agent → 停止 | `spawn_agent` explorer → 終端処理 |\n"
        "| Codex 親 | cursor-agent → `spawn_agent` worker → 親実装 → 停止 | "
        "`spawn_agent` explorer → 終端処理 |",
    )


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


REPAIR_LOOP_BACKSTOP = 20
REPAIR_LOOP_STREAK = 2
REPAIR_LOOP_SURFACES = {
    "plugins/devkit/skills/dig/SKILL.md": "### 8. 修正ループ",
    "plugins/devkit/skills/goal-prompt/SKILL.md": "## 上限停止の自動算出",
    "plugins/devkit/skills/repo-loop/SKILL.md": "### 独立レビュー",
}
REPAIR_LOOP_BACKSTOP_RE = re.compile(r"(\d+)\s*巡(?:に達した|到達)")
REPAIR_LOOP_STREAK_RE = re.compile(r"(\d+)\s*巡連続")
REPAIR_LOOP_ZERO_EXIT_RE = re.compile(r"(findings|指摘)\s*が\s*ゼロ")


def _repair_loop_sections(docs: Docs) -> list[tuple[str, str, str]]:
    """修正ループ停止条件を置く surface と節本文。

    membership は節見出しの構造で決める。数値そのものを対象特定に使うと、
    バックストップ値を変えた退行が検査対象から消えて素通りする。
    """
    sections: list[tuple[str, str, str]] = []
    for path, heading in REPAIR_LOOP_SURFACES.items():
        body = _section_body(docs.get(path, ""), heading)
        sections.append((path, heading, body))
    return sections


def check_repair_loop_stop_conditions(docs: Docs) -> list[str]:
    """3 スキルの修正ループ停止条件を揃える。

    件数停滞・再出・バックストップに加え、連続しきい値とゼロ終了も検査する。
    """
    problems: list[str] = []
    backstops: list[tuple[str, int]] = []
    streaks: list[tuple[str, tuple[int, ...]]] = []
    for path, heading, body in _repair_loop_sections(docs):
        if not body:
            problems.append(f"{path}: {heading} がない")
            continue
        if REPAIR_LOOP_ZERO_EXIT_RE.search(body) is None:
            problems.append(f"{path}: findings/指摘ゼロ終了の条件がない")
        if "前巡以上" not in body:
            problems.append(f"{path}: 件数非改善の停止条件がない")
        if "同一 finding" not in body or "再出" not in body:
            problems.append(f"{path}: 同一 finding 再出の停止条件がない")
        found_streaks = tuple(
            int(match.group(1)) for match in REPAIR_LOOP_STREAK_RE.finditer(body)
        )
        if len(found_streaks) != 2:
            problems.append(
                f"{path}: 巡連続しきい値が 2 件でない: {found_streaks}"
            )
        elif any(value != REPAIR_LOOP_STREAK for value in found_streaks):
            problems.append(
                f"{path}: 巡連続しきい値が {REPAIR_LOOP_STREAK} でない: "
                f"{found_streaks}"
            )
        else:
            streaks.append((path, found_streaks))
        match = REPAIR_LOOP_BACKSTOP_RE.search(body)
        if match is None:
            problems.append(f"{path}: バックストップ巡の停止条件がない")
        else:
            backstops.append((path, int(match.group(1))))

    if len(streaks) == len(REPAIR_LOOP_SURFACES):
        streak_sets = {values for _, values in streaks}
        if len(streak_sets) != 1:
            problems.append(
                f"修正ループの巡連続しきい値が surface 間で不一致: {streaks}"
            )

    if len(backstops) == len(REPAIR_LOOP_SURFACES):
        values = {value for _, value in backstops}
        if len(values) != 1:
            problems.append(
                f"修正ループのバックストップが surface 間で不一致: {backstops}"
            )
        elif next(iter(values)) != REPAIR_LOOP_BACKSTOP:
            problems.append(
                f"修正ループのバックストップが {REPAIR_LOOP_BACKSTOP} でない: "
                f"{backstops}"
            )
    return problems


def targets_repair_loop_stop_conditions(docs: Docs) -> int:
    del docs
    return len(REPAIR_LOOP_SURFACES)


def mutate_repair_loop_stop_conditions(docs: Docs) -> Docs:
    return _replace_once(
        docs,
        "plugins/devkit/skills/dig/SKILL.md",
        "件数が前巡以上の状態が 2 巡連続した / ",
        "",
    )


def mutate_repair_loop_stop_conditions_drops_recurrence(docs: Docs) -> Docs:
    return _replace_once(
        docs,
        "plugins/devkit/skills/goal-prompt/SKILL.md",
        "同一 finding（ファイル・箇所・根本原因同一。文言一致ではない）が 2 巡連続で再出、",
        "",
    )


def mutate_repair_loop_stop_conditions_shifts_backstop(docs: Docs) -> Docs:
    mutated = docs
    for path, old, new in (
        (
            "plugins/devkit/skills/dig/SKILL.md",
            "20 巡に達した",
            "21 巡に達した",
        ),
        (
            "plugins/devkit/skills/goal-prompt/SKILL.md",
            "20 巡到達",
            "21 巡到達",
        ),
        (
            "plugins/devkit/skills/repo-loop/SKILL.md",
            "20 巡に達した",
            "21 巡に達した",
        ),
    ):
        mutated = _replace_once(mutated, path, old, new)
    return mutated


def mutate_repair_loop_stop_conditions_shifts_streak(docs: Docs) -> Docs:
    return _replace_once(
        docs,
        "plugins/devkit/skills/repo-loop/SKILL.md",
        "2 巡連続",
        "3 巡連続",
    )


def mutate_repair_loop_stop_conditions_drops_zero_exit(docs: Docs) -> Docs:
    return _replace_once(
        docs,
        "plugins/devkit/skills/goal-prompt/SKILL.md",
        "findings がゼロで終了する。",
        "",
    )


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


# ---------------------------------------------------------------------------
# B8: request_user_input をハーネス判定キーへ格上げする退行を防ぐ
# ---------------------------------------------------------------------------

# 散文ハーネスは構造的に判定できないため未検査とする。
# goal-prompt のハーネス節は 2 文からなり、前者は親の決定、後者は親ごとの質問手段
# （正当に `request_user_input` を含む）。両者を文言に頼らず区別する手段がない。
UNCHECKED_HARNESS_DOCS = frozenset({"plugins/devkit/skills/goal-prompt/SKILL.md"})
HARNESS_HEADING = re.compile(r"^## ハーネス[^\n]*$", re.MULTILINE)
GOAL_PROMPT = "plugins/devkit/skills/goal-prompt/SKILL.md"
HANDOFF = "plugins/devkit/skills/handoff/SKILL.md"
BACKTICK_IDENTIFIER = re.compile(r"`([^`]+)`")


def _skill_paths(docs: Docs) -> list[str]:
    return sorted(path for path, _ in _skill_docs(docs))


def _harness_section(text: str) -> str | None:
    """`## ハーネス` 前方一致の節をちょうど 1 つ返す。0 件・2 件以上は None。"""
    matches = list(HARNESS_HEADING.finditer(text))
    if len(matches) != 1:
        return None
    return _section_body(text, matches[0].group(0))


def _harness_table_columns(
    section: str,
) -> tuple[list[str], list[str] | None] | None:
    """ハーネス節内の最初の判定表から判定列と質問列を返す。

    dig はハーネス表と工程表を同じ節に持つため、節全体ではなく表単位で切る。
    setup / repo-loop は先頭列が `親` で判定列が 2 列目なので、列名で選ぶ。
    質問列はヘッダに `質問` を含む最初の列。無ければ第 2 要素が None。
    """
    lines = section.splitlines()
    for index, line in enumerate(lines):
        if not line.startswith("|"):
            continue
        header = _cells(line)
        decision_col = next(
            (i for i, name in enumerate(header) if "判定" in name or "条件" in name),
            None,
        )
        if decision_col is None or index + 1 >= len(lines):
            continue
        question_col = next(
            (i for i, name in enumerate(header) if "質問" in name),
            None,
        )
        decision: list[str] = []
        question: list[str] | None = [] if question_col is not None else None
        for row in lines[index + 2 :]:
            if not row.startswith("|"):
                break
            cells = _cells(row)
            decision.append(cells[decision_col] if len(cells) > decision_col else "")
            if question is not None and question_col is not None:
                question.append(
                    cells[question_col] if len(cells) > question_col else ""
                )
        return decision, question
    return None


def _docs_with_decision_tables(docs: Docs) -> dict[str, list[str]]:
    """判定列だけを返す。レジストリ完全性 meta-test 用。"""
    found: dict[str, list[str]] = {}
    for path in _skill_paths(docs):
        if path in UNCHECKED_HARNESS_DOCS:
            continue
        section = _harness_section(docs.get(path, ""))
        if section is None:
            continue
        columns = _harness_table_columns(section)
        if columns is not None:
            found[path] = columns[0]
    return found


def _backtick_identifiers(cell: str) -> frozenset[str]:
    """セル内の backtick で囲まれた識別子だけを集める。

    dig の 2 行目は否定形として AskUserQuestion を裸で含む。裸トークンを拾うと
    集合が壊れ、dig だけが落ちる。囲まれたものだけを識別子とする。
    """
    return frozenset(BACKTICK_IDENTIFIER.findall(cell))


# 判定列の行ごとの識別子集合。文言は文書ごとに揺れるが、構成は 10 本で一致する。
EXPECTED_DECISION_IDS = (
    frozenset({"AskUserQuestion"}),
    frozenset({"spawn_agent"}),
    frozenset(),
)
# 質問列の比較対象は harness の 3 ツールだけ。EnterPlanMode 等は承認手段なので含めない。
HARNESS_QUESTION_TOOLS = ("AskUserQuestion", "spawn_agent", "request_user_input")
EXPECTED_QUESTION_IDS = (
    frozenset({"AskUserQuestion"}),
    frozenset({"request_user_input"}),
    frozenset(),
)


def _has_identifier(text: str, identifier: str) -> bool:
    """完全な識別子だけを単語境界で検出する。

    premises.json の value_patterns と同じ前後読みを使う。部分文字列一致だと
    LegacyAskUserQuestion のように前後に文字が付いた別識別子でもヒットする。
    """
    return (
        re.search(
            rf"(?<![A-Za-z0-9_]){re.escape(identifier)}(?![A-Za-z0-9_])",
            text,
        )
        is not None
    )


def _question_tool_ids(cell: str) -> frozenset[str]:
    """質問セルから harness の 3 ツールを backtick 不問で集める。

    判定列と違い、質問セルは文書ごとに backtick の有無が揺れる
    (裸の AskUserQuestion と `AskUserQuestion` が混在)。囲みを要求すると
    片方の文書群だけが落ちる。3 ツール以外は比較対象にしない。
    一致は `_has_identifier`（premises.json と同じ単語境界）で取る。
    """
    return frozenset(
        tool for tool in HARNESS_QUESTION_TOOLS if _has_identifier(cell, tool)
    )


def check_harness_decision_table_excludes_request_user_input(
    docs: Docs,
) -> list[str]:
    """判定表の判定セル・質問セルを識別子集合で固定する。

    位置関係（節冒頭の禁止文の有無）では成立しない。ハーネス節の見出しが
    3 形式に分かれ、しかも `request_user_input` が節冒頭の禁止文に現れる文書が
    複数あるため、判定表のセルを直接見る。
    """
    problems: list[str] = []

    for path in _skill_paths(docs):
        if path in UNCHECKED_HARNESS_DOCS:
            continue
        section = _harness_section(docs.get(path, ""))
        if section is None:
            problems.append(f"{path}: ハーネス節がちょうど 1 つでない")
            continue
        columns = _harness_table_columns(section)
        if columns is None:
            problems.append(f"{path}: ハーネス判定表がない")
            continue
        cells, questions = columns
        # 性質 1: データ行はちょうど 3 行。
        if len(cells) != 3:
            problems.append(f"{path}: 判定表のデータ行が 3 行でない: {cells}")
            continue
        # 性質 2: 判定列は行ごとの backtick 識別子集合で固定する。
        # 文言（が使える / が利用可能な 等）は文書ごとに揺れるが、識別子構成は
        # 10 本で一致する。揺れる部分ではなく揃っている部分を見る。
        for index, (cell, expected) in enumerate(
            zip(cells, EXPECTED_DECISION_IDS, strict=True), start=1
        ):
            actual = _backtick_identifiers(cell)
            if actual != expected:
                problems.append(
                    f"{path}: 判定セル {index} の識別子集合が {sorted(expected)} "
                    f"でない: {sorted(actual)} ({cell})"
                )
        # 性質 3: 判定セルに request_user_input を判定キーとして書かない。
        # backtick 無しの混入も拒否する（集合等価は囲み付きだけを見るため）。
        # 検出は `_has_identifier` で行い、legacy_request_user_input 等の部分一致を避ける。
        for index, cell in enumerate(cells, start=1):
            if _has_identifier(cell, "request_user_input"):
                problems.append(
                    f"{path}: 判定セル {index} に request_user_input がある: {cell}"
                )
        # 性質 4: 質問列も行ごとのツール識別子集合で固定する。
        # 包含判定だと余計なツールを足す退行が通る。文言は揺れても識別子構成は揃う。
        if questions is None:
            problems.append(f"{path}: ハーネス表に質問列がない")
        elif len(questions) != 3:
            problems.append(f"{path}: 質問列のデータ行が 3 行でない: {questions}")
        else:
            for index, (cell, expected) in enumerate(
                zip(questions, EXPECTED_QUESTION_IDS, strict=True), start=1
            ):
                actual = _question_tool_ids(cell)
                if actual != expected:
                    problems.append(
                        f"{path}: 質問セル {index} のツール集合が {sorted(expected)} "
                        f"でない: {sorted(actual)} ({cell})"
                    )

    return problems


def targets_harness_decision_table_excludes_request_user_input(docs: Docs) -> int:
    return sum(1 for path in _skill_paths(docs) if path not in UNCHECKED_HARNESS_DOCS)


def mutate_harness_injects_request_user_input_into_cell(docs: Docs) -> Docs:
    """判定セルへ request_user_input を挿入する（性質 3）。"""
    return _replace_once(
        docs,
        HANDOFF,
        "| `AskUserQuestion` が使える Claude 親 |",
        "| `AskUserQuestion` / `request_user_input` が使える Claude 親 |",
    )


def mutate_harness_injects_spawn_agent_into_first_row(docs: Docs) -> Docs:
    """1 行目の判定セルへ spawn_agent を混入させる（性質 2）。"""
    return _replace_once(
        docs,
        HANDOFF,
        "| `AskUserQuestion` が使える Claude 親 |",
        "| `AskUserQuestion` または `spawn_agent` が使える Claude 親 |",
    )


def mutate_harness_injects_extra_decision_id_into_first_row(docs: Docs) -> Docs:
    """1 行目の判定セルへ別識別子を追加する（性質 2 の集合等価）。"""
    return _replace_once(
        docs,
        HANDOFF,
        "| `AskUserQuestion` が使える Claude 親 |",
        "| `AskUserQuestion` または `BrowserTool` が使える Claude 親 |",
    )


def mutate_harness_injects_capability_into_fallback_row(docs: Docs) -> Docs:
    """3 行目のフォールバックへ識別子参照を持ち込む（性質 2）。"""
    return _replace_once(
        docs,
        HANDOFF,
        "| 判定不能 | 選択肢付き自由文 |",
        "| `BrowserTool` が利用可能な Browser 親 | 選択肢付き自由文 |",
    )


def mutate_harness_drops_ask_user_question_from_claude_row(docs: Docs) -> Docs:
    """Claude 親行の質問セルから AskUserQuestion を外す（性質 4）。"""
    return _replace_once(
        docs,
        HANDOFF,
        "| `AskUserQuestion` が使える Claude 親 | AskUserQuestion |",
        "| `AskUserQuestion` が使える Claude 親 | 選択肢付き自由文 |",
    )


def mutate_harness_adds_request_user_input_to_claude_question(docs: Docs) -> Docs:
    """Claude 親行の質問セルへ request_user_input を足す（性質 4 の集合等価）。"""
    return _replace_once(
        docs,
        HANDOFF,
        "| `AskUserQuestion` が使える Claude 親 | AskUserQuestion |",
        "| `AskUserQuestion` が使える Claude 親 | AskUserQuestion / request_user_input |",
    )


def mutate_harness_renames_ask_user_question_to_legacy_in_claude_question(
    docs: Docs,
) -> Docs:
    """Claude 親行の質問セルを LegacyAskUserQuestion へ改名する（性質 4 の単語境界）。"""
    return _replace_once(
        docs,
        HANDOFF,
        "| `AskUserQuestion` が使える Claude 親 | AskUserQuestion |",
        "| `AskUserQuestion` が使える Claude 親 | LegacyAskUserQuestion |",
    )


def mutate_harness_drops_request_user_input_from_codex_row(docs: Docs) -> Docs:
    """Codex 親行の質問セルから request_user_input を落とす（性質 4）。"""
    return _replace_once(
        docs,
        HANDOFF,
        "| それがなく `spawn_agent` が使える Codex 親 | "
        "plan mode は `request_user_input`、通常 mode は選択肢付き自由文 |",
        "| それがなく `spawn_agent` が使える Codex 親 | "
        "plan mode、通常 mode は選択肢付き自由文 |",
    )


def mutate_harness_adds_ask_user_question_to_codex_question(docs: Docs) -> Docs:
    """Codex 親行の質問セルへ AskUserQuestion を足す（性質 4 の集合等価）。"""
    return _replace_once(
        docs,
        HANDOFF,
        "| それがなく `spawn_agent` が使える Codex 親 | "
        "plan mode は `request_user_input`、通常 mode は選択肢付き自由文 |",
        "| それがなく `spawn_agent` が使える Codex 親 | "
        "plan mode は `request_user_input` / AskUserQuestion、通常 mode は選択肢付き自由文 |",
    )


def mutate_harness_injects_request_user_input_into_fallback_question(
    docs: Docs,
) -> Docs:
    """フォールバック行の質問セルへ request_user_input を混入させる（性質 4）。"""
    return _replace_once(
        docs,
        HANDOFF,
        "| 判定不能 | 選択肢付き自由文 |",
        "| 判定不能 | `request_user_input` |",
    )


def mutate_harness_swaps_decision_rows(docs: Docs) -> Docs:
    """1 行目と 2 行目の判定セルを入れ替える（性質 2）。"""
    return _swap_once(
        docs,
        HANDOFF,
        "| `AskUserQuestion` が使える Claude 親 |",
        "| それがなく `spawn_agent` が使える Codex 親 |",
    )


def mutate_harness_drops_decision_row(docs: Docs) -> Docs:
    """データ行を 1 行削除する（性質 1）。"""
    return _replace_once(
        docs,
        HANDOFF,
        "| 判定不能 | 選択肢付き自由文 |\n",
        "",
    )


def mutate_harness_drops_section_heading(docs: Docs) -> Docs:
    """ハーネス節の見出しごと削除する（性質 1 またはレジストリ完全性）。"""
    return _replace_once(docs, HANDOFF, "## ハーネス・進捗\n\n", "")


# ---------------------------------------------------------------------------
# B6: 書き込み境界の禁止 / 許可集合を集合等価で固定する
# ---------------------------------------------------------------------------

def _split_boundary_items(text: str) -> frozenset[str]:
    """読点・中黒・` / ` で分割して集合化する。"""
    items: list[str] = []
    for part in text.split("、"):
        for mid in part.split("・"):
            for piece in mid.split(" / "):
                cleaned = piece.strip().strip("。")
                if cleaned:
                    items.append(cleaned)
    return frozenset(items)


# (path, 節見出し, 禁止操作の期待集合, 許可書き込みの期待集合)
# 期待集合は実本文を分割規則で起こした値。実装に合わせて緩めない。
WRITE_BOUNDARY_DOCS: tuple[tuple[str, str, frozenset[str], frozenset[str]], ...] = (
    (
        GOAL_PROMPT,
        "## 禁止事項",
        frozenset(
            {
                "コード実装",
                "PR",
                "commit",
                "push",
                "計画レビュー",
                "独立レビュー",
                "Claude Code 組み込み `/goal` の自動発動",
                "scheduler",
                "loop 登録",
                "thought-db 書き込み",
            }
        ),
        frozenset({"Goal ファイルと専用 `.gitignore` の作成"}),
    ),
    (
        HANDOFF,
        "## 書き込み契約",
        frozenset({"既存ファイルの編集", "削除", "commit", "push"}),
        frozenset({"handoff と必要な専用 `.gitignore` の新規 Write"}),
    ),
)


def _boundary_sets(body: str) -> tuple[frozenset[str], frozenset[str]]:
    """節から禁止操作集合と許可書き込み集合を取り出す。"""
    prohibited: set[str] = set()
    allowed: set[str] = set()
    for match in re.finditer(r"([^。\n]*を(?:行わない|しない)。)", body):
        sentence = match.group(1)
        content = re.sub(r"を(?:行わない|しない)。$", "", sentence)
        # 「X以外は行わず、Yをしない」は Y だけが禁止集合。
        if "以外は行わず" in content:
            content = content.split("以外は行わず", 1)[1].lstrip("、")
        content = re.sub(r"^[-*]\s*", "", content.strip())
        prohibited |= _split_boundary_items(content)
    for match in re.finditer(r"([^。\n]*)以外は(?:変更しない|行わず)", body):
        prefix = re.sub(r"^[-*]\s*", "", match.group(1).strip())
        allowed |= _split_boundary_items(prefix)
    return frozenset(prohibited), frozenset(allowed)


def check_write_boundary_sets_are_exact(docs: Docs) -> list[str]:
    """書き込み境界の禁止 / 許可集合を登録値と完全一致させる。

    `assert "commit" in prohibitions` のような部分集合検査は項目の削除しか
    検出できない。集合等価にして追加も削除も検出する。

    許可文・例外句の意味判定はここでは行わない。言い回しは列挙しきれず
    check として収束しないため、構造（抽出集合の一致と節の存在）だけを見る。
    """
    problems: list[str] = []
    for path, heading, expected_prohibited, expected_allowed in WRITE_BOUNDARY_DOCS:
        text = docs.get(path)
        if text is None:
            problems.append(f"{path}: 対象文書が存在しない")
            continue
        body = _section_body(text, heading)
        if not body:
            # 節ごと消える退行を見逃さない。
            problems.append(f"{path}: {heading} がない")
            continue
        prohibited, allowed = _boundary_sets(body)
        if prohibited != expected_prohibited:
            problems.append(
                f"{path}: 禁止操作集合が期待と違う: "
                f"missing={sorted(expected_prohibited - prohibited)}, "
                f"extra={sorted(prohibited - expected_prohibited)}"
            )
        if allowed != expected_allowed:
            problems.append(
                f"{path}: 許可書き込み集合が期待と違う: "
                f"missing={sorted(expected_allowed - allowed)}, "
                f"extra={sorted(allowed - expected_allowed)}"
            )
    return problems


def targets_write_boundary_sets_are_exact(docs: Docs) -> int:
    return len(WRITE_BOUNDARY_DOCS)


def mutate_write_boundary_drops_prohibition(docs: Docs) -> Docs:
    """禁止項目を 1 つ削除する。"""
    return _replace_once(
        docs,
        GOAL_PROMPT,
        "コード実装、PR、commit、push、",
        "コード実装、PR、push、",
    )


def mutate_write_boundary_adds_exception(docs: Docs) -> Docs:
    """禁止列から項目を外して抽出集合を狭める。

    集合差分で落ちる。例外句の文言そのものを検出しているわけではない。
    """
    return _replace_once(
        docs,
        GOAL_PROMPT,
        "コード実装、PR、commit、push、計画レビュー、独立レビュー、"
        "Claude Code 組み込み `/goal` の自動発動、scheduler / loop 登録、"
        "thought-db 書き込みを行わない。",
        "コード実装、PR、push、計画レビュー、独立レビュー、"
        "Claude Code 組み込み `/goal` の自動発動、scheduler / loop 登録、"
        "thought-db 書き込みを行わない。ただし承認があれば commit してよい。",
    )


def mutate_write_boundary_adds_allowed_write(docs: Docs) -> Docs:
    """許可書き込み集合へ 1 つ追加する。"""
    return _replace_once(
        docs,
        GOAL_PROMPT,
        "Goal ファイルと専用 `.gitignore` の作成以外は変更しない。",
        "Goal ファイルと専用 `.gitignore` の作成、premises.json の更新以外は変更しない。",
    )


def mutate_write_boundary_drops_section(docs: Docs) -> Docs:
    """節ごと削除する。"""
    return _replace_once(docs, GOAL_PROMPT, "## 禁止事項\n\n", "")


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
    "fixed_backend_assignment": Check(
        run=check_fixed_backend_assignment,
        mutate=mutate_fixed_backend_assignment,
        extra_mutations=(
            mutate_fixed_backend_assignment_swaps_review,
            mutate_fixed_backend_assignment_drops_fallback,
            mutate_fixed_backend_assignment_drops_review_lane,
            mutate_fixed_backend_assignment_duplicates_role,
            mutate_fixed_backend_assignment_duplicates_parent,
        ),
        targets=targets_fixed_backend_assignment,
        category="B4",
        why="backend の固定割り当てとフォールバック順序の退行を防ぐ",
    ),
    "repair_loop_stop_conditions": Check(
        run=check_repair_loop_stop_conditions,
        mutate=mutate_repair_loop_stop_conditions,
        extra_mutations=(
            mutate_repair_loop_stop_conditions_drops_recurrence,
            mutate_repair_loop_stop_conditions_shifts_backstop,
            mutate_repair_loop_stop_conditions_shifts_streak,
            mutate_repair_loop_stop_conditions_drops_zero_exit,
        ),
        targets=targets_repair_loop_stop_conditions,
        category="B5",
        why="3 スキルへ散った修正ループ停止条件のドリフトを防ぐ",
    ),
    "harness_decision_table_excludes_request_user_input": Check(
        run=check_harness_decision_table_excludes_request_user_input,
        mutate=mutate_harness_injects_request_user_input_into_cell,
        extra_mutations=(
            mutate_harness_injects_spawn_agent_into_first_row,
            mutate_harness_injects_extra_decision_id_into_first_row,
            mutate_harness_injects_capability_into_fallback_row,
            mutate_harness_drops_ask_user_question_from_claude_row,
            mutate_harness_adds_request_user_input_to_claude_question,
            mutate_harness_renames_ask_user_question_to_legacy_in_claude_question,
            mutate_harness_drops_request_user_input_from_codex_row,
            mutate_harness_adds_ask_user_question_to_codex_question,
            mutate_harness_injects_request_user_input_into_fallback_question,
            mutate_harness_swaps_decision_rows,
            mutate_harness_drops_decision_row,
            mutate_harness_drops_section_heading,
        ),
        targets=targets_harness_decision_table_excludes_request_user_input,
        category="B8",
        why="request_user_input をハーネス判定キーへ格上げする退行を防ぐ",
    ),
    "write_boundary_sets_are_exact": Check(
        run=check_write_boundary_sets_are_exact,
        mutate=mutate_write_boundary_drops_prohibition,
        extra_mutations=(
            mutate_write_boundary_adds_exception,
            mutate_write_boundary_adds_allowed_write,
            mutate_write_boundary_drops_section,
        ),
        targets=targets_write_boundary_sets_are_exact,
        category="B6",
        why="書き込み境界の禁止/許可集合への追加・削除を防ぐ",
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
    "B4",
    "B5",
    "B6",
    "B8",
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


def test_harness_registry_covers_all_skills():
    """判定表が取れた文書と UNCHECKED_HARNESS_DOCS の和が全 SKILL.md と一致する。

    新しいスキルを足したときに登録漏れが fail になり、未検査側への振り分け忘れを防ぐ。
    """
    skill_paths = set(_skill_paths(REAL_DOCS))
    table_docs = set(_docs_with_decision_tables(REAL_DOCS))
    unchecked = set(UNCHECKED_HARNESS_DOCS)
    assert table_docs.isdisjoint(unchecked), (
        f"判定表と未検査レジストリが重複: {sorted(table_docs & unchecked)}"
    )
    assert table_docs | unchecked == skill_paths, (
        "ハーネスレジストリが全 SKILL.md を覆っていない: "
        f"missing={sorted(skill_paths - (table_docs | unchecked))}, "
        f"extra={sorted((table_docs | unchecked) - skill_paths)}"
    )
