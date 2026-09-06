# ECS media stack: xiaoya (小雅) + OpenList — verified 2026-08-15

Host: 火山云 ECS 115.190.215.93, Debian 12, Docker 29.7.0, host nginx 1.22.1.

## Port map (current)
| Port | Owner | Notes |
|---|---|---|
| 5678 | xiaoya web (小雅) | **User decision: served by xiaoya CONTAINER's own nginx, NOT host nginx proxy** (host-nginx merge attempt rolled back) |
| 5244 | container-internal alist admin | published `127.0.0.1:5244:5244` → docker-proxy holds loopback only |
| 2345/2346/2347 | xiaoya 115 / misc | published 0.0.0.0 |
| 5245 | onelist container | 172.17.0.2 |
| 5246 | openlist (systemd) | /opt/openlist, http_port=5246 (moved from 5244: collided with onelist's 5245, later xiaoya alist) |
| 80/8443/8444 | host nginx | JonLink / CouchDB / plugin repo — must stay 200 after any nginx surgery |

## Containers / services
- **xiaoya**: image `xiaoyaliu/alist:patched` — **PATCHED. Do NOT rebuild with official ddsrem update script**: it pulls official `latest` and recreates the container, wiping the patch and returning to the updateall hang. Restore path: `/opt/backups/restore-xiaoya.sh` (loads `docker save` image backup `/opt/backups/xiaoya-patched-20260815.tar.gz`, rm old, re-run, wait 45s, verify).
  Exact run command (also inside restore script):
  `docker run -d --name xiaoya --restart always --entrypoint /entrypoint.sh -p 2345:2345 -p 2346:2346 -p 2347:2347 -p 127.0.0.1:5244:5244 -v /etc/xiaoya:/data -v /etc/xiaoya/data:/www/data xiaoyaliu/alist:patched /opt/alist/alist server --no-prefix`
- **openlist**: systemd service `openlist.service`; binary `/opt/openlist/openlist`; config `/opt/openlist/data/config.json` (http_port 5246; keep `.bak.*` copies when editing).
- **alist's bundled host nginx**: master started from `/opt/alist` cwd reading the SAME `/etc/nginx` config, workers run as `message+` (host nginx workers are `www-data`). It grabs contested ports (5678/5244) — this is the "second nginx master". Harmless when not running; `kill <pid>` if it steals ports.
- xiaoya-proxy / xiaoya-115cleaner / xiaoyakeeper (ddsderek images): leave alone.

## updateall hang root cause (why official updates break)
entrypoint `/updateall` runs `mv config.json` (moves the TEMPLATE containing `ALIST_TOKEN_EXPIRE_TIME` / `PAGESIZE` placeholders), then curls `https://xiaoyahelper.zngle.cf/initsoutv.sh` — **unreachable from this ECS** → hangs BEFORE the sed substitution lines → alist FATA "load config error".
Patch (applied in patched image): `timeout 10` on the curl + run the placeholder substitutions immediately after the `mv`, so config is valid even if the download never happens. Values: `ALIST_TOKEN_EXPIRE_TIME`=4800 (or `/data/alist_token_expire_time.txt`), `PAGESIZE`=1000 (or `/data/115_page_size.txt`).

## User's chosen architecture (2026-08-15)
- "xiaoya本身带nginx,你只要把证书加上" — xiaoya serves 5678 via its OWN container nginx; host nginx must NOT proxy it. Rollback performed: `rm /etc/nginx/sites-enabled/xiaoya-openlist`, reload host nginx, verify 80/8443/8444 still 200.
- **Cert injection plan** (pending user's own xiaoya re-update): copy self-signed certs `/opt/couchdb/certs/fullchain.pem` + `privkey.pem` into `/etc/xiaoya/` (= container `/data`, survives recreation), edit container nginx to `listen 443 ssl; ssl_certificate /data/fullchain.pem; ssl_certificate_key /data/privkey.pem;`, and map the published port to 443 if HTTPS is the goal.
- OpenList external 5244: re-arrange AFTER xiaoya update (depends whether the official update publishes 5244; if it does, host nginx can single-proxy openlist on another free port).

## Verification after any change
```bash
curl -sI http://127.0.0.1:5678/     # xiaoya (container nginx/alist)
curl -sI http://127.0.0.1:5246/     # openlist internal
curl -sI http://127.0.0.1:80/       # JonLink
curl -skI https://127.0.0.1:8443/   # CouchDB
curl -skI https://127.0.0.1:8444/   # plugins repo
```
