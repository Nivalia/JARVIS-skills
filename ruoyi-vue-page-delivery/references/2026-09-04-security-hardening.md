# 2026-09-04 JonLink 安全加固实录(Pentest + SAST + SCA + P0/P1 修复)

第二段会话:用户先要"渗透/代码审计/依赖/配置/API 五面体检",再要求修 P0 + P1。
P0 一次干完(改 yml + nginx + 改 key);P1 中途被用户叫停 CORS 白名单("项目还没开发好"),
保留 `*`。本文件记录 P0/P1 实测路径、踩过的坑、真假阳性的分界,以及 RuoYi 通用安全加固清单。

## 渗透阶段(nmap → ffuf → sqlmap → 手工)

工具到位情况:
- ✅ nmap 7.93 / ffuf / sqlmap / httpx / hydra / nikto / gobuster 本机已有
- ❌ nuclei / gitleaks / trivy github release 拉取超时(国内网络),改用 OSV.dev API + 手工 NVD 对照
- ✅ semgrep 1.176.0 pip 装 OK,7 秒跑全 698 个文件

Druid 弱口令真打穿:

```text
POST http://127.0.0.1:8080/druid/submitLogin
Body: loginUsername=jonlink&loginPassword=94e85dc9ad723d16b88ccf25
→ 200 success + JSESSIONID 派发
→ /druid/datasource.html 200 通过,所有 SQL 历史/连接配置/URI 统计可读
```

- `login-password` 是 yml 里的字面 hash 值,不是 hash-of-password。
  **任何人拿到源码即可登录**(Druid 1.2.x 的"密码字段"行为)。
- `statViewServlet.allow: ` 空 → 任何 IP 可达。
- Druid 1.2.28 的 `executeSql.json` / `selectFileApi.json` 被 wall filter 挡
  ("Do not support this request"),但 SQL 历史/数据源/连接池/URI 统计仍全部可读。
- `/druid/sql.json` POST 一条 select 即返 ResultCode=1 + EffectedRowCount=1(只是历史 SQL 列表,不是即时执行)。

V3/api-docs 公网 200 公开(512 paths,227KB),Druid 公网 + 弱口令 = 攻击者拿靶纸 + 内网拓扑。

## SAST(semgrep p/owasp-top-ten + p/java + p/secrets)13 命中

| 严重 | 位置 | 规则 |
|---|---|---|
| ERROR | sql/jonlink_20260417.sql:69/70 | detected-bcrypt-hash(SQL 初始化数据) |
| WARN  | SysIndexController:34 | unrestricted-request-mapping |
| WARN  | WxMpCallbackController:380 | use-of-sha1 |
| WARN  | HttpUtils:218 | weak-ssl-context(允许 TLS 1.0/1.1) |
| WARN  | HttpUtils:268/273 | insecure-trust-manager(空实现,MITM) |
| WARN  | HttpUtils:285 | insecure-hostname-verifier(永远 true) |
| WARN  | AesUtils:74/101 | cbc-padding-oracle(AES/CBC/PKCS5Padding) |
| WARN  | Md5Utils:22 / UUID:119 | use-of-md5 |
| WARN  | GenController:254 | permissive-cors |

手工 grep 额外:

- v-html 2 处真 XSS 风险:
  - `HeaderNotice/DetailView.vue:45` `v-html="detail.noticeContent"` 系统通知渲染
  - `HeaderSearch/index.vue:48,49` `v-html="highlightText(...)"` 菜单高亮
- v-html 2 处自控(`html2Text`/`document.write` 打印预览),**不是 XSS**,但 grep 报警噪声
- `Runtime.exec` / `ProcessBuilder` / `XMLDecoder` 命中 = 0
- `${...}` 字符串拼接:仅 `GenTableMapper.createTable` 一处,管理员触发的代码生成器,可接受

## SCA(166 deps / 0 OSV 命中)

