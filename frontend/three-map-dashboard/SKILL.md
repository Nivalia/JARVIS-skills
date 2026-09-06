---
name: three-map-dashboard
description: "3D map in dashboards: sizing, camera fit, drill-down."
---

# 3D Map in Dashboard (three.js / three-scope-map)

Integrating the three-scope-map template engine (or any three.js map widget) into a RuoYi/Vue admin dashboard page. Written from adapting the Zhejiang template to a single-city (石家庄) scope — every pitfall below was hit and fixed in real browser sessions.

## Workflow

1. **Copy the template, don't freestyle** (three-scope-map rule): copy engine files (`mapTheme.ts` / `mapTerrainMaterial.ts` / `mapDataAdapter.ts` / the Vue component), keep SPDX + author attribution comments (code-only, never render in UI).
2. **Adapt data**: GeoJSON → `src/assets/maps/`, terrain textures → `src/assets/textures/map/`, geo types → `src/types/geo.ts`. Fix relative import depth — components 2+ dirs deep need `../../../../` not `../../`.
3. **Set scope** in `mapDataAdapter`: `initialMapState` + cache keyed `scope:code` (e.g. `city:130100`).
4. **Verify with readPixels** (scripts/probe-map-fill.js) — never trust a screenshot alone; measure geometry bbox fill %.

## Pitfalls

### 1. Absolute root stage overflows the card
Component root `.map-stage` is `position: absolute; inset: 0; width: 100%`. If the wrapper div is `position: static`, the containing block resolves upward → canvas renders at viewport-ish size and **spills out of the card** (seen: canvas 1056px vs card 616px, "地图出框了"). Fix: wrapper `style="position: relative"` — one line.

### 2. getScopeTransform scale shrinks the map
Template returns `scale 0.768` for non-world scopes → geometry occupies only ~54%×69% of canvas → heavy black borders. For a single city/district set scale `1.0`. `updateProjectionFromGeoData` auto-fits geometry to the logical canvas (860×530 minus padding), so scale 1.0 fills it.

### 3. Camera is calibrated for the whole country
`cameraViewConfig.default` (fov 31, position [72,-760,500], target [-18,-42,8], distance ~875) leaves a single city small/off-center. Add `byScope.city` (and `district` for drill-down) with a closer position + target at the map group center (`getScopeTransform` position, e.g. (-16,-42,-22)). Note `fitBuiltInCameraViewToViewport` only adjusts when aspect < 16/9, so wide canvases keep the raw config. Iterate: change → reload → probe fill% until ~87–90% both axes (top edge touching canvas = too close, back off).

### 4. Ripple/flyline source is hash-random per city
`getEffectSourceLabelName` for `scope === 'city'` picks `labels[hashString(code) % labels.length]` — pure luck which county radiates (石家庄 → 深泽县, 东北远郊). Users notice immediately. Fix: prefer main urban districts first (`labels.find(l => /长安区|桥西区|.../.test(l.name))`), fall back to hash. One function feeds both label ripple and flyline source.

### 5. Drill control bar covers the map
`.map-drill-control` template CSS is `left:50%; top:176px; translateX(-50%)` → sits mid-map. Move to `left:12px; top:12px`. Users hate UI overlaid on the map ("菜单位置在地图中间 真的好吗").

### 6. Drill-down silently does nothing
- `createDrillControl()` often gets commented out when "simplifying" — that kills the Back button, not the drill. Keep it; district drill needs it.
- District data: DataV `{adcode}_full.json` **404s**; only `{adcode}.json` exists (own boundary, 1 feature). City `{code}_full.json` works. `loadMapLevel` falls back through its URL list, but that means a 404 + fetch round-trip per drill.
- **Localize district GeoJSON**: download all `{adcode}.json` → `src/assets/maps/district/`, static-import, prefill `geoJsonCache`. Corporate networks often can't reach `geo.datav.aliyun.com`; the failure is **silent** (catch → console.warn, drill just doesn't happen). Zero-network drill-down is the only reliable option.

### 7. External drill trigger (list click → drill)
To drill from a list click, add a `drillName` prop + async watch that calls internal `drillToFeature`. Dedupe: if already `district` and `drillStack[top].state.regionName === name`, skip; else `await drillBack()` then drill. The `isDrilling` guard makes the losing call a no-op when the map's own pointer handler and the watch race.

### 8. Fixed pixel heights break on other viewports
A fixed map height (e.g. 250px) becomes a "扁带" on wide screens (1920px central column → 1700×250). Use `flex:1; min-height:0` inside a grid row so the map fills remaining height; give side panels a `min-height` (e.g. county list 170px) so the row can't collapse. User screens vary; sanity-check at 1280 and 1920.

## Layout recipe (dark screen, one page, no scroll)

- `.dashboard { height: calc(100vh - <chrome>px); overflow: hidden; display:flex; flex-direction:column }` → single screen, no scrollbar.
- Body grid: `grid-template-columns: 216px minmax(0,1fr) 236px; grid-template-rows: minmax(0,1fr) auto` (side panels / center map / bottom strip).
- Bottom strip: `grid-template-columns: 250px minmax(0,1fr) 330px` (待办 / 流水表 / 扫码动态).
- Side panels `display:flex; flex-direction:column; min-height:0`; scrollable lists `flex:1; overflow:auto`.
- Dark el-table via `--el-table-*` CSS vars on the table class (transparent bg, blue header).
- Map wrapper: `position:relative; flex:1; min-height:0; margin:8px; background:#050b05; overflow:hidden`.

## Verification

- `scripts/probe-map-fill.js` — paste into browser_console: canvas size, geometry bbox, fill %, inside-check.
- Hover works? Snapshot readPixels → dispatch pointermove → resnapshot → count changed pixels (>threshold) = raycast hit.
- Click-through: dispatch pointerdown/up on `.map-host`; **verify via drill-control text, NOT the list `.active` class** — active persists from earlier list clicks and misleads diagnosis.
- Intercept `console.warn` (swap console.warn, collect into window array) to catch silent `Map drilldown failed` paths.
- Reload before interaction tests: entry animation (~3.5s) makes early synthetic clicks miss polygons.
- DataV district adcode table + camera values used: references/three-scope-map-sjz-integration.md

## Support files
- `references/three-scope-map-sjz-integration.md` — 石家庄 single-city adaptation detail: file layout, working camera values, 22-district adcode table, drill-stack watch snippet.
- `scripts/probe-map-fill.js` — WebGL readPixels fill probe (paste into browser_console).
