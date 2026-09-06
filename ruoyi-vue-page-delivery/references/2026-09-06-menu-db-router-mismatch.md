# 2026-09-06 财务模块 UI 重构(第二轮):菜单 DB 设计导致路由匹配失败

## 上下文

第二轮重构 receivable.vue → Aeglx 看仍然是空白。本次会话最终定位根因:**Vue 代码没问题,是菜单 DB 树结构坏掉,前端 router 找不到路径,Vue 渲染「404 找不到网页」内置 error 组件**。

前情提要:第一次重构(fans-management-page 之后)已经知道代码可跑,但财务 receivable 一直空白。误诊了多个方向(vue-tsc、token 过期、dist cache、API 缺失),最终用 chromium CDP 才看到 404 页面。

## 真正的根因:菜单 DB 的 ParentView 设计错误

### 现象链

1. 用户打开 `/finance/receivable` → Vue SPA fallback 渲染 index.html
2. Vue Router 启动 → 调用 `generateRoutes()` → `getRouters()` 拿数据
3. 后端 `getRouters` 返回路由树,结构是:
   ```
   /finance (Layout)
     └─ receivable (ParentView, path='receivable')
          └─ receivable (C, path='receivable', component='finance/receivable/index')
   ```
4. 前端 `filterAsyncRouter` 处理时,ParentView 分支把 `el.path` = `'receivable'`(子节点)拼接成 `/finance/receivable` (对的),但**问题**是:ParentView 本身(`path='receivable'`)也被作为路由 addRoute,但**它的 path 跟父节点 `/finance/receivable` 不冲突**(因为是空 path 加 '/' 拼接)
5. 子菜单的 component='finance/receivable/index',vue-router 通过 `import.meta.glob` 匹配到我的 vue 文件,生成 chunk OK
6. **真正失败**:`isMenuFrame()` 后端逻辑见下 → 后端给 ParentView 类型的菜单没生成完整 children,导致前端拿到的是缺一条子的路由树

### 后端 isMenuFrame() 限制(关键代码)

`SysMenuServiceImpl.java:511`:
```java
public boolean isMenuFrame(SysMenu menu) {
    return menu.getParentId().intValue() == MENU_ROOT_ID  // ← 仅顶层 parent_id=0 才返回 true
        && UserConstants.TYPE_MENU.equals(menu.getMenuType())
        && menu.getIsFrame().equals(UserConstants.NO_FRAME);
}
```

而**ParentView 类型菜单**(如 menu_id=2569「往来管理」)的 parent_id 是 2365(财务系统 Layout),不是 0。`isMenuFrame` 返回 false → `buildMenus` 走的是 `else if (TYPE_DIR)` 分支。但 2569 的 `menu_type='M'`,不是 `'dir'`,所以也没走到 children 分支。

**结果**:ParentView 2569 落到最后 `routers.add(router)`,只加了自身,**children 数组是空的**。

前端 `filterAsyncRouter` 拿到的是:
```json
{ path: 'finance', component: 'Layout', children: [] }
```

`/finance/receivable` 路由**完全不存在** → vue-router 走 `:pathMatch(.*)*` fallback → 渲染「404 找不到网页」页面。

### Aeglx 之前为什么能进财务模块?

这菜单是 Aeglx 接过来时就坏的 — 之前从来没人访问过 `/finance/receivable`。菜单 SQL 可能是 Aeglx 自己加的,parent_id 设错。

### 数据 SQL 现状(接管时)

```sql
SELECT menu_id, parent_id, menu_name, path, component
FROM sys_menu WHERE menu_id IN (2365, 2567, 2568, 2569, 2404);
-- 2365 财务系统    parent_id=0     path=finance   comp=Layout
-- 2567 会计核算    parent_id=2365  path=accounting  comp=NULL
-- 2568 台账财务    parent_id=2365  path=ledgerFin   comp=NULL
-- 2569 往来管理    parent_id=2365  path=receivable  comp=NULL  ← ParentView,path 跟子菜单冲突!
-- 2404 应收款      parent_id=2569  path=receivable  comp=finance/receivable/index  ← path 跟父一样!
```

`2404` parent_id=2569(ParentView),`2569` path='receivable',`2404` path='receivable' — **父子 path 完全相同**,addRoute 时:
- `/finance/receivable` (ParentView 拼出来)
- `/finance/receivable/receivable` (child 被 filterChildren 二次拼接!)

## 修复方案

不要去改后端 `buildMenus` 逻辑(改 Java + rebuild + 重启代价大)。直接**清理菜单树**:

```sql
-- 1) 把 25 个 C 菜单的 parent_id 全部从 2567/2568/2569/2570/2571/2572/2573 改成 2365
UPDATE sys_menu SET parent_id = 2365
WHERE menu_id IN (2398, 2404, 2410, 2416, 2423, 2429, 2435, 2441, 2448,
                   2454, 2490, 2491, 2492, 2478, 2479, 2493, 2538, 2542,
                   2531, 2545, 2547, 2534, 2552, 2557, 2559);

-- 2) 删掉空 ParentView (component=NULL)
DELETE FROM sys_menu WHERE menu_id IN (2567, 2568, 2569, 2570, 2571, 2572, 2573);

-- 3) role_menu 同步删
DELETE FROM sys_role_menu WHERE menu_id IN (2567, 2568, 2569, 2570, 2571, 2572, 2573);
```

改完后 `/getRouters` 返回:
```json
[
  {"path": "/finance", "component": "Layout", "children": [
    {"path": "receivable", "component": "finance/receivable/index", "meta": {...}},
    {"path": "payable", ...},
    ... (25 个 children)
  ]}
]
```

前端 router 正常注册 `/finance/receivable`,Vue 渲染成功。

## 诊断流程(下次重现空白页直接跑这套)

按顺序,**每一项必须 confirm 才能下结论**:

### 1. curl 后端 getRouters

```python
import subprocess, json
r = subprocess.run(['curl', '-s', '-X', 'POST', 'http://127.0.0.1:8080/login',
                    '-H', 'Content-Type: application/json',
                    '-d', '{"username":"admin","password":"admin123"}'],
                   capture_output=True, text=True)
token = json.loads(r.stdout)['token']
r = subprocess.run(['curl', '-s', 'http://127.0.0.1:8080/getRouters',
                    '-H', f'Authorization: Bearer {token}'],
                   capture_output=True, text=True)
data = json.loads(r.stdout)

# 找目标路径的完整父链
def find_chain(nodes, path, chain=[]):
    for n in nodes:
        if isinstance(n, dict):
            new_chain = chain + [(n.get('path'), n.get('component'), len(n.get('children', [])))]
            if n.get('path') == path or n.get('path') == '/' + path:
                return new_chain
            if n.get('children'):
                r = find_chain(n['children'], path, new_chain)
                if r: return r
    return None

# 找 /finance 父菜单
chain = find_chain(data['data'], 'finance')
print('finance chain:', chain)
# 如果 chain 中 children 都空 → 路由不会注册
```

**判据**:
- 顶层 path='finance' 存在 ✓
- 顶层 children 数量 > 0 ✓
- 每个 child 的 component 不是 NULL ✓
- target path(如 'receivable') 在 children 链上,component='finance/receivable/index' ✓

**任何一项不过 → 菜单 DB 问题,不是 Vue 问题。**

### 2. 数据库直查

```sql
-- 看目标路径的 parent 链
SELECT menu_id, parent_id, menu_name, path, component, menu_type
FROM sys_menu WHERE path = 'receivable' OR menu_name = '应收款';

-- 关键诊断
SELECT menu_id, parent_id, menu_name
FROM sys_menu WHERE parent_id = 0 AND menu_name LIKE '%财务%';
```

**找两类问题**:
- A) **parent 链断裂**:菜单 A parent=B,B 不在 sys_menu
- B) **路径冲突**:父子 path 相同(我这次栽的)
- C) **ParentView 缺失 component**:menu_type='M' 且 component=NULL,parent 不是 0

### 3. chromium CDP 验证(必走)

**vue-tsc pass + curl 200 + grep dist OK ≠ 浏览器 OK**。只有 chromium 能确认运行时。

我之前栽坑的脚本(可直接复用):

```bash
# 起 chromium (background)
chromium --headless --disable-gpu --no-sandbox \
  --remote-debugging-port=4183 \
  --user-data-dir=/tmp/cprof \
  --remote-allow-origins=* \
  --disable-dev-shm-usage \
  --hide-scrollbars \
  --window-size=1440,900 \
  about:blank > /tmp/chr.log 2>&1 &
```