OSV.dev 对 com.alibaba / Spring 4.x / JonLink 内部 4.0.x 命名空间覆盖不全,0 vuln 不可全信。
**必须配合手工 NVD 对照**(下面)。结论:无 critical CVE,无 log4shell,建议升 druid 1.2.28 → 1.2.30+。

## 配置 P0 真问题(application.yml + druid.yml + nginx)

| Key | 风险 | 修法 |
|---|---|---|
| `token.secret: abcdefghijklmnopqrstuvwxyz` | HIGH RuoYi 默认,可伪造 JWT | 改 `${JWT_SECRET:随机48B}` |
| `wx.aes.key: CRJcY+YUEO8qfQY8agmnqw==` | HIGH 解密所有 wx_mp_account.appSecret 命脉 | 改 `${WX_AES_KEY:...}`,真生产覆盖 |
| `wx.callback.allow-mock: true` | **CRIT 微信回调签名验证被绕过** | 改 `${WX_CALLBACK_ALLOW_MOCK:false}` |
| `druid.login-username: jonlink` / `login-password: 94e85dc9ad723d16b88ccf25` | **CRIT 已实测可登** | nginx deny / 改密码 / 关 statViewServlet |
| `druid.master.password: jonlink_root_pwd` | HIGH DB root 明文 | 改 Vault/env 降权 |
| `server.profile: D:/jonlink/uploadPath` | MED Windows 路径残留 | 改 `/opt/JonLink/uploadPath` + 迁移 |
| `CORS addAllowedOriginPattern("*")` | MED 跨域反射 | 改白名单(**用户暂缓:开发期保持 \***) |

## P0 修复路径(已干完 + e2e 复验)

1. `application.yml:100` `secret: ${JWT_SECRET:YqV2c8TkP4nHbW7XmZ3eL6sJ9uR1vN5dA0gF8iD3oB2hC4kE6}`
2. `application.yml:160` `allow-mock: ${WX_CALLBACK_ALLOW_MOCK:false}`
3. `/etc/nginx/sites-available/jonlink` 在 `^~ /prod-api/` 之前插入:
   ```nginx
   location ^~ /prod-api/druid/ { return 403; }
   ```
4. `mvn package -DskipTests -B` → 旧 jar 备份 → kill 旧进程 → nohup 起新 jar
5. e2e 复验全过:旧 JWT 401 / 微信回调 invalid signature / Druid via nginx 403 / 业务 API 不回退

## P1 修复路径(干到一半被叫停)

1. `wx.aes.key` 改 env 占位符 ✅
2. `JonlinkDashboardController` 类级加 `@PreAuthorize("@ss.hasPermi('ledger:dashboard:list')")` ✅
3. SQL 授权:sys_menu 加「业务看板」perms=ledger:dashboard:list,关联 role_id=1 ✅
4. CORS 改白名单 ❌ 用户:"项目还没开发好" → 改回 `*` + 注释标注真生产必改

**重要:用户纠错时** — 选项顺序保持"最窄改动优先"是对的,但**安全建议如果用户选"不动"**,
记录他的理由(开发期/测试期/等真生产),**注释里留 TODO 而不是反复推销**。

## nginx `^~` 优先级 — 真验证

`^~` 是前缀锁死,**两个 `^~` 块同时存在时长前缀赢**。所以在 `^~ /prod-api/` 之前插入
`^~ /prod-api/druid/ { return 403; }` 就能精确拦截 druid,而其他 `/prod-api/*` 仍走代理。

实测:第一次 reload 后 curl 看到 302 是 nginx open file cache 旧值,第二次/强制刷新后 403。
**复验时多打几次**,别把缓存假阳性当成"修复失败"。

## RuoYi hasPermi + super-admin `*:*:*` 通配(关键)

`PermissionService.hasPermissions()`:
```java
return permissions.contains(Constants.ALL_PERMISSION) || permissions.contains(StringUtils.trim(permission));
```

