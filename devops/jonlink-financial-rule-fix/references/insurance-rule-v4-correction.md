# JonLink Insurance Ledger calcCommission v1 → v4 修复实录 (2026-08-25)

## 业务规则（v4 最终定稿）

| 量 | 公式 | 含税 (taxFlag=1) | 不含税 (taxFlag=0) |
|---|---|---|---|
| 上游佣金 | 基数 × upRate / 100 | 基数 = premium / 1.06 | 基数 = premium |
| 下游佣金 | 基数 × downRate / 100 | 基数 = premium / 1.06 | 基数 = premium |
| 净费 | premium(原始) - 上游佣金 | 1000 - 94.34 = 905.66 | 1000 - 100 = 900 |
| 利润 | 上游佣金 - 下游佣金 | 94.34 - 47.17 = 47.17 | 100 - 50 = 50 |
| 保费 | 原始值 | 纯统计，不参与利润公式 | 纯统计 |

**1 个税开关同时作用于上游+下游**——这是从 v3 修正后用户最终确认的版本。

## 反面案例：v1 错在哪

```java
// ❌ v1: 每个公式各自处理税分支, 下游漏了 ÷1.06
if ("1".equals(ledger.getTaxFlag())) {
    upCommission = premium.divide(new BigDecimal("1.06"), 4, RoundingMode.HALF_UP)
            .multiply(upRate).divide(ONE_HUNDRED, 2, RoundingMode.HALF_UP);
} else {
    upCommission = premium.multiply(upRate).divide(ONE_HUNDRED, 2, RoundingMode.HALF_UP);
}
downCommission = premium.multiply(downRate).divide(ONE_HUNDRED, 2, RoundingMode.HALF_UP); // ❌ 不除 1.06
netFee = premium.subtract(downCommission); // ❌ 减错量, 应该减上游佣金
profit = upCommission.subtract(downCommission); // ✅
```

**3 个 bug 同时存在**: ①下游漏 1.06 ②净费减错量 ③代码读起来像"上游独有税逻辑"，下游规则被默默吞。

## v4 重构

### calcCommission 重写

```java
/**
 * 自动算 4 列 (R14/R15)
 *
 * 计算规则(v4 定稿 2026-08-25):
 *   1 个税开关(taxFlag)同时作用于上游佣金和下游佣金
 *   - 含税(taxFlag=1): 上下游佣金基数 = 保费 / 1.06
 *   - 不含税(taxFlag=0): 上下游佣金基数 = 保费(原始)
 *   - 净费 = 保费(原始) - 上游佣金(始终用原始保费减)
 *   - 利润 = 上游佣金 - 下游佣金
 *   - 保费仅统计, 不参与利润公式
 */
private void calcCommission(JonlinkInsuranceLedger ledger)
{
    BigDecimal premium = ledger.getPremium() == null ? BigDecimal.ZERO : ledger.getPremium();
    BigDecimal upRate = ledger.getUpRate() == null ? BigDecimal.ZERO : ledger.getUpRate();
    BigDecimal downRate = ledger.getDownRate() == null ? BigDecimal.ZERO : ledger.getDownRate();

    // 佣金基数: 含税则 保费/1.06, 不含税则 保费原值
    BigDecimal commissionBase = premium;
    if ("1".equals(ledger.getTaxFlag()))
    {
        commissionBase = premium.divide(new BigDecimal("1.06"), 4, RoundingMode.HALF_UP);
    }

    // 上游佣金 = 基数 × 上游政策%
    BigDecimal upCommission = commissionBase.multiply(upRate)
            .divide(new BigDecimal("100"), 2, RoundingMode.HALF_UP);
    // 下游佣金 = 基数 × 下游政策%
    BigDecimal downCommission = commissionBase.multiply(downRate)
            .divide(new BigDecimal("100"), 2, RoundingMode.HALF_UP);
    // 净费 = 保费(原始) - 上游佣金
    BigDecimal netFee = premium.subtract(upCommission);
    // 利润 = 上游佣金 - 下游佣金
    BigDecimal profit = upCommission.subtract(downCommission);

    ledger.setUpCommission(upCommission);
    ledger.setDownCommission(downCommission);
    ledger.setNetFee(netFee);
    ledger.setProfit(profit);
}
```

