#!/usr/bin/env python3
"""
build_slides.py — generate the student-union slide deck as a set of SVG files.

Each slide is a standalone SVG. They are embedded in the page with <object>
so the browser renders them as real documents (which is also what makes
prefers-reduced-motion work).

Why generate rather than hand-write: the slides share a template (header bar,
footer, palette, title block), and a template that lives in one place cannot
drift the way six hand-written files drift.

Run:  python3 scripts/build_slides.py
"""
from __future__ import annotations

import os
import xml.dom.minidom

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "assets", "svg", "slides")
os.makedirs(OUT, exist_ok=True)

# Matches the site's palette (style.css) so the deck reads as part of the site.
INK = "#e8e4dc"
INK_DIM = "#a09a8e"
PAPER = "#12110f"
CARD = "#1a1815"
LINE = "#2e2a24"
AMBER = "#e8a33d"
TEAL = "#4fd0c4"
VIOLET = "#b06fd8"
BLUE = "#5b9fd8"

# CJK-capable stack. The container only has WenQuanYi Zen Hei, so it is listed
# explicitly; real users will get PingFang or Noto.
CJK = ("PingFang TC, PingFang HK, Noto Sans CJK TC, Noto Sans CJK SC, "
       "Microsoft JhengHei, WenQuanYi Zen Hei, sans-serif")
MONO = "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"

W, H = 1280, 720


def esc(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def text(x, y, s, size=24, fill=INK, weight=400, family=CJK, anchor="start",
         opacity=None, letter=None):
    op = f' opacity="{opacity}"' if opacity is not None else ""
    ls = f' letter-spacing="{letter}"' if letter else ""
    return (f'<text x="{x}" y="{y}" fill="{fill}" font-size="{size}" '
            f'font-weight="{weight}" font-family="{family}" '
            f'text-anchor="{anchor}"{op}{ls}>{esc(s)}</text>')


def wrap(s: str, limit: int) -> list[str]:
    """Wrap on CJK characters and on spaces for Latin runs.

    CJK has no spaces, so a naive word-wrap would put a whole Chinese sentence
    on one line. Split on any character but keep Latin words together.
    """
    out, line, i = [], "", 0
    while i < len(s):
        ch = s[i]
        if ch == "\n":
            if line:
                out.append(line)
            line = ""
            i += 1
            continue
        # Keep runs of ASCII (words, numbers, punctuation) together.
        if ch.isascii() and (ch.isalnum() or ch in "'.,!?:;-/()"):
            j = i
            while j < len(s) and s[j].isascii() and \
                    (s[j].isalnum() or s[j] in "'.,!?:;-/()"):
                j += 1
            token = s[i:j]
        else:
            token = ch
            j = i + 1
        if len(line) + len(token) > limit and line:
            out.append(line)
            line = token.lstrip()
        else:
            line += token
        i = j
    if line:
        out.append(line)
    return out


def para(x, y, s, size=22, fill=INK_DIM, limit=26, lh=None, family=CJK,
         weight=400):
    """Draw wrapped text. Returns the y after the last line."""
    lh = lh or int(size * 1.62)
    for i, ln in enumerate(wrap(s, limit)):
        y += lh if i else 0
        out = text(x, y, ln, size, fill, weight, family)
        yield out
    return y + lh


def slide(idx, total, kicker, title, body_svg, foot=None, accent=AMBER):
    """Wrap body content in the slide chrome."""
    n = f"{idx:02d}"
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
        f'role="img" aria-labelledby="t{n} d{n}">',
        f'<title id="t{n}">{esc(title)}</title>',
        f'<desc id="d{n}">{esc(foot or title)}</desc>',
        f'<rect width="{W}" height="{H}" fill="{PAPER}"/>',
        # Accent hairline down the left edge.
        f'<rect x="0" y="0" width="6" height="{H}" fill="{accent}"/>',
        # Top rule.
        f'<line x1="60" y1="96" x2="{W-60}" y2="96" stroke="{LINE}" '
        f'stroke-width="2"/>',
        text(60, 58, kicker, 15, accent, 700, MONO, letter="3"),
        text(W - 60, 58, f"{n} / {total}", 15, INK_DIM, 400, MONO, "end"),
        text(60, 150, title, 46, INK, 700, CJK),
    ]
    parts.append(body_svg)
    if foot:
        parts.append(text(60, H - 34, foot, 14, INK_DIM, 400, MONO))
    parts.append("</svg>")
    return "\n".join(parts)