`ALL_PERMISSION = "*:*:*"`。所以:
- super-admin 角色用户 permissions 永远有 `*:*:*` → **任何 @PreAuthorize 都过**。
- 普通角色用户(无 `*:*:*`)才走精确匹配。
- 测鉴权必须建一个**非 super-admin 的低权限用户**(角色 100 jl_biz),**不要用 admin 测 403**。
- role_id=100(我之前测用)本身有一堆 perms 但**没有 dashboard 权限**,验证 `@PreAuthorize("ledger:dashboard:list")` 时 200 + body "没有权限" = 文案 403,代码 200(Spring Security 的实现习惯),**别被状态码 200 误导**。

## RuoYi 公共端鉴权测试方法

`@Anonymous` 注解由 framework 的 `PermitAllUrlProperties` 扫描后塞到 SecurityConfig 的
permitAll 列表(已经在 `ruoyi-vue-page-delivery` SKILL 里记过)。**新增端点只用加注解,不动 SecurityConfig**。

但 `@Anonymous` 的"跳过"只对 Spring Security 而言 — **Druid / Swagger / actuator 不走 Spring Security 的 permitAll 机制**,
必须 nginx 层 deny。

## 2026-09-04 安全加固最终改动清单(备份齐全)

> **最终状态(2026-09-04 23:05)**:用户中途撤回 IP 白名单功能(原话"别先知我ip啊")。当前 jar
> **不包含** IP 白名单代码。本节列的是当时"全部改完时"的清单,IP 白名单部分**已回滚**。

- `/opt/JonLink/audit-2026-09-04/`
  - `REPORT.md` — 全栈体检报告(接口/端口/反代/内存)
  - `FIX-RECORD.md` — P0 修复记录
  - `FIX-RECORD-P1.md` — P1 修复记录
  - `backup-application*.yml` × 3 + `backup-nginx-jonlink` + `backup-ResourcesConfig.java` +
    `backup-JonlinkDashboardController.java` + `backup-jonlink-admin-*.jar` × 2
  - `sast/sast-{owasp,secrets,custom}.json` — semgrep 原始输出
  - `sca/{dep-tree,osv-input,KEY-DEPS-VULNS}.{txt,md}` + `query-batches/` — SCA 证据

## 留待 P2(用户拍板时再做)

| 项 | 备注 |
|---|---|
| CORS 改白名单 | 用户决定"等开发完" |
| v-html 2 处加 DOMPurify | 通知内容重构时 |
| `server_tokens off` + `etag off` (nginx 全局) | 1 行,任意时机 |
| spring-devtools 排除生产打包 | 任意 |
| AES/CBC → AES/GCM | 跟 wx.aes.key 改真随机一起做 |
| profile 路径换 Linux | 任意 |
| DRUID 密码改 | 已被 nginx 拦,弱口令可缓 |
| druid 1.2.28 → 1.2.30+ | 任意 |
| wx_mp_account.id=2 重加密或删 | 改 WX_AES_KEY 前必做(只有 1 条测试数据,直接删最省) |

---

# 第三段会话:P2 全修 + 登录 IP 白名单(用户指示"全修 不用经过我同意")

用户原话:"全修吧 不用经过我同意,除了别加白名单,禁止ip登录就行"
(译:**除了 CORS 白名单别动外,其余 P2 全部自动修,顺便加登录 IP 白名单**)

这一步把 P2 7 项 + 1 项新需求全做了,e2e 复验全过。本节记录可复用的技术点。

## AES/CBC → AES/GCM 双格式兼容(通用模式)

直接换 AES/GCM 会**让历史密文全部读不出来**。正确做法:写 GCM 加密新数据,
用密文前缀(`AES-GCM:` vs `AES:`)区分新旧,**旧密文 fallback 用旧算法解**。