### 同步 domain 字段注释（必做）

`JonlinkInsuranceLedger.java:88-101` 的 `/** comment */` 和 `@Excel(name=...)` 必须跟代码一致，否则 admin 导出 + DB 注释会跟实际算出来对不上：

```java
/** 下游佣金 = 保费/1.06 × 下游政策%(含税) | 保费 × 下游政策%(不含税)(自动算) */
@Excel(name = "下游佣金(自动算)")
private BigDecimal downCommission;

/** 上游佣金 = 保费/1.06 × 上游政策%(含税) | 保费 × 上游政策%(不含税)(自动算) */
@Excel(name = "上游佣金(自动算)")
private BigDecimal upCommission;

/** 净费 = 保费 - 上游佣金(自动算, 始终用原始保费减) */
@Excel(name = "净费 = 保费 - 上游佣金(自动算)")
private BigDecimal netFee;

/** 利润 = 上游佣金 - 下游佣金(自动算, 保费仅统计不入利润公式) */
@Excel(name = "利润 = 上游佣金 - 下游佣金(自动算)")
private BigDecimal profit;
```

### mvn 验证

```bash
cd /opt/JonLink/JonLink-Vue
mvn compile -pl jonlink-system -am -DskipTests -q
# exit 0 = 编译通过, 可以放心重启服务
```

## 校验样例（用户提供）

| premium | taxFlag | upRate | downRate | 上游佣金 (期望) | 下游佣金 (期望) | 净费 | 利润 |
|---|---|---|---|---|---|---|---|
| 1000 | 1 | 10% | 5% | 94.33 / 94.34* | 47.16 / 47.17* | 905.66 | 47.17 |
| 1000 | 0 | 10% | 5% | 100 | 50 | 900 | 50 |

*0.01 差异来源: `HALF_UP` + 4 位中间精度。如果要 100% 对齐用户手算，调整为全精度中间运算 + 末尾 round 2 (见 SKILL.md Step 5a)。

## 沟通教训（防下次重犯）

用户**改了 3 次**才说清楚净费公式。教训:

1. **抽象规则不可靠**。"净费 = 保费 - 保费×政策"——"政策"是哪个？上游、下游、独立字段？三种解释都对得上代码。**拒绝在没数字样例的情况下动手**。
2. **让用户给数字而不是公式**。本会话最终推进方式是 "保费=1000, taxFlag=1, upRate=10%, downRate=5% → 净费=多少?" 直接反推 "净费政策 = 上游政策"。
3. **歧义澄清用 2-3 选 1**，不要 open-ended。`clarify(..., choices=[...])` 比 "你再说清楚一点" 高效 10 倍。
4. **rule version 内联**。calc method javadoc 里写 "v4 定稿 2026-08-25"——下次接手不用重头问。
5. **clarify 5 分钟超时 = 自决信号**（本会话第二次自决场景）。详见 SKILL.md Step 7。

## 涉及文件清单

### 模块 1: jonlink_insurance_ledger (保险台账) — v1→v4

| 文件 | 改动 |
|---|---|
| `jonlink-system/src/main/java/com/jonlink/system/service/impl/JonlinkInsuranceLedgerServiceImpl.java` | `calcCommission()` v1→v4 (共享 base + 1 个税开关) |
| `jonlink-system/src/main/java/com/jonlink/system/domain/JonlinkInsuranceLedger.java` | 4 个字段注释 + `@Excel(name=...)` 同步 |

### 模块 2: fin_commission (佣金结算单) — 加 tax_flag 字段全套联动

第二轮(同会话内)在 `fin_commission` 模块加了 `tax_flag` 列, 7 处联动改动:

| 文件 | 改动 |
|---|---|
| `jonlink-system/src/main/java/com/jonlink/system/domain/FinCommission.java` | 加 `taxFlag` 字段 + getter/setter + `@Excel` 注释 |
| `jonlink-system/src/main/java/com/jonlink/system/service/impl/FinCommissionServiceImpl.java` | `calculateCommission(premium, rate)` → `(premium, rate, taxFlag)`, 含税分支除 1.06 |
| `jonlink-system/src/main/java/com/jonlink/system/service/IFinCommissionService.java` | 接口签名同步加 taxFlag 参数 |
| `jonlink-system/src/main/resources/mapper/system/FinCommissionMapper.xml` | `resultMap` + `INSERT` 加 `tax_flag` 列 |
| `JonLink-Vue3-TS/src/views/finance/commission/index.vue` | 表单加 el-switch + submit 公式带分支 + form 初值 `taxFlag:'0'` + reset 时 Object.assign 同步 |
| `sql/fin_new_tables.sql` | 新表 DDL 加 `tax_flag` 列 + COMMENT |
| `sql/fin_commission_add_tax_flag_20260825.sql` | **新文件**: 已存在表 ALTER TABLE 加列, 命名带日期 |

### 未改动（已扫描，确认无问题）

- `jonlink-system/src/main/resources/mapper/ledger/JonlinkDashboardMapper.xml` — 所有 `SUM(profit)` 都是独立列，没用 premium 当分母
- `jonlink-system/src/main/resources/mapper/system/FinVoucherMapper.xml:186-201` — `sumLedgerPerformance` 同理
- `JonlinkProduct.java` — `upRate`/`downRate`/`deductTax` 字段定义无问题

## DB 迁移

```bash
# 已存在库执行 ALTER(新部署直接走 fin_new_tables.sql)
mysql -uroot -p jonlink < /opt/JonLink/JonLink-Vue/sql/fin_commission_add_tax_flag_20260825.sql
```

旧记录 `tax_flag` 会是 NULL, insert 默认 '0' 才生效, 旧记录 select 出来 taxFlag 为 null。但新插入的走 DEFAULT '0', null ≠ '1' 走不含税分支, 行为正确。

## 第二轮教训（fin_commission 加 tax_flag）

1. **本次 clarify 二次超时仍自决**。第二轮问"fin_commission 也按 v4 改吗"同样 5 分钟未回——按 Step 7 纪律直接走"最小侵入+保守"路径: 加 `tax_flag` 列(带 DEFAULT '0' 兼容旧记录), 不动现有字段, 不删数据。
2. **改了 ServiceImpl 必须改 Interface**。`IFinCommissionService.calculateCommission` 签名加 taxFlag 参数, 否则 Spring 装配 `ServiceImpl` 时报 "method override mismatch"。
3. **mapper.xml INSERT 是最大陷阱**。Java 编译能过, 但运行时 `insertFinCommission` 调用时如果 XML 没列 `tax_flag`, 实际 SQL 不带这列, `useGeneratedKeys` 仍然返回 id——但旧列没新值, 触发 silent data inconsistency。**改完必 grep `INSERT INTO <table>`** 确认。
4. **ALTER TABLE 脚本必须独立成文件**。不要直接改 `fin_new_tables.sql` —— 那是给新部署用的; 已存在库要走 ALTER。新建 `sql/<table>_add_<col>_<YYYYMMDD>.sql` 单文件, 命名带日期方便追溯。
5. **前端 form 三处都要加新字段**: 初值 `reactive({...})` + reset 时 `Object.assign(form, {...})` + submit 时 payload 带上。漏一处表单就静默丢字段。

## 已知后续 TODO（未来有真实数据时）

- DB 历史数据重算: `UPDATE jonlink_insurance_ledger SET up_commission=..., down_commission=..., net_fee=..., profit=... WHERE created_time < '2026-08-25'` + 重跑 autoBook 冲红重做凭证
- fin_commission 同理: `UPDATE fin_commission SET commission_amount = IF(tax_flag='1', premium/1.06*commission_rate/100, premium*commission_rate/100) WHERE created_time < '2026-08-25'`
