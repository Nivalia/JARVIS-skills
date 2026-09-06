# Pitfall 46, 47, 48 — Menu path/component mismatch, "claimed complete" verification protocol, and build-the-fs-first rule

**Origin**: validated 2026-08-22 on the jonlink 政策展示模块 M0-M2 task. After the backend finished, mvn package succeeded, the frontend rebuilt, all 11 controller endpoints returned 200, the user pointed out "M2 还没完成?" — and the actual bug was in the **sys_menu row** for the view page, not in any code or build. The 4-layer verification protocol in this file catches that class of bug in 5 seconds for any future module.

## Pitfall 46 — Menu row `path` and `component` mismatch → joined URL points to a non-existent fs path

**Symptom**: A new `sys_menu` row was added for a "view" page under a parent module menu. The Vue file exists at e.g. `src/views/policy-view/index.vue`. `vite build` succeeds. The dist chunk is present. `mvn package` succeeds. `/getRouters` returns the row. The user clicks the menu → **blank page or vue-router 404**. Looks like a routing bug, vite build issue, or framework bug. None of those.

**Why this traps you**:
- `sys_menu.path` (URL segment) and `sys_menu.component` (Vue fs path under `views/`) are **two independently derived strings** in the SQL row
- Vue-router's dynamic-route registration joins them as `<parent.path>/<child.path>`
- Frontend `loadView(component)` resolves `component` → `views/<component>.vue`
- If `path` and `component` don't share the same directory prefix, the URL the user lands on (parent.path + child.path) doesn't match the registered route (whose component resolves from a different directory)

**Wrong → right example** (real jonlink 2026-08-22 fix):

```sql
-- ❌ WRONG: parent.path='policy', child.path='view'
--          component='policy-view/index'
--          joined URL '/policy/view' → fs views/view/index.vue (404)
INSERT INTO sys_menu(menu_id, menu_name, parent_id, path, component, ...)
VALUES(2503, '政策查看', 2500, 'view', 'policy-view/index', ...);

-- ✅ RIGHT: child.path mirrors the component prefix
--          joined URL '/policy/policy-view' → fs views/policy-view/index.vue
INSERT INTO sys_menu(menu_id, menu_name, parent_id, path, component, ...)
VALUES(2503, '政策查看', 2500, 'policy-view', 'policy-view/index', ...);
```

| `parent.path` | `child.path` | `child.component` | Joined URL | Vue fs path | Status |
|---|---|---|---|---|---|
| `policy` | `policy-view` | `policy-view/index` | `/policy/policy-view` | `views/policy-view/index.vue` | ✅ |
| `policy` | `category` | `policy/category/index` | `/policy/category` | `views/policy/category/index.vue` | ✅ |
| `policy` | `view` | `policy-view/index` | `/policy/view` | `views/view/index.vue` (404) | ❌ |

**Detection** — run after EVERY new sys_menu row:

```bash
mysql -uroot -p<pwd> <db> -e "
  SELECT m1.path AS parent_path, m2.menu_name AS child,
         m2.path AS child_path, m2.component
    FROM sys_menu m1
    JOIN sys_menu m2 ON m2.parent_id = m1.menu_id
   WHERE m2.component IS NOT NULL AND m2.component <> '' AND m2.menu_type='C'
   ORDER BY m1.menu_id, m2.menu_id;"
```

For each row: compute `<parent.path>/<child.path>` and compare to `<component>` prefix. They must agree. If not, fix the path.

**Fix** — single SQL UPDATE, no rebuild needed:

```sql
UPDATE sys_menu SET path='<correct-prefix>' WHERE menu_id=<X>;
```

