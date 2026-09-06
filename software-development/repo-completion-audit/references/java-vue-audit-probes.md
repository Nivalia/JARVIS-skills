# Java + Vue3 Audit Probes

Adapted probe recipes for repos where the skill's default TS/Python
recipes don't translate. Verified against JonLink (RuoYi fork, 124k
LOC, 2026-09-01).

## Why the default probes don't translate

The SKILL.md's six dimensions are stack-agnostic in **concept** but the
**recipes** assume TS / Python / C++. Java + Vue3 repos need:

- Per-module Maven layout (not `packages/*/`)
- `src/main/java` + `src/test/java` (not `src/`)
- `pom.xml` dependency analysis (not `package.json`)
- A separate sibling Vue3 project (not nested `packages/frontend/`)
- SQL table ownership probe (not relevant for TS apps)

## Dim 1: Code Volume Reality (Java + Vue3)

```bash
# Per-module LOC for Maven multi-module layout
BACKEND=/opt/JonLink/JonLink-Vue
for mod in admin framework system common quartz generator; do
  src="$BACKEND/jonlink-$mod/src/main/java"
  [ -d "$src" ] && echo "$mod: $(find $src -name '*.java' | xargs cat 2>/dev/null | wc -l) LOC"
done

# Frontend Vue3 sibling project
FRONTEND=/opt/JonLink/JonLink-Vue3-TS
find $FRONTEND/src -type f \( -name '*.vue' -o -name '*.ts' -o -name '*.js' \) \
  -not -path '*/node_modules/*' | xargs cat 2>/dev/null | wc -l

# Sub-decomposition by Vue directory
for sub in api views components router store utils; do
  find $FRONTEND/src/$sub -type f \( -name '*.vue' -o -name '*.ts' -o -name '*.js' \) \
    2>/dev/null | xargs cat 2>/dev/null | wc -l
done
```

**Detection pitfall**: RuoYi single-tier fork naming. Repo dir is
`JonLink-Vue/` but it's the **backend** because:
- `pom.xml` at root (Maven parent)
- 6 modules: `jonlink-{admin,framework,system,common,quartz,generator}`
- `target/*.jar` already built
- Java packages under `com.jonlink.*` (rebranded from `com.jonlink`)

The separate frontend lives in `JonLink-Vue3-TS/` (sibling, no
`pom.xml`, no `target/`). Don't trust directory names.

Detection: `find . -maxdepth 5 -name "pom.xml"` — present in `*-Vue` =
backend; absent in `*-Vue3-TS` = frontend.

## Dim 2: Test Coverage Reality (Java + Vue3)

```bash
# Java tests
find $BACKEND -path '*/src/test/java/*.java' -name '*.java' | wc -l
find $BACKEND -path '*/src/test/java/*.java' -name '*.java' \
  | xargs cat 2>/dev/null | wc -l

# Vue3 tests
find $FRONTEND/src \( -name '*.spec.ts' -o -name '*.test.ts' \) | wc -l
find $FRONTEND/src \( -name '*.spec.ts' -o -name '*.test.ts' \) \
  | xargs cat 2>/dev/null | wc -l

# test-to-src ratio (often 0% — that itself is the score)
src=$(find $BACKEND -path '*/src/main/java/*.java' | xargs cat 2>/dev/null | wc -l)
test=$(find $BACKEND -path '*/src/test/java/*.java' | xargs cat 2>/dev/null | wc -l)
echo "src=$src test=$test ratio=$((test * 100 / (src + 1)))%"
```

## Dim 3: Mock vs Real Implementation (Java + Vue3)

### False-positive grep traps

**Trap 1**: `grep -rn 'return new ArrayList<>' --include='*.java'` matches
BOTH:

```java
return new ArrayList<>();                       // RED FLAG: empty fallback
return new ArrayList<>(map.values());           // OK: real aggregation
```

The trailing `;` does not disambiguate. Read the file before flagging.
A genuine empty-list fallback has **nothing inside the angle brackets**
AND no method call chained off it. Anything with content inside `<>` or
after `<>` is real work.