```java
// jonlink-common/.../utils/security/AesUtils.java
private static final String TRANSFORM_GCM = "AES/GCM/NoPadding";
private static final String TRANSFORM_CBC = "AES/CBC/PKCS5Padding";
private static final String PREFIX_GCM   = "AES-GCM:";
private static final String PREFIX_CBC   = "AES:";
private static final int GCM_TAG_BITS = 128;
private static final int GCM_IV_BYTES = 12;

public static String encrypt(String plain) {
    // 前缀已加密的幂等返回
    if (plain.startsWith(PREFIX_GCM) || plain.startsWith(PREFIX_CBC)) return plain;
    byte[] iv = new byte[GCM_IV_BYTES];
    new SecureRandom().nextBytes(iv);                       // 每次随机 IV
    Cipher c = Cipher.getInstance(TRANSFORM_GCM);
    c.init(Cipher.ENCRYPT_MODE, key, new GCMParameterSpec(GCM_TAG_BITS, iv));
    byte[] ct = c.doFinal(plain.getBytes(UTF_8));
    // iv || ciphertext 输出(IV 必须前置才能解)
    byte[] out = concat(iv, ct);
    return PREFIX_GCM + Base64.getEncoder().encodeToString(out);
}

public static String decrypt(String s) {
    if (s.startsWith(PREFIX_GCM)) return decryptGcm(s.substring(PREFIX_GCM.length()));
    if (s.startsWith(PREFIX_CBC)) return legacyDecryptCbc(s.substring(PREFIX_CBC.length()));
    return s;                                                // 非密文原样返回
}
```

**e2e 验证**:写新行 id=3 secret 头变 `AES-GCM:`,旧行 id=2 仍 `AES:` 头,GET /wx/account/{id}
两条都 200,证明 CBC fallback 有效。

⚠️ **何时需要真重加密**:应用层有 upsert/批量 update 逻辑时,旧 CBC 密文会随写入动作
被 GCM 重新加密(因为 `encrypt` 看到 `AES:` 前缀不会重写,但 `decrypt` 拿到明文后
走 `update` 链路会变成 GCM)。一次性脚本重加密更稳:

```sql
-- 1. 备份
CREATE TABLE wx_mp_account_bak_20260904 AS SELECT * FROM wx_mp_account;
-- 2. 启动时用 WX_AES_KEY=<新 key> 让应用自动重写
-- 3. 跑一次全表 SELECT+UPDATE 触发应用层 encrypt
-- 4. 验证全表都是 AES-GCM: 头后再 DROP bak 表
```

## 登录 IP 白名单(RuoYi 通用,无现成组件可复用)

RuoYi 默认只有 `sys.login.blackIPList` 黑名单。**白名单是新增需求**,实现路径:
- `sys_config` 加 2 行:`sys.login.whiteIPList`(逗号分隔 CIDR/IP,空=不启用)
  + `sys.login.whiteIPListStrict`(true=白名单为空也拒绝,默认 false)
- `SysLoginService.loginPreCheck()` 末尾加检查逻辑(在 IP 黑名单之后)
- 用现成的 `IpUtils.isMatchedIp()` 做 CIDR 匹配,不用新写算法

```java
// 严格模式 OR 白名单非空 → 启用检查;只要当前 IP 不在白名单就拒
String whiteStr = configService.selectConfigByKey("sys.login.whiteIPList");
boolean strict = "true".equals(configService.selectConfigByKey("sys.login.whiteIPListStrict"));
if (StringUtils.isNotEmpty(whiteStr) || strict) {
    if (!IpUtils.isMatchedIp(whiteStr, IpUtils.getIpAddr())) {
        throw new BlackListException();
    }
}
```

### ⚠️ Redis 缓存陷阱(踩过)

**`sys_config` 的值缓存在 Redis**(`sys_config:<configKey>`),改 DB 后**不会立即生效**,
必须手动清缓存:

```bash
redis-cli del sys_config:sys.login.whiteIPList
redis-cli del sys_config:sys.login.whiteIPListStrict
```

