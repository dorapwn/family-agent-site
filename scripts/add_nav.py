#!/usr/bin/env python3
"""
add_nav.py — insert the new page into every <nav> bar, in canonical order.

The site has one canonical page order (scripts/check_pages.py -> NAV_ORDER).
Rather than hand-editing eleven nav bars, this rewrites each <nav> block from
that list, so the order can never drift.

Idempotent: running it twice changes nothing the second time.

Usage:  python3 scripts/add_nav.py
"""
from __future__ import annotations

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from check_pages import NAV_ORDER  # noqa: E402

LABELS = {
    "index.html": "← 返主頁",
    "study.html": "學業",
    "home.html": "家務",
    "work.html": "工作",
    "fun.html": "玩樂",
    "ai-guide.html": "用 AI 指南",
    "tips.html": "小技巧",
    "trouble.html": "常見問題",
    "telegram.html": "裝 Telegram",
    "wishlist.html": "許願清單",
    "behind.html": "幕後",
}


def nav_html(current: str) -> str:
    """The nav bar for a page: every other page, in canonical order."""
    parts = []
    for p in NAV_ORDER:
        if p == current:
            # A page links itself as a "you are here" marker.
            parts.append(f'<strong>{LABELS[p]}</strong>')
        else:
            parts.append(f'<a href="{p}">{LABELS[p]}</a>')
    return "  " + " ·\n  ".join(parts)


def rewrite(path: str) -> bool:
    src = open(path, encoding="utf-8").read()
    m = re.search(r'(<nav\b[^>]*>)(.*?)(</nav>)', src, re.S)
    if not m:
        return False
    new = m.group(1) + "\n" + nav_html(os.path.basename(path)) + "\n" + m.group(3)
    if new == m.group(0):
        return False
    out = src[:m.start()] + new + src[m.end():]
    open(path, "w", encoding="utf-8").write(out)
    return True


def main() -> int:
    changed = []
    for p in NAV_ORDER:
        f = os.path.join(ROOT, p)
        if os.path.exists(f) and rewrite(f):
            changed.append(p)
    print("nav updated in:", ", ".join(changed) if changed else "(nothing to do)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