def photo(x, y, w, h, src, radius=6, fit="slice"):
    """A browser-captured still, clipped to rounded corners.

    fit="slice" fills the box and crops the overflow (good for photos, keeps
    the frame a fixed size). fit="meet" shows the whole image and letterboxes
    the difference — needed for a wide banner strip, where cropping would cut
    the flags in half.
    """
    cid = f"c{x}{y}"
    extra = ""
    if fit == "meet":
        # Draw the letterbox fill first, so the rounded corners still read.
        extra = (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" '
                 f'rx="{radius}" fill="{CARD}"/>')
    return (
        f'<defs><clipPath id="{cid}">'
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}"/>'
        f'</clipPath></defs>'
        + extra +
        f'<image x="{x}" y="{y}" width="{w}" height="{h}" '
        f'preserveAspectRatio="xMidYMid {fit}" clip-path="url(#{cid})" '
        f'href="{src}"/>'
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" '
        f'fill="none" stroke="{LINE}" stroke-width="2"/>'
    )


def bullets(x, y, items, size=23, fill=INK_DIM, gap=40, dot=TEAL, dotr=5,
            limit=30):
    """Bulleted list with a coloured dot per line."""
    out = []
    cy = y
    for it in items:
        out.append(f'<circle cx="{x+6}" cy="{cy-8}" r="{dotr}" fill="{dot}"/>')
        lines = wrap(it, limit)
        for i, ln in enumerate(lines):
            out.append(text(x + 26, cy + i * int(size * 1.55), ln, size, fill))
        cy += gap + (len(lines) - 1) * int(size * 1.55)
    return "\n".join(out)


def stat(x, y, value, label, color=AMBER, vsize=64):
    return (text(x, y, value, vsize, color, 700, MONO) +
            text(x, y + 34, label, 19, INK_DIM, 400, CJK))


# ---------------------------------------------------------------------------
# The slides.
#
# Every factual claim below was read off the live HKUSTSU site on 2026-10-24
# with a browser, not from memory. See scripts/capture_su.py.
#
# Where a number appears, it is the site's own figure:
#   - 82 societies: the site's own society dropdown lists 83 entries, one of
#     which is a placeholder called "test Society", so 82 are real.
#   - The six categories are the site's own section headings:
#     School Societies / Art and Cultural Clubs / ICA and Independent Clubs /
#     Sports / House Associations / Departmental Societies.
#   - Voting: the Annual Election elects one Executive Committee cabinet,
#     one Editorial Board cabinet and ten Popularly Elected Councilors.
#     Eligible voters are full members who log in with their HKUST account.
# ---------------------------------------------------------------------------

TOTAL = 7


