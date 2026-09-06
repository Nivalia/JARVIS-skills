# Incremental M-Stage Rollout Pattern (M0 → M7) for adding a business module to a running admin

**Class of work**: adding a NEW business vertical (e.g. finance / HR / inventory / CRM) to an existing RuoYi-Vue3 fork (jonlink / plus / eladmin / etc.) WITHOUT taking the system offline or breaking existing modules. Validated end-to-end on JonLink's finance system rollout: 2026-08-19 → 2026-08-20, M0-M7 in 7 increments, zero downtime, zero regression.

## Why a "rolling M-stage" pattern

Naïve approach: build the entire feature in one branch, merge, deploy. Problems:
- Can't validate each layer independently — a DB schema bug blocks UI work, a UI bug blocks e2e
- Hard to roll back partially
- User has no visibility into progress until the very end
- mvn package and npm build each take 1-3 minutes; rebuilding the whole stack per iteration is wasteful

The M-stage pattern instead splits work into 7 stages with a clear deliverable + verification recipe per stage. Each stage compiles + runs + has a smoke test. Stages compose bottom-up: schema → core CRUD → engines → reports → UI → regression.

## The 7 stages (verified 2026-08-19/20 on JonLink finance)

### M0 — Schema + code-generator landing
**Deliverable**: 17 business tables created in DB; auto-generated CRUD classes (Service/Mapper/Controller/Domain/XML) landed in the right modules; menus + admin permissions seeded.

**Why first**: every later stage depends on the tables. The generator output gives you a free CRUD scaffold for each table — saving 200+ lines of boilerplate per table.

**Recipe**:
1. Create tables via SQL DDL (the existing system tables are `sys_*`, `wx_*`, `biz_*`; add a new prefix `fin_*` / `hr_*` / etc.). Use the SAME conventions: `bigint id`, `varchar(32) biz_no UNIQUE`, `char(1) status`, `create_by/create_time/update_by/update_time`, `remark`. MariaDB 10.11 / MySQL 8 both fine.
2. Open the admin web → System Tools → Code Gen (path `/tool/gen`). For each table: **Import** (form: `tplWebType=element-plus`, `tplCategory=crud`, `packageName=com.jonlink.system`) → edit display flags → **Generate Code** → downloads zip.
3. Unzip each table's generator output. Files to land:
   - `main/java/com/jonlink/system/{domain,mapper,service,service/impl}/*` → `jonlink-system/src/main/java/com/jonlink/system/{domain,mapper,service,service/impl}/`
   - `main/java/com/jonlink/web/controller/system/<FinXxx>Controller.java` → `jonlink-admin/src/main/java/com/jonlink/web/controller/system/` (NOT `jonlink-system` — see pitfall 38)
   - `vue/api/<module>/<business>.ts` → `JonLink-Vue3-TS/src/api/<module>/`
   - `vue/views/<module>/<business>/index.vue` → `JonLink-Vue3-TS/src/views/<module>/`
   - `<business>Menu.sql` → run against DB to register menus + 5 button perms
4. Run mvn package: confirm `BUILD SUCCESS` (no `ConflictingBeanDefinitionException`, no MyBatis errors).
5. Smoke test: login → hit `/<module>/<business>/list` with Bearer token → expect `code:200` even with `rows:[]`.

**Time**: ~3 hours for 17 tables if generator is healthy.

### M1 — Core CRUD with business logic
**Deliverable**: the FIRST business workflow (e.g. vouchers for finance, tickets for HR) end-to-end. State machine + validation + period close + minimal UI.

**Why second**: forces you to discover which generator-output is GOOD ENOUGH and which needs hand-extending. The generator gives CRUD; M1 adds the BRAIN.

**Recipe**:
1. Pick the simplest domain (vouchers are simpler than reimbursements). Add state machine fields + business validation methods to the auto-generated ServiceImpl.
2. Use `@Transactional(rollbackFor = Exception.class)` (RuoYi default) — but validate state BEFORE throwing (see pitfall 37).
3. Build a SIMPLE custom Vue page replacing the auto-gen's bulky 6-button toolbar. Frontend first-line pattern: `(row && row.id)` guards (pitfall 35), `@click="handler()"` parens (pitfall 40), no `.catch(() => {})` (pitfall 31).
4. mvn + npm + curl + browser e2e. Verify state machine transitions (e.g. 0→1→2→3 in order), debit/credit balance, period close.