**Trap 2**: `grep -rln 'mock\|Mock'` matches legitimate class names:

```java
WxMpService.java        // wechat SDK has a `mock` config mode — NOT fake impl
WxH5Controller.java     // may use WxMpService.mock in dev
```

Always read the file. In Java web apps with SDKs, "Mock" in a class
name often means an OPTIONAL MODE, not fake production code.

**Trap 3**: Vue3 dev-mock comments vs hardcoded-mock-data:

```typescript
// NOT a red flag: dev-mode comment explaining fallback path
// mock 模式下走补全 keyword_meta 路径

// IS a red flag: hardcoded data assigned in a data-loading function
function loadStats() {
  // 暂用 mock 数据, 等真实接口接入
  stats.value = { points: 1280, orders: 6, coupons: 3, distribute: 2 }
}
```

The distinguishing signal: the **object literal assignment inside a
loader function with a TODO-style comment**. Dev-mock comments appear
in `api/*.ts`; hardcoded data appears in `views/**/*.vue` loaders.

### Working probe pattern

```bash
# Step 1: gather candidates
grep -rln 'mock\|Mock\|fake\|stub\|Fake\|Stub' $BACKEND \
  --include='*.java' | grep -v 'src/test/'
grep -rln 'mock\|Mock\|fake\|stub' $FRONTEND/src \
  --include='*.ts' --include='*.vue'

# Step 2: for each candidate, read and classify:
#   (a) legit SDK name (WxMpService, MockMvc)
#   (b) dev-mode comment in api/ (not a flag)
#   (c) TODO-style hardcoded data in views/ loader (IS a flag)
#   (d) return new ArrayList<>() with empty brackets (IS a flag)

# Step 3: ALSO grep for hardcoded object-literal assignments in loaders
grep -rn '\.value\s*=\s*{' $FRONTEND/src/views --include='*.vue' | head
```

### TODO / FIXME / HACK honesty markers

```bash
grep -rE 'TODO|FIXME|XXX|HACK' $BACKEND --include='*.java' | wc -l
grep -rE 'TODO|FIXME|XXX|HACK' $FRONTEND/src --include='*.vue' --include='*.ts' \
  | grep -v node_modules | wc -l
```

