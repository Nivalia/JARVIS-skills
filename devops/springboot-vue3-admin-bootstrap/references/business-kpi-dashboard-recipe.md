# Business KPI Dashboard — Session Recipe (2026-08-17, jonlink ledger)

Session-specific detail for Pitfall 30 (business KPI dashboard pattern). Captures the exact insurance-ledger dashboard that was built, with verified data sources, controller shape, and the dark gradient KPI card CSS.

## Why this skill exists separately

`jonlink-data-screen` (user-owned) and `jonlink-vue3-data-screen` (user-owned) both focus on **3D-map dashboards**. Neither covers pure-business-KPI pages with no map. This reference captures the pattern so the next "build a dashboard for module X" request doesn't re-discover:
- The wx/* controller is wrong for business data
- Pure-SQL aggregation goes in a separate mapper
- Dark gradient cards use a single `--accent` CSS variable

## What was built (2026-08-17)

User said: "台账看板 数据不真实,页面不好看 从新设计" (台账看板 = ledger dashboard). Investigation showed:

1. **Existing dashboard** (`/wx/dashboard/*`) returned 200, but values were public-account stats (`fans / verified / verified_amount / ledger_premium / ledger_profit`) — meaningless for an insurance ledger business.
2. **No `JonlinkDashboardController` existed** — the wx controller was the only dashboard controller in the project. Ledgers and product/channel tables were not represented.
3. **Wx controller's `WxBizMapper.xml`** queries `wx_mp_user / wx_biz_order / wx_dist_member` — completely disconnected from `jonlink_insurance_ledger`.

## Backend architecture

```
controller/ledger/JonlinkDashboardController.java
   → @RequestMapping("/ledger/dashboard")
   → extends BaseController
   → 7 @GetMapping endpoints, each returns AjaxResult = success(Map) or success(List<Map>)
   → no @PreAuthorize (default role check via sys_menu perms handles it)

mapper/ledger/JonlinkDashboardMapper.java (interface)
   → 13 methods, ALL return Map<String,Object> or List<Map<String,Object>>
   → no entity coupling; pure aggregation

mapper/ledger/JonlinkDashboardMapper.xml
   → resultType="map" on every <select>
   → pure SELECTs; no DDL/DML; aggregation over 5 business tables
   → data sources: jonlink_product / jonlink_channel / jonlink_channel_user /
                   jonlink_insurance_ledger / jonlink_settle_record
```

The 5-table source list is the entire dependency surface. To port this pattern to another business module, **change the 5 tables and the KPI column names**; everything else (controller layout, mapper interface shape, SQL templates) is generic.

## SQL template patterns (verified)

### KPI aggregation — single endpoint, multiple SELECTs
```xml
<select id="kpiProduct" resultType="map">
    SELECT COUNT(*) AS product_count,
           SUM(CASE WHEN shelf_status='1' THEN 1 ELSE 0 END) AS product_active
    FROM jonlink_product
</select>

<select id="kpiLedger" resultType="map">
    SELECT IFNULL(SUM(premium),0) AS total_premium,
           IFNULL(SUM(profit),0)  AS total_profit,
           COUNT(*) AS total_policy,
           IFNULL(SUM(CASE WHEN up_settle_status='0' THEN premium ELSE 0 END),0) AS unsettled_up_premium,
           IFNULL(SUM(CASE WHEN down_settle_status='0' THEN premium ELSE 0 END),0) AS unsettled_down_premium
    FROM jonlink_insurance_ledger
</select>
```

### Trend by date — group by formatted date
```xml
<select id="premiumTrend" resultType="map">
    SELECT DATE_FORMAT(ledger_date,'%m-%d') AS d,
           IFNULL(SUM(premium),0) AS premium,
           IFNULL(SUM(profit),0) AS profit,
           COUNT(*) AS cnt
    FROM jonlink_insurance_ledger
    WHERE ledger_date &gt;= DATE_SUB(CURDATE(), INTERVAL #{days} DAY)
    GROUP BY DATE_FORMAT(ledger_date,'%Y-%m-%d')
    ORDER BY DATE_FORMAT(ledger_date,'%Y-%m-%d')
</select>
```

### Top N by metric — ORDER BY DESC LIMIT
```xml
<select id="channelTop" resultType="map">
    SELECT up_channel AS name,
           IFNULL(SUM(premium),0) AS premium,
           COUNT(*) AS cnt,
           IFNULL(SUM(profit),0) AS profit
    FROM jonlink_insurance_ledger
    WHERE up_channel IS NOT NULL AND up_channel &lt;&gt; ''
    GROUP BY up_channel
    ORDER BY premium DESC
    LIMIT #{limit}
</select>
```

### Distribution (returned as map-of-lists for 2×2 pie matrix)
```xml
<select id="productShelf" resultType="map">
    SELECT CASE shelf_status WHEN '1' THEN '上架' WHEN '0' THEN '下架' ELSE '未知' END AS name,
           COUNT(*) AS value
    FROM jonlink_product
    GROUP BY shelf_status
</select>
```
Controller bundles 3-4 such SELECTs into one `data = {shelf, policy, tax, company}` map → returned to the 2×2 pie matrix in one round-trip.

## Controller shape (verified, copy-paste pattern)

```java
@GetMapping("/kpi")
public AjaxResult kpi() {
    Map<String,Object> data = new HashMap<>();
    Map<String,Object> product = jonlinkDashboardMapper.kpiProduct();
    Map<String,Object> channel = jonlinkDashboardMapper.kpiChannel();
    Map<String,Object> salesman = jonlinkDashboardMapper.kpiSalesman();
    Map<String,Object> ledger = jonlinkDashboardMapper.kpiLedger();
    data.put("productCount", product.get("product_count"));
    data.put("channelCount", channel.get("channel_count"));
    data.put("salesmanCount", salesman.get("salesman_count"));
    data.put("totalPremium", ledger.get("total_premium"));
    data.put("totalProfit", ledger.get("total_profit"));
    data.put("totalPolicy", ledger.get("total_policy"));
    data.put("unsettledPremium", ledger.get("unsettled_premium"));
    return success(data);
}
```

## Verified data after first E2E (2026-08-17)

After mvn build + restart + 7 endpoint smoke test:

| Endpoint | HTTP | Sample |
|---|---|---|
| `/ledger/dashboard/kpi` | 200 | productCount=86 / channelCount=25 / salesmanCount=160 / totalPremium=280 / totalProfit=14 / totalPolicy=1 |
| `/ledger/dashboard/premiumTrend?days=30` | 200 | `[{d:'08-17',premium:280,profit:14,cnt:1}]` |
| `/ledger/dashboard/companyShare` | 200 | `[{name:'平安产险',value:280}]` |
| `/ledger/dashboard/channelTop?limit=10` | 200 | `[{name:'联创云服',premium:280,cnt:1,profit:14}]` |
| `/ledger/dashboard/productDistribution` | 200 | `{tax:[{name:'不扣税',value:86}], company:[8 companies], shelf:[{name:'上架',value:86}], policy:[{name:'上游政策',value:86}]}` |
| `/ledger/dashboard/salesmanTop?limit=10` | 200 | `[{name:'杜梦雨',premium:280,cnt:1,profit:14}]` |
| `/ledger/dashboard/recentLedger?limit=5` | 200 | `[{policy_no:'10927066601316606823', product_name:'平安惠农意外险(家庭版)', premium:280, profit:14, ledger_date:'2026-08-17', up_status:'待结算', down_status:'已结算'}]` |

8 insurance companies surfaced in productDistribution: 平安产险/太平洋产险/人保财险/众安在线/京东安联/安盛天平/紫金财险/华农财险 — these reflect what `jonlink_product` actually has, not what the wx controller claimed.

## Frontend (dashboard/index.vue) — key CSS

```css
.dashboard {
  background: linear-gradient(135deg, #0B1220 0%, #0F172A 60%, #111827 100%);
  min-height: 100vh;     /* not calc(100vh - 84px) */
  padding: 20px;
  color: #E2E8F0;
}

