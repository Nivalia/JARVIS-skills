---
name: springboot-vue3-admin-bootstrap
description: "Bootstrap RuoYi Spring Boot 3 + Vue3 admin from source — 45 numbered pitfalls including (Pitfall 40) @click handler no-parens → MouseEvent → silent TypeError trap, (Pitfall 41) DB column comment ≠ engine code convention, (Pitfall 42) silent Vue3 scoped-slot `<!---->` when financeDict helper is used without an import, (Pitfall 43) layout `watchEffect` on useWindowSize() causing mobile/desktop toggle loop + sidebar flicker, (Pitfall 44) MyBatis LEFT JOIN → 3 distinct SQL ambiguity errors, (Pitfall 45) sys_menu middle-parent component='Layout' → nested Layout records → 2 sidebars (see new sibling skill `sys-menu-component-parentview-trap`). Standing UI rule (no raw 0/1/2/3 in user-facing labels) and M0-M7 incremental business-module rollout pattern."
---

# Spring Boot + Vue3 Admin Bootstrap

Class: deploying + bootstrapping a multi-module Spring Boot 3 + Vue3 admin system (RuoYi-Vue3, RuoYi-Vue-Plus, eladmin, vue-vben-admin or similar) from source/backup to a working dev environment with MySQL + Redis in docker, CRUD APIs generated, and Vite frontend live.

## When to use

Trigger any of:
- "scaffold / build / bootstrap an admin system from source"
- "wire application.yml to docker MySQL/Redis"
- "generate CRUD for ~10-20 business tables" (often `jl_*`, `biz_*`, `sys_*` prefix)
- "RuoYi 部署 / 启动 / 跑起来"
- "multi-module Maven dependency version error"
- "Spring Boot Lookup method resolution failed / class not found at startup"
- "MyBatis mapper XML Table 'xxx' doesn't exist" (placeholder escape bug)
- "Vite dev server won't start, vite: not found"
- "docker-entrypoint-initdb.d not running my new SQL"
- "admin-web 5173 / 80 / 404 / 跨域"
- "menu names / dict labels showing as mojibake (ç³»ç»Ÿç®¡ç†) after fresh MySQL container"
- "RuoYi frontend renders garbled glyphs in Element Plus / icons"
- "RuoYi 4.x Table 'db.sys_notice_read' doesn't exist"
- "18 张表代码生成了但页面 404" / "generated code landed but menu pages 404" / "菜单点了 404"
- "1:1 仿站 / 扒某个保险后台的菜单和字段" (reverse-engineer a RuoYi-style SaaS via token + JS bundle)
- "batchGenCode / 批量生成代码 / generator zip 怎么用"
- "项目改名 / rebrand / 英文名 中文名" (RuoYi fork re-branding sweep — see `references/jonlink-rebranding.md`)
- "部署 / docker 拉不动镜像 / 卡在 Pulling fs layer" (fall back to local MariaDB/Redis — see `references/local-mariadb-fallback.md`)

Don't use for: production hardening (k8s, HTTPS, secrets, HA) — that's `production-readiness` territory. This skill gets the **dev environment** running and the **CRUD layer** complete.

## First rule: USE THE BUILT-IN CODE GENERATOR before hand-writing CRUD

RuoYi / RuoYi-Vue-Plus / eladmin / vue-vben-admin ALL ship a working code generator accessible from the admin UI menu **系统工具 → 代码生成** (path `/tool/gen`). Endpoint: `POST /tool/gen/importTable` (imports a real MySQL table into the generator), then `GET /tool/gen/download/{tableName}` returns a zip containing:

- `{Class}Controller.java` + `Service/Impl` + `Mapper` + `Domain` + XML
- `vue/api/<module>/<business>.js` (axios wrappers for list/get/add/update/del/export)
- `vue/views/<module>/<business>/index.vue` (RuoYi Element Plus CRUD page with query form + table + add/edit dialog + 5 buttons)
- `<business>Menu.sql` — INSERT statements for `sys_menu` + 5 button permissions (query/add/edit/remove/export). Idempotent: re-importing appends NEW menu rows via `@parentId := LAST_INSERT_ID()`

**Recipe for using the generator** (instead of hand-writing):

1. Confirm table exists in MySQL (or `CREATE TABLE` it first).
2. Login as admin → System Tools → Code Gen → **Import** the table (form: `tplWebType=element-plus`, `tplCategory=crud`).
3. On the edit page: set `packageName=com.<your>.<module>`, edit column display types (`query`/`list`/`edit` flags, dict types).
4. Click **Preview** to see what files will be generated. Click **Generate Code** → downloads `jonlink.zip`.
5. Unzip → copy `main/java/**` into your module's `src/main/java/`, copy `vue/**` into `admin-web/src/`.
6. Run the `<business>Menu.sql` against the DB to register the menu.
7. Rebuild backend + frontend, restart services.

**Default generator quirks** that bite you:

- Package name is hardcoded in `generator.yml` (`com.jonlink.system`). UI import form lets you override per-table — always set this before generate.
- Generator paths land in `/system/<business>` by default — for business modules, edit `vm/java/controller.java.vm` and `vm/sql/sql.vm` to point to `/<your>/<business>` and parent_id of your module's top-level menu.
- Generator `tplCategory=crud` outputs ONE list page; for tree/sub/master-detail use `tree` or `sub`. No support for non-Element UI targets (e.g. vant) — see references for H5 workaround.

**When NOT to use the generator** (hand-write instead):

- Need non-standard interaction (drag-drop forms, canvas editors, multi-tab wizards, dynamic schema-driven forms).
- Need strict field validation beyond what `@NotBlank`/`@Size` annotations give.
- Need nested master-detail forms (use `tplCategory=sub` for simple 1:N, hand-write for complex).
- Need H5/mobile (vant) — generator only outputs Element Plus admin UI.

The user's preference is **generator-first**. Hand-writing CRUD then asking the generator to "fix it" or "regenerate the same table" is a wasteful loop. Generate once, copy to module, tweak details by hand.

## Quick start (the 6-step sequence)

1. **Restore source** (tar -xzf → place under project root)
2. **Verify rename complete** if migrated (`grep -r 'old.pkg' src/` → must be 0)
3. **Bring up DB**: `docker compose up -d mysql redis` with `volumes: ./sql:/docker-entrypoint-initdb.d:ro`. **CRITICAL**: prepend a `00-set-charset.sql` wrapper (see pitfall 13) — MySQL container defaults to latin1 connection for init SQL, which corrupts every Chinese row.
4. **Patch application.yml**: MySQL URL → `jdbc:mysql://127.0.0.1:3306/<db>?allowPublicKeyRetrieval=true`; Redis host → `127.0.0.1`, password
5. **`mvn install -DskipTests` then `java -jar target/<app>.jar`** — do NOT use `spring-boot:run` for multi-module (see pitfalls)
6. **Frontend**: `npm install --include=dev` (NOT plain `npm install` — see pitfalls), then `npm run dev`. **Also delete the `css: { postcss: { plugins: [...] } }` charset-removal block** in `admin-web/vite.config.js` (see pitfall 14).

If any step fails, jump to the matching `references/<topic>.md` file.

## Pitfalls (READ THESE BEFORE CODING)

### 1. `mvn spring-boot:run` fails with "Lookup method resolution failed" in multi-module

`org.springframework.boot.devtools.restart.classholder.RestartClassLoader` cannot resolve classes from sibling modules that were added to the reactor after devtools started. Symptoms: `BeanCreationException: Error creating bean with name 'JlXxxController': Lookup method resolution failed` immediately after adding a new module's controller.

**Fix**: skip devtools run entirely for multi-module. Use:
```bash
mvn install -DskipTests
java -jar target/<module>-admin.jar
```

### 2. `application.yml` uses CRLF; the `patch` tool breaks it

Spring Boot config files in this codebase are CRLF (`\r\n`). The `patch` tool re-validates as LF-YAML and refuses to write. Symptoms: `mapping values are not allowed here` from yamllint.

**Fix**: use Python `execute_code` with binary read/write to preserve line endings:
```python
path = '/path/to/application.yml'
with open(path, 'rb') as f: data = f.read()
data = data.replace(b'host: localhost\r\n', b'host: 127.0.0.1\r\n')
with open(path, 'wb') as f: f.write(data)
```
Or use `sed -i` with CRLF-aware tools.

### 3. New module added to parent `<modules>` → child poms need `<dependencyManagement>`

When you add `jonlink-insure` to `<modules>`, any module that depends on it (e.g. `jonlink-admin`) gets `'dependencies.dependency.version' is missing` UNLESS the parent has:
```xml
<dependencyManagement>
  ...
  <dependency>
    <groupId>com.example</groupId>
    <artifactId>jonlink-insure</artifactId>
    <version>${project.version}</version>
  </dependency>
</dependencyManagement>
```

### 4. `docker-entrypoint-initdb.d/*.sql` only runs on FIRST container start

If the MySQL container was created before you added SQL files, **new files are silently ignored**. Two fixes:
- **Fresh start** (loses data): `docker compose down && rm -rf deploy/data/mysql && docker compose up -d`
- **Hot-apply** (keeps data): loop over files and `docker exec jonlink-mysql mysql -uroot -p<pwd> <db> < /path/to/file.sql`

### 5. MyBatis mapper XML generated with `#{name}` but real table is `jl_apply_record` (camelCase leak)

When generating XML via Python template substitution, if the table name placeholder consumed adjacent text (e.g. `__TABLE__` ate a suffix leaving `jl_<empty>`), the SQL ends up `insert into jl_applyRecord` instead of `insert into jl_apply_record`. The DB then returns `Table 'db.jl_applyRecord' doesn't exist`.

**Fix pattern**: use regex replace with explicit word boundaries:
```python
import re
for f in glob.glob('**/JlXxxMapper.xml'):
    new = re.sub(r'\bjl_([A-Z][a-z]+[A-Z]\w*)\b',
                 lambda m: 'jl_' + snake(m.group(1)), open(f).read())
    open(f, 'w').write(new)
```

### 6. `{{` and `}}` from Python template `.replace()` aren't auto-escaped

Java class bodies contain `{` and `}`. When generating Java code via Python, naive `.replace('__CLS__', cls)` doesn't double-brace. After writing, the Java source has `{{` `}}` which breaks javac with "illegal start of expression" / "class, interface, enum, or record expected".

**Fix**: post-process step to replace all `{{` → `{` and `}}` → `}` after generation, across all generated `.java` files:
```python
for f in glob.glob('**/*.java'):
    with open(f, 'rb') as fh: data = fh.read()
    data = data.replace(b'{{', b'{').replace(b'}}', b'}')
    with open(f, 'wb') as fh: fh.write(data)
```

### 7. Public controller returns 401 — need `@Anonymous`

RuoYi security blocks all unauthenticated requests by default. For public endpoints (H5, captcha, login, swagger), annotate the controller class:
```java
import com.jonlink.common.annotation.Anonymous;
@Anonymous
@RestController
@RequestMapping("/api/h5")
public class H5Controller { ... }
```
The framework's `PermitAllUrlProperties` scans both class-level and method-level `@Anonymous`.

### 8. RuoYi captcha toggle goes through Redis cache

`sys.account.captchaEnabled=false` in `sys_config` only takes effect after `redisCache.getCacheObject(...)` returns the new value. After `UPDATE sys_config`, also delete the cached key — the cache key is exactly `sys_config:sys.account.captchaEnabled`:

```bash
# docker Redis:
docker exec jonlink-redis redis-cli -a <pwd> DEL sys_config:sys.account.captchaEnabled
# local Redis (no auth):
redis-cli DEL sys_config:sys.account.captchaEnabled
```

`DEL` the single key is safer than `FLUSHDB` (which wipes every cached config — user will see default skin/register flags until keys re-populate). Verify login works after: `curl -s -X POST http://127.0.0.1:8080/login -H 'Content-Type: application/json' -d '{"username":"admin","password":"admin123"}'` should return a token, not `{"msg":"验证码已失效","code":500}`.

### 9. `npm install` skips devDependencies — frontend dev won't start

Symptoms: `vite: not found` despite `vite` being in `package.json` devDependencies. Some npm 8+ configs default to omitting devDeps in production-like contexts.

**Fix**: `npm install --include=dev` or explicit `npm install --include=dev vite@<version> sass-embedded@<version> unplugin-auto-import ...`

