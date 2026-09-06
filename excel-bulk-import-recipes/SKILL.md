---
name: excel-bulk-import-recipes
description: "Use when user gives you an xlsx to import into a DB table."
license: MIT
metadata:
  category: backend
  version: "0.1.0"
---

# Excel/CSV Bulk Import into Existing CRUD Tables

End-to-end recipe for "user hands me an xlsx + tells me to put it into the system + maybe extend the schema to fit". Validated 2026-08-17 against `/opt/产品.xlsx` (69 rows of insurance products) → `jonlink_product` table on jonlink (RuoYi fork).

## When this skill applies

Trigger when ANY of these are true:
- User provides an `.xlsx`/`.xls`/`.csv` and says "导入", "写入", "入库", "填到 XX 表里"
- The target table exists already (no need to `jonlink-gen` from scratch — different skill)
- The xlsx columns **don't perfectly match** the DB schema → need to map/extend/infer
- User gives business rules in natural language ("下游政策 = upstream − 5", "这些产品不扣税") that must be encoded into rows
- Dictionary tables (insurance companies, channel providers) need new entries inferred from row content

If the table doesn't exist yet, use `jonlink-springboot-scaffold` instead — this skill assumes the table is live.

## Hard rules (read first)

1. **Never DELETE or DROP in unattended sessions.** Safety policies block these keywords and you lose data. Use `RENAME TABLE` for backups and let the import script INSERT only into an empty/empty-after-rename table.
2. **Never trust `pymysql.cursor.rowcount` for bulk inserts in a loop** — it returns the LAST execute's count (always 1 for single-row inserts). Verify with `SELECT count(*)` after commit.
3. **Never use `INSERT IGNORE` when a UNIQUE NOT NULL column has empty-string defaults.** All 8 rows will silently skip. Use `INSERT` + manual conflict resolution, or pre-clear the colliding values.
4. **For any Java file change touching >5 lines, prefer `write_file` of the complete corrected file over `patch`.** The patch tool can destroy leading-indentation in multi-line Java edits if `old_string` lacks full context — silent Java compile failure.
5. **Four files must change in lock-step when adding a column to a CRUD table** (domain / Mapper XML / frontend types / frontend page). Skipping any one = silent UI or API bug.

## The recipe

### Step 1: Inventory the xlsx

```bash
python3 -c "
import openpyxl
wb = openpyxl.load_workbook('<path>', data_only=True)
for s in wb.sheetnames:
    ws = wb[s]
    print(f'{s}: {ws.max_row} 行 x {ws.max_column} 列')
    for r in ws.iter_rows(min_row=1, max_row=min(ws.max_row, 5), values_only=True):
        print(' ', r)
"
```

Capture:
- Sheet name (often singular Chinese like `产品数据`)
- Header row (column names — these are your clue for mapping)
- Data rows count
- Per-column data distribution (use `Counter()` for categorical columns; for company names, count substring matches against a known list)

### Step 2: Compare xlsx columns to DB schema

For each xlsx column, decide:
- **Maps directly** to a DB column → use as-is in INSERT
- **Needs substring/format inference** (e.g. company name extracted from `产品名称`) → write a detector function
- **Has a derived value** (e.g. `down_rate = up_rate - 5`) → compute in Python, do not import
- **Has no target column** → add it (Step 3) OR drop it into `remark` as a pipe-delimited string

Document the mapping in a comment block at the top of the import script — future-you will thank present-you.

### Step 3: Extend schema if needed (RENAME-to-bak pattern)

Only do this if xlsx has columns that don't fit the existing schema.

```sql
RENAME TABLE <orig> TO <orig>_bak_$(date +%Y%m%d);

CREATE TABLE <orig> (
    ... copy ALL old columns from `DESC <orig>` ...
    <new_col> <type> NOT NULL DEFAULT '...' COMMENT '...',  -- inserted at the right position
    ... audit fields unchanged ...
    PRIMARY KEY (id),
    KEY idx_<existing> (<existing>)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- rollback is ONE statement away:
--   RENAME TABLE <orig> TO <orig>_broken; RENAME TABLE <orig>_bak_<yyyymmdd> TO <orig>;
```

### Step 4: Supplement dictionaries

If your xlsx references entities (companies, channels, types) that aren't in the dictionary tables, add them with proper codes. **Test for UNIQUE collisions first:**

```sql
-- Insert a test row to discover silent collisions
INSERT INTO <dict>(name, code, ...) VALUES ('test1', 'tmp_code', ...);
-- If "Duplicate entry '' for key 'uk_code'" → existing rows have empty code, can't bulk INSERT
-- Fix with three-step:
UPDATE <dict> SET code = 'tmp1' WHERE id = 1;
UPDATE <dict> SET code = '' WHERE id = 2;  -- clear the collision
UPDATE <dict> SET code = 'real_code', remark='已补 code' WHERE id = 1;
```

### Step 5: Write the import script (Python + pymysql)

The full template lives at `templates/import_products.py` in this skill — copy and adapt.

Key structure:
- `NAME_MAP` list — substring match table for dictionary inference
- `detect_company(name, intro)` — primary signal = `简介【】`, fallback = product name
- `parse_rate(s)` — strip `%`, `float()`, default to 0 on None
- Loop rows → build tuple → `INSERT` → `commit()` at end
- Final verification: `SELECT count(*), SUM(<constraint_check>), ...` — assert invariants

### Step 6: Run + verify

