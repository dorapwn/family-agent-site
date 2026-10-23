# supabase/ — optional direct-to-database wishlist

The wishlist page works today with **no database**: it assembles the message
and hands it to Telegram, and the user taps send. That path needs no server, no
credentials, and no third party.

If the admin sets up Supabase, the same form can post straight into a table and
the user's tap of "send" stops being load-bearing. This directory holds that
optional path. **Nothing here is required for the site to function.**

## What the admin needs

Two things from the Supabase project, both safe to publish:

- Project URL — `https://<ref>.supabase.co`
- **Publishable** key (`anon` in older projects) — Settings → API

These are designed to be public. They are safe in a browser file *because of
the RLS policies* in `wishlist.sql`, which allow exactly one operation:
inserting a row. A visitor can submit a wish; they cannot read anyone's.

The key that must never leave the server is **`service_role`**. It bypasses RLS
entirely, so anyone holding it can read and delete every row. It belongs in the
agent's environment, not in this repo or any page.

Hermes can reach the table either way:
- the Supabase MCP connector (`https://mcp.supabase.com/mcp`, OAuth, already in
  the approved catalog), or
- the `service_role` key in the agent's env, used server-side only.

## 1. Create the table

Run `wishlist.sql` in the Supabase SQL editor as the project owner. It creates
the table, enables RLS, grants `anon` insert and nothing else, and adds CHECK
constraints so bad rows are rejected by the database itself rather than by
JavaScript the caller can skip.

## 2. Point the page at it

In `wishlist.html`, the `<html>` tag carries the config. Unset means the page
uses the Telegram handoff:

```html
<html lang="zh-Hant"
      data-supabase-url="https://<ref>.supabase.co"
      data-supabase-key="<publishable key>">
```

Then include the script before `</body>`:

```html
<script src="supabase/submit.js"></script>
```

Without those two attributes the script stays inert and the button keeps its
original label, so there is no broken intermediate state to test.

## 3. Read the wishes

```
select who, what, why, how, created_at from wishes order by created_at;
```

Clear old ones out when convenient:

```
delete from wishes where created_at < now() - interval '90 days';
```

## What was verified, and how

**The browser path in this repo was verified here, by `tests/test_supabase_path.py`** —
it stands up a stub that mimics PostgREST and serves a copy of the page carrying
the `data-supabase-*` attributes exactly as an admin would set them. Checks:

- POST goes to `/rest/v1/wishes`, `Prefer: return=minimal`, JSON body with
  exactly the four table columns and nothing else
- success clears the form and says so
- a database rejection tells the user it did not save and does **not** clear the
  form, and offers talking to the agent — the wish is never silently lost
- a network failure reports plainly and keeps the text
- empty submits are still blocked before any request is made
- with no configuration, the button reads「砌好，撳我去 Telegram 送出」and the
  Telegram path is still taken
- exactly one POST per submit (the page carries a single handler, not two)

**The SQL's security properties were NOT re-verified in this environment.** A
PostgreSQL 18 instance is reachable here, but it is Vaultgres test infrastructure
for an unrelated project, not a Supabase emulator — and a static GitHub Pages
site could not reach it in any case. The `anon` behaviour listed below comes from
the schema's own reasoning, and should be re-run against a real Supabase project
before anyone relies on it:

- insert as `anon` → allowed by `wishes_insert_anon`, and no SELECT policy exists
- select as `anon` → **no policy matches, so it is denied.** Two independent
  things make it so: RLS with no `select` policy, and `revoke select ... from anon`
  at the grant level. The revoke is defence in depth — if someone later adds a
  `select` policy by mistake, the grant still blocks the read.
- update / delete / truncate as `anon` → denied, both by policy and by revoke
- `who` outside the four names → rejected by `who_allowed`
- `what` of 61 chars, or whitespace only → rejected by `what_len`
- `why` of 201 chars → rejected by `why_len` (200 passes)
- `how` of 9 → rejected by `how_range`

Re-run this against the real project:

```sql
set role anon;                 -- as the project owner, in the SQL editor
insert into wishes (who, what) values ('媽媽', '語音讀出');  -- expect: success
select * from wishes;          -- expect: permission denied
update wishes set what = 'x';  -- expect: permission denied
delete from wishes;            -- expect: permission denied
reset role;
```

## Spam

INSERT-only does not stop a bot writing junk. At household volume the dashboard
is enough. If that stops being true, put a Turnstile or hCaptcha check in front
of the insert, and turn on Supabase's API rate limits.

## Privacy note

This table holds what the household asks for. It is not where client
information belongs — a social worker's case notes never go here, and never go
to any hosted service. Keep those conversations in the agent's own memory, or
not at all.