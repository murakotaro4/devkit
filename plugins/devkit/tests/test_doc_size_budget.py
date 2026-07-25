"""配布ドキュメントのサイズ上限（圧縮の巻き戻り防止 ratchet）。

2026-07-25 に Claude 5 世代のコンテキスト設計へ追従して 105,616 -> 56,717 字へ圧縮した。
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
    "plugins/devkit/skills/dig/SKILL.md": 12350,
    "plugins/devkit/skills/goal-prompt/SKILL.md": 2080,
    "plugins/devkit/skills/handoff/SKILL.md": 2440,
    "plugins/devkit/skills/improve-skill/SKILL.md": 4260,
    "plugins/devkit/skills/memory-review/SKILL.md": 4670,
    "plugins/devkit/skills/refactor/SKILL.md": 2690,
    "plugins/devkit/skills/repo-loop/SKILL.md": 9080,
    "plugins/devkit/skills/setup/SKILL.md": 6510,
}

TOTAL_BUDGET = 62_320


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


MAX_SLACK = 1.20  # 上限は実測の 20% 増しまで


def test_budgets_are_not_silently_slackened():
    """上限が実測から乖離していないこと（上限を上げるだけの回避を封じる）。

    上限は引き上げてよいが、引き上げた分だけ実測も増えていなければ通らない。
    これにより「先に上限を大きくしてから膨らませる」抜け道を塞ぐ。
    """
    slack = {
        path: (actual, budget)
        for path, budget in BUDGETS.items()
        if (actual := _chars(path)) * MAX_SLACK < budget
    }
    assert not slack, (
        f"上限が実測の {MAX_SLACK:.0%} を超えて緩んでいる。ratchet として機能していない: "
        + ", ".join(f"{p} 実測{a} vs 上限{b}" for p, (a, b) in sorted(slack.items()))
    )


def test_total_budget_is_not_silently_slackened():
    """合計上限も実測から乖離させない（個別だけ締めても合計で抜けられるため）。"""
    total = sum(_chars(path) for path in BUDGETS)
    assert TOTAL_BUDGET <= total * MAX_SLACK, (
        f"合計上限が実測の {MAX_SLACK:.0%} を超えて緩んでいる: "
        f"実測{total} vs 上限{TOTAL_BUDGET}"
    )


def test_total_budget_does_not_exceed_sum_of_file_budgets():
    """合計上限がファイル別上限の総和を超えないこと（二重の緩和を防ぐ）。"""
    assert TOTAL_BUDGET <= sum(BUDGETS.values()), (
        f"合計上限がファイル別上限の総和より緩い: "
        f"{TOTAL_BUDGET} > {sum(BUDGETS.values())}"
    )
