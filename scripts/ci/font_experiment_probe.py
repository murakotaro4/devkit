#!/usr/bin/env python3
# 実物の検出述語(setup_terminal_font.font_is_registered)で判定するプローブ
from __future__ import annotations

import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SETUP_SCRIPTS = REPO_ROOT / "plugins/devkit/skills/setup/scripts"
sys.path.insert(0, str(SETUP_SCRIPTS))

import setup_terminal_font  # noqa: E402


def main() -> int:
    names = setup_terminal_font.read_font_names(None)
    registered = setup_terminal_font.font_is_registered(names)
    payload = {
        "registered": registered,
        "font_face": setup_terminal_font.FONT_FACE,
        "names": names,
        "udev_names": [name for name in names if "udev" in name.lower()],
    }
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
