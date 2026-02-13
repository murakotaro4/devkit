#!/usr/bin/env python3
"""
Amazon.co.jp search/dp scraper via agent-browser + Chrome CDP.

Safety constraints:
- Do NOT dump HTML, cookies, account, address, order history, etc.
- Output only minimal product metadata (ASIN/title/price/rating/reviewCount, bullets/tech/details).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
import tempfile
import urllib.parse
from pathlib import Path
from typing import Any


ASIN_RE = re.compile(r"^[A-Z0-9]{10}$")


def now_ts() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def die(msg: str, code: int = 1) -> None:
    print(msg, file=sys.stderr)
    raise SystemExit(code)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_json_atomic(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_dir = path.parent
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=tmp_dir, delete=False) as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")
        tmp_path = Path(f.name)
    tmp_path.replace(path)


def parse_int_from_text(s: str | None) -> int | None:
    if not s:
        return None
    digits = re.sub(r"[^0-9]", "", s)
    return int(digits) if digits else None


def parse_price_jpy(price_txt: str | None) -> int | None:
    return parse_int_from_text(price_txt)


def parse_rating(rating_txt: str | None) -> float | None:
    if not rating_txt:
        return None
    nums = [float(x) for x in re.findall(r"([0-9]+(?:\.[0-9]+)?)", rating_txt)]
    nums = [n for n in nums if 0.0 <= n <= 5.0]
    if not nums:
        return None
    if len(nums) == 1:
        return nums[0]
    # Many locales include the max score "5" in the same string; pick the other value.
    others = [n for n in nums if abs(n - 5.0) > 1e-9]
    return others[0] if others else nums[0]


def parse_review_count(rc_txt: str | None) -> int | None:
    if not rc_txt:
        return None
    s = rc_txt.strip()
    s = s.strip("()（）").replace(",", "")

    m = re.match(r"^([0-9]+(?:\.[0-9]+)?)\s*万", s)
    if m:
        return int(float(m.group(1)) * 10000)

    return parse_int_from_text(s)


def normalize_asin(asin: str | None) -> str | None:
    if not asin:
        return None
    a = asin.strip().upper()
    return a if ASIN_RE.match(a) else None


def normalize_dp_url(domain_origin: str, asin: str | None) -> str | None:
    a = normalize_asin(asin)
    if not a:
        return None
    return f"{domain_origin}/dp/{a}"


def run_agent_browser(cdp: int, args: list[str], json_out: bool = True) -> dict[str, Any] | None:
    cmd = ["agent-browser", "--cdp", str(cdp)]
    if json_out:
        cmd.append("--json")
    cmd += args

    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if proc.returncode != 0:
        die(f"agent-browser failed ({proc.returncode}): {' '.join(cmd)}\n{proc.stderr.strip()}")

    if not json_out:
        return None

    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        die(f"agent-browser JSON parse error: {e}\n--- stdout ---\n{proc.stdout[:2000]}")


def ab_open_and_eval(*, cdp: int, url: str, wait_ms: int, js: str) -> Any:
    run_agent_browser(cdp, ["open", url], json_out=True)
    run_agent_browser(cdp, ["wait", str(wait_ms)], json_out=True)
    out = run_agent_browser(cdp, ["eval", js], json_out=True)
    if not out or not out.get("success"):
        die(f"agent-browser eval failed: {out}")
    return out.get("data", {}).get("result")


def build_search_url(domain_origin: str, query: str, page: int) -> str:
    # Keep it simple: /s?k=...&page=...
    q = urllib.parse.quote_plus(query)
    if page <= 1:
        return f"{domain_origin}/s?k={q}"
    return f"{domain_origin}/s?k={q}&page={page}"


def cmd_search(args: argparse.Namespace) -> int:
    domain_origin = f"https://{args.domain}"
    js = read_text(Path(args.script_dir) / "extract_search.js")

    queries: list[str] = args.query
    pages: int = args.pages
    wait_ms: int = args.wait_ms
    cdp: int = args.cdp

    all_candidates: list[dict[str, Any]] = []
    page_logs: list[dict[str, Any]] = []

    for q in queries:
        for page in range(1, pages + 1):
            url = build_search_url(domain_origin, q, page)
            result = ab_open_and_eval(cdp=cdp, url=url, wait_ms=wait_ms, js=js)

            items = result if isinstance(result, list) else []
            page_logs.append(
                {
                    "query": q,
                    "page": page,
                    "url": url,
                    "count": len(items),
                }
            )

            for it in items:
                if not isinstance(it, dict):
                    continue
                asin = normalize_asin(it.get("asin"))
                if not asin:
                    continue

                title = it.get("title") if isinstance(it.get("title"), str) else None
                price_txt = it.get("priceTxt") if isinstance(it.get("priceTxt"), str) else None
                rating_txt = it.get("ratingTxt") if isinstance(it.get("ratingTxt"), str) else None
                rc_txt = it.get("rcTxt") if isinstance(it.get("rcTxt"), str) else None
                rank = it.get("rank") if isinstance(it.get("rank"), int) else None

                all_candidates.append(
                    {
                        "asin": asin,
                        "title": title,
                        "url": normalize_dp_url(domain_origin, asin),
                        "priceTxt": price_txt,
                        "ratingTxt": rating_txt,
                        "rcTxt": rc_txt,
                        "price": parse_price_jpy(price_txt),
                        "rating": parse_rating(rating_txt),
                        "reviewCount": parse_review_count(rc_txt),
                        "query": q,
                        "page": page,
                        "rank": rank,
                    }
                )

    total_candidates = len(all_candidates)

    by_asin: dict[str, dict[str, Any]] = {}
    for it in all_candidates:
        asin = it["asin"]
        if asin not in by_asin:
            by_asin[asin] = it

    out_obj = {
        "at": now_ts(),
        "domain": args.domain,
        "queries": queries,
        "pages": page_logs,
        "total_candidates": total_candidates,
        "total_unique_asin": len(by_asin),
        "items": list(by_asin.values()),
    }

    if args.out:
        write_json_atomic(Path(args.out), out_obj)
    else:
        json.dump(out_obj, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")

    return 0


def cmd_dp(args: argparse.Namespace) -> int:
    domain_origin = f"https://{args.domain}"
    js = read_text(Path(args.script_dir) / "extract_dp.js")

    cdp: int = args.cdp
    wait_ms: int = args.wait_ms
    cap: int = args.cap

    src_path: str | None = args.input

    asins: list[str] = []
    if args.asin:
        for a in args.asin:
            na = normalize_asin(a)
            if na and na not in asins:
                asins.append(na)
    elif src_path:
        data = json.loads(Path(src_path).read_text(encoding="utf-8"))
        items = data.get("items", [])
        if not isinstance(items, list):
            die("input JSON format error: items must be list")
        for it in items:
            if not isinstance(it, dict):
                continue
            na = normalize_asin(it.get("asin"))
            if na and na not in asins:
                asins.append(na)
    else:
        die("dp: --in または --asin が必要です")

    asins = asins[:cap]

    out_path = Path(args.out) if args.out else None

    existing: dict[str, Any] | None = None
    done_asins: set[str] = set()
    if out_path and args.resume and out_path.exists():
        try:
            existing = json.loads(out_path.read_text(encoding="utf-8"))
            ex_items = existing.get("items", [])
            if isinstance(ex_items, list):
                for it in ex_items:
                    if isinstance(it, dict):
                        na = normalize_asin(it.get("asin"))
                        if na:
                            done_asins.add(na)
        except Exception:
            # If broken, ignore and overwrite.
            existing = None
            done_asins = set()

    out_items: list[dict[str, Any]] = []
    if existing and isinstance(existing.get("items"), list):
        out_items = [it for it in existing["items"] if isinstance(it, dict)]

    def flush_partial() -> None:
        if not out_path:
            return
        out_obj = {
            "at": now_ts(),
            "domain": args.domain,
            "src": src_path,
            "cap": cap,
            "items": out_items,
        }
        write_json_atomic(out_path, out_obj)

    for asin in asins:
        if asin in done_asins:
            continue

        url = normalize_dp_url(domain_origin, asin)
        if not url:
            continue

        result = ab_open_and_eval(cdp=cdp, url=url, wait_ms=wait_ms, js=js)
        if not isinstance(result, dict):
            out_items.append({"asin": asin, "url": url, "error": "unexpected_result"})
            flush_partial()
            continue

        # Ensure minimal keys and normalized URL.
        item: dict[str, Any] = dict(result)
        item["asin"] = normalize_asin(item.get("asin")) or asin
        item["url"] = normalize_dp_url(domain_origin, item["asin"]) or url

        price_txt = item.get("priceTxt") if isinstance(item.get("priceTxt"), str) else None
        rating_txt = item.get("ratingTxt") if isinstance(item.get("ratingTxt"), str) else None
        rc_txt = item.get("reviewCountTxt") if isinstance(item.get("reviewCountTxt"), str) else None
        item["price"] = parse_price_jpy(price_txt)
        item["rating"] = parse_rating(rating_txt)
        item["reviewCount"] = parse_review_count(rc_txt)

        out_items.append(item)
        flush_partial()

        if item.get("error") == "captcha":
            # Fail-fast: continuing will just keep failing.
            flush_partial()
            die(
                "CAPTCHA/Robot Check を検出しました。ChromeのGUIで解いてから再実行してください（途中までの出力は保存済み）。",
                code=2,
            )

    out_obj = {
        "at": now_ts(),
        "domain": args.domain,
        "src": src_path,
        "cap": cap,
        "items": out_items,
    }

    if out_path:
        write_json_atomic(out_path, out_obj)
    else:
        json.dump(out_obj, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")

    return 0


def main(argv: list[str]) -> int:
    script_dir = Path(__file__).resolve().parent

    parser = argparse.ArgumentParser(prog="amazon_search.py")
    parser.set_defaults(func=None)
    parser.add_argument("--cdp", type=int, default=9222, help="CDP port (default: 9222)")
    parser.add_argument("--domain", default="www.amazon.co.jp", help="Target domain (default: www.amazon.co.jp)")
    parser.add_argument("--wait-ms", type=int, default=1200, help="Wait after open (ms)")
    parser.add_argument(
        "--script-dir",
        default=str(script_dir),
        help="Directory that contains extract_*.js (for dev/debug)",
    )

    sub = parser.add_subparsers(dest="cmd", required=True)

    p_search = sub.add_parser("search", help="Search results -> minimal JSON")
    p_search.add_argument("--query", action="append", required=True, help="Search query (repeatable)")
    p_search.add_argument("--pages", type=int, default=1, help="Pages per query (default: 1)")
    p_search.add_argument("--out", help="Output JSON path (default: stdout)")
    p_search.set_defaults(func=cmd_search)

    p_dp = sub.add_parser("dp", help="Product pages -> minimal JSON")
    p_dp.add_argument("--in", dest="input", help="Input search JSON path")
    p_dp.add_argument("--asin", action="append", help="ASIN (repeatable). Overrides --in if provided.")
    p_dp.add_argument("--cap", type=int, default=60, help="Max number of ASINs to fetch (default: 60)")
    p_dp.add_argument("--out", help="Output JSON path (default: stdout)")
    p_dp.add_argument(
        "--no-resume",
        dest="resume",
        action="store_false",
        default=True,
        help="Disable resume when --out exists (default: resume)",
    )
    p_dp.set_defaults(func=cmd_dp)

    ns = parser.parse_args(argv)

    if ns.func is None:
        die("no command")
    return int(ns.func(ns))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
