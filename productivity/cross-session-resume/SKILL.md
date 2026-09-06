---
name: cross-session-resume
description: Resume interrupted work from a prior Hermes session (续上).
license: MIT
metadata:
  category: productivity
  version: "1.0.0"
---

# Cross-Session Resume (续上)

Use when the user opens a fresh CLI/TUI session and asks "为什么没有上下文内容了"
(why is there no context), or says "续上" / "继续" expecting you to pick up a
previous day's project work. The overnight-handoff pattern (user sleeps, expects
autonomous dev to a deadline, resumes the next morning) makes this a recurring flow.

## Step 1 — Explain why context is gone (30 seconds, no hand-wringing)

A new `hermes` launch starts a NEW session with `history=0`; prior context lives in
the OLD session file. It is not lost. Check:
- `hermes sessions list` — shows current session (title "—") vs prior sessions with
  titles, previews, and last-active times.
- `grep "conversation turn" ~/.hermes/logs/agent.log | tail` — the
  `history=0` entry for your session id proves the fresh start.
- Model switch (e.g. MiniMax→deepseek) is unrelated to context loss — don't blame it.

Recovery commands to give the user:
```bash
hermes --continue                # resume most recent session
hermes --resume <session_id>     # resume a specific one (from `hermes sessions list`)
```

## Step 2 — Reconstruct the prior session state (when continuing in-place)

Do NOT ask the user to repeat themselves — pull it from history:
1. `session_search()` browse — list recent sessions, pick the matching one by
   title/preview/date.
2. `session_search(session_id="<id>")` read-mode — returns FIRST 20 + LAST 10
   messages. The tail is gold: the final assistant message usually contains the
   explicit "interrupted here / leftover: X" summary (tool-iteration caps often end
   sessions mid-wiring).
3. `session_search(query="<topic>", sort="newest")` — find the most recent state
   summary, including handoff summaries made from OTHER platforms (e.g. a QQ-bot
   session that already summarized the CLI work).

## Step 3 — Verify environment is still alive before touching code

Prior sessions leave long-running processes. Check before rebuilding anything:
- Backend: `ss -tlnp | grep :8080` + `ps aux | grep "java -jar.*admin.jar"`
- Frontend: `ps aux | grep vite` (jonlink: vite on :80, dev server)
- DB: `mysqladmin ping` / `systemctl is-active mariadb`
- Backend log file path (jonlink: `/tmp/jonlink-admin.log`) for verifying calls.
Report the leftover task + running services as a compact table, then finish the job
in ONE pass — including browser verification of the exact thing that was left broken
(see Step 4).

## Step 4 — Finish the leftover, verify end-to-end

Pick up the explicit leftover from the old session's tail (e.g. "button added but
handler not wired"). For RuoYi-Vue3-TS page fixes, the complete workflow is in
`jonlink-vue3-admin-scaffolding` P25/P26 (dead-button wiring + types-barrel imports).
Verification = browser click → dialog → backend log line → DB idempotency check, NOT
just "compiles".

## Pitfalls

- **Do not recreate the wheel**: the old session usually already did the design work;
  read its tail summary before proposing a new approach.
- **Sibling pages are the pattern source**: for frontend wiring, copy the idiom from a
  working sibling page in the same module, not from memory.
- **"没上下文" ≠ "没记忆"**: persistent memory/skills ARE loaded in new sessions; only
  the conversation transcript is per-session. Say so when the user worries.
- **QQ/gateway sessions may already contain the handoff summary** — search them too
  (user often checks in via QQ the next morning before the CLI session).
