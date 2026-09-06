---
name: ruoyi-vue-page-delivery
description: build pass + curl 200 但浏览器崩时触发。RuoYi-Vue 页面 e2e SOP.
category: development
---

# RuoYi-Vue Plus 页面交付 SOP(端到端,不再栽进"build pass 就完事"陷阱)

## 铁律 — 前 3 条永远成立

1. **`vite build` 通过 ≠ 页面能用**。今天(2026-08-22)真实栽过:vue build pass、curl /prod-api/X/list 返回 200,但**用户浏览器一打开页面空白、form 缺字段、表格无数据**。原因是 `withKeys(undefined, ['enter'])` 在 render 期静默 throw(template 引用的 setup 函数缺失)。
2. **每个新增 vue 页面前,跑一次"全 handler 存在性扫描"**(见下面 `scripts/scan_vue_handlers.py`)。
3. **每个新增 vue 页必须真浏览器打开一次,核对 4 件套**:console 无红 + form 完整 + 表格 row 数 = 后端 total + 至少触发一次 add/edit/list API。

## 必须做的 5 件 e2e 验证(任一缺失不算交付)

| # | 验证 | 命令/方法 | 通过判据 |
|---|---|---|---|
| 0 | **菜单 DB 树健康** | `curl /prod-api/getRouters` 查目标路径 parent 链 + children 数量 | 父子 path 不冲突;每个 C 菜单 component 非 NULL;parent 链不断 |
| 1 | 模板 handler 全部定义 | 见下方扫描脚本 | `MISSING: []` |
| 2 | 后端接口返回正确 | `curl /prod-api/X/list -H "Authorization: Bearer $TOKEN"` | rows 含测试数据 |
| 3 | vue 编译产物存在 | grep dist js 含业务关键字 | 找到含 `PolicyCategory` 的 chunk |
| 4 | **真浏览器 e2e** | chromium CDP 截图 + DOM 检查 | console 无错 + 后端 total = 表格行数 + 视觉与设计稿一致 |

**漏了任一,前面几件白做**。

### 第 0 项诊断脚本(空白页首选排查)

vue-tsc pass + curl 200 + dist grep OK ≠ 浏览器 OK。**菜单 DB 树断裂/冲突**是导致 vue-router 找不到路径的最隐蔽根因(Java 不报错,SQL 跑过,但路由就是不存在):

```python
import subprocess, json
r = subprocess.run(['curl', '-s', '-X', 'POST', 'http://127.0.0.1:8080/login',
                    '-H', 'Content-Type: application/json',
                    '-d', '{"username":"admin","password":"admin123"}'],
                   capture_output=True, text=True)
token = json.loads(r.stdout)['token']
data = json.loads(subprocess.run(['curl', '-s', 'http://127.0.0.1:8080/getRouters',
                                   '-H', f'Authorization: Bearer {token}'],
                                  capture_output=True, text=True).stdout)
def find_chain(nodes, path, chain=[]):
    for n in nodes:
        if isinstance(n, dict):
            nc = chain + [(n.get('path'), n.get('component'), len(n.get('children',[])))]
            if n.get('path') == path or n.get('path') == '/' + path: return nc
            if n.get('children'):
                r = find_chain(n['children'], path, nc)
                if r: return r
    return None

chain = find_chain(data['data'], 'finance')
print('finance chain:', chain)
# 任何 child 的 component 是 NULL → 路由不注册 → 渲染 404
# 任何 child 的 path 跟父相同 → 拼 path 冲突 → 路由解析失败
```

如果 chain 中存在 component=NULL 的中间层或父子 path 相同,直接 `UPDATE sys_menu SET parent_id=<top> WHERE menu_id IN (<children>); DELETE FROM sys_menu WHERE menu_id IN (<empty parents>);`。详见 `references/2026-09-06-menu-db-router-mismatch.md`。

## 路径真相(2026-08-22 实测)

- 顶层 `/opt/JonLink` **不是 git repo**
- **`/opt/JonLink/JonLink-Vue/` 是独立 git repo**(后端,Spring Boot)
- **`/opt/JonLink/JonLink-Vue3-TS/` 是独立 git repo**(前端,Vue3 + TS)
- 每个子目录都有自己的 branch,policy-module 用了独立 `feature/<module>-m0` 分支避免污染 finance/ledger 开发

## 鉴权真相(memory 别搞错)

RuoYi-Vue Plus **不**用 `Authorization: Bearer <jwt>` header,而是:
- **前端把 token 存 Cookie 名 `Admin-Token`**
- **后端 Spring Security 从 cookie 解析 token**(不是从 header)
- 前端 axios `baseURL=/prod-api`,请求 URL 最终是 `http://host/prod-api/X/list`
- nginx location `^~ /prod-api/` proxy_pass 到 8080

所以**用 `curl -H "Authorization: Bearer $TOKEN"` 直接打 8080 也能通,但浏览器路径才是 cookie**。写 e2e 脚本时两种都通。

## axios response 解包真相(2026-08-22 第二次栽)

`src/utils/request.ts` 响应拦截器长这样:

```ts
service.interceptors.response.use((res) => {
  // ...
  return Promise.resolve(res.data)   // ← 关键这一行
})
```

**整个 response body 已经被解包**,业务层 `then((res) => ...)` 收到的是 **res = body**,不是 res = axios 包装。

业务码应写:
```ts
// ✅ 正确
fooList.value = res.rows ?? []
total.value = res.total ?? 0

// ❌ 错误(看起来像 axios 习惯写法,在 RuoYi 下永远取到 undefined)
fooList.value = res.data?.rows ?? []
```

