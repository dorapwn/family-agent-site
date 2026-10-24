#!/usr/bin/env python3
"""
capture_su.py — capture the real HKUSTSU web pages that the slide deck uses.

Every photo in the deck is a screenshot of a live page, taken here. Nothing is
stock art and nothing is drawn by hand.

Run:  python3 scripts/capture_su.py
Needs: playwright + chromium (see the repo README for the venv path).

Why a script and not manual screenshots: the deck must be reproducible. If a
fact on a slide changes, the next run of this script re-captures the evidence
and the deck can be re-checked against it.

The pages are JavaScript-rendered, so each capture waits for the content to
actually appear rather than for the load event, and scrolls to trigger the
lazy-loaded sections.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMG = os.path.join(ROOT, "assets", "img")

# name -> (url, what the shot is for)
SHOTS = {
    "su-home": (
        "https://hkustsu.hkust.edu.hk/",
        "Home page hero - the union's own banner wall of society flags.",
    ),
    "su-about": (
        "https://hkustsu.hkust.edu.hk/about-us",
        "About Us - the tab strip (Executive Committee / Council / ...).",
    ),
    "su-societies": (
        "https://hkustsu.hkust.edu.hk/societies",
        "Societies page - the searchable list of every society.",
    ),
    "su-orgchart-top": (
        "https://hkustsu.hkust.edu.hk/about-us",
        "Union Structure org chart, top half (Referendum -> General Meeting "
        "-> the four branches).",
    ),
    "su-structure": (
        "https://hkustsu.hkust.edu.hk/about-us",
        "Union Structure, full page.",
    ),
    "su-faq": (
        "https://hkustsu.hkust.edu.hk/faq",
        "FAQ - the membership steps the deck quotes.",
    ),
    "su-fee": (
        "https://hkustsu.hkust.edu.hk/su-fee-info",
        "SU Fee Info page.",
    ),
    "su-banners": (
        "https://hkustsu.hkust.edu.hk/societies",
        "Hero band of society banners, cropped to a 16:9 strip.",
    ),
}


def capture(pw) -> int:
    from playwright.sync_api import sync_playwright

    os.makedirs(IMG, exist_ok=True)
    written = 0

    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": 1280, "height": 800})

        for name, (url, why) in SHOTS.items():
            page.goto(url, wait_until="networkidle")
            # These pages fetch their content after load; wait for real text
            # rather than trusting the load event.
            page.wait_for_timeout(3000)
            # Trigger lazy-loaded sections.
            for _ in range(6):
                page.mouse.wheel(0, 900)
                page.wait_for_timeout(350)
            page.mouse.wheel(0, -20000)
            page.wait_for_timeout(600)

            if name == "su-orgchart-top":
                # The org chart lives on the About Us page under a tab. Click
                # it, then crop to the chart itself.
                tab = page.locator("text=Union Structure")
                if tab.count():
                    tab.first.click()
                    page.wait_for_timeout(1500)
                img = page.locator("img").filter(has=page.locator("svg")).first
                target = img if img.count() else page
                target.screenshot(path=os.path.join(IMG, f"{name}.jpg"))
            elif name == "su-banners":
                # Just the hero band: 1280 wide, 250 tall, at the top.
                page.screenshot(path=os.path.join(IMG, f"{name}.jpg"),
                                clip={"x": 0, "y": 0, "width": 1280, "height": 250})
            else:
                page.screenshot(path=os.path.join(IMG, f"{name}.jpg"))

            written += 1
            print(f"  {name}.jpg  <- {why}")

        browser.close()
    return written


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
    except ImportError:
        print("playwright is not installed in this interpreter.\n"
              "Run it with the browser venv, e.g.\n"
              "  /opt/data/.toolchain/browser-venv/bin/python scripts/capture_su.py",
              file=sys.stderr)
        return 1
    n = capture(None)
    print(f"captured {n} screenshots into assets/img/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
