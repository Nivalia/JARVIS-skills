---
name: obsidian-self-host
description: Self-host Obsidian via CouchDB + git remote on Linux.
---

# Self-Hosted Obsidian with CouchDB LiveSync + Git Backup

Class: deploy a fully self-managed Obsidian knowledge vault on a remote Linux server (Debian/Ubuntu) with **two sync layers**:

1. **Git remote (bare repo)** — point-in-time backup, 5-min auto-push via Obsidian Git plugin, gives full history and offline cold-restore.
2. **CouchDB + Self-hosted LiveSync** — real-time multi-device sync (desktop ⇄ mobile ⇄ tablet), end-to-end encrypted with a user passphrase, conflict-free.

Replaces Obsidian's official Sync ($4/mo) and runs on a server the user already controls.

## When to use

Trigger any of:
- User says "在服务器部署 Obsidian / 自托管 / 不想买 Obsidian Sync"
- User wants Obsidian sync between desktop and phone without the official cloud
- User wants full vault history on a remote they control
- User already has a remote Linux box (VPS / ECS) and wants to use it

## When NOT to use

- User just wants to read/edit local notes — use `obsidian` (the client-side skill) instead
- User has no remote server — recommend Obsidian's official Sync, iCloud, or Syncthing between their own devices
- User wants HA / clustered CouchDB / multi-region — that's a different scale of work

## Two-layer architecture (the non-obvious part)

A common mistake is to pick ONE of {git, LiveSync} and call it done. They cover **different failure modes**:

| Layer | What it protects against | What it doesn't |
|---|---|---|
| **Git (bare remote)** | accidental delete, ransomware, "I edited this wrong 2 months ago", server crash | real-time multi-device sync — git push is minutes, not seconds |
| **LiveSync (CouchDB)** | real-time multi-device, "I edited on phone, want it on desktop now" | historical recovery — CouchDB stores deltas, not full snapshots |

You need both. Git for history, CouchDB for liveness.

## The 8-step deploy sequence

Run these in order. Each step is independently testable. If step N fails, fix that step before proceeding.

### Step 1 — SSH access to the server

You need an SSH key on the **client** (your local machine where Hermes runs), and the matching public key on the server's `~/.ssh/authorized_keys`.

**Critical: verify fingerprints match BEFORE debugging sshd_config.** See `springboot-vue3-admin-bootstrap` pitfall #25. sshd gives no hint about which key it rejected, so fingerprint mismatch is the #1 silent failure here.

```bash
# 1. Client — note your fingerprint
ssh-keygen -lf ~/.ssh/id_ed25519.pub

# 2. Server — make sure your pubkey is there with right perms
ssh root@<server-ip> 'cat ~/.ssh/authorized_keys; ls -la ~/.ssh/'

# 3. First connect
ssh root@<server-ip> 'echo OK; hostname; df -h /opt | tail -1; docker --version 2>&1; nginx -v 2>&1'
```

You should see OK, a hostname, free disk, and Docker + nginx versions. Debian 12 / Ubuntu 22+ with Docker 20+ and nginx 1.18+ is the verified stack.

### Step 2 — Bare git remote

```bash
ssh root@<server-ip> 'mkdir -p /opt/<vault-name>.git && git init --bare /opt/<vault-name>.git && \
  git -C /opt/<vault-name>.git config receive.denyCurrentBranch ignore && \
  echo OK_bare_git'
```

Then on the client, init a working tree, write a `.gitignore` (see `references/gitignore-template.md`), commit + push.

### Step 3 — CouchDB data directory + admin/local.ini (NOT a docker-compose yet)

CouchDB 3.x in Docker runs as UID 5984 inside the container. Two pitfalls:

- **Bind-mounted ini must be readable by UID 5984** — if you `chmod 600` it as root on the host, CouchDB fails with `grep: /opt/couchdb/etc/local.d/local.ini: Permission denied` and goes into a restart loop. **Fix**: `chown 5984:5984 <ini-file>; chmod 644`.
- **Do NOT put `COUCHDB_USER`/`COUCHDB_PASSWORD` env vars alongside a mounted local.ini** — they conflict.

Generate two random passwords:

```bash
ADMIN_PASS=$(openssl rand -hex 16)
USER_PASS=$(openssl rand -hex 16)
echo $ADMIN_PASS > ~/.config/couchdb_admin_pass
echo $USER_PASS > ~/.config/couchdb_user_pass
chmod 600 ~/.config/couchdb_*
```

Build `local.ini` (template in `references/couchdb-local.ini`). Key sections: `[chttpd]` bind to 127.0.0.1, `[chttpd_auth] require_valid_user = true`, `[admins]` and `[<username>]` sections.

### Step 4 — Self-signed TLS cert (10 years is fine)

```bash
ssh root@<server-ip> "mkdir -p /opt/couchdb/certs && \
  openssl req -x509 -nodes -newkey rsa:2048 \
    -keyout /opt/couchdb/certs/privkey.pem \
    -out /opt/couchdb/certs/fullchain.pem \
    -days 3650 \
    -subj '/CN=<server-ip>/O=<vault-name>/C=CN' \
    -addext 'subjectAltName=IP:<server-ip>,DNS:localhost'"
```

10-year cert is fine for self-hosted — you'll just hit "Not Secure" warnings in browsers/clients. Click through.

### Step 5 — CouchDB container (host network, not bridge)

**Use `--network host`, not port mapping.** Bridge mode via docker-proxy caused `Connection reset by peer` even though the container's internal curl worked. Host network bypasses docker-proxy and lets nginx talk to 127.0.0.1:5984 directly.

```bash
ssh root@<server-ip> "docker run -d \
  --name couchdb \
  --restart unless-stopped \
  --network host \
  -v /opt/couchdb/data:/opt/couchdb/data \
  -v /opt/couchdb/etc/local.ini:/opt/couchdb/etc/local.d/local.ini:ro \
  apache/couchdb:3.4"
```

Wait ~15s for startup, then verify:

```bash
ssh root@<server-ip> 'docker logs couchdb --tail 5; echo ==='
ssh root@<server-ip> 'curl -s --max-time 5 http://127.0.0.1:5984/_up'
# expect: {"status":"ok","seeds":{}}
```

If `/_up` returns empty/connection-refused, see `references/couchdb-troubleshooting.md` step 5.

### Step 6 — Provision the per-user database + register the user

CouchDB 3.x **does NOT auto-create `_users` records** — you must PUT them explicitly, otherwise the user can't authenticate.

```bash
# 1. Create the vault database (use admin)
ssh root@<server-ip> "curl -s -X PUT -u admin:$ADMIN_PASS \
  http://127.0.0.1:5984/<vault-name>"

# 2. Register the user record in _users (use admin)
ssh root@<server-ip> "curl -s -X PUT -u admin:$ADMIN_PASS \
  http://127.0.0.1:5984/_users/org.couchdb.user:<username> \
  -H 'Content-Type: application/json' \
  -d '{\"name\":\"<username>\",\"password\":\"<user_pass>\",\"roles\":[],\"type\":\"user\"}'"
```

The vault DB and user record both need to exist for LiveSync to work.

### Step 7 — nginx reverse proxy with WSS upgrade

LiveSync uses WebSockets. nginx must:
- terminate TLS (handles self-signed cert warnings)
- reverse-proxy HTTP and WSS to `127.0.0.1:5984`
- hold the connection open for hours (LiveSync keeps WS alive)