.kpi-card {
  --accent: #3B82F6;
  position: relative;
  padding: 18px 16px;
  border-radius: 8px;
  background: linear-gradient(135deg, rgba(30,41,59,.85), rgba(15,23,42,.85));
  border: 1px solid rgba(148,163,184,.12);
  overflow: hidden;
  transition: transform .2s, box-shadow .2s;
}
.kpi-card:hover { transform: translateY(-2px); box-shadow: 0 8px 24px rgba(6,182,212,.15); }
.kpi-card::before {
  content: ''; position: absolute; top: 0; left: 0; right: 0; height: 2px;
  background: var(--accent); box-shadow: 0 0 12px var(--accent);
}
.kpi-blue   { --accent: #3B82F6; }
.kpi-cyan   { --accent: #06B6D4; }
.kpi-purple { --accent: #A855F7; }
.kpi-orange { --accent: #F59E0B; }
.kpi-green  { --accent: #10B981; }
.kpi-red    { --accent: #EF4444; }
.kpi-value { font-size: 26px; font-weight: 700; color: #F8FAFC;
             font-family: 'DIN','Helvetica Neue',sans-serif; }
```

Don't try to use the existing RuoYi admin theme (light table-card style) on a business dashboard — it looks like a CRUD page. The user reaction was "数据不真实, 页面不好看" partly because the wx dashboard was rendered in light theme with no business KPIs.

## What NOT to do

- **Don't reuse `WxMpBizController`/`WxBizMapper`** for a business dashboard — the wx template leaks into everything and the data is wrong.
- **Don't add new columns to existing entity mappers for aggregation** — keep the dashboard mapper separate. Entity mappers should serve CRUD; aggregation gets its own file with `resultType="map"`.
- **Don't `el-table` every chart** — the user said "页面不好看". The 6 KPI + 4 charts + recent rows mix is the look.
- **Don't fix-height the dashboard container** — `min-height: 100vh` lets it scroll on small screens; the 3D-map dashboard uses `calc(100vh - 84px)` because the map needs to fill the viewport. KPI pages have more content than fits one screen and scrolling is fine.

## Future portability checklist

When porting this to another jonlink module:

1. Replace the 5 source table names (`jonlink_product` → `<module>_product` etc.) in the XML.
2. Change KPI column aliases (`product_count`, `total_premium`) to match the new module's metric names.
3. Frontend: change `upChannel`, `applicant`, `premium`, `profit`, `ledger_date` to whatever the new module uses.
4. The `BaseController` `success()` wrapper, the `<select resultType="map">` shape, the `@GetMapping` defaults, and the `?days=30 / ?limit=10` param conventions stay the same.

The seven-endpoint ceiling (KPI + trend + share + top + distribution + recent) is the right shape for any "how is the business doing" page; if you need more than seven endpoints, the page has too many concerns and should be split.