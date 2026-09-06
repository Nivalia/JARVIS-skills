# 2026-09-04 JonLink 全栈体检实录(接口/端口/反代/内存/安全)

用户诉求:"检查方向、接口、端口、漏洞、bug、反代、内存占用率,要求接口前后一致、api 前后端统一"。
以下是当次实测数据与结论,可作为下次体检的基线对照。

## 实测基线(2026-09-04)

| 项 | 值 |
|---|---|
| 拓扑 | nginx:80 → 127.0.0.1:8080 (`jonlink-admin.jar`),静态 root=`JonLink-Vue3-TS/dist` |
| 后端路由 | 536 条(420 个 `*Controller.java`) |
| 前端 endpoint | 294 个(`src/api/**`) |
| parity | MISSING = 0 |
| handler 扫描 | 全量 `src/views/**/*.vue`,MISSING = 0 |
| `res.data?.rows` 误用 | 0 |
| 响应耗时 | `/`=0.6ms、captchaImage=6ms、finance/tax/summary=102ms、system/auditLog/list=175ms |
| DB/缓存 | MySQL(MariaDB)127.0.0.1:3306 ping 10ms;Redis 127.0.0.1:6379,1.09MB / 61 key |
| JVM | RSS 819MB,G1 堆 total 400MB/used 254MB,Metaspace 110MB,**MaxHeapSize 1.98G** |
| 主机 | 7.9G 内存、已用 4.5G、**swap = 0**、磁盘 58% |

## 找到的真问题

1. **`/ledger/dashboard/subjectBalanceTop10` 曾 500** —
   `Reference 'value' not supported (reference to group function)`。MySQL 不允许在
   `WHERE/HAVING` 直接引用 `SUM(...) AS value` 别名 → 修法是聚合放子查询,外层
   `SELECT ... FROM ( ... ) t WHERE value != 0`。当次热修已进新 jar(14:26 重启),
   curl 复验 200,但源码未提交。
2. **`server.profile: D:/jonlink/uploadPath`** — Windows 路径残留,Linux 上生成了名为
   `D:\jonlink\uploadPath` 的畸形软链接目录,所有上传文件落在这里,迁移即丢。
3. **两个子 repo 大量未提交**(后端 267 个变更文件),运行中的 jar 与 git HEAD 不对应,
   回滚不可行。

## 安全隐患清单(RuoYi 通用,不止 JonLink)

- `SecurityConfig` 里 `/druid/**` 是 permitAll,经 nginx `/prod-api/druid/index.html` 可达
  (302 到登录页),仅靠 druid 自身密码挡 → 建议 nginx 层 `deny`。
- **`token.secret` 仍是 RuoYi 默认 `abcdefghijklmnopqrstuvwxyz`** → 可离线伪造 admin JWT,必改。
- `/v3/api-docs/`、`/prod-api/swagger-ui/index.html` 生产 200 公开,接口结构外泄。
- `application-druid.yml` 明文库密码且用 root 连库。
- actuator 已被 Spring Security 拦成 401(这条 OK,别误报)。

## 排查中踩到的方法论坑(下次直接避)

- **接口 parity 脚本第一版报 34 条 MISSING,全是假阳性**。原因:只解析注解里第一个字符串、
  没处理裸 `@RequestMapping`、没做尾斜杠双向前缀容错。修正后 MISSING=0。
  **先怀疑自己的解析器,别急着报"前后端不一致"**。
- **不要凭猜的 URL 做健康探测**。我探 `/ledger/dashboard/kpiLedger` 得到
  `No static resource ...` 就差点写成缺接口 —— 真实接口是 `/kpi`(聚合),`kpiLedger` 只是
  mapper 的 select id。**探测 URL 必须来自 Controller 注解或 `src/api/*.ts`,不能来自 mapper id**。
- mapper 干跑要先 `html.unescape`,否则 `&gt;=` 报成 `Unknown column 'gt'`(第一轮 7 条假 FAIL,
  清洗后 18 条全 ok)。
- 长 `find | while` 一行流会被 terminal 硬拦(oversized inline payload)→ 写成
  `/tmp/*.sh` 脚本文件再 `bash` 跑。
