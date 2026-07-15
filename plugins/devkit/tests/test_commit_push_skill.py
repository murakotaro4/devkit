"""commit-push スキル(安全な分割 commit + push)の契約テスト."""

from __future__ import annotations

import ast
import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SKILL_PATH = REPO_ROOT / "plugins" / "devkit" / "skills" / "commit-push" / "SKILL.md"
OPENAI_YAML_PATH = (
    REPO_ROOT / "plugins" / "devkit" / "skills" / "commit-push" / "agents" / "openai.yaml"
)

EXPECTED_ALLOWED_TOOLS = [
    "Read",
    "Grep",
    "Glob",
    "Bash",
    "AskUserQuestion",
    "request_user_input",
    "TaskCreate",
    "TaskUpdate",
]

COMMIT_CONTRACT_STRINGS = (
    "論理グループは最大 5 個とする。",
    "commit 前に、分割案（論理グループ・対象ファイル・コミットメッセージ案・解決済み push 先）を提示し、ユーザー承認を得る。",
    "バイナリ・巨大ファイルは内容検査不能として、承認前に明示する。",
    "`git add -A` / `git add .` / `git commit -a` を禁止する。",
    "add は `git --literal-pathspecs add -- <paths>` のみを使う。",
    "`--literal-pathspecs` は pathspec magic と glob 展開を無効化する。",
    "`--` はオプション終端であり path を literal 化しないため、`--literal-pathspecs` を必須とする。",
    "`--no-verify` などによる hook 迂回を禁止する。",
    "開始時に既存の staged 変更があれば停止する。",
    "グループ単位で、index 空確認 → literal add → `git diff --cached --name-only` の完全一致確認 → commit → `git show --name-only --format= HEAD` で照合、という 5 段階検証を行う。",
)

SECRET_CONTRACT_STRINGS = (
    "パス層では secret-like path を対象から外して報告する。",
    "内容層では commit 直前に staged diff へ既知パターン検査を行う。",
    "内容層で secret を検出した場合は、自動除外して続行せず停止する。",
)

PUSH_CONTRACT_STRINGS = (
    "push 前に `git rev-parse --abbrev-ref --symbolic-full-name @{u}` で upstream を解決し、承認提示に含める。",
    "push は `git push <remote> HEAD:<branch>` の明示単一 refspec のみを使う。",
    "force push・`--tags`・複数 ref を禁止する。",
    "upstream 不在・detached HEAD・origin なしでは push せず停止して報告する。",
    "push reject 時は fetch して状況を報告し、自動 rebase しない。",
)

SHARED_CONTRACT_STRINGS = (
    "共通動作の正本として devkit リポジトリの `AGENTS.md`「スキル共通契約」を参照する。",
    "## ハーネス判定",
    "`AskUserQuestion` が使える → Claude 親。",
    "`AskUserQuestion` がなく `spawn_agent` が使える → Codex 親。",
    "## 質問手段",
    "Claude 親: `AskUserQuestion`",
    "Codex 親 plan mode: `request_user_input`",
    "Codex 親通常 mode / 判定不能: 選択肢を箇条書きで提示して自由文回答を求める",
    "## タスクリスト連動",
    "Claude 親: `TaskCreate` / `TaskUpdate` が利用可能なら、workflow の step を登録し開始時 `in_progress`・完了時 `completed` に更新する。",
    "Codex 親: 組み込み plan 機能または通常の進捗報告で同等の進捗提示を行う。",
)


def _skill_text() -> str:
    return SKILL_PATH.read_text(encoding="utf-8")


def _frontmatter() -> str:
    text = _skill_text()
    match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    assert match, "frontmatter が見つからない"
    return match.group(1)


def test_skill_exists():
    assert SKILL_PATH.exists(), "commit-push の SKILL.md が存在しない"


def test_agents_openai_yaml_exists():
    assert OPENAI_YAML_PATH.exists(), "commit-push の agents/openai.yaml が存在しない"


def test_skill_frontmatter_allowed_tools_contract():
    frontmatter = _frontmatter()
    allowed_tools_match = re.search(r"allowed-tools:\s*(\[[^\n]*\])", frontmatter)
    assert allowed_tools_match, "allowed-tools が見つからない"
    actual_tools = ast.literal_eval(allowed_tools_match.group(1))
    assert actual_tools == EXPECTED_ALLOWED_TOOLS


def test_commit_contract():
    text = _skill_text()
    for contract in COMMIT_CONTRACT_STRINGS:
        assert contract in text


def test_secret_two_layer_contract():
    text = _skill_text()
    for contract in SECRET_CONTRACT_STRINGS:
        assert contract in text


def test_push_contract():
    text = _skill_text()
    for contract in PUSH_CONTRACT_STRINGS:
        assert contract in text


def test_shared_skill_contract():
    text = _skill_text()
    for contract in SHARED_CONTRACT_STRINGS:
        assert contract in text
