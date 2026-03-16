# BroomBuster — Web App Architecture

This document describes the planned architecture for turning BroomBuster into a
mobile-friendly web app (PWA) with user login, accessible from an iPhone.

---

## Goal

- **Accessible on iPhone** via Safari (installable as a home-screen app)
- **Free hosting** — low refresh rate (5–60 min) is acceptable
- **Multi-user login** so the app can be shared
- **Minimal code changes** — reuse all existing Python logic

---

## Architecture Overview

```
iPhone / Safari
  └─ index.html (vanilla JS + Plotly.js CDN + Supabase JS CDN)
       │  navigator.geolocation → lat/lon
       │  POST /check {lat, lon, region} + Bearer JWT
       ▼
Render.com (free web service) — FastAPI
  ├─ api/api.py          ← thin wrapper around existing src/
  ├─ api/deps.py         ← JWT verification (~15 lines)
  └─ src/                ← UNCHANGED (analysis, maps, data_loader, car, gps, …)
       │  Loaded at startup; both region GDFs cached in memory
       ▼
Supabase (free tier)
  ├─ Auth  (email + password, magic link — issues JWTs)
  └─ PostgreSQL  (user_prefs — one row per user)
```

---

## Tech Stack

| Layer | Choice | Why |
|---|---|---|
| Frontend | Vanilla HTML + JS (`index.html`) | Single-screen app; no build step |
| Maps | Plotly.js CDN + `fig.to_dict()` from backend | Reuses 100 % of `maps.py` |
| Geolocation | `navigator.geolocation.getCurrentPosition()` | Works on iPhone Safari over HTTPS |
| Backend | FastAPI + Uvicorn | Wraps existing Python; minimal boilerplate |
| Auth | Supabase Auth | Free, JWT-based, handles registration/reset/refresh |
| Database | Supabase PostgreSQL | Free, managed; only one small table needed |
| Hosting | Render.com free tier | Fine for low-traffic, low-refresh-rate use |
| PWA | `manifest.json` + service worker | "Add to Home Screen" on iPhone |

---

## API Endpoints

```
GET  /health
     → {"status": "ok", "regions_loaded": [...]}
     No auth. Used as Render.com health probe and UptimeRobot ping target.

GET  /cities
     → {"regions": {...}, "cities": {...}}
     No auth. Populates the region/city picker on first page load.

POST /check
     Body:  {"lat": 37.82, "lon": -122.28, "region": "bay_area"}
     Auth:  Bearer JWT (Supabase)
     → {
         "message":       "► Even side: Mon 1st & 3rd — 8AM–10AM",
         "urgency":       "tomorrow",   // "today" | "tomorrow" | null
         "schedule_even": [...],
         "schedule_odd":  [...],
         "car_side":      "even",
         "address":       "2930 Chestnut St",
         "figure":        { ...Plotly figure dict... }
       }

GET  /prefs
     Auth: Bearer JWT
     → {"home_lat": ..., "home_lon": ..., "preferred_region": ..., "notify_email": ...}

POST /prefs
     Body:  {"home_lat": ..., "home_lon": ..., "preferred_region": ..., "notify_email": ...}
     Auth:  Bearer JWT
     → {"saved": true}
```

---

## Database Schema (Supabase)

```sql
CREATE TABLE user_prefs (
    user_id          UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    home_lat         DOUBLE PRECISION,
    home_lon         DOUBLE PRECISION,
    preferred_region TEXT DEFAULT 'bay_area',
    notify_email     BOOLEAN DEFAULT FALSE,
    updated_at       TIMESTAMPTZ DEFAULT now()
);

-- Each user can only see and modify their own row.
ALTER TABLE user_prefs ENABLE ROW LEVEL SECURITY;
CREATE POLICY "own row" ON user_prefs
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);
```

No location history is stored — check results are computed on demand.

---

## Auth Flow

1. User opens the app in Safari → Supabase JS SDK checks `localStorage` for a session.
2. No session → login screen (email + password form).
3. Login → Supabase Auth returns a signed JWT → stored in `localStorage`.
4. User taps "Check my location":
   - `navigator.geolocation.getCurrentPosition()` → lat/lon
   - `POST /check` with `Authorization: Bearer <jwt>`
5. FastAPI verifies the JWT (HS256, Supabase JWT secret) and runs the pipeline.
6. Response JSON → `Plotly.react()` renders the map; status banner updates.
7. JWT auto-refreshed silently by Supabase JS SDK (7-day sessions by default).

---

## Code Changes

### `src/maps.py` — extract figure builder (minimal refactor)