Have the user **log out + log back in** to refresh `/getRouters` cache.
No backend rebuild (rows read live from MySQL).
No frontend rebuild (the Vue file location doesn't change — only the URL path).

**Why this trap is silent and demoralizing**: `mvn package` exits 0, `vite build` exits 0, `getRouters` returns the row, vue-router registers the route, the URL joins correctly in the matcher. BUT the URL the user clicks doesn't match the registered route's derived URL because **two SQL strings (path and component) went out of sync**. No curl/200/POST/GET endpoint exposes this — the API layer is fine. Only live browser navigation catches it.

**Sibling traps**: Pitfall 38 (duplicate controller bean name → ConflictingBeanDefinitionException on the Java ↔ Spring side), Pitfall 45 (sys_menu middle parent has component='Layout' instead of NULL → nested Layout). Both are "two same-name things in two places produce silent failure at the bridge". Pitfall 46 is the third instance of this class: SQL URL-path mismatch with fs path.

## Pitfall 47 — The 4-layer "claimed complete" verification protocol

When a multi-stage task feels "done" but the user might still find a hidden gap, run this **once before reporting completion**:

### Layer A — backend smoke
`curl` every controller endpoint exposed by the new module, expected `code:200` with non-empty data. Auth-tokenized requests, mixed-method endpoints (POST/PUT/DELETE/GET), edge cases (delete with children, upload empty file, version restore with missing version).

### Layer B — production-shape compile
`mvn -pl <admin> -am package -DskipTests`. Not just `compile` — the `package` phase runs `spring-boot:repackage` which builds the fat jar including shade plugin transformations (custom encryptors / AES keys / deserialization filters from `jonlink-common`). `compile`-OK can fail at `package` time. Don't report "ready to run" based on `compile`.

### Layer C — frontend production build
`vite build` (not `vite dev`). Production build enforces type checks the dev server lazily skips. Dev-server-OK can fail at `vite build` due to TypeScript strictness, dead-code elimination, or chunk size limits. Verify the dist directory contains every new page as a chunk or merges into the main chunk with the expected feature string.

### Layer D — db↔vue-router agreement
The Pitfall 46 SQL detection, run for every new menu row. Cross-check no broken joined URLs. **Run before** Layer A's e2e if the page doesn't render.

### Optional Layer E — real browser e2e
Open the page in a real browser, click every new menu, observe navigation, observe toast feedback. Catches the dozen "works in curl, blank in browser" failures that A/B/C/D miss (Pitfall 35, 31, 40).

**The trap**: it's tempting to declare "M2 complete" once layers A+B+C pass, because the backend rebuild succeeded, the frontend build succeeded, all 11 endpoints return 200. But layer D (sql path/component agreement) catches the class of bug where the menu row was written with mismatched strings. Always run layer D before reporting completion of a new business module task.

**Why this protocol matters**: the jonlink 2026-08-22 政策展示模块 M2 task had layers A+B+C all pass. The user pointed out "M2 还没完成?" — and the actual bug was layer D: the menu_id=2503 row had `path='view'` while `component='policy-view/index'`.
- A: curl /policy/view/current/X returns 200 — controller works
- B: mvn package succeeds — Java unchanged
- C: vite build succeeds — Vue unchanged
- only D (SQL data shape) was wrong, and only live browser navigation exposed it

5 seconds for layer D's query vs hours of "why is the page blank" debugging.

## Pitfall 48 — Build the SQL `path` from the fs prefix, not from the URL you want

**Counter-rule** to Pitfall 46 — the correct mental model for the author:

When adding a new business module page, **write the Vue file FIRST**, then derive `path` from the file's directory prefix. Don't write the Vue file in one folder and the SQL `path` in another, then wonder why the URL is wrong.

```bash
# 1. Decide the fs layout (this is the source of truth)
mkdir -p src/views/<module>/<page>
# This is now:    views/<module>/<page>/index.vue

# 2. The component string in sys_menu MUST be:
component='<module>/<page>/index'
# (loadView(component) → views/<module>/<page>/index.vue)

# 3. The child path MUST mirror the same directory prefix:
path='<module>/<page>'
# (vue-router joins parent.path + child.path → /
# and the result's resolved component directory = the URL = the fs path)
```

**Why directory-first**: the file system is harder to rename than the SQL row. Build the file layout, then write the SQL to match. Don't try to compromise between an aesthetic URL and the fs layout — they must agree.

**Counter-example (the jonlink 2026-08-22 mistake)**: Vue file at `views/policy-view/index.vue`, `component='policy-view/index'`, then because `/policy/policy-view` looked ugly, set `path='view'`. Now URL `/policy/view` doesn't match fs `views/policy-view/`. The aesthetic-driven SQL choice broke the navigation. Always make the SQL row match the fs layout, not the other way around.

**Clean URL alternative**: if `/policy/policy-view` is genuinely ugly, the fix is to **rename the fs directory** to match a desired URL. `views/policy/view/index.vue` with `path='view'` and `component='policy/view/index'` works and is honest about the URL. Don't take shortcuts that decouple SQL from fs.
