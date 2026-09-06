---
name: hermes-system-diagnostics
description: "Diagnose Hermes Agent ↔ Web UI integration and API 404s."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [hermes, web-ui, integration, diagnostics, api, troubleshooting]
    related: [hermes-agent]
---

# Hermes System Diagnostics

Diagnose integration issues between **Hermes Agent** (Python CLI/gateway), **Hermes Web UI** (Node dashboard on port 8648), **Hermes Studio MCP** (browser/api/devices/use tool servers), and the **Agent Bridge** (Python↔Node IPC).

Use this when a user reports: "API 404", "修改密码 404", "Web UI can't talk to agent", "port mismatch", or any cross-component symptom where the bug is somewhere in the seam between services.

## Component map (verify before diagnosing)

Always confirm the running topology first. Don't trust config files — verify with `lsof -i`/`ss -tlnp`:

| Component | Port | Process hint | Data location |
|---|---|---|---|
| **Hermes Agent CLI** | n/a | `/usr/local/lib/hermes-agent/venv/bin/python hermes ...` | `/root/.hermes/` (config.yaml, .env, state.db, sessions/) |
| **Hermes Agent Gateway** | **18789** (loopback) | `hermes gateway run --replace` | same as above |
| **Hermes Web UI server** | **8648** (all interfaces) | `node .../hermes-web-ui/dist/server/index.js` | **`/root/.hermes-web-ui/`** (hermes-web-ui.db, .login-lock.json, logs/) |
| **Agent Bridge** | `ipc:///tmp/hermes-agent-bridge.sock` | `hermes_bridge.py` | n/a (transient) |
| **Hermes Studio MCP servers** | stdio (watchdog-spawned) | `bin/hermes-studio-mcp.mjs {api,browser,devices,use}` | n/a |
| **OpenClaw gateway** (separate product) | 18789 too — be careful | `openclaw/dist/index.js gateway` | `/root/.nvm/.../openclaw/` |

**Critical**: Web UI's database is **NOT** under `~/.hermes/` — it's under `~/.hermes-web-ui/`. Searching the wrong directory wastes hours.

## Diagnostic workflow

Follow this order — earlier steps eliminate whole classes of misdiagnosis:

### 1. Verify topology and reachability
```bash
ss -tlnp | grep -E '8648|18789'
curl -s http://localhost:8648/api/health | head -1   # should be 200
curl -s http://localhost:18789/health | head -1       # agent gateway
```

### 2. Get the source of truth: OpenAPI spec
```bash
curl -s http://localhost:8648/api/openapi.json | python3 -c "import json,sys; d=json.load(sys.stdin); print(len(d['paths']))"
```
Returns ~278 routes. **BUT**: routes registered with sub-router instances like `var kY=new q; kY.post("/api/hermes/auth/minimax/start", ...)` do NOT appear in OpenAPI. If you suspect a route is "missing" from OpenAPI, grep the server bundle directly:
```bash
strings /root/.nvm/versions/node/v24.18.1/lib/node_modules/hermes-web-ui/dist/server/index.js | grep -E '/auth/|/api/' | head -30
```

### 3. Cross-check frontend vs backend
- Frontend calls live in `/root/.nvm/versions/node/v24.18.1/lib/node_modules/hermes-web-ui/dist/client/assets/js/*.js`
- Look for `s("/api/...", ...)` patterns — that's the authenticated fetch helper
- Compare against OpenAPI `paths` set; missing-in-OpenAPI is NOT the same as missing-on-server

### 4. Test with real auth, not just existence
Static 200/401 probes lie. To run end-to-end tests you need a valid token. Steps:
1. Look up the user in `sqlite3 /root/.hermes-web-ui/hermes-web-ui.db`
2. Generate a matching scrypt hash (see `references/known-quirks.md` for the salt-encoding pitfall)
3. Inject hash → login → use token

### 5. Interpret "404" reports carefully
Users often confuse:
- **401 Unauthorized** → frontend fetch helper auto-logs-out and redirects to login. The user sees "an error" but no clear status code.
- **400 Bad Request** with body `{"error":"..."}` → server-side validation, NOT a routing failure
- **404 Not Found** → only when the route truly doesn't exist (rare; see Known Quirks)

