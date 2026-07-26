"""配布ドキュメントサイズの telemetry 完全性検査。

これは ratchet（壁）ではなく、baseline 比レポートに現れないドキュメントを
作らないための検査である。判断記録は docs/reviews/2026-07-26-doc-size-telemetry.md。
"""

from __future__ import annotations

import json
from pathlib import Path

import report_doc_size


REPO_ROOT = Path(__file__).resolve().parents[3]
SKILLS_DIR = REPO_ROOT / "plugins" / "devkit" / "skills"


def _skill_docs() -> set[str]:
    """skills 配下の全 Markdown（Windows の "\\" 区切りは as_posix で正規化）。"""
    return {path.relative_to(REPO_ROOT).as_posix() for path in SKILLS_DIR.glob("**/*.md")}


def test_baseline_covers_every_distributed_markdown():
    docs = _skill_docs()
    assert docs <= set(report_doc_size.SIZE_BASELINE), (
        f"baseline 未登録の Markdown がある: {sorted(docs - set(report_doc_size.SIZE_BASELINE))}"
    )


def test_baseline_has_no_entry_for_missing_files():
    missing = sorted(
        path for path in report_doc_size.SIZE_BASELINE if not (REPO_ROOT / path).is_file()
    )
    assert not missing, f"実体の無い baseline 登録がある: {missing}"


def test_report_never_fails_on_oversized_doc(tmp_path, monkeypatch, capsys):
    """サイズ超過で終了コードが変わらないこと（超過分岐を実際に通す）。"""
    doc = tmp_path / "oversized.md"
    doc.write_text("x" * 100, encoding="utf-8")
    skills = tmp_path / "plugins" / "devkit" / "skills"
    skills.mkdir(parents=True)

    monkeypatch.setattr(report_doc_size, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        report_doc_size,
        "SIZE_BASELINE",
        {"oversized.md": 1},
    )
    monkeypatch.setattr(report_doc_size, "YAML_TOTAL_BASELINE", 0)

    assert report_doc_size.main([]) == 0
    captured = capsys.readouterr()
    assert "+9900.0%" in captured.out or "+9900%" in captured.out

    assert report_doc_size.main(["--format", "json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["baseline_commit"] == report_doc_size.BASELINE_COMMIT
    assert "markdown" in payload
    assert "markdown_total" in payload
    assert "yaml_total" in payload
    assert payload["markdown"][0]["path"] == "oversized.md"
    assert payload["markdown"][0]["baseline"] == 1
    assert payload["markdown"][0]["current"] == 100
    assert payload["markdown"][0]["delta"] == 99
    assert payload["markdown"][0]["delta_percent"] == 9900.0
    percents = [item["delta_percent"] for item in payload["markdown"]]
    assert percents == sorted(percents, reverse=True)


def test_report_fails_on_missing_baseline_file(tmp_path, monkeypatch):
    monkeypatch.setattr(report_doc_size, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        report_doc_size,
        "SIZE_BASELINE",
        {"missing.md": 10},
    )
    monkeypatch.setattr(report_doc_size, "YAML_TOTAL_BASELINE", 0)

    assert report_doc_size.main([]) != 0
