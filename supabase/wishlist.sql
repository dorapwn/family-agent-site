-- wishlist.sql — 許願表 database
--
-- Goal: strangers' browsers may SUBMIT a wish, and may not READ anyone's.
-- Everything below serves that one sentence. If you change anything, keep
-- that property intact.
--
-- Apply with: supabase db execute --file wishlist.sql   (or paste in the SQL
-- editor). Run it as the project owner, not as the anon role.

-- ── 1. the table ──────────────────────────────────────────────────────────
create table if not exists wishes (
  id          uuid primary key default gen_random_uuid(),
  who         text not null,
  what        text not null,
  why         text,
  how         smallint,
  created_at  timestamptz not null default now(),

  -- Validate in the DATABASE, not in the browser. A browser check is a
  -- courtesy; this is the actual boundary, because anyone can skip our JS
  -- and POST directly with the anon key.
  constraint who_allowed check (who in ('大女','細女','媽媽')),
  constraint what_len     check (char_length(btrim(what)) between 1 and 60),
  constraint why_len      check (why is null or char_length(why) <= 200),
  constraint how_range    check (how is null or how between 1 and 5)
);

-- ── 2. RLS: the switch that makes the anon key safe ───────────────────────
-- Without this line the anon key can read and delete the whole table. With it
-- enabled and NO select policy, the anon role gets zero rows back.
alter table wishes enable row level security;

-- Submitting is allowed...
create policy "anon may submit a wish"
  on wishes for insert
  to anon
  with check (true);

-- ...and that is deliberately the ONLY policy. In Postgres, a role with no
-- matching policy is denied, so on its own this file would give:
--   insert → allowed
--   select → 0 rows (RLS silently filters, no error)
--   update / delete → permission denied
--
-- Do not "helpfully" add a select policy later. That is the one edit that
-- turns this into a public list of what a minor and a social worker want.

-- Belt and braces: also deny the reading and modifying privileges at the
-- grant level. INSERT must stay granted — Supabase grants it on the table and
-- the policy above is what constrains it. Revoking it breaks inserts for
-- everyone while exposing nothing to anon.
--
-- With the revoke in place the observed behaviour is stricter than the policy
-- alone: select raises "permission denied" instead of quietly returning zero
-- rows. That is the better outcome — a caller cannot even confirm the table
-- exists — and it holds even if a select policy is added later by mistake.
revoke select, update, delete, truncate on wishes from anon;
grant insert on wishes to anon;

-- ── 3. reading it (admin side) ────────────────────────────────────────────
-- The agent reads with its service_role key or the Supabase MCP connector.
-- That key bypasses RLS, which is exactly what we want and exactly why it must
-- never appear in any HTML file, in this repo, or in a browser.
--
-- service_role  → full read/write, bypasses RLS. NEVER in client code.
-- anon/publishable → what the browser uses. Safe only because of §2.

-- ── 4. spam ───────────────────────────────────────────────────────────────
-- INSERT-only still allows a bot to write garbage. There is no rate limit in
-- Postgres RLS, so pick one:
--   (a) add a Cloudflare Turnstile or hCaptcha check before the insert, or
--   (b) accept the noise and delete it in the Supabase dashboard — fine at
--       household volume, because the endpoint is not linked from anywhere
--       except the wishlist page.
-- Also worth turning on: Supabase → Authentication → CAPTCHA, and the
-- project's API rate limits, so one client cannot flood the table.

-- ── 5. the read query the agent runs ──────────────────────────────────────
-- select who, what, why, how, created_at from wishes order by created_at;
--
-- Deleting spam:
-- delete from wishes where created_at < now() - interval '90 days';