**Smoke test**: create a voucher, post it, reverse it. Verify state transitions match the DB rows. Read the saved voucher from the DB directly via `mysql -e "SELECT * FROM fin_voucher ORDER BY id DESC LIMIT 3"` to confirm field mapping is right.

### M2 — Business engines (template-driven automation)
**Deliverable**: engines that consume templates + produce side-effects (e.g. voucher templates → posting → ledger log). The "automation layer" that connects business operations to the core ledger.

**Recipe**:
1. Create a `IFinXxxEngine` interface + `Impl` class. Read templates (`fin_voucher_template`), replace placeholders (`{downCommission}` → actual value), call `voucherService.saveWithEntries(...)`, write log.
2. Add `FinXxxController` endpoints for `book / unbook / listBySourceId`. Always wire perm prefix `finance:<x>:<op>` and add to `sys_menu` + admin role.
3. Duplicate-template protection via DB UNIQUE KEY on `uk_source (book_type, source_id)` — catch `SQLIntegrityConstraintViolationException` and rethrow as friendly `ServiceException`.
4. curl smoke each engine end-to-end. mvn package.

**Smoke test**: 5 templates × 1 source row each = 5 successful vouchers + 5 log rows. Try the same source twice → expect "该台账(X)已记账,不能重复" without rollback-only error (pitfall 37).

### M3 — Cross-domain operations (partner auto-create, settlement, etc.)
**Deliverable**: workflows that span multiple tables (e.g. ledger → partner auto-create → receivable → settlement).

**Recipe**:
1. Add `upsertByName` to partner service — "if exists, return id; if not, create and return id". One method, single transaction.
2. Settlement engine: read source (e.g. receivable), check amount, write settlement, update source `status`, write settlement log. Wrap in single `@Transactional`.
3. Browser e2e: confirm the cross-table side effects (e.g. partner row appears, receivable `status` flips from 0 to 1/2).

**Smoke test**: over-settlement rejection (try to settle 1000 when receivable is 100 → expect 400/500 with clear error). Under-settlement OK (partial settle).

### M4 — Money movement (accounts, receipts, payments, flows)
**Deliverable**: bank accounts + receipt/payment slips + automatic flow log + balance update.

**Recipe**:
1. Account table: `init_balance`, `current_balance`. Always pair — `current_balance = init_balance + SUM(receipts) - SUM(payments)` derived from flows, not stored. (Or store + reconcile.) 
2. Receipt: `confirm` action updates `account.current_balance` and writes a `flow` row with `direction` (1=in/0=out).
3. Over-payment rejection: check `payment.amount <= account.current_balance` before confirm.
4. Browser e2e: confirm receipt → balance goes up; confirm payment → balance goes down; over-payment blocked.

**Smoke test**: create account with 100000 init → confirm receipt 100 → balance 100100 → confirm payment 200000 → expect rejection. Verify flow log has 1 row per confirmed receipt/payment.

### M5 — Reports (read-only aggregations)
**Deliverable**: report endpoints + report pages that read-only aggregate over the existing tables.

**Recipe**:
1. Add `IFinReportService` interface — pure read, no writes.
2. Use `resultType="map"` for aggregate queries — but **declare an explicit `<resultMap>`** with the camelCase property mapping (pitfall 36 — the silent-list-collapse trap).
3. Endpoints: `/finance/report/subjectBalance` + `incomeStatement` + `balanceSheet` + `ledgerPerformance`. Each returns `{ rows: [...], totals: {...} }`.
4. Browser e2e: load report, verify numbers match `mysql -e "SELECT SUM(...) FROM fin_voucher WHERE period='2026-08'"`.

**Smoke test**: cross-check report total against `mysql` aggregate query. Mismatch = report bug.

