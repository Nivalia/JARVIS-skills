# RuoYi/JonLink @Excel(name) Shortening — Backend Excel Header Naming

## The standing rule (extends `finance-ui-labeling-and-dict.md`)

The UI label rule — no raw `0` / `1` / `2` / `3` in user-facing labels — applies **equally** to **Excel export table headers**. The `@Excel(name = "...")` annotation drives:

1. The Excel/CSV file header row that users open and read
2. Some downstream PDF exports
3. Anyone comparing spreadsheets between sessions/days

When `@Excel(name = "活跃度 1高 2中 3低(定时任务计算)")`, the exported xlsx has a 20-character header that:
- Forces the user to widen the column to read it
- Mixes the field name with its enum value list
- Repeats the same enum list across every related field

## The split — what `@Excel(name=...)` should hold vs not

| Element | Should be in @Excel(name) | Should NOT |
|---|---|---|
| Field name (≤8 chars) | yes | |
| Bracket-paren clarification (`(可选)` `(冗余)`) | no | move to `/** javadoc */` |
| Enum value list (`0否 1是`, `0草稿 1待审 ...`) | no | already shown via `<dict-tag>` in UI; Excel readers can look up the dict |
| DB column reference (`按type指向wx_mp_user.id`) | no | DBA sees the schema |
| Computed formula (`= 保费 - 上游佣金(自动算)`) | no | move to `/** javadoc */` or unit name (e.g. `netFee`, `profit`) |
| Unit (`(元)` `(¥)` `(天)`) | no | global header note + tooltip; mixing it into name clutters every column |

## Manual mapping beats algorithmic normalization

I tried a regex normalizer that strips brackets, matches `中文 + 空格 + 数字枚举` patterns, and truncates. It failed on:
- Pure enum strings (`0待发 1成功 2失败 ...`) → no Chinese core to extract
- Mixed English/Chinese (`balanceDirection 余额方向 0借 1贷`) → kept the wrong segment
- English names like `partnerName` → kept the wrong segment or truncated `partnerName` to `partnerN`

**The robust path**: build a hand-written mapping table keyed on `(DomainFile, propFieldName, currentExcelName) → newName`. Validate against current source first (so every mapping has a match), then bulk-apply.

```python
mapping = {
    ("FinVoucher.java", "status", "0草稿 1已审核 2已过账 3已作废"): "状态",
    ("WxMpUser.java", "subscribe", "关注状态 0否 1是"): "订阅",
    ("JonlinkInsuranceLedger.java", "profit",
     "利润 = 上游佣金 - 下游佣金(自动算)"): "利润",
    # ...
}
# 验证: 先确保 old 能在源文件中找到
for (fname, prop, old), new in mapping.items():
    pattern = re.compile(rf'@Excel\(name = "{re.escape(old)}"\)\s*private\s+\w+\s+{re.escape(prop)}\s*;')
    if not pattern.search(open(fp).read()):
        print(f"NOT FOUND: {fname}.{prop} = {old}")
# 批量替换: f'name = "{old}"' → f'name = "{new}"'
```

## Full-scan strategy — one grep, no early stopping

I initially stopped at 19 "obvious" long names and missed 75+ more — same-domain `@Excel` names in finance, ledger, wx modules. **Lesson**: never stop the scan after the first batch. The single source of truth is one regex over the whole domain directory, then dedupe by current name.

```bash
# Find every @Excel(name="...") where name > 8 chars across ALL domain files
python3 - << 'PY'
import re, os
domain_dir = "/opt/JonLink/JonLink-Vue/jonlink-system/src/main/java/com/jonlink/system/domain"
hits = []
for f in sorted(os.listdir(domain_dir)):
    if not f.endswith('.java'): continue
    content = open(os.path.join(domain_dir, f)).read()
    for m in re.finditer(r'@Excel\s*\(\s*name\s*=\s*"([^"]+)"\s*\)\s*private\s+(\w+)\s+(\w+)\s*;', content):
        nm, t, n = m.group(1), m.group(2), m.group(3)
        if len(nm) > 8:
            hits.append({'file': f, 'type': t, 'field': n, 'excel_name': nm})
print(f"total long names: {len(hits)}")
PY
```

