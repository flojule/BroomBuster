# MapLibre GL JS Migration Plan

## Problem

The current map stack has three performance bottlenecks:

1. **~3 MB Plotly bundle** loaded on every page visit. Plotly is a general-purpose charting
   library; we only use the `Scattermapbox` trace type, which is a thin wrapper over Mapbox GL JS.
2. **Server-side figure serialization.** Every `/check` call makes the server convert a full
   GeoDataFrame into Plotly trace arrays (with densified coordinates for hover detection) and
   return the result as JSON. This adds 200–800 ms of CPU work and 200–500 KB to every response.
3. **Round-trip for every map render.** The map cannot display zone overlays without a completed
   `/check` API call, so the map is blank until the server responds.

---

## Solution

| Layer | Before | After |
|---|---|---|
| Map engine | Plotly 2.32 (Mapbox GL wrapper) | **MapLibre GL JS** (Mapbox GL fork, fully open-source) |
| Map tiles | Carto / OSM raster tiles | **OpenFreeMap** vector tiles (free, no API key) |
| Zone rendering | Server builds Plotly traces; client re-renders | **Client renders GeoJSON** from `/check` response |
| `/check` response | Full Plotly `figure` dict (~200–500 KB) | GeoJSON `FeatureCollection` (~50–150 KB, no densification) |
| Hover detection | Plotly densified line coordinates | MapLibre `queryRenderedFeatures` (native GPU) |
| Car markers | Plotly `Scattermapbox` traces | MapLibre `Marker` HTML elements |

---

## Architecture After Migration

```
Browser                                 Server
──────                                  ──────
MapLibre GL JS (~750 KB)  ←─────────── /check → { urgency, schedule, geojson }
OpenFreeMap tiles  ←────── CDN tiles
GeoJSON source  ◄── data from /check response
  └── fill layer      (polygons — Chicago)
  └── outline layer   (polygon borders)
  └── line layer      (streets — Oakland, SF)
Car markers  ◄── MapLibre Marker API (HTML elements)
```

---

## Files Changed

### `src/maps.py`
- Remove `_build_map_figure()` and `plot_map_dict()` (the Plotly-specific pipeline).
- Add `build_map_geojson()`: same urgency logic, same color palette, same hover HTML —
  but output is a GeoJSON `FeatureCollection` with per-feature properties:

  **Polygon zones (Chicago):**
  ```json
  { "render_type": "polygon", "urgency": "tomato", "fill_color": "rgba(r,g,b,a)", "border_color": "rgba(r,g,b,a)", "hover_html": "<b>Street</b><br>..." }
  ```

  **Street lines (Oakland / SF):**
  ```json
  { "render_type": "line", "urgency": "cornflowerblue", "line_color": "cornflowerblue", "line_width": 1.5, "hover_html": "<b>Street</b><br>..." }
  ```

- Remove `_densify()` usage for lines — MapLibre's `queryRenderedFeatures` fires along the
  entire line geometry natively.  This alone reduces response payload by ~60% for line-heavy
  cities.
- Keep `plot_map()` (CLI browser preview) using Plotly — it is only used for offline debugging
  and not part of the API path.

### `api/api.py`
- Replace `maps.plot_map_dict(...)` call with `maps.build_map_geojson(...)`.
- Return `geojson` key instead of `figure` key in the `/check` response.
- Remove the `import maps` Plotly dependency from the hot path.

### `frontend/index.html`
- **Remove** `<script src="https://cdn.plot.ly/plotly-2.32.0.min.js">` (~3 MB).
- **Add** MapLibre GL JS CDN (`maplibre-gl@4`) + its CSS (~750 KB total).
- Map style URLs (OpenFreeMap, no API key required):
  - Light: `https://tiles.openfreemap.org/styles/positron`
  - Dark: `https://tiles.openfreemap.org/styles/dark-matter`
  - Standard: `https://tiles.openfreemap.org/styles/bright`
- Replace all Plotly API calls:

  | Old (Plotly) | New (MapLibre) |
  |---|---|
  | `Plotly.newPlot(mapDiv, [], layout)` | `new maplibregl.Map({ container: 'map', style })` |
  | `Plotly.react(mapDiv, traces, layout)` | `map.getSource('zones').setData(geojson)` |
  | `Plotly.relayout(mapDiv, {'mapbox.center': ...})` | `map.flyTo({ center, zoom })` |
  | `Plotly.restyle(...)` for car markers | `marker.getElement().style.width = '...'` |
  | `mapDiv._fullLayout.mapbox._subplot.map` | direct `map` variable |
  | `plotly_click` / `plotly_hover` events | `map.queryRenderedFeatures` in `mousemove` |
  | `Scattermapbox` car traces | `maplibregl.Marker` HTML elements |

- Zone layers added after `map.on('load')`:
  1. `zones-fill` — `type: fill`, filtered to polygon features, color from `fill_color` property
  2. `zones-polygon-outline` — `type: line`, polygon borders from `border_color` property
  3. `zones-street-line` — `type: line`, street lines from `line_color`/`line_width` properties
- Hover: `map.on('mousemove', queryRenderedFeatures)` → show `#custom-hover` element
- Style switching: `map.setStyle(newUrl)` + `map.once('style.load', () => re-add zone layers)`

---

## What Does NOT Change

- Auth flow (Supabase)
- Cars panel UI and all car management logic
- Schedule display (`scheduleHTML`, `updateStatusFromSchedules`)
- `/prefs`, `/cities`, `/health` endpoints
- Server-side data loading (`data_loader.py`, `analysis.py`, `cities.py`)
- `maps.plot_map()` (offline CLI preview — kept with Plotly)

---

## Performance Impact

| Metric | Before | After |
|---|---|---|
| JS bundle (map engine) | ~3 MB (Plotly) | ~750 KB (MapLibre) |
| `/check` response size | ~200–500 KB (Plotly figure) | ~50–150 KB (raw GeoJSON) |
| Server CPU per /check | High (trace building + densification) | Lower (GeoJSON mapping only) |
| Hover detection | Densified coordinates in JS | Native GPU hit-testing |
| Tile rendering | Raster PNG tiles | Vector tiles (sharp at all zoom levels) |
| Map style switch | Full `Plotly.newPlot` re-render | `map.setStyle()` smooth transition |