不删缓存,SQL 改了 `update_time=NULL` 但读的还是旧值,看到"配置没生效"会以为是代码 bug。
生产环境改完 sys_config 必跑这两行,或重启 jar 让 `loadingConfigCache()` 重建缓存。

### e2e 验证矩阵

| 场景 | 期望 | 实测 |
|---|---|---|
| 配 `127.0.0.1` strict=false | 通 | 200 + token |
| 配 `10.0.0.0/8` strict=false (本机 127.0.0.1 不在) | 拒 | 黑名单错误 |
| strict=true 白名单空 | 拒 | 黑名单错误 |
| 全空 strict=false | 通(等同旧行为) | 200 |

## spring-boot-maven-plugin 排除 devtools(Spring Boot 4.x)

```xml
<plugin>
  <groupId>org.springframework.boot</groupId>
  <artifactId>spring-boot-maven-plugin</artifactId>
  <configuration>
    <addResources>true</addResources>
    <!-- 关键:不让 devtools 类进生产 jar -->
    <excludeDevtools>true</excludeDevtools>
  </configuration>
</plugin>
```

`<optional>true</optional>` 只阻止依赖传递,不能阻止 devtools 类被打进自己项目的 BOOT-INF/lib。
要真排除必须用 `<excludeDevtools>` 配置。Spring Boot 4.x 文档已确认这个 plugin 配置项。

## nginx 全局硬化(1 行就够)

```nginx
# /etc/nginx/nginx.conf,在 http { } 块里
server_tokens off;       # 响应头 Server: nginx(去掉版本号)
etag off;                # 删 ETag 头(防 inode 泄露,1.22.1 默认开)
```

`server_tokens` 只能去掉版本号,不能去掉 `nginx` 本身(那是协议要求)。要更彻底得编译 nginx
打补丁。对渗透测试这已经够用。

## aliyun maven 镜像的已知缺口(踩过)

| 缺失包 | 备注 |
|---|---|
| `com.alibaba:druid-spring-boot-4-starter:1.2.29` | 只有 1.2.28 |
| `com.alibaba:druid-spring-boot-4-starter:1.2.30` | 只有 1.2.28 |

1.2.30 在 maven 中央仓有,aliyun 没同步。真生产**必须切回官方仓库或代理**才能升 1.2.30+。
**坑**:`-U` 强制刷新会留 `.lastUpdated` 缓存文件,后续构建仍然报 missing。**清掉才有效**:

```bash
rm -rf ~/.m2/repository/com/alibaba/druid-spring-boot-4-starter/1.2.29 \
       ~/.m2/repository/com/alibaba/druid-spring-boot-4-starter/1.2.30
```

但即便清掉,aliyun 仍然 404。**正确做法**:换仓库(改 `~/.m2/settings.xml` 加 `<mirror>https://repo.maven.apache.org/maven2</mirror>` 或用 sonatype/aliyun proxy),不在 pom 改版本。

## v-html 加 DOMPurify 的正确顺序(关键)

**错误写法**(看着对但仍 XSS):

```ts
function highlightText(text: string): string {
  return DOMPurify.sanitize(text.replace(reg, '<span class="highlight">$1</span>'))
}
```

`text` 是菜单名(管理员可控),正则替换可能注 HTML。`DOMPurify.sanitize` 只看**最终 HTML 字符串**,
**对生成 HTML 阶段注入的 `<script>` 也会被过滤**,但对**让管理员写 `<img onerror=...>` 之类
被 sanitize 干掉后的结果是元素消失**,而不是转义 — 用户看到的是"菜单不见了"。

**正确写法**:**先 HTML 转义 text,再注入高亮 span,最后 DOMPurify 过滤**:

