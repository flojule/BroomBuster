# BroomBuster — Performance Plan

All options listed here are free. Paid upgrades (Render paid tier, etc.) are deliberately excluded — this is a prototype.

---

## Current bottlenecks

### 1. Render.com cold start (~20-40 s)
The free tier spins the container down after 15 minutes of inactivity. The next request has to wait for Docker to start, Python to load, and all city GeoDataFrames to load into memory. For a first-time or infrequent visitor this is the dominant source of latency.

### 2. Server-side Plotly figure on every /check (3-8 MB response)
The `/check` endpoint builds a full Plotly figure including all street-segment geometries for the region, serialises it to JSON, and sends it over the wire. For San Francisco this is 3-8 MB per request. This drives both server latency (~1-2 s) and network transfer time on mobile.

### 3. No client-side caching
Every tap on "check" makes a full round-trip. Street-sweeping schedules change at most once a year. Returning to the same address always fetches the same data.

### 4. All geometry sent per request
Street segments that are not near the car are still included in the figure and serialised. The viewport is typically much smaller than the full region dataset.

---

## Options

### A — UptimeRobot warm-up ping (recommended, do now)

Ping `GET /health` every 5 minutes using the free UptimeRobot monitor. This keeps the Render container warm for any user who visits within the past 5 minutes.

- **Result**: eliminates the cold-start delay for anyone using the app regularly.
- **Trade-off**: the container will still cold-start if no one (including the monitor) has hit it in 15+ minutes. This is acceptable for a prototype.
- **Cost**: free (UptimeRobot free plan allows monitors at 5-minute intervals).
- **Setup**: create a new monitor at uptimerobot.com pointing to `https://<render-url>/health`.

---

### B — localStorage response cache (recommended, do now)

Cache the schedule portion of the `/check` response in `localStorage`, keyed by `(region, lat rounded to 3 decimal places, lon rounded to 3 decimal places)`. TTL: 24 hours.

On a cache hit, show the schedule immediately and re-fetch the Plotly figure in the background.

- **Result**: repeat visits to the same address are instant.
- **Trade-off**: schedule data can be up to 24 hours stale, which is fine for street-sweeping. The full figure is always re-fetched, so the map stays current.
- **Cost**: free. Uses browser storage only.
- **Storage**: store only `{ urgency, schedule_even, schedule_odd, car_side, address, ts }` — not the figure. The figure JSON alone is 3-8 MB, which would exhaust the 5 MB `localStorage` limit.
- **Implementation notes**:
  - Key: `bb_check_${region}_${lat.toFixed(3)}_${lon.toFixed(3)}`
  - Evict entries older than 24 h on startup.

---

### C — Server-side spatial pre-filter

Before building the Plotly figure, clip the GeoDataFrame to a bounding box around the car (e.g., 0.02 degrees ~ 2 km radius). Only the visible streets are serialised and returned.

- **Result**: reduces response size and server CPU. SF would drop from 3-8 MB to ~0.5-1 MB for a typical viewport.
- **Trade-off**: none significant. Streets just outside the initial viewport won't appear until the user pans — acceptable since the map auto-zooms to the car.
- **Cost**: free. Change is entirely server-side.
- **Implementation**: pass a bbox to `maps.py` and filter the GeoDataFrame before rendering.

---

### D — Pre-generated static GeoJSON served from CDN

Export one GeoJSON file per city at deploy time (via `scripts/export_geojson.py`). Host on GitHub Pages or Supabase Storage (both free). The frontend fetches and renders the geometry client-side; the backend only returns the schedule text and urgency, not the figure.

- **Result**: geometry loads from CDN in under 1 s after first visit (browser-cached). `/check` becomes a small JSON call (~1 KB).
- **Trade-off**:
  - Files are large uncompressed (SF ~17 MB, Oakland ~17 MB, Chicago ~5 MB). Gzip brings them to ~3-5 MB each.
  - Urgency color-coding must be computed client-side (JS port of the Python analysis logic).
  - Data updates require re-export and re-deploy.
  - Plotly is replaced by a lighter mapping library (Mapbox GL or Leaflet).
- **Cost**: free. GitHub Pages is free; Supabase Storage has a 1 GB free limit.

---

### E — PMTiles vector tiles (best long-term option)

Convert shapefiles to PMTiles format (a single-file tile archive). Host on Cloudflare R2 (free 10 GB) or GitHub Releases. Use `protomaps-leaflet` or `mapbox-gl` to render tiles client-side; tiles load incrementally as the user pans and zooms.

- **Result**: near-instant map rendering at any zoom level; scales to any dataset size.
- **Trade-off**:
  - Requires `tippecanoe` CLI to generate tiles (one-time or on data update, ~2 min per city).
  - Urgency color-coding via Mapbox style expressions (more complex than Python logic).
  - Plotly replaced entirely by a tile-based renderer.
  - More pipeline to maintain.
- **Cost**: free. Cloudflare R2 free tier is 10 GB storage, 10 million read operations/month.

---

## Recommended order

| Priority | Option | Effort | Impact |
|---|---|---|---|
| 1 | UptimeRobot ping (A) | 5 min | Eliminates cold-start for regular users |
| 2 | localStorage cache (B) | 2 h | Instant repeat loads |
| 3 | Spatial pre-filter (C) | 2-3 h | Cuts response size 5-10x |
| 4 | Static GeoJSON on CDN (D) | 1-2 days | Eliminates map from API response |
| 5 | PMTiles (E) | 3-5 days | Best user experience at scale |

Options A, B, and C are the short-term improvements — all free, all straightforward. D and E require reworking the map rendering and are better suited once the prototype is more stable.

The Render free tier spin-down after 15 minutes is a known limitation that will remain until the service is upgraded to a paid plan. The UptimeRobot ping mitigates it but does not eliminate it completely.
