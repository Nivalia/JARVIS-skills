# CouchDB troubleshooting — fix the 6 most common failure chains

Use this AFTER running `docker logs couchdb --tail 30` to read the actual error. Match the symptom to the fix below.

## Chain 1: Container restart loop, logs say `Permission denied`

```
grep: /opt/couchdb/etc/local.d/local.ini: Permission denied
ERROR: CouchDB 3.0+ will no longer run in "Admin Party" mode...
```

**Cause**: bind-mounted local.ini has 600 perms owned by root; CouchDB runs as UID 5984 inside the container.

**Fix** (on the host):
```bash
ssh root@<server-ip> 'chown 5984:5984 /opt/couchdb/etc/local.ini && chmod 644 /opt/couchdb/etc/local.ini'
docker restart couchdb
sleep 10
docker logs couchdb --tail 5    # should see "Apache CouchDB has started"
```

## Chain 2: Container running, `curl 127.0.0.1:5984/_up` returns empty / `Connection reset by peer`

**Cause**: docker-proxy (the bridge-mode TCP forwarder) is silently failing. Host 5984 listener exists but doesn't forward properly.

**Diagnosis**:
```bash
ssh root@<server-ip> 'ss -tlnp | grep ":5984"'
# If it shows "docker-proxy" pid → docker-proxy issue
# If it shows "beam.smp" pid → CouchDB is listening natively (host network, OK)

ssh root@<server-ip> 'docker exec couchdb curl -s http://127.0.0.1:5984/_up'
# If this returns {"status":"ok"} but the host curl doesn't → docker-proxy issue
```

**Fix**: recreate the container with `--network host` (no port mapping):
```bash
ssh root@<server-ip> "docker rm -f couchdb
docker run -d \
  --name couchdb \
  --restart unless-stopped \
  --network host \
  -v /opt/couchdb/data:/opt/couchdb/data \
  -v /opt/couchdb/etc/local.ini:/opt/couchdb/etc/local.d/local.ini:ro \
  apache/couchdb:3.4"
```

## Chain 3: nginx → CouchDB returns 502 Bad Gateway

```bash
# Check the chain end-to-end:
ssh root@<server-ip> 'curl -s --max-time 5 http://127.0.0.1:5984/_up'
# OK → CouchDB alive
# empty/refused → fix CouchDB first (chain 1 or 2)

ssh root@<server-ip] 'curl -sk --max-time 5 https://127.0.0.1:8443/_up'
# 502 → nginx can't reach upstream
# OK → nginx → CouchDB works

# If 502 specifically:
ssh root@<server-ip] 'tail -10 /var/log/nginx/error.log'
# Look for "connect() failed (111: Connection refused)" — means CouchDB down
# Or "no live upstreams" — means upstream block misconfigured
```

**Common nginx mistakes**:
- Forgot `proxy_set_header Upgrade $http_upgrade;` and `Connection "upgrade";` — LiveSync needs WS upgrade
- Used `proxy_pass http://127.0.0.1:5984;` but the upstream block says `server 127.0.0.1:5984` — match them
- nginx is listening on :8443 but firewalld/security group blocks it from public — verify with public IP curl

**Verify nginx config**:
```bash
ssh root@<server-ip] 'nginx -t'                       # syntax check
ssh root@<server-ip] 'ps aux | grep "[n]ginx: master"' # find real master pid
ssh root@<server-ip] "kill -HUP <master-pid>"          # reload without restart
```

## Chain 4: LiveSync client says "401 Unauthorized"

```bash
# 1. Confirm creds match the local.ini
ssh root@<server-ip] 'ssh-keygen -lf /opt/couchdb/etc/local.ini'  # N/A — but check passwords match what you saved
cat ~/.config/couchdb_user_pass

# 2. Confirm the user is registered in _users
ssh root@<server-ip] "curl -s -u admin:<ADMIN_PASS> \
  http://127.0.0.1:5984/_users/org.couchdb.user:<USERNAME>"
# expect: {"_id":"org.couchdb.user:<USERNAME>","_rev":"...",...}
# 404 → user NOT registered → PUT it (see step 6 of main SKILL.md)

# 3. Confirm the database exists
ssh root@<server-ip] "curl -s -u admin:<ADMIN_PASS> \
  http://127.0.0.1:5984/_all_dbs"
# should include "<vault-name>"
```

## Chain 5: LiveSync connects but says "Database name conflict" / "DB doesn't exist"

User authenticated successfully but the DB they want isn't in `_all_dbs`. Fix:

```bash
ssh root@<server-ip] "curl -s -X PUT -u admin:<ADMIN_PASS> \
  http://127.0.0.1:5984/<vault-name>"
# expect: {"ok":true}
```

Then in Obsidian plugin settings, the DB dropdown will list the new DB.

## Chain 6: nginx listens on :8443 from server-side curl, but public curl fails

**Server-side** (works):
```bash
ssh root@<server-ip] 'curl -sk https://127.0.0.1:8443/_up'
# {"status":"ok","seeds":{}}
```

**Public-side** (fails):
```bash
curl -sk https://<server-ip>:8443/_up
# curl: (7) Failed to connect to <server-ip> port 8443: Connection timed out
```

**Cause**: cloud security group / OS firewall blocks port 8443 from public IPs. nginx is correctly listening but no traffic reaches it.

**Fix** (Aliyun ECS example):
- Cloud console → ECS → Security Groups → Inbound rules → Add: `TCP:8443, 0.0.0.0/0` (or restrict to your home/work IP)

**Fix** (ufw on host):
```bash
ssh root@<server-ip] 'ufw allow 8443/tcp && ufw reload'
# or for iptables:
ssh root@<server-ip] 'iptables -A INPUT -p tcp --dport 8443 -j ACCEPT'
```

**Verify**:
```bash
ssh root@<server-ip] 'iptables -L INPUT -n | grep 8443'   # confirm rule present
curl -sk https://<server-ip>:8443/_up                    # should now return ok
```

## Bonus: docker pull hangs (China mirror config)

If `docker pull apache/couchdb:3.4` stalls at 0 MB/min, configure mirror in `/etc/docker/daemon.json`:

```json
{
  "registry-mirrors": [
    "https://docker.xuanyuan.me",
    "https://docker.1ms.run",
    "https://docker.m.daocloud.io"
  ]
}
```

Then `systemctl restart docker` and re-pull.

If mirrors also fail, see `springboot-vue3-admin-bootstrap` pitfall #12 — fall back to a non-Docker deployment.