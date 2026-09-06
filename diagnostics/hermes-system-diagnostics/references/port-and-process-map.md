# Port and Process Map

Detailed commands for confirming the running Hermes topology and locating logs.

## Quick reachability check

```bash
# Listening ports
ss -tlnp 2>/dev/null | grep -E '8648|18789'

# Process details
ps -eo pid,user,cmd | grep -E 'hermes-web-ui|hermes_bridge|hermes gateway|hermes-studio-mcp' | grep -v grep

# Health probes
curl -sS http://localhost:8648/api/health   # Web UI
curl -sS http://localhost:18789/health       # Agent gateway (loopback only)
curl -sS http://localhost:8648/api/openapi.json | python3 -c "import json,sys;d=json.load(sys.stdin);print(f'{len(d[\"paths\"])} routes')"
```

## Process → log mapping

| Process | Log location |
|---|---|
| Web UI server | `/root/.hermes-web-ui/logs/server.log` and `/root/.hermes-web-ui/server.log` |
| Agent Bridge (Python) | `/root/.hermes-web-ui/logs/bridge.log` |
| Hermes Gateway | `/root/.hermes/logs/` (gateway-starts.log, gateway output) |
| MCP servers (api/browser/devices/use) | watchdog-managed; check `/root/.hermes/logs/` or journalctl |

## DB locations

| Component | DB path |
|---|---|
| Web UI users/sessions/etc | `/root/.hermes-web-ui/hermes-web-ui.db` (sqlite, has `users`, `sessions`, `messages`, `workflows`, `kanban_*, `gc_*`, `user_themes`, `mcu_devices`...) |
| Hermes Agent sessions/state | `/root/.hermes/state.db` |
| Hermes Kanban | `/root/.hermes/kanban.db` |
| Web UI login lockout state | `/root/.hermes-web-ui/.login-lock.json` (JSON file, not sqlite) |
| Web UI device identity | `/root/.hermes-web-ui/device-identity.json` |

## Clearing login rate-limit without restart

```bash
echo '{"passwordIpMap":{},"tokenIpMap":{},"pairingIpMap":{},"globalMinuteCount":0,"globalMinuteWindow":0,"globalTotalFailures":0,"globalLockedUntil":0}' > /root/.hermes-web-ui/.login-lock.json
# Then restart the web UI: kill the node process; launcher restarts it
```

Or bypass per-request (debugging only):
```bash
curl -X POST http://localhost:8648/api/auth/login \
  -H "Content-Type: application/json" \
  -H "X-Forwarded-For: 192.168.99.99" \
  -d '{"username":"admin","password":"..."}'
```

## Restart commands

```bash
# Web UI (depends on how it was started; the OpenClaw-style launcher auto-respawns)
pkill -f 'hermes-web-ui/dist/server/index.js'
# Hermes gateway (similar auto-restart pattern)
hermes gateway restart   # if CLI installed; otherwise kill+respawn

# Force a fresh agent gateway:
hermes gateway run --replace &
```

## Useful bundle grep commands

```bash
# List all API paths registered in the bundle (including sub-routers)
strings /root/.nvm/versions/node/v24.18.1/lib/node_modules/hermes-web-ui/dist/server/index.js | grep -oE '/api/[a-zA-Z0-9_/{}/:.-]+' | sort -u

# Find specific handler
grep -aoE 'function [a-zA-Z]+\([^)]*\)\{[^}]*(change|password)[^}]*\}' /root/.nvm/versions/node/v24.18.1/lib/node_modules/hermes-web-ui/dist/server/index.js | head -5

# List frontend fetch URLs
grep -hoE '"/api/[^"]+"' /root/.nvm/versions/node/v24.18.1/lib/node_modules/hermes-web-ui/dist/client/assets/js/*.js | sort -u
```