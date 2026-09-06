# Local MariaDB + Redis fallback (when Docker image pulls stall)

Situation: Docker Hub unreachable AND configured mirrors (xuanyuan.me, 1ms.run, daocloud) also stall at ~0 MB/min. Debian/Ubuntu servers commonly already have `mariadb-server` + `redis-server` installed (Debian 12 ships MariaDB 10.11 + Redis 7) but stopped. Using them beats fighting a multi-GB image pull.

## Detection

```bash
which mysqld mariadbd redis-server        # if present → installed, likely just stopped
systemctl is-active mariadb redis-server   # both 'inactive' = stopped
docker pull ... 2>&1                       # stalls at "Pulling fs layer" forever
# confirm stall: docker data dir flat over 20s
S1=$(du -sm /var/lib/containerd/io.containerd.content.v1.content 2>/dev/null | cut -f1); sleep 20; S2=$(...); # Δ≈0 = stalled
```

Note: newer dockerd stores image content under `/var/lib/containerd/io.containerd.content.v1.content` (containerd image store), not `/var/lib/docker` — monitor the right dir.

## Startup + auth

```bash
systemctl start mariadb redis-server
ss -tlnp | grep -E ":3306|:6379"
```

MariaDB root uses `unix_socket` auth by default → connect WITHOUT password as root:

```bash
mysql -uroot -e "ALTER USER 'root'@'localhost' IDENTIFIED BY '<pwd>';"
mysql -uroot -p<pwd> -e "SELECT VERSION();"   # verify
```

After the ALTER, passwordless socket login stops working for root — that's expected.

## DB creation + import

RuoYi init SQL usually has NO `CREATE DATABASE` / `USE` — create first:

```bash
mysql -uroot -p<pwd> -e "CREATE DATABASE IF NOT EXISTS <db> DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
mysql -uroot -p<pwd> <db> < sql/jonlink_init.sql
mysql -uroot -p<pwd> <db> < sql/quartz.sql
# verify table count
mysql -uroot -p<pwd> -N -e "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='<db>';"
```

## Compatibility checks before choosing this path

```bash
grep -icE 'utf8mb4_0900|check constraint|functional index' init.sql   # expect 0
grep -c "create table" init.sql                                       # lowercase 'create table' — count with -i
```
- A column NAMED `json_result varchar(2000)` is fine — that's a varchar, not JSON type.
- MariaDB 10.11 accepts RuoYi's `engine=innodb`, `comment = '...'`, utf8mb4 — no MySQL-8-only syntax observed.
- Redis (Debian) binds 127.0.0.1, no `requirepass` → application.yml redis `password:` stays empty; backend `host: localhost` works as-is.

## After backend is up

- Verify login: `curl -s -X POST http://127.0.0.1:8080/login -H 'Content-Type: application/json' -d '{"username":"admin","password":"admin123"}'` → expect `{"code":200,"token":"..."}` (after captcha disabled + Redis DEL, see SKILL pitfall 8).
- The 启动成功 banner in logs (`先知·智源启动成功`) confirms full wiring.

## Cleanup

Leftover half-pulled docker images: `docker system prune -a` (or just leave them; they're partial).
