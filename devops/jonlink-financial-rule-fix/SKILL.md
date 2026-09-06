---
name: jonlink-financial-rule-fix
description: "Fix JonLink financial rule bugs. Use when calc wrong."
---

# JonLink 财务业务规则修复 SOP

When a user reports "JonLink 财务模块字段规则计算逻辑不准" / "利润算错" / "上下佣不对" / "净费公式有问题" / "保费不该参与计算", **do not guess** — follow this 5-step audit-driven workflow. Tested on `JonlinkInsuranceLedger.calcCommission()` v1→v4 rewrite (2026-08-25).

## Why this matters

JonLink has ≥2 parallel financial modules that touch the same business concepts:

| 模块 | 后端表 | 入口 controller / service |
|---|---|---|
| 保险台账 (核心) | `jonlink_insurance_ledger` | `JonlinkInsuranceLedgerServiceImpl.calcCommission` |
| 保险佣金结算单 | `fin_commission` | `FinCommission` domain, `commission/index.vue` 前端提交 |

**Both modules compute commissions / rebates / profit independently.** Fixing only one is the #1 silent failure — the user sees "fixed" but the other module still produces wrong numbers.

## When to use

- User says "X 算得不对" / "利润不准" / "上下游佣金公式有问题"
- User says "改财务模块" / "更新业务规则"
- User provides a v-N version of business rules and asks "按这个改"
- Any calc method on `JonlinkInsuranceLedger` / `FinCommission` / `*SettleRecord` / `*Ledger*` is being touched

## Workflow

### Step 1 — Lock down the rule with concrete numbers

**Do NOT start coding until the user has given at least one numeric example.** The most common failure mode is the user describes rules abstractly ("上游佣金是保费的某个比例"), you implement something, and they correct you 2-3 times because "政策" might mean `up_rate` / `down_rate` / `net_rate` / a hardcoded amount — **the field name is ambiguous**.

Push for:
- A concrete example: "premium=1000, 含税, upRate=10%, downRate=5% → upstream=?, downstream=?, netFee=?"
- Which quantity does "含税" affect? upstream only / downstream only / both / netFee / all of the above?
- If user says "净费 = 保费 - 保费×政策" but doesn't say which policy, **stop and ask** — it could be up/down/independent. Don't guess.

If user has corrected rules 2+ times already, ask for the **final expected numeric values** for each field, not just the formula.

### Step 2 — Map the rule → codebase, scan all 4 layers

For each business rule change, **before coding**, scan all 4 layers:

| Layer | What to grep | Why |
|---|---|---|
| **Backend calc method** | `grep -rn "calcCommission\|calculate\|compute" <module>/service/impl/` | The actual formula lives here |
| **Backend domain comment** | `grep -nE "/\*\*.*=" <module>/domain/*Ledger.java` | DB annotation export uses `/** comment */` + `@Excel(name=...)` — both must match the actual rule, or admin export will show wrong column titles |
| **Frontend hardcoded formulas** | `grep -rn "p.premium \* .*Rate / 100\|1\.06" <vue>/views/finance/` | Frontend pre-calc on form submit is the #1 hidden dupe — fix backend alone won't help |
| **MyBatis aggregation SQL** | `grep -rnE "SUM\(.*premium.*\)\|SUM\(.*profit.*\)" <module>/resources/mapper/` | Verify report SQL doesn't do `SUM(profit) / SUM(premium)` — that injects premium into profit denominator |

### Step 3 — Verify the field exists before assuming

**Do not assume fields exist based on the user's rule.** Before writing `netFee = premium - premium × netRate`, confirm `netRate` actually exists:

```bash
grep -nE "private.*[Nn]etRate|private.*[Nn]etFee" <module>/domain/<Entity>.java
```

If the field doesn't exist, the user's formula references a non-existent quantity — **stop and clarify**, don't invent.

### Step 4 — Refactor calc method to shared base (when tax affects ≥2 quantities)

**Anti-pattern**: repeating the tax branch in each formula.

```java
// ❌ Before: each formula reimplements tax logic
if (taxFlag==1) upCommission = premium/1.06 * upRate;
else upCommission = premium * upRate;
downCommission = premium * downRate; // forgot to handle tax!
// ... 6 lines later, the missing branch causes a bug
```

**Pattern**: compute the base ONCE, reuse for all downstream.

