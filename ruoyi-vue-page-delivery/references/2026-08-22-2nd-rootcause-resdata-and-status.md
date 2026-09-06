# 2026-08-22 第二次栽:列表不显示 + 菜单不显示

用户已经在 session 摘要里看过 handleQuery 修复(第一次栽),但**修复后再打开 `/policy/category/index` 还是显示"暂无数据"**,用户截图反馈。本节记录两个新的真根因。

## 真根因 #1:`res.data?.rows` vs `res.rows`

**现象**:API `/prod-api/policy/category/list` 返回 `{"total":5,"code":200,"rows":[...]}` (status 200, 1281B,total=5),但 `el-table` 永远显示"暂无数据"。

**RuoYi 拦截器源**(`src/utils/request.ts`):
```ts
service.interceptors.response.use((res) => {
  // ...
  return Promise.resolve(res.data)   // ← 业务层收到的 res 已经是 body
})
```

**业务码错写**:
```ts
// category/index.vue
function getList() {
  listPolicyCategory(quejlParams.value).then((res: any) => {
    categoryList.value = res.data?.rows ?? []   // res.data === undefined
    loading.value = false
  })
}
```

**正确写法**:
```ts
function getList() {
  listPolicyCategory(quejlParams.value).then((res: any) => {
    categoryList.value = res.rows ?? []   // 直接 res,不要再 .data
    total.value = res.total ?? 0
    loading.value = false
  })
}
```

**对照其它正常模块**(wx/account/index.vue):
```ts
accountList.value = response.rows   // 直接 .rows,印证拦截器已解包
```

**判别快测**:`performance.getEntriesByType('resource').filter(r => r.name.includes('X/list'))` 拿 status。200 + 表格空 = `res.data?.x` 误写。

## 真根因 #2:`sys_menu.status` 逆映射 + super-admin bypass 是错的

**两步踩**:
1. (踩) 我创建菜单时 `INSERT INTO sys_menu(... status ...) VALUES(... '1' ...)`,意图"启用"。但 RuoYi `sys_menu.status` 语义是 **`'0'` = 启用**、`'1'` = 停用(逆映射!)
2. (踩) 我以为 super-admin (user_id=1, role_id=1) 自动 bypass 不需要 `sys_role_menu`。但 `/getRouters` 调用的 `selectMenuTreeByUserId` SQL 仍是:
   ```sql
   where u.user_id = #{userId}
     and m.menu_type in ('M', 'C')
     and m.status = 0         -- ← filter 干掉 status='1' 的行
     AND ro.status = 0
   ```
   即使 user_id=1 也会走 user-role join,status='1' 的菜单被 filter 掉,**bypass 假设错的**。

**修复**:
```sql
UPDATE sys_menu SET status='0' WHERE menu_id BETWEEN 2500 AND 2530;

SET @rid_admin := (SELECT role_id FROM sys_role WHERE role_key='admin');
INSERT IGNORE INTO sys_role_menu(role_id, menu_id)
SELECT @rid_admin, menu_id FROM sys_menu WHERE menu_id BETWEEN 2500 AND 2530;
```

**判别快测**:
```bash
TOKEN=$(curl -s -X POST 'http://127.0.0.1:8080/login' \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"admin123"}' \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")

curl -s "http://127.0.0.1:8080/getRouters" -H "Authorization: Bearer $TOKEN" \
  | python3 -c "import sys,json;d=json.load(sys.stdin)['data'];
import sys; sys.stdout.write('\n'.join(c['meta']['title'] for grp in d for c in grp.get('children',[])))"
```
→ 出现"政策分类"= 路由已生效;没有=被 filter 掉。

**`sys_menu.status` 字段语义表**(RuoYi 反人类不统一):

| 表 | `'0'` | `'1'` |
|---|---|---|
| `sys_menu.status` | **启用(显示)** | 停用(隐藏) |
| `sys_user.status` / `sys_role.status` | 停用 | 启用 |
| `sys_dict_type.status` | 启用 | 停用 |
| 业务 `xxx.status`(自建) | 启用 | 停用 |

## 浏览器端验证四件套(修正版)

| # | 验证 | 失败排查 |
|---|---|---|
| 1 | scan_vue_handlers.py MISSING=[] | 参照其它同类 RuoYi 模块,补 handler 函数 |
| 2 | curl `/getRouters` | 不含菜单 = status 错或 bypass 假设错 |
| 3 | curl `/prod-api/X/list` | total=0 = 数据问题;total>0 但表格空 = res.data? 误写 |
| 4 | 真浏览器 e2e | console 无红 + form 完整 + 行数 == total |

## 同类下次自动避

- **新建菜单 SQL 必看 status='0'**:`DEFAULT '0'` 写死在 INSERT 里(或初始化后立即 `UPDATE ... SET status='0'`)
- **建业务表 `status`** 直接 `DEFAULT '0'` 也行(RuoYi 业务表用 0 启用)
- **业务层 list** 永远 `res.rows / res.total`,不写 `res.data`
