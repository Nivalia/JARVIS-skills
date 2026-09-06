---
name: jonlink-ruoyi-field-name-cleanup
description: "Shorten Chinese field names across 4 layers."
---

# JonLink / RuoYi 字段名清理(4-layer consistency)

When the user complains "字段名太长" / "表头太乱" / "导出 Excel 列名带枚举说明看不懂", the fix touches **4 separate layers** that must stay consistent. This skill captures the workflow, the rules for what is shortable vs what must be preserved, and the pitfalls of mass-mapping tables.

## Why 4 layers must stay in sync

| Layer | What it controls | Where to edit |
|---|---|---|
| **Java `@Excel(name=...)`** | Admin export xlsx header | `<domain>.java` annotation |
| **Frontend `<el-table-column label="...">`** | List page column title | `<vue>/views/<m>/<e>/index.vue` |
| **Frontend `<el-form-item label="...">`** | Search/filter form label, dialog field title | same vue file |
| **Dict `sys_dict_data.label`** | Dropdown option text (rendered via `<dict-tag>`) | DB `sys_dict_data` rows |

The export header comes from `@Excel(name=...)` not from the Vue label. The page column title comes from the Vue label not from `@Excel`. They drift independently. A "field name cleanup" without 4-layer edits leaves the user fixing complaints per-layer.

## What is shortable vs preserved

Always run a discovery scan first. The same scan tells you both categories.

**Preserve (DO NOT change):**
- **Pure English prop names** (`receiptNo / paymentNo / voucherNo / expenseNo / invoiceNo / partnerName / settleRecordNo / sourceNo / subjectCode / subjectName`). These are database column names; changing them breaks prop bindings and DB queries.
- **WeChat/technical API standard field names** (`AppSecret / access_token / AppID / openid / ticket / Token`). Changing them breaks integration with WeChat open platform.
- **Dict values** (`'0' / '1'` codes, NOT labels). Labels may be shortened.

**Shorten (candidate targets):**
- Pure Chinese compound phrases (`渠道关联ID` → `渠道ID`, `上游结算单号` → `上游结算单`)
- Redundant parentheticals (`产品名称(带出)` → `产品名称`, `批次号(唯一)` → `批次号`, `保费(手动,¥)` → `保费`)
- Pure-enum expansions (`0停用 1启用` → `状态`, `0应收 1应付` → `类型`, `方向 0流入 1流出` → `方向`)
- DB column references (`关联 wx_mp_template.id` → `模板ID`)
- Hand-curated math/algorithm notes (`利润 = 上游佣金 - 下游佣金(自动算)` → `利润`)

## Algorithm vs hand-mapping

**Algorithmic shortening is fragile for Chinese.** Regexes like `[\uff08\(].*?[\uff09\)]` remove parentheticals correctly, but mistreat compound names: `partnerName` would become `partnerN` if you slice `>8` chars. `isNewFollow` with prefix becomes `isNewFol`.

**Hand-curated mapping tables are correct but error-prone to write.** When you batch-shorten 100+ fields, the table itself becomes the bug source:
- Listing `(file, field, old, new)` misses `@Excel(name=...)` strings that don't match the field name 1:1 (e.g., `field=phone` but `name="客户手机号"`)
- Repeated mapping entries for the same `(old, new)` cause confusion about which already exists
- Old names that were renamed in a prior round get listed again

**Pattern that works**: include the **prop name** in every mapping entry as an anchor, so verification can grep for `prop` independently of `name`:

```python
# mapping format: (file, prop, old_name, new_name)
mappings = [
    ("WxLedgerItem.java", "phone", "客户手机号", "手机号"),
    ("WxLedgerItem.java", "openid", "客户openid", "openid"),
    ("WxLedgerItem.java", "occurredTime", "业务发生时间(核销/发送/扫码时刻)", "业务时间"),
]
```

This catches the case where you wrote the mapping but the file's current `@Excel(name=...)` was already renamed in a prior round — verification will report "name doesn't exist" and you skip without double-rewriting.

## 4-layer edit workflow

```
1. Discovery scan:
   find all @Excel(name="...") in Domain/ > 7 chars (or 5+ if user complains hard)
   find all <el-table-column label="..."> > 5 chars
   find all <el-form-item label="..."> > 5 chars
   find all <el-descriptions-item label="..."> > 5 chars

2. Classify each hit as PRESERVE or SHORTEN (per the rules above)

3. For SHORTEN, build hand-curated mapping table with prop anchors

4. Apply mapping table to:
   - Backend Domain .java @Excel(name=)
   - Frontend vue <el-table-column> / <el-form-item> / <el-descriptions-item> label

5. Build + restart + verify by exporting xlsx and parsing the headers
```