```java
// ✅ After: shared base + uniform downstream
BigDecimal commissionBase = premium;
if ("1".equals(ledger.getTaxFlag())) {
    commissionBase = premium.divide(new BigDecimal("1.06"), 4, RoundingMode.HALF_UP);
}
BigDecimal upCommission = commissionBase.multiply(upRate).divide(ONE_HUNDRED, 2, RoundingMode.HALF_UP);
BigDecimal downCommission = commissionBase.multiply(downRate).divide(ONE_HUNDRED, 2, RoundingMode.HALF_UP);
BigDecimal netFee = premium.subtract(upCommission); // premium is the ORIGINAL, not base
BigDecimal profit = upCommission.subtract(downCommission);
```

Subtle traps:
- `netFee` may use **original premium**, not the tax-adjusted base — confirm with user.
- Rounding mode (`HALF_UP` vs `HALF_DOWN` vs `HALF_EVEN`) and precision (2 vs 3 decimals) — user's hand-calc may be 0.01 off. Confirm acceptable drift OR pin precision.

### Step 5 — Verify and sync comments

After patching:
1. **`mvn compile -pl <module> -am -DskipTests -q`** — exit code 0 confirms Java compiles. Never trust "I edited the file, looks fine."
2. **Patch domain `/** comment */` and `@Excel(name=...)` to match new rule** — these feed admin export + DB annotation, drift causes "logic right but UI label wrong" bugs.
3. **Document the rule version inline** in the calc method's javadoc, e.g. `/* v4 定稿 2026-08-25: ... */` — saves the next maintainer (and your future self) re-deriving it.

### Step 5a — Precision drift (重要)

`HALF_UP` + 4 位中间精度 + 末尾 2 位会跟用户手算差 ±0.01。实测 `1000/1.06×0.1`:
- 代码: `943.3962 × 0.1 = 94.33962 → round(2) = 94.34`
- 用户手算: `1000/1.06=943.396..., ×0.1=94.3396... ≈ 94.33`

**默认接受 0.01 漂移, 但要先问用户**。如果用户要 100% 对齐, 改用"全程不取整, 最后一步 round 2":

```java
// 全精度中间运算 + 末尾 round 2 (对齐用户手算)
BigDecimal premium = ledger.getPremium();
BigDecimal upRate = ledger.getUpRate();
BigDecimal upCommissionRaw = premium.divide(ONE_POINT_06, 10, RoundingMode.HALF_UP).multiply(upRate);
BigDecimal upCommission = upCommissionRaw.divide(ONE_HUNDRED, 2, RoundingMode.HALF_UP);
// 注意: 即使最后 round, 前面保留 10 位精度而非 4 位, 可缩小漂移
```

**铁律**: 不要在用户没确认 0.01 漂移可接受前默默选精度——用户实测时会发现"明明手算 94.33 你给我 94.34", 触发返工。

### Step 6 — DB migration for new fields (税开关新增 case)

If the rule fix requires a new column (e.g. `fin_commission.tax_flag`), the fix is **4 联动点**, not 1:

| # | 文件 | 改动 |
|---|---|---|
| 1 | Domain `<Entity>.java` | 新字段 + getter/setter + `@Excel(name=...)` |
| 2 | `<Entity>ServiceImpl.java` (calc) | 签名加新参数, 公式带新分支 |
| 3 | `<Entity>Service` (interface) | 签名同步 (改了 impl 必须改 interface) |
| 4 | `<Entity>Mapper.xml` | `resultMap` 加 `<result>` + `INSERT` 列表加列 |
| 5 | 前端 `<module>/index.vue` | 表单加 el-switch + 初值 + submit 公式带分支 |
| 6 | `sql/fin_new_tables.sql` (新表) | DDL 加列 + COMMENT 说明规则 |
| 7 | `sql/<table>_add_<col>_<YYYYMMDD>.sql` (已存在表) | ALTER TABLE 加列, **单文件独立**, 命名带日期 |

**最容易漏的第 4 步 (Mapper XML INSERT)** — 编译能过、单元测试可能跳过、运行时 `column count mismatch` 才报。养成改完 SQL 就 `mvn compile + grep "INSERT INTO <table>"` 双确认。

迁移 SQL 模板:

```sql
-- v4 规则: <table> 加 <col> 列(<table>已存在表用 ALTER, 新表直接走 fin_new_tables.sql)
-- YYYY-MM-DD
ALTER TABLE <table>
    ADD COLUMN `<col>` <TYPE> DEFAULT '<default>' COMMENT '<规则说明>'
    AFTER `<preceding_col>`;
```

### Step 7 — `clarify` 超时自决纪律