Always test the URL the frontend actually calls, not what you assume it should call.

### 6. "Gateway is dead / QQBot broken" triage (verified 2026-09)
User reports "QQBot unavailable / skills broken / mcp can't see" — often conflated. Run this matrix:

```bash
hermes gateway status          # Active: inactive|active; "Stale gateway_state.json" warning is normal after SIGTERM
hermes gateway list            # which profiles exist; should NOT all show "not running"
ss -tlnp | grep -E '8648|18789'   # Web UI / agent bridge ports
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8648/healthz
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8648/mcp/{api,use,devices}
```

**Stale-state pitfall**: `gateway_state.json` shows `running` but process is gone. Means the unit died ungracefully (SIGTERM, OOM, parent killed). `hermes gateway start` recreates state cleanly. **Do not** try to edit state.json by hand.

**Unit definition outdated**: status line says `Installed gateway service definition is outdated`. Run `hermes gateway restart` (auto-refreshes unit). `restart` sometimes hangs → use `stop` then `start`.

After start, verify adapter loaded by grepping fresh gateway.log lines (timestamp > start time):
```bash
journalctl --user -u hermes-gateway.service -n 30 --no-pager    # often empty (no journal)
tail -50 /root/.hermes/logs/gateway.log | grep -iE "(adapter|connected|websocket|ready)"
```

QQBot adapter success pattern: `Access token refreshed → WebSocket connected → Identify sent → Ready, session_id=...`. Anything before "Ready" is in-progress; anything after, like `code=4009 Session timed out`, is a reconnect cycle (normal).

### 7. User-stated-vs-actual config drift ("I configured X already")
Frequent pattern: user says "X is configured / enabled / running" but config has zero evidence. **Always grep first, then state the delta in a comparison table**. Don't substitute memory for grep — see `references/cross-tool-memory-drift.md` for the SOP.

```bash
# Config evidence checklist (run all four, then table them):
grep -nE "(qqbot|QQBot|tencent)" /root/.hermes/config.yaml
grep -nE "^QQ|^QQBOT" /root/.hermes/.env | sed 's/=.*/=***/'
jq '.providers | keys' /root/.hermes/auth.json
ls /root/.hermes/skills/ | wc -l
```

Then format as:
| Source | User claims | Actual grep result |
|---|---|---|
| config.yaml | "QQBot registered" | line 188-189: `qqbot: [hermes-qqbot]` ✅ |
| .env | "all keys there" | 5 vars present, all non-placeholder ✅ |
| auth.json | "qqbot provider set" | 0 hits in `.providers` ❌ |

The key insight: **`auth.json` is the LLM credential pool** (minimax/deepseek/etc), **NOT platform adapter credentials**. Platform adapters (QQBot/Telegram/Discord/Slack) read `.env` directly. Don't tell the user "auth.json is missing QQBot" — that's a category error.

## Known 404 hotspots (verified 2026-08)

| Frontend calls | Reality | Fix |
|---|---|---|
| `/api/hermes/v1/` (in `index-BhdrPxdZ.js`) | does NOT exist | Remove or replace — leftover stub |
| `/api/tts/proxy` (in `ChatPanel`, `GroupChatView`) | real path is `/api/tts/proxy/audio/speech` | Frontend uses this as `baseUrl` only — actual call appends `/audio/speech` |
| `/api/hermes/kanban/events` (in `KanbanView`) | registered as **WebSocket**, not HTTP | Use `ws://` URL, not `fetch()`. GET returns 404 with "Task not found" |

## See also
- `references/known-quirks.md` — scrypt hash format, IP rate limiter mechanism and bypass, .login-lock.json structure, fetch helper behavior
- `references/port-and-process-map.md` — extended troubleshooting commands and per-process log locations
- `references/gateway-and-platforms.md` — Gateway lifecycle (start/stop/restart pitfalls), QQBot variable names, `hermes send` syntax, e2e verification
- `references/cross-tool-memory-drift.md` — "user says X but grep says Y" SOP and the compare-table template