## E2E verification: parse xlsx to read headers

Curl returns a binary xlsx. You can't read it as text. Use Python's `zipfile`:

```python
import zipfile, re, urllib.request

# Get admin token
login_req = urllib.request.Request(
    "http://127.0.0.1:8080/login",
    data=b'{"username":"admin","password":"admin123"}',
    headers={"Content-Type": "application/json"},
    method="POST",
)
token = json.loads(urllib.request.urlopen(login_req).read())["token"]

# Hit export endpoint
export_req = urllib.request.Request(
    "http://127.0.0.1:8080/<module>/<entity>/export",
    method="POST",
    headers={"Authorization": f"Bearer {token}"},
    data=b"",
)
body = urllib.request.urlopen(export_req).read()

# xlsx is a zip; sheet1.xml holds cell values inline
with zipfile.ZipFile(__import__("io").BytesIO(body)) as z:
    with z.open("xl/worksheets/sheet1.xml") as f:
        raw = f.read().decode("utf-8")
m = re.search(r'<row r="1">.*?</row>', raw, re.S)
if m:
    headers = re.findall(r'<t[^>]*>([^<]*)</t>', m.group(0))
    # headers is the actual export column titles
```

Run this against every `@PostMapping("/export")` controller and report per-controller:
- Total column count
- Max header length
- Number of headers > 5 (or > 7) chars

Categorize "still long" results into PRESERVE (acceptable) vs SHORTENABLE (must fix).

## Common pitfalls

### Pitfall 1 — The prop-name is in a different module than the @Excel annotation

`SysUser` lives in `jonlink-common` (not `jonlink-system/domain`). When applying mappings, **search the whole tree**, not just `jonlink-system/src/main/java/com/jonlink/system/domain/`. If you fix `jonlink-system` only, `mvn clean package -pl jonlink-admin -am` will still package `jonlink-common`'s old class.

### Pitfall 2 — When the column-label and prop-name disagree, you've broken a binding

`field=appSecret` but `label="AppSecret"` works because the name matches the prop. If you rename label to "公众号密钥" without renaming prop, the dict-tag lookup fails. Either keep the label exact or change BOTH.

### Pitfall 3 — Test data with NULL subscribe_time makes interval filtering look broken

When verifying date-range filters, the filter returns 0 rows because `subscribe_time IS NULL` for every row, not because the filter is wrong. Inject a row with a known date:

```sql
UPDATE wx_mp_user SET subscribe_time = '2026-08-15 10:00:00' WHERE id = 256;
-- run e2e with the date range that includes 2026-08-15
-- e2e finished:
UPDATE wx_mp_user SET subscribe_time = NULL WHERE id = 256;
```

Without this, you might falsely report "filter returns 0 → filter is broken → debug for hours".

### Pitfall 4 — Auth token expires between tests

After a `systemctl restart`, all previously-issued admin tokens become invalid because the JWT signing secret may have been regenerated, or the `exp` claim was set in the past. Always re-login before each test:

```python
# After any restart, re-login
token = json.loads(urllib.request.urlopen(login_req).read())["token"]
```

### Pitfall 5 — Controller path discovery

Don't guess URLs like `/wx/qrScanLog/export` from the Vue page route. Read the controller:

```bash
grep -rn "@RequestMapping" /opt/<project>/jonlink-admin/src/main/java/ \
  --include="*.java" | grep -v "@RestController"
# Look for class-level @RequestMapping("/<module>/<entity>") + @PostMapping("/export")
# Then URL = class-level mapping + method-level mapping
```

Also watch for sub-paths (`@RequestMapping("/wx/mp")` + `@GetMapping("/order/exportFailList")`).

## Cross-reference: mvn rebuild trap

This skill assumes the deploy pipeline (`mvn clean package -pl jonlink-admin -am -q`) catches all Domain changes. If a future version of the project moves Domain classes to a third module, you'll need `mvn clean package -DskipTests` (no `-pl` flag) to rebuild the full reactor. See `ruoyi-vue-page-delivery` for the multi-module cache trap details.

## Reference

- `references/preserve-vs-shorten-decision-tree.md` — flowchart for ambiguous cases (e.g., `policyNo` looks short but is a prop name; `policyUser` looks English but might be domain-only)
- `references/4-layer-edit-checklist.md` — per-page checklist to confirm Domain → Mapper → Frontend label → Dict all align after a round
- `references/xlsx-header-parser.md` — copy-paste Python snippet for parsing export xlsx column titles
