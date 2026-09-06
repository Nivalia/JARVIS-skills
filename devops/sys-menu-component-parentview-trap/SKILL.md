---
name: sys-menu-component-parentview-trap
description: "sys_menu middle parent component must be NULL."
---

# Pitfall: `sys_menu.component='Layout'` on middle parent menus → 2 sidebars

## Symptom (visual + DOM-level)
- **User-visible**: "页面出现了 2 次侧边栏菜单" / "框架错位" / "侧边栏闪现"
- **DOM truth**:
  ```js
  document.querySelectorAll('.app-wrapper').length       // 2
  document.querySelectorAll('.main-container').length    // 2
  document.querySelectorAll('.sidebar-container').length // 2
  document.querySelectorAll('.navbar').length            // 2
  ```
- `element_count` in `browser_snapshot` a11y tree is roughly 2× the correct value (140 vs 80; 158 vs 98)
- `browser_vision` may *say* "1 sidebar" because the inner sidebar is rendered on top of the outer with the same content — do **not** trust vision alone

## Root cause
JonLink / RuoYi `getRouters` returns a tree like:
```
Finance       → component="Layout"      (root, full chrome: sidebar + navbar + main)
├── Report    → component="ParentView"  (middle, pure <router-view/> container)
│   └── SubjectBalance → "finance/report/subjectBalance"
├── Core      → component="ParentView"
└── ...
```
The mapping rule (backend `SysMenuServiceImpl`):
```java
public boolean isParentView(SysMenu menu) {
    return menu.getParentId() != 0 && menu.getMenuType().equals("M");
}
// In getRouters → if StringUtils.isEmpty(menu.component) && isParentView(menu) → "ParentView"
```
**Three and only three valid `component` values**:
| Menu position | DB `component` field | What `getRouters` returns | Frontend component |
|---|---|---|---|
| Root (`parent_id=0`, `menu_type=M`) | `'Layout'` | `'Layout'` | `Layout` (full chrome) |
| Middle parent (`parent_id!=0`, `menu_type=M`) | **NULL** | `'ParentView'` | `ParentView` (just `<router-view/>`) |
| Leaf (`menu_type=C`) | `'path/to/xxx/index'` | `'path/to/xxx/index'` | `loadView(component)` |

**If a middle parent gets `component='Layout'`** (manually written or migrated wrong), `getRouters` returns `'Layout'` for it. `permission.ts filterAsyncRouter` maps `'Layout'` → `Layout` component. `vue-router 4` `addRoute` then registers both `Finance` and `Report` as full Layout records. On URL match, `matched.length` = 3, **two Layouts render** (Finance's chrome + Report's chrome + IncomeStatement page nested inside Report).

## Diagnosis checklist
1. `document.querySelectorAll('.app-wrapper').length` → 2 confirms
2. `curl http://localhost/prod-api/getRouters -H "Authorization: Bearer $T" | jq '.data[].component, .data[].children[].component, ...'` → grep for `'Layout'` appearing on non-root nodes
3. SQL: `SELECT menu_id, menu_name, parent_id, path, component FROM sys_menu WHERE component='Layout';` → if any `parent_id != 0` row appears → bug

## Fix (one-shot SQL)
```sql
-- 1. Middle parents: NULL lets backend auto-resolve to 'ParentView'
UPDATE sys_menu SET component = NULL
WHERE menu_id IN (
  SELECT menu_id FROM (
    SELECT menu_id FROM sys_menu
    WHERE component = 'Layout' AND parent_id != 0 AND menu_type = 'M'
  ) t
);
-- 2. Only the absolute root (parent_id=0, menu_type=M) stays 'Layout'
-- (no change needed if it's already correct; verify with:
SELECT menu_id, menu_name, parent_id, path, component
FROM sys_menu WHERE component='Layout';  -- expect ONLY parent_id=0 rows
```

After SQL: no jar rebuild needed (data-driven). User must hard-refresh: `?nocache=N` + clear `localStorage`/`sessionStorage`/`document.cookie` then re-login so `permission.ts generateRoutes` re-adds routes from the new tree.

## Verification
```js
// Browser console after re-login + hard navigate:
JSON.stringify({
  appWrapper: document.querySelectorAll('.app-wrapper').length,
  mainContainer: document.querySelectorAll('.main-container').length,
  appMain: document.querySelectorAll('.app-main').length,
  sidebar: document.querySelectorAll('.sidebar-container').length,
  navbar: document.querySelectorAll('.navbar').length
})
// Expect: all = 1
```

## Don't confuse these traps
1. **`a11y tree` (`browser_snapshot`)** shows nested `menubar > menu > menuitem` even when DOM has only one sidebar — a11y is role-flattened, not DOM-flattened. Don't trust element_count alone.
2. **`browser_vision`** can also say "1 sidebar" when DOM has 2 if the inner one occludes the outer — always verify with `querySelectorAll`.
3. **Ground truth order**: `querySelectorAll` DOM count → element outerHTML inspection → vision screenshot. Use all three.

## Related (same skill family)
- `references/silent-template-failures-and-layout-flicker.md` — layout/index.vue `watchEffect` flicker (different cause, same symptom family)
- `references/permissions-router-registration.md` — how `permission.ts generateRoutes` produces the route tree from `/getRouters`