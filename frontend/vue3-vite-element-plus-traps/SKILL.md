---
name: vue3-vite-element-plus-traps
description: "Vue 3 + Vite frontend pitfalls."
---

# Vue 3 + Vite + Element Plus — Frontend Traps During Feature Work

The RuoYi-Vue3 (and any fork — vue-element-plus, jonlink-Vue3-TS, etc.) + Vite + Spring Boot stack has a class of bugs that **pass `vite build` cleanly, render an empty / broken page**, and are invisible to curl. This skill captures the patterns and the browser verification recipes that catch them.

The unifying lesson: **a successful `vite build` is NOT proof the feature works.** Always verify in the browser after every edit, not just confirm HTTP 200 from curl.

---

## Trap 1 — Local variable named `h` silently shadows the Vue `h` render function

**Symptom**: After adding a SVG-based render-function component (e.g. for a placeholder document card), the page renders empty / `main` is blank. Console shows:

```
TypeError: h is not a function
```

**Why**: In Vue 3 `<script setup>` / defineComponent, you import `h` from `'vue'`:

```ts
import { ref, computed, defineComponent, h } from 'vue'
```

Then inside a setup() function you write render JSX like:

```ts
setup(props, { emit }) {
  return () => {
    const w = props.main ? 1600 : 600
    const h = props.main ? 900 : 450   // ← local const 'h' shadows module 'h'!
    return h('div', { ... })             // ← throws: this h is a number 900
  }
}
```

The `const h = props.main ? 900 : 450` line **re-declares** a local `h` that shadows the imported Vue render function for the rest of that block. By the time you call `return h('div', …)`, `h` is the number 900, not the render function.

**Fix**: rename the local variable (e.g. `height` / `ph` / `px`) AND/OR use a clear alias for Vue's `h`:

```ts
import { ref, computed, defineComponent, h as vueH } from 'vue'

setup(props, { emit }) {
  return () => {
    const w = props.main ? 1600 : 600
    const height = props.main ? 900 : 450
    return vueH('div', { ... })
  }
}
```

The error is a clear `TypeError: h is not a function` — easy to catch with browser console. Hard to find if you only trust `vite build`.

**Verification recipe**:

```bash
# 1. Watch browser console for uncaught exceptions after every render-function edit
# 2. If main/main area is empty, immediately check:
grep -n 'const h =' src/App.vue   # anything that matches is the bug
# 3. fix + rebuild + reload
```

---

## Trap 2 — Dynamic routes from `/getRouters()` make `/<module>/<page>` a 404 on direct URL

**Symptom**: The menu `联系人管理` is visible in the sidebar and clicking it works. But navigating directly to `http://host/<module>/<page>` shows the SPA's 404 page (or a white page). Logout/login doesn't help.

**Why**: In RuoYi-Vue3 / its forks, the sidebar menu is dynamically built by `getRouters()` which pulls `sys_menu` rows joined with their `component`. The router is augmented via `router.addRoute(...)` after login. **The router only knows the routes that were returned for the current role's JWT session.**

But the SPA's catch-all 404 handler is **also** registered. So:
- Sidebar click → router resolves the dynamic route → page renders
- Hard URL `/<module>/<page>` → router doesn't find it (because it was added by `addRoute` AFTER `router.onReady` fired) → falls through to 404

**The fix is verification: always navigate from the sidebar**, or click a menu link. If you must deep-link, log out + log back in first so `getRouters()` re-runs.

**Detection recipe**:

```bash
# In browser devtools console, after a 404 page:
JSON.stringify(window.location.pathname, null, 2)
# click around the sidebar menu and see if the page exists in the menu tree.
# It's not a build bug — it's a router-discovery ordering issue.
```

**Alternative**: stock RuoYi-Vue3 ships with all standard module routes already in `src/router/modules/*.ts`. Project-added modules (like a custom ledger / finance / contact module) won't be there — they live only in `sys_menu`. That's why direct URLs fail but sidebar links work.

