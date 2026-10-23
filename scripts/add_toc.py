#!/usr/bin/env python3
"""Insert a table of contents into every page that has two or more <h2>.

Generated rather than hand-written, because a hand-written TOC rots: every
time someone adds a heading they must remember to add a line too. This script
is idempotent — it replaces an existing <details class="toc"> rather than
stacking a second one — so it is safe to re-run before every commit.

Usage:  python3 scripts/add_toc.py [--check]

  --check  exit non-zero if any page is missing or has a stale TOC, without
           writing anything. This is what CI calls.
"""
import html
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Pages with no TOC: 404 (not linked from the nav) and pages too short to need
# one. Keep in sync with NAV_ORDER in check_pages.py.
SKIP = {"404.html"}

TOC_OPEN = '<details class="toc">'
TOC_CLOSE = "</details>"


def slugify(text: str, seen: dict[str, int]) -> str:
    """A short, stable, readable anchor id.

    Headings here are Chinese, so we keep their characters. GitHub Pages
    handles UTF-8 ids fine and a readable id beats a hash nobody can type.
    """
    s = re.sub(r"<[^>]+>", "", text)
    s = html.unescape(s).strip()
    # Keep letters, digits, CJK; turn everything else into a separator.
    s = re.sub(r"[^\w㐀-鿿]+", "-", s, flags=re.UNICODE).strip("-").lower()
    if not s:
        s = "section"
    # Guarantee uniqueness without silently renaming on a collision.
    if s in seen:
        seen[s] += 1
        s = f"{s}-{seen[s]}"
    else:
        seen[s] = 0
    return s


def main() -> int:
    check = "--check" in sys.argv
    files = sorted(
        f for f in os.listdir(ROOT)
        if f.endswith(".html") and f not in SKIP
    )
    bad = []
    for f in files:
        p = os.path.join(ROOT, f)
        s = open(p, encoding="utf-8").read()
        try:
            heads = re.findall(r"<h2[^>]*>(.*?)</h2>", s, re.S)
        except Exception as e:  # pragma: no cover
            print(f"  {f}: {e}")
            bad.append(f)
            continue
        if len(heads) < 2:
            continue

        seen: dict[str, int] = {}
        entries = []
        for h in heads:
            label = re.sub(
                r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", h))
            ).strip()
            entries.append((slugify(h, seen), label))

        toc = (
            f'<details class="toc">\n'
            f'  <summary>呢頁有咩</summary>\n'
            f'  <ol>\n'
            + "".join(f'    <li><a href="#{i}">{l}</a></li>\n' for i, l in entries)
            + f"  </ol>\n{TOC_CLOSE}"
        )

        # Drop any existing TOC, plus one blank line either side of it, so
        # re-running cannot accumulate whitespace.
        s2 = re.sub(
            re.escape(TOC_OPEN) + r".*?" + re.escape(TOC_CLOSE) + r"\n*",
            "",
            s,
            flags=re.S,
        )
        s2 = re.sub(r"\n{3,}", "\n\n", s2)
        nav = re.search(r"</nav>\n", s2)
        if nav:
            at = nav.end()
        else:
            # The homepage has no nav bar — its card grid is the navigation.
            # Anchor to the end of <header> instead.
            hdr = re.search(r"</header>\n", s2)
            if not hdr:
                print(f"  {f}: nowhere to put the TOC")
                bad.append(f)
                continue
            at = hdr.end()
        s2 = s2[:at] + "\n" + toc + "\n" + s2[at:]

        # Stamp ids onto the h2s, in order, only where one is missing.
        it = iter(entries)

        def stamp(m):
            if "id=" in m.group(1):
                return m.group(0)
            return f'<h2 id="{next(it)[0]}"{m.group(1)}>'

        s2 = re.sub(r"<h2([^>]*)>", stamp, s2)

        if s2 == s:
            if check:
                continue
        if check:
            print(f"  {f}: TOC missing or stale")
            bad.append(f)
        else:
            open(p, "w", encoding="utf-8").write(s2)
            print(f"  {f}: {len(entries)} headings")

    if check and bad:
        print("\nTOC check FAILED. Run: python3 scripts/add_toc.py")
        return 1
    if check:
        print("toc check passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())