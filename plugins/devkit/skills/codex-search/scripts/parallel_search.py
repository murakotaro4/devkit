#!/usr/bin/env python3
"""並列Codex検索スクリプト"""

import asyncio
import argparse
import json
import sys


async def search(
    query: str, index: int, model: str, semaphore: asyncio.Semaphore
) -> dict:
    """単一のCodex検索を実行"""
    async with semaphore:
        proc = await asyncio.create_subprocess_exec(
            "codex",
            "--search",
            "exec",
            "-m",
            model,
            query,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        return {
            "index": index,
            "query": query,
            "success": proc.returncode == 0,
            "output": stdout.decode("utf-8", errors="replace"),
            "error": stderr.decode("utf-8", errors="replace")
            if proc.returncode != 0
            else "",
        }


async def main(queries: list[str], model: str, max_concurrent: int):
    """複数クエリを並列実行"""
    semaphore = asyncio.Semaphore(max_concurrent)
    tasks = [search(q, i, model, semaphore) for i, q in enumerate(queries, 1)]
    results = await asyncio.gather(*tasks)

    # 標準出力に結果を出力
    for r in results:
        status = "✓" if r["success"] else "✗"
        print(f"### [{status}] Query {r['index']}: {r['query']}\n")
        print(r["output"] if r["success"] else f"**Error:** {r['error']}")
        print("\n---\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="並列Codex検索")
    parser.add_argument("--queries", "-q", required=True, help="JSON配列のクエリ")
    parser.add_argument("--model", "-m", default="gpt-5.2", help="使用モデル")
    parser.add_argument(
        "--max-concurrent", "-c", type=int, default=5, help="最大同時実行数"
    )
    args = parser.parse_args()

    queries = json.loads(args.queries)
    if not queries:
        print("エラー: クエリが空です", file=sys.stderr)
        sys.exit(1)

    asyncio.run(main(queries, args.model, args.max_concurrent))
