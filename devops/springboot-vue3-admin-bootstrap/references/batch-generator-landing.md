# Batch code-generator landing (10-20 tables in one go)

Full end-to-end recipe proven on jonlink (18 business tables, RuoYi-Vue3, Spring Boot 4). Use when the admin UI already has a full menu tree but the pages 404 because generated code was never landed.

## When to use
- Generator tables already imported (`gen_table` has rows) but backend/frontend code not in the source tree.
- sys_menu already has business menus (2000+ range) but `component` points at non-existent views.
- User expects: click every menu → page renders, list API returns 200.

## 0. Backup (always first)
```bash
BK=/opt/jonlink-backup/gen-handoff-$(date +%Y%m%d%H%M)
mkdir -p $BK
docker exec jonlink-mysql mysqldump -uroot -p$PWD jonlink gen_table gen_table_column sys_menu > $BK/db_backup.sql
cp /proc/<backend-pid>/fd/4 $BK/jonlink-admin.jar.old   # running jar via open fd
```

## 1. Get the generated zip via API (no UI needed)
```python
import subprocess, json
TOKEN = json.loads(subprocess.run(['curl','-s','-H','Content-Type: application/json',
    '-d','{"username":"admin","password":"admin123"}',
    'http://localhost:8080/login'],capture_output=True,text=True).stdout)['token']
tables = 'jl_apply_record,jl_channel,...'   # comma-joined, 18 tables
r = subprocess.run(['curl','-s','-o','/tmp/gen.zip',
    '-H',f'Authorization: Bearer {TOKEN}',
    f'http://localhost:8080/tool/gen/batchGenCode?tables={tables}'], capture_output=True, text=True)
```
Zip layout: `main/java/com/jonlink/system/{controller,domain,mapper,service,service/impl}/JlXxx.java` + `main/resources/mapper/system/JlXxxMapper.xml` + `vue/api/system/{biz}.js` + `vue/views/system/{biz}/index.vue` + `{biz}Menu.sql`. Expect 162 files for 18 tables (90 java + 18 xml + 18 vue + 18 js + 18 sql).

## 2. Land backend
```bash
GEN=/path/to/extracted; SRC=/opt/jonlink/backend/jonlink-system/src/main
cp -r $GEN/main/java/* $SRC/java/
cp -r $GEN/main/resources/* $SRC/resources/
```
Verify: `find $SRC -name "Jl*.java" | wc -l` should be ~90. (Note: `find -name "Jl*.java"` via shell glob can under-count if invoked through some executors — use explicit `find ... | sort`.)

## 3. Land frontend + fix collisions BEFORE compile
```bash
cp $GEN/vue/api/system/*.js /opt/jonlink/admin-web/src/api/system/
cp -r $GEN/vue/views/system/* /opt/jonlink/admin-web/src/views/system/
```
THEN check for overwritten RuoYi originals (pitfall 23):
```bash
cd admin-web && git status --short src/api/system/ src/views/system/
git checkout -- src/api/system/config.js src/api/system/notice.js \
                src/views/system/config/index.vue src/views/system/notice/index.vue
```
And rename any `/system/config` → `/system/goodsconfig`, `/system/notice` → `/system/jlnotice` collisions (pitfall 21) — backend controller + api js + views dir together.

## 4. Align sys_menu to generated files (pitfall 22)
Do NOT run the `{biz}Menu.sql` files when menus already exist. Instead:
```sql
UPDATE sys_menu SET component='system/{biz}/index' WHERE menu_id=<C-menu-id>;
UPDATE sys_menu SET perms='system:{biz}:query' WHERE menu_id=<F-button-id>;  -- match Controller @PreAuthorize EXACTLY
INSERT IGNORE INTO sys_role_menu (role_id, menu_id) SELECT 1, menu_id FROM sys_menu WHERE menu_id >= 2071;
```
Tables whose code was generated but have NO menu row (e.g. jl_notice, jl_export_task, jl_insurance_company, jl_renewal_operation) need new C menus + F buttons INSERTed and role-bound.

## 5. Compile + fix generator bugs
`mvn -q clean package -DskipTests` → likely compile errors from velocity bugs in Domains (pitfall 20: `readConverterExp` corruption, `$column` placeholders). Batch-fix all `domain/Jl*.java`, rebuild.

## 6. Restart + verify
```bash
# stop old jar (by PID, not pkill -f java), start new:
java -Duser.timezone=Asia/Shanghai -Xms512m -Xmx1024m -jar /opt/jonlink/backend/jonlink-admin/target/jonlink-admin.jar &
# restart admin-web vite (import.meta.glob needs restart to see NEW vue dirs)
```
Verification checklist (all must pass):
1. `GET /getRouters` (Bearer) → walk tree; every C menu `component` exists under `src/views/`.
2. `GET /system/{biz}/list` for all 18 → `code:200` (empty tables return `total:0`, not error).
3. POST a test row → list shows it → DELETE it (keep DB clean).
4. Unauthenticated API call → body `code:401` (RuoYi returns HTTP 200 with code=401; that's correct, frontend interceptor handles it).
5. SPA routes (`/insure/products`, `/order/list`, `/dashboard/index`, ...) → HTTP 200 (SPA shell; real render needs browser).

## Gotchas observed
- `batchGenCode` needs `Authorization: Bearer` header; plain `Admin-Token` may 401 on some RuoYi forks.
- jl_notice/jl_export_task/jl_insurance_company/jl_renewal_operation generated fine but had no menus — audit `gen_table` vs `sys_menu` C-menus to find orphans.
- Dashboard/data-screen menu (`/dashboard/index`) points at a view that doesn't exist in stock RuoYi — create `src/views/dashboard/index/index.vue` (stats cards hitting the list APIs + placeholder charts) or 404.
- Multi-menu same-table: 保单详情+保单查询 both → `system/policy/index`; 批改 3 pages → `system/order/index`. Acceptable (same list page, different perms).