---

## Trap 3 — `mv dist /tmp/backup` then `cp dist.new dist` fails because `dist.new` doesn't exist

**Symptom**: After `vite build` you want to swap the new dist in place but keep a backup. You run:

```bash
mv /opt/project/dist /tmp/backup-$(date +%s)
ls /opt/project/dist    # ← does not exist! vite can't write here next time
```

Now if you try to `cp -r .next dist` or run `vite build` again, the rebuild either fails silently or recreates an empty dist because the source `vite build` output already landed somewhere else (`dist/` is the default).

**The robust sequence** is:

```bash
# 1. Confirm dist exists and check the hash of the current production JS
ls /opt/project/dist/static/js/index-*.js
NEW_HASH=$(ls /opt/project/dist/static/js/index-*.js | head -1)
echo "current prod JS: $NEW_HASH"

# 2. Move it ASIDE (in place rename, atomic)
mv /opt/project/dist /opt/project/dist.bak.$(date +%s)
# Note: dist.bak.<ts> is OUTSIDE the vite write target

# 3. Build — vite creates a fresh dist/
cd /opt/project && npx vite build

# 4. Reload browser with hard refresh (Cmd+Shift+R / Ctrl+Shift+F5)
#    — verify the new hash is in the served HTML
curl -sS http://host/ | grep -E 'index-[A-Za-z0-9_-]+\.js'
```

**Never** move dist aside and then try to `cp dist.new dist` — if your build step is `vite build`, there's never a `dist.new`. Always let vite regenerate, don't manually copy.

**Detection**: the symptom is "page reload still shows old hash" even though `ls dist` shows fresh files. That means your `mv` succeeded but the deploy step that should swap files (often a manual `cp -r`) ran first or moved files into a sub-path. Re-check the sequence.

---

## Trap 4 — Element Plus `el-form--inline` with a long label-width → label truncated to 2 lines, button pushed to row 2

**Symptom**: On a CRUD page (e.g. `联系人管理`, `渠道/业务员`, `险种管理`), the search form looks broken:
- Label `联系人姓名` is rendered as `联系人姓\n名` (label width too narrow, label wraps)
- The `搜索` / `重置` buttons are pushed to a second row
- The whole search area feels bloated and ugly

**Why**: Three compounding issues:

1. **`label-width="68px"` is too narrow for Chinese 4-character labels** — 4 Chinese chars × 14px ≈ 56-60px PLUS the colon / spacing → exceeds 68px and wraps.
2. **Default `el-input` width is auto** — Vue 3 Element Plus `el-input` defaults to a wide width that consumes the available form width, leaving no room for buttons.
3. **`el-form-item` margin + auto input width** — three wide items + spacing > available width → wrap to next line, pushing buttons out.

The user's verbatim complaint is "出现了 2 行字段" (the field shows as 2 lines).

**Fix — proven pattern** (lift from any one page and apply across the module):