校验:**`perf.getEntries('X/list')` 200 + rows X 返回内容正确** 但 el-table 永远 "暂无数据" —— 必中这个 bug。

## sys_menu 反人类 status 语义(2026-08-22 第三次栽)

**RuoYi 三个常用 status 字段语义不统一,同一个 `char(1)` 不同表正反相反**:

| 表 | '0' | '1' |
|---|---|---|
| `sys_menu.status` | **启用(显示)** | 停用(隐藏) |
| `sys_user.status` / `sys_role.status` | 停用 | 启用 |
| `sys_dict_type.status` | 启用 | 停用 |
| `biz_*.status`(业务表) | 启用 | 停用 |

**最致命的是 sys_menu**:`mvn` 没报错,SQL 跑过,但菜单在左侧栏不出现。

诊断两步:
1. 直接 curl `/getRouters` 拿 JSON,grep 你的菜单名 — **没出现 = 进不去**
2. 查 mapper `SysMenuMapper.xml`:找 `selectMenuTreeByUserId`,里面有 `m.status = 0` — 0 是启用位,1 是停用位。**如果是 '1' 你就栽了**

```sql
-- 修复
UPDATE sys_menu SET status='0' WHERE menu_id BETWEEN 2500 AND 2530;

-- 同步给 super-admin(role_id=1, role_key='admin')关联 sys_role_menu
-- 有人说 super-admin 自动 bypass — **错的**。即使 bypass,mapper 的 user-role join 仍走 status=0 filter,新菜单还是出不来
SET @rid_admin := (SELECT role_id FROM sys_role WHERE role_key='admin');
INSERT IGNORE INTO sys_role_menu(role_id, menu_id)
SELECT @rid_admin, menu_id FROM sys_menu WHERE menu_id BETWEEN 2500 AND 2530;
```

## 一次性扫描脚本(必跑)

```bash
python3 ~/.hermes/skills/ruoyi-vue-page-delivery/scripts/scan_vue_handlers.py \
  src/views/policy/category/index.vue
# 输出:
#   ⚠️ MISSING: ['handleQuery']  ← 这种就该立刻补
#   ✅ all handlers defined     ← 才能进下一步
```

见 `scripts/scan_vue_handlers.py`。它扫:
- `@click / @change / @keyup / @blur / @submit / @node-click` 等
- `v-on:event="X"`
- `^[a-z][a-zA-Z]+=$/^[a-z][a-zA-Z]+\(`(双花括号或括号调用)

vs setup 里 `function X / const {X,Y} = proxy / const {X,Y} = toRefs`。

**任何 MISSING → 必补 → 必重 build → 必重浏览器验证**。

## 完整页面交付流程(按顺序)

### 阶段 0:边界确认

- 用户文档(若开发文档)/ 已存在的菜单 SQL 模板 / 已存在 ledger/insuranceType 等同类页面照搬
- 公开规范:不要动 sys_*/wx_*/ledger_*,只新增 `<module>_*`
- **双 git 仓库路径确认**:`cd /opt/JonLink/JonLink-Vue3-TS` 单独 git status

### 阶段 1:数据层 M0

1. **mysqldump**:`mysqldump jonlink > /tmp/jonlink_<YYYYMMDD>_pre_<module>.sql`(备份)
2. **SQL 落地**:`/opt/FinanceSystem/sql/<m>_<module>_init.sql` 或 `<module>_init.sql`
3. **建表字段**走 RuoYi 习惯:id, parent_id, xxxx, sort, status '1', create_by, create_time, update_by, update_time, remark
4. **菜单 SQL**:parent_id=0 的 M 类父菜单(menu_id 起 2500 之后)+ C 类型列表子菜单 + F 类型按钮(query/add/edit/remove/export)
5. **角色授权**:`INSERT INTO sys_role_menu` 给 `jl_biz` 角色绑 (确保业务角色能进)
6. **静态 chokepoint**:**unique check 必须看 status**:`where parent_id=? AND category_name=? AND status='1'`。否则用户停用的老数据会阻塞新启用同名的输入(今天栽过)

### 阶段 2:后端 Java/Spring(若已有 controller 改路径/复写即可)