### M6 — Subsidiary CRUD with computed fields (invoice + expense)
**Deliverable**: business documents that aren't core ledger but interact with it (e.g. invoices feed into expense claims). Often involves a master-detail pattern (one expense = N items).

**Recipe**:
1. Master-detail: one DB table for the master (`fin_expense`), another for the items (`fin_expense_item`), joined by `expense_id`. Always include `sort_order` in items for stable display.
2. **Extend the auto-gen controller in place** — do NOT create a sibling controller in `system.controller` (pitfall 38). Add `addWithItems(@RequestBody Map body)` that calls a custom `createWithItems` service method.
3. Verify mock: for "外部 API 核验" style endpoints, add a `verify` endpoint that does basic validation only (amount > 0, no real tax API call).
4. Browser e2e: master-detail dialog — add 3 items, change 1, delete 1, submit. Verify `totalAmount` on the master row = sum of item amounts.

**Smoke test**: item-only inserts (no master) should fail. Master-only insert (no items) should fail. Both present, totalAmount recomputed on submit.

### M7 — Regression test (原模块零破坏)
**Deliverable**: proof that the M0-M6 rollout did NOT break the existing system.

**Recipe** (the part users care about most):
1. Open dashboard (`/index` or equivalent). Verify all KPI cards render with the existing data shape.
2. Open each existing top-level menu (公众号管理 / 保险业务台账 / 系统管理 / 分销管理). Click each first-level child. Verify list pages render without 401/403/500.
3. For each existing page, click the top-bar 删除 button — verify Pitfall 32's `:disabled="multiple"` behavior is unchanged (button enabled only after ticking a row).
4. Real-browser e2e via `browser_navigate` + `browser_snapshot`. Don't rely on curl alone — many UI bugs don't surface in API responses.
5. No console errors: `browser_console {clear: true}` then navigate, then `browser_console` to read any errors.

**Smoke test**: take a real screenshot of dashboard + 1 page from each existing module. Archive under `backup/m7-smoke-<page>.png`.

**Backup at end of M7**:
```bash
mkdir -p /opt/<project>/backup
cp jonlink-admin/target/jonlink-admin.jar /opt/<project>/backup/jonlink-admin-m7.jar
cp -r JonLink-Vue3-TS/dist /opt/<project>/backup/dist-m7
mysqldump -uroot -p<pwd> <db> --single-transaction --triggers --routines > /opt/<project>/backup/<db>-m7.sql
ls -la /opt/<project>/backup/
```

## Cross-cutting rules (apply to every M-stage)

### 1. Package discipline
- **Services / Domain / Mapper**: `jonlink-system/src/main/java/com/jonlink/system/{service,service/impl,domain,mapper}/`
- **Controllers**: `jonlink-admin/src/main/java/com/jonlink/web/controller/system/` (NOT in `jonlink-system` — pitfall 38)
- **API wrappers**: `<admin-web>/src/api/<module>/<business>.ts`
- **Vue pages**: `<admin-web>/src/views/<module>/<business>/index.vue`

### 2. Build verification per stage
- After EVERY mvn package: `mvn package -DskipTests 2>&1 | grep -E "ERROR|BUILD SUCCESS" | tail -3` (must show BUILD SUCCESS)
- After EVERY npm build: `npm run build:prod 2>&1 | tail -5` (must show dist artifacts)
- After EVERY backend restart: `curl -s http://localhost:8080/captchaImage` (must return `code:200`)
- After EVERY nginx reload: `curl -sI http://localhost/` (must return 200)

### 3. curl smoke test per stage
```bash
TOKEN=$(curl -s -X POST http://localhost:8080/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"admin123"}' | jq -r .token)

# List the new module's resources
curl -s -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8080/<module>/<business>/list" | jq .total
# Expect: 0 (empty initial) or the seeded count

# Create + read + update + delete cycle
curl -s -X POST -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '<create body>' "http://localhost:8080/<module>/<business>"
```

### 4. Browser e2e per stage
- Navigate to `/<module>/<business>` with `?nocache=<stage-id>` (vite HMR may serve stale chunks)
- Verify list page renders + form/dialog opens
- Submit a real create + verify the row appears
- For state-machine endpoints, verify the transition buttons are correctly enabled/disabled per state

