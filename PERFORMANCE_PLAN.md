# BroomBuster — Map Loading Performance Plan

## Current Bottlenecks

1. **Render.com free tier spins down** after 15 min of inactivity — first request takes 15–30 s.
2. **`/check` builds the full Plotly figure server-side** each call: GDF lookup + geometry serialisation + JSON response can be 3–8 MB for SF.
3. **No client-side caching** — identical location checked twice fetches everything again.
4. **All geometry sent per request** — even unchanged background zones are re-serialised.

---

## Options (ordered by impact vs effort)

### A — UptimeRobot warm-up ping ✅ *Do this now*
- Ping `GET /health` every 5 min (free tier on uptimerobot.com).
- **Result**: eliminates the 15–30 s cold-start for active users.
- **Trade-off**: none. Service stays warm as long as at least one user/bot pings it.
- **TODO**: create UptimeRobot monitor pointing to `https://<render-url>/health`.

---

### B — Client-side `localStorage` response cache ✅ *Do this now*
- Cache the `/check` JSON response keyed by `(lat_rounded, lon_rounded, region)`.
- TTL: 24 h (schedules are daily).
- On cache hit: render instantly, refresh silently in background.
- **Result**: repeat visits / same location = instant load.
- **Trade-off**: stale data up to 24 h (acceptable for street-sweeping schedules). Storage limit ~5 MB per origin (SF figure JSON ≈ 3–8 MB — may need to store only the schedule fields, not the full figure).
- **TODO**:
  - [ ] Store `{ urgency, schedule_even, schedule_odd, car_side, address, ts }` (not the figure) in localStorage.
  - [ ] On cache hit, show schedule immediately; re-fetch figure asynchronously.
  - [ ] Key: `bb_check_${region}_${lat.toFixed(3)}_${lon.toFixed(3)}`.
  - [ ] Evict entries older than 24 h on startup.

---

### C — Pre-generated static GeoJSON on CDN
- At deploy time, run `python scripts/export_geojson.py` to write one GeoJSON per city.
- Host on GitHub Pages / Cloudflare R2 / Supabase Storage (free tiers all work).
- Frontend fetches and renders client-side with Plotly or Mapbox GL layers.
- **Result**: zone overlays load from CDN cache in <1 s after first visit.
- **Trade-off**:
  - Large files: SF ≈ 17 MB, Oakland ≈ 17 MB, Chicago ≈ 4.6 MB (uncompressed). Gzip brings them to ~3–5 MB each.
  - Data updates require re-export and re-deploy (not automated).
  - Street-level colour coding (today/tomorrow/clear) must be computed client-side instead of server-side — needs JS port of `_sweeping_color()`.
- **TODO**:
  - [ ] Write `scripts/export_geojson.py` (one file per city, pre-computed colour fields).
  - [ ] Set up CDN hosting.
  - [ ] Port urgency colouring to JS (`analysis.parse_sweeping_code` → JS equivalent).
  - [ ] Update frontend to fetch from CDN and render with Mapbox GL data layers.

---

### D — PMTiles / MVT vector tiles *(preferred long-term)*
- Convert shapefiles to PMTiles format (single-file archive of tiles at all zoom levels).
- Host the `.pmtiles` file on Cloudflare R2 or similar object storage.
- Use `protomaps-leaflet` or `mapbox-gl` tile source to render client-side.
- **Result**: tiles load incrementally as user pans/zooms — very fast, scales to any dataset size.
- **Trade-off**:
  - Requires `tippecanoe` + `pmtiles` CLI tools for tile generation.
  - Color-coding must be done client-side via Mapbox style expressions.
  - More complex pipeline to maintain.
  - Tile generation takes ~2 min per city (one-time or on data update).
- **TODO**:
  - [ ] Install `tippecanoe`, generate `.pmtiles` for each city.
  - [ ] Upload to Cloudflare R2 (free 10 GB storage).
  - [ ] Implement Mapbox GL style with `match` expressions for urgency colours.
  - [ ] Remove Plotly for map rendering; keep only for car markers or migrate those too.

---

### E — Server-side spatial hash index
- At startup, partition each city's GDF into a 2D grid (~500 m cells).
- `/check` lookups query only cells within the viewport bbox — O(1) vs O(n).
- **Result**: `/check` response time drops from ~2 s to <0.3 s.
- **Trade-off**: higher cold-start RAM (all cities pre-indexed); no change to data pipeline.
- **TODO**:
  - [ ] Implement `SpatialGrid(gdf, cell_deg=0.005)` class in `src/`.
  - [ ] Replace `myCity` full-GDF pass in `maps.py` with grid-filtered subset.
  - [ ] Benchmark before/after on Render.com free tier.

---

### F — Render.com paid tier ($7/mo)
- Eliminates spindown entirely; 2× RAM (1 GB) for both city GDFs in memory.
- **Trade-off**: cost. Worth it once user base grows.

---

## Recommended Sequence

| Phase | Action | Effort | Impact |
|-------|--------|--------|--------|
| 1 | UptimeRobot (A) | 5 min | Eliminates cold-start |
| 2 | localStorage cache (B) | 2 h | Instant repeat loads |
| 3 | Spatial hash index (E) | 1 day | 5–10× server speed |
| 4 | PMTiles + CDN (D) | 3–5 days | Best long-term UX |

Items C and F are lower priority — C has large file sizes and D supersedes it; F is a cost spend best deferred.
