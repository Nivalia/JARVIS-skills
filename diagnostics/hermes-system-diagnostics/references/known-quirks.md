# Known Quirks

Non-obvious behaviors in the Hermes stack that cause diagnostic misreads.

## 1. Scrypt hash format — salt is the hex STRING, not the binary

Web UI stores passwords as `scrypt:<salt_hex>:<hash_hex>`. The Node verification function `Nh`:

```js
function Nh(I, e) {  // I = password, e = stored hash
  let [l, t, n] = e.split(":");
  // l = "scrypt", t = salt_hex (string), n = hash_hex (string)
  let c = Buffer.from(n, "hex");
  let G = scryptSync(I, t, c.length);  // ← salt is passed as the HEX STRING
  return G.length === c.length && timingSafeEqual(G, c);
}
```

**Trap**: `scryptSync(password, salt, dklen)` — when `salt` is a string, Node treats it as UTF-8 bytes. So the salt input is actually the **ASCII bytes of the hex string** (32 bytes), not the original 16 random bytes.

**Correct Python injection**:

```python
import hashlib, secrets

def make_hash(password):
    salt_hex = secrets.token_hex(16)  # 32 hex chars = 16 raw bytes
    salt_ascii = salt_hex.encode("utf-8")  # 32 ASCII bytes (this is what Node uses!)
    derived = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt_ascii,        # ← 32-byte ASCII string of the hex
        n=16384, r=8, p=1,
        dklen=64                # K8I in the bundle
    )
    return f"scrypt:{salt_hex}:{derived.hex()}"

# Inject into /root/.hermes-web-ui/hermes-web-ui.db
```

If you pass `salt=secrets.token_bytes(16)` (the raw 16 bytes), the login will return 401 — the hashes won't match.

## 2. IP rate limiter persists, trusts X-Forwarded-For

The login rate limiter (constants `Iq=10`, `lq=60*60e3` = 60min, window `eq=15*60e3`) tracks failures per `jE(req)` which is `req.ip || req.request?.ip || "unknown"`.

**Critical security/diagnostic issue**: Web UI's `jE()` accepts `X-Forwarded-For` and `X-Real-IP` headers with **no proxy validation**. During diagnostics this is your friend — you can bypass the IP lockout by sending `X-Forwarded-For: 10.10.10.10`. In production it's an authentication bypass if the UI is exposed without a trusted reverse proxy.

**State file**: `/root/.hermes-web-ui/.login-lock.json`
```json
{
  "passwordIpMap": { "<ip>": { "failures": N, "lockedUntil": <ms>, "firstFailureAt": <ms> } },
  "globalMinuteCount": 0,
  "globalLockedUntil": 0
}
```

In-memory state is saved to disk by `kr()` after changes; loaded at startup. To clear without restarting: write `{"passwordIpMap": {}, ...}` to the file then send SIGHUP/restart the service.

## 3. Frontend fetch helper auto-logs-out on 401

In `dist/client/assets/js/index-BhdrPxdZ.js` the helper `Kt(e, t)`:

```js
const a = await fetch(r, {...t, headers: n});
const l = !e.startsWith("/api/hermes/v1/") && !e.startsWith("/v1/");
if (a.status === 401 && l) {
  Vk();                          // ← clears token
  qm("expired");                  // ← toast "session expired"
  if (route !== "login") router.replace({ name: "login" });
  throw new Error("Unauthorized");
}
```

**Why this matters for diagnosis**: When a user says "modifying password gives me an error", what they often saw was the login redirect (because their JWT had expired between Settings page load and submit). They remember "an error happened" but the actual status code was 401, not 404. Always check `/api/auth/me` with the token they were using to confirm.

## 4. OpenAPI spec misses sub-router routes

Routes registered via sub-instances (`var kY = new q(); kY.post(...)`) don't appear in `/api/openapi.json`. The scan walks only the top-level `app` routes. Example: `/api/hermes/auth/minimax/start` is registered on `kY`, not `app`, so it's invisible in the spec.

**Diagnostic shortcut**: when the frontend calls a URL not in OpenAPI, don't conclude it's missing. Grep the bundle:
```bash
strings <server_index_js> | grep -F "$url"
```

## 5. SPA fallback masks 404s in some cases

The web UI has a catch-all that returns the SPA shell (200 + HTML) for unmatched paths **only when the path doesn't start with `/api/`**. Pure-API paths always hit the router and return real 404s. So a frontend bug that posts to `/foo/bar/baz` returns 404, but `get('')` or '' returns the SPA shell. Use `curl -i` (not `-I`) to confirm.

## 6. SQLite command not always available

The host where hermes-agent ships often lacks the `sqlite3` binary. Use Python:
```python
import sqlite3
db = sqlite3.connect("/root/.hermes-web-ui/hermes-web-ui.db")
cur = db.cursor()
cur.execute("SELECT username, substr(password_hash,1,40) FROM users").fetchall()
```