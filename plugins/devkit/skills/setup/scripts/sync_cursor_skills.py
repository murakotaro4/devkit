#!/usr/bin/env python3
"""One-release compatibility entrypoint for the v10.1.0 updater."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from prune_legacy_cursor_sync import dump_result, prune_legacy_cursor_sync


sys.dont_write_bytecode = True


def main() -> int:
    parser = argparse.ArgumentParser(description="Prune legacy DevKit Cursor skill sync assets.")
    parser.add_argument("--source", type=Path, help="Ignored v10.1.0 compatibility argument")
    parser.add_argument("--target", type=Path, default=Path.home() / ".cursor")
    parser.add_argument("--check", action="store_true", help="Report planned changes without writing files")
    parser.add_argument("--format", choices=["json"], default="json", help="Output format")
    args = parser.parse_args()

    changed, actions, reason = prune_legacy_cursor_sync(args.target, args.check)
    dump_result(changed, actions, reason=reason)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
