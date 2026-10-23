"""Test the Supabase-configured path against a stub that mimics PostgREST.

A real Supabase project is not available here, so this stands up a tiny HTTP
server that behaves like PostgREST for POST /rest/v1/wishes and records what it
receives, plus a static server that serves a copy of wishlist.html with the
data-supabase-* attributes already in the <html> tag — exactly the edit an
admin makes. Setting them via JS after load does not work, because an external
<script src> runs during parse, before any later script can touch <html>.

Verified: right URL, method, headers, JSON body, success clears the form,
a constraint rejection and a network failure both tell the user rather than
losing the wish, and empty submits are still blocked.
"""
import json
import os
import re
import shutil
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer, SimpleHTTPRequestHandler

from playwright.sync_api import sync_playwright

SITE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STUB_PORT = 8901
STATIC_PORT = 8902
received = []
fail_next = {"status": None, "body": ""}
fails = []


def check(label, cond, detail=""):
    print(("  PASS  " if cond else "  FAIL  ") + label + ("" if cond else f"  <- {detail}"))
    if not cond:
        fails.append(label)


class Stub(BaseHTTPRequestHandler):
    """Mimics PostgREST, including the CORS headers Supabase actually sends.

    A browser preflights the POST because of the Authorization header, so a
    stub without Access-Control-Allow-* would fail for reasons that have
    nothing to do with the code under test.
    """

    def log_message(self, *a):
        pass

    def _cors(self):
        origin = self.headers.get("Origin")
        self.send_header("Access-Control-Allow-Origin", origin or "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers",
                         "authorization, apikey, content-type, prefer")
        self.send_header("Access-Control-Max-Age", "600")

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0))).decode()
        received.append({
            "path": self.path,
            "method": "POST",
            "origin": self.headers.get("Origin"),
            "apikey": self.headers.get("apikey"),
            "auth": self.headers.get("Authorization"),
            "content_type": self.headers.get("Content-Type"),
            "prefer": self.headers.get("Prefer"),
            "body": body,
        })
        if fail_next["status"]:
            status, payload = fail_next["status"], fail_next["body"]
            fail_next["status"] = None
        else:
            status, payload = 201, ""
        self.send_response(status)
        self._cors()
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(payload.encode())