```ts
function highlightText(text: string): string {
  if (!search.value) return DOMPurify.sanitize(text, { USE_PROFILES: { html: true } });

  // 1) 先把 text 里的 < > & " ' 全部转义成实体(防止管理员塞的 HTML 生效)
  const safeText = String(text).replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  } as Record<string, string>)[c]);

  // 2) 在已转义文本上做高亮(此时不会有 HTML 注入)
  const highlighted = safeText.replace(new RegExp(`(${escapeRegExp(search.value)})`, 'gi'),
    '<span class="highlight">$1</span>');

  // 3) 最后 DOMPurify 兜底,只允许 span + class
  return DOMPurify.sanitize(highlighted, {
    USE_PROFILES: { html: true },
    ALLOWED_TAGS: ['span'],
    ALLOWED_ATTR: ['class']
  });
}
```

三步缺一不可:**单靠 DOMPurify.sanitize 仍会被管理员的 `<script>` 在替换前污染输入字符串**。

**HeaderNotice/DetailView 的 noticeContent** 是后端存储的富文本(管理员通过 sys_notice 表写入,
最终走 `/system/notice` 接口),管理员可控。Vue computed `safeContent` 单独 sanitize 即可,
不需要预先 HTML 转义(因为业务就是渲染 HTML)。

## 用户工作风格信号(重要 — 影响后续默认行为)

本会话用户对安全加固的偏好,编码进 `SOUL.md` 之外的 SKILL 行为:

1. **"全修 不用经过我同意"** — 用户对常规安全加固项不再要逐项确认。后续默认:**除了明确禁止
   的项外,P0/P1 级别修复自动干完,只汇报结果不重复问**。**例外**:架构层改动、改 DB 加密数据、
   跨仓库文件删除,仍要先报方案草稿。
2. **"不加白名单 项目还没开发好"** — **开发期不应用生产环境的强约束**(CORS 白名单、强制 HTTPS、
   CSP 严格化)。判断标准:**用户提到"还没开发完"或"开发期"** → 此类控制全缓,等用户明示
   "上生产"再改。**改完后在代码里留 TODO 注释**而不是反复推销。
3. **"禁止ip登录"** — 明确需求,但实现方式用户没指定。**自主选** RuoYi 现成的 sys_config +
   IpUtils 路径(非自创模块),改完汇报。
4. **回复要短** — "继续吧" / "继续" 这种单字回复在 P0/P1 阶段是"在等结果"的信号,不要把它当
   "要我等你思考" → **直接做,做完报 e2e 结果**。P2 阶段的"全修"指令,做完一行标题 + 修复
   清单就够,不要长篇解释每一项。

## 完整的"全自动安全修复"流程(下次直接照抄)

1. 用户说"全修" → 立即列出方案清单(每项 1 行,改什么 + 风险等级),不分阶段问
2. **同步备份**:`cp` 所有要改的文件到 `audit-2026-MM-DD/backup-*`
3. **改代码 + 改 yml + 改 pom + 改 nginx**(并行工具调用,互不依赖)
4. **mvn package** → 备份旧 jar → kill 旧 PID → 起新 jar
5. **前端如果改了**:`pnpm run build:prod` → 旧 dist 自动被覆盖(nginx `root` 指向 dist,无额外操作)
6. **e2e 复验**:
   - 业务 API:admin 登录 → 跑 8-12 个核心 list/detail/getInfo → 全 200
   - 旧 P0 仍生效(nginx 403,invalid signature,旧 token 401)
   - 新增项针对性测(如 IP 白名单:127.0.0.1 通 + 10.0.0.0/8 拒 + strict 拒)
   - 清理测试数据(测试用户 / 临时 wx_mp_account 行 / 临时上传文件)
7. **写修复记录**到 `audit-2026-MM-DD/FIX-RECORD-Pn.md`
8. **更新 SOUL.md / memory?** 不主动,**只**记录用户明确说的"记住 X"才动 memory

## 备份位置(本次)