```vue
<el-form :model="quejlParams" :inline="true" v-show="showSearch"
         label-width="70px" class="jl-search-form">
  <el-form-item label="姓名" prop="contactName">
    <el-input v-model="quejlParams.contactName"
              placeholder="联系人姓名" clearable @keyup.enter="handleQuery" />
  </el-form-item>
  <el-form-item label="电话" prop="phone">
    <el-input v-model="quejlParams.phone"
              placeholder="联系电话" clearable @keyup.enter="handleQuery" />
  </el-form-item>
  <el-form-item label="状态" prop="status">
    <el-select v-model="quejlParams.status" placeholder="全部" clearable
               class="jl-select-status">
      <el-option v-for="dict in jonlink_enable_disable" :key="dict.value"
                 :label="dict.label" :value="dict.value" />
    </el-select>
  </el-form-item>
  <el-form-item class="jl-form-actions">
    <el-button type="primary" icon="Search" @click="handleQuery">搜索</el-button>
    <el-button icon="Refresh" @click="resetQuery">重置</el-button>
  </el-form-item>
</el-form>

<style scoped>
.jl-search-form :deep(.el-form-item) {
  margin-right: 16px;
  margin-bottom: 12px;
}
.jl-search-form :deep(.el-form-item .el-input),
.jl-search-form :deep(.el-form-item .el-select) {
  width: 180px;
}
.jl-search-form :deep(.jl-select-status.el-select) {
  width: 120px;
}
.jl-search-form :deep(.el-input__wrapper) {
  border-radius: 8px;
  box-shadow: 0 0 0 1px var(--el-border-color) inset;
  transition: box-shadow 0.18s ease;
}
.jl-search-form :deep(.el-input__wrapper:hover) {
  box-shadow: 0 0 0 1px var(--el-color-primary) inset;
}
.jl-search-form :deep(.el-input.is-focus .el-input__wrapper) {
  box-shadow: 0 0 0 1px var(--el-color-primary) inset, 0 0 0 3px rgba(64, 158, 255, 0.12);
}
.jl-search-form :deep(.el-form-item__label) {
  font-size: 13px;
  color: #606266;
  font-weight: 500;
  padding-right: 8px;
  white-space: nowrap;   /* prevent the truncation the user complained about */
}
.jl-search-form :deep(.el-input__inner) {
  height: 32px;
  line-height: 32px;
  font-size: 13px;
}
.jl-search-form :deep(.jl-form-actions .el-button) {
  height: 32px;
  padding: 0 14px;
  font-size: 13px;
  border-radius: 8px;
}
.jl-search-form :deep(.jl-form-actions .el-button + .el-button) {
  margin-left: 8px;
}
.jl-search-form :deep(.el-form-item__content) {
  line-height: 32px;
}
</style>
```

**Key changes vs the RuoYi generator default**:
- Label text shortened (`联系人姓名` → `姓名`, `联系电话` → `电话`)
- `label-width="70px"` instead of `68px` (covers 4-character Chinese labels comfortably without overflow)
- Placeholder text shortened
- Status select: `120px` (was 200px default)
- Input: `180px` (was auto)
- `white-space: nowrap` on label explicitly prevents the "联系人姓\n名" two-line wrap
- Buttons: 32px height + 8px radius to match input
- Hover/focus: subtle primary inset glow (matches the rest of the app)

**Detection recipe** (when the user complains about a search bar looking ugly):

```bash
# 1. Open the page in browser
# 2. browser_console eval:
JSON.stringify(Array.from(document.querySelectorAll('.el-form-item__label')).map(el => ({
  text: el.textContent,
  w: el.offsetWidth, h: el.offsetHeight
})))
# 3. If h > 32 → label is wrapping → label-width too narrow OR text too long
# 4. If formItems sit at top=104 vs top=154 → buttons pushed to row 2
# 5. Either fix labels and/or apply the jl-search-form style block above
```

**Apply across a module**: if the user expresses approval of one polished page, grep other files in the same module and apply the same `:class="jl-search-form"` wrapper + style block:

```bash
grep -rl '<el-form :model=' src/views/ledger/ | head -10
# every match is a candidate for the same polish
```

---

## Trap 5 — Vue template auto-import doesn't extend to `<script setup>` (ReferenceErrors not caught by `vite build`)

**Symptom**: Click a CRUD toolbar button → dialog never opens. Console shows `ReferenceError: parseTime is not defined` (or `useDict`, `proxy.$modal`, etc.).

**Why**: in Vue 3 `<template>`, Vue's compiler auto-hoists helpers used in templates. So `{{ parseTime(row.date, '{y}-{m}-{d}') }}` works without an explicit import in `.vue` files. But `<script setup>` does NOT auto-import. A `reset()`, `watch()`, `computed()`, or handler that calls the same helper throws `ReferenceError` → the component is marked broken → its entire subtree (including `<el-dialog>`) is never mounted.