The body of `plot_map()` becomes a private `_build_map_figure()` that `return`s the
`go.Figure`. The public API gains one additional function:

```python
def plot_map(myCar, myCity, schedule_even=None, schedule_odd=None, message=None):
    """Unchanged behaviour — opens the map in a browser tab."""
    fig = _build_map_figure(myCar, myCity, schedule_even, schedule_odd, message)
    fig.show(config=dict(scrollZoom=True, displayModeBar=True, displaylogo=False))

def plot_map_dict(myCar, myCity, schedule_even=None, schedule_odd=None, message=None) -> dict:
    """Return the Plotly figure as a JSON-serialisable dict (for the web API)."""
    fig = _build_map_figure(myCar, myCity, schedule_even, schedule_odd, message)
    return fig.to_dict()
```

Everything else in `src/` is **unchanged**.

### New files

```
api/
  api.py           FastAPI app (~100 lines): startup GDF loading, routes, static mount
  deps.py          JWT verification via Supabase JWT secret (~15 lines)
  requirements.txt fastapi, uvicorn, python-jose[cryptography], supabase, httpx

frontend/
  index.html       Single-page app (~300 lines): login, geolocation, map render
  manifest.json    PWA manifest (name, icons, display: standalone)
  sw.js            Minimal service worker (cache-first shell for offline support)
  icon-192.png     App icon

Dockerfile         Multi-stage build for Render.com
render.yaml        Render service config (optional)
```

---

## Hosting Setup

| Service | Purpose | Cost |
|---|---|---|
| Render.com free web service | FastAPI backend + static frontend files | $0 |
| Supabase free project | Auth + PostgreSQL | $0 |
| UptimeRobot (free) | Ping `/health` every 10 min to prevent Render spin-down | $0 |

**Render.com specifics:**

- Start command: `uvicorn api.api:app --host 0.0.0.0 --port $PORT`
- Build command: `pip install -r requirements.txt && pip install -r api/requirements.txt`
- Environment variables: `SUPABASE_URL`, `SUPABASE_JWT_SECRET`, `SUPABASE_SERVICE_KEY`,
  plus existing `EMAIL_*` vars if notifications are enabled.
- Data files: Oakland shapefile committed to repo; SF and Chicago auto-downloaded at startup.
- RAM: both region GDFs ≈ 200 MB → fits in the 512 MB free-tier limit.

Render free services spin down after 15 min of inactivity. Cold start is ~20–40 s (geopandas
load). This is acceptable at a 5–60 min refresh interval.

---

## Repo Structure After Migration

```
BroomBuster/
├── src/                 ← UNCHANGED (all existing Python modules)
│   ├── analysis.py
│   ├── car.py
│   ├── cities.py
│   ├── config.py
│   ├── data_loader.py
│   ├── gps.py
│   ├── maps.py          ← add plot_map_dict() + extract _build_map_figure()
│   ├── notification.py
│   └── main.py          ← CLI entry point, still works as-is
│
├── api/                 ← NEW
│   ├── api.py
│   ├── deps.py
│   └── requirements.txt
│
├── frontend/            ← NEW
│   ├── index.html
│   ├── manifest.json
│   ├── sw.js
│   └── icon-192.png
│
├── data/                ← unchanged
├── scripts/             ← unchanged
├── tests/               ← unchanged
├── requirements.txt     ← unchanged (CLI deps)
├── Dockerfile           ← NEW
└── render.yaml          ← NEW
```

---

## Implementation Phases

| Phase | Work |
|---|---|
| 1 | `api/api.py` + `api/deps.py` + `plot_map_dict()` in `maps.py`; test locally |
| 2 | Supabase project + `user_prefs` table + `/prefs` endpoints |
| 3 | `frontend/index.html` (login, geolocation, fetch, Plotly render) |
| 4 | `Dockerfile` + Render.com deploy + UptimeRobot |
| 5 | `manifest.json`, `sw.js`, PWA install test on iPhone |

The CLI (`python src/main.py`) continues to work throughout all phases.

---

## Verification

1. `pytest tests/` — all existing tests pass (no changes to `src/`)
2. `curl -X POST http://localhost:8000/check -H "Authorization: Bearer <jwt>" \`
   `-d '{"lat":37.82,"lon":-122.28,"region":"bay_area"}'` — returns JSON with figure
3. Open `http://localhost:8000` on iPhone (via ngrok or local WiFi) — login works,
   geolocation prompt appears, map renders
4. "Add to Home Screen" on iPhone → app opens in standalone mode (no browser chrome)
5. Deploy to Render.com → repeat test on the real HTTPS URL