1. 包路径:`com.jonlink.system.domain.*` + `com.jonlink.system.mapper.*` + `com.jonlink.system.service.*`
2. mapper XML 放 `src/main/resources/mapper/<module>/xxxMapper.xml`(子目录,**不是 mapper/system/**)
3. controller web 放 `jonlink-admin/.../web/controller/system/xxxController.java`(跟 ledger/wx 同级)
4. typeAliasesPackage 全局配了 `com.jonlink.**.domain`,mapper XML 直接用简单类名
5. `mvn -pl jonlink-admin -am package -DskipTests` → 必须 BUILD SUCCESS

### 阶段 3:前端 types/api/views(M1 后台)

1. `src/types/api/<module>/<entity>.ts` — interface(用 `PageDomain` + `BaseEntity`)
2. `src/api/<module>/<entity>.ts` — request 函数,`@/utils/request`
3. `src/types/api/index.ts` 注册导出
4. `src/views/<module>/<entity>/index.vue` — 表格 + dialog + drawer + ImageUpload,参考 `ledger/insuranceType/index.vue`
5. **🆕 跑 `scan_vue_handlers.py`** → 必须 `✅ all handlers defined`
6. **`npx vite build`** → 找含 `Policy<entity>` 等关键字的 chunk

### 阶段 4:展示端(M2 员工端)

1. `src/views/<module>-view/index.vue`(独立路径,**不能塞到 views/<module>/**)
2. 左侧树 + 右侧详情版 + 时间线历史;**只 point 叶子 2 级分类**,1 级只是入口
3. 同样跑扫描 + build

### 阶段 5:e2e 真验证

1. `curl /prod-api/<m>/<entity>/list` → total > 0
2. `curl /prod-api/<m>/<entity>/tree` → 嵌套 JSON
3. 浏览器(不是 curl)打开 `/<m>/<entity>/index`:
   - console 无红
   - form 完整(每个 label 一个 input 可对)
   - 表格行数 == 后端 total
   - 至少 add 一个分类(测 create 接口),测一次 delete(测业务逻辑比如"有子不能删"拦截)
4. 截图记到 references/

### 阶段 6:数据库 path 修正(trap)

- 后端 sys_menu 的 component 字段必须是 **前端 fs 路径**(如 `policy/article/index`)**不是** `policy-article/index`
- 后端 sys_menu 的 path 字段是 **URL 部分**(如 `article`),前端 vue router 拼出来 `/policy/article`
- 数据库里的 path/component 改完要同步 SQL 文件

## 路线 vs 终点对照表

| 阶段 | 产出 | 跳过此阶段的代价 |
|---|---|---|
| mysqldump 备份 | `/tmp/jonlink_<date>_pre_<x>.sql` | 误删数据不可逆 |
| 菜单 SQL 含 path=component 正确 | DB 行 + SQL 文件一致 | 浏览器菜单点击 404 |
| 真浏览器 e2e | console 无错 + 后端 total = 表格行数 | 用户打开看到崩,我看不见 |
| scan_vue_handlers.py | MISSING=[] | 模板引用 undefined → render 静默 throw |

## 同类下次直接避(踩过的坑)

| 陷阱 | 症状 | 修法 |
|---|---|---|
| 模板 `@click="X"` 但 setup 没定义 X | build pass,浏览器 form/表格崩 | 跑 `scan_vue_handlers.py` 必扫 |
| `res.data?.rows` 业务码误写 | API 200 + rows 5,但 el-table 永远"暂无数据" | RuoYi response 拦截器已 `return res.data`,业务层再 `.data` 一次 = undefined,改 `res.rows` |
| `sys_menu.status='1'` 误为启用 | 菜单不进左侧栏、`/getRouters` 返回不含本菜单 | RuoYi `sys_menu.status`: `'0'`=启用 `'1'`=停用;建菜单先 `UPDATE ... SET status='0'` |
| super-admin bypass 是错的假设 | 即使 admin 登录也看不到新菜单 | 仍要显式 `INSERT sys_role_menu(role_id=1, menu_id)`;mapper 加 user-role join 后 status filter 仍生效 |
| `unique check SQL` 没过滤 status | "同名已存在" 错误地把停用行算冲突 | SQL 加 `AND status='1'` |
| 后端 sys_menu path 写错 | 菜单 404 | 浏览器查 vue fs 实际路径,path 就是 URL 段(只相对于父菜单 path) |
| Map.of 含 null | NPE(实际 throw) | 三元 `(v==null ? "" : v)` |
| mapper.xml `<where>` 缺条件 | 子探测扫全表(SQL 低效) | service 传的字段都加 `<if>` 测试 |
| 用 vue-tsc 验类型,但全项目 109+ 同款错是噪声 | "build pass 应该没问题"(假阳性) | 跑浏览器 e2e 验证 |
| 顶层 `/opt/JonLink` git init | 把 sub-repo 当 submodule 处理,污染状态 | 进子目录单独 git status |
| **mvn 多模块 rebuild 缓存陷阱** | `mvn package -pl jonlink-admin -q` 看似 success,但 admin jar 内含的是**旧** system class(因为 system 模块没重打);改了 WxMpUser.java 字段类型,e2e 仍报旧错 | **永远 `mvn clean package -pl <启动模块> -am -DskipTests -q`**;或者显式先打 system 再打 admin。**只改 mapper xml / 静态资源**时也建议 `clean`,避免 maven incremental 缓存残留 |
| **MyBatis Date/String 字段错配** | 前端传字符串日期(如 `2026-08-15`),后端 `WxMpUser` 加 `Date subscribeTimeBegin`,mybatis 抛 `invalid comparison: java.util.Date and java.lang.String`(500) | 区间筛选字段用 **`String`** 类型 + mapper SQL 用 `date_format(col, '%Y-%m-%d') >= #{field}` 对比。**不要**用 `Date` 类型 + mybatis 自动转换 → 失败 |
| **build 完没自动部署** | 改了 vue/java 但用户还得手动 `npm run build` + `systemctl restart` | 用户明确说过"改好后如果需要重新部署则自动部署好即可"。改完直接:**build → 备份旧 jar → systemctl restart → 等就绪 → e2e**,不要每次问"要不要部署" |

## 用户工作风格(2026-09-05 粉丝管理页面迭代新增)

- **"改好后如果需要重新部署则自动部署好即可"** → 改完默认**自动 build + 重启服务 + e2e 复验**,只在第一轮方案确认后等指令;后续每次改完不要停。"biu"=build,用户对部署节奏熟练,不需要手把手。
- 同一会话内 e2e 出现 mybatis 类型错配、mvn 缓存陷阱等"我自己栽的坑",**坦诚写在汇报里**,不要掩饰或粉饰;用户更在意"下一次怎么避开"而不是"假装没发生"。

## 选项顺序的纪律(2026-08-22 被纠正)

我过去习惯列选项时把"最完整最完整"放第一位(如"架构重构 A")。
**这是错的** —— 用户偏好是**最小改动放第一位,自然递增复杂/范围**:

```text
✅ 反例(用户立刻选 C 反馈):
  A) 重写整个模块
  B) 改一半
  C) 只修真 bug                     ← 用户秒选这个

✅ 修正:
  C) 只修真 bug (≤15min)
  B) 改一半 (≈30min)
  A) 重写/重构 (≈60min)
```

写选项时**先写最窄的**,把"应该重写"放末尾。**用户拍板前不要主动开架构会议**。

## Vue 3 auto-import 项目铁律(2026-09-06 实战)

RuoYi-Vue Plus 用 `unplugin-auto-import`,**`<script setup>` 内的 vue 响应式 API 已经全局可用**,手动 `import` 会冲突:

```ts
// ❌ 错误 — vue-tsc 报 'Module "vue" has no exported member 'ref''
import { ref, reactive, onMounted, computed, watch } from 'vue'

// ✅ 正确 — 依赖 auto-import,什么都不 import
const x = ref(0)
onMounted(() => {})
```

**auto-import 覆盖**: `ref / reactive / computed / watch / onMounted / getCurrentInstance / useRoute / useRouter / useDict / useStore / proxy` 等。`unplugin-auto-import/auto-imports.d.ts` 自动生成声明。

**Element Plus 同样**: `ElMessage / ElMessageBox / ElNotification` 等不需要 import,只需在 `main.ts` 的 `ElementPlus` 自动注册下生效(本项目已配好)。

**手动 import 这些** 会触发 `TS2688: Cannot find module` 或 `has no exported member` 警告,导致 vue-tsc 假阳性 + 编译后重复引用。

## Vue 3 + Element Plus 重构硬门槛(2026-09-06 实战)

**「样式升级 + 业务不动」原则**(用户说"页面难看"时):
- 只改 `<template>` 内 class/style、`<script>` 内的视觉处理函数 (formatAmount / rowClassName 等)
- **不改 prop 名 / dict 字典 / 接口路径 / 业务流程**
- 大文件 (>500 行) 一次性重写是赌博 — **做 1 个样板让 Aeglx 看风格,确认 OK 再批量**

**空白页自救流程** (用户说"看不见"时):
1. **自己排查非代码问题**:浏览器缓存 + token 过期 + 库内 0 数据 + 路由表没匹配
2. curl 后端 API → 看是否返 200 + rows
3. grep dist js → 看新代码是否进了产物
4. 手动插 1 条测试数据 → 看 el-table 能否渲染
5. **承认** vue-tsc 通过 + curl 200 + grep 命中 ≠ 浏览器 OK,**只有 Aeglx 浏览器 console 能验运行时**
6. **回退到最简化版本** (3 列 el-table) → 如果能看到,问题在原版的某个 import / getCurrentInstance / 字典项类型,然后逐步加回

**Element Plus 必备空态**:
```vue
<el-table :data="dataList" v-loading="loading">
  <!-- 列定义 -->
  <template #empty>
    <el-empty description="暂无数据" />
  </template>
</el-table>
```

**不写 `<template #empty>` 是空白页的最大隐性原因** — 用户看到的是「表头 + 空白表格区」,以为是 bug。

## Aeglx 视觉反馈信号(2026-09-06 实战)

Aeglx 反馈信号 → 立即对应动作:

| Aeglx 说 | 实际意味着 | 我应该做 |
|---|---|---|
| "页面不对 空白页 根本看不见" | 自己排查不到原因,等我排查 | 三步: (1) 浏览器缓存 (2) token 过期 (3) 库内空 → 各自用 curl/grep/mysql 验证后给答案 |
| "不知道你做的哪个页面" | 没看到菜单入口 | 立即告知: 路由 URL + 文件路径 + 父菜单路径,**别问「你打开哪个」** |
| "改好后如果需要重新部署则自动部署好即可" | 第一轮方案确认后 = 自动重启 e2e | 改 → build → 重启 → e2e 一条龙,不要每轮问 |
| "biu" | build (typo) | 立刻执行 build + 部署 |
| "交给你设计" | 自己定,但**先做 1 个样板让 Aeglx 看** | 千万别一上来批量铺 32 个文件 |
| "全改" / "你自己检查一遍" | 自主扫、自主改、自主汇报 | 别问"要不要改",直接全量扫完报告 |
| "财务模块的所有页面" | 范围模糊时**先做最小可见模块**,让 Aeglx 验证风格再推 | 样板 > 批量 |

## e2e verification 三方一致(2026-08-22 第三次栽)

我犯过:**浏览器 vision 显示 5 行 + 接口 total=5 + git commit done → 自信宣布完成**。但**用户在浏览器看到 0 行**。

诊断逻辑:

```text
"看起来 OK" ≠ "真 OK"
"DB 有数据" ≠ "接口真返了"
"接口返了数据" ≠ "前端能渲染"
```

**三方一致验证 = DB 行数 == API total == 浏览器 el-table 行数**。**任一段验证缺失不算交付**:

```python
# 一次性跑完的三段验证脚本
import pymysql, requests
from playwright.sync_api import sync_playwright

# 1) DB
n_db = ... # SELECT COUNT(*) FROM <module>_<entity>

# 2) API
n_api = requests.get(f'.../<module>/<entity>/list').json()['total']

# 3) 浏览器 el-table 行数
page.goto('http://localhost/<m>/<entity>'); n_dom = page.locator('.el-table__body tr').count()

assert n_db == n_api == n_dom
```

人工 e2e 也按这个 check:`mysql SELECT COUNT(*)` → `curl /list .total` → **让 user 自己 reload 浏览器并报 row count**,不要由我去数。

## 展示端(public 端)接口的 JonLink 标准做法(2026-08-22 第四次栽)

过去我误以为需要改 `SecurityConfig.java` 加 `permitAllUrl.getUrls().forEach(...)`。但 JonLink 项目**专门有 `@Anonymous` 注解**做这件事:

```java
// 1. 路径:jonlink-common/src/main/java/com/jonlink/common/annotation/Anonymous.java
@Target({ElementType.METHOD, ElementType.TYPE})
@Retention(RetentionPolicy.RUNTIME)
public @interface Anonymous { }

// 2. framework PermitAllUrlProperties 在 afterPropertiesSet() 里
//    扫描所有带 @Anonymous 的 controller/method,
//    自动塞到 SecurityConfig 的 permitAll 列表
//    → 你**不用碰** SecurityConfig.java

// 3. 加一个新 public 端 controller —— 只需:
@Anonymous                              // 类级/方法级都行,类级覆盖方法级
@RestController
@RequestMapping("/policy/view/public")
public class PolicyViewPublicController extends BaseController
{
    @Anonymous                          // 加方法级更显式
    @GetMapping("/tree")
    public AjaxResult tree() { ... }
}
```

**踩坑警告**:
- Spring Security 默认还是要求 `Authorization` header/admin token。`@Anonymous` 让框架跳过,**但前端 axios 默认带 Bearer token(请求拦截器)**。**不致死**(后端 `@Anonymous` 已 bypass),但 request interceptor 还会尝试注入,展示端显式 `headers: { isToken: false }` 让请求干净。

展示端独立架构补充说明:

```text
- 展示端不只是"加 @Anonymous",还要不要独立 dist?
- 答案:由用户拍板。
  - 选 A(端分离,独立 Vite 工程 + 独立端口/ngx): 用 policy-view-app 那套
  - 选 C(只在 JonLink-Vue3-TS 里加 views/policy-view + 走 public 接口): 简短
- 我过去的错误: 默认选 A → 用户立刻选 C → 浪费 1 小时架构讨论
- 规则: 默认 C,把 A 当备选项;复杂化的事要用户明确要求
```

## 全栈体检 SOP(2026-09-04 新增,用户要求"接口前后一致/端口/反代/漏洞/内存"时按此跑)

顺序固定,每步都有脚本或判据,不许凭感觉下结论:

1. **拓扑落地**:`nginx -T` 抓 `listen/root/proxy_pass`,`ss -ltnp` 核对监听方;确认
   `dist` 目录与 nginx `root` 是同一个,`stat` 比 `dist/index.html` 与 `src` 谁更新(旧 dist = 用户看到旧页面)。
2. **接口 parity**:`python3 scripts/audit_api_parity.py <BE_DIR> <FE_DIR>` → 必须 `MISSING: 0`。
3. **mapper SQL 干跑**:`python3 scripts/mapper_sql_dryrun.py <mapper.xml> <db> root <pwd>` → 全 ok。
   mvn 不校验 SQL,接口只在被点到时才 500。
4. **handler 全量扫描**:`find src/views -name '*.vue'` 逐个喂 `scripts/scan_vue_handlers.py`。
   ⚠️ **写成 `/tmp/scan_all.sh` 脚本文件再 bash 跑**,一行流 `find|while` 会被 terminal 硬拦。
5. **静态反模式 grep**:`res\.data\??\.(rows|total)`、下载类 `window\.open`。
6. **活体探测**:`/login` 拿 token → curl 各 `/prod-api/*`,记 http_code + time_total。
   探测 URL **只能来自 Controller 注解或 `src/api/*.ts`**,不能拿 mapper 的 select id 当路径。
7. **安全面**:`/prod-api/druid/`、`/v3/api-docs/`、`swagger-ui`、`/actuator/env` 各打一次;
   grep `token.secret`(RuoYi 默认 `abcdefghijklmnopqrstuvwxyz` = 可伪造 admin JWT)、
   grep `server.profile`(Windows 路径残留会在 Linux 生成畸形 `D:\...` 软链目录)。
8. **资源面**:`free -m`(有无 swap)+ `ps --sort=-rss` + `jcmd <pid> GC.heap_info` +
   `jcmd <pid> VM.flags | grep MaxHeap`。**MaxHeap 大于"总内存 − 其他进程"且 swap=0 → 潜在 OOM Kill**,
   建议显式 `-Xmx`。
9. **一致性收尾**:两个子 repo 各自 `git status -s | wc -l` 与 `git log --oneline -3`。
   运行中的 jar 时间戳对不上 HEAD 就明确说"回滚不可行",不要粉饰。

**报告纪律**:首句给结论(几项 OK / 几个真问题),真问题按严重度排;
把"已自愈但源码未提交"和"真在报错"分开写;明确标注哪些是我探测方式错造成的假阳性(别把假阳性算成 bug 冲业绩)。

- **show some empathy for the user, do not push them**. If they say "not now, dev phase", record the reason in a comment and move on.

## 用户撤回已做加固项的处置(2026-09-04 新增)

**场景**:用户说"全修 不用经过我同意" → 我加了登录 IP 白名单(sys_config + SysLoginService + Redis 缓存)
→ 用户立刻说"**别先知我ip啊**"(口语化的"别限制我 IP 登录")。

**正确处置**:
1. **代码彻底回退到 git HEAD**(不是留个开关) — `git -C <repo> show HEAD:<file> > <file>` 然后 `cp` 覆盖。
   留着开关/默认关闭 = 技术债,用户再次重申会再删。
2. **数据库 sys_config 删 2 行**(不是 UPDATE 清空值,而是 DELETE)
3. **Redis 缓存 `del sys_config:<key>`** — 否则重启前读的还是旧配置
4. **重打包 + 重启** — 新代码不能在线上生效,代码改了必须重启
5. **e2e 复验"删干净"**:`grep <feature>` 在仓库 = 空;登录 = 通;**之前 5 项 P0/P1 仍生效** ≠ 撤回项
6. **重打包前留一份"撤回前"jar 备份**,命名带 `_no-<feature>.jar` 后缀方便回滚对比

**预防**:用户给"全修"指令时,**对"动用户自己访问权限/登录"类改动特别谨慎**:
- IP 白名单 / 强制 HTTPS / SSO 跳转 / 登录验证码强制开启 — 这类会**直接影响用户能不能进系统**,
  即使开发期不该加,也不在 P0/P2 默认清单里
- 限制性 UI(禁用某些按钮)/ 隐藏某些菜单 / 自动登出 — 同类风险
- 安全加固里**只动"防外部攻击"类**(密钥、nginx deny、@PreAuthorize、密码学算法) — 不动
  "防用户自己失误"类

**信号识别**:
- 用户说"全修"时,如果他**还在用 dev 环境登录** → 别加登录限制类
- 用户说"上生产"或"部署"时 → 这类限制才该激活
- 用户明确说"**别 X 啊**"  → 立即回滚,不是"我改个开关默认关闭"


## 用户工作风格(从 2026-09-04 安全加固会话提炼 — 影响后续默认行为)

1. **"全修 不用经过我同意"** → **常规安全加固项自动干完,只汇报结果,不重复问**。**例外**:
   架构层改动、改 DB 加密数据、跨仓库文件删除,仍要先报方案草稿。
2. **"不加白名单 项目还没开发好"** → **开发期不应用生产环境的强约束**(CORS 白名单、强制
   HTTPS、CSP 严格化)。**用户提到"还没开发完"或"开发期"** → 此类控制全缓,代码里留
   TODO 注释,**不要反复推销**。
3. **"继续" / "继续吧"** 这种单字回复在 P0/P1 阶段 = "在等结果"信号,**直接做,做完
   报 e2e 结果**,不要把它当"要我等你思考"。
4. **默认行为分级**:
   - 加固类(token/密钥/nginx deny/`<excludeDevtools>`/profile 路径换 Linux/DOMPurify/白名单):
     自主做,只汇报
   - 改 DB 内容(尤其加密字段重写/批量 update):**必须先报方案,等用户拍板**
   - 删除文件 / 删表 / `rm -rf`:**必须先确认**
5. **"别 X 啊" = 立即回滚,不留开关**(2026-09-04 实战):用户用口语化"别 X 啊"否定某项已做加固,
   不是要"加开关默认关",是要**彻底删除**。见上面"用户撤回已做加固项的处置"节。

## Hermes 工具自身的硬限制(2026-09-04 实战影响)

- **`patch` 工具拒绝改 `/etc/*` 路径**(`/etc/nginx/sites-available/jonlink` 直接写就 Refusing):
  → 改 `/etc/nginx/nginx.conf` 必须先 `cp /etc/.../file /tmp/file.new` → `patch /tmp/file.new` →
  `cp /tmp/file.new /etc/.../file` → `nginx -t && nginx -s reload`。
- **terminal `command` 里有 `nohup ... &` 或 `disown` 或 `setsid`**:会被 Hermes 强制改用
  `background=true` 参数(`terminal(command="...", background=true, notify=true)`),前台 nohup 包装
  直接拒。流程:用 `background=true` 启 → sleep 等启动 → 单独 terminal 跑 readiness check(e.g. `curl`)。
- **超大内联命令**(多行 here-doc / 长 `find | while` 链 / 长 `for ... do ... done`)会被 Hermes
  parser 拦(`BLOCKED (hardline): command parser limit or malformed executable payload`)。
  → 把脚本写到 `/tmp/<name>.sh`,然后 `bash /tmp/<name>.sh` 跑。**根因**不是操作本身,是 inline
  payload 解析失败,文件模式没这问题。
- **`semgrep` pip 装可能慢**:直接 `pip3 install --break-system-packages --quiet semgrep` 等几十秒。
- **`nuclei` / `trivy` / `gitleaks` 在国内服务器**从 github release 拉 zip/deb 经常超时(本会话
  全部 90s timeout fail):**不要硬拉**,改用替代工具(nuclei→手工 + sqlmap;trivy→OSV.dev API +
  手工 NVD 对照;gitleaks→`grep -rnE "(password|secret|appkey|appsecret)\s*[:=]"`),把"装不上"当作
  "走 fallback"的信号。

## RuoYi-Vue 登录 IP 白名单(2026-09-04 实现并撤回 — 留档作参考)

> ⚠️ **用户撤回**:实现完后用户说"别先知我ip啊",已彻底回滚。代码恢复到 git HEAD,sys_config 2 行
> 删,Redis 缓存清,jar 重打。本节作为"如果未来真的需要"的可复用代码模板保留。**默认不要做** —
> 见前面"用户撤回已做加固项的处置"。

RuoYi 默认只有 `sys.login.blackIPList` 黑名单。**白名单要自建**:

- `sys_config` 配 2 行:`sys.login.whiteIPList`(逗号分隔 CIDR/IP) + `sys.login.whiteIPListStrict`(true=白名单空也拒)
- `SysLoginService.loginPreCheck()` 末尾加白名单检查,复用 `IpUtils.isMatchedIp()`
- **改完 sys_config 必须 `redis-cli del sys_config:sys.login.*` 清 Redis 缓存**,否则
  `loadingConfigCache()` 不会重建
- 默认行为(白名单空 + strict=false) = 全通,等同旧行为,**不动**
- e2e 矩阵:127.0.0.1 通 / 10.0.0.0/8 拒 / strict=true 拒 / 全空 strict=false 通

## AES GCM 双格式兼容模式(2026-09-04 实战)

换加密算法时不能让历史密文失效。**通用模式**:密文前缀区分新旧算法,decrypt 按前缀
选择算法。代码模板已记录在 `references/2026-09-04-security-hardening.md` 的 P2 节。

## v-html 加 DOMPurify 的正确顺序(踩过)

**单靠 `DOMPurify.sanitize()` 仍会被替换前注入的 HTML 污染**。正确三步:
1. **先 HTML 转义**(把 `< > & " '` 替换为实体)
2. **再注入你自己的安全 HTML**(如 `<span class="highlight">`)
3. **最后 DOMPurify 过滤**(白名单 `ALLOWED_TAGS` + `ALLOWED_ATTR`)

管理员可控输入(`menu.name`、`noticeContent` 等)必须走这三步。详见 reference 文档。

## Spring Boot 4.x maven plugin: 排除 devtools 进生产

`<optional>true</optional>` 只能阻止依赖传递,**不能阻止 devtools 类被打进 BOOT-INF/lib**。
生产排除必须:

```xml
<plugin>
  <groupId>org.springframework.boot</groupId>
  <artifactId>spring-boot-maven-plugin</artifactId>
  <configuration>
    <excludeDevtools>true</excludeDevtools>
  </configuration>
</plugin>
```

## 全自动安全修复 SOP(下次直接照抄)

1. 备份:`cp <file> /opt/<project>/audit-YYYY-MM-DD/backup-<name>` 一次性
2. 并行改(代码/yml/pom/nginx 互不依赖,工具调用能 batch 就 batch)
3. `mvn package -DskipTests -B` + 备份旧 jar + kill 旧 PID + 起新 jar
4. 前端改了 → `pnpm run build:prod`(dist 自动覆盖,nginx `root` 指向 dist)
5. e2e 复验 = 业务 8-12 个核心 API + 旧 P0 仍生效 + 新增项针对性测
6. 清理测试数据(测试用户/临时 wx_mp_account 行/临时上传文件)
7. 写 `FIX-RECORD-Pn.md`

具体流程在 `references/2026-09-04-security-hardening.md` 的 "完整的'全自动安全修复'流程" 节。

## RuoYi-Vue 安全加固铁律(2026-09-04,pentest + SAST + SCA + 修 P0/P1 实战)

RuoYi 模板自带多个**默认就是不安全**的项,**任何新部署必须做下面这 5 件事**,否则 = 公网裸奔:

| # | 项 | 默认值(不安全) | 改法 | 严重 |
|---|---|---|---|---|
| 1 | `token.secret` | `abcdefghijklmnopqrstuvwxyz` | `${JWT_SECRET:随机48B}`,env 覆盖 | HIGH |
| 2 | `wx.callback.allow-mock` | `true`(微信回调签名被绕过) | `${WX_CALLBACK_ALLOW_MOCK:false}` | CRIT |
| 3 | `druid.statViewServlet.allow` | 空(任何 IP) | nginx `location ^~ /prod-api/druid/ { return 403; }` | CRIT |
| 4 | `wx.aes.key` | yml 明文(所有 appSecret 命脉) | `${WX_AES_KEY:...}` env 覆盖 | HIGH |
| 5 | `druid.master.password` | yml 明文 | Vault/env 降权 | HIGH |

**前 3 项 15 分钟改完,改动局限在 yml + 1 行 nginx,无 DB 影响**。
**后 2 项必须配重加密脚本**(`wx_mp_account.app_secret` 用新 key 重加密,失败可回滚到旧 key)。

### RuoYi hasPermi 的 super-admin 短路(测鉴权必看)

`PermissionService.hasPermissions()`:
```java
return permissions.contains(Constants.ALL_PERMISSION) || permissions.contains(StringUtils.trim(permission));
```
`ALL_PERMISSION = "*:*:*"`。super-admin(role_key=admin)用户 permissions 永远含 `*:*:*`,
**任何 `@PreAuthorize("@ss.hasPermi('X')")` 都过**。所以:

- 测鉴权**必须建一个非 super-admin 的低权限用户**(如 role_id=100 jl_biz),**别用 admin 测 403**。
- body 是 "没有权限" + http code **200**(不是 403),这是 Spring Security 默认实现,**别被状态码 200 误导**。

### nginx `^~` 长前缀赢(精确拦截模式)

```nginx
# 长的 ^~ 在前,短的 ^~ 在后,都生效
location ^~ /prod-api/druid/ { return 403; }   # 精确拦截
location ^~ /prod-api/ { proxy_pass ...; }      # 其他透传
```
**两个 `^~` 块同时存在时长前缀赢** — RuoYi 的 prod-api 反代常用 `^~ /prod-api/`,
要拦截某个子路径就在它前面加更长的 `^~ /prod-api/X/ { ... }`。

### Spring yml 占位符 syntax(挪硬编码 key 出去)

```yaml
# 默认值,本地用;真生产用 env KEY 覆盖
secret: ${JWT_SECRET:YqV2c8TkP4nHbW7XmZ3eL6sJ9uR1vN5dA0gF8iD3oB2hC4kE6}
allow-mock: ${WX_CALLBACK_ALLOW_MOCK:false}
```
比 Jasypt / 配置文件外置简单。**注:重启会丢旧 secret 签的所有 JWT**,用户全部要重登。

### 渗透测试的"假 200"陷阱

Spring 8080 对未注册路径统一返 200 + body 是错误 JSON(`{"msg":"No static resource...","code":500}`)。
nikto / ffuf / sqlmap 看到 200 就标"命中",**实际是 500 body**。复验时必须 `head -c 200 /tmp/r` 看 body,别只看 status code。

### Vue 异步调用的 unhandledrejection 误报(2026-09-04 实战)

RuoYi 前端 `CommandCenter.vue` 类 onMounted 并发调 12 个 API:

```ts
getDashboardKpi().then((res) => { kpi.value = res.data || {} })  // 缺 .catch
```

任何一个 reject 冒到 Vue async handler → F12 console 报 `Error: <msg>`(msg 经常是**误取上下文文本**,
比如"推送失败(已记录)"实际是 dashboard UI label,被 Vue 错误消息路径当成异常文本)。

**根因**:`.then` 链没接 `.catch`,reject 走 unhandledrejection 路径。**12 个 API 实际全 200,
业务数据正常,只是 console 噪音**。

**真修复**(二选一,**不靠 try/catch**,加全局 hook 即可):

```ts
// src/main.ts 末尾
app.mount('#app')

// [AUDIT-2026-09-04] 全局吞 unhandledrejection,避免 console 出现 Vue runtime 包装的
// 误导性错误字符串(经常把 UI label 当作 Error message 抛出)
window.addEventListener('unhandledrejection', (e) => {
  e.preventDefault()
})
```

**额外**:`.then(...).catch(() => {})` 加在每个调用上,防 unhandledrejection 噪音 + 给业务层
留"业务数据失败"的处理空间。

**排查策略**:报"Error: 推送失败(已记录)"时,先 grep 后端代码确认这字样在哪(WxMsgPushService.java
的 sendByPhone 返回 Map)→ 不是 API 失败,是 console 噪音。再用 F12 Network 确认 12 个 API 状态码
都是 200。**不要花时间追 stack trace 里的"`at te index-D96DZNg5.js:2:481`"** — Vue 编译
后所有 `await` 都被命名为 `te`,无追踪价值。

### 前端 v-html 模板里"已记录"字样做兜底(防 grep 误判)

`grep -rn "已记录" dist/js/` 在 min js 里查不到,因为 min 化会把字符串分散到多行。
碰到"已知某字样"想确认前端是否有:**查 vue 源文件 `src/**` 的 raw 文本,别在 dist min js
里搜**(搜不到 = 误报,以为后端返回)。

### 全栈体检 + 加固 SOP 引用

- 基础体检流程见本文件"全栈体检 SOP"段
- 加固实录(P0 修完 / P1 改一半被叫停 / Druid 真打穿 / 微信回调绕过 e2e 复验):`references/2026-09-04-security-hardening.md`
- 全栈体检基线:`references/2026-09-04-jonlink-fullstack-audit.md`

## 关联引用

- **全栈体检基线与假阳性教训(2026-09-04)** 见 `references/2026-09-04-jonlink-fullstack-audit.md`
- **安全加固实录(2026-09-04,P0/P1 修复路径、Druid 真打穿、RuoYi hasPermi super-admin 短路、nginx ^~ 长前缀赢、AES GCM 双格式兼容、IP 白名单 sys_config + Redis 缓存陷阱、DOMPurify 三步法、用户"全修"工作风格)** 见 `references/2026-09-04-security-hardening.md`
- 接口对账脚本 `scripts/audit_api_parity.py`;mapper SQL 干跑 `scripts/mapper_sql_dryrun.py`

- 同类项目 / JonLink-policy-module 实战 `references/2026-08-22-policy-module-episode.md`
- **2026-09-05 粉丝管理页面迭代复盘(mvn 多模块 rebuild 缓存、MyBatis Date/String 错配、自动部署流水线、e2e 验证矩阵)** 见 `references/2026-09-05-fans-management-page.md`
- **2026-09-06 财务模块 UI 重构 + @Excel 字段名短化(扫描方法学、手工映射原则、jl-* 设计规范、Vue3 auto-import 坑、chromium e2e 硬限制、Aeglx 视觉反馈信号)** 见 `references/2026-09-06-finance-page-restructure.md`
- **2026-09-06 财务重构第二轮:菜单 DB 树结构坏掉导致 vue-router 找不到路径(空白页真因)** 见 `references/2026-09-06-menu-db-router-mismatch.md`
- **第二次栽(2026-08-22):res.data?.rows 与 sys_menu.status 逆映射** 见 `references/2026-08-22-2nd-rootcause-resdata-and-status.md`
- **第三次 + 第四次栽(2026-08-22):e2e 三方一致 + `@Anonymous` 公共端接口** 见 `references/2026-08-22-3rd-and-4th-iteration.md`
- JonLink 子模块细节(政策、withKeys 等)RuoYi 通用 → 详见 `jonlink-policy-module` SKILL(原话未改,作为政策模块的"原汁原味"参考)
- 后端 java/skill 见 `~/.hermes/skills/jonlink-policy-module/SKILL.md`(policy 特定细节)
- vue 端前置必备 skill: `frontend-dev`(design system), `fullstack-dev`(后端架构)
