# Hermes Gateway & Platform Adapter Reference

Verified 2026-09. Sources: `hermes gateway status/list`, `~/.hermes/logs/gateway.log`, `~/.hermes/.env`, `~/.hermes/config.yaml`, `~/.hermes/auth.json`.

## Gateway lifecycle

| State | Detection | Action |
|---|---|---|
| `Active: active (running)` | `hermes gateway status` | No action |
| `Active: inactive (dead)` + `Stale gateway_state.json` | SIGTERM/kill without cleanup | `hermes gateway start` (cleans state) |
| `Active: inactive` + `service definition is outdated` | unit file drifted from current install | `hermes gateway restart` refreshes unit; if it hangs: `stop` then `start` |
| Active but adapters `Disconnected` | adapter token expired / network | Check `tail gateway.log | grep -iE "token|websocket|disconnect"` |

**Pitfall — `restart` vs `start`+`stop`**: `hermes gateway restart` occasionally hangs for 30+ s and returns timeout. If that occurs, fall back to `stop` then `start` — they're separate transactions, each returns cleanly.

**Pitfall — gateway start kills running agent sessions** (per memory 2026-09-01). CLI/TUI sessions are NOT affected; only platform-originated gateway chats die.

**Pitfall — Web UI (`8648`) and Gateway (`18789`) are independent**. Web UI keeps running even when gateway is dead. Don't conflate "Web UI 200" with "gateway healthy".

## QQBot adapter — exact variable names

In `~/.hermes/.env`:

| Variable | Purpose | Example format |
|---|---|---|
| `QQ_APP_ID` | bot app id | 10-digit numeric |
| `QQ_CLIENT_SECRET` | OAuth secret | 32-char alphanumeric |
| `QQ_ALLOW_ALL_USERS` | "true"/"false" gate | lowercase |
| `QQ_ALLOWED_USERS` | allowlist, comma-separated openids | openid hex strings |
| `QQBOT_HOME_CHANNEL` | home channel id (chat_id) | openid hex string |

**Common misconceptions**:
- Variable names are **NOT** `QQ_BOT_TOKEN` / `QQ_BOT_SECRET`. The actual names are `QQ_APP_ID` / `QQ_CLIENT_SECRET`.
- `auth.json` does **NOT** need a `qqbot` provider entry. `auth.json` is the **LLM** credential pool (minimax/deepseek/anthropic/etc), NOT platform credentials. Platform adapters read `.env` directly.
- `config.yaml` only needs `qqbot: [hermes-qqbot]` under `platform_toolsets`. Don't add extra config blocks — adapter code reads env directly.

## Verifying QQBot is live

```bash
# 1. Adapter loaded (look for Access token refreshed after start time)
tail -100 /root/.hermes/logs/gateway.log | grep -E "Access token|WebSocket connected|Identify sent|Ready"

# 2. e2e send (note: -t flag, message is positional)
hermes send -t qqbot "ping $(date +%H:%M:%S)"
# Expected: "Sent to qqbot home channel (chat_id: ...)"

# 3. Wrong syntax trap
hermes send qqbot "msg"   # ERROR: "unrecognized arguments: msg" — positional msg without -t
hermes send -h             # shows: -t TARGET required, message is positional
```

## Other platform adapters (same pattern)

Telegram, Discord, Slack, Signal, WhatsApp all follow the same shape:
- Variables in `.env` (e.g. `TELEGRAM_BOT_TOKEN`, `SLACK_BOT_TOKEN`)
- Adapter auto-loads if env vars present + `platform_toolsets.<name>` registered
- `hermes send -t <platform> "msg"` to e2e test
- Adapter code at `/usr/local/lib/hermes-agent/gateway/platforms/<name>/`

For platform-specific docs: `/usr/local/lib/hermes-agent/website/docs/user-guide/messaging/<name>.md`.