User-driven clarifications (`clarify(...)`) 在用户不在场时**5 分钟超时未回**。本类工作流连续调用 2 次都超时, 然后靠自决推进。**纪律**:

1. **第一次 clarify 超时** → 把所有开放选项列成"待用户确认的决策表", 列出每个选项的优劣, 重新问一次。
2. **第二次 clarify 还是超时** → **不再问**, 按以下优先级自决:
   - 优先"最小侵入 + 最保守" (不删字段, 只加列 / 只改公式不变接口)
   - 必须保留 DB 历史兼容 (新列有 DEFAULT, 旧记录走 fallback 分支)
   - 自决方案必须在回复里明说"我按 X 方案做的, 因为 Y; 你不同意可以回滚命令 Z"
3. **绝不超过 3 次 clarify** —— 用户的耐心有限, 你的判断力应该填剩余缺口。

### Step 8 — Re-verify after clarify timeout

如果你是按自决方案改的, **改完必须 verify**:
- 后端: `mvn compile` + 看 mapper XML 是否完整联动
- 前端: `grep "form.<新字段>" <vue>` 看初值/reset/submit 三处都覆盖
- DB: ALTER 脚本单文件, 不动原 DDL

## Audit checklist before declaring "done"

```
[ ] Calc method patched + mvn compile green
[ ] Domain /** comment */ matches new rule
[ ] @Excel(name=...) on the auto-calc field matches new rule
[ ] Frontend vue form pre-calc (if any) patched
[ ] MyBatis aggregation SQL: SUM(profit) doesn't use premium as denominator
[ ] Other parallel module (fin_commission vs jonlink_insurance_ledger) NOT silently skipped
[ ] User has acknowledged numeric drift if rounding differs from hand-calc
```

If any item unchecked, **do not** tell the user "全程改完".

## Failure mode: parallel modules

`JonlinkInsuranceLedger.calcCommission` and `FinCommission` are two **independent** financial systems. Common user phrasing:

> "改财务模块" → might mean only ledger, might mean both.

**Ask**: "fin_commission 结算单(独立于台账)也用同一条 v4 规则改? 还是只动台账?" — present as a 2-choice clarify, not open-ended.

## Related references

- Parent: `jonlink-vue3-bootstrap-pitfalls` (L4/L5 frontend + backend first-run traps — different scope, user-owned skill)

## Backend mapper: Date vs String type trap for date-range search fields

When adding a frontend date-range filter (`<el-date-picker type="daterange" value-format="YYYY-MM-DD">`) that hits a MyBatis `<if>` clause comparing against a `Date` column, the symptom is:

```
### Error querying database.  Cause: java.lang.IllegalArgumentException:
invalid comparison: java.util.Date and java.lang.String
```

even though the mapper XML reads `and subscribe_time >= #{subscribeTimeBegin}` and looks correct.

**Root cause**: Element Plus serializes the range into `string[]` on the wire. Spring MVC binds the query param to the Domain field. If the Domain field is declared `Date` but Spring ends up binding a `String` (or `Date` that's been mis-parsed), MyBatis's `PreparedStatement.setObject` rejects the type mismatch at execution time.

**Two acceptable fixes** (pick one per query-only field):

1. **Domain field = `String`, mapper uses `date_format()`** — recommended for query-only fields:
   ```xml
   <if test="subscribeTimeBegin != null and subscribeTimeBegin != ''">
     and date_format(subscribe_time, '%Y-%m-%d') &gt;= #{subscribeTimeBegin}
   </if>
   ```
   ```java
   private String subscribeTimeBegin;   // NOT Date
   ```

2. **Domain field stays `Date`, use `<bind>` to convert in mapper** — keeps `@JsonFormat` output serialization working:
   ```xml
   <bind name="_beginStr" value="subscribeTimeBegin != null ? new java.text.SimpleDateFormat('yyyy-MM-dd').format(subscribeTimeBegin) : null" />
   <if test="_beginStr != null and _beginStr != ''">
     and date_format(subscribe_time, '%Y-%m-%d') &gt;= #{_beginStr}
   </if>
   ```

**Detection**: hit the endpoint with a forced date range via curl. If the response body contains `invalid comparison: java.util.Date and java.lang.String`, the field-type-vs-mapper mismatch is the cause.

**Verify after fix**: inject a known-dated row into MySQL, then re-curl with the date range that should include and exclude that row. Don't trust "default query returns 0 rows" — many JonLink tables have `subscribe_time=NULL` for legacy rows, so 0 results might just mean "no data has dates", not "fix works".
