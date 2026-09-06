# Why Python `hashlib.scrypt` ≠ Node `crypto.scryptSync` for the same "salt"

Both functions accept a "salt" argument but interpret it differently. This is the gotcha that burns you every time you try to forge a Node-format scrypt hash from Python.

## The trap

Node:

```js
// dist/server/index.js — actual code
function AX(I) {
  let e = randomBytes(16).toString('hex');                  // "abcd1234..." (string)
  let l = scryptSync(I, e, 64).toString('hex');              // scryptSync(pwd, saltString, len)
  return `scrypt:${e}:${l}`;
}

function Nh(I, e) {
  let [l, t, n] = e.split(':');
  let c = Buffer.from(n, 'hex');                            // the stored hash, as raw bytes
  let G = scryptSync(I, t, c.length);                       // scryptSync(pwd, saltString, len)
  return G.length === c.length && timingSafeEqual(G, c);
}
```

So Node takes the salt as a **string** (which becomes UTF-8 bytes of the hex characters). For a 32-char hex salt, that's 32 ASCII bytes — NOT 16 raw random bytes.

Python's natural reading:

```python
import hashlib, secrets
salt = secrets.token_bytes(16)                              # 16 raw bytes — WRONG for Node compat
hashlib.scrypt(b'pwd', salt=salt, n=16384, r=8, p=1, dklen=64)
```

This produces a hash that won't validate in Node because Node is hashing with 32 ASCII bytes (the hex string) as the salt, not the 16 raw bytes.

## Correct Python that matches Node

```python
import hashlib, secrets
salt_hex = secrets.token_hex(16)                            # 32 hex chars, e.g. "ab12cd34..."
salt_ascii_bytes = salt_hex.encode('utf-8')                 # 32 ASCII bytes — match Node
derived = hashlib.scrypt(b'pwd', salt=salt_ascii_bytes, n=16384, r=8, p=1, dklen=64)
hash_hex = derived.hex()
stored = f"scrypt:{salt_hex}:{hash_hex}"                    # matches Node format exactly
```

Defaults are the same: `n=16384, r=8, p=1, maxmem=32MB`. Use `dklen=64` (constant `K8I` in the JS).

## Why Node treats strings this way

Per the Node docs: "If `salt` is a string, it is encoded as UTF-8 before being used." This is buried — most people expect `Buffer.from(saltString, 'hex')` behavior, but Node does NOT do that for you. It just stringifies the salt and feeds the bytes in.

## Verification

```python
# In one process, check Python output against a known-good Node hash
import subprocess, json
# Take any existing user row's hash and verify a Python-generated one validates.
# Easiest: log in via curl with the password you used in Python.
# If you get 200, your hash matches what Nh() will compute.
```

## Round-trip sanity check (works without server)

You can verify the format locally with Node REPL:

```bash
node -e "
const { scryptSync, timingSafeEqual } = require('crypto');
const salt = 'ab12cd34ef56...';  // 32 hex chars
const hash = scryptSync('password', salt, 64).toString('hex');
console.log('scrypt:' + salt + ':' + hash);
"
```

Paste that into the DB and login via curl to confirm.

## Other Node-vs-Python crypto gotchas (for future reference)

- **bcrypt**: not used here, but if it ever comes up, Node's `bcrypt` and Python's `bcrypt`/`passlib` both store self-describing strings (`$2b$...`) — no salt-encoding trap.
- **argon2**: same UTF-8 salt rule. Node's argon2 will encode a string salt as UTF-8 bytes; Python's argon2-cffi treats `salt=bytes` as raw bytes.
- **PBKDF2**: same trap. Always encode salt as UTF-8 bytes of the string when matching Node.