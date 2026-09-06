# RuoYi Code Generator — End-to-End Recipe

The RuoYi code generator (`/tool/gen`) is the **fastest path** from "I have a MySQL table" to "I have a working CRUD page with menu, role permissions, and Vue UI". This reference is the exact step-by-step.

## Endpoints (no UI needed)

```
# 1. Login (need an admin token)
POST /login  body= {"username":"admin","password":"admin123"}
→ returns {"token":"eyJ..."}

# 2. Import a real table into the generator
POST /tool/gen/importTable?tables=jl_follow_up&tplWebType=element-plus
→ 200 with no body, registers the table

# 3. (Optional) Edit column display flags via the edit endpoint
GET /tool/gen/{tableId}  → returns info + rows + tables

# 4. Generate and download
GET /tool/gen/download/{tableName}  → returns jonlink.zip
```

## What the zip contains

After `unzip jonlink.zip` you'll see exactly:

```
main/java/com/jonlink/<pkg>/controller/JlFollowUpController.java
main/java/com/jonlink/<pkg>/domain/JlFollowUp.java
main/java/com/jonlink/<pkg>/mapper/JlFollowUpMapper.java
main/java/com/jonlink/<pkg>/service/IJlFollowUpService.java
main/java/com/jonlink/<pkg>/service/impl/JlFollowUpServiceImpl.java
main/resources/mapper/<module>/JlFollowUpMapper.xml
upMenu.sql                                  ← sys_menu inserts + 5 buttons
vue/api/<module>/<business>.js              ← axios: list/get/add/update/del
vue/views/<module>/<business>/index.vue     ← Element Plus CRUD page
```

All in one zip, ready to drop into the project.

## Integration recipe (after unzip)

```bash
# 1. Copy Java sources to your module (replace default `com.jonlink.system`)
cp -r main/java/com/jonlink/system/*  /opt/jonlink/backend/jonlink-<module>/src/main/java/com/jonlink/<module>/

# 2. Copy XML mapper to resources
cp main/resources/mapper/system/* /opt/jonlink/backend/jonlink-<module>/src/main/resources/mapper/<module>/

# 3. Copy Vue files into admin-web
cp vue/api/<module>/<business>.js        /opt/jonlink/admin-web/src/api/<module>/
cp vue/views/<module>/<business>/index.vue /opt/jonlink/admin-web/src/views/<module>/<business>/

# 4. Run the menu SQL against the DB (registers menu + 5 buttons)
docker exec -i jonlink-mysql mysql -uroot -p<pwd> jonlink < upMenu.sql

# 5. Rebuild backend, restart vite, verify
mvn -pl jonlink-admin -am package -DskipTests
java -jar jonlink-admin/target/jonlink-admin.jar
```

After backend restart, the menu appears in the sidebar (the `<business>Menu.sql` insert added the `sys_menu` row with `parent_id` pointing at the default top-level "系统工具" — see customization below).

## Quirks and how to customize

### Package name hardcoded in `generator.yml`

`backend/jonlink-generator/src/main/resources/generator.yml`:
```yaml
gen:
  packageName: com.jonlink.system  # ← generator default
```

The import form lets you override per-table (field "生成包路径"). If you always generate business code in `com.jonlink.insure`, edit `generator.yml` once and rebuild the generator jar.

### Menu parent_id hardcoded to "系统工具" (id=3)

The `vm/sql/sql.vm` template has `parent_id = '3'` baked in. If your business module's top-level menu is id=2000 (投保入口) not 3, edit the .vm template:

```bash
# Find the hardcoded line
grep -n "parent_id" backend/jonlink-generator/src/main/resources/vm/sql/sql.vm
# Replace '3' with your module's top-level menu id (or use a placeholder)
```

After editing, rebuild `jonlink-generator` jar and restart backend.

### Menu path defaults to `/system/<business>`

`vm/sql/sql.vm` also bakes `path = '<business>'` and `component = 'system/<business>/index'`. To get `/insure/<business>`, edit the .vm similarly. Without this fix, your generated Vue page lands under `/system/<business>` and may 404 if the router's `/system` guard requires different role.

### Generator outputs Element Plus only — not Vant, not Antd

If you need an H5/mobile page, the generator doesn't help. Hand-write the Vue page (use the Element Plus version as a structural reference), and copy just the Controller/Service/Mapper from the zip.

### Generator's "tplCategory" — pick the right one

- `crud` (default): list + add/edit dialog + delete + export. ~80% of cases.
- `tree`: adds a tree sidebar with category tree + nested list.
- `sub`: master-detail (e.g. order + order items). Adds a `sub-domain.java.vm`.
- For master-detail with multiple children, generator falls short — hand-write.

### Toggling `query`/`list`/`edit`/`insert` per column

On the generator's edit page, each column has checkboxes:
- `query`: appears in the search form
- `list`: appears as a column in the table
- `edit`: editable in add/edit dialog
- `insert`: included in add form (defaults true if edit is true)

For dropdown columns, set `dictType` to a `sys_dict_type.dict_type` value (e.g. `jl_category`) — the generated Vue will render an `<el-select>` with options fetched from `/system/dict/data/type/<dictType>` automatically.

## Verifying the generated code works

After copying to your module:

```bash
# Compile-check
mvn -pl jonlink-admin -am compile -DskipTests
# expect: BUILD SUCCESS, no compile errors

# Run
java -jar jonlink-admin/target/jonlink-admin.jar
# expect: "JonLink 启动成功" banner

# Login + verify the menu appears in the sidebar
TOKEN=$(curl -s -X POST http://localhost:8080/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"admin123"}' | jq -r .token)
curl -s http://localhost:8080/getRouters -H "Authorization: Bearer $TOKEN" \
  | jq '.data[].children[].path' | grep -i <business>
# expect: "<business>" appears

# Hit the new endpoint
curl -s "http://localhost:8080/<module>/<business>/list?pageNum=1&pageSize=5" \
  -H "Authorization: Bearer $TOKEN"
# expect: 200 with `{"total":0,"rows":[],"code":200}` if table empty
```

## Re-running the generator

If you change the schema and re-generate, the new `<business>Menu.sql` will APPEND a duplicate menu row (because `@parentId := LAST_INSERT_ID()` always returns the latest id). To avoid this:

1. `DELETE FROM sys_menu WHERE menu_name = '<business>菜单';` before running
2. Or `TRUNCATE sys_menu;` and re-import the original `jonlink_init.sql` + all generated menu files