# three-scope-map 石家庄单市集成实录

从 ZhejiangThreeMap.vue 模板适配到石家庄单市（JonLink 数据大屏 `/wx/screen`）的已验证参数与文件布局。

## 文件布局（Vue3-TS 项目）

```
src/views/wx/dashboard/components/
  ShijiazhuangThreeMap.vue      # 引擎（ZhejiangThreeMap 改名，约 2800 行）
  mapTheme.ts                   # 主题：MAP_THEME_PRIMARY='#9fc53a' 单入口派生
  mapTerrainMaterial.ts         # 地形材质（4 张 jpg 纹理）
  mapDataAdapter.ts             # scope 状态 + GeoJSON 缓存（本地化后零网络）
src/assets/maps/
  sjz.json                      # 石家庄 22 区县（DataV 130100_full.json）
  district/<adcode>.json        # 22 个区县本地数据（下钻用）
src/assets/textures/map/        # terrain-diffuse/height/normal/roughness.jpg
src/types/geo.ts                # GeoFeatureCollection 等类型
```

## 已验证参数

```ts
// getScopeTransform：city/district 必须 scale 1.0（模板默认 0.768 → 黑边）
{ position: new THREE.Vector3(-16, -42, -22), scale: 1.0 }

// cameraViewConfig.byScope：city 和 district 共用（几何体 mapScale 自适应后同样占满逻辑画布）
city:     { fov: 31, position: [64, -644, 417], target: [-16, -42, -22] },
district: { fov: 31, position: [64, -644, 417], target: [-16, -42, -22] },
// 1280x633 视口、canvas 556x270 实测：fillW 86.7% / fillH 89.6%
// district 下钻实测：fillW 99.6% / fillH 90.4%（区县数据范围更贴合）
```

迭代方法：改参数 → 刷新 → 跑 scripts/probe-map-fill.js → 目标两轴 87-90%。顶部 y=0 贴边说明太近，回退。

## DataV GeoJSON URL 规则

| 层级 | URL | 结果 |
|---|---|---|
| 市 | `https://geo.datav.aliyun.com/areas_v3/bound/130100_full.json` | 200（含 22 区县 children） |
| 区县 | `https://geo.datav.aliyun.com/areas_v3/bound/130102.json` | 200（仅自身边界，1 feature） |
| 区县 | `https://geo.datav.aliyun.com/areas_v3/bound/130102_full.json` | **404**（区县级没有 full 版） |

模板 `datavUrls` district 分支先试 `_full.json` 再试 `.json`——能 fallback 但每次下钻多一次 404 往返；本地化后不走网络。

## 石家庄 22 区县 adcode（properties.adcode，下钻 code 来源）

130102 长安区 · 130104 桥西区 · 130105 新华区 · 130107 井陉矿区 · 130108 裕华区 · 130109 藁城区 · 130110 鹿泉区 · 130111 栾城区 · 130121 井陉县 · 130123 正定县 · 130125 行唐县 · 130126 灵寿县 · 130127 高邑县 · 130128 深泽县 · 130129 赞皇县 · 130130 无极县 · 130131 平山县 · 130132 元氏县 · 130133 赵县 · 130181 辛集市 · 130183 晋州市 · 130184 新乐市

下载脚本（python）：遍历 `https://geo.datav.aliyun.com/areas_v3/bound/{adcode}.json`，`json.dump(ensure_ascii=False)` 存 `src/assets/maps/district/`。22 个全部 200。

## 外部触发下钻（列表点击 → 地图下钻）

组件加 `drillName?: string` prop，dashboard 传 `:drill-name="selectedCounty"`。watch 逻辑（去重关键）：

```ts
watch(() => props.drillName, async (name) => {
  if (!name || isDrilling) return;
  if (currentState.scope === 'district') {
    const top = drillStack[drillStack.length - 1];
    if (top && top.state.regionName === name) return; // 地图自身点击已下钻 → 跳过
    await drillBack();                                 // 切区县：先回市级再钻
  }
  void drillToFeature(name);
});
```

地图点击 emit select 会同步更新 selectedCounty → drillName → 此 watch 与 onPointerDown 内的 drillToFeature 竞争，`isDrilling` 保证败者变 no-op。

## 调试要点

- 下钻是否真执行：临时在 `drillToFeature` 开头插 `console.warn('[drill] enter', name, 'isDrilling=', isDrilling, 'scope=', currentState.scope)`，浏览器里先 `window.__warns=[]; console.warn = (...a)=>{__warns.push(...); orig(...)}` 再点击。
- 判断点击是否命中区县：**看 drill 控制条文本**（`区县 / 裕华区`），不要看列表 `.active`——active 会被之前的列表点击残留，导致误判"点了没反应"。
- 合成点击要在页面加载 + 入场动画（~3.5s）后；多次乱点可能让 isDrilling/drillStack 状态混乱，先 `location.reload()` 清状态。
- 下钻后区县地图 fillW 99.6% 属正常（单区县边界贴合），无需再调相机。