Categorize hits:
1. **Pure English 9–11 chars** (`receiptNo`, `paymentNo`, `voucherNo`, `expenseNo`, `invoiceNo`, `partnerName`, `settleRecordNo`, `subjectCode`, `subjectName`) — **leave alone**. They are reasonable English prop names that fit a spreadsheet column width; truncating to `receiptN` makes the column ambiguous.
2. **Pure Chinese + (clarification)** (`渠道来源 0自定义 ...`, `活跃度 1高 2中 3低(定时任务计算)`) — short, replace.
3. **English + Chinese clarification** (`发送方openid`, `扫码粉丝openid`, `关联 wx_mp_template.id`) — keep Chinese-only, drop DB-ref and English suffix.
4. **Formula** (`净费 = 保费 - 上游佣金(自动算)`, `利润 = 上游佣金 - 下游佣金(自动算)`) — replace with just the math label (`净费`, `利润`).

## Naming conflicts after shortening — the column-collision check

After shortening, **always check for header collisions** in the same Domain class. Two fields with similar short names will collide in the export:

```java
// BAD: both become "access_token"
@Excel(name = "缓存的access_token")        private String accessToken;
@Excel(name = "access_token过期时间")      private Date tokenExpireTime;
// → after rename:
// "access_token" (G) "access_token过期时间" (H) — confusing

// GOOD: distinct
@Excel(name = "access_token")              private String accessToken;
@Excel(name = "过期时间")                  private Date tokenExpireTime;
```

Verification after rebuild + restart:

```bash
# 1. Login + token
curl -s -X POST 'http://localhost:8080/login' -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"admin123"}' -o /tmp/login.json
TOKEN=$(python3 -c "import json;print(json.load(open('/tmp/login.json'))['token'])")

# 2. Trigger export endpoint (POST, returns xlsx)
curl -s -X POST "http://localhost:8080/<module>/export" \
  -H "Authorization: Bearer $TOKEN" -o /tmp/export.xlsx

# 3. Parse xlsx header row from sharedStrings + inline strings
python3 - << 'PY'
import zipfile, re
with zipfile.ZipFile('/tmp/export.xlsx') as z:
    raw = z.open('xl/worksheets/sheet1.xml').read().decode('utf-8')
headers = re.findall(r'<t[^>]*>([^<]*)</t>', re.search(r'<row r="1">.*?</row>', raw, re.S).group(0))
for i, h in enumerate(headers):
    print(f"  {chr(65+i)}: {h!r}")
PY
```

If two columns have the same header text, the user can't tell which is which in the exported file. Fix by further differentiation (`access_token` vs `过期时间`, not `access_token` vs `access_token过期时间`).

## Don't rely on the dict — `@Excel(name)` IS the export header

`<dict-tag>` in the UI displays enum labels, but **the Excel export uses `@Excel(name)` directly** with no dict lookup. So even if the page shows `状态: 已启用` (dict-translated), the export column header reads exactly what `@Excel(name)` says. That asymmetry — dict-driven UI vs annotation-driven export — is why the annotation needs its own polishing pass separate from the dict setup work.

## Build + deploy cycle for Excel-only changes

Excel header changes are **Java-only** — no frontend rebuild needed:

```bash
# Rebuild backend only (admin pulls in system via -am)
cd /opt/JonLink/JonLink-Vue
mvn clean package -DskipTests -pl jonlink-admin -am -q

# Restart service
systemctl restart jonlink.service
# wait 10s for Spring Boot ready (curl http://localhost:8080/login)

# Trigger export + verify header row via the curl + xlsx parse recipe above
```

For frontend changes (filter fields, dict-tag colors, label shortening in Vue), the full front+back cycle is required (see Trap 1 of `vue3-vite-element-plus-traps` skill).
