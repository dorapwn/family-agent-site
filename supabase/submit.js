// supabase-submit.js — optional. Use this ONLY if the admin has wired up a
// Supabase project. Without a project URL and publishable key configured, the
// wishlist page keeps its Telegram handoff and nothing here runs.
//
// Why the publishable key is safe to put in a public HTML file: it is designed
// to be public. It only works within the bounds of the RLS policies in
// supabase/wishlist.sql — which permit INSERT and nothing else. The key that
// must never appear in this repo or any page is service_role.
//
// Both keys are read from data-* attributes on <html>, set by the admin at
// deploy time. The defaults below mean "not configured": if an admin forgets,
// the page falls back to Telegram rather than posting into the void.

(function () {
  var root = document.documentElement.dataset;
  var url = (root.supabaseUrl || "").replace(/\/+$/, "");
  var key = root.supabaseKey || "";
  var form = document.getElementById("wish");
  var preview = document.getElementById("preview");
  if (!form) return;

  var configured = url && key;

  function collectRow() {
    var how = form.querySelector('input[name="how"]:checked');
    return {
      who: document.getElementById("who").value,
      what: document.getElementById("what").value.trim(),
      why: document.getElementById("why").value.trim() || null,
      how: how ? parseInt(how.value, 10) : null
    };
  }

  function validate(row) {
    if (!row.who) return "請先揀「邊個想要」。";
    if (!row.what) return "請填「想要咩功能」，一句話就得。";
    return "";
  }

  function sendTelegram(text) {
    var bot = root.telegramBot || "";
    var target = bot
      ? "https://t.me/" + bot + "?text=" + encodeURIComponent(text)
      : "https://t.me/share/url?url=" + encodeURIComponent(location.href) +
        "&text=" + encodeURIComponent(text);
    window.location.href = target;
  }

  form.addEventListener("submit", function (ev) {
    ev.preventDefault();
    var row = collectRow();
    var problem = validate(row);
    if (problem) { preview.textContent = problem; return; }

    if (!configured) {
      // Unconfigured: Telegram is not a lesser path, it is the right one.
      sendTelegram(telegramText(row));
      return;
    }

    preview.textContent = "送出緊⋯⋯";
    fetch(url + "/rest/v1/wishes", {
      method: "POST",
      headers: {
        "apikey": key,
        "Authorization": "Bearer " + key,
        "Content-Type": "application/json",
        // Ask PostgREST to reject anything the table constraints dislike,
        // so a bad row fails loudly instead of landing in the table.
        "Prefer": "return=minimal"
      },
      body: JSON.stringify(row)
    }).then(function (res) {
      if (res.ok) {
        preview.textContent = "收到，唔使再撳。助理會記低。";
        form.reset();
        // Keep the Telegram copy as a backup path in case the row is later
        // judged spam: the agent can always ask the user directly.
        console.log("wish recorded", row.who, new Date().toISOString());
      } else {
        return res.text().then(function (t) {
          preview.textContent = "送唔到。請直接同助理講：「" +
            row.what + "」—— 我幫你記低。";
          console.warn("supabase rejected:", res.status, t);
        });
      }
    }).catch(function (err) {
      preview.textContent = "而家 send 唔到（可能offline）。" +
        "請撳多一次，或者直接同助理講。";
      console.warn("supabase unreachable:", err);
    });
  });

  function telegramText(row) {
    var lines = ["【許願】", "邊個：" + row.who, "想要：" + row.what];
    if (row.why) lines.push("原因：" + row.why);
    if (row.how) lines.push("幾想要：" + row.how + "/5");
    return lines.join("\n");
  }

  if (!configured) {
    // Make the active path visible in the UI so nobody wonders whether the
    // form goes anywhere.
    var btn = form.querySelector(".send");
    if (btn) btn.textContent = "砌好，撳我去 Telegram 送出";
  }
})();