```python
import urllib.request, json, websocket, time, base64
# 连 CDP
tabs = json.loads(urllib.request.urlopen("http://127.0.0.1:4183/json").read())
ws = websocket.create_connection(tabs[0]['webSocketDebuggerUrl'])

def call(method, params=None, mid=[1]):
    ws.send(json.dumps({"id": mid[0], "method": method, "params": params or {}}))
    mid[0] += 1
    while True:
        msg = json.loads(ws.recv())
        if msg.get('id') == mid[0] - 1: return msg

# 注入 token cookie
import subprocess
r = subprocess.run(['curl', '-s', '-X', 'POST', 'http://127.0.0.1:8080/login',
                    '-H', 'Content-Type: application/json',
                    '-d', '{"username":"admin","password":"admin123"}'],
                   capture_output=True, text=True)
token = json.loads(r.stdout)['token']
call("Network.enable")
call("Network.setCookie", {"name": "Admin-Token", "value": token, "domain": "127.0.0.1", "path": "/"})

# 导航 + 截图
call("Page.enable")
call("Emulation.setDeviceMetricsOverride", {"width": 1440, "height": 900, "deviceScaleFactor": 1, "mobile": False})
call("Page.navigate", {"url": "http://127.0.0.1/finance/receivable"})
time.sleep(6)  # 给 Vue + axios 加载时间

# 关键诊断
result = call("Runtime.evaluate", {"expression": """
JSON.stringify({
  url: location.href,
  has404: document.body.innerText.includes('404错误'),
  hasJlPage: !!document.querySelector('.jl-page'),
  statCardCount: document.querySelectorAll('.jl-stat-card').length,
  bodyTxt: document.body.innerText.substring(0, 200)
})
""", "returnByValue": True})
data = json.loads(result['result']['result']['value'])
print('render:', data)
```

**关键变量**:`has404=true` + `hasJlPage=false` = **菜单路由问题**,不是 Vue 代码问题。

### 4. 截图取证

```python
shot = call("Page.captureScreenshot", {"format": "png"})
with open('/tmp/page.png', 'wb') as f:
    f.write(base64.b64decode(shot['result']['data']))
```

用 `vision_analyze` 看一眼,**别只看 DOM 文本**。我栽了几次发现 DOM 是"先知·智源管理系统",文字看着正常,但实际渲染的是「404 找不到网页」错误页 + 侧栏菜单 → 误以为登录态 + 进入。

## 易混信号

- ❌ "**DOM 文本里有「先知·智源管理系统**」 → 进入成功"** → 错。SPA 任何路由都有这个标题(在 Layout 里),不证明路由匹配
- ❌ "**侧栏有「财务系统」菜单** → 财务页面能进"** → 错。菜单项显示 vs 子页面路由是两个独立机制,菜单项从 sidebar routes 拿,子页面从动态 addRoute 拿
- ❌ "**getRouters 返回 200** → 路由树 OK"** → 错。可能返回的路由树里有 component=NULL 的 ParentView,前端 addRoute 时 children 为空

## 本会话已交付的视觉效果(receivable 样板)

Aeglx 确认「每个页面有特有特性」后做的设计:
- **顶部 4 卡片** Dashboard:本周应收 / 已收款 / 逾期 / 未收余额 (蓝绿红橙四色边)
- **快捷筛选条**:状态 radio + 时间 radio + 高级筛选按钮
- **高级筛选**:默认收起,点击展开 6 个字段
- **紧凑主表**:单号 monospace + 状态 tag + 金额 in/out 着色 + 逾期红底
- **表脚合计**:总金额 / 已收 / 未收 着色
- **空数据图标** `el-empty` 兜底
- **核销 Dialog**:摘要卡 + 计算核销后剩余颜色变化

每个财务页面照此样板,字段和视觉细节按业务调整。

## 关键教训

1. **菜单 DB 设计错误比 Vue 错误更隐蔽** — Java 后端不报错,SQL 跑过,mvn pass,前端 build pass,**全部检查项都过了,但路由就是不存在**。前端 vue-router 找不到路径会渲染 404,不是 throw error。
2. **chromium CDP 是唯一真验证手段** — `vue-tsc pass` + `curl 200` + `dist grep OK` + **DOM 文本看着对**都不够,必须实际渲染截图。
3. **菜单树的 parent 链 + component 字段**是必须直查的项,加进 `vue-page-delivery` SOP。
4. **ParentView 的 isMenuFrame 限制**只支持 parent_id=0,作为架构约束:**ParentView 必须放顶层**,不能嵌套在 Layout 下。

## 配套修改

- `SysMenuServiceImpl.buildMenus` 的 else-if 链没覆盖 `parent_id!=0 && TYPE_MENU && component=NULL` 情况,可以加个 if 分支修,但本会话没改(改 Java + rebuild 代价 > 直接修菜单数据)。
- 前端 `permission.ts` 的 `filterChildren` 在 ParentView 拼 path 时**不会校验父子 path 不冲突**,这个其实也是个坑,但没改前端(没必要,DB 已经清理)。
- `vite.config.ts` 的 dev proxy 是 `/dev-api` 而生产 nginx 是 `/prod-api`,**导致 vite dev (port 82) 跑出来的 vue 应用调后端 API 404**,不是生产 nginx 配置问题。开发要用 nginx 或自己改 proxy。
