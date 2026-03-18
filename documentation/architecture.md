# BroomBuster — Architecture

## What it does

BroomBuster tells you whether a parked car is in the path of an upcoming street sweeper. Given a GPS coordinate (or a manually entered address), it finds the matching street segment in the city's sweeping schedule, determines whether sweeping is today or tomorrow, and renders a color-coded map.

It supports multiple cities — currently Oakland, San Francisco, Berkeley, Alameda (grouped as the Bay Area region), and Chicago — and lets a user track several cars at once, each with its own saved location.

---

## How it works

The core flow is:

1. The frontend sends a location (lat/lon) and a region name to the backend.
2. The backend loads the city's street-sweeping shapefile or GeoJSON into a GeoDataFrame (once at startup, cached in memory).
3. It finds the street segment nearest to the car by spatial join, reads the sweeping schedule for that block, and determines urgency relative to today's date.
4. It builds a Plotly figure (color-coded street segments: red = today, orange = tomorrow, blue = safe) and returns it alongside the schedule text as JSON.
5. The frontend renders the figure with Plotly.js and updates the status banner.

---

## Components

```
Browser (iPhone / desktop)
  └── index.html  (vanilla JS + Plotly.js + Supabase JS)
        |  Login / session management via Supabase Auth
        |  POST /check  {lat, lon, region}  +  Bearer JWT
        |  GET/POST /prefs  (saved cars and preferences)
        v
Render.com  (Docker container — FastAPI + Uvicorn)
  ├── api/api.py      HTTP routes; city GDF loading; car lookup; Plotly figure assembly
  ├── api/deps.py     JWT verification (ES256 via JWKS, or HS256 via secret)
  └── src/            All analysis, data loading, and mapping logic
        |  Supabase client (service key) used only for /prefs persistence
        v
Supabase
  ├── Auth            Issues and validates JWTs; handles sign-up, login, token refresh
  └── PostgreSQL      user_prefs table — one row per user (saved cars, preferred region)
```

---

## Source layout

```
BroomBuster/
├── src/
│   ├── analysis.py      Sweeping schedule parsing; day-matching; urgency logic
│   ├── car.py           Car object: spatial join to find street segment
│   ├── cities.py        City and region definitions (URLs, schemas, bboxes, timezones)
│   ├── config.py        Credentials from environment variables
│   ├── data_loader.py   Downloads, caches, and normalises city datasets
│   ├── gps.py           Traccar API + Nominatim reverse-geocoding (CLI only)
│   ├── maps.py          Plotly map builder; returns figure dict for the API
│   ├── notification.py  Email alert via Gmail SMTP (CLI only)
│   └── main.py          CLI entry point
│
├── api/
│   ├── api.py           FastAPI app: startup loading, all routes, static file mount
│   ├── deps.py          JWT verification
│   └── requirements.txt
│
├── frontend/
│   ├── index.html       Single-page PWA: login, multi-car UI, map render
│   ├── manifest.json    PWA manifest (installable on iPhone)
│   ├── sw.js            Service worker (app-shell caching)
│   └── icon-*.png/svg   App icons
│
├── data/
│   └── oakland/         Oakland shapefile (bundled in repo)
│       other cities are downloaded at first startup and cached locally
│
├── scripts/
│   ├── build_berkeley_geojson.py    Converts Berkeley PDF schedules to GeoJSON
│   └── build_alameda_geojson.py     Converts Alameda PDF schedules to GeoJSON
│
├── tests/               pytest suite covering analysis, data loading, pipeline
├── Dockerfile           Docker image for Render.com
└── render.yaml          Render service configuration
```

---

## Data pipeline

City data is loaded once per cold start:

- **Oakland**: shapefile bundled in the repo (`data/oakland/`).
- **San Francisco**: downloaded from DataSF at startup and cached on disk.
- **Berkeley** and **Alameda**: generated from city PDFs via scripts; the resulting GeoJSON files must be present at startup (they are checked in once generated).
- **Chicago**: downloaded from the Chicago Data Portal at startup and cached.

Each city's data is loaded in a background thread so the server is available immediately; the first `/check` request for a city waits only until that city's data is ready.

All datasets are normalised to a common schema:

| Column | Description |
|---|---|
| `STREET_NAME` | Street name, upper-case |
| `DAY_EVEN` / `DAY_ODD` | Sweeping day code for even/odd address side |
| `DESC_EVEN` / `DESC_ODD` | Human-readable schedule description |
| `TIME_EVEN` / `TIME_ODD` | Sweeping time window |
| `L_F_ADD` … `R_T_ADD` | Address-range bounds for each side of the block |

---

## Authentication

Supabase Auth issues JWTs on login. The frontend stores the session in `localStorage` and passes the token as `Authorization: Bearer <jwt>` on every API call. The backend verifies the token using the Supabase JWKS endpoint (ES256) or the JWT secret (HS256, legacy projects). No location data is stored server-side; `/prefs` stores only saved cars and the preferred region.

---

## External dependencies

| Service | What it provides | Free tier limits |
|---|---|---|
| Render.com | Hosts the Docker container (API + frontend) | Spins down after 15 min of inactivity; 512 MB RAM; shared CPU |
| Supabase | Authentication and PostgreSQL | 50,000 MAU; 500 MB database; unlimited API calls |

No other paid or external services are required in the default configuration. The Traccar GPS integration and email notifications are optional and used only by the CLI.
