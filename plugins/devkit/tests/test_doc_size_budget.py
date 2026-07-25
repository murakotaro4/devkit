"""配布ドキュメントのサイズ上限（圧縮の巻き戻り防止 ratchet）。

2026-07-25 に Claude 5 世代のコンテキスト設計へ追従して 105,616 -> 54,465 字へ圧縮した。
一次記録は docs/reviews/2026-07-25-context-engineering-claude5.md。

この検査だけは本文の文言をミラーせず、サイズという不変条件だけを強制する。
上限は圧縮直後の実測値 + 約 10%。契約を足して超えた場合は、
「どこかを削って収める」か「上限を上げる判断を明示する」かをレビューで選ばせるのが狙い。
"""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]

# path -> 文字数上限（圧縮直後の実測 + 約 10%）
BUDGETS = {
    "AGENTS.md": 8720,
    "plugins/devkit/skills/backlog/SKILL.md": 2870,
    "plugins/devkit/skills/catch-up/SKILL.md": 3250,
    "plugins/devkit/skills/commit-push/SKILL.md": 3400,
    "plugins/devkit/skills/dig/SKILL.md": 10960,
    "plugins/devkit/skills/goal-prompt/SKILL.md": 2080,
    "plugins/devkit/skills/handoff/SKILL.md": 2440,
    "plugins/devkit/skills/improve-skill/SKILL.md": 4170,
    "plugins/devkit/skills/memory-review/SKILL.md": 4670,
    "plugins/devkit/skills/refactor/SKILL.md": 2690,
    "plugins/devkit/skills/repo-loop/SKILL.md": 8540,
    "plugins/devkit/skills/setup/SKILL.md": 6060,
}

TOTAL_BUDGET = 59_900


def _chars(relpath: str) -> int:
    return len((REPO_ROOT / relpath).read_text(encoding="utf-8"))


def test_every_distributed_doc_stays_within_budget():
    over = {
        path: (actual, budget)
        for path, budget in BUDGETS.items()
        if (actual := _chars(path)) > budget
    }
    assert not over, (
        "圧縮後のサイズ上限を超過している。契約を追加したなら他を削るか、"
        "上限引き上げを diff レビューで明示的に判断すること: "
        + ", ".join(f"{p} {a}>{b}" for p, (a, b) in sorted(over.items()))
    )


def test_total_distributed_doc_size_stays_within_budget():
    total = sum(_chars(path) for path in BUDGETS)
    assert total <= TOTAL_BUDGET, f"配布ドキュメント合計が上限超過: {total} > {TOTAL_BUDGET}"


def test_budget_covers_every_distributed_skill():
    """スキルを増やしたら上限登録も必須にする（登録漏れで ratchet が空洞化しないように）。"""
    skills = {
        str(path.relative_to(REPO_ROOT))
        for path in (REPO_ROOT / "plugins" / "devkit" / "skills").glob("*/SKILL.md")
    }
    assert skills <= set(BUDGETS), f"上限未登録の SKILL.md がある: {sorted(skills - set(BUDGETS))}"


def test_budgets_are_not_silently_slackened():
    """上限が実測から大きく乖離していないこと（緩めるだけの回避を検出する）。"""
    slack = {
        path: (actual, budget)
        for path, budget in BUDGETS.items()
        if (actual := _chars(path)) * 2 < budget
    }
    assert not slack, (
        "上限が実測の 2 倍以上に緩んでいる。ratchet として機能していない: "
        + ", ".join(f"{p} {a} vs {b}" for p, (a, b) in sorted(slack.items()))
    )