**Also bites yarn**: `NODE_ENV=production` set globally (e.g. by deploy tooling) makes BOTH npm and yarn silently skip devDependencies. Symptom is identical. Confirm with `echo $NODE_ENV` first; if it's `production`, prefix install with `NODE_ENV=development`:

```bash
NODE_ENV=development yarn install --check-files
```

After install, verify the binary exists: `ls node_modules/.bin/vite` — must be present, not just the package directory.

**npm ≥11 `allow-scripts` mechanism** (newer failure mode, 2025+): npm 11 defaults to BLOCKING package postinstall scripts unless approved (`npm approve-scripts` / `--allow-scripts`). Symptoms: `node_modules` exists and is populated, but `node_modules/vite` is **missing entirely** (or the package dir exists but `node_modules/.bin/vite` and `esbuild`'s binary are absent) — `vite: not found` on `npm run dev`, and `npm install` succeeds silently with a warning like `npm warn allow-scripts ... Run 'npm approve-scripts --allow-scripts-pending' to review`.

**Fix**: explicitly reinstall the failing package(s) by version — this re-runs the blocked postinstall and creates `.bin` links:
```bash
npm install vite@6.4.1 --no-audit --no-fund
# for Vue2 (vue-cli): 
npm install @vue/cli-service@4.4.6 --no-audit --no-fund
```
Verify: `ls node_modules/.bin/ | grep -E 'vite|vue-cli-service'` and `node node_modules/vite/bin/vite.js --version`. This applies to ALL packages with install scripts (esbuild, vue-demi, core-js, highlight.js).

### 10. Vite default port is 80, not 5173 (RuoYi admin-web)

`admin-web/vite.config.js` sets `server.port = 80` to avoid CORS with the backend (which serves admin-web). Needs root or `sudo setcap cap_net_bind_service=+ep $(which node)`. The auto-open `xdg-open ENOENT` error in dev logs is harmless in headless.

### 11. Default RuoYi MySQL URL is `localhost:3306` — needs `allowPublicKeyRetrieval=true` for MySQL 8

MySQL 8 defaults to `caching_sha2_password`. Without `allowPublicKeyRetrieval=true` in JDBC URL, you'll get `Public Key Retrieval is not allowed`. Use:
```
jdbc:mysql://127.0.0.1:3306/<db>?useUnicode=true&characterEncoding=utf8&serverTimezone=GMT%2B8&allowPublicKeyRetrieval=true
```

### 12. Docker Hub unreachable in China — configure registry mirrors

Default `registry-1.docker.io` times out. Add to `/etc/docker/daemon.json`:
```json
{
  "registry-mirrors": [
    "https://docker.xuanyuan.me",
    "https://docker.1ms.run",
    "https://docker.m.daocloud.io"
  ]
}
```
Then `docker pull docker.1ms.run/library/mysql:8.0` and `docker tag docker.1ms.run/library/mysql:8.0 mysql:8.0`.

**If mirrors also stall** (blob download ~0 MB/min, `du /var/lib/containerd/io.containerd.content.v1.content` flat across 20s while dockerd holds ESTAB connections to mirror IPs): **abandon Docker for the DB entirely — use locally-installed MariaDB + Redis** (Debian/Ubuntu servers commonly have `mariadb-server` + `redis-server` installed but stopped). RuoYi SQL is MariaDB-compatible (uses `engine=innodb`, plain `varchar/json` columns; MariaDB 10.11 accepts it). This is much faster than fighting the image pull:

```bash
# check what's already installed before pulling anything:
which mysqld mariadbd redis-server   # if present, they're installed but stopped
systemctl start mariadb redis-server
# set root password (MariaDB uses unix_socket auth for root by default — connect without password first):
mysql -uroot -e "ALTER USER 'root'@'localhost' IDENTIFIED BY '<pwd>';"
# then patch application-druid.yml password to match, create DB + import:
mysql -uroot -p<pwd> -e "CREATE DATABASE IF NOT EXISTS <db> DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
mysql -uroot -p<pwd> <db> < sql/init.sql
```

**Pitfalls of the MariaDB path**: (a) Debian's `mysql-server` package IS MariaDB — `mysqld --version` will say `10.11.18-MariaDB`, that's fine; (b) MariaDB root uses `unix_socket` plugin by default — connect as root with NO password (socket auth) to run the ALTER, then password auth works; (c) check the init SQL has no MySQL-8-only syntax first: `grep -icE 'utf8mb4_0900|functional index|check constraint' init.sql` should be 0 (a column NAMED `json_result` as varchar is fine, that's not JSON type); (d) init SQL often has NO `CREATE DATABASE`/`USE` statement — create the DB yourself before importing; (e) Redis in Debian binds `127.0.0.1` with no password — application.yml `password:` stays empty. See `references/local-mariadb-fallback.md`.

### 13. Chinese 乱码 — MySQL container's `docker-entrypoint-initdb.d/*.sql` runs with latin1 connection

**Symptom**: data is in DB, UTF-8 source SQL has Chinese like `'系统管理'`, but the live API returns `ç³»ç»Ÿç®¡ç†` for menu names. `HEX(menu_name)` is `C3A7C2B3...` (double-encoded). Affects every `name`/`title` field in `sys_menu`, `sys_role`, `sys_dict_type`, `sys_dict_data`, `sys_dept`, `sys_post`, `sys_config` — i.e. 100+ rows of 乱码 after a fresh container.

**Root cause**: MySQL Docker image defaults the `docker-entrypoint-initdb.d/*.sql` client connection to `latin1` (not utf8mb4). When the SQL file contains UTF-8 bytes for Chinese characters, MySQL stores them as latin1 → utf8mb4 hybrid = double-encoded mojibake. Same root cause as 双重 UTF-8 编码.

**Fix** (two parts, do BOTH):

**(a) Prevent future builds** — prepend a `00-set-charset.sql` wrapper file that runs FIRST in `docker-entrypoint-initdb.d/`:
```sql
SET NAMES utf8mb4;
SET CHARACTER_SET_CLIENT = utf8mb4;
SET CHARACTER_SET_RESULTS = utf8mb4;
SET CHARACTER_SET_CONNECTION = utf8mb4;
SET collation_connection = utf8mb4_unicode_ci;
```
Filename must sort before other SQL (alphabetical order: `00-` < `01-` < `jl_*`).

**(b) Recover existing data** — run a Python repair script with PyMySQL. Detect double-encoded rows via `byte_len / char_len >= 4` AND `first_byte in (0xC2, 0xC3, 0xC4, 0xC5)`. For each, decode bytes: `bytes.decode('utf-8')` → string with latin1 + extended chars → `bytes(ord(c) for c in s)` → original bytes → `.decode('utf-8')` = correct text. UPDATE with corrected UTF-8 bytes. **Note**: bytes < 25 chars often contain a mix of 2-tier and 3-tier encoding due to 0x9F/0x90/0x86 falling outside latin1 — the recovery loop may need 3+ iterations. For business-critical text (menu names, role names), the more reliable shortcut is: hardcode the correct Chinese name → `UPDATE sys_menu SET menu_name = '系统管理' WHERE menu_id = 1` over 100 rows via dict. See `references/mysql-utf8-recovery.md`.

**Detect on existing install**:
```bash
mysql -h127.0.0.1 -uroot -p<pwd> <db> --default-character-set=latin1 \
  -e "SELECT menu_id, menu_name FROM sys_menu WHERE menu_id IN (1,2,100)"
# expect: 系统管理 / 系统监控 / 用户管理
# if you see mojibake like ç³»ç»Ÿç®¡ç†, the DB has double-encoded rows
```

### 14. RuoYi-Vue3 ships a `charset-removal` postcss plugin → CSS 乱码

**Symptom**: Vite dev server starts fine, login page HTML loads, but **Element Plus / icon fonts render as garbled characters** (boxes, `?`, broken glyphs). Console shows no errors. `curl http://127.0.0.1/` returns correct HTML but the rendered UI is unreadable.

**Root cause**: `admin-web/vite.config.js` contains a postcss plugin block that strips every `@charset "UTF-8";` declaration from imported CSS. Element Plus's CSS (and many vendor stylesheets) declare their own `@charset`; once removed, the CSS parser doesn't know the file is UTF-8 and falls back to wrong encoding for non-ASCII glyphs.

**Fix**: delete the entire `css: { postcss: { plugins: [...] } }` block in `admin-web/vite.config.js`. The `postcssPlugin: 'internal:charset-removal'` was originally added to avoid duplicate `@charset` declarations in bundled CSS — but Element Plus and many icon libraries rely on it being present. Safe to remove. After deletion, restart Vite (it auto-restarts on config change).

### 15. RuoYi 4.x added tables (`sys_notice_read`) not in 3.x init SQL

**Symptom**: backend logs `Table 'jonlink.sys_notice_read' doesn't exist` on first page load. The mapper XML `com.jonlink.system.mapper.SysNoticeReadMapper.xml` is bundled in `jonlink-system-3.9.2.jar` (RuoYi 4.x) but `jonlink_init.sql` is from RuoYi 3.x.

**Fix**: add the missing table to your init SQL and re-run:
```sql
DROP TABLE IF EXISTS sys_notice_read;
CREATE TABLE sys_notice_read (
    read_id   BIGINT NOT NULL AUTO_INCREMENT,
    notice_id INT    NOT NULL,
    user_id   BIGINT NOT NULL,
    read_time DATETIME,
    PRIMARY KEY (read_id),
    UNIQUE KEY uk_notice_user (notice_id, user_id),
    KEY idx_user (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='公告已读记录';
```
Or `docker exec jonlink-mysql mysql -uroot -p<pwd> <db> < add_table.sql` to hot-apply.

### 16. MySQL 8 `caching_sha2_password` requires BOTH `allowPublicKeyRetrieval=true` AND a non-localhost user grant

Even with the JDBC URL fix from pitfall 11, backend still fails with `Access denied for user 'jonlink'@'172.18.0.1'` when the JDBC URL uses `localhost`. Why: Docker's internal DNS resolves `localhost` to a host-mode mapping, but Spring connects via the container network IP (e.g. `172.18.0.x`), which doesn't match the user grant on `@'localhost'`. Symptom chain: First error is `Public Key Retrieval is not allowed` (fix: pitfall 11 URL). After that fix, second error appears: `Access denied for user 'jonlink'@'<docker-network-ip>'`.

**Fix**: create a wildcard-host user, not just a localhost one:
```sql
CREATE USER IF NOT EXISTS 'jonlink'@'%' IDENTIFIED WITH mysql_native_password BY '<pwd>';
GRANT ALL ON <db>.* TO 'jonlink'@'%';
FLUSH PRIVILEGES;
```

The `@'%'` matches any source IP. Both `@'localhost'` AND `@'%'` can coexist. The `mysql_native_password` plugin (vs default `caching_sha2_password`) avoids the public-key-retrieval rabbit hole entirely if you can set it at user-create time.

### 17. Can't rebuild but need to change connection params — patch the jar in-place

When you only have the prebuilt `jonlink-admin.jar` (no source/maven on this box) and the URL or password in `BOOT-INF/classes/application-druid.yml` is wrong, do NOT throw the jar away and rebuild from source. Patch it in-place:

```python
import zipfile, shutil, os
src = '/path/to/jonlink-admin.jar'
dst = '/tmp/jonlink-admin-patched.jar'
target = 'BOOT-INF/classes/application-druid.yml'
with zipfile.ZipFile(src, 'r') as zin, zipfile.ZipFile(dst, 'w', zipfile.ZIP_DEFLATED) as zout:
    for item in zin.infolist():
        data = zin.read(item.filename)
        if item.filename == target:
            data = data.replace(b'old-url-string', b'new-url-string', 1)
        zout.writestr(item, data)
shutil.copy(dst, src)
```

Notes:
- Always keep a backup: `cp jar jar.bak` before patching.
- `writestr(item, data)` on an `item` you didn't read preserves metadata (timestamps, attrs). Don't reconstruct `ZipInfo` manually.
- For YAML edits, edit in binary mode (`'rb'`/`'wb'`) to preserve line endings (see pitfall 2).
- Test: extract the patched file and `grep` to confirm the replacement took.
- For Spring to pick up the change, restart the JVM. `java -jar` exits and re-loads everything from disk.

### 18. Destructive ops: backup-aware restore protocol

When the user says "delete everything in /opt/X and redeploy from /opt/X-backup", do NOT just `rm -rf`. Always follow this 6-step protocol BEFORE touching anything:

1. **Inventory the target dir**: `ls -la /opt/<project>/`, identify subdirs.
2. **Inventory the backup**: `ls -la /opt/<project>-backup/`, `tar -tzf ... | head` to confirm contents parse.
3. **Diff current vs backup**: `diff -rq /opt/<project> /tmp/backup-extract 2>&1 | head` — surface what's about to be lost. Items only-in-target (current) are unrecoverable after deletion.
4. **Enumerate what the backup does NOT cover**: env-installed software (`/opt/jdk`), unrelated projects (`/opt/openlist`), container data volumes (bind mounts that the backup tar excludes), running processes the user might not realize are tied to this dir.
5. **Present a 3-option plan**: (A) full restore from backup, (B) keep code, reset DB only, (C) full nuke including backup. Do NOT pick for them.
6. **After confirmation**: do it as one logical transaction: stop processes → stop containers → `rm -rf` → restore → rebuild → start. If any step fails, halt and report — don't paper over.

Common user assumption: "if I have a backup, redeploy is safe." Reality: backups are point-in-time snapshots; any work since the snapshot is lost. Surface this clearly so the user can choose knowingly.

### 19. Don't blanket-pkill matching process names

`pkill -f "node.*vite"` or `pkill -f "java"` matches the COMMAND STRING, not the actual process identity. If you have two unrelated processes whose argv happens to contain those tokens (e.g. a Vite dev server for admin-web AND h5-insure both contain "node" + "vite"), `pkill -f` will kill both.

**Fix**: identify the exact PIDs first via `ps aux | grep`, then `kill -9 <pid1> <pid2>`. For Java, prefer `pkill -9 -f jonlink-admin.jar` (matches the specific jar filename, won't hit other JVMs).

For backgrounded `npm run dev | tee` processes, the chain is `bash → npm → node → vite`. Killing the npm PID leaves the node child orphaned. Use `pkill -9 -f "node.*vite"` after first identifying which vite dev server you mean.

### 20. Generator velocity bug: Chinese table comments with `（...）` corrupt the Domain file

RuoYi generator renders `readConverterExp` from column comments. If a comment contains parentheses, commas, or quotes — e.g. `配置项 JSON（例如 {"downloadNewPolicy":true}）` or `产品编码（COM000）` — the generated `@Excel(name = "...", readConverterExp = "...")` line becomes a **compile error** (`')' expected`). Comments ending with `（AES加密）`-style suffixes also produce garbage like `readConverterExp = "A=ES加密"`. Unrendered Velocity placeholders also leak through: `/** $column.columnComment */` + `@Excel(name = "${comment}", readConverterExp = "$column.readConverterExp()")`.

**Symptom**: `mvn package` fails with `COMPILATION ERROR ... ')' expected` in `domain/JlXxx.java` line ~30.

**Fix** (batch-clean all generated Domains after landing, before compiling):
```python
import re, glob
for f in glob.glob('**/domain/Jl*.java'):
    c = open(f).read()
    c = re.sub(r'@Excel\(name = "([^"]*)", readConverterExp = "[^"]*"\)', r'@Excel(name = "\1")', c)  # drop readConverterExp entirely
    c = re.sub(r'    /\*\* \$column\.columnComment \*/\r?\n', '', c)                                   # drop unrendered comment line
    c = re.sub(r'@Excel\(name = "\$\{comment\}"\)', '@Excel(name = "状态")', c)
    open(f, 'w').write(c)
```
Scan with `grep -rn "\$column\|\$comment\|readConverterExp" .../domain/Jl*.java` to find all affected files.

### 21. Generated `/system/{business}` routes collide with RuoYi built-ins

The generator defaults to `@RequestMapping("/system/{businessName}")`. Business names derived from table prefixes can collide with RuoYi's own controllers. Observed collisions:

- `jl_channel_goods_config` → businessName `config` → `/system/config` **collides with SysConfigController** (参数设置 menu 106, perms `system:config:*`)
- `jl_notice` → `/system/notice` **collides with SysNoticeController**

**Fix**: rename the collision before compiling — backend `@RequestMapping` + all `@PreAuthorize` perms + frontend api js + frontend views dir:
- `config` → `goodsconfig` (`/system/goodsconfig`, `system:goodsconfig:*`)
- `notice` → `jlnotice` (`/system/jlnotice`, `system:jlnotice:*`); generate a separate `jlnotice.js` with renamed functions (`listJlNotice` etc.) so it doesn't shadow RuoYi's `notice.js`/`listNotice`.

Check all routes are unique after renaming: `grep -rh "@RequestMapping" .../controller/Jl*.java | sort | uniq -d` (must be empty) and cross-check against `jonlink-admin/src/main/java/com/jonlink/web/controller/**`.

### 22. Landing generated code: menu component/perms alignment + role binding

Generated zip's `<business>Menu.sql` inserts menus under 系统工具 with perms `system:{biz}:*`, but if menus were pre-created (e.g. hand-written business menus with custom perms), **do NOT run the Menu.sql** (duplicate rows). Instead align existing menu rows to the generated files:

1. **C menus**: `UPDATE sys_menu SET component='system/{biz}/index' WHERE menu_id=N` — the component must exactly match `src/views/system/{biz}/index.vue`.
2. **F buttons**: perms must exactly match the Controller's `@PreAuthorize("@ss.hasPermi('system:{biz}:list/add/edit/remove/export/query')")` strings, else buttons 403.
3. **admin role binding**: admin bypasses perm checks (`hasPermi` special-cases `role_key=admin`), but bind anyway for robustness:
   ```sql
   INSERT IGNORE INTO sys_role_menu (role_id, menu_id) SELECT 1, menu_id FROM sys_menu WHERE menu_id >= <first-new-id>;
   ```
4. **Verify via getRouters**: login → `GET /getRouters` → walk the tree; every C menu's `component` must match a real file under `src/views/`.

### 23. Generated frontend files can overwrite RuoYi originals — check git before trusting

Copying `vue/api/system/*.js` and `vue/views/system/*` over `src/` **silently overwrites RuoYi's own files** when names collide. Observed: generated `config.js` clobbered RuoYi's `@/api/system/config` (which `main.js` imports `getConfigKey` from) → vite `Pre-transform error: Failed to resolve import "@/api/system/config"`.

**Fix**: after copying, `cd admin-web && git status --short src/api src/views` — any `M`/`D` on pre-existing files is suspicious. Restore originals: `git checkout -- src/api/system/config.js src/views/system/config/index.vue src/api/system/notice.js src/views/system/notice/index.vue`. Keep generated versions under unique names (`goodsconfig.js`, `jlnotice.js`).

### 24. Spring Boot fat jar: `unzip -l` top-level does NOT show nested module classes

Business classes live in `BOOT-INF/lib/jonlink-system-*.jar` (a nested jar), not as top-level entries. `unzip -l app.jar | grep JlProduct` returns nothing even though classes are inside. **This is not a packaging failure.**

**Fix** (verify nested contents):
```bash
unzip -q app.jar 'BOOT-INF/lib/jonlink-system-*.jar' -d /tmp/jarcheck
unzip -l /tmp/jarcheck/BOOT-INF/lib/jonlink-system-*.jar | grep -c "Jl.*Controller"   # expect 18
```
Also confirm the module is actually a dependency: `grep -A2 'jonlink-system' jonlink-admin/pom.xml` — it may come transitively via `jonlink-framework`. The authoritative end-to-end check is: login → hit `GET /system/{biz}/list` with Bearer token → expect `code:200` (not 404/401).

## CRUD generation pattern (10+ tables)

For "generate CRUD for ~10-20 tables" requests:

1. Define table fields as Python dict: `{'product': {'name': '产品', 'fields': [('Long','id',...), ('String','productName',...), ...], 'perms': 'jl:product', 'class': 'Product'}, ...}`
2. Generate for each table: `Domain.java`, `Mapper.java`, `Mapper.xml`, `IService.java`, `ServiceImpl.java`, `Controller.java`
3. Write to: `<module>/src/main/java/<base>/{domain,mapper,service,service/impl}/` + `<admin>/src/main/java/.../web/controller/`
4. Post-process: `{{` → `{`, `}}` → `}` (see pitfall 6)
5. For XML tables, run snake_case fix (see pitfall 5)
6. Wire into parent `pom.xml` `<dependencyManagement>` if new module

## Verification recipe (after bootstrap)

```bash
# Backend health
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8080/    # expect 200

# Login (after captcha disabled)
TOKEN=$(curl -s -X POST http://127.0.0.1:8080/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"admin123"}' | jq -r .token)

# List businesses
curl -s http://127.0.0.1:8080/insure/product/list -H "Authorization: Bearer $TOKEN"

# Swagger UI (proves all controllers wired)
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8080/swagger-ui.html  # expect 302

# API count (proves all controllers loaded)
curl -s http://127.0.0.1:8080/v3/api-docs | jq '.paths | keys | length'

# Menu title sanity (catches 乱码 in pitfall 13)
curl -s http://127.0.0.1:8080/getRouters -H "Authorization: Bearer $TOKEN" \
  | jq '.data[].meta.title' | head -10
# expect: "产品管理" / "系统管理" / "用户管理" — NOT ç³»ç»Ÿç®¡ç†
```

### 25. SSH key fingerprint mismatch — verify before debugging sshd_config

**Symptom**: you've added your public key to `~/.ssh/authorized_keys`, permissions are right, `sshd_config` looks fine, yet `ssh user@host` keeps returning `Permission denied (publickey)`. You start adjusting `PubkeyAcceptedAlgorithms`, `PermitRootLogin`, `StrictModes`, etc., none of which fix it. Wasted 30+ minutes.

**Root cause**: the fingerprint of the key on the SERVER doesn't match the fingerprint of the key on the CLIENT. The public key you pushed was from a different machine/old install/random `id_ed25519.pub` you grabbed from the wrong directory. sshd correctly rejects the offered key.

**Diagnosis (do this BEFORE touching sshd_config)**:

```bash
# 1. On the CLIENT (your box) — note your key's fingerprint
ssh-keygen -lf ~/.ssh/id_ed25519.pub
#   → SHA256:Uh6gnUSgOugEo/Kh5sGxKqRqcF/MoKp5cF07BPowDZA

# 2. On the SERVER — compute the fingerprint of what's IN authorized_keys
ssh-keygen -lf ~/.ssh/authorized_keys
#   → SHA256:+DiY3wvvV6TuJJhbpZisF/zLDA0zPMSvHdkr4UvCOqU  ← MISMATCH!

# 3. With verbose SSH to see which key was offered
ssh -v user@host
#   debug1: Offering public key: /root/.ssh/id_ed25519 ED25519 SHA256:Uh6gnUSgOugEo/Kh5sGxKqRqcF/MoKp5cF07BPowDZA
#   debug1: Authentications that can continue: publickey,password  ← silently rejected, no reason given
```

**Fix**: copy the CORRECT `cat ~/.ssh/id_ed25519.pub` from the client INTO the server's `~/.ssh/authorized_keys`, then verify the fingerprint matches on both sides. sshd gives no hint about WHICH key it rejected — that's by design (security), so the only diagnostic path is fingerprint comparison.

**Why this is so easy to miss**: the public key string looks plausible (`AAAAC3NzaC1lZDI1NTE5AAAAI...`), sshd happily reads the file, permissions check out, the failure message just says "Permission denied". You never see WHICH key sshd rejected. Compare fingerprints first.

### 26. nginx master PID confusion when nginx is started outside systemd

**Symptom**: nginx is running (`ss -tlnp | grep :80` shows worker PIDs), but `systemctl reload nginx` returns `nginx.service is not active` and `nginx -s reload` says `/run/nginx.pid: No such file or directory`. `nginx` (without flags) tries to start a NEW master, fails on port 80 already in use.

**Root cause**: nginx was started manually (`nginx 2>&1` from a previous debugging session) rather than via systemd. The actual master process is the OLDEST nginx pid, not the one systemd would have started.

**Diagnosis**:

```bash
ps aux | grep '[n]ginx' | head
# root  420524  nginx: master process nginx      ← THIS is the real master
# www-data 420525-420528  nginx: worker process
# root  1276123  nginx: master process /usr/sbin/nginx   ← zombie from a failed systemctl
```

**Fix**: send SIGHUP directly to the real master PID (lowest-numbered `nginx: master process`):

```bash
# 1. Kill any zombie / failed second masters first
pkill -9 -f "nginx: master process /usr/sbin"  # only if you see one

# 2. SIGHUP the real master — it re-reads /etc/nginx/nginx.conf AND sites-enabled/*
kill -HUP 420524
sleep 2
ss -tlnp | grep ':<your-new-port>'
# should now see the new site listening
```

**Prevention** (do this on first contact with a server):
- `systemctl status nginx` → if "inactive (dead)" but port 80 is listening, nginx was started manually
- Either commit to systemd: `systemctl enable --now nginx && systemctl reload nginx` going forward
- Or always use `kill -HUP <master-pid>` for reloads

### 27. No-backup default for destructive ops (user preference)

User preference for this account: **`rm -rf` / replace / overwrite operations do NOT need a default backup.** Don't auto-create `.bak` files, don't `cp` the original next to the new version, don't zip up directories before deleting. Just do the destructive op.

**Exception (do back up)**:
- The user explicitly says "先留一份" / "先备份一下" / "我先看看再删"
- The op is irreversible AND the user has not pre-committed to the new state (e.g. they asked "replace X with Y, but keep X around in case Y is wrong")

**Default procedure**:
1. Take inventory of what's about to be lost (size, count, key paths)
2. Report the loss in the result: "删前 X.X MB → 删后释放 X.X MB"
3. Don't ask "要备份吗" — just do it

**Origin**: 2026-08-14 user said "旧版本可以直接删 不用备份" after I auto-created `ima-skill.v1.1.7.bak/` for a skill upgrade. They had to manually clean it up.

### 28. MyBatis `<where>` filter clauses are NOT auto-generated when you add a domain column

**Symptom**: You add a new column to a RuoYi/MyBatis domain table (e.g. `contact_id BIGINT` on
`jonlink_channel`, `channel_id` / `up_channel` on `jonlink_product`, `policy_type` on the product
table). You update `JonlinkXxx.java`, the `<resultMap>`, `<sql id="selectVo">`, `<insert>`, `<update>`
branches — and the API's `?newCol=value` filter **silently returns every row instead of just the
matching ones**. `code:200`, `total:69` (or whatever the table rowcount is), shape identical. The
dropdown filter in the UI does nothing and you can't tell from curl.

**Why**: RuoYi's generated mapper XMLs have a `<select id="selectJonlinkXxxList">` with a `<where>`
block whose `<if>` clauses were emitted by the original generator, one per column the generator
knew about. Adding a new column to the table + DTO + resultMap + selectVo + insert/update does
NOT generate a matching `<if>` filter. The controller forwards the new field (`query.setX(value)`),
MyBatis silently ignores it because there's no filter clause to apply, and you get an unfiltered
`SELECT *` back.

**Pattern observed**: three separate filter fields (`contact_id` on `channel/list`,
`channel_id` and `up_channel` on `product/list`) all bit this in the same session. The first two
were caught immediately because user asked; the third lived in production silently because
`?channelId=15` returned all 86 rows instead of 17 — looked healthy in the browser until the user
clicked the dropdown and saw the full list regardless of selection.

**Fix**: whenever you add a new column to a domain table, audit the corresponding
`selectJonlinkXxxList` `<where>` block and add `<if>` for it. Pattern:

```xml
<where>
    <if test="productName != null and productName != ''"> and product_name like concat('%', #{productName}, '%')</if>
    <if test="typeId != null"> and type_id = #{typeId}</if>
    <if test="channelId != null"> and channel_id = #{channelId}</if>      <!-- NEW -->
    <if test="upChannel != null and upChannel != ''"> and up_channel = #{upChannel}</if>  <!-- NEW -->
    <if test="shelfStatus != null and shelfStatus != ''"> and shelf_status = #{shelfStatus}</if>
</where>
```

**Detection recipe** (after every domain column addition):

```bash
# 1. Find the list query's <where> block
grep -n -A 30 'selectJonlinkXxxList' jonlink-system/src/main/resources/mapper/ledger/JonlinkXxxMapper.xml

# 2. Compare against the columns your DTO exposes. Every field the controller forwards
#    to query.setX() should have a matching <if> in <where>. The resultMap/selectVo/insert/update
#    branches are obvious; <where> is easy to forget.

# 3. End-to-end check: hit the API with the filter param set to a value that should EXCLUDE rows.
#    If total == table rowcount, the filter is no-op'd.
TOKEN=$(curl -s -X POST http://127.0.0.1:8080/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"admin123"}' | jq -r .token)
curl -sS "http://127.0.0.1:8080/ledger/product/list?channelId=15&pageSize=1" \
  -H "Authorization: Bearer $TOKEN" | jq .total
# Expect: 17 (the 17 products belonging to channel 15), NOT 86 (full table rowcount)
```

**Why this trap is dangerous**: `code:200` + non-zero `total` looks healthy on every curl-based
verification. The bug only surfaces when the user actually clicks the dropdown filter in the UI
and sees the same full list regardless of selection. By then it's been live for an unknown
duration.

### 29. `@/utils/request` is default export, NOT named — vite build fails on first `request(...)` call

**Symptom**: You add an ad-hoc API call to a Vue page (e.g. `loadContactList()` that does
`request({ url: "/ledger/contact/list", method: "get" })` to fetch a dropdown's options). You
write `import { request } from "@/utils/request"` because every other API client file in this
codebase uses named imports. `vite build` fails with:

```
✗ Build failed
"request" is not exported by "src/utils/request.ts", imported by
"src/views/ledger/channel/index.vue?vue&type=script&setup=true&name=Channel&lang.ts".

src/utils/request.ts (9:9): "request" is not exported by "src/utils/request.ts"
```

**Why**: in a RuoYi-Vue3 (and its forks: jonlink, plus, etc.) codebase, `src/utils/request.ts`
exports the axios instance as a **default export** (`export default service`), even though the
auto-imported API client wrappers (`@/api/ledger/product.ts` etc.) use named exports
(`export function listProduct(...)`). This asymmetry is consistent across the codebase but
non-obvious — you have to look at the actual `request.ts` source to see it.

**Fix**: always import as default for the low-level axios instance:

```ts
// ✅ correct — default import of the axios service
import request from "@/utils/request"

// ❌ wrong — looks plausible, will fail vite build
import { request } from "@/utils/request"
```

**Detection recipe** (before you write any direct `request(...)` call from a `<script>` block):

```bash
# Look at the actual export shape
head -20 src/utils/request.ts | grep -E '^export'
# Expect:   export default service
# NOT:      export const request = ...
```

**Why this trap bites once per session**: every session that uses `request` directly (instead of
going through `@/api/<module>` wrappers) gets it wrong the first time. It's only the 6th or 7th
time in this codebase that the pattern crops up. Pin it.

### 30. Business KPI dashboard (no 3D map) — pure-SQL aggregation + dark gradient cards

When you build a business dashboard for a jonlink module (e.g. "业务看板 / 业务数据看板"), the existing `WxMpBizController` (`/wx/dashboard/*`, based on `wx_*` tables) is **wrong for business data** — its KPI objects (`fans / verified / verified_amount / ledger_premium`) are public-account centric and meaningless for insurance / channel / product / salesman domain. The page renders, the API returns 200, but the values are noise.

**Pattern** (validated 2026-08-17 on `jonlink_dashboard` for jonlink ledger module):

#### (a) Backend: separate `XxxDashboardController` + `XxxDashboardMapper` for pure SQL aggregation

Don't reuse the entity domain classes' mapper (you'd be pulling 5+ JOINs into a "business view"). Create:

```
controller/ledger/JonlinkDashboardController.java
   → /ledger/dashboard/kpi | premiumTrend | companyShare | channelTop | productDistribution | salesmanTop | recentLedger
mapper/ledger/JonlinkDashboardMapper.java
   → List<Map<String,Object>> / Map<String,Object> return types only
mapper/ledger/JonlinkDashboardMapper.xml
   → resultType="map"; pure SELECT; no DDL/DML; sums + counts over business tables
```

Three rules:
1. **Mapper method return = `Map<String, Object>`** — not a DTO class. Aggregation outputs are heterogeneous per endpoint (`total_premium / total_profit / total_policy / unsettled_*`); boxing into a DTO would couple the chart shapes to the entity layer.
2. **`<select id="kpiXxx" resultType="map">`** — single SELECT per endpoint, no JOINs unless joining the SAME table (`COUNT(*)` + `SUM(CASE WHEN ...)`). Avoid LEFT JOIN with dictionary tables in the same query — keeps the mapper self-contained.
3. **Controller is `@RestController`, `@RequestMapping("/<module>/dashboard")`, extends `BaseController`** — uses `success(map)` / `success(list)` for the unified `{msg,code,data}` envelope. No `@PreAuthorize` annotation needed if the dashboard is viewable by any logged-in user (default RuoYi role check on the route menu covers it).

```java
// JonlinkDashboardController.java (verified 2026-08-17)
@RestController
@RequestMapping("/ledger/dashboard")
public class JonlinkDashboardController extends BaseController {
    @Autowired private JonlinkDashboardMapper mapper;

    @GetMapping("/kpi")
    public AjaxResult kpi() {
        Map<String,Object> data = new HashMap<>();
        data.put("productCount", mapper.kpiProduct().get("product_count"));
        data.put("channelCount", mapper.kpiChannel().get("channel_count"));
        data.put("salesmanCount", mapper.kpiSalesman().get("salesman_count"));
        data.put("totalPremium", mapper.kpiLedger().get("total_premium"));
        data.put("totalProfit", mapper.kpiLedger().get("total_profit"));
        data.put("totalPolicy", mapper.kpiLedger().get("total_policy"));
        data.put("unsettledPremium", mapper.kpiLedger().get("unsettled_premium"));
        return success(data);
    }
    // ... similar for premiumTrend / companyShare / channelTop / etc.
}
```

#### (b) Frontend: dark gradient KPI card style (CSS variable + accent bar)

The user said the wx dashboard was "数据不真实, 页面不好看". The look matters. Use the gradient accent + hover-lift pattern:

```vue
<div class="kpi-card kpi-blue">
  <div class="kpi-icon"><el-icon :size="22"><Money /></el-icon></div>
  <div class="kpi-body">
    <div class="kpi-label">累计保费</div>
    <div class="kpi-value">¥ {{ fmtMoney(kpi.totalPremium) }}</div>
    <div class="kpi-foot">保单 {{ kpi.totalPolicy }} 笔</div>
  </div>
</div>

<style>
.kpi-card {
  --accent: #3B82F6;  /* per-card CSS variable */
  position: relative;
  padding: 18px 16px;
  border-radius: 8px;
  background: linear-gradient(135deg, rgba(30,41,59,.85), rgba(15,23,42,.85));
  border: 1px solid rgba(148,163,184,.12);
  transition: transform .2s, box-shadow .2s;
  overflow: hidden;
}
.kpi-card:hover { transform: translateY(-2px); box-shadow: 0 8px 24px rgba(6,182,212,.15); }
.kpi-card::before {  /* top accent bar */
  content: ''; position: absolute; top: 0; left: 0; right: 0; height: 2px;
  background: var(--accent);
  box-shadow: 0 0 12px var(--accent);
}
.kpi-icon {
  width: 48px; height: 48px; border-radius: 8px;
  display: flex; align-items: center; justify-content: center;
  background: rgba(255,255,255,.04);
  border: 1px solid var(--accent);
  color: var(--accent);
}
.kpi-blue   { --accent: #3B82F6; }   /* 蓝 */
.kpi-cyan   { --accent: #06B6D4; }   /* 青 */
.kpi-purple { --accent: #A855F7; }   /* 紫 */
.kpi-orange { --accent: #F59E0B; }   /* 橙 */
.kpi-green  { --accent: #10B981; }   /* 绿 */
.kpi-red    { --accent: #EF4444; }   /* 红 */
</style>
```

Each KPI gets a one-line color override `--accent`. Don't hardcode 6 different `.kpi-card-blue / .kpi-card-cyan` selectors — that explodes the CSS.

#### (c) Chart layout that fills without scrolling

Three-row grid:
- **Row 1** (6-col): 6 KPI cards (`grid-template-columns: repeat(6, 1fr)`); responsive: `repeat(3,1fr)` at 1400px, `repeat(2,1fr)` at 768px
- **Row 2** (2-col): trend (bar+line dual y-axis) + company share (pie ring). `height: 320px` per chart
- **Row 3** (2-col): channel TOP N (horizontal gradient bars) + recent rows table

Do NOT use `calc(100vh - 84px)` like the 3D-map dashboard — business KPI pages **scroll normally** because 6 KPI + 4 charts + a table don't fit one screen. Use `min-height: 100vh` + page-level scroll.

#### (d) echarts patterns that survive this layout

- **Dual y-axis trend**: bar for premium (primary axis), line for profit (secondary axis). Smooth line + `areaStyle` gradient fill `rgba(245,158,11,0.35) → rgba(245,158,11,0)`.
- **Pie with `radius: ['38%', '70%']`** — donut ring works in 320px tall panels; full pie wastes center space.
- **Horizontal bars with gradient**: `LinearGradient(0,0,1,0)` left-to-right, `borderRadius: [0,4,4,0]` for right-rounded tips; `label.position = 'right'` to put numbers outside the bar (always legible even on narrow panels).
- **Pie matrix (2×2 mini pies)**: 4 pie refs in a `display: grid; grid-template-columns: 1fr 1fr` container. Each mini pie chart ~180px tall.

#### (e) Disposal + refresh

Refresh pattern: button → `allCharts.forEach(c => c.dispose()); allCharts.length = 0;` → re-`init` all → update header timestamp. **Don't reuse instances** across a structural refresh — if the user toggled a filter that changes number of KPI cards, old instances stay in the DOM and you'll have ghost charts.

Resize handler: `window.addEventListener('resize', () => allCharts.forEach(c => c.resize()))`; remove on `onBeforeUnmount`. Same `echarts.dispose(ref as HTMLElement)` on unmount.

#### (f) Endpoint inventory checklist

For a "see how we're doing" page on a business module, **always expose at minimum**:

| Endpoint | SQL pattern | Used by |
|---|---|---|
| `/<m>/dashboard/kpi` | 4 SELECTs, one per domain table | KPI card grid |
| `/<m>/dashboard/<metric>Trend?days=30` | `DATE_FORMAT(col,'%Y-%m-%d')`, GROUP BY date | Trend chart |
| `/<m>/dashboard/<entity>Share` | `GROUP BY <fk>` | Pie |
| `/<m>/dashboard/<entity>Top?limit=10` | `ORDER BY <metric> DESC LIMIT N` | Horizontal bar |
| `/<m>/dashboard/<entity>Distribution` | 3-4 GROUP BYs, returned as a `data = {shelf, policy, tax, company}` map | 2×2 mini pie matrix |
| `/<m>/dashboard/recent<Entity>?limit=5` | `ORDER BY date DESC LIMIT N` | Recent rows table |

7 endpoints is the right ceiling — more than 7 = the page has too many concerns, split it.

#### (g) Detection recipe (when user says "X 看板数据不真实")

```bash
# 1. List existing /<module>/dashboard/* endpoints
grep -rn "dashboard" /opt/<project>/<module>/src/main/java/com/<base>/web/controller/ 2>/dev/null
# 2. Compare endpoint SQL to the domain they actually mean
grep -rn "FROM wx_\|FROM jonlink_" /opt/<project>/<module>/src/main/resources/mapper/<module>/*Mapper.xml 2>/dev/null
# 3. If the dashboard controller queries wx_* tables but the module is jonlink ledger/product/channel, you have a wx-template leak.
```

### 31. `.catch(() => {})` on every CRUD handler — silently swallows success AND error feedback

**Symptom**: User reports "保险/公众号模块的删除按钮都不能用" / "I clicked 删除 and nothing happens". You open the browser, click a row's delete button →, a confirmation modal appears →, user clicks 确定 →, the row disappears from the table →, **but there is NO "删除成功" toast anywhere on screen**. In the failure case (foreign-key violation, record not found, code:500), the user sees... nothing at all. Both the success path and the error path feel "broken" — the user cannot tell whether the action succeeded, failed, or was never sent.

**Why**: The stock RuoYi-Vue3 CRUD generator writes every delete / batch-delete / remove handler as:

```ts
function handleDelete(row: JonlinkProduct) {
  const _ids = row.id || ids.value
  proxy.$modal.confirm('是否确认删除产品管理编号为"' + _ids + '"的数据项？').then(function() {
    return delProduct(_ids)
  }).then(() => {
    getList()
    proxy.$modal.msgSuccess("删除成功")   // ← only runs on code === 200
  }).catch(() => {})                       // ← black hole
}
```

Two failure modes interact:

1. **`msgSuccess` only fires when the response code is exactly `200`**. In `src/utils/request.ts` the response interceptor does:
   ```ts
   if (code === 500) {
     ElMessage({ message: msg, type: 'error' })
     return Promise.reject(new Error(msg))
   } else if (code === 601) { ... return Promise.reject(new Error(msg)) }
   else if (code !== 200) { ElNotification.error(...); return Promise.reject('error') }
   ```
   That reject **skips the next `.then()` entirely** — `msgSuccess` never runs. So even when the row really was deleted and the row disappears from the table, the user gets zero feedback.

2. **The empty `.catch(() => {})` is a black hole**. Any reject — real network error, 500 with a useful error message, 401 re-login prompt — is silently dropped. The ElMessage.error from the response interceptor does flash briefly (because it fired before the reject), but it's a transient toast in a corner the user isn't looking at, and any re-login flow that the interceptor kicks off gets its `.then()` chain discarded.

**Why this trap is dangerous**: A user clicks 删除, the row vanishes, the list reloads (because `getList()` is inside the first `.then()`), they assume success. If the row actually failed to delete (service threw and rolled back), the list reload will show the row again — but the user already moved on. Worse: in the 401 case, the "重新登录" modal may appear mid-action and silently close if the user clicks elsewhere, leaving them with a stale JWT.

**The fix** (single-file, safe): replace the empty catch with one that surfaces real errors and silently swallows only the cancel case (ElMessageBox confirmation dialogs reject with `e.message === 'cancel'` when the user clicks 取消 or the X close button):

```ts
function handleDelete(row: JonlinkProduct) {
  const _ids = row.id || ids.value
  proxy.$modal.confirm('是否确认删除产品编号为"' + _ids + '"的数据项？')
    .then(() => delProduct(_ids))
    .then(() => {
      getList()
      proxy.$modal.msgSuccess("删除成功")
    })
    .catch((e: any) => {
      // 用户点取消时不弹"已取消"提示; 其它所有错误都展示给用户
      if (e && e.message && e.message !== 'cancel') {
        proxy.$modal.msgError(e.message || '操作失败')
      }
    })
}
```

The `e.message !== 'cancel'` guard preserves the original intent (silently swallow ElMessageBox cancel when the user clicks 取消 — that should be a no-op, not an error toast) but surfaces **everything else** as a `msgError` — including `code:500` rejects. The duplicate-toast-vs-no-toast trade-off: yes, the response interceptor in `request.ts` already fired an `ElMessage.error` for `code:500` (so the user sees it twice), but **duplicate is better than silent loss**. The 401 branch in the interceptor handles re-login itself before the reject, so it doesn't double-fire.

**`.ts` file caveat** — `proxy.$modal` only exists in `<script setup>` of `.vue` files where `getCurrentInstance()` returns a usable proxy. In plain `.ts` files (helpers outside any component scope), `proxy` is undefined and this patch will throw a ReferenceError at runtime. The fix in `.ts` files: `.catch(() => undefined)` or `.catch(() => {})` — there is no UI to surface to anyway. Audit each `.ts` file before applying the same patch.

**Bulk fix recipe** (all `.vue` + `.ts` files in `src/views/`, applied via execute_code):

```python
import re, glob

PATTERN = re.compile(r'\)\.catch\(\(\) => \{\}\)')
REPLACEMENT = '}).catch((e: any) => { if (e && e.message && e.message !== "cancel") { proxy.$modal.msgError(e.message || "操作失败"); } })'

count = 0
files = []
for f in glob.glob('src/views/**/*.vue', recursive=True) + glob.glob('src/views/**/*.ts', recursive=True):
    with open(f) as fp: src = fp.read()
    if not PATTERN.search(src): continue
    new = PATTERN.sub(REPLACEMENT, src)
    # Catch some 替换 — 之前的 regex 会产生 }}).catch 这种 syntax 错, 修一下
    new = re.sub(r'\}\}\)\.catch', '}).catch', new)
    new = re.sub(r' \}\}\s*\}\)\.catch', ' }).catch', new)
    with open(f, 'w') as fp: fp.write(new)
    files.append(f); count += len(PATTERN.findall(src))
print(f'{len(files)} files, {count} replacements')
```

Verified pattern in production (jonlink 2026-08-19): 25 .vue + 1 .ts files, 32+ replacements, all `vite build` OK after cleanup.

**Where this pattern hides in jonlink**: the `.catch(() => {})` appears in every stock-generated CRUD view. In one audit, **9 ledger views + 12 wx views + ~4 batch handlers = 32+ occurrences**, all on handlers named `handleDelete` / `handleBatchDelete` / `handleRemove` / `handleSettle` / `handleGenTable`. Find them all:

```bash
cd /opt/<project>/<admin-web>
python3 - <<'PY'
import re, os
pat = re.compile(r'\.catch\(\(\)\s*=>\s*\{\s*\}\s*\)')
hits = []
for root, _, files in os.walk('src/views'):
    for f in files:
        if not f.endswith('.vue') and not f.endswith('.ts'): continue
        path = os.path.join(root, f)
        text = open(path).read()
        for m in pat.finditer(text):
            ctx = text[max(0, m.start()-300):m.start()]
            fn = re.search(r'function\s+(handle[A-Z][a-zA-Z]+)', ctx)
            hits.append((path, fn.group(1) if fn else '?'))
for h in hits: print(f'{h[0]}  {h[1]}')
print(f'TOTAL: {len(hits)} empty catches in views/')
PY
```

**Detection recipe** (any time a user reports "I clicked X and nothing happened"):

1. Open the page in the browser, open DevTools Network
2. Click the row button → does the request go out? If yes, what is the HTTP status and the body's `code`?
3. If the row vanishes (data really changed) but no toast → Trap 31
4. If the network request is missing entirely → suspect Trap E first (no-parens click), then the modal layer
5. If the request returns `code:500` with no toast → Trap 31 confirmed

**End-to-end browser verification is mandatory**: after fixing any `.catch(() => {})`, the success path's `msgSuccess` toast should appear in the bottom-right of the page within ~200ms of clicking 确定 in the confirmation modal. If it doesn't, the reject path is still swallowing something — re-read `src/utils/request.ts` and trace which `code` branch is firing.

**This trap is a sibling of Pitfall 29 / Trap E / Pitfall 32**, not a separate problem. All four manifest as "I clicked the button and nothing happened":
- **Pitfall 29** is about importing `request` wrong (build fails)
- **Trap E** is about the click event carrying the wrong arg (handler sees MouseEvent)
- **Pitfall 31** is about the response getting swallowed (no UI feedback)
- **Pitfall 32** is about `:disabled="multiple"` being the RuoYi default — the button is correctly disabled until you tick a row, but the user reads it as "broken"

When debugging "nothing happens", check all four before declaring the feature broken.

**Bonus trap inside the same fix**: the toast itself runs from the wrong scope when the user scrolls the page. `msgSuccess` uses `ElMessage` which renders into `document.body`, so it stays visible. But `ElMessageBox.confirm` (the modal) uses the dialog layer — confirm the modal actually opens by checking the DOM for `.el-message-box` BEFORE debugging the catch.

### 32. `:disabled="multiple"` RuoYi default — buttons look "broken" until user ticks a row

**Symptom**: User reports "列表页删除按钮不能点" / "the top-bar 删除 button is dead". You open the page →, the button is rendered red and looks enabled →, you click it →, **nothing happens** →, you conclude the click handler is broken (Trap E?) or the click event is swallowed. You spend 30 minutes debugging the wrong layer.

**Why**: The stock RuoYi-Vue3 CRUD generator wires the top-bar batch-action buttons to a `multiple` ref computed by `handleSelectionChange`:

```ts
function handleSelectionChange(selection: T[]) {
  ids.value = selection.map(item => item.id)
  single.value = selection.length != 1
  multiple.value = !selection.length    // ← empty selection → true
}

<el-button :disabled="multiple" @click="handleDelete()">删除</el-button>
<el-button :disabled="single"   @click="handleUpdate()">修改</el-button>
```

**The user's mental model**: a red "删除" button reads as "this will delete selected rows". RuoYi binds `:disabled="multiple"`, where `multiple` is `true` when **nothing** is selected. So the button is **disabled by default** and only becomes clickable after the user ticks **at least one row checkbox**. The `:disabled="single"` on 修改 inverts: only clickable when exactly one row is selected.

**Why this is a real bug surface**: in element-plus, a button bound to `:disabled="multiple"` may not visibly render the `[disabled]` attribute when `multiple` evaluates to `true` via a complex expression path (e.g. when `multiple` is a `ref` that doesn't yet reflect a `watch` update). The button **looks enabled but isn't** — users click, nothing happens, they file a bug. This is the highest-frequency "false alarm" on jonlink's WX module because most WX business tables are empty (Pitfall 33), so users see only the always-disabled top-bar buttons.

**Do NOT change `:disabled="multiple"` to `:disabled="!multiple"`**. This inverts the binding so the button is **always** enabled (even with no selection), then `handleDelete()` runs with empty `ids.value` and either fires a malformed request (`DELETE /ledger/product/`) or silently no-ops. This is a worse failure mode — looks enabled, clicks work, but the action is wrong. Verified in production: one jonlink session saw `:disabled="multiple"` → `!multiple` flip, the button became enabled-with-no-rows, then `handleDelete()` fired with empty `ids.value` and the user could no longer tell whether they had actually selected anything.

**Fix options**:

1. **Do nothing** — this is RuoYi's documented convention. Most operators learn "tick first, then click 删除" within a few uses. Document it in the user onboarding.
2. **Tooltip hint** — add `<el-tooltip>` that explains the requirement:
   ```vue
   <el-tooltip :content="multiple ? '请先勾选要删除的行' : ''" placement="top">
     <el-button :disabled="multiple" @click="handleDelete()">删除</el-button>
   </el-tooltip>
   ```
3. **Visible disabled hint** — render an info icon next to disabled buttons:
   ```vue
   <el-button :disabled="multiple" @click="handleDelete()">删除</el-button>
   <el-icon v-if="multiple" class="disabled-hint"><QuestionFilled /></el-icon>
   ```

**Detection recipe** — for every CRUD page in the project, verify both bindings are correct:

```bash
cd /opt/<project>/<admin-web>
# Find every delete button's :disabled binding
grep -rn ':disabled="multiple"\|:disabled="!multiple"' src/views/
# Find every update button's :disabled binding
grep -rn ':disabled="single"\|:disabled="!single"' src/views/
# Expected (RuoYi convention): every delete button uses "multiple", every update button uses "single"
# Any "!multiple" or "!single" is a regression — invert back.
```

The `:disabled="multiple"` is **correct** as-is. The trap is that operators who don't recognize the RuoYi convention think it's wrong and "fix" it (verified jonlink regression 2026-08-19 — the bad fix landed in 21 files before being rolled back).

### 33. Empty business tables look like "broken delete buttons" to a new user

**Symptom**: User opens the WX module (公众号管理) for the first time. Every list page shows "暂无数据" (no data). Every top-bar 删除 button is `disabled` (Pitfall 32 — correct RuoYi behavior). User concludes "the delete buttons don't work" and files a bug against the framework, not against the missing seed data.

**Why**: A fresh jonlink install has zero records in many of the WX business tables. Specifically, after the standard `init.sql` runs, these tables typically have 0 rows:

| Table | Typical row count | Why empty |
|---|---|---|
| `wx_mp_account` | 0 | User must configure their WX appId/appSecret manually |
| `wx_tag` | 0 | User must sync from WX API or add by hand |
| `wx_fc_config` | 0 | Form field config — created on first H5 page deploy |
| `wx_dist_member` | 0 | No referrals yet |
| `wx_dist_commission` | 0 | No orders yet |
| `wx_qr_scan_log` | 0 | No scans yet |
| `wx_biz_order` | 0 | No orders yet |
| `wx_msg_rule` | 0 | User must configure push rules |
| `wx_template` | 0 | User must sync templates from WX API |

The insurance/ledger module, by contrast, has seeded data (`jonlink_insurance_company` has 9 rows, `jonlink_channel` has 25, `jonlink_product` has 86, `jonlink_channel_user` has 160, `jonlink_settle_record` typically 0 but ledger has at least 1 test row). So the insurance module "feels alive" — list pages render, delete buttons become enabled after ticking. The WX module "feels dead" — empty list, disabled buttons, no way to demonstrate the delete flow.

**The trap**: the user reports "删除功能键无法使用" **across the project** because they sampled the WX module first. They aren't testing the code — they're sampling the data state. Fixing only Pitfall 31 (catch swallowing) doesn't help — empty tables don't unblock themselves. Fixing only Pitfall 32 (disabled binding) doesn't help — the buttons are correctly disabled when no rows are selected. The only real fixes are:

1. **Seed test data** for at least one WX table (e.g. add 3 sample `wx_tag` rows + 1 sample `wx_mp_account` row). This lets the user see the full delete flow at least once on the module that "feels dead".
2. **Empty-state messaging** — when a CRUD table has 0 rows, show a hint that explains how to seed the first record:
   ```vue
   <el-empty
     v-if="total === 0"
     description="暂无数据 — 请先在公众号后台同步标签 / 模板 / 规则,或手动新增"
   >
     <el-button type="primary" @click="handleAdd">新增</el-button>
   </el-empty>
   ```
3. **Distinguish "delete" from "select to delete"** in the button label:
   ```vue
   <el-button :disabled="multiple" @click="handleDelete()">
     {{ multiple ? '删除 (请先勾选)' : '删除所选' }}
   </el-button>
   ```

**Detection recipe** — run this on every jonlink install to spot which modules will look "broken" to a new user:

```bash
mysql -uroot -p<pwd> jonlink -e "
  SELECT 'wx_mp_account'        AS tbl, COUNT(*) cnt FROM wx_mp_account UNION
  SELECT 'wx_tag',               COUNT(*) FROM wx_tag UNION
  SELECT 'wx_fc_config',         COUNT(*) FROM wx_fc_config UNION
  SELECT 'wx_dist_member',       COUNT(*) FROM wx_dist_member UNION
  SELECT 'wx_dist_commission',   COUNT(*) FROM wx_dist_commission UNION
  SELECT 'wx_qr_scan_log',       COUNT(*) FROM wx_qr_scan_log UNION
  SELECT 'wx_biz_order',         COUNT(*) FROM wx_biz_order UNION
  SELECT 'wx_msg_rule',          COUNT(*) FROM wx_msg_rule UNION
  SELECT 'wx_template',          COUNT(*) FROM wx_template UNION
  SELECT 'jonlink_product',       COUNT(*) FROM jonlink_product UNION
  SELECT 'jonlink_channel',      COUNT(*) FROM jonlink_channel UNION
  SELECT 'jonlink_channel_user', COUNT(*) FROM jonlink_channel_user UNION
  SELECT 'jonlink_insurance_ledger', COUNT(*) FROM jonlink_insurance_ledger
" | sort -k2 -n
# Any WX table with 0 rows will show a disabled delete button
# that the user will read as "broken".
```

### 34. "删除功能键无法使用" — the 3-trap triage cluster

When the user reports "删除功能键无法使用" or "the delete buttons don't work anywhere", work **all three** of these in parallel:

- **Pitfall 31** — empty `.catch(() => {})` swallows success/error feedback (fix: see above)
- **Pitfall 32** — RuoYi's `:disabled="multiple"` is the correct convention (don't "fix" it)
- **Pitfall 33** — empty WX business tables look like broken buttons (seed data + empty-state messaging)

Each individual fix only addresses a third of the complaint. Fix only Pitfall 31 and the user can't tick-then-delete (Pitfall 32 is correct as-is). Fix only Pitfall 32 and the user sees no confirmation feedback (Pitfall 31 still swallowing). Fix only Pitfall 33 and the buttons work on seeded tables but the code is still fragile.

**The cheapest triage move** is real-browser e2e (open the page in browser, click delete, observe):
- Confirmation dialog appears and disappears without toast → **Pitfall 31**
- Button doesn't react at all to click → **Pitfall 32** (or possibly 33 if no row to tick)
- Rows visible but disabled → **Pitfall 33 + Pitfall 32** working as designed

Each diagnostic takes <30s and narrows the fix list immediately. Don't start writing fixes before doing the browser e2e — you'll fix the wrong trap and miss the others.

### 35. `row.id` on the first line of a toolbar handler — TypeError silently swallowed by `.catch`

**Symptom (after Pitfall 31 is fixed)**: User ticks rows in the table. The top-bar "删除" button becomes enabled (Pitfall 32 reversed — ticked selection makes `multiple.value=false`, button enabled). User clicks it. **No modal appears. No toast. No network request. The page just sits there.** This is the 4th trap in the "delete button doesn't work" cluster — sibling to 31/32/33 but deeper.

Worse case: **row-level inline "删除"** works fine (clicks row button → modal appears → confirm → row vanishes). Only the **top-bar batch button** is silent. This asymmetry is the diagnostic clue.

**Why** (the actual chain — verified 2026-08-19 on `/wx/fan` with 5 real rows):

1. Toolbar template writes `@click="handleDelete()"` (with parens). User-tick + click → button enabled → click event fires normally.
2. Vue 3 compiles `@click="handleDelete()"` to `onClick: a[4] || (a[4] = l => A(l))`. The wrapper passes whatever the event invoker hands it (`l`) to `A` (the minified `handleDelete`) as the first arg.
3. In most Vue 3 + element-plus combinations the invoker passes a `MouseEvent` — `A(u)` reads `u.id` → undefined → `|| ids.value` → array of ticked ids → modal opens. **Works.**
4. **In some nested invoker paths** (especially `<el-button>` inside `<el-row>`/`<el-col>` where sibling handlers also bind), the invoker passes **the row identifier proxy, NOT a MouseEvent**. `u` becomes a Component internal proxy or `null`. **Then `u.id` throws `TypeError: Cannot read properties of null (reading 'id')`.**
5. The throw lands inside the `.then()` chain's first Promise. The next `.then(() => msgSuccess("删除成功"))` is skipped (Promise rejected). The `.catch((e) => { if (e?.message !== 'cancel') msgError(...) })` catches — BUT:
   - If the throw is a Vue-internal string/number (not an Error object), `e.message` is `undefined`, the `if (e && e.message && e.message !== 'cancel')` guard fails, **and `msgError` is NOT called** — the throw is silently swallowed.
   - Even if `msgError` does fire, the modal already failed to open — there's nothing to dismiss.

End result: **the user sees nothing**. No modal. No toast. No network call. The handler "ran" (in the sense that Vue's click listener was invoked) but every observable side-effect died at the first line.

**Inline row-delete works** because `@click="handleDelete(scope.row)"` (with an explicit row arg) makes the wrapper `(me) => A(scope.row)` — the invoker's MouseEvent is discarded, scope.row is always a real domain object, `row.id` is always defined. Only toolbar `@click="handleXxx()"` triggers this trap.

**Diagnosis recipe** (when "toolbar 删除 does nothing but row-level 删除 works"):

1. Open browser DevTools console.
2. Tick a row. Click toolbar 删除.
3. Console is silent (no log, no error, no network in the Network panel).
4. Add `console.log('[handler] entry, row=', row)` as the FIRST line of `handleDelete`. Rebuild. Re-click.
5. If the log fires but the next line (`const _ids = row.id || ids.value`) doesn't print, the throw is on that line.
7. Optional deeper trace — wrap the WHOLE first line in try/catch and see what `e` actually is:
   ```ts
   try { const _ids = row.id || ids.value } catch (e) { console.error('handleDelete first line:', e, 'row=', row); return }
   ```

**The fix** — defensive guard at the top of every toolbar handler that reads a field from `row`:

```diff
- function handleDelete(row: WxMpUser) {
-   const _ids = row.id || ids.value
+ function handleDelete(row: WxMpUser) {
+   const _ids = (row && row.id) || ids.value
```

`(row && row.id)` short-circuits cleanly when `row` is null/undefined (returns `undefined`), otherwise returns `row.id`. The fallback to `ids.value` (the ticked-rows array) keeps the same behavior as before for the "no row selected" path. **Pick this form (`(row && row.X)`) over `row?.id`** to stay consistent with the older guarded spots already in this codebase.

**Don't stop at `row.id`**. Audit every handler that reads ANY field off `row` in the first 1-3 lines of the function body. Common patterns:

```ts
const _ids = (row && row.id) || ids.value                    // most common
const _name = (row && row.fieldKey) || ''                   // for display text
const _batch = (row && row.batchNo) || ''                   // for confirm message
const _v = (row && row.version) || 1                        // for optimistic locking
```

If the confirm message uses a field off row, guard THAT too — otherwise a TypeError there will replace the modal-show error with an undefined interpolation in the modal title.

**Bulk-fix recipe** (one-time, when this trap is first hit in a project):

```bash
cd /opt/<project>/<admin-web>

python3 - <<'PY'
import re, glob

# All .vue files under src/views/ledger and src/views/wx (or wherever
# CRUD views live). Skip .ts files unless they have access to `proxy`.
files = []
for d in ['src/views/ledger', 'src/views/wx', 'src/views/business']:
    for f in glob.glob(f"{d}/**/*.vue", recursive=True):
        files.append(f)

changed = 0
patches = 0
for fp in files:
    with open(fp, 'r', encoding='utf-8') as f:
        src = f.read()
    new = src

    # Pattern 1: `const _ids = row.id || ids.value` (the headline case)
    new, n = re.subn(
        r'(function handle[A-Z][a-zA-Z]+\(row:\s*\w+\)\s*\{\s*\n\s*)(const \w+\s*=\s*)row\.(\w+)(\s*\|\|\s*ids\.value)',
        r'\1\2(row && row.\3)\4',
        new
    )
    patches += n

    # Pattern 2: `proxy.$modal.confirm('...编号为"' + (row.fieldKey || '')` style
    # (defensive — apply if function uses row.X in any literal)
    new, m = re.subn(
        r"(proxy\.\$modal\.confirm\([^)]*?)\(row\.(\w+)\s*\|\|\s*['\"`]?\)",
        r"\1(row && row.\2) || '')",
        new
    )
    patches += m

    if new != src:
        with open(fp, 'w', encoding='utf-8') as f:
            f.write(new)
        changed += 1

print(f"patched {changed} vue files, {patches} total replacements")
PY

# Rebuild
npx vite build 2>&1 | tail -3
```

**Always rebuild + real-browser verify**. The bulk patch is mechanical but only a real browser click proves it works:

1. Tick one row.
2. Click toolbar 删除 → expect modal: "是否确认删除...编号为\"X\"的数据项?"
3. Click 取消 → modal closes silently, DB unchanged.
4. Re-tick, click 确定 → modal closes, row vanishes, green msgSuccess toast appears (from Pitfall 31 fix), DB row deleted.
5. **Cancel confirm must NOT trigger a cancel toast** — verify by clicking 取消 and observing that no toast flashes.
6. **Always SQL-restore the test row** — never leave the DB dirty:
   ```sql
   INSERT INTO <table> (id, ...) SELECT <old_id>, ... FROM <table> WHERE <old_id> LIMIT 0;
   -- or, if the row was the only one:
   DELETE FROM <table> WHERE id = <old_id>;  -- already deleted
   -- then re-insert via API or direct SQL with a synthesized row
   ```

**Why this trap is so easy to miss in isolation**: the user says "delete doesn't work". Triage suggests Pitfall 31/32/33. Fix all three, rebuild, reload, retest — **still nothing**. The fourth trap is invisible until you actually look at the handler body and realize `row.id` is the first thing it touches. Always read the first 5 lines of `handleDelete` / `handleCheck` / `handleSettle` / `handleXxx` before declaring the page "fixed".

**Companion fix for `.ts` files**: handlers in plain `.ts` files (helpers outside `<script setup>`) don't have `proxy` and can't call `msgError`. For those, the catch can only do `.catch(() => undefined)` or `.catch((e) => console.error(e))`. The first-line `row.id` guard is still mandatory — same TypeError will happen, just with a console error instead of a toast.

**The four traps as a debugging checklist** (use this order — cheapest first):

| # | Diagnostic | | Trap |
|---|---|---|
| 1 | Click the button. Does ANY a network call go out? | | If no → Trap E (no-parens click) or Pitfall 32 (disabled) or Trap 35 (first-line throw) |
| 2 | Network call returns but no UI confirmation? | | Pitfall 31 (catch swallowing) |
| 3 | Confirmation appears but disappears without toast? | | Pitfall 31 (success-path skip) |
| 4 | Row vanishes but no "删除成功" toast? | | Pitfall 31 (msgSuccess blocked by reject) |
| 5 | Page "looks broken" with no rows visible? | | Pitfall 33 (empty table) |
| 6 | Button visibly disabled but user expects to click? | | Pitfall 32 (correct RuoYi convention — UX issue, not bug) |
| 7 | Toolbar batch silent, row-level works? | | **Pitfall 35** (this entry) |

Don't guess from " the diagnosis. Walk through 1-7 in order — each takes <30 seconds of real browser interaction and identifies exactly which fix to apply.

**Origin**: this trap was found on 2026-08-19 when the user said "粉丝管理页面的删除就无法使用阿, 全选粉丝后删除就没有相应" (粉丝管理 / wx/fan). Pitfall 31 had been fixed the day before, but the user was still seeing silent toolbar-delete failures. The bulk fix landed on 23 .vue files (`(row && row.id) || ids.value` everywhere), all rebuilds + browser verifies passed, and the silent failure disappeared. This trap should be checked **immediately after** Pitfall 31 in any new project onboarding.

### 36. `resultType="java.util.Map"` in aggregate queries silently drops columns AND collapses the returned list

**Symptom**: A report/list endpoint returns `code:200` with `data: [{...}]`, BUT the array length is much smaller than the underlying table (e.g. 1 row when `SELECT * FROM fin_subject WHERE is_leaf=1` returns 17). Or, the JSON shows `"subjectId": null, "subjectCode": "1001", ...` — a literal null where the SQL clearly populates the column.

**Why**: MyBatis's auto-mapping for `resultType="java.util.Map"` does **not** auto-convert `subject_id` → `subjectId` (no `mapUnderscoreToCamelCase` for Map result types). The column name becomes the literal map key, and SQL `AS` aliases are unreliable across MyBatis versions.

The **list-collapsing** variant is even sneakier: when the Java code builds `Map<Long, Map<String,Object>>` keyed by `(Long) s.get("id")` and the first row's `id` key is `null` (because the column name didn't match), every subsequent row's `id` key is also `null` — and `Map.put(null, ...)` overwrites the previous `null` entry. The Map ends up with 1 entry regardless of how many rows the SQL returned. Jackson serializes whatever the Map contains. SQL/MAPPER are both correct; the List contains the right number of `Map` objects; the Map itself has 1 entry.

**Fix**: declare an explicit `<resultMap>` and use `resultMap=` not `resultType="java.util.Map"`:

```xml
<resultMap id="SubjectMap" type="java.util.LinkedHashMap">
  <result column="id"               property="id" />
  <result column="subject_code"     property="subjectCode" />
  <result column="subject_name"     property="subjectName" />
  <result column="subject_type"     property="subjectType" />
  <result column="balance_direction" property="balanceDirection" />
</resultMap>

<select id="listLeafSubjects" resultMap="SubjectMap">
  select id, subject_code, subject_name, subject_type, balance_direction
  from fin_subject where status = '1' and is_leaf = '1'
  order by subject_code
</select>
```

Key points:
1. `resultMap="XxxMap"` not `resultType="java.util.Map"`
2. column names go **as-is** (no `AS` aliases needed)
3. Java reads `r.get("id")`, `r.get("subjectCode")` etc. — these are the properties you declared in the resultMap
4. If you need a different output key (e.g. Java side uses `subjectId` but DB column is `id`), map them separately: `<result column="id" property="subjectId" />`

**Detection recipe** (run after every aggregate endpoint that returns `List<Map>`):

```bash
TOKEN=$(curl -s -X POST http://127.0.0.1:8080/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"admin123"}' \
  | jq -r .token)

curl -s -H "Authorization: Bearer $TOKEN" \
  "http://127.0.0.1:8080/<your-endpoint>" | python3 -c "
import sys, json
d = json.load(sys.stdin)['data']
print('total:', len(d))
for r in d[:3]: print(r)"
```

If `total < SQL COUNT(*)` or any key is `null` when the column is NOT NULL, you're in this trap. Add the `<resultMap>`, rebuild, re-test.

**Don't confuse with Pitfall 5** — Pitfall 5 is about column-name placeholders being eaten by template substitution. This trap (36) is about Map key/value mapping, which happens entirely inside MyBatis runtime — no template substitution involved.

### 37. `@Transactional(rollbackFor=Exception.class)` + `ServiceException` catch = silent rollback-only

**Symptom**: An `@Transactional` method catches `ServiceException` and "continues", but ALL its DB writes are silently rolled back. The HTTP response is `code:500` with `msg: "Transaction rolled back because it has been marked as rollback-only"`. The catch block looks like it "handled" the exception — but the data is gone.

**Why**: Spring marks the transaction `rollback-only` the moment `ServiceException` propagates up to the `@Transactional` proxy boundary, EVEN IF the calling method then catches it. Once `rollback-only` is set, ALL writes in that transaction (including the ones after the catch block) are rolled back at commit time.

`@Transactional(rollbackFor = Exception.class)` says "any Exception triggers rollback". Spring uses `TransactionAspectSupport.currentTransactionStatus().setRollbackOnly()` when the exception escapes the proxied method. The `catch` block runs in the SAME transaction context — the rollback-only flag persists.

**Fix — validate state BEFORE calling the proxied service**:

```java
// BEFORE (broken — ServiceException from unpost() silently marks rollback-only)
try {
    voucherService.unpost(row.getVoucherId(), operator);
} catch (ServiceException e) {
    log.warn("反过账跳过(可能草稿): {}", e.getMessage());
}
row.setStatus("0");
logMapper.updateFinLedgerVoucherLog(row);  // <-- silently rolled back at commit

// AFTER (works — unpost never called when state doesn't allow it)
FinVoucher v = voucherService.selectFinVoucherById(row.getVoucherId());
if (v != null && "2".equals(v.getStatus())) {
    voucherService.unpost(row.getVoucherId(), operator);  // safe: state is valid
} else {
    log.warn("凭证 {} 非已过账状态(status={}),跳过 unpost",
             row.getVoucherNo(), v == null ? "?" : v.getStatus());
}
row.setStatus("0");
logMapper.updateFinLedgerVoucherLog(row);
```

**Alternative fixes** (use only when you genuinely need to swallow a specific exception):

1. `@Transactional(noRollbackFor = ServiceException.class)` — Spring won't mark rollback-only for that one exception class. But this loses rollback safety for OTHER exceptions inside the same method, so apply carefully.
2. Move the swallow into a separate `@Transactional(propagation = REQUIRES_NEW)` inner method that owns its own transaction.
3. Wrap the swallowed exception in a domain-specific subclass (`NoOpException extends RuntimeException`) and configure `noRollbackFor` on it.

**Why this trap bites RuoYi-Vue3 + Spring Boot 4.x specifically**: the RuoYi-Vue3 templates default to `rollbackFor = Exception.class` (the broadest). This is correct for standard CRUD where any error should roll back. It becomes a trap only when a developer adds a "try / catch / continue" block expecting catch to actually commit. They will not — Spring commits-with-rollback-only, throwing 500.

**Detection recipe** (when you see "Transaction rolled back because it has been marked as rollback-only" in the boot/test log, AND the catch block seemed to "handle" the exception):

1. Find the actual exception type that triggered rollback (usually `ServiceException` thrown deep inside the proxied call).
2. Confirm `@Transactional(rollbackFor = ...)` includes that exception's superclass (default `RuntimeException` is included).
3. **Restructure**: validate state BEFORE the proxied call, so the exception is never thrown in the first place.

### 38. Custom M-stage endpoint patches must edit the AUTO-GEN controller in `web.controller.system`, not create a sibling in `system.controller`

**Symptom**: After M0 generator output is in place (controllers in `com.jonlink.web.controller.system.<FinXxx>Controller.java`, jonlink-admin module), a later module stage (M1/M2/M3...) needs a new endpoint on a controller that already exists. You write a brand-new `FinExpenseController.java` and put it in `com.jonlink.system.controller` (the jonlink-system module package, where services live). `mvn package` succeeds. The app starts. **BeanDefinitionStoreException** at startup:

```
org.springframework.context.annotation.ConflictingBeanDefinitionException:
  Annotation-specified bean name 'finExpenseController' for bean class
  [com.jonlink.system.controller.FinExpenseController] conflicts with existing,
  non-compatible bean definition of same name and class
  [com.jonlink.web.controller.system.FinExpenseController]
```

The app fails to start. The "controller is duplicated" error message looks like a copy-paste mistake — it's not. It's **two different classes with the same default bean name** (`<ClassName>Controller` lowercased). Spring picks the one it scans first; the second scan fails.

**Why this is so tempting to do wrong**: the jonlink-system module is the obvious place for "new business code" — services, domain, mapper all live there. The auto-generated controller in `web.controller.system` (admin module) feels like a remote artifact that's been there since M0 and shouldn't be touched. So you naturally reach for "create a sibling in system.controller/". But that **always fails** because both controllers get the default `@RestController` → bean name `finExpenseController` → Spring can't tell them apart.

**Pitfall 45** in `jonlink-batch-module-deploy` covers the **initial move** of generated output from gen zip to `web.controller.system`. This pitfall (38) covers the **follow-on question** of where to put custom endpoints added in later stages.

**Fix — always edit the existing auto-gen controller in place**:

```bash
# RIGHT: open the auto-gen controller and add your custom endpoint
vim jonlink-admin/src/main/java/com/jonlink/web/controller/system/FinExpenseController.java

# WRONG: create a new controller with the same name in the wrong package
vim jonlink-system/src/main/java/com/jonlink/system/controller/FinExpenseController.java
```

Add the new method alongside `getInfo` / `add` / `edit` / `remove`:

```java
@PreAuthorize("@ss.hasPermi('finance:expense:add')")
@PostMapping("/withItems")
public AjaxResult addWithItems(@RequestBody Map<String, Object> body) {
    Long id = expenseService.createWithItems(
        (String) body.get("applicant"),
        (String) body.get("deptName"),
        ...
    );
    return AjaxResult.success(id);
}
```

The class is already `@RestController` + `@RequestMapping("/finance/expense")` — your `@PostMapping("/withItems")` is appended to the same controller. No bean-name collision. The `expenseService` field is already injected via `@Autowired IFinExpenseService expenseService`; add new dependencies (mappers, other services) to that block.

**Don't try to "extend" the auto-gen controller via inheritance or composition** — adding a `FinExpenseControllerExt extends FinExpenseController` (or wrapping it in a facade) introduces a second `@RestController` bean that scans the same `@RequestMapping` namespace, and you hit the same `ConflictingBeanDefinitionException` plus a more confusing `Ambiguous mapping` error. Just open the auto-gen file and add your methods.

**Why P38 differs from P45**: P45 is a one-time setup move (all 17 controller files from the M0 gen zip → admin module). P38 is the recurring question "where do I put a new endpoint when adding M1/M2 features" — answered by "edit the file that's already there."

**Detection recipe** (after any mvn package that includes a new business endpoint):

```bash
# 1. Did the bean-name collision error happen at startup?
grep -A2 "ConflictingBeanDefinitionException" /tmp/jonlink-admin.log
# If yes: you have duplicate <FinXxx>Controller beans.

# 2. Find both copies (should only be one)
find /opt/JonLink/JonLink-Vue/jonlink-system/src/main/java/com/jonlink/system/controller -name '*Controller.java' 2>/dev/null
find /opt/JonLink/JonLink-Vue/jonlink-admin/src/main/java/com/jonlink/web/controller/system -name '*Controller.java' | wc -l
# jonlink-system: should be 0 (controllers live in jonlink-admin only)
# jonlink-admin: should equal the auto-gen count

# 3. Move: delete the wrong-package copy, add your method to the auto-gen file
rm /opt/JonLink/JonLink-Vue/jonlink-system/src/main/java/com/jonlink/system/controller/FinExpenseController.java
# then patch FinExpenseController.java in jonlink-admin
```

### 39. Vue `<script setup>` redeclaration — ref name and function name collide at compile time

**Symptom**: In a `<script setup lang="ts">` block, you define both a `ref` for component state AND a function for handler logic using the same name:

```ts
const viewItems = ref<any[]>([])      // state for the dialog table
function viewItems(row: any) { ... } // handler that opens the dialog
```

`npm run build` (or `vite build`) fails with a parser error before any TypeScript checking:

```
SyntaxError: Identifier 'viewItems' has already been declared
  at constructor (.../@babel/parser/lib/index.js:369:19)
  at checkRedeclarationInScope (.../index.js:3623:19)
  at declareName (.../index.js:1589:12)
```

The error is in `<script setup>` only — the same names in `<script>` (Options API) would NOT collide because Options API separates `data()`, `methods`, `computed` etc. into different keys.

**Why**: `<script setup>` flattens all top-level bindings into a single scope before the compiler emits the setup function. A `const` and a `function` with the same identifier in the same scope are a TypeScript / ES2015 redeclaration — illegal in strict mode. The `@babel/parser` Babel transform that Vite uses for `<script setup>` enforces this even when `lang="ts"` is set.

**Why this trap bites once per rewrite**: When you do a wholesale rewrite of an auto-gen view (replace the dialog-heavy default with a custom dialog + handler), it's natural to name the new dialog's row-collection `viewItems` (mirrors what the auto-gen page did) and the handler that opens the dialog also `viewItems(row)`. The auto-gen page had these as separate `data()` and `methods` keys, so they didn't collide; in `<script setup>` they do.

**Fix — rename one side**:

```ts
// Common rename patterns:
//   ref:  viewItems → itemRows / dialogRows / rows
//   fn:   viewItems → viewItems / openDetail / showDetail
const itemRows = ref<any[]>([])       // ← renamed from viewItems
function viewItems(row: any) {        // ← handler keeps the name
  getExpense(row.id).then((res: any) => {
    itemRows.value = res.data.items || []   // ← references renamed ref
    viewOpen.value = true
  })
}
```

**Convention**: handlers that "view" or "open" something tend to keep action-style names (`viewItems`, `showDetail`, `openApply`); refs tend to take a more descriptive container name (`itemRows`, `dialogItems`, `detailData`).

**Detection recipe** (after every wholesale rewrite of a stock CRUD view):

```bash
# 1. Build and check for the error
npm run build:prod 2>&1 | grep -E "already been declared|SyntaxError" | head
# If any matches: rename the colliding identifier.

# 2. Audit the script setup block for common collision candidates
grep -n -E "^const (view|show|open|apply|edit|add|remove|delete|submit|save|cancel|reset|viewItems)" src/views/<module>/<biz>/index.vue | head -20
# Look for duplicate identifier names across `const` and `function` lines.
```

**Why this trap is so easy to miss in isolation**: the file is 200+ lines, the Vue compiler only complains about ONE identifier at a time, and the renaming is mechanical. But each rename invalidates every `<template>` reference that used the old name. Always do the rename + grep-after, not rename + commit.

**Companion trap — `<script setup>` is hoisted**: unlike Options API, every binding in `<script setup>` is hoisted to the top of the setup closure in declaration order. So a `function viewItems(row)` that references `viewItems` (the ref) will fail at runtime with `TypeError: viewItems is not a function` (or vice versa) because the function is hoisted to before the ref's initialization. This is a runtime error, not a build error, and shows up only when the handler is invoked. Always rename at build time, never at runtime debugging time.

### 40. `@click="handler"` (no parens) — Vue passes the MouseEvent as the first arg, your handler reads `row.X` on it, TypeError → silent catch swallow → "the button does nothing"

**The single most-recurring class of bug** on this project (verified 2026-08-11, 2026-08-14, 2026-08-19 — at least 3 distinct batch-fixes across M1, M2, M5, M6 phases). Detailed diagnostic, fix recipe, bulk-fix script, and the 4-trap triage cluster — see `references/vue-click-handler-pitfall-40.md`.

## Reference files

- `references/maven-multi-module.md` — dependencyManagement, parent/child pom patterns, the mvn install → java -jar sequence
- `references/docker-mysql-redis-init.md` — docker-compose config, initdb.d lifecycle, registry mirror setup, captcha-via-Redis
- `references/mybatis-xml-template-escape.md` — Python template → MyBatis XML gotchas (double brace, snake_case leak, #{} regex bug)
- `references/yaml-crlf-patch.md` — preserving CRLF when patching application.yml
- `references/jonlink-framework-quirks.md` — @Anonymous, @PreAuthorize, captcha, jwt secret, swagger auto-init
- `references/vue3-vite-setup.md` — npm install devDeps, port 80, xdg-open, proxy /dev-api, **charset-removal postcss fix (pitfall 14)**
- `references/verification-recipes.md` — curl-based smoke tests for each major API group
- `references/mysql-utf8-recovery.md` — diagnosing and repairing double-encoded Chinese rows (pitfall 13)
- `references/code-generator-recipe.md` — RuoYi `/tool/gen` end-to-end workflow: import table → edit display flags → preview → download zip → unpack → copy to module → run `<business>Menu.sql` → rebuild. Includes which `.vm` templates to patch for non-default module paths and parent_id.
- `references/batch-generator-landing.md` — landing generated code for 10-20 tables at once via `batchGenCode` API: zip layout, sys_menu component/perms alignment, orphan-table menus, compile-fix loop, end-to-end verification checklist (pitfalls 20-24).
- `references/jonlink-site-reverse-engineering.md` — extracting a competitor RuoYi admin's menu tree / API routes / field schemas from the minified SPA bundle + a JWT, without a browser: baseURL discovery, auth-header probing, getRouters dump, field inference from validation errors, and pivoting to hand-designed tables when the token is low-privilege.
- `references/jonlink-rebranding.md` — full re-brand sweep for RuoYi forks (English + Chinese name): env titles, pom name/description, homepage contact card QQ群 removal, y_project repo links, allowed-domains, FUNDING.yml; what NOT to change (package names, artifactId) and the must-be-0 grep verification.
- `references/local-mariadb-fallback.md` — using locally-installed MariaDB 10.11 + Redis 7 when Docker Hub AND mirrors stall: detection, unix_socket root auth, DB creation (init SQL has no CREATE DATABASE), compatibility checks, and MySQL-8-only syntax scan.
- `references/business-kpi-dashboard-recipe.md` — pure-SQL-aggregation business KPI dashboard (no 3D map): separate `XxxDashboardController` + `XxxDashboardMapper.xml`, dark gradient KPI cards with `--accent` CSS variable, 7-endpoint ceiling, porting checklist (pitfall 30).
- `references/finance-module-rollout-m0-m7.md` — incremental M-stage rollout pattern (M0 建表 → M7 部署验证) for adding a finance/business module to a running admin: generator-first, package discipline (services in `system/`, controllers in `web.controller.system`), curl冒烟 + 浏览器 e2e per stage, M-stage naming conventions, DB菜单/权限patch节奏, smoke-test对原功能零破坏.
- `references/finance-ui-labeling-and-dict.md` — the **standing UI rule** (no raw `0`/`1`/`2`/`3` numbers in user-facing labels — always Chinese text) + the **`financeDict.ts` centralized helper pattern** (single source of truth for enum→label+tag-color translation across all finance/admin pages) + **Pitfall 41: DB column comment vs engine code mismatch** (e.g. `direction` convention drift between DDL `COMMENT` text and `setDirection("0")` calls) + **the mandatory `import` warning** for `finDict` / `finDictItem` (missing import → silent `<!---->` in scoped slots, the most-easily-missed cause of empty cells).
- `references/excel-export-table-header-shortening.md` — **the same UI label rule applied to backend `@Excel(name=...)` annotation** (which is what users actually see in Excel/CSV exports, NOT the dict-translated UI label). Covers: what to keep vs what to drop from `name=`, why regex normalization fails (pure enum / mixed English+Chinese / English prop name) and **a hand-written mapping table keyed on `(DomainFile, prop, currentName) → newName`** is the only reliable path, the **single full-directory scan** (do not stop after first batch — found 94 names by stopping at 19 the first time), and the **column-collision check** after shortening (e.g. both `accessToken` and `tokenExpireTime` ending up as `access_token` variants). Includes the build/deploy cycle for Excel-only changes (backend `mvn -pl jonlink-admin -am` + `systemctl restart jonlink.service`, no frontend rebuild needed) and the curl + xlsx header-parse recipe to verify changes actually landed in the exported file.
- `references/silent-template-failures-and-layout-flicker.md` — **Pitfall 42** (Vue 3 scoped-slot `<!---->` when `financeDict` helper is used without `import` — silent in production build; diagnosis: grep for import before debugging template) + **Pitfall 43** (`watchEffect` on `useWindowSize()` causing sidebar flicker + main-area stacking + the missing `display: flex` on `.app-wrapper`). The 4-check triage table for "I changed code and the page is broken" cluster.