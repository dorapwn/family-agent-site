#!/usr/bin/env python3
"""
check_pages.py — pre-deploy gate for the static guide site.

Cheap structural checks that catch the bugs hand-edited HTML actually hits:
nested <p>, unbalanced non-void tags, dead local links, missing assets, and
Markdown bold syntax leaking into HTML (excluding DSE grade notation like 5**).

Usage:  python3 scripts/check_pages.py
Exit:   0 = clean, 1 = at least one error
"""
from __future__ import annotations

import os
import re
import sys
import xml.dom.minidom

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Tags that never have a closing tag.
VOID = {"img", "br", "hr", "meta", "link", "input", "source", "area", "col",
        "embed", "param", "track", "wbr"}

# Tags whose content is text-only, so <p> inside them would be invalid.
PHRASING = {"a", "b", "strong", "em", "i", "span", "code", "label", "small"}

CONTAINERS = ["html", "head", "body", "div", "figure", "figcaption", "table",
              "thead", "tbody", "tr", "ol", "ul", "li", "nav", "header",
              "footer", "section", "pre", "main", "h2", "h3", "p", "title"]

ASSETS = ["assets/four-rooms.mp4", "assets/img/poster.png",
          "assets/img/hkeaa-dse-dates.png", "assets/img/hermes-voice-mode.png",
          "assets/svg/mock-scores.svg", "assets/svg/flow-capture.svg",
          "assets/svg/flow-publish.svg", "assets/svg/flow-ascii.svg",
          "assets/ascii/four_rooms.py", "style.css"]

# Every page except 404 must be reachable from every other page's nav.
NAV_PAGES = ["index.html", "telegram.html", "behind.html", "wishlist.html",
             "study.html", "home.html", "work.html", "fun.html"]

errors: list[str] = []


def err(msg: str) -> None:
    errors.append(msg)


def pages() -> list[str]:
    out = []
    for f in sorted(os.listdir(ROOT)):
        if f.endswith(".html"):
            out.append(f)
    return out


def check_tag_balance(name: str, src: str) -> None:
    for tag in CONTAINERS:
        opens = len(re.findall(r"<%s(?=[\s>])" % tag, src))
        closes = len(re.findall(r"</%s\s*>" % tag, src))
        if opens != closes:
            err(f"{name}: <{tag}> {opens} open vs {closes} close")

    for tag in VOID:
        if re.search(r"</%s\s*>" % tag, src):
            err(f"{name}: </{tag}> is a void element, must not be closed")


def check_no_nested_p(name: str, src: str) -> None:
    """<p> cannot contain <p>. Walk the open/close sequence with a stack.

    Reports only the first offender: once a <p> nests, the stack stays
    desynced and every later <p> would be a false positive, burying the
    one line the author actually needs to fix.
    """
    stack: list[str] = []
    reported = False
    token = re.compile(r"<(/?)([a-zA-Z][a-zA-Z0-9]*)\b[^>]*?(/?)>")
    for m in token.finditer(src):
        closing, tag, selfclose = m.group(1), m.group(2).lower(), m.group(3)
        if tag in VOID or selfclose:
            continue
        if closing:
            if stack and stack[-1] == tag:
                stack.pop()
            elif tag in stack:
                while stack and stack.pop() != tag:
                    pass
            continue
        # opening tag
        if tag == "p" and "p" in stack and not reported:
            line = src.count("\n", 0, m.start()) + 1
            snippet = src[max(0, m.start() - 40):m.start() + 40].replace("\n", " ")
            err(f"{name}:{line}: nested <p> — ...{snippet}...")
            reported = True
        if tag not in PHRASING:
            stack.append(tag)


def check_markdown(name: str, src: str) -> None:
    # Strip code spans and <code> blocks first: a page may legitimately
    # quote the literal marker (e.g. documenting the very bug this checks).
    scannable = re.sub(r"<code\b[^>]*>.*?</code>", "", src, flags=re.S)
    scannable = re.sub(r"`[^`]*`", "", scannable)
    # DSE grades ("1**" .. "5**") are not Markdown. Require the ** to not
    # follow a digit, which skips grades but still catches real bold spans.
    if re.search(r"(^|[^0-9])\*\*[^*]+\*\*", scannable):
        err(f"{name}: Markdown bold marker in HTML (use <strong>)")


def check_refs(name: str, src: str) -> None:
    base = os.path.join(ROOT, name)
    for attr, ref in re.findall(r'\b(src|href)="([^"]+)"', src):
        if ref.startswith(("http://", "https://", "#", "mailto:", "data:")):
            continue
        if not ref:
            continue
        target = os.path.normpath(os.path.join(os.path.dirname(base), ref))
        if not os.path.exists(target):
            err(f"{name}: {attr}=\"{ref}\" -> missing on disk")


def main() -> int:
    pgs = pages()
    if not pgs:
        print("no pages found", file=sys.stderr)
        return 1

    print(f"checking {len(pgs)} pages: {', '.join(pgs)}")

    for name in pgs:
        with open(os.path.join(ROOT, name), encoding="utf-8") as fh:
            src = fh.read()
        check_tag_balance(name, src)
        check_no_nested_p(name, src)
        check_markdown(name, src)
        check_refs(name, src)

    for a in ASSETS:
        if not os.path.exists(os.path.join(ROOT, a)):
            err(f"asset missing: {a}")

    # Nav consistency: a guide a user cannot navigate to is a dead end.
    # Checked as a matrix so a page added to NAV_PAGES but forgotten in one
    # page's <nav> fails loudly instead of silently dropping out.
    for src in NAV_PAGES:
        sp = os.path.join(ROOT, src)
        if not os.path.exists(sp):
            err(f"nav: {src} listed in NAV_PAGES but missing on disk")
            continue
        s = open(sp, encoding="utf-8").read()
        for dst in NAV_PAGES:
            if dst == src:
                continue
            if f'href="{dst}"' not in s:
                err(f"nav: {src} has no link to {dst}")

    svg_dir = os.path.join(ROOT, "assets", "svg")
    if os.path.isdir(svg_dir):
        for f in sorted(os.listdir(svg_dir)):
            if not f.endswith(".svg"):
                continue
            p = os.path.join(svg_dir, f)
            try:
                xml.dom.minidom.parse(p)
                print(f"  svg ok   {f}")
            except Exception as exc:
                err(f"assets/svg/{f}: not valid XML ({exc})")

    if errors:
        print(f"\nFAILED ({len(errors)}):", file=sys.stderr)
        for e in errors:
            print(f"  ERROR: {e}", file=sys.stderr)
        return 1

    print("page check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())