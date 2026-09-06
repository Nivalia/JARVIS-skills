---
name: docker-mysql-utf8-init
description: Fix MySQL Docker garbled Chinese via 3-layer charset config.
---

# Docker MySQL UTF-8 Initialization Fix

## Symptom

Database stores Chinese (or other non-ASCII) characters as garbled bytes. When the data is returned via API, frontend shows mojibake like `ç³»ç»Ÿç®¡ç†` instead of `系统管理`. The same byte stream looks "correct Chinese" only when connected with `--default-character-set=latin1`.

## Root Cause (Three Layers)

Three problems compound:

1. **`mysqld` defaults `--character-set-client-handshake=TRUE`** — the client's charset wins over the server's. With `--character-set-server=utf8mb4` set correctly, `character_set_server=utf8mb4` looks fine — but `character_set_client`, `character_set_connection`, `character_set_results` all stay at `latin1` (the mysql CLI default).

2. **mysql CLI defaults to latin1** — when the MySQL Docker entrypoint script runs each `docker-entrypoint-initdb.d/*.sql` file via `mysql` CLI, the CLI connection is latin1.

3. **Latin1 cannot round-trip all bytes** — latin1 only covers U+0000–U+00FF. UTF-8 bytes outside this range (0x80–0x9F as raw bytes, e.g. part of `系统管理` containing `0x9F`, `0x90`, `0x86`) trigger an additional escape round-trip → **triple encoding** mixed with double encoding.

A character like `系统` (UTF-8: `E7 B3 BB E7 BB 9F`) becomes:
- `E7 B3 BB` → latin1 chars `ç³»` → UTF-8 of that → `C3 A7 C2 B3 C2 BB`
- `E7 BB 9F` → latin1 chars `ç»\x9f` (0x9F is latin1 control char, not "normal") → escapes into a wider UTF-8 representation → `C3 A7 C2 BB C5 B8`

End result: stored bytes are triple-encoded in some places, double-encoded in others. Decoding back requires knowing the exact number of encodings.

## Diagnosis (run before fixing)

```sql
-- 1. Check current character set variables
SHOW VARIABLES WHERE Variable_name IN (
  'character_set_client',
  'character_set_connection',
  'character_set_results',
  'character_set_server',
  'character_set_database'
);
-- Expectation when broken: client/connection/results = latin1, server/database = utf8mb4

-- 2. Detect double-encoded data
-- If first byte of a UTF-8 string is C2 or C3, the bytes are double-encoded
SELECT
  'sys_menu' AS tbl,
  COUNT(*) AS total,
  SUM(CASE WHEN HEX(SUBSTRING(menu_name, 1, 1)) IN ('C3', 'C2')
           THEN 1 ELSE 0 END) AS double_encoded
FROM sys_menu;
-- When broken: double_encoded > 0
```

## Fix Recipe (apply all three layers)

### Layer 1 — Override `my.cnf` (mount custom config)

Create `deploy/mysql-conf/my-charset.cnf`:

```ini
[mysqld]
character-set-server = utf8mb4
collation-server = utf8mb4_unicode_ci
init-connect = 'SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci'

[client]
default-character-set = utf8mb4

[mysql]
default-character-set = utf8mb4
```

In `docker-compose.yml`:

```yaml
volumes:
  - ./mysql-conf/my-charset.cnf:/etc/mysql/conf.d/my-charset.cnf:ro
```

### Layer 2 — Skip the client charset handshake

Add to the mysql container `command:`:

```yaml
command:
  - --character-set-server=utf8mb4
  - --collation-server=utf8mb4_unicode_ci
  - --skip-character-set-client-handshake  # forces server charset, not client
  - --default-authentication-plugin=mysql_native_password
```

Without this flag, even with the cnf override, the `mysql` CLI inside the container will overwrite `character_set_client` back to latin1 because the handshake respects the client's preference.

### Layer 3 — Wrapper SQL file (belt + suspenders)

Create `sql/00-set-charset.sql` (must run first):

```sql
SET NAMES utf8mb4;
SET CHARACTER_SET_CLIENT = utf8mb4;
SET CHARACTER_SET_RESULTS = utf8mb4;
SET CHARACTER_SET_CONNECTION = utf8mb4;
SET collation_connection = utf8mb4_unicode_ci;
```

Mount it first in docker-compose.yml with explicit numeric prefix:

```yaml
volumes:
  - ./sql/00-set-charset.sql:/docker-entrypoint-initdb.d/00-set-charset.sql:ro
  - ./sql/jonlink_init.sql:/docker-entrypoint-initdb.d/10-jonlink_init.sql:ro
  # ... other SQL files with explicit 20-, 30-, etc. prefixes
```

### Bonus — Environment variables

In `docker-compose.yml`:

```yaml
environment:
  LANG: C.UTF-8
  LC_ALL: C.UTF-8
  MYSQL_INIT_COMMAND: "SET NAMES utf8mb4; SET CHARACTER_SET_CLIENT=utf8mb4;"
```

## Verification

After re-creating the container from scratch (`docker compose down -v` + remove data dir + `docker compose up -d`), confirm:

```bash
# 1. All client charsets should now be utf8mb4
docker exec jonlink-mysql mysql -uroot -pXXX -e "
  SHOW VARIABLES WHERE Variable_name LIKE 'character_set%';
"
# Expect: all = utf8mb4

# 2. No double-encoded rows
mysql -h127.0.0.1 -uroot -pXXX dbname -e "
  SELECT HEX(SUBSTRING(menu_name, 1, 1)) FROM sys_menu WHERE menu_id = 1;
"
# Expect: starts with E7 (correct UTF-8 of 系), NOT C3 (double-encoded)

# 3. Visually verify
mysql -h127.0.0.1 -uroot -pXXX dbname -e "
  SELECT menu_name FROM sys_menu WHERE menu_id IN (1, 100);
"
# Expect: 系统管理, 用户管理 — readable Chinese
```

## Pitfalls

- **The `--skip-character-set-client-handshake` flag is the actual fix.** Without it, the my.cnf `[client]` section's `default-character-set` is ignored because the mysql CLI negotiates a latin1 connection anyway. Symptom of forgetting this: `character_set_server=utf8mb4` but `character_set_client=latin1`, init SQL still double-encoded.

- **Don't rely on `SET NAMES` alone inside SQL files.** It works, but if the file is large or you forgot to put it first, late `INSERT` statements will still get encoded with whatever charset the connection had at that point. The cnf + flag combo is more robust.

- **Pre-existing double-encoded data is NOT recoverable by `CONVERT(col USING utf8)`** when there's mixed double + triple encoding (different bytes triggered different numbers of escape rounds). Plan to wipe and re-init, or restore from a backup made before the encoding went wrong.

- **Don't add Chinese strings to SQL files before the fix is applied** — they'll get double-encoded on first init, and you'll be chasing the bug forever. Init order matters.

- **MySQL 8.0 default `collation_server` is `utf8mb4_0900_ai_ci`** for new installs. If you specify `utf8mb4_unicode_ci` for backward compat with RuoYi-style apps, do so in BOTH the mysqld command and the cnf file.

## See Also

- `references/byte-level-trace.md` — exact byte-by-byte encoding chain with worked example
- `references/docker-compose-snippet.yml` — minimal complete compose file with all three layers
- `references/why-latin1-triggers-triple-encoding.md` — deeper Unicode explanation