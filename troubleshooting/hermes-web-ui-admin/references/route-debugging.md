# SPA ↔ Backend Route Debugging

The user reports "API 404" but the route works. Usually the diagnosis is:

1. The user is reading the wrong status code (401 masquerades as "session expired", 403 as "forbidden", and only 404 stays 404 in the toast).
2. The SPA fallback at `/` catches everything that isn't `/api/*`, so GET on a path that should be POST returns the SPA HTML.
3. There's an actual typo in the SPA bundle.

## The fetch helper that lies to you

In `dist/client/assets/js/index-BhdrPxdZ.js`:

```js
async function Kt(e, t = {}) {
  // ... builds headers, adds Authorization from Hl() ...
  const a = await fetch(r, { ...t, headers: n });
  const l = !e.startsWith("/api/hermes/v1/") && !e.startsWith("/v1/");
  if (a.status === 401 && l) {
    throw Vk(),         // clears token
      qm("expired"),    // toast "login expired"
      Fi.currentRoute.value.name !== "login" && Fi.replace({ name: "login" }),
      new Error("Unauthorized");
  }
  if (!a.ok) {
    const s = await a.text().catch(() => "");
    throw a.status === 403 && l && s.includes("User is disabled or does not exist")
      ? (Vk(), qm("expired"), ..., new Error("Unauthorized"))
      : qm("forbidden"),
      new Error(`API Error ${a.status}: ${FG(s, a.statusText)}`);
  }
  return a.json();
}
```

Translation:
- **401** → silently log out and bounce to `/login`. User sees "session expired", thinks their password is wrong.
- **403** with "User is disabled" → same treatment.
- **Anything else** (including 404) → toast `forbidden` and throw `API Error {code}: {body}`. User sees a number in a toast.

So when the user reports "404" they have usually seen an actual 404 toast, but the upstream cause is more often:
- Wrong method (frontend says GET, backend only registers POST)
- Token expired (which the helper would have caught, but only on `/api/*` — `/v1/*` and `/api/hermes/v1/*` skip the auto-logout, so a 401 there surfaces as 401 in the toast)
- The URL is genuinely missing from the backend

## The actual 404 hunting workflow

```bash
# 1. Enumerate every static path the SPA actually requests
cd /root/.nvm/versions/node/v24.18.1/lib/node_modules/hermes-web-ui/dist/client/assets/js
grep -rohE '"/api/[^"]+"|`/api/[^`]+`' . \
  | sed -E 's/^["`]|["`]$//g' \
  | grep -v '\${' | grep -v ':[a-z]' \
  | sort -u > /tmp/spa-paths.txt

# 2. Pull the OpenAPI route catalog
curl -s http://localhost:8648/api/openapi.json | python3 -c "
import json,sys
spec=json.load(sys.stdin)
for p in spec['paths']: print(p)
" | sort -u > /tmp/openapi-paths.txt

# 3. Diff — paths in SPA but NOT in OpenAPI
comm -23 /tmp/spa-paths.txt /tmp/openapi-paths.txt
```

**But wait** — OpenAPI is **incomplete**. It misses routes registered by the inline sub-routers (`q`, `kY`, `EV`, `jc`) that iterate over OAuth provider lists. Treat the diff as **suspects**, not verdicts. Test each one for real with curl before reporting.

## Test each suspect (with auth)

```bash
# Get a token
TOKEN=$(curl -sS -X POST http://localhost:8648/api/auth/login \
  -H "Content-Type: application/json" \
  -H "X-Forwarded-For: 10.10.10.10" \
  -d '{"username":"admin","password":"HermesTest2026!"}' | python3 -c "import json,sys;print(json.load(sys.stdin)['token'])")

# Try the suspect
for url in /api/hermes/auth/minimax/start /api/hermes/v1/ /api/tts/proxy; do
  for method in GET POST; do
    code=$(curl -sS -o /dev/null -w "%{http_code}" -X $method \
      "http://localhost:8648$url" \
      -H "Authorization: Bearer $TOKEN" \
      -H "Content-Type: application/json" \
      -d '{}')
    echo "$method $url → $code"
  done
done
```

| Code | Meaning |
|---|---|
| 200, 400 (validation error) | Route exists, body schema is wrong |
| 401 | Route exists, you lost auth — get a fresh token |
| 404 | **Route is genuinely missing** — this is a real bug |
| 405 | Method not allowed — frontend is sending the wrong verb |

## Known real 404s as of web-ui v0.6.37

These are bugs that exist today (from production debugging on 2026-08-05):

1. `/api/hermes/auth/minimax/start` (and `/poll/:id`) — frontend `ModelsView-935qUyTa.js` writes `minimax` instead of `minimax`. Backend registers `minimax`. Real 404.
2. `/api/hermes/v1/` — sometimes called from `index-BhdrPxdZ.js`. Backend never registers this exact path.
3. `/api/tts/proxy` (without `/audio/speech`) — frontend uses as a `baseUrl` default in `ChatPanel-RXiioiaT.js`; users normally overwrite it but if not, the base URL alone 404s.

False positives (OpenAPI missing them but they actually work):
- `/api/hermes/auth/minimax/start` and related — registered in the inline sub-router `kY`, not surfaced in OpenAPI
- `/api/hermes/pets/*` — registered by sub-router
- `/api/hermes/workflows/*` — registered by sub-router
- `/api/mcu-devices` — registered by sub-router
- `/api/hermes/kanban/events` — WebSocket, not HTTP GET

## Common SPA typos that turn into 404

- `minimax` vs `minimax`
- missing `/api/hermes/` prefix (some routes need it, some don't — `/api/auth/*` does not, `/api/hermes/*` does)
- `/api/tts/proxy` vs `/api/tts/proxy/audio/speech`
- Wrong dynamic param encoding (`${id}` vs `:id` vs `{id}` — backend uses `{id}`)

Always cross-check against `dist/server/index.js` for the actual `q.post(...)` / `kY.get(...)` / etc. registration.

## Verify before declaring it fixed

End-to-end: log in via the SPA, exercise the action in the browser, watch DevTools Network tab for the actual status code, and confirm DB side-effects (e.g., new row in `jl_notice_log` after a notice push).