```bash
python3 /tmp/import_<table>.py 2>&1 | tail -20
# Verify in mysql directly:
mysql -h 127.0.0.1 -uroot -p<pwd> <db> -e "
  SELECT count(*) total FROM <table>;
  SELECT <group_col>, count(*) FROM <table> GROUP BY <group_col> ORDER BY 2 DESC;
  SELECT <constraint_col>, count(*) FROM <table> GROUP BY <constraint_col>;
"
```

Invariants to assert:
- `total == len(xlsx_data_rows)` (every xlsx row landed)
- `SUM(<constraint>) == total` (every row satisfies the business rule)
- `SUM(<other_constraint>) == total`
- All groups have non-zero counts (no orphans)

### Step 7: 4-file sync if schema changed

| File | Edit |
|---|---|
| `jonlink-{module}/.../domain/{Entity}.java` | field + `@Excel(name=..., readConverterExp="0=上游,1=下游")` + getter/setter + toString.append |
| `jonlink-{module}/.../resources/mapper/{module}/{Entity}Mapper.xml` | `<result>` in resultMap + column in `<sql id="...Vo">` + `<if test="...">` in INSERT + UPDATE blocks |
| `JonLink-Vue3-TS/src/types/api/{module}/{business}.ts` | add field to entity interface |
| `JonLink-Vue3-TS/src/views/{module}/{business}/index.vue` | `<el-table-column>` display + `<el-radio-group>` in dialog + `rules.<field>` + `reset()` initial value |

### Step 8: End-to-end verification gate

```bash
# Backend compile + jar
cd /opt/JonLink/JonLink-Vue
mvn -pl jonlink-{module} -am compile -q -DskipTests
mvn -pl jonlink-admin -am package -DskipTests -q
ls -la jonlink-admin/target/*.jar  # expect ~90MB

# Frontend build
cd /opt/JonLink/JonLink-Vue3-TS
./node_modules/.bin/vite build --mode production
ls dist/static/js/{business}-*.js  # expect new hash

# Restart + smoke test through real API
pkill -f jonlink-admin.jar; sleep 2
nohup java -jar /opt/JonLink/JonLink-Vue/jonlink-admin/target/jonlink-admin.jar > /tmp/jonlink.log 2>&1 &
sleep 30 && ss -tlnp | grep ":8080"  # expect 1 listener

TOKEN=$(curl -s -X POST http://127.0.0.1:8080/login -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}' | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")
curl -s "http://127.0.0.1:8080/{module}/{business}/list?pageNum=1&pageSize=3" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
# ↑ MUST show the new field in rows[0]
```

If API response is missing the new field:
- mapper XML `<result>` forgot the column → silent (query works, just returns null)
- domain field camelCase mismatch (e.g. `policyType` vs `policy_type`)
- types.ts field name doesn't match backend JSON key (case-sensitive)

### Step 9: Backup hygiene (don't forget)

The `_bak_YYYYMMDD` table is **one `RENAME` away from recovery** but should be dropped once prod has been stable for one release cycle:

```sql
-- After one release (or one week, whichever is longer), drop the backup:
DROP TABLE <table>_bak_YYYYMMDD;  -- only after verifying prod is healthy
```

## Pitfalls

| # | Pitfall | Symptom | Fix |
|---|---|---|---|
| A | `RENAME` is the only safe swap | `CREATE TABLE AS SELECT` loses indexes/auto_increment | Always `RENAME TABLE` |
| B | `pymysql` rowcount is LAST execute only | Loop of 69 inserts reports rowcount=1 | Verify with `SELECT count(*)` |
| C | `INSERT IGNORE` with empty-default UNIQUE | All 8 rows skipped silently | Pre-clear unique values or use `ON DUPLICATE KEY UPDATE` |
| D | patch tool destroys Java indentation | `@Excel` becomes 12-space nested | For >5-line Java edits, `write_file` full file |
| E | prod profile placeholder fails | `Could not resolve placeholder 'spring.datasource.druid.initialSize'` | Drop `-Dspring.profiles.active` (uses default yml) |
| F | jonlink-admin.jar location trap | ClassNotFoundException for new fields | Use `mvn -pl jonlink-admin -am package`, jar is at `jonlink-admin/target/jonlink-admin.jar` |
| G | Substring match collides (e.g. "太平洋" inside "太平洋产险") | Wrong company inferred | Use ordered NAME_MAP with `startswith()` or longer keys first |
| H | xlsx `data_only=True` for formulas | Formula cells return None instead of computed value | Always `data_only=True` AND re-save xlsx in Excel (LibreOffice formulas don't always evaluate) |

## Reference: Why this skill exists

The first jonlink-monolith-dev and jonlink-springboot-scaffold skills cover **building new CRUD tables** (generator, scaffolds). They do NOT cover **importing external data into existing tables**, which is a different lifecycle step that almost every jonlink module hits once it goes to production. Capturing the recipe prevents re-discovering `cur.rowcount` lies and `INSERT IGNORE` silent-skips every single time.

## Related skills

- `jonlink-springboot-scaffold` — building new CRUD tables from scratch (this skill assumes they exist)
- `jonlink-monolith-dev` — running the generator, hand-written CRUD conventions, BFF patterns
- `jonlink-mybatis-xml-pitfalls` — when the schema sync XML edit silently breaks the running jar
- `software-development/systematic-debugging` — for `mvn passes but API returns wrong` debugging
- `database-admin` — for backup/cleanup of bak tables after release cycle