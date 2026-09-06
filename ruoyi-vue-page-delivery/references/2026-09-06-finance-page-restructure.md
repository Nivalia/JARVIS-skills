# 2026-09-06 财务模块页面重构 + 后端 @Excel 字段名短化实战

## 任务范围

两件事并行,Aeglx 一句话分别触发:

1. **粉丝管理页面** → 看 wx/user 是 Aeglx 指定的「标杆页」,以后其他 wx 页面照搬这个
2. **财务模块 UI 难看 + 后端表头字段名太长** → 全财务模块 32 个 vue + 全 domain 后端 @Excel 短化

## 战果(本会话跨多个 Aeglx 消息累计)

### 短化工作(可复用方法学)

#### 前端 label 短化(24 + 26 处)

`label="金额(元)"` → `label="金额"`(单位全局统一)、`"保费(¥)"` → `"保费"`(货币符号统一)。

**扫描技巧**:
```bash
# 找所有 ≥6 字静态 label (排除字符串模板/变量绑定)
grep -rn -E '<(el-table-column|el-form-item)[^>]*\blabel\s*=\s*"([^"]{6,})"' src/views/ \
  --include=*.vue | grep -v 'dict\.|item\.|f\.|c\.|s\.|p\.|t\.|ch\.|a\.' | head
```

**必保留**:
- 微信 API 标准字段名:`AppSecret` / `access_token` / `openid` / `ticket` / `AppID` / `Token`
- 纯英文 prop 字段:`receiptNo` / `voucherNo` / `partnerName` / `subjectCode` 等 — 改了前端 prop 绑定会挂

#### 后端 @Excel name 短化(47 + 17 + 5 = 69 处)

`name = "活跃度 1高 2中 3低(定时任务计算)"` → `name = "活跃度"`(枚举说明走字典渲染)。

**铁律 3 条**:
1. **enum 字典化**:状态字段走 sys_dict_data 表 + 前端 `<dict-tag>`,**不**把枚举说明塞进字段名
2. **数据库列名引用删除**:`name = "关联 wx_mp_template.id"` → `name = "模板ID"`(DBA 看 schema 就懂)
3. **公式/算法描述删除**:`name = "利润 = 上游佣金 - 下游佣金(自动算)"` → `name = "利润"`(算法在 javadoc 注释)

**扫描技巧**:
```bash
# 找所有 @Excel(name=...) 中 >7 字的 (排除技术名词 + 纯英文 prop)
grep -rn '@Excel(name =' jonlink-system/src/main/java/com/jonlink/system/domain/ \
  --include=*.java | grep -E '"[^"]{8,}"'
```

**手工映射表方法**:
- 别写智能算法 (regex 替换总有边界 case 漏掉类型/语境)
- 49+ 个手工映射表 (prop + 旧 name + 新 name),**用 prop 锁定字段**而不是用 name 字符串 (因为同一字段可能多个 `@Excel` 共用)
- 改完用 `javap -p <ClassFile>.class` 验证 jar 内字段类型对得上

**撞坑**: `name = "..."` vs `name="..."` vs `name = "...",width=30,...` 三种写法都有,patch 时用最宽松匹配然后 `<if test="...">` 局部检查。

### Vue 页面重构 (32 个财务页面)

**Aeglx 选择**:
- 范围:全部财务 (32 个 vue) + 自己设计
- 风格:交给 JARVIS

**已完成**:
- `/opt/JonLink/JonLink-Vue3-TS/src/views/finance/receivable/index.vue` 重写 (715 → 240 行,**保业务不动,只升级样式**)

**统一设计规范 (jl-* 自定义类)**:

```css
/* 筛选区卡片化 */
.jl-form--query {
  background: #fafbfc; border: 1px solid #ebeef5; border-radius: 6px;
  padding: 14px 16px 0 4px; margin-bottom: 12px;
}

/* 工具栏主辅分组 */
.jl-toolbar { display: flex; justify-content: space-between; align-items: center; }
.jl-toolbar__main { display: flex; gap: 8px; }

/* 金额对齐 + 着色 */
.jl-money { font-variant-numeric: tabular-nums; font-weight: 500; }
.jl-money--in { color: #67c23a; }   /* 已收 */
.jl-money--out { color: #f56c6c; }  /* 未收 */

/* 行状态高亮 */
.jl-row--paid { background: #f0f9eb !important; }
.jl-row--overdue { background: #fef0f0 !important; }

/* 表脚合计 */
.jl-table-footer {
  display: flex; justify-content: space-between;
  background: #fafbfc; border-radius: 6px; padding: 12px 16px;
}

/* Dialog Tab */
.jl-dialog :deep(.el-dialog__body) { padding: 12px 24px 0; }
.jl-dialog-tabs :deep(.el-tabs__header) { margin-bottom: 16px; }
```

