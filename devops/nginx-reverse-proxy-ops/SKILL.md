---
name: nginx-reverse-proxy-ops
description: "Use when nginx reload fails or ports fight."
---

# nginx Reverse-Proxy Ops (multi-instance / Docker-heavy hosts)

Class: operating nginx on a Linux host that ALSO runs Docker containers and possibly multiple nginx builds. Covers the failure mode where "the config is fine but the port doesn't answer" — usually two nginx masters fighting or a reload that silently rolled back.

## When to use
- `curl http://127.0.0.1:<port>` → connection refused / empty, but `ss` shows something listening and `nginx -T` shows the server block
- `[emerg] bind() to 0.0.0.0:<port> failed (98: Address already in use)` in `/var/log/nginx/error.log`
- After adding/editing a server block, reload "worked" but the new port still doesn't respond
- Need to put a TLS cert on a service inside a container that has its own nginx
- User says "app X 自己带 nginx,你只要把证书加上" (drop the host-proxy plan, serve via the app's own nginx)

## Root-cause model (read first)
1. **A reload that hits ANY bind failure rolls back ENTIRELY.** `kill -HUP` (or `nginx -s reload`) loads the new config; if any `listen` can't bind, nginx keeps serving the OLD worker set — new server blocks never load. Error log shows `[emerg] ... still could not bind()`. **`nginx -t` / `nginx -T` only parse files; they CANNOT tell you what's actually loaded.**
2. **Docker-proxy counts as a port holder.** `docker run -p 127.0.0.1:5244:5244` puts docker-proxy on 127.0.0.1:5244 → an nginx `listen 0.0.0.0:5244` FAILS (0.0.0.0 covers 127.0.0.1). nftables shows the mechanism: `nft list ruleset` → `ip daddr 127.0.0.1 tcp dport 5244 dnat to 172.17.0.x:5244`.
3. **There may be MORE than one nginx master on the host** (e.g. an app's bundled nginx started from its own cwd, reading the SAME `/etc/nginx` config). It can grab contested ports, so `ss` shows "nginx" holding the port but requests get refused — it's the OTHER master with different workers (check worker user: www-data vs message+).
4. **`nginx -s stop/reload` needs `/run/nginx.pid`**; if that file is empty/missing (nginx started manually), use `kill <master-pid>` / `kill -HUP <master-pid>` directly.

## Diagnostic sequence (in this order)
```bash
# 1. Count masters and note worker users — TWO masters = port fight
ps aux | grep '[n]ginx: master'
#    master A: ... nginx: master process nginx            workers www-data
#    master B: ... nginx: master process /usr/sbin/nginx  workers message+  ← bundled app nginx

# 2. Which PID actually owns the port
ss -tlnp | grep -E ':<port>'

# 3. Reload-time errors (bind conflicts) — the smoking gun
tail -50 /var/log/nginx/error.log | grep -E 'emerg|bind'

# 4. Config file HAS the block (does NOT mean it loaded)
nginx -T 2>&1 | grep -A5 'listen <port>'

# 5. Free the port, then reload the real master
kill <competing-master-pid>          # -s stop needs the pid file which may be broken
kill -HUP <real-master-pid>
ss -tlnp | grep -E ':<port>'         # confirm the intended owner
curl -sI http://127.0.0.1:<port>/    # confirm it answers
```

## Fix patterns
- **Port held by a second nginx master** → kill it (or disable its config), reload the system master.
- **Port held by docker-proxy (127.0.0.1:PORT publish)** → nginx cannot `listen 0.0.0.0:PORT`; either drop the nginx server block and let the container own the port, or change the container publish and move nginx's listen elsewhere.
- **Adding TLS to a container's OWN nginx** → put certs on the container's persistent data volume (host dir mounted into the container, e.g. `/etc/xiaoya` → `/data`) so they survive container recreation; edit the container nginx config (`listen 443 ssl; ssl_certificate /data/fullchain.pem; ssl_certificate_key /data/privkey.pem;`); verify the published port maps to 443 if HTTPS is the goal.
- **User overrides a proxy plan mid-flight** ("X 自己带 nginx,你只要加证书") → cleanly roll back: remove the sites-enabled symlink, reload, verify REMAINING services still answer (80/8443/8444...), free the contested ports, then prep the new approach. Never leave half-applied server blocks.

## Pitfalls
- `nginx -t` / `nginx -T` pass ≠ config loaded. The loaded config is what workers serve after the last SUCCESSFUL reload.
- IPv6: `[::]:5244` may bind while `0.0.0.0:5244` fails (docker-proxy holds v4 loopback) — ss shows both lines; check each.
- Two masters can both read `/etc/nginx` — whichever starts LAST wins contested ports; killing the loser reveals the port was never served by the intended config.
- On the user's ECS, INPUT policy is ACCEPT (no ufw/iptables blocks) — "connection refused with a listener present" is almost always the second-master/bind-rollback issue, not a firewall.

## Reference files
- `references/xiaoya-openlist-stack.md` — ECS 小雅 (xiaoya) + OpenList: ports, containers, patched-image update flow, cert-injection plan (session-verified)
