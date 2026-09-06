---
name: hermes-web-ui-admin
description: "Recover Hermes Web UI admin and debug SPA 404s."
version: 0.1.0
author: Hermes Agent
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [hermes, hermes-web-ui, admin-recovery, route-debugging, scrypt, auth]
---

# Hermes Web UI Admin & Route Debugging

Two related diagnostic tasks that recur on the same host:
1. **Admin recovery** — forgotten/breached password, login rate-limit lockout (10 fails → 60min IP lock, in-memory).
2. **Route 404 hunting** — user reports "API 404" but the route works in isolation; usually a typo, missing `/api/hermes/` prefix, or SPA fallback eating a real 404.

The SPA auth helper silently logs the user out on 401, which makes 401 look like "the page broke" and 404 (raised as `API Error 404: ...` toast) look like a path problem. Get the diagnosis right before touching anything.

## Quick reference

| Symptom | Real cause | Fix |
|---|---|---|
| "I can't log in" after wrong password repeated | 10-fail IP lock, 60min | `X-Forwarded-For: 10.10.10.10` header (see references/admin-recovery.md) |
| Admin password lost | scrypt hash unrecoverable | Inject new hash via sqlite3 (see references/scrypt-format.md) |
| "API 404" but OpenAPI lists it | typo in SPA path or wrong HTTP method | Cross-check `dist/client/assets/js/*.js` → `dist/server/index.js` |
| "404 Not Found" on a clearly-listed route | Wrong method, missing token, or SPA fallback eating the route | Test with explicit `method=` and `Authorization:` |
| `Kt()` fetch helper silently kicks user to /login | 401 from upstream, not a code bug | Check upstream status, not the URL |

## Hard invariants

- **Web UI port is 8648** by default; Hermes Gateway is 18789. They are separate. Mixing them up is the #1 confusion source.
- **Backend DB is at `/root/.hermes-web-ui/hermes-web-ui.db`** (sqlite3). NOT in `/root/.hermes/`.
- **Rate-limit state is in-memory** (`FI` object in `dist/server/index.js`). Restarting the service clears it. The on-disk `.login-lock.json` is only a checkpoint — restart fully wipes in-memory state.
- **OpenAPI is incomplete.** It misses routes registered by the `q` / `kY` / `EV` / `jc` express sub-routers that scan over OAuth provider lists. Always test the actual URL, not just OpenAPI.

## Workflow

1. **Confirm scope.** Are we recovering admin access, or chasing a 404? Different references.
2. **If admin recovery** → `references/admin-recovery.md` — covers X-Forwarded-For bypass, sqlite password reset, and the critical scrypt format gotcha.
3. **If 404 debugging** → `references/route-debugging.md` — covers the cross-check pattern (SPA → openapi.json → curl with auth) and the actual 404 root cause list (3 real ones as of v0.6.37).
4. **Always verify the fix.** End-to-end: login → exercise the action → confirm in DB.

## Reference files

- `references/admin-recovery.md` — login rate-limit mechanics, password hash injection, scrypt format gotcha
- `references/route-debugging.md` — SPA↔backend path cross-check, known 404 list, fetch helper behavior
- `references/scrypt-format.md` — why Python `hashlib.scrypt` doesn't match Node `crypto.scryptSync` for the same input
- `templates/diagnose_404.sh` — shell script that diffs SPA calls against OpenAPI and reports genuine 404s