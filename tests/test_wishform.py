"""Exercise the wishlist form in a real browser and assert the deep link.

GitHub Pages cannot receive a POST, so the form assembles a message and hands
it to Telegram. This checks the assembled text, not just that a click happened.
"""
import os, re, sys, urllib.parse
from playwright.sync_api import sync_playwright

URL = os.environ.get("WISHFORM_URL", "http://127.0.0.1:8899/wishlist.html")
fails = []


def check(label, cond, detail=""):
    print(("  PASS  " if cond else "  FAIL  ") + label + ("" if cond else f"  <- {detail}"))
    if not cond:
        fails.append(label)


with sync_playwright() as p:
    b = p.chromium.launch(args=["--no-sandbox"])
    pg = b.new_page(viewport={"width": 390, "height": 844})  # phone-sized
    errors = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    pg.goto(URL, wait_until="networkidle")

    check("no JS errors on load", not errors, errors)

    # 1. submitting empty must not navigate away
    pg.click("button.send")
    pg.wait_for_timeout(300)
    msg = pg.inner_text("#preview")
    check("empty submit blocked with guidance", "請先揀" in msg, msg)
    check("stayed on page (no nav)", "wishlist.html" in pg.url, pg.url)

    # 2. fill it in
    pg.select_option("#who", "細女")
    pg.fill("#what", "影張相就記低今日做咩")
    pg.fill("#why", "唔想打字")
    pg.click('.stars label:has(input[value="5"]) span')  # "好想要好想要"
    check("rating selected", pg.eval_on_selector_all(
        "input[name=how]", "els => els.filter(e=>e.checked).length") == 1)

    # intercept navigation instead of leaving the test to telegram.com
    with pg.expect_request(re.compile(r"t\.me"), timeout=5000) as nav:
        pg.click("button.send")
    req = nav.value
    final = req.url
    print("  deep link:", final[:110])

    check("goes to a t.me link", final.startswith("https://t.me/"), final)

    q = urllib.parse.urlparse(final).query
    params = urllib.parse.parse_qs(q)

    # t.me/<bot>?text=...  OR  t.me/share/url?url=..&text=...
    text = params.get("text", [""])[0]
    check("carries the feature request", "影張相就記低今日做咩" in text, text)
    check("carries who", "細女" in text, text)
    check("carries why", "唔想打字" in text, text)
    check("carries rating 5/5", "5/5" in text, text)
    check("has a marker so the agent can triage",
          "許願" in text, text)
    print("  assembled message:\n   ", text.replace("\n", "\n    "))

    check("no JS errors during submit", not errors, errors)

    # 3. narrow viewport: nothing should overflow horizontally
    ow = pg.evaluate("document.documentElement.scrollWidth")
    cw = pg.evaluate("document.documentElement.clientWidth")
    check("no horizontal overflow on 390px", ow <= cw + 1, f"scroll={ow} client={cw}")

    b.close()

print()
if fails:
    print("FAILED:", "; ".join(fails))
    sys.exit(1)
print("form checks passed")