Template at `references/nginx-couchdb.conf`. **Pick a non-conflicting port** — `8443` is safe (8080/80 often taken by other services). Verify `nginx -t` then `kill -HUP <real-master-pid>` (see `springboot-vue3-admin-bootstrap` pitfall #26 for nginx-master-PID issues).

```bash
# Verify from the SERVER itself (bypasses any firewall)
ssh root@<server-ip> 'curl -sk https://127.0.0.1:8443/_up'
# expect: {"status":"ok","seeds":{}}

# Verify from the CLIENT (your laptop)
curl -sk https://<server-ip>:8443/_up
# expect: {"status":"ok","seeds":{}}
```

If both pass, nginx → CouchDB works end-to-end. If the server-side test passes but client-side fails, **firewall / cloud security group** is blocking port 8443. Configure it in your cloud console.

### Step 8 — Client setup (Obsidian desktop + mobile)

Template at `references/obsidian-client-setup.md`. Key facts:

- Install **Self-hosted LiveSync** community plugin (NOT "Remotely Save" — different plugin)
- URI: `https://<server-ip>:8443/`
- Username: the one you PUT into `_users`
- Password: from `~/.config/couchdb_user_pass` (or wherever you saved it)
- **Passphrase**: you SET this in the client. It's end-to-end encryption. **There is no recovery** — losing it means losing the vault. Use a password manager.
- Database name: matches the DB you PUT in step 6

For mobile: same plugin, same URI/creds, same passphrase.

## Pitfalls (READ FIRST)

### 1. SSH key fingerprint mismatch (most common silent failure)

See `springboot-vue3-admin-bootstrap` pitfall #25. **Verify `ssh-keygen -lf` matches on both sides BEFORE debugging sshd.**

### 2. nginx master PID confusion

If nginx is running outside systemd (typical after `nginx 2>&1` from a debug session), `systemctl reload nginx` fails with "not active", and `nginx -s reload` fails with `/run/nginx.pid: No such file or directory`. Use `kill -HUP <master-pid>` directly on the oldest `nginx: master process`.

**Deeper failure mode**: if the port still doesn't answer after reload — or `ss` shows "nginx" listening but curl gets refused — there may be a SECOND nginx master on the host (e.g. alist's bundled nginx from /opt/alist, workers run as `message+`) and/or the reload rolled back because a `listen` collided with docker-proxy (e.g. `-p 127.0.0.1:5244:5244`). Full diagnostic path: `nginx-reverse-proxy-ops` skill.

### 3. CouchDB container goes into restart loop with "Permission denied"

You bind-mounted `local.ini` from the host but it has 600 perms owned by root. CouchDB runs as UID 5984. **Fix**: `chown 5984:5984 /opt/couchdb/etc/local.ini; chmod 644`.

### 4. CouchDB returns "Connection reset by peer" even though container curl works

docker-proxy (the bridge-mode TCP forwarder) sometimes silently fails. Use `--network host` to bypass it — CouchDB binds host 127.0.0.1:5984 directly.

### 5. nginx → CouchDB returns 502 Bad Gateway

- Check `ss -tlnp | grep ':5984'` — CouchDB not listening? → container restart loop (pitfall 3)
- Check `nginx -t` — config syntax error? → see `nginx error.log`
- Check nginx is the real master: `ps aux | grep '[n]ginx: master'` (pitfall 2)

### 6. LiveSync client says "401 Unauthorized"

- Username/password mismatch → re-check `~/.config/couchdb_user_pass`
- User not registered → see step step 6 (`PUT _users/org.couchdb.user:<name>`)
- DB doesn't exist → see step 6 (`PUT /<vault-name>`)

### 7. Obsidian plugin "Self-hosted LiveSync" won't auto-detect URI

You need to enable HTTPS in the URI (`https://...`, not `http://...`) — self-signed cert is fine, the plugin has a "Accept self-signed certs" toggle.

### 8. CouchDB N=3 replication error on first start

You'll see in logs: `Request to create N=3 DB but only 1 node(s)`. **Harmless** — CouchDB defaults to expecting a 3-node cluster but you have 1. The first start creates `_replicator` and `_users` with N=1 instead; this is what you want.

