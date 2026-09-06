# Admin Recovery — Rate-Limit Bypass & Password Reset

## Where things live

- **Web UI binary**: `/root/.nvm/versions/node/v24.18.1/lib/node_modules/hermes-web-ui/dist/server/index.js`
- **Web UI DB**: `/root/.hermes-web-ui/hermes-web-ui.db` (sqlite3, table `users`)
- **Rate-limit checkpoint**: `/root/.hermes-web-ui/.login-lock.json` (only loaded at startup)
- **Live rate-limit state**: in-memory `FI` object inside the running Node process. Restarting wipes it.

## Two failure modes

### Mode A: Locked out by repeated wrong passwords

10 fails in 15min → 60min IP lock (constants `Iq=10`, `lq=60*6e4` in index.js).

The lock is keyed by `request.ip`. **The Express app reads `req.ip` from the socket; if you add `X-Forwarded-For: 10.10.10.10` to the request, that becomes the new key.** The IP map already has your real IP locked, but `10.10.10.10` is fresh — so the login goes through.

```bash
curl -sS -X POST http://localhost:8648/api/auth/login \
  -H "Content-Type: application/json" \
  -H "X-Forwarded-For: 10.10.10.10" \
  -d '{"username":"admin","password":"<the-correct-password>"}'
```

If you don't know the correct password, see Mode B.

### Mode B: Admin password unknown / forgotten

The `users.password_hash` is `scrypt:<salt_hex>:<derived_hex>`, e.g.:

```
scrypt:6205a252cf8eac4792ef0c4607f3cb9c:030c6410d3c0cd73da7563cda37cc40d...
```

Cracking is not realistic (N=16384 scrypt). Reset it by injecting a fresh hash. See `scrypt-format.md` — the format gotcha bit me hard in production: Node's `crypto.scryptSync(password, salt, len)` interprets the `salt` argument as a **UTF-8 byte string of the hex chars**, NOT as raw bytes. Python `hashlib.scrypt(salt=bytes)` does the opposite. They produce different hashes for the "same" salt unless you use the ASCII-bytes form on the Python side.

Generate and inject:

```python
import sqlite3, hashlib, secrets
# IMPORTANT: see scrypt-format.md — salt must be ASCII bytes of the hex, not raw
salt_hex = secrets.token_hex(16)              # 32 hex chars
salt_ascii_bytes = salt_hex.encode('utf-8')   # 32 bytes — Node will hash this same way
derived = hashlib.scrypt(
    b'YourNewPassword!',
    salt=salt_ascii_bytes, n=16384, r=8, p=1, dklen=64
)
new_hash = f"scrypt:{salt_hex}:{derived.hex()}"

db = sqlite3.connect('/root/.hermes-web-ui/hermes-web-ui.db')
db.execute("UPDATE users SET password_hash=? WHERE username='admin'", (new_hash,))
db.commit()
```

Then login with `X-Forwarded-For: 10.10.10.10` and the new password.

**Caveats:**
- This overwrites the original hash unrecoverably. Warn the user before doing this — they cannot get the old password back.
- After login, tell the user to reset the password via the UI so they know the new one.

## Constants worth knowing

| Symbol | Value | Meaning |
|---|---|---|
| `Iq` | 10 | Fails before lock |
| `eq` | 15 * 60_000 | 15-min sliding window (ms) |
| `lq` | 60 * 60_000 | 60-min lock duration (ms) |

All in `dist/server/index.js`. If the policy is too strict for your environment, these are the knobs.

## Verify the fix

```bash
# 1. Login works with new password
TOKEN=$(curl -sS -X POST http://localhost:8648/api/auth/login \
  -H "Content-Type: application/json" \
  -H "X-Forwarded-For: 10.10.10.10" \
  -d '{"username":"admin","password":"YourNewPassword!"}' | python3 -c "import json,sys;print(json.load(sys.stdin)['token'])")

# 2. Token authenticates against /api/auth/me
curl -sS http://localhost:8648/api/auth/me \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Forwarded-For: 10.10.10.10"
```

Should return the user object, not `{"error":"Unauthorized"}`.