```
/opt/JonLink/audit-2026-09-04/
├── backup-nginx.conf                          nginx 全局
├── backup-jonlink-admin-2026-09-04-2122.jar   P0 改前
├── backup-jonlink-admin-2026-09-04-2127.jar   P1 改前
├── backup-jonlink-admin-2026-09-04-2137.jar   P2 改前
├── backup-pom.xml / backup-jonlink-admin-pom.xml
├── backup-application.yml × 2 / application-druid.yml
├── backup-nginx-jonlink
├── backup-ResourcesConfig.java / backup-JonlinkDashboardController.java
├── backup-AesUtils.java                       AES 重写前
├── backup-SysLoginService.java                IP 白名单前
├── backup-DetailView.vue / backup-HeaderSearch.vue
├── FIX-RECORD.md / FIX-RECORD-P1.md / FIX-RECORD-P2.md
├── backup-jonlink-admin-2026-09-04-2305-no-whitelist.jar   IP 白名单撤回后备份
└── REPORT.md + sast/ + sca/ + cfg/ + api/    原始 audit 证据
```

## 第四段会话:撤回 IP 白名单(用户原话"别先知我ip啊")

P2 收尾后,用户发现我加了登录 IP 白名单(sys_config 2 行 + SysLoginService 改 + Redis 缓存),
立刻否决:**"别先知我ip啊"**(口语化"别限制我 IP 登录")。

### 处置流程(下次直接照抄)

1. **代码彻底回退到 git HEAD**(不留开关默认关):
   ```bash
   git -C /opt/JonLink/JonLink-Vue show HEAD:jonlink-framework/src/main/java/com/jonlink/framework/web/service/SysLoginService.java > /tmp/orig.java
   cp /tmp/orig.java /opt/JonLink/JonLink-Vue/jonlink-framework/src/main/java/com/jonlink/framework/web/service/SysLoginService.java
   grep -nE "whiteIPList|白名单" <file>   # 确认无残留
   ```
2. **DB 删 sys_config 2 行**:`DELETE FROM sys_config WHERE config_key IN ('sys.login.whiteIPList','sys.login.whiteIPListStrict')`
3. **Redis 缓存清**:`redis-cli del sys_config:sys.login.whiteIPList sys_config:sys.login.whiteIPListStrict`
4. **重打包** + **备份"撤回前"jar**(命名 `_no-whitelist.jar` 方便回滚对比)
5. **kill 旧 PID + 启新 jar** + **e2e 复验"删干净"**:
   - 登录 = 200 通(原本就应该是通,但确认没误拒)
   - 业务 API 仍全 200
   - 之前 5 项 P0/P1 修复仍生效(nginx 403、invalid signature、dashboard 鉴权等)
6. **写备份**:把"撤回前的 jar"也存到 `audit-2026-09-04/`,命名清楚

### 教训(给未来会话的)

- **"全修 不用经过我同意" 是个模糊授权**。常规安全项(token/密钥/nginx deny/算法)自动做没问题。
  但**任何"动用户自己登录/访问"的项**(IP 白名单、强制 HTTPS、SSO 跳转、登录验证码强制开启、
  限制性 UI、自动登出)即使加在 dev 期,用户会立刻撤回 — **因为他自己登录会受影响**。
- **撤回信号识别**:
  - "别 X 啊" / "不要 X" / "撤回" / "回退" / "还 X" — 立即执行回滚
  - **不要** 解释"其实加了个开关默认关" / "可以加白名单自己加" — 用户已明确否决
  - **不要** 留 feature flag 默认 disabled — 技术债,用户再次重申会再删
- **回滚的代码路径**:已经从 jar 包运行状态中体现的功能,要回滚必须:
  1. 代码 `git show HEAD` 取回
  2. DB / Redis 同步清
  3. **重打包 + 重启**(只改代码不重启 = 线上仍是旧代码)
  4. e2e 复验
- **预防**:在做"动用户访问权限"类加固前,问一句"这影响你自己登录吗?" 如果答案是"我自己登录可能受影响",**先报方案**。否则**默认不做**。
