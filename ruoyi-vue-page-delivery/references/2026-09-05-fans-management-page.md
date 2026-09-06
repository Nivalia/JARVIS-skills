# 2026-09-05 粉丝管理页面迭代复盘

## 任务范围

`/opt/JonLink/JonLink-Vue3-TS/src/views/wx/user/index.vue`(粉丝管理列表页) UI 改版:
- 筛选区从 3 项扩到 8 项(手机号/昵称/订阅/活跃度/绑定来源/关注时间区间)
- 按钮区分主操作 vs 维护操作,撞色修
- 主表精简列,头像/昵称/手机合并为"粉丝"列,加相对时间
- Dialog 分 3 tab(基础信息 / 分销绑定 / 活动数据)
- 后端 mapper + domain 加新筛选条件支持
- **全栈 e2e 验证**

## 改了什么

| 文件 | 改动 |
|---|---|
| `src/types/api/wx/user.ts` | `UserQuejlParams` 扩 5 字段:`subscribe` / `activityLevel` / `bindSource` / `subscribeTimeBegin` / `subscribeTimeEnd` |
| `src/views/wx/user/index.vue` | 完全重写 715 行;`<script setup>` + TS strict;3 tab dialog;jl-* 自定义样式 |
| `jonlink-system/.../domain/WxMpUser.java` | 加 `subscribeTimeBegin`/`subscribeTimeEnd` 字段 + getter/setter(**`String` 类型,不是 `Date`**) |
| `jonlink-system/.../mapper/wx/WxMpUserMapper.xml` | where 子句加 5 个新条件 + `order by u.subscribe_time desc` |

## 撞坑 + 修复(必读)

### 坑 1:mvn 多模块 rebuild 缓存

第一次 build 只跑了 `mvn package -pl jonlink-admin -q`,没 `-am` → system 模块没重打。改完 `WxMpUser.java` 字段类型从 `Date` 变 `String` 后,重启服务,**e2e 仍报旧错**。`unzip -p` 验证 jar 内 class 字段仍是 `Date`。

**修法**:以后改 system 模块后,必须:

```bash
mvn clean package -pl jonlink-admin -am -DskipTests -q
```

**教训**:`-q` 模式吞 stdout,看不到 system 编译日志,容易误判"已重打"。**always clean + -am**。

### 坑 2:MyBatis Date/String 字段错配(致命)

加 `Date subscribeTimeBegin` 字段 + 前端传字符串 `"2026-08-15"` → mybatis `PreparedStatement.setObject` 类型不一致,运行时抛:

```
Cause: java.lang.IllegalArgumentException: invalid comparison: java.util.Date and java.lang.String
```

**误以为是 SQL 函数 date_format 没生效**,换 `<bind>` 标签转 String → 仍错。**根因**是 java 字段类型不匹配,不是 SQL 写法问题。

**修法**:
1. `WxMpUser.subscribeTimeBegin/End` 类型从 `Date` 改为 `String`
2. getter/setter 同步改
3. mapper 写法:`date_format(subscribe_time, '%Y-%m-%d') >= #{subscribeTimeBegin}` ← 字段是 String 后 mybatis 自动走 setString,date_format 输出也是字符串,匹配成功

**教训**:mybatis 区间筛选 / 字典过滤新增字段,前端发什么类型,后端就用什么类型,不要给一个"看起来更合理"的类型(Date → String 自动转换在 mybatis 这层不工作)。

### 坑 3:npm install --no-save 踩坏 devDeps

为装 `@types/node` 让 vue-tsc 不报「Cannot find type definition file for 'node'」,跑了 `npm install --no-save @types/node` —— **副作用:devDependencies 里的 vue-tsc/vite 被移到 `.ignored/`,`.bin/vue-tsc` 不见了**。

**修法**:`NODE_ENV=development npm install --include=dev --no-audit --no-fund` —— dev 模式装回。