### 5. DB menu + permission seeding per stage
- New menus: INSERT into `sys_menu` with `parent_id` matching the parent module
- New perms: each controller endpoint's `@PreAuthorize` perm string (`<module>:<biz>:<op>`) must match a `sys_menu.perms` row
- admin binding: `INSERT IGNORE INTO sys_role_menu (role_id=1, menu_id=<new>)`
- Hard reload menu cache: re-login (the JWT carries the menu list)

### 6. Don't touch the existing system
**Hard constraint**: do not modify any existing `wx_*`, `biz_*`, `sys_*`, `jonlink_*` controllers/services/domains. New code lives in `fin_*` namespace. Generator produces same-namespace CRUD; that's fine because it's net-new tables, but if you find yourself wanting to extend an existing controller, STOP and add a NEW controller in `web.controller.system/` with a different perm prefix.

### 7. No backups by default
Per the user's no-backup-default preference (Pitfall 27), do not auto-create `.bak` files at every save. Backup only at the END of an M-stage (or the end of M7 final smoke test) into `/opt/<project>/backup/`.

## Verification recipe per stage (cumulative)

After M0:
```bash
mysql -uroot -p<pwd> <db> -e "SHOW TABLES LIKE '<prefix>_%'" | wc -l   # expect 17
curl -s -H "Authorization: Bearer $TOKEN" "http://localhost:8080/<module>/<business>/list" | jq .code   # expect 200
```

After M1-M6:
```bash
mysql -uroot -p<pwd> <db> -e "SELECT COUNT(*) FROM <master_table>"
# Should match the rows you created in browser e2e

curl -s -H "Authorization: Bearer $TOKEN" "http://localhost:8080/<module>/<business>/<id>" | jq .data.totalAmount
# Should match the value you submitted
```

After M7:
```bash
# Dashboard
curl -s http://localhost/ | head -c 200
# Each existing module's first page
for path in /system/user /wx/fan /ledger/insurance /finance/voucher; do
  curl -sI "http://localhost${path}" | head -1
done
# All should return 200
```

## What this pattern protects against

- **Premature optimization**: M1's "simple custom page replacing 6-button auto-gen" only emerges once you've felt the pain of the auto-gen's bloat. Skipping it = a UI that no one wants to use.
- **Engine complexity creep**: M2's engines are the highest-leverage code — done wrong, they cascade into M3-M6. Doing them as the second-toughest stage (after core CRUD) means you have the patterns to lean on.
- **Cross-table side-effect bugs**: M3 forces you to discover the partner/settlement pattern. Without it, M4's account flows become a tangled mess.
- **Report correctness**: M5's reports are read-only but trust-critical. A wrong total in a financial report is worse than no report.
- **Master-detail UX**: M6's master-detail pattern is the last non-trivial UX. Get it right and the rest is plain CRUD.
- **Regression**: M7 is the stage the USER cares about most. Skipping it = the user finds out 2 weeks later when they click on a page they hadn't touched.

## Time budget per stage (JonLink finance 2026-08-19/20)

| Stage | Hours | Output |
|---|---|---|
| M0 | ~3h | 17 tables + auto-gen CRUD landed |
| M1 | ~2h | core CRUD + state machine + UI |
| M2 | ~1.5h | 5 templates + engine + ledger log |
| M3 | ~1h | partner auto-create + settlement |
| M4 | ~1h | accounts + receipts/payments + flows |
| M5 | ~1h | 4 reports |
| M6 | ~0.5h | master-detail (expense + items) |
| M7 | ~0.5h | regression smoke test |

**Total**: ~10.5h for 17 tables, ~25 java files, ~15 vue files, ~40 endpoints. Per-stage granularity means you can stop after any stage with a working system.

## What this pattern does NOT cover

- Performance tuning (covered separately — `production-readiness`)
- HA / k8s / load balancing
- Security hardening beyond RuoYi's `@PreAuthorize` defaults
- Multi-tenant data isolation
- Audit log retention policy
- Migration tooling (e.g. Liquibase / Flyway)

These are concerns for the deployment / production-readiness phase, not the rollout phase.