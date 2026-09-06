# Pitfall 44 — MyBatis LEFT JOIN for "show names instead of IDs" produces 3 SQL ambiguity errors

Companion reference for the `springboot-vue3-admin-bootstrap` skill.
Covers the most common SQL pattern in a finance/admin CRUD module:
"list pages need to show `partnerName / bankAccountName / voucherNo /
invoiceNo / subjectCode` instead of the raw `*_id` foreign keys", which
means adding `LEFT JOIN` to the existing `selectVo` SQL — and the three
ambiguity errors that always surface during that change.

**Symptom (verified 2026-08-20 on jonlink finance module — 11 VOs / 11
mappers in one batch)**

After adding `LEFT JOIN fin_partner p ON r.partner_id = p.id` (and
similar joins to `fin_bank_account / fin_voucher / fin_subject /
fin_invoice / fin_expense`) to the existing `selectVo` SQL, jar build
succeeds (`mvn package` exit 0), but the first API hit returns:

```
{
  "msg": "### Error querying database. Cause:
 java.sql.sql.SQLIntegrityConstraintViolationException:
 Column 'id' in SELECT is ambiguous",
  "code": 500
}
```

You change `select id` to `select r.id`. Rebuild. Hit it again. Now:

```
Column 'source_type' in SELECT is ambiguous
```

Fix that one too. Hit again:

```
Column 'receipt_id' in where clause is ambiguous
```

Each one of these is a DIFFERENT underlying problem with a different
fix. Treating them as the same bug wastes ~30 minutes per VO × 11 VOs
= ~5 hours if you don't know the three-part recipe.

**Why this trap is universal**

In RuoYi-Vue3 generated modules, every business table has one Mapper
XML with one `<sql id="selectXxxVo">` that lists every column with
`select id, col1, col2, ... from fin_xxx`. The `resultMap` then maps
each column by name to a property. The moment you add a LEFT JOIN
that pulls in `fin_partner.id` or `fin_voucher.id` (because almost
every joined table has an `id` primary key), the existing `select
id` becomes ambiguous — MySQL has no way to know which `id` you want.

The same problem applies to ANY column the joined table happens to
share with the main table: `create_by / create_time / update_by /
update_time / status / source_type / source_id` — pick any two tables
in your system and there's a 60% chance they share a column name.

## The three ambiguity errors and the canonical fix

### Error 1 — `Column 'id' in SELECT is ambiguous`

**Cause**: `select id, col1, col2, ...` becomes ambiguous because
joined tables also have `id`. Common joined tables that all have
`id`: `fin_partner`, `fin_bank_account`, `fin_voucher`, `fin_subject`,
`fin_invoice`, `fin_expense`.

**Fix**: alias the `id` column.

```xml
<sql id="selectFinReceiptVo">
    select r.id, r.bill_no, r.amount, ...        -- WRONG: r.id OK, but
                                                   rest of columns
                                                   also ambiguous if
                                                   joined table has same name
    from fin_receipt r
    LEFT JOIN fin_partner p ON r.partner_id = p.id
</sql>
```

**Better fix (see Error 2)**: use `SELECT r.*` to avoid qualifying every
column manually.

### Error 2 — `Column 'X' in SELECT is ambiguous` (non-id)

**Cause**: even with `r.id` qualified, every other column in the
original `select` list is unqualified. Joined tables that share a
column with the main table (`status`, `source_type`, `remark`,
`create_by`, etc.) will trip this. Manually qualifying each one
(`r.bill_no, r.amount, ...`) is tedious and brittle.

**Fix**: replace the column list with `SELECT <main_alias>.*` plus
the joined columns as `AS <resultMap_property_name>` so the
`resultMap` binding still works:

```xml
<sql id="selectFinReceiptVo">
    select r.*
    , p.partner_name AS partner_name
    , ba.account_name AS bank_account_name
    , v.voucher_no AS voucher_no
    from fin_receipt r
    LEFT JOIN fin_partner p ON r.partner_id = p.id
    LEFT JOIN fin_bank_account ba ON r.bank_account_id = ba.id
    LEFT JOIN fin_voucher v ON r.voucher_id = v.id