**撞坑**:
- `import { ref, reactive } from 'vue'` 在 auto-import 项目里**会冲突**(vue-tsc 报错 `has no exported member 'ref'`),unplugin-auto-import 已经把 vue 反应式 API 全局注入了 → **不要**在 `<script setup>` 里手动 import vue
- `proxy/formRef` 不能重复声明 (`Cannot redeclare block-scoped variable`)
- TS 严格模式下 callback 参数必须显式类型:`(s: number, r: any) => s + Number(r.amount || 0)`
- `vue-tsc --noEmit` 一次性扫 — 项目历史 412 个错是噪声,**只看自己改的文件的增量错**
- `delReceivable` 这种 API 不存在时不要瞎 import,降级 `ElMessage.warning('TODO')` 兜底

**重要 — 重构原则**:
- Aeglx 几次都说 "字段太长"、"页面难看" — **都是 UI 升级,不是业务流程改造**
- 别随便改业务字段 (prop 名、dict 字典、表结构),只改视觉/样式/label
- 大文件 (715 行) 一次性重写风险高,先做 1 个样板页让 Aeglx 确认风格,再批量推

## 重构后 e2e 验证 (撞坑系列)

### vue-tsc 校验的盲点

`vue-tsc --noEmit` 通过 ≠ 浏览器能跑。TypeScript 类型对,运行时仍可能 throw:
- `Element Plus` 的 el-table 缺 `<el-empty>` 时,空数据渲染为「空白页」(用户感受「白屏」)
- `proxy.$refs[name]` 在 TS strict 模式下类型 `never`,要 `(proxy.$refs[name] as any)`
- `vue-i18n` / `useDict` 字典项类型 `DictItem | undefined`,访问 `.type` 前要 `?:` 或 fallback `|| 'info'`

**真正 e2e 验证的硬门槛**:
- 浏览器 console 无红 (F12 → Console 看)
- el-table 行数 = 后端 list 接口 total
- 至少触发一次 add/edit/list API (Network 面板看 4xx/5xx)

### chromium headless e2e 的硬限制

本环境无浏览器 daemon + 不能装 puppeteer + chromium 后台启动不稳,**SP + cookie + token 注入的 e2e 跑不动**。退路:

1. **curl 后端 API 验证** — 排除后端问题
2. **grep dist js 验证前端代码进了产物** — `grep -l 'jl-finance-page' dist/static/js/*.js`
3. **vue-tsc --noEmit 验证类型** — 但不是充分条件
4. **让 Aeglx 在浏览器手动验证** — **承认工具局限,不假装能做**

**不要假装**: e2e 验证失败时说「应该 OK」是错的。要明确「vue-tsc 通过 + dist 含代码 + 后端 API 返 200 = 静态验证 100%,但**运行时错误只有 Aeglx 浏览器 console 能看到**」。

## Aeglx 工作风格更新 (本次新增)

- **「全改」+「你自己检查一遍」** = 自主扫,自主改,自主汇报全量结果,不要反复问
- **「不知道你做的哪个页面」** = Aeglx 没看到入口。**先告诉 URL + 文件路径**,别问「你打开哪个 URL」
- **「页面不对 空白页 根本看不见」** = 三种可能: (a) 浏览器缓存没刷 (b) token 过期 (c) 库内 0 数据导致空表看起来白。先**自己排查**这三种,别让 Aeglx 给证据
- 看到「空白页」先 curl 后端 API + grep dist 验证代码 + 手动写测试数据,**自己排除非代码问题**,再问 Aeglx
- 长组件 (700+ 行) 一次性重写是赌博,**做 1 个样板让 Aeglx 验证风格再批量**

## 留给 v2 的事

- 剩下 31 个财务 vue 文件 (voucher / invoice / payment 等) — **没做**,等 Aeglx 确认 receivable 风格 OK 再推
- 前后端 prop 字段的 5-6 字复合词 (`渠道关联ID` / `保险公司名称` 等) — 留在 prop 字段名层级,不进一步短化
- 19 个英文 prop (receiptNo / voucherNo 等) 保留,业务 prop 不能动
- 标签列 N+1 (wxLedgerItem 逐 user 拉 tag) — 后端 mapper 没 GROUP_CONCAT,等 v2 性能优化

## 关联参考

- 同会话内 `wx/user` 粉丝管理重构实战:`references/2026-09-05-fans-management-page.md`
- 整站体检 + 安全加固:`references/2026-09-04-jonlink-fullstack-audit.md`
- 早期 policy-module 端到端 SOP:`references/2026-08-22-policy-module-episode.md`