class Quiet(SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


# Build a served copy with the config in the <html> tag, as an admin would.
SERVE = os.path.join(tempfile.gettempdir(), "wishlist_testsite")
shutil.rmtree(SERVE, ignore_errors=True)
os.makedirs(SERVE)
for item in ("style.css", "supabase"):
    os.symlink(os.path.join(SITE, item), os.path.join(SERVE, item))
src = open(os.path.join(SITE, "wishlist.html"), encoding="utf-8").read()


def make_page(path, url=None, key=None):
    s = src
    if url:
        s = s.replace("<html lang=\"zh-Hant\">",
                      f'<html lang="zh-Hant" data-supabase-url="{url}" '
                      f'data-supabase-key="{key}">', 1)
    assert ("data-supabase-url" in s) == bool(url), "config injection failed"
    open(os.path.join(SERVE, path), "w", encoding="utf-8").write(s)


STUB_URL = f"http://127.0.0.1:{STUB_PORT}"
make_page("configured.html", STUB_URL, "sb_publishable_TESTKEY")
make_page("broken-url.html", "http://127.0.0.1:9", "sb_publishable_TESTKEY")
make_page("plain.html")  # no config: must keep using Telegram

srv = HTTPServer(("127.0.0.1", STUB_PORT), Stub)
threading.Thread(target=srv.serve_forever, daemon=True).start()


def serve_static():
    os.chdir(SERVE)
    HTTPServer(("127.0.0.1", STATIC_PORT), Quiet).serve_forever()


threading.Thread(target=serve_static, daemon=True).start()

BASE = f"http://127.0.0.1:{STATIC_PORT}"
KEY = "sb_publishable_TESTKEY"


def open_page(p, page="configured.html"):
    b = p.chromium.launch(args=["--no-sandbox"])
    pg = b.new_page(viewport={"width": 390, "height": 900})
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.on("console", lambda m: errs.append("console.error: " + m.text)
          if m.type == "error" else None)
    pg.goto(f"{BASE}/{page}", wait_until="networkidle")
    return b, pg, errs


with sync_playwright() as p:
    print("=== A. configured: request shape ===")
    received.clear()
    b, pg, errs = open_page(p)
    pg.select_option("#who", "大女")
    pg.fill("#what", "校曆自動讀")
    pg.fill("#why", "唔使自己抄")
    pg.click('.stars label:has(input[value="3"]) span')
    pg.click("button.send")
    pg.wait_for_timeout(1200)

    check("no JS errors", not errs, errs)
    check("exactly one request reached the API", len(received) == 1, len(received))
    if received:
        r = received[0]
        check("posted to /rest/v1/wishes", r["path"] == "/rest/v1/wishes", r["path"])
        check("uses POST", r["method"] == "POST", r["method"])
        check("sends publishable key as apikey", r["apikey"] == KEY, r["apikey"])
        check("sends Bearer auth", (r["auth"] or "").endswith(KEY), r["auth"])
        check("json content-type", r["content_type"] == "application/json", r["content_type"])
        check("asks for no rows back (Prefer: return=minimal)",
              r["prefer"] == "return=minimal", r["prefer"])
        try:
            j = json.loads(r["body"])
        except Exception as e:
            j = {}
            check("body is valid JSON", False, f"{e}: {r['body']!r}")
        if j:
            check("body: who", j.get("who") == "大女", j)
            check("body: what", j.get("what") == "校曆自動讀", j)
            check("body: why", j.get("why") == "唔使自己抄", j)
            check("body: how as int 3", j.get("how") == 3, j)
            check("body has exactly the table columns",
                  set(j) == {"who", "what", "why", "how"}, sorted(j))
    msg = pg.inner_text("#preview")
    check("confirms receipt", "收到" in msg, msg)
    check("form cleared after success",
          pg.input_value("#what") == "" and pg.input_value("#who") == "", "not cleared")
    b.close()

    print("\n=== B. database rejects the row (constraint violation) ===")
    received.clear()
    fail_next["status"] = 400
    fail_next["body"] = json.dumps(
        {"message": 'new row for relation "wishes" violates check constraint "who_allowed"',
         "code": "23514"})
    b, pg, errs = open_page(p)
    pg.select_option("#who", "大女")
    pg.fill("#what", "測試違規")
    pg.click("button.send")
    pg.wait_for_timeout(1200)
    check("request was attempted", len(received) == 1, len(received))
    msg = pg.inner_text("#preview")
    check("tells the user it did not save", "送唔到" in msg, msg)
    check("offers the talk-to-the-agent fallback", "直接同助理講" in msg, msg)
    check("does NOT clear the form (nothing lost)",
          pg.input_value("#what") == "測試違規", pg.input_value("#what"))
    b.close()

    print("\n=== C. network unreachable ===")
    received.clear()
    b, pg, errs = open_page(p, "broken-url.html")
    pg.select_option("#who", "媽媽")
    pg.fill("#what", "廚房行程")
    pg.click("button.send")
    pg.wait_for_timeout(3000)
    msg = pg.inner_text("#preview")
    check("reports failure plainly", ("send 唔到" in msg) or ("offline" in msg), msg)
    check("keeps the text for a retry",
          pg.input_value("#what") == "廚房行程", pg.input_value("#what"))
    b.close()

    print("\n=== D. validation still applies when configured ===")
    received.clear()
    b, pg, errs = open_page(p)
    pg.click("button.send")
    pg.wait_for_timeout(500)
    msg = pg.inner_text("#preview")
    check("blocked with guidance", "請先揀" in msg, msg)
    check("no request sent for an empty form", len(received) == 0, len(received))
    b.close()

    print("\n=== E. no config: still the Telegram path, button says so ===")
    b, pg, errs = open_page(p, "plain.html")
    btn = pg.inner_text("button.send")
    check("button advertises the real path", "Telegram" in btn, btn)
    pg.select_option("#who", "細女")
    pg.fill("#what", "相片整成短片")
    with pg.expect_request(re.compile(r"t\.me"), timeout=5000) as nav:
        pg.click("button.send")
    txt = nav.value.url
    check("unconfigured still reaches Telegram", txt.startswith("https://t.me/"), txt[:60])
    check("no JS errors", not errs, errs)
    b.close()

srv.shutdown()
print()
if fails:
    print("FAILED:", "; ".join(fails))
    sys.exit(1)
print("supabase-path checks passed")