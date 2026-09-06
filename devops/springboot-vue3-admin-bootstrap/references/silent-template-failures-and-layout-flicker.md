# Silent Template Failures + Layout Flicker (P42, P43)

Companion reference for the `springboot-vue3-admin-bootstrap` skill. Covers two silent frontend traps that don't surface in dev mode but break production builds.

## P42 — Vue 3 scoped-slot `<!---->` when helper is used without an import

**Symptom (verified 2026-08-16 on jonlink `/finance/reimburse/invoice` — ~3 hours misdiagnosed as "template destructure style")**

After patching 3 `<el-table-column>` cells in a vue file to use the centralized `financeDict.ts` helper (`finDictItem(row.X, 'invoice_type').type` for el-tag color, `finDict(row.X, 'invoice_type')` for label text), the build succeeds, the page loads, but **the 3 patched cells render as empty** — column header visible, data row visible, the `.cell` div present, but inner content is a single Vue comment node `<!---->`.

Sibling columns using the same helper in OTHER vue files (e.g. `subject/index.vue`) render correctly. Browser console is **silent** — no Vue warn, no compile error, no network error. `npm run build:prod` succeeds. `mysql` query confirms data is in DB. Every other element on the page is fine.

**Why this is a real trap**

The user reports "发票类型/方向/核销状态 3 列显示空白" and you naturally start debugging the **template** (`#default="{ row }"` destructure style? `:type="undefined"` from `finDictItem`? mixing `scope.row` and `{ row }`?). All wrong. The actual cause is in the `<script setup>` block, NOT the template.

**Root cause**

The `<script setup lang="ts">` block was missing the `import { finDict, finDictItem } from '@/utils/financeDict'` line. Vue 3 + element-plus handles undeclared identifiers in scoped slots by **silently replacing the entire slot body with an empty comment node** — no warning, no error in production builds (dev mode `console.warn` is suppressed by Vite's prod transform).

The template LOOKS correct (`<template #default="{ row }">` destructure, `row.invoiceType` access, `finDictItem`/`finDict` calls). The data IS in DB. The `financeDict.ts` file DOES exist (`grep -rn 'FIN_DICTS' src/utils/financeDict.ts` returns hits). The build succeeds. The page renders. **Only the cells that reference the un-imported helper render as `<!---->`.**

**Diagnosis recipe (do these in order, before patching the template)**

```bash
# 1. Confirm import missing in the broken file
grep -n 'import.*financeDict' /opt/JonLink/JonLink-Vue3-TS/src/views/finance/<page>/index.vue
# expect: 1 line. 0 lines = bug is the missing import, NOT the template.

# 2. Confirm symptom in browser DOM (devtools console)
document.querySelector('.el-table__row').outerHTML
# look for <!----> inside .cell divs — those columns are silently failing

# 3. Cross-check against a working sibling file
grep -n 'import.*financeDict' /opt/JonLink/JonLink-Vue3-TS/src/views/finance/<working-page>/index.vue
# expect: 1 line. If working file has it and broken file doesn't, import IS the fix.

# 4. Confirm financeDict.ts is exported correctly
grep -n 'export' /opt/JonLink/JonLink-Vue3-TS/src/utils/financeDict.ts | head
# expect: `export const FIN_DICTS` + `export function finDict` + `export function finDictItem`
# If any of these is missing, the build would error out — so the file is fine, the per-page import is the issue.
```

**Fix — add the import at the top of `<script setup lang="ts">`**

```ts
import { finDict, finDictItem } from '@/utils/financeDict'
```

After `npm run build:prod` + `nginx -s reload` + browser hard-reload (`?nocache=N`), the 3 cells render the el-tag with proper label and color.

**Why this trap is so easy to miss**

When bulk-patching many `<el-table-column>` cells, the import line is easy to overlook. Every individual element (template, data, dict file, build) is correct. Only the integration is broken, and Vue hides the failure.

**Why the previous context wasted ~3 hours on this**

I correctly identified the symptom as `<!---->` in the DOM, but assumed it was a template-style problem (`#default="{ row }"` vs `#default="scope"`) because the destructure style "looked suspicious". Real cause was 200 lines earlier in the same file — the missing import. **Always grep for the import BEFORE debugging the template.**

**This trap is a sibling of Pitfall 40 / 31 / 35** — all four manifest as "I changed code and the page is broken". The "broken" surface looks identical (cells empty, button dead, network call missing), but the diagnostic paths are completely different. Always do this 4-check before declaring any "edit broke the page" report fully diagnosed:

| # | Diagnostic | | Pitfall |
|---|---|---|---|
| 1 | `grep -n 'import.*<helper>'` — is the helper imported in THIS file? | | **P42** (silent `<!---->`) |
| 2 | `grep -n '@click="handler()"` — does the handler have parens? | | P40 (no-parens → MouseEvent) |
| 3 | `grep -A2 '.catch'` — is there an empty `.catch(() => {})`? | | P31 (catch swallowing) |
| 4 | Browser network panel — does the request go out? | | If no → Trap E; if yes → response-code trap |

Check 1 takes 5 seconds and was the actual fix in the 2026-08-16 case.

**Companion fix in `references/finance-ui-labeling-and-dict.md`**

The same trap is also documented in `references/finance-ui-labeling-and-dict.md` § "Usage in `.vue` pages" — the import is mandatory in every vue file that calls `finDict` / `finDictItem`. Bulk-patch warning included: when adding a new usage, always run `grep -c 'financeDict' <file>.vue` AFTER the patch and verify count ≥ 2 (1 import + ≥ 1 usage).

---

## P43 — `watchEffect` on `useWindowSize()` causes layout flicker + main-area stacking

**Symptom**

Every page reload causes sidebar to flash open/close. Main content area appears to "jump" on top of sidebar for ~100ms after navigation. Window resize across the 992px boundary (Bootstrap's `md` breakpoint) triggers the flicker again. Worst case: window width near 992px creates an **infinite toggle loop** between mobile and desktop device modes.

**Why (verified 2026-08-16 on jonlink `src/layout/index.vue` — user reported "昨天的问题又出来了")**

```ts
const { width, height } = useWindowSize()
const WIDTH = 992

watchEffect(() => {                    // ← runs on EVERY reactive width change
  if (width.value - 1 < WIDTH) {
    useAppStore().toggleDevice('mobile')
    useAppStore().closeSideBar({ withoutAnimation: true })
  } else {
    useAppStore().toggleDevice('desktop')
    if (!useAppStore().sidebar.opened) {
      useAppStore().toggleSideBar(true)
    }
  }
})
```

Three problems compound:

1. **`watchEffect` re-runs on every reactive dep change**. `useWindowSize()` exposes `width` as a reactive ref; any window resize (browser devtools opening, stylesheet load, font swap) fires it.
2. **`toggleDevice` + `closeSideBar` mutate the same store**. Even if `width` doesn't cross 992, the body of the effect runs (touching `width.value` registers as a dep), and the toggle calls feed back into reactive deps that some `watchEffect` re-runs can chain on.
3. **No debounce**. A slow drag-resize across 992 fires the effect dozens of times, each causing a momentary `closeSideBar` + `toggleSideBar(true)` flip.

The main-area-stacking symptom comes from a SECOND root cause: `<el-aside>` and `<el-main>` are not laid out with explicit flex containers. `.app-wrapper` uses `position: relative; height: 100%` with no `display: flex`. The `<el-aside>` sidebar takes its natural width, the `<div class="main-container">` flows in the document block (NOT side-by-side). When `height: 100vh; overflow: hidden` is applied to main-container, its initial height collapses to the navbar height (~50px) — the rest of the page goes to viewport top, **stacking under the sidebar**. Within ~100ms, Vue's reactivity settles, sidebar takes its full height, main-container pushes down. The eye sees this as "main jumping on top of sidebar".

**Fix — two parts**

(a) Replace `watchEffect` with `onMounted` + debounced `resize` listener:

```ts
const initialResizeDone = ref(false)
let resizeTimer: ReturnType<typeof setTimeout> | null = null
function applyResponsive(): void {
  if (width.value - 1 < WIDTH) {
    useAppStore().toggleDevice('mobile')
    useAppStore().closeSideBar({ withoutAnimation: !initialResizeDone.value })
  } else {
    useAppStore().toggleDevice('desktop')
    if (!useAppStore().sidebar.opened) useAppStore().toggleSideBar(true)
  }
  initialResizeDone.value = true
}
onMounted(() => {
  applyResponsive()  // first mount: no animation (no flicker on load)
  window.addEventListener('resize', () => {
    if (resizeTimer) clearTimeout(resizeTimer)
    resizeTimer = setTimeout(applyResponsive, 150)  // debounce
  })
})
onBeforeUnmount(() => {
  window.removeEventListener('resize', () => {})
  if (resizeTimer) clearTimeout(resizeTimer)
})
```

The `initialResizeDone` flag suppresses the close-sidebar animation on first mount (so the page loads with sidebar already in its target state) but allows animations on subsequent resizes.

(b) Force proper flex layout on `.app-wrapper` so sidebar + main-container always sit side-by-side at full viewport height:

```scss
.app-wrapper {
  @include mix.clearfix;
  position: relative;
  height: 100%;
  width: 100%;
  display: flex;       /* ← was missing; without it, sidebar is block-flow */

  &.mobile.openSidebar {
    position: fixed;
    top: 0;
  }
}

// Mobile: sidebar becomes overlay drawer, NOT a flex item
.app-wrapper.mobile .sidebar-container {
  position: fixed;
  top: 0;
  left: 0;
  height: 100vh;
  z-index: 1001;
}

.main-container:has(.fixed-header) {
  height: 100vh;
  overflow: hidden;
  flex: 1;             /* ← fill remaining horizontal space */
  min-width: 0;        /* ← allow flex item to shrink below content width */
}

.sidebar-container {
  height: 100vh;
  flex-shrink: 0;      /* ← never let flex shrink sidebar below its content width */
}
```

The `mobile` selector restores the original drawer-overlay behavior on mobile so flex doesn't push main off-screen when sidebar appears.

**Why both parts are needed**

Part (a) stops the rapid open/close toggling. Part (b) stops the main-area-stacking even on the FIRST paint. If you only do (a), the layout still stacks on page load (because `watchEffect` was the only thing keeping it sane via reactive store mutations); if you only do (b), the flicker on resize across 992px still happens.

**Detection recipe**

```bash
# 1. Confirm watchEffect is the trigger
grep -n 'watchEffect.*useWindowSize\|useWindowSize().*watchEffect' src/layout/index.vue

# 2. Confirm flex layout is missing
grep -n 'display: flex' src/layout/index.vue  # expect: 0 (the bug)
grep -n 'display:.*flex' src/layout/index.vue  # broader

# 3. Browser devtools performance recording during a slow drag-resize across 992px
#    - if the sidebar's left position is changing rapidly, watchEffect is the cause
#    - if main-container height is 0 then 100vh, flex layout is missing
```

**Companion fix for the sidebar hidden state on logout**

`useAppStore().sidebar.hide` controls a SEPARATE hide flag (different from `sidebar.opened`). When the user logs out and back in, `hide` may still be true from a previous session — sidebar doesn't render at all. If the user reports "侧边栏完全没了", check `useAppStore().sidebar.hide` in the store and reset to `false`.

**Origin**

This trap recurred on jonlink 2026-08-16 after the layout was thought to be fixed in M0. User said "昨天的问题又出来了" — same flicker symptom. Real cause: the original fix (the `watchEffect` on width) was itself a partial workaround that addressed the static layout but introduced the flicker. Lesson: layout fixes need to consider BOTH the responsive breakpoint transitions AND the initial paint state.

---

## How P42 and P43 relate to the existing pitfalls

P42 belongs with P40 / P31 / P35 as a member of the "I changed code and the page is broken" cluster — the surface symptom is identical but the diagnostic path is completely different. The 4-check table in P42 is the canonical triage for "page broken after my edit".

P43 is a layout-level trap. It only triggers on responsive breakpoint crossings or first paint, not on edit actions. Diagnose it with grep (watchEffect / flex layout) before browser interaction.

Both were caught in the same session (2026-08-16). The user's primary complaint was "invoice 3 列空 cell" (P42) and "侧边栏闪现 + 框架错位" (P43). Fixing only one would have left the user dissatisfied; both fixes landed in the same build.