**教训**:`--no-save` 是双刃剑,会重写 `package.json` 影响后续 npm install,**只在临时一次性实验时用**,要保住 devDeps 必须用 `--include=dev`。

## e2e 验证矩阵(交付前必跑)

用 `admin/admin123` 拿 Bearer token(直接打 8080,nginx 走的 `/prod-api/login` 默认路径不通,要打 `:8080/login` 白名单):

```python
import urllib.request, json

# 拿 token
data = json.dumps({"username":"admin","password":"admin123"}).encode()
req = urllib.request.Request("http://127.0.0.1:8080/login", data=data,
                            headers={"Content-Type":"application/json"}, method="POST")
token = json.loads(urllib.request.urlopen(req).read())["token"]

def call(path):
    req = urllib.request.Request(f"http://127.0.0.1:8080{path}",
                                  headers={"Authorization": f"Bearer {token}"})
    return json.loads(urllib.request.urlopen(req).read())
```

| 用例 | 期望 | 实测 |
|---|---|---|
| `GET /wx/user/list` 无筛选 | total=2088 | ✓ |
| `?subscribe=1` | total=1994 | ✓ |
| `?activityLevel=1` | total=0(库内无高频) | ✓ |
| `?bindSource=0` | total=2088 | ✓ |
| `?subscribeTimeBegin=2026-08-01&subscribeTimeEnd=2026-08-31` 区间 | 注入 id=256 后 total=1, ids=[256] | ✓(注入后) |
| `?subscribeTimeBegin=2099-01-01&subscribeTimeEnd=2099-12-31` | 注入 id=512 后 total=1, ids=[512] | ✓ |
| 边界 `?subscribeTimeBegin=2026-09-01&subscribeTimeEnd=2026-09-30` 不含两端 | total=0 | ✓ |
| 组合 `?subscribe=1&subscribeTimeBegin=2026-08-01&subscribeTimeEnd=2026-08-31` | total=1, ids=[256] | ✓ |

**注入 / 清理**:用 mysql cli 直连 `mysql -u root -pjonlink_root_pwd jonlink -e "UPDATE wx_mp_user SET subscribe_time='2026-08-15 10:00:00' WHERE id=256;"`,e2e 跑完恢复 `UPDATE ... SET subscribe_time=NULL`。

## 部署流水线(全程未问用户,自动完成)

```bash
# 1. 前端
cd /opt/JonLink/JonLink-Vue3-TS
NODE_ENV=production npm run build:prod    # → dist/

# 2. 后端(强制 clean + -am,系统修改后必走)
cd /opt/JonLink/JonLink-Vue
mvn clean package -DskipTests -pl jonlink-admin -am -q

# 3. 重启(nginx 不动,dist 已落盘 + HTML 不缓存直接生效)
systemctl restart jonlink.service

# 4. 等就绪
for i in {1..20}; do
  code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 2 http://127.0.0.1:8080/login)
  if [ "$code" = "200" ] || [ "$code" = "405" ]; then echo "ready $i s"; break; fi
  sleep 1
done

# 5. e2e(走上面验证矩阵)
```

## Aeglx 工作风格更新

- **改完直接部署** — 第一次方案确认后,改 → build → 重启 → e2e 一条龙,不要每轮问
- **biu** = build(typo,含义自明)
- 同一会话内栽坑坦诚写在汇报里(mybatis 类型错配 + mvn 缓存坑),用户更在意"下次怎么避"而非粉饰
- 长任务前必给"方案草稿 + 开放问题列表",等 Aeglx 逐条定再动手

## 复盘结论

**这次"5 个新筛选项 + Dialog 分 tab + UI 重排"是个标准 CRUD 改造**,工作量集中在前端(715 行),后端改动极小(mapper where + Domain 2 字段)。最大价值在踩坑 1+2 —— 这两条对所有 JonLink 后续"加筛选条件"任务都通用。

**遗留**:标签列 N+1 问题(`/wx/userTag/user/{userId}` 逐条 fetch)、CRM 字段(累计订单/消费)留待 v2。