Low counts are GOOD here. Combined with "0 tests", low TODO means the
project is either tiny scope or has hidden gaps — investigate which
(see SKILL.md pitfall #6).

## Dim 4: Roadmap vs Reality (Java + Vue3)

```bash
# Backend git log (look for repeated amend-style commits)
cd $BACKEND && git log --pretty=format:'%h %ad %s' --date=short --all

# Frontend git log
cd $FRONTEND && git log --pretty=format:'%h %ad %s' --date=short --all

# Same commit message twice = amend history
# E.g. "M0 政策展示模块(后端骨架 + 菜单 SQL)" appearing twice
# in `git log` output = history was rewritten, not trustworthy
```

## Dim 5: Marketing vs Documentation (Java + Vue3)

```bash
# Total .md file count
find /opt/<project> -maxdepth 4 -name '*.md' \
  | grep -v node_modules | grep -v '.git/'

# README rebrand check for framework forks
grep -E 'ruoyi|RuoYi|先知|智源|aliyun|tencent|折扣场|秒杀场' \
  $BACKEND/README.md $FRONTEND/README.md

# Note: rebrand often cleans Java packages + filenames but NOT README
# (RuoYi fork keeps README until explicitly rewritten)

# LICENSE copyright check
head -3 $BACKEND/LICENSE 2>/dev/null
```

## Dim 6: E2E Real Runnability (Java + Vue3)

```bash
# Backend jar + process
find $BACKEND -name '*.jar' -not -path '*/.git/*'
ps aux | grep -E 'java -jar' | grep -v grep | head

# Port listeners (8080=Spring Boot, 6379=Redis, 3306=MariaDB)
ss -tlnp 2>/dev/null | grep -E ':8080|:6379|:3306'

# Local + remote HTTP probe
curl -sS -m 5 -o /dev/null -w 'HTTP %{http_code}\n' http://localhost:8080/
curl -sS -m 5 -o /dev/null -w 'HTTP %{http_code}\n' http://localhost:8080/captchaImage
curl -sS -m 8 -o /dev/null -w 'HTTP %{http_code}\n' http://<ECS-IP>/
curl -sS -m 8 -o /dev/null -w 'HTTP %{http_code}\n' http://<ECS-IP>:8080/

# Frontend dist
ls -la $FRONTEND/dist/ 2>/dev/null
ls -la /opt/<project>/<sibling-app>/dist/ 2>/dev/null

# Startup scripts + Docker
find /opt/<project> -maxdepth 3 \
  \( -name 'start*.sh' -o -name 'start*.bat' -o -name 'Dockerfile*' -o -name 'docker-compose*' \) \
  | grep -v node_modules | grep -v .git
```

## Cross-dimension: DB table ownership probe

Java web apps almost always have DB credentials in plaintext in
`application-druid.yml` or `application.yml`. Use them to run a
business-vs-framework residue probe:

```bash
# Step 1: extract datasource config
grep -E 'datasource|username|password|url:' $BACKEND/*/src/main/resources/application-druid.yml

# Step 2: probe with the credentials you just found
mysql -u<user> -p<password> <dbname> -e 'SHOW TABLES;' > /tmp/tables.txt

# Step 3: classify
echo "业务表: $(grep -c '^<your_namespace>_' /tmp/tables.txt)"
echo "框架基表: $(grep -cE '^(sys_|gen_|qrtz_)' /tmp/tables.txt)"
```

For JonLink: 9 `jonlink_*` tables (insurance/channel/contact etc.) +
23 `fin_*` tables (financial) + 3 `policy_*` tables (recent module) vs
20 framework residue (`sys_*`/`gen_*`/`qrtz_*`). The 9:20 ratio
answers "how much is real business vs inherited RuoYi skeleton" without
needing to argue the framing.

**Security caveat**: documenting this probe is fine — the credentials
are in the project's own plaintext config, not a secret. Do NOT save
extracted credentials to memory or skill files.

## Cross-dimension: sys_menu menu tree probe

For RuoYi-fork projects, the actual product scope lives in `sys_menu`:

```bash
mysql -u<user> -p<password> <dbname> \
  -e 'SELECT menu_name, component FROM sys_menu WHERE menu_name LIKE \"%<keyword>%\";'"
```

Counts and component paths tell you which modules have a real
frontend page backing them. For JonLink: 404 sys_menu entries,
30+ are `finance/*` and 5+ are `policy/*` — confirms both modules
have actual page backings, not just backend code.

## Worked example: JonLink (2026-09-01)

| Dim | Probe | Result | Score |
|---|---|---|---|
| 1 | Maven per-module LOC | 67,942 LOC backend + 56,303 LOC frontend | 75% |
| 2 | Java test count | 0 | 0% |
| 3 | mock/Mock grep | 8 backend hits (all WxMp SDK names, not fake impl) + 1 Vue3 hardcoded data flag (`fan/Index.vue:95-99`) | 85% |
| 4 | git log | 6 backend commits (3 repeated amend) + 5 frontend commits | N/A — no ROADMAP to compare |
| 5 | .md count + README rebrand grep | 2 .md files, both still RuoYi upstream (含"先知·智源"/"jonlink.vip"/"阿里云折扣场") | 50% |
| 6 | process + port + curl | jar built, java running, port 8080 listening, local + remote HTTP 200 | 95% |

**Top 3 red flags surfaced**:
1. 0 tests across 124k LOC (Dim 2 critical)
2. README still RuoYi upstream (Dim 5 marketing lie)
3. `views/h5/fan/Index.vue:95-99` hardcoded mock data with explicit TODO comment (Dim 3 real flag)

**False positive caught during the audit**:
- `FinReportServiceImpl.java:54` flagged as "hardcoded empty list" by initial grep `return new ArrayList<>;` (false — line is `return new ArrayList<>(map.values());`, real aggregation). Lesson: read file before flagging Dim 3 hits.