def build() -> None:
    slides = []

    # -- 1. Cover -----------------------------------------------------------
    body = (
        photo(60, 200, 620, 440, "../../img/su-home.jpg") +
        text(730, 250, "香港科技大學學生會", 34, INK, 700, CJK) +
        text(730, 296, "HKUST Students' Union", 20, INK_DIM, 400, MONO) +
        text(730, 350, "點解要投票？", 40, AMBER, 700, CJK) +
        text(730, 400, "你嘅一票，", 22, INK_DIM, 400, CJK) +
        text(730, 432, "決定咗邊個幫你辦事。", 22, INK_DIM, 400, CJK) +
        text(730, 500, "由網頁截圖 + SVG 拼出嚟", 16, TEAL, 400, MONO) +
        text(730, 526, "每張相都係真實網頁", 16, TEAL, 400, MONO)
    )
    slides.append(slide(1, TOTAL, "STUDENT UNION · 投票指南",
                        "學生會點解要投票", body,
                        "資料來源：hkustsu.hkust.edu.hk（瀏覽器截圖）"
                        " · 2026 年 10 月 24 日",
                        accent=AMBER))

    # -- 2. What the union actually does ------------------------------------
    body = (
        text(60, 215, "學生會唔係「空氣」——", 28, INK, 700, CJK) +
        text(60, 258, "佢真係會幫你做嘢。", 28, INK, 700, CJK) +
        bullets(60, 322, [
            "管理你參與嘅社團同興趣組",
            "出一份學生報《振翅》，有自己嘅編輯部",
            "收會費、發會員證、辦理入會",
            "每年搞大型活動同迎新",
            "代表學生同學校傾：宿位、學費、課程",
        ]) +
        # A stat block, so the number is stated once and given weight.
        # Sits below the last bullet, which ends around y=490.
        text(60, 578, "82", 76, TEAL, 700, MONO) +
        text(160, 560, "個學生社團", 24, INK, 700, CJK) +
        text(160, 590, "六大類，由藝術組到宿生會", 18, INK_DIM, 400, CJK) +
        text(760, 215, "社團六大分類", 19, AMBER, 700, CJK) +
        "\n".join(
            text(760, 262 + i * 44, f"— {c}", 21, INK_DIM)
            for i, c in enumerate([
                "學院社團",
                "藝術及文化組",
                "ICA 及獨立社團",
                "體育組",
                "宿生會",
                "學系社團",
            ])
        ) +
        text(760, 545, "六大類", 18, TEAL, 400, CJK)
    )
    slides.append(slide(2, TOTAL, "你付錢，佢做嘢",
                        "學生會實際做啲咩", body,
                        "社團數目、分類：hkustsu.hkust.edu.hk/societies",
                        accent=TEAL))

    # -- 3. How the union is structured -------------------------------------
    body = (
        photo(60, 215, 640, 300, "../../img/su-orgchart-top.jpg") +
        text(750, 215, "架構圖", 19, AMBER, 700, CJK) +
        bullets(750, 265, [
            "全體會員大會（最高）",
            "學生會執行委員會",
            "學生會理事會",
            "編輯部",
            "學生法庭",
        ], size=20, gap=36, dot=AMBER, limit=14) +
        # What the diagram actually says, in the reader's own language.
        text(60, 560, "最高嗰個唔係執委會：", 21, AMBER, 700, CJK) +
        text(60, 594, "係全體會員大會 —— 即係所有會員都有份嘅最高決定權。", 21,
             INK_DIM, 400, CJK)
    )
    slides.append(slide(3, TOTAL, "架構",
                        "邊個做主？", body,
                        "架構圖：hkustsu.hkust.edu.hk/about-us",
                        accent=BLUE))

    # -- 4. Why voting matters ----------------------------------------------
    body = (
        text(60, 210, "唔投票 = 由得人哋決定", 30, INK, 700, CJK) +
        text(60, 252, "投咗票 = 你都係決策嘅一部分", 30, INK, 700, CJK) +
        "\n".join(
            f'<rect x="60" y="{300 + i*86}" width="1160" height="66" '
            f'rx="8" fill="{CARD}" stroke="{LINE}" stroke-width="2"/>' +
            f'<circle cx="96" cy="{333 + i*86}" r="9" fill="{TEAL}"/>' +
            text(126, 341 + i * 86, t, 23, INK) +
            text(1180, 341 + i * 86, s, 20, INK_DIM, 400, MONO, "end")
            for i, (t, s) in enumerate([
                ("執委會邊個做主", "你會唔會信佢"),
                ("邊個做編輯部", "學生報點寫"),
                ("邊十位做普選評議員", "同你最直接嘅代表"),
                ("公投同特別會員大會", "最高嗰個決定權"),
            ])
        )
    )
    slides.append(slide(4, TOTAL, "你嘅一票有咩用",
                        "點解要投票", body,
                        "根據學生會架構同選舉規則：會員大會、公投、"
                        "執委會、普選評議員",
                        accent=VIOLET))

    # -- 5. How to vote ------------------------------------------------------
    body = (
        text(60, 210, "加入 = 有投票權", 30, INK, 700, CJK) +
        text(60, 258, "入會三步（學生會 FAQ 原文）", 22, AMBER, 700, CJK) +
        bullets(60, 315, [
            "登入學生會平台",
            "撳「Get Started」",
            "填資料 + 上載會費證明",
        ], size=24, gap=44, limit=22) +
        text(760, 210, "然後去投票", 30, INK, 700, CJK) +
        bullets(760, 275, [
            "用科大帳戶登入投票網站",
            "揀你想投嘅職位，按提示投票",
            "過咗截止時間就唔得",
        ], size=22, gap=42, dot=AMBER, limit=13) +
        # What the election actually elects, per the Election Committee.
        text(60, 520, "每年選咩？", 22, AMBER, 700, CJK) +
        text(60, 556, "執委會一屆、編輯部一屆、普選評議員十位。", 21,
             INK_DIM, 400, CJK) +
        text(60, 588, "投票喺網上進行，投票連結會經電郵發出。", 21,
             INK_DIM, 400, CJK) +
        text(760, 470, "唔記得點做？", 20, INK_DIM, 400, CJK) +
        text(760, 500, "su_union@connect.ust.hk", 19, TEAL, 400, MONO)
    )
    slides.append(slide(5, TOTAL, "點樣做",
                        "點樣投票", body,
                        "入會步驟：hkustsu.hkust.edu.hk/faq；"
                        "選舉細節：hkustsucouncil.wordpress.com",
                        accent=TEAL))

    # -- 6. What to check before you vote -----------------------------------
    body = (
        text(60, 210, "投票之前，睇清楚呢幾樣", 30, INK, 700, CJK) +
        "\n".join(
            f'<rect x="60" y="{268 + i*88}" width="1160" height="70" '
            f'rx="8" fill="{CARD}" stroke="{LINE}" stroke-width="2"/>' +
            text(92, 312 + i * 88, f"{i+1}", 30, AMBER, 700, MONO) +
            text(150, 300 + i * 88, t, 23, INK) +
            text(150, 328 + i * 88, d, 18, INK_DIM, 400, CJK)
            for i, (t, d) in enumerate([
                ("過往做過啲咩", "睇佢哋過往搞過嘅活動，睇得唔唔到做得實唔實"),
                ("有咩政績可以攞出嚟", "有冇報告、有冇交代錢用咗喺邊"),
                ("計劃講得實唔實", "係咪有具體時間表，唔係淨係講「會努力」"),
                ("肯唔肯答問題", "肯唔肯出席答問、肯唔肯講唔做得到嘅部分"),
            ])
        )
    )
    slides.append(slide(6, TOTAL, "唔好亂投",
                        "投票前要睇啲咩", body,
                        "原則：睇紀錄、睇政績、睇計劃、睇態度",
                        accent=AMBER))

    # -- 7. Closing ---------------------------------------------------------
    body = (
        # The banner strip is 1280x250 (5.1:1). Displaying it at 560x300
        # with "slice" would crop it to 560x109 and cut the flags in half,
        # so it is shown whole with "meet" and the box matches its aspect.
        photo(60, 215, 560, 109, "../../img/su-banners.jpg", fit="meet") +
        text(60, 360, "社團旗幟：學生會網頁首頁影落嚟", 16, INK_DIM, 400, CJK) +
        text(680, 235, "社團都係靠你哋撐起", 30, INK, 700, CJK) +
        text(680, 285, "想玩、想學、想做嘢？", 22, INK_DIM, 400, CJK) +
        text(680, 325, "加入社團 → 認識人 → 有票投", 22, INK_DIM, 400, CJK) +
        text(680, 400, "去投你嘅一票。", 40, AMBER, 700, CJK) +
        text(680, 450, "hkustsu.hkust.edu.hk", 19, TEAL, 400, MONO) +
        text(680, 490, "su_union@connect.ust.hk", 17, INK_DIM, 400, MONO) +
        text(60, 540, "呢套簡報：每張相都係用瀏覽器影低嘅真實網頁。",
             20, INK_DIM, 400, CJK) +
        text(60, 572, "資料日期：2026 年 10 月 24 日。",
             17, INK_DIM, 400, CJK)
    )
    slides.append(slide(7, TOTAL, "最後",
                        "去投你嘅一票", body,
                        "網址：hkustsu.hkust.edu.hk",
                        accent=VIOLET))

    for i, s in enumerate(slides, 1):
        p = os.path.join(OUT, f"slide-{i}.svg")
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(s)
        # Fail here rather than at deploy time. A malformed slide is a build
        # bug, and the XML parser names the line and column.
        xml.dom.minidom.parse(p)
        print(f"  {os.path.relpath(p, ROOT)}  {len(s)//1024} KB")


if __name__ == "__main__":
    build()