**Fix is one line**: `import { parseTime } from "@/utils/jonlink"` (NOT `@/utils/jonlink` — RuoYi-Vue3's default path is the jonlink-renamed variant in forks).

**`vite build` does NOT catch this** — ReferenceErrors surface only at runtime. Always check browser console after `<script>` edits.

---

## Trap 6 — `@click="handler"` injects MouseEvent as first arg when handler takes `row`

**Symptom**: clicking toolbar button reads `row.batchNo` as undefined → shows misleading "缺少批次号" or opens an empty form.

**Why**: Vue binds `@click="handler"` (no parens) to pass `MouseEvent` as arg 1. If `function handler(row)` exists with required `row`, you get a `MouseEvent` standing in.

**Fix**: `@click="handler()"` (with empty parens, no event pass). Affects every generated RuoYi CRUD page; one audit found 26 files / 49 occurrences.

---

## Trap 7 — `component` field on `sys_menu` row must not be empty

**Symptom**: After `INSERT INTO sys_menu` for a new top-level module + `sys_role_menu` grant, the menu does not appear in the sidebar — even though backend restarted and permissions are right.

**Why**: `filterAsyncRouter()` calls `loadView(componentStr)`; if the value is null or empty, the route is silently dropped.

**Fix**: every top-level `sys_menu` row that renders a real page must have a non-null `component` matching an existing `.vue` file.

**Verify**: `SELECT menu_id, menu_name FROM sys_menu WHERE component IS NULL OR component = '';` — any rows are menu entries that won't render.

---

## Trap 8 — `vue-tsc` `noImplicitAny` flags array callback params even when the array is typed `ref<T[]>`

**Symptom**: `vue-tsc --noEmit` reports e.g.

```
src/views/wx/user/index.vue(603,43): error TS7006: Parameter 'ut' implicitly has an 'any' type.
```

on every line that does `userTags.value.filter(ut => …)` / `.map(ut => …)` / `.some(ut => …)`, **even though** `userTags` is declared `ref<UserTagItem[]>([])` with a fully typed item interface.

**Why**: vue-tsc / TypeScript's inference through `.filter` / `.map` / `.some` on a `Ref<T[]>` whose value is `UserTagItem[]` is reliable in most positions — but the moment any *intermediate* step (e.g. `userTags.value = (row && row.tags) || []` where `row.tags` is `any[]`) reassigns the ref with an `any[]`-tainted value, downstream callbacks lose their inferred item type. Subsequent `.filter(ut => …)` then needs an explicit `(ut: UserTagItem)` annotation, otherwise strict `noImplicitAny` fires 5+ times on the same file.

The trap is not "declare the interface" (you did). It's "any sub-expression that touches an `any[]` propagates back through the type of the ref's value and breaks inference on the *next* `.filter`".

**Fix**: annotate the callback parameter explicitly. Don't fight the inference, just type the param.

```ts
// ❌ ut is implicit any after userTags.value = (row && row.tags) || []
userTags.value.filter(ut => ut.tagId !== tag.tagId)

// ✅ annotate
userTags.value.filter((ut: UserTagItem) => ut.tagId !== tag.tagId)

// ✅ also cast the assignment to keep the ref's type intact
userTags.value = ((row && row.tags) || []) as UserTagItem[]
```

**Detection recipe**:

```bash
# Run vue-tsc on the edited file only (or whole project, fast enough)
./node_modules/.bin/vue-tsc --noEmit 2>&1 | grep -E "error TS7006|index\\.vue"
# any TS7006 line on a .vue file is the pattern
```

**Important**: TS7006 errors are project-relative — if the project already has hundreds of pre-existing TS errors, grep for **delta from the last green baseline** rather than total count. A new error in your edited file is the signal.

---

## Trap 9 — `<el-date-picker type="daterange" value-format="YYYY-MM-DD">` sends strings; backend `Date` field → MyBatis "invalid comparison: Date and String" 500

**Symptom**: frontend date-range query for `/list?subscribeTimeBegin=2026-01-01&subscribeTimeEnd=2026-12-31` returns `500 invalid comparison: java.util.Date and java.lang.String`. All other (non-date) filters work. Backend mapper XML looks correct (`and subscribe_time >= #{subscribeTimeBegin}`).

**Why**: Element Plus `el-date-picker` with `value-format="YYYY-MM-DD"` serializes the chosen range into `string[]` on the wire. Spring MVC binds the query param to `WxMpUser.subscribeTimeBegin` — if the field is declared `Date`, Spring's binding either fails silently or sets it to `Date("2026-01-01")` parsed in server TZ. MyBatis then sees the parameter as `Date` and refuses to compare with a date column expression `subscribe_time >= #{...}` because the JDBC driver / MySQL parameter type doesn't match the column type — and the error surfaces as a mybatis-level `IllegalArgumentException`, not a Spring binding error.

**Fix — pick the path of least surprise**:
1. **Frontend sends string, backend field is `String`, mapper compares via `date_format()`** (recommended for date-range search fields):
   ```xml
   <if test="subscribeTimeBegin != null and subscribeTimeBegin != ''">
     and date_format(subscribe_time, '%Y-%m-%d') &gt;= #{subscribeTimeBegin}
   </if>
   ```
   ```java
   // Domain field — String, not Date
   private String subscribeTimeBegin;
   ```
   Tradeoff: can't use the field for output serialization / `@JsonFormat`. But for query-only fields this is the cleanest path.

2. **Field stays `Date`, use `<bind>` to format in mapper**:
   ```xml
   <bind name="_beginStr" value="subscribeTimeBegin != null ? new java.text.SimpleDateFormat('yyyy-MM-dd').format(subscribeTimeBegin) : null" />
   ```
   ```xml
   <if test="_beginStr != null and _beginStr != ''">
     and date_format(subscribe_time, '%Y-%m-%d') &gt;= #{_beginStr}
   </if>
   ```
   Tradeoff: more mapper noise, but keeps Domain field `Date` for output serialization.

**Detection recipe**:

```bash
# 1. Hit the affected endpoint with curl, force the date param
curl -s "http://host/api/list?subscribeTimeBegin=2026-01-01&subscribeTimeEnd=2026-12-31" \
  -H "Authorization: Bearer $TOKEN"
# 2. If response body contains:
#    "invalid comparison: java.util.Date and java.lang.String"
# 3. Field is Date in domain, value-format is YYYY-MM-DD in frontend → apply fix
```

Don't waste a build cycle trying to convert the string at the controller boundary — by then the `Date` field has been bound and the comparison has already failed inside MyBatis.

---

## Combined verification recipe after any frontend edit

```bash
# 1. Rebuild — does NOT prove the feature works
cd /opt/<project>/<frontend>
nohup npx vite build > /tmp/build-$(date +%s).log 2>&1 &
# (background + notify_on_complete, or just wait synchronously with a generous timeout)

# 2. Confirm new bundle hashes are in dist/
NEW_JS=$(ls dist/static/js/index-*.js | head -1)   # or dist/assets/ for vite < 5
NEW_CSS=$(ls dist/static/css/index-*.css | head -1)
echo "new JS=$NEW_JS  CSS=$NEW_CSS"

# 3. Confirm the served HTML or static files reference the new hash
curl -sS http://host/ | grep -E 'index-[A-Za-z0-9_-]+\.js'

# 4. In the browser:
#    a) Hard reload (Ctrl+Shift+F5 / Cmd+Shift+R) to bust cache
#    b) Open console — look for ReferenceError, TypeError
#    c) Click the feature you edited — observe real behavior
#    d) For CRUD pages: navigate via sidebar (Trap 2) not deep URL

# 5. After sys_menu INSERTs: log out, log in again, then look.
```

**Curl alone is never enough**. ReferenceErrors, Vue render-function crashes, missing-menu cases, label-width truncation — none of them change HTTP status from 200 to non-200.