### 9. Don't use the public domain's TLS for the public IP — cert mismatch

If the server has a Let's Encrypt cert for `notes.yourdomain.com` but you're connecting via `https://123.45.67.89:8443/`, the cert CN is the domain not the IP. Either:
- Use self-signed (CN=<ip>, SAN IP:<ip>) and click through warnings
- Issue a separate cert for the IP (uncommon)
- Use a domain with a real A record and the real cert

For self-hosted single-user, self-signed is the simplest path.

### 10. Obsidian Git plugin + LiveSync running together = duplicate writes

Both layers will write your changes — Git via commit hook, LiveSync via CouchDB replication. They can race: Git sees a stale snapshot and commits an older version. **Solution**: configure Obsidian Git with `Auto-commit interval: 5+ minutes` (don't auto-commit on every save), and let LiveSync handle real-time sync. Git is just for the daily snapshot.

### 11. Domestic network + Chinese Obsidian: community plugin "Browse" tab is empty / fails to load

**Symptom** (very common for users in mainland China): "浏览" (Browse) button shows up after disabling 受限模式, but clicking it returns a blank page or hangs. The plugin marketplace CDN is unreachable from domestic ISPs.

**Fix — self-host the plugins as static files**, served by nginx on a second port (e.g. 8444). Don't depend on the CDN at all.

```bash
# 1. Make a directory tree mirror Obsidian's plugin layout
ssh root@<server-ip> 'mkdir -p /srv/obsidian-plugins/obsidian-git \
                                  /srv/obsidian-plugins/self-hosted-livesync'

# 2. Download plugin zips to the server (use github.com or ghfast mirror)
# Obsidian Git is now at Vinzent03/obsidian-git (renamed from Vinzent/obsidian-git)
GHFAST='https://ghfast.top/https://github.com'

# obsidian-git latest
ssh root@<server-ip> "
  curl -fSL -o /tmp/og.zip '${GHFAST}/Vinzent03/obsidian-git/releases/latest/download/obsidian-git.zip'
  unzip -q /tmp/og.zip -d /srv/obsidian-plugins/obsidian-git-tmp
  # zip extracts as obsidian-git/{main.js,manifest.json,styles.css}
  mv /srv/obsidian-plugins/obsidian-git-tmp/obsidian-git/* /srv/obsidian-plugins/obsidian-git/
  rm -rf /srv/obsidian-plugins/obsidian-git-tmp /tmp/og.zip"

# self-hosted-livesync ships as bare files (NOT zipped) — download individually
ssh root@<server-ip> "
  for f in main.js manifest.json styles.css; do
    curl -fSL -o /srv/obsidian-plugins/self-hosted-livesync/\$f \
      '${GHFAST}/vrtmrz/obsidian-livesync/releases/latest/download/'\$f
  done"

# 3. Generate a separate self-signed cert for the plugins port
ssh root@<server-ip> "
  openssl req -x509 -nodes -newkey rsa:2048 \
    -keyout /opt/couchdb/certs/privkey-plugins.pem \
    -out    /opt/couchdb/certs/fullchain-plugins.pem \
    -days 3650 \
    -subj '/CN=<server-ip>/O=<vault-name>-plugins/C=CN' \
    -addext 'subjectAltName=IP:<server-ip>,DNS:localhost'"

# 4. Add a second nginx site on port 8444 serving /srv/obsidian-plugins
cat > /etc/nginx/sites-available/plugins <<'NGINX'
server {
    listen 8444 ssl;
    server_name _;
    ssl_certificate     /opt/couchdb/certs/fullchain-plugins.pem;
    ssl_certificate_key /opt/couchdb/certs/privkey-plugins.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    root /srv/obsidian-plugins;
    autoindex on;
    types { application/javascript js; application/json json; text/css css; }
    location / { try_files $uri $uri/ =404; }
}
NGINX
ssh root@<server-ip> 'ln -sf /etc/nginx/sites-available/plugins /etc/nginx/sites-enabled/ \
  && kill -HUP $(pgrep -o "[n]ginx: master")'

# 5. Verify
curl -sk https://<server-ip>:8444/                 # expect: autoindex HTML listing
curl -sk https://<server-ip>:8444/obsidian-git/manifest.json   # expect: JSON manifest
```

**Client-side install** (no marketplace needed):

```bash
# On the user's machine — pulls the 3 plugin files directly into the vault
cd ~/Documents/<vault>/.obsidian/plugins
mkdir -p obsidian-git          && cd obsidian-git
curl -kO https://<server-ip>:8444/obsidian-git/main.js \
     -kO https://<server-ip>:8444/obsidian-git/manifest.json \
     -kO https://<server-ip>:8444/obsidian-git/styles.css
cd .. && mkdir -p self-hosted-livesync && cd self-hosted-livesync
curl -kO https://<server-ip>:8444/self-hosted-livesync/main.js \
     -kO https://<server-ip>:8444/self-hosted-livesync/manifest.json \
     -kO https://<server-ip>:8444/self-hosted-livesync/styles.css
# Restart Obsidian → 第三方插件 → enable both plugins
```

`-k` skips the self-signed cert check (only used during this one-time install). In the Obsidian UI you can also click through the `NET::ERR_CERT_AUTHORITY_INVALID` warning.

### 12. Chinese Obsidian UI: English-only setup instructions don't match

Settings panel translations in 中文版:

| English UI | 中文 UI |
|---|---|
| Settings | 设置 |
| Community plugins | 第三方插件 |
| Browse | 浏览 |
| Install | 安装 |
| Enable | 启用 |
| Restricted mode is on | 受限模式已启用 |
| Turn off restricted mode | 关闭受限模式 |
| Installed plugins | (no separate tab — visible under 第三方插件) |

**Critical first step in 中文版**: ⚙️ 设置 → 第三方插件 → click "关闭受限模式" before anything else. Until restricted mode is off, no community plugins are visible at all — even ones already installed locally. This catches Chinese users who try to skip straight to "Browse".

## Verification recipe

After deploy, run all of these from the CLIENT:

```bash
# 1. Bare git reachable
git ls-remote ssh://root@<server-ip>/opt/<vault-name>.git
# expect: refs/heads/master  refs/heads/main

# 2. CouchDB via nginx reachable from internet
curl -sk https://<server-ip>:8443/_up
# expect: {"status":"ok","seeds":{}}

# 3. CouchDB auth works
curl -sk -u <user>:<pass> https://<server-ip>:8443/<vault-name>
# expect: {"db_name":"<vault-name>","doc_count":0,...}

# 4. nginx access log shows your client IP
ssh root@<server-ip> 'tail -5 /var/log/nginx/access.log'
# expect: GET /_up HTTP/1.1 200 ... <your-ip>

# 5. CouchDB process is healthy (not restart-looping)
ssh root@<server-ip> 'docker ps --format "{{.Names}} {{.Status}}" | grep couchdb'
# expect: couchdb Up <N> minutes/hours (not "Restarting")
```

If all 5 pass, the stack is healthy. Open Obsidian, install plugins, connect, create a test note, wait 5s, check it appears on mobile.

## Reference files

- `references/gitignore-template.md` — Obsidian `.gitignore` (what to exclude vs. include from version control)
- `references/couchdb-local.ini` — annotated local.ini for single-user self-host
- `references/nginx-couchdb.conf` — nginx site config with WSS upgrade, TLS, and reverse-proxy
- `references/couchdb-troubleshooting.md` — step-by-step fixes for the 6 most common failure chains
- `references/obsidian-client-setup.md` — full client-side setup walkthrough (desktop + mobile), including passphrase setup and security warnings
- `references/security-checklist.md` — minimum hardening for an internet-exposed CouchDB (firewall rules, rate limits, fail2ban, backup cron)