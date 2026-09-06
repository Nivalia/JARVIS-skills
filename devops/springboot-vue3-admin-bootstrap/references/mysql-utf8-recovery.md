# MySQL UTF-8 双重编码 Recovery (RuoYi/docker-entrypoint-initdb.d)

When MySQL Docker container runs `docker-entrypoint-initdb.d/*.sql`, it uses
**latin1** as the client connection charset by default. When the SQL file contains
UTF-8 bytes for Chinese characters, MySQL stores them as a latin1 → utf8mb4 hybrid,
producing double-encoded mojibake (乱码) like `ç³»ç»Ÿç®¡ç†` instead of `系统管理`.

This file explains how to **detect** and **repair** such corruption.

## How to detect

```bash
# Query with --default-character-set=latin1 — the latin1 connection
# will correctly read double-encoded bytes as their intended Chinese:
mysql -h127.0.0.1 -P3306 -uroot -p<pwd> <db> \
  --default-character-set=latin1 \
  -e "SELECT menu_id, menu_name FROM sys_menu WHERE menu_id IN (1,2,100)"
```

If the result shows correct Chinese (`系统管理`, `系统监控`, `用户管理`),
your DB has double-encoded data. The **default utf8mb4 connection** will show mojibake.

The smoking-gun check: `HEX(menu_name)` starts with `C3` (utf-8 encoded `ç`):

```bash
mysql -h127.0.0.1 -P3306 -uroot -p<pwd> <db> \
  -e "SELECT menu_id, HEX(SUBSTRING(menu_name,1,1)) FROM sys_menu WHERE menu_id=1"
# C3  → confirmed double-encoded
# E7  → correct UTF-8 (system = 0xE7)
```

## How to repair — fast path (hardcode known strings)

For ~100 well-known menu names, roles, dicts, depts, posts — fastest to hardcode.
Run after `pip install pymysql`:

```python
#!/usr/bin/env python3
"""Repair jonlink DB double-encoded Chinese — fast hardcoded path."""
import pymysql

conn = pymysql.connect(host='127.0.0.1', port=3306, user='root',
                       password='<pwd>', database='jonlink', charset='utf8mb4')
cur = conn.cursor()

# (id, name, remark) triples — overwrite double-encoded rows with correct text
menu_fixes = [
    (1, '系统管理', '系统管理目录'),
    (2, '系统监控', '系统监控目录'),
    (100, '用户管理', '用户管理菜单'),
    (101, '角色管理', '角色管理菜单'),
    # ... ~100 rows total, see session transcript for full list
]
btn_fixes = [(1000, '用户查询'), (1001, '用户新增'), ...]   # F-type buttons

# Apply
for mid, name, remark in menu_fixes + [(m[0], m[1], '') for m in btn_fixes]:
    cur.execute("UPDATE sys_menu SET menu_name=%s, remark=%s WHERE menu_id=%s",
                (name, remark, mid))
conn.commit()

# Repeat for sys_role, sys_dict_type, sys_dict_data, sys_dept, sys_post, sys_user, sys_config
```

Trade-off: hardcoded but predictable. Recovers in one shot regardless of how deep
the double-encoding went.

## How to repair — generic decoder (when you don't know the strings)

Iterative decoding. Some rows are 2-tier, some are 3-tier (mixed because bytes
0x9F / 0x90 / 0x86 fall outside latin1 range), so the loop is required.