</sql>
```

The `<main_alias>.*` syntax returns all columns of the main table
unambiguously. The `AS partner_name` aliases keep the column names
matching what the `resultMap` expects (your VO's
`<result property="partnerName" column="partner_name" />` still
binds correctly).

If you forget the `AS`, the joined columns will be returned under
their source-table names (`p.partner_name`, `ba.account_name`), the
`resultMap` won't bind them, and your VO's `partnerName` will be
null. Frontend will fall back to "id" via `row.partnerName || row.partnerId`,
and you'll debug the wrong layer.

### Error 3 — `Column 'X' in where clause is ambiguous`

**Cause**: `<if test="..."> and X = #{X}</if>` uses unqualified
column names. After adding LEFT JOINs, those columns are now present
in multiple tables and MySQL can't choose. This is **separate** from
Errors 1 and 2 — fixing the SELECT clause doesn't fix the WHERE.

Common offenders: `doc_id` (in `fin_receivable` AND `fin_payable` for
allocation), `receipt_id` (in `fin_receipt` AND via joins),
`voucher_id` (in `fin_voucher` AND via joins to `fin_receipt` etc.),
`partner_id` (in `fin_partner` AND joined `fin_partner`).

**Fix**: prefix every where-column with the main table alias.

```xml
<!-- WRONG after adding LEFT JOIN fin_partner p -->
<if test="partnerId != null"> and partner_id = #{partnerId}</if>

<!-- DO -->
<if test="partnerId != null"> and r.partner_id = #{partnerId}</if>
```

For `<select id="selectXxxById">` blocks (which use `where id = #{id}`
without alias), the `id` is still ambiguous after Error 1's fix.
Either alias it (`where r.id = #{id}`) OR change to `where <alias>.id = #{id}`.

## Canonical 11-VO batch fix recipe

When the user asks "make all finance list pages show names instead of
IDs", the work touches every VO/Mapper for every table with `_id`
foreign keys. For each:

1. **Inventory which tables have the join targets** (run a SQL
   query to confirm `fin_partner / fin_bank_account / fin_subject /
   fin_voucher / fin_invoice / fin_expense / fin_receivable /
   fin_payable / fin_receipt / fin_payment` exist and have the
   expected `name / no / code` columns).

2. **Add fields to VO** (with `@Excel(name = "...")` annotation
   matching existing style + getter/setter; one block of fields +
   one block of methods before `toString()`).

3. **Add `<result property="X" column="Y" />` to the resultMap** for
   each new field, in the same order as the SELECT columns.

4. **Replace `selectFinXxxVo` with**:
   ```xml
   select <main_alias>.*
   , <joined>.col1 AS col1
   , <joined>.col2 AS col2
   , ...
   from fin_xxx <main_alias>
   LEFT JOIN fin_yyy <alias_y> ON <main_alias>.fk_id = <alias_y>.id
   LEFT JOIN fin_zzz <alias_z> ON <main_alias>.fk_id = <alias_z>.id
   ```
   Use short aliases (`r`, `p`, `ba`, `v`, `s`, `inv`, `ex`) — pick
   one per table and be consistent. Watch for `fin_expense_item`
   where the main table is `ei` (not `e`) to avoid collisions with
   the `fin_expense` join alias.

5. **Bulk-prefix where-clause columns with main alias**:
   ```python
   import re
   aliases = {
     'FinReceipt': 'r', 'FinPayment': 't', 'FinAllocation': 'a',
     'FinCashFlow': 'f', 'FinExpense': 'e',
     'FinExpenseItem': 'ei',  # NOT 'e' — see step 4
     'FinInvoice': 'i', 'FinLedgerVoucherLog': 'l',
     'FinPayable': 'pb', 'FinReceivable': 'rv',
     'FinVoucherEntry': 've'
   }
   for fname, alias in aliases.items():
     text = open(f'src/main/resources/mapper/system/{fname}Mapper.xml').read()
     for col in ['id', 'create_by', 'create_time', ...]:  # all columns
       text = re.sub(r'(\s+and\s+)' + col + r'(\s*=)',
                     r'\1' + alias + '.' + col + r'\2', text)
     open(..., 'w').write(text)
   ```
   Run this BEFORE mvn package — fix all 11 mappers in one pass,
   then compile once. Don't iterate mvn build per mapper.

6. **Type-specific quirk — `FinAllocation` has `doc_type`-driven joins**:
   ```xml
   LEFT JOIN fin_receivable rcv ON a.doc_type='0' AND a.doc_id = rcv.id
   LEFT JOIN fin_payable pab  ON a.doc_type='1' AND a.doc_id = pab.id
   ```
   And the SELECT needs `COALESCE(rcv.doc_no, pab.doc_no) AS doc_no`
   because either join might match — depending on which doc_type
   the row has.

