#!/usr/bin/env bash
# Verify that a MySQL container is using UTF-8 correctly and its init SQL
# data isn't double-encoded. Run against any jonlink-style MySQL instance.
#
# Usage: ./verify-utf8.sh [host] [port] [root_password]
# Defaults: 127.0.0.1 3306 jonlink_root_pwd

set -e

HOST="${1:-127.0.0.1}"
PORT="${2:-3306}"
PASS="${3:-jonlink_root_pwd}"

MYSQL="docker exec jonlink-mysql mysql -uroot -p$PASS"
HOSTMYSQL="mysql -h$HOST -P$PORT -uroot -p$PASS"

echo "=== 1. Check character set variables ==="
$HOSTMYSQL -e "
SHOW VARIABLES WHERE Variable_name IN (
  'character_set_client',
  'character_set_connection',
  'character_set_results',
  'character_set_server',
  'character_set_database'
);" 2>&1 | grep -v "Warning"

BROKEN=0
for var in character_set_client character_set_connection character_set_results; do
  val=$($HOSTMYSQL -N -e "SHOW VARIABLES LIKE '$var'" 2>/dev/null | awk '{print $2}')
  if [ "$val" != "utf8mb4" ]; then
    echo "  ❌ $var = $val (expected utf8mb4)"
    BROKEN=1
  fi
done

if [ $BROKEN -eq 0 ]; then
  echo "  ✅ All connection charsets are utf8mb4"
fi

echo ""
echo "=== 2. Check for double-encoded data ==="
RESULT=$($HOSTMYSQL -N -e "
SELECT
  CONCAT(tbl, ': ', double_encoded, '/', total)
FROM (
  SELECT 'sys_menu' AS tbl, COUNT(*) AS total,
    SUM(CASE WHEN HEX(SUBSTRING(menu_name, 1, 1)) IN ('C3', 'C2') THEN 1 ELSE 0 END) AS double_encoded
  FROM sys_menu
  UNION ALL
  SELECT 'sys_role', COUNT(*),
    SUM(CASE WHEN HEX(SUBSTRING(role_name, 1, 1)) IN ('C3', 'C2') THEN 1 ELSE 0 END)
  FROM sys_role
  UNION ALL
  SELECT 'sys_dict_type', COUNT(*),
    SUM(CASE WHEN HEX(SUBSTRING(dict_name, 1, 1)) IN ('C3', 'C2') THEN 1 ELSE 0 END)
  FROM sys_dict_type
) t;
" 2>/dev/null)

if echo "$RESULT" | grep -q ": [1-9]"; then
  echo "  ❌ Double-encoded data found:"
  echo "$RESULT" | sed 's/^/    /'
  exit 1
else
  echo "  ✅ No double-encoded rows"
  echo "$RESULT" | sed 's/^/    /'
fi

echo ""
echo "=== 3. Visual check (Chinese should display correctly) ==="
$HOSTMYSQL -e "
SELECT menu_id, menu_name FROM sys_menu WHERE menu_id IN (1, 2, 100, 105);
" 2>/dev/null

echo ""
echo "=== All checks passed if no ❌ above ==="