```python
#!/usr/bin/env python3
"""Repair jonlink DB double-encoded Chinese — generic decoder."""
import pymysql

# utf8mb4 connection, use_unicode=False so we get raw bytes
conn = pymysql.connect(host='127.0.0.1', port=3306, user='root',
                       password='<pwd>', database='jonlink',
                       charset='utf8mb4', use_unicode=False)
cur = conn.cursor()


def fix_bytes(b):
    """Iteratively unwrap N-tier double UTF-8 encoding. Returns raw correct UTF-8 bytes, or None on failure."""
    iterations = 0
    while iterations < 5:
        try:
            s = b.decode('utf-8')
        except UnicodeDecodeError:
            return None
        # Check whether s is all-latin1 (last tier reached)
        if all(ord(c) <= 0xFF for c in s):
            try:
                raw = bytes(ord(c) for c in s)
                correct_str = raw.decode('utf-8')
                return correct_str.encode('utf-8')
            except UnicodeDecodeError:
                # Not valid UTF-8 — try one more tier
                b = raw
                iterations += 1
                continue
        else:
            # s contains chars > 0xFF — encoding was applied extra times
            try:
                b = s.encode('latin-1')
                iterations += 1
            except UnicodeEncodeError:
                return None
    return None


def fix_table(tbl, id_col, col):
    cur.execute(f"SELECT {id_col}, {col} FROM {tbl}")
    fixed = 0
    for rid, raw in cur.fetchall():
        if not isinstance(raw, bytes) or raw[:1] not in (b'\xc2', b'\xc3', b'\xc4', b'\xc5'):
            continue
        new = fix_bytes(raw)
        if new is None or new == raw:
            continue
        cur.execute(f"UPDATE {tbl} SET {col}=%s WHERE {id_col}=%s", (new, rid))
        fixed += 1
    conn.commit()
    return fixed


tables = [
    ('sys_menu', 'menu_id', 'menu_name'),
    ('sys_role', 'role_id', 'role_name'),
    ('sys_dict_type', 'dict_id', 'dict_name'),
    ('sys_dict_data', 'dict_code', 'dict_label'),
    ('sys_user', 'user_id', 'nick_name'),
    ('sys_dept', 'dept_id', 'dept_name'),
    ('sys_post', 'post_id', 'post_name'),
    ('sys_config', 'config_id', 'config_name'),
]
for tbl, id_col, col in tables:
    n = fix_table(tbl, id_col, col)
    if n:
        print(f"  {tbl}.{col}: {n} rows fixed")
```

**Note**: this generic decoder worked only on a subset of rows in the original
session. The hardcoded path is more reliable for known text. Use both: try
generic first, then hardcode the remainder.

## How to prevent recurrence

**Wrap every init script** with a charset-setting SQL file at the top of
`docker-entrypoint-initdb.d/`. Filename must sort first:

```bash
ls /opt/jonlink/backend/sql/00-set-charset.sql
# /opt/jonlink/backend/sql/00-set-charset.sql
```

```sql
-- /opt/jonlink/backend/sql/00-set-charset.sql
SET NAMES utf8mb4;
SET CHARACTER_SET_CLIENT = utf8mb4;
SET CHARACTER_SET_RESULTS = utf8mb4;
SET CHARACTER_SET_CONNECTION = utf8mb4;
SET collation_connection = utf8mb4_unicode_ci;
```

In `docker-compose.yml`, mount the SQL directory:
```yaml
volumes:
  - /opt/jonlink/backend/sql:/docker-entrypoint-initdb.d:ro
```

If files in `sql/` are already prefixed with `01-`, `02-`, etc., put the wrapper
as `00-set-charset.sql` so it executes first alphabetically.

## Verify after repair

```bash
# Connect with utf8mb4 (default) — should now show correct Chinese:
mysql -h127.0.0.1 -P3306 -uroot -p<pwd> <db> \
  -e "SELECT menu_id, menu_name FROM sys_menu WHERE menu_id IN (1,2,100)"
# expect: 系统管理 / 系统监控 / 用户管理
```

Or via the running app's API:
```bash
TOKEN=$(curl -s -X POST http://127.0.0.1:8080/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"admin123"}' | jq -r .token)

curl -s http://127.0.0.1:8080/getRouters -H "Authorization: Bearer $TOKEN" \
  | jq '.data[].meta.title' | head -10
# expect: "产品管理" / "系统管理" / "用户管理" — NOT ç³»ç»Ÿç®¡ç†
```

## Underlying mechanism — for the curious

UTF-8 encodes codepoints with 1-4 bytes:
- ASCII (U+0000–U+007F): 1 byte (0x00–0x7F)
- Latin1 supplement (U+0080–U+07FF): 2 bytes (start 0xC2 or 0xC3)
- BMP (U+0800–U+FFFF): 3 bytes (start 0xE0–0xEF)
- Astral (U+10000+): 4 bytes (start 0xF0–0xF4)

When MySQL container runs init SQL with latin1 client charset:
1. Client sends bytes E7 B3 BB (UTF-8 of `系`) over the wire
2. Server's `character_set_client = latin1` reads these as 3 latin1 chars (each a different letter)
3. Server stores these 3 chars via `character_set_connection = utf8mb4`: encodes back to UTF-8 = C3 A7 C2 B3 C2 BB
4. Each retrieval decodes this triple-encoded string as UTF-8 → first two bytes C3 A7 → latin1 supplement U+00E7 = `ç`

The triple-encoding variant happens for characters whose UTF-8 bytes contain
0x9F, 0x90, or 0x86 — these are not in latin1 (which only goes up to 0xFF for
control chars), so MySQL's auto-conversion path adds another UTF-8 wrap.

This is why the same column can have a mix of 2-tier and 3-tier encoded rows.