7. **Build, restart, curl-test each endpoint** for 500 errors:
   ```bash
   mvn clean package -DskipTests -pl jonlink-admin -am
   pkill -f jonlink-admin.jar
   java -jar jonlink-admin/target/jonlink-admin.jar > /tmp/jonlink.log 2>&1 &
   sleep 25
   TOKEN=$(curl -s -X POST http://localhost/prod-api/login \
     -H 'Content-Type: application/json' \
     -d '{"username":"admin","password":"admin123"}' | grep -o '"token":"[^"]*"' | cut -d'"' -f4)
   for ep in receipt/list payment/list expense/list item/list flow/list \
              receivable/list payable/list allocation/list voucher/list \
              entry/list log/list invoice/list; do
     curl -s -H "Authorization: Bearer $TOKEN" \
       "http://localhost/prod-api/finance/$ep?pageNum=1&pageSize=1" \
       | jq -r 'if .msg then "ERR: \(.msg[:100])" else "OK" end'
   done
   ```

8. **Verify the joined fields actually appear in JSON**:
   ```bash
   curl -s -H "Authorization: Bearer $TOKEN" \
     'http://localhost/prod-api/finance/receipt/list?pageNum=1&pageSize=2' \
     | jq '.rows[0] | {partnerName, bankAccountName, voucherNo}'
   # expect: {"partnerName":"<actual name>","bankAccountName":"<actual name>","voucherNo":null}
   ```
   If `null` for everything, the JOIN is matching nothing — usually
   the `WHERE` filter is dropping the join rows. Check that the
   join condition uses the correct column (`r.partner_id = p.id`
   not `r.partner_id = p.partner_id`).

## Frontend expectations

The frontend Vue files already need to display these new fields.
Pattern (already established across the finance module):
```vue
<el-table-column label="往来单位" prop="partnerName" min-width="160" show-overflow-tooltip>
  <template #default="{ row }">
    <span>{{ row.partnerName || row.partnerId || '-' }}</span>
  </template>
</el-table-column>
```

The `|| row.partnerId` part is critical: when JOIN returns null
(e.g. `partnerId=0` for system entries), the frontend falls back to
the ID rather than rendering a blank cell. **Always test the
fallback case in the browser** — build will pass even if you forget
the fallback, and a "blank cell" looks identical to "the JOIN
failed" without manual inspection.

## Why the watchEffect-style bug "id ambiguous" hides for a while

If you have any `<select id="selectXxxById">` block that uses
`where id = #{id}` (not `where r.id = #{id}`), it will FAIL with
Error 1 the first time someone hits the detail endpoint. But if
nobody hits detail (because the list page is the only thing people
use), Error 1 only shows up when you fix Error 2 first. So:

```
Fix Error 1 (alias r.id in SELECT)
   → Error 1 disappears, Error 2 appears (Column 'X' in SELECT is ambiguous)
Fix Error 2 (use r.* instead of column list)
   → Error 2 disappears, Error 3 appears (Column 'X' in where clause is ambiguous)
Fix Error 3 (prefix WHERE columns with alias)
   → everything works
```

The 3-step escalation is the diagnostic signature. If you see only
Error 1, you're not done. If you see Error 3, you've passed Error 2.

## Connection to other pitfalls

- **P40 / P42**: frontend "X empty cell" after backend change.
  Always verify BOTH layers — sometimes the JOIN is correct but the
  frontend forgot the `|| row.partnerId` fallback and the user
  reports "the column is blank", which they interpret as a backend
  bug when it's actually a frontend display issue.
- **Trap A in jonlink-mybatis-xml-pitfalls**: cross-mapper resultMap
  reference. Different bug class — that's about resultMap location,
  not column qualification. If you see "Result Maps collection does
  not contain value", that's P40 territory, not P44.

## Origin

This pattern was hit on jonlink 2026-08-20 when the user asked to
"make list pages show names instead of IDs, including backend JOIN".
11 VOs and 11 mappers were touched in one batch — the 3-error
escalation played out ~3 times in iteration before the recipe above
was pinned down. Saving here so the next module doesn't repeat the
3-error whack-a-mole cycle.