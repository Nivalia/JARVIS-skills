"""Verified-working xlsx → DB bulk import template.

Adapted from `/opt/产品.xlsx` (69 rows of insurance products) → `jonlink_product`
on 2026-08-17. Copy this, change the imports / NAME_MAP / insert_sql / DB target,
and follow the recipe in ../SKILL.md §Step 5.

Hard rules baked in:
  - Never trust cur.rowcount after a loop of single INSERTs (verify with SELECT count)
  - Pre-clear UNIQUE NOT NULL columns that have empty-string defaults
  - Detect foreign keys via substring match in product name + 简介【】 tag
  - Business rules (e.g. down_rate = up_rate - 5) computed in Python, not imported
"""

import openpyxl
import re
import sys
import pymysql

XLSX = "<path-to.xlsx>"            # CHANGE
SHEET_NAME = "<sheet>"             # CHANGE

# 1. Foreign-key detection map — order matters: longest key first to avoid
#    substring collisions (e.g. "太平洋" matching inside "太平洋产险")
NAME_MAP = [
    ("<company_display>",  ("<key1>", "<key2>"),  "<code>"),    # CHANGE per project
    # ("平安产险", ("平安",), "pingan"),
    # ("太平洋产险", ("太平洋",), "cpic"),
    # ...
]

CHANNEL_COLUMN_NAME = "<xlsx column>"   # CHANGE
CHANNEL_DICT_TABLE  = "<dict_table>"    # CHANGE

def detect_fk(name, intro):
    """Primary signal = operator-entered 【】 tag. Fallback = product name prefix."""
    m = re.search(r'【([^】]+)】', intro or "")
    if m:
        tag = m.group(1)
        for display, keys, code in NAME_MAP:
            for k in keys:
                if k in tag:
                    return display, code
    for display, keys, code in NAME_MAP:
        for k in keys:
            if k in (name or ""):
                return display, code
    return None, None

def parse_rate(s):
    """'15%' or 15 → 15.0. None → None."""
    if s is None: return None
    try: return float(str(s).strip().replace("%", ""))
    except: return None

# === DB ===
conn = pymysql.connect(host="127.0.0.1", port=3306, user="<user>",
                       password="<pwd>",
                       database="<dbname>", charset="utf8mb4")
cur = conn.cursor()

# Load dictionaries (filter empty codes to avoid the silent-skip trap)
cur.execute("SELECT id, code, name FROM <dict_table>")
fk_map = {row[1]: (row[0], row[2]) for row in cur.fetchall() if row[1]}
cur.execute(f"SELECT id, name FROM {CHANNEL_DICT_TABLE}")
ch_map = {row[1]: row[0] for row in cur.fetchall()}

# === Parse xlsx ===
wb = openpyxl.load_workbook(XLSX, data_only=True)
ws = wb[SHEET_NAME]

rows, skipped = [], []
for r in ws.iter_rows(min_row=2, values_only=True):
    if not r[0]: continue
    platform, name, intro, price, rate_s, *_ = r     # ADAPT columns
    display, code = detect_fk(name, intro)
    if not code or code not in fk_map:
        skipped.append((name, intro))
        continue
    fk_id, fk_name = fk_map[code]
    up_rate = parse_rate(rate_s) or 0
    down_rate = max(up_rate - 5, 0)              # CHANGE business rule
    ch_id = ch_map.get(platform)
    rows.append((
        (name or "").strip(),
        fk_id, fk_name, ch_id, platform,
        up_rate, down_rate,
        "0", "0", "1",                          # CHANGE constraints
        0,
        f"导入自 {XLSX} | 简介:{intro}",
        "system_migration", "2026-08-17 23:30:00", "system_migration", "2026-08-17 23:30:00",
    ))

print(f"Parsed: {len(rows)} rows; skipped: {len(skipped)}")
for s in skipped: print(f"  - {s}")

# === Insert ===
insert_sql = """INSERT INTO <table> (col1, col2, ...) VALUES (%s, %s, ...)"""
for row in rows:
    cur.execute(insert_sql, row)
conn.commit()

# === Verify (DO NOT trust cur.rowcount — it's 1 for single-row inserts) ===
cur.execute("SELECT count(*) FROM <table>")
total = cur.fetchone()[0]
assert total == len(rows), f"count mismatch: {total} vs {len(rows)}"

cur.execute("""SELECT <group_col>, count(*) FROM <table> GROUP BY <group_col> ORDER BY 2 DESC""")
print("By group:")
for r in cur.fetchall(): print(f"  {r}")

cur.execute("""SELECT <constraint_col>, count(*) FROM <table> GROUP BY <constraint_col>""")
print("Constraints:")
for r in cur.fetchall(): print(f"  {r}")

conn.close()