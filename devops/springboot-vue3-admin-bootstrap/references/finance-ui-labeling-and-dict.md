# Finance/Admin UI Labeling Rule + Centralized Dict Pattern

## 1. The UI labeling rule (user preference, 2026-08-20)

**Rule**: Never display raw enum numbers (`0`, `1`, `2`, `3`) in admin list pages, form labels, or search fields. Always translate to the human-readable label.

### Wrong (raw numbers, ambiguous)
- Column header: `label="0草稿 1已审 2已驳回"`
- Form item: `label="0草稿 1启用"`
- Search input placeholder: `请输入0进项 1销项`
- Table cell showing `status=0` as text

### Right (label-only, with the dict inferred from dict/help text or context)
- Column header: `label="发票类型"`
- Form item: `label="状态"` with `<el-select>` of `进项` / `销项` (NOT `0` / `1`)
- Table cell showing `<el-tag type="success">增值税专票</el-tag>` (NOT `0`)

### When the user calls out this rule

The user has corrected this pattern explicitly: "别用数字 123 代表功能，改用功能说明 如 是 否等". Treat it as a **standing UI preference**, not a one-off fix. Every new enum/status/direction field must default to the labeled form. If you find old code that uses raw numbers, batch-fix it in the same session.

### Where the trap hides

- Auto-generated CRUD pages from RuoYi `/tool/gen` use verbose `label="0草稿 1已审 2已驳回"` text directly in column headers — the generator doesn't separate label from help text.
- Form fields for `direction`, `invoice_type`, `expense_type`, `tax_flag`, `subject_type`, `balance_direction`, `is_leaf`, `status` default to `<el-input>` (text input) — wrong control type for an enum. Use `<el-select>` with explicit `<el-option>` entries that show labels only.
- `<el-tag :type="...">{{ row.status }}</el-tag>` shows the raw value when no `<template #default>` wrapper exists.
- Validation rules `message: "0草稿 1启用不能为空"` must drop the number prefix and use `message: "状态不能为空"`.

### Bulk-fix recipe

```python
import re, glob
# 1) Replace verbose labels in column headers
LBL = re.compile(r'label="(\d[^\d]*?\d[^"]*?)"')
# 2) Replace raw status prop columns with template-tagged wrapper
# 3) Patch form rules
```

Actually the cleanest path is the **`financeDict.ts` helper** below — replaces ~50 lines of `v-if`/`<el-tag>` boilerplate per page with one helper call, AND enforces the label-only rule by construction (formatter never returns raw value).

## 2. `financeDict.ts` — centralized enum-display helper

`src/utils/financeDict.ts` (created 2026-08-20, jonlink finance M0-M7 rollout). Single source of truth for translating enum values to Chinese labels + el-tag color.

### The pattern

```typescript
export type DictMap = Record<string, {
  label: string
  tag?: 'success' | 'info' | 'warning' | 'danger' | 'primary'
}>

export const FIN_DICTS: Record<string, DictMap> = {
  voucher_status: {
    '0': { label: '草稿',   tag: 'info' },
    '1': { label: '已审核', tag: 'warning' },
    '2': { label: '已过账', tag: 'success' },
    '3': { label: '已作废', tag: 'danger' },
  },
  common_status: {
    '0': { label: '停用', tag: 'danger' },
    '1': { label: '启用', tag: 'success' },
  },
  cash_flow_direction: {  // 0=out, 1=in (engine convention)
    '0': { label: '流出', tag: 'warning' },
    '1': { label: '流入', tag: 'success' },
  },
  // ... voucher_source, period_status, ledger_log_status, settle_status,
  //     invoice_type, invoice_direction, invoice_settle, allocation_type,
  //     balance_direction, subject_type, yes_no, expense_type, expense_status,
  //     receipt_biz_type, ledger_book_type, receipt_payment_status, ...
}

export function finDict(value: any, dictKey: string): string {
  if (value === null || value === undefined || value === '') return ''
  const map = FIN_DICTS[dictKey]
  if (!map) return String(value)
  const item = map[String(value)]
  return item ? item.label : String(value)
}

export function finDictItem(value: any, dictKey: string): { label: string; type?: string } {
  if (value === null || value === undefined || value === '') return { label: '' }
  const map = FIN_DICTS[dictKey]
  if (!map) return { label: String(value) }
  const item = map[String(value)]
  return item ? { label: item.label, type: item.tag } : { label: String(value) }
}
```

### Usage in `.vue` pages

```vue
<template>
  <!-- Display column with el-tag coloring -->
  <el-table-column label="状态" align="center" prop="status">
    <template #default="{ row }">
      <el-tag :type="finDictItem(row.status, 'voucher_status').type" disable-transitions>
        {{ finDict(row.status, 'voucher_status') }}
      </el-tag>
    </template>
  </el-table-column>

  <!-- Plain text column (no tag color needed) -->
  <el-table-column label="业务类型" prop="bizType">
    <template #default="{ row }">
      {{ finDict(row.bizType, 'receipt_biz_type') }}
    </template>
  </el-table-column>
</template>

<script setup lang="ts">
import { finDict, finDictItem } from '@/utils/financeDict'
</script>
```

### ⚠️ The `financeDict` import is MANDATORY in every vue file that calls it

The most common silent failure with this pattern: a `<script setup>` block calls `finDict(...)` / `finDictItem(...)` in the template but **forgets the import line**. Vue 3 + element-plus does NOT throw a console error or warning. The scoped slot template fails to render and the cell shows as an empty comment node (`<!---->`) — the same symptom as "data missing".

**Symptoms** (verified 2026-08-16 on jonlink `/finance/reimburse/invoice` — 3 columns rendered empty for ~3 hours before diagnosis):

1. Multiple `<el-table-column>` cells render as empty (column header is visible, data row is visible, the cell `.cell` div is present, but inner content is `<!---->`).
2. Sibling columns using the same helper in OTHER files render correctly.
3. Browser devtools console is silent — no Vue warn, no compile error.
4. `npm run build:prod` succeeds.
5. `grep -n 'import.*financeDict' <broken-file>.vue` returns **zero matches**.

**Diagnosis** (do these in order, before touching the template):

```bash
# 1. Confirm import missing
grep -n 'import.*financeDict' /opt/JonLink/JonLink-Vue3-TS/src/views/finance/<page>/index.vue
# expect: 1 line. 0 lines = bug is here.

# 2. Confirm symptom in DOM (browser devtools console)
document.querySelector('.el-table__row').outerHTML
# look for "<!---->" inside .cell — those columns are silently failing

# 3. Cross-check against a working sibling file
grep -n 'import.*financeDict' /opt/JonLink/JonLink-Vue3-TS/src/views/finance/<working-page>/index.vue
# expect: 1 line. If the working file has it and broken file doesn't, import is the fix.
```

**Fix** — add the import at the top of `<script setup lang="ts">`:

```ts
import { finDict, finDictItem } from '@/utils/financeDict'
```

After rebuild (`npm run build:prod`) + `nginx -s reload` + browser hard-reload (`?nocache=N`), the cells render correctly.

**Why this trap is so easy to miss**: when bulk-patching many `<el-table-column>` cells to use `finDictItem`, the import line is easy to overlook. The template LOOKS correct, the build SUCCEEDS, the data is in the database — every individual element is fine, but the integration silently fails. Vue's scoped slot error handling converts the throw into `<!---->` and never logs.

**Prevention**: when patching a vue file to use `finDict`, ALWAYS run `grep -c 'financeDict' <file>.vue` AFTER the patch and verify the count is ≥ 2 (1 import + ≥ 1 usage). If only 1 (one usage, no import), add the import. Better: build a project-wide lint rule that requires `import { finDict, finDictItem } from '@/utils/financeDict'` whenever a template uses those names.

### Why this pattern beats per-page el-tag v-if blocks

| Old pattern | New pattern |
|---|---|
| `<el-tag v-if="row.status==='0'" type="info">草稿</el-tag><el-tag v-else type="success">已审</el-tag>` | `<el-tag :type="finDictItem(row.status, 'voucher_status').type">{{ finDict(row.status, 'voucher_status') }}</el-tag>` |
| 4-8 lines per status column | 4 lines, reusable across pages |
| Status enum changes require editing every page that displays it | Edit `financeDict.ts` once |
| Label/color drift across pages (one says "草稿", another says "未审") | Single source of truth |
| Violates UI labeling rule silently (raw numbers in user input fields) | Always returns label or original value as fallback |

### Naming convention for dict keys

- `<entity>_<field>` pattern: `voucher_status`, `cash_flow_direction`, `invoice_type`
- For fields with yes/no semantics: `yes_no` (NOT `common_yes_no`) — `yes_no` is short and matches the DB `is_leaf` use case
- For generic 0=disabled 1=enabled: `common_status`
- Don't prefix with `fin_` — the file is already in `financeDict.ts` so the namespace is implicit

### Add a new dict in 3 steps

1. Add the entry to `FIN_DICTS` with `label` + `tag` for each enum value.
2. In the `.vue` page, `import { finDict, finDictItem } from '@/utils/financeDict'` and call `finDict(row.X, '<new_dict>')`.
3. Verify in browser: the cell shows the Chinese label with correct tag color.

## 3. Pitfall 41: DB column comment ≠ engine code convention

**Symptom**: SQL `DESC fin_cash_flow` shows `direction` with `COMMENT '0流入 1流出'`, but the Java engine writes `flow.setDirection("0")` for outgoing payments. Looking at the comment, "0=流入" would be the natural reading; looking at the engine, "0=out" is the truth. Front-end dict has `'0': { label: '流入' }` matching the comment — but the engine writes 0 for outflow. Display shows "流入" for an outflow row.

**Why this matters**: the comment is documentation that becomes the authoritative reference for "what does 0 mean?". Frontend and backend code drift from the comment, and one of them is wrong. The M0 generator stamps comments based on the DDL in `ruoyi-generator`, but the engine impl is hand-written and may flip the convention silently.

**Fix — synchronize at one of three levels**:

(a) **Update the DB comment** to match the engine (preferred when engine is "right" per business logic):

```sql
ALTER TABLE fin_cash_flow
  MODIFY COLUMN direction char(1) NOT NULL DEFAULT '0' COMMENT '0流出 1流入';
```

Verified 2026-08-20 on jonlink: the engine's `// 1=in` / `// 0=out` comments inside `FinFundEngineImpl.java` are the authoritative mapping (receipt → "1" in, payment → "0" out). The original `COMMENT '0流入 1流出'` in the DDL was the opposite.

(b) **Update the engine code** to match the comment (when the comment represents the original spec).

(c) **Update the dict** in `financeDict.ts` and the engine to match the comment, AND add a unit test for both directions so the next refactor catches drift.

**The diagnostic recipe** (after every new engine method that writes an enum value):

```bash
# 1. Find all places an enum is written
grep -nE 'setDirection|setStatus|setType' jonlink-system/src/main/java/com/jonlink/system/service/impl/Fin*EngineImpl.java

# 2. Compare to the DB column comment
mysql -uroot -p<pwd> <db> -N -e "SHOW FULL COLUMNS FROM <table> WHERE Field='<col>'"

# 3. Compare to the front-end dict
grep -A8 "<new_dict>:" src/utils/financeDict.ts

# 4. Verify each layer agrees
```

Verified drift points (jonlink, 2026-08-20):
- `fin_cash_flow.direction` — comment said "0流入 1流出", engine wrote "1=in / 0=out". Aligned to engine (a).
- `fin_expense.expense_type` — comment said "0管理费用 1销售费用", dialog said "日常报销/差旅报销". Aligned to dialog labels (a) since the dialog was the business-meaningful translation.
- `fin_expense.status` — comment said "0草稿 1待审 2已审 3已付款 4驳回", dict had "0=草稿 1=待审 2=已审 3=已付款 4=驳回". Already aligned.

## 4. Quick checklist (run before declaring a UI cleanup stage done)

- [ ] Every `el-table-column` for `status` / `direction` / `expense_type` / `invoice_type` / etc. uses `finDictItem` + `<el-tag>` (not raw `{{ row.X }}` or `v-if="==='0'"`).
- [ ] Every verbose column header like `0草稿 1已审` is replaced with just `状态`.
- [ ] Every form field with enum semantics uses `<el-select>` with labeled options (not `<el-input>`).
- [ ] Every `rules.X.message` no longer includes the digit prefix (e.g. `"状态不能为空"` not `"0草稿 1启用不能为空"`).
- [ ] `financeDict.ts` covers every enum the page displays — if a new enum is added, the dict must be extended BEFORE the page is touched.
- [ ] DB column comments match engine code conventions (or vice versa) — verified by `SHOW FULL COLUMNS` + `grep setX` cross-check.