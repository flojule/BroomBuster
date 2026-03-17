# BroomBuster

Know before the sweeper comes. An interactive map that shows your parked car and tells you whether street sweeping applies to that block — today, tomorrow, or not at all. Works as a **mobile PWA** (add to iPhone/Android home screen) and as a Python CLI.

**Bay Area**

![Map screenshot — Bay Area](images/bay_area.png)

**Chicago, IL**

![Map screenshot — Chicago](images/chicago.png)

## Features

- **Multi-car tracking** — save multiple cars, each with its own color, schedule, and address.
- **Tap-to-place** — tap anywhere on the map to pin a car's location; or type an address to geocode it.
- **GPS** — one tap to move a car to your phone's current GPS position.
- **Urgency color coding** — streets and banners color-coded by sweeping urgency:
  - 🔴 **Red** — sweeping today
  - 🟠 **Orange** — sweeping tomorrow
  - 🔵 **Blue** — no sweeping soon
- **Live status banner** — top bar names which specific car needs to move, if any.
- **PWA** — installable on iPhone/Android via "Add to Home Screen"; works offline for shell assets.
- **Multi-city / multi-region** — Bay Area (Oakland, SF, Berkeley, Alameda) and Chicago.
- **Python CLI** — the original command-line tool still works independently.

## Supported cities

| City | Data source | Status |
|---|---|---|
| Oakland, CA | Bundled shapefile | ✅ Ready |
| San Francisco, CA | Auto-download from DataSF on first run | ✅ Ready |
| Chicago, IL | Auto-download from Chicago Data Portal | ✅ Ready |
| Berkeley, CA | PDF schedules parsed by build script | ✅ Ready |
| Alameda, CA | PDF schedule parsed by build script | ✅ Ready |

## Project layout

```
BroomBuster/
├── data/
│   └── oakland/
│       └── StreetSweeping.shp      # Bundled Oakland shapefile
├── images/
│   ├── bay_area.png                # Screenshots used in this README
│   └── chicago.png
├── src/
│   ├── main.py          # CLI entry point
│   ├── cities.py        # City and region configuration (URLs, paths, schemas)
│   ├── data_loader.py   # Downloads, caches, and normalises city data
│   ├── car.py           # Car object: location, geocoding, GeoDataFrame helpers
│   ├── gps.py           # Traccar API + Nominatim reverse-geocoding
│   ├── maps.py          # Plotly map: colour-coded streets + car markers
│   ├── analysis.py      # Sweeping schedule parsing and day-matching logic
│   ├── notification.py  # Email alert via Gmail SMTP
│   └── config.py        # Credentials from environment variables / .env
├── api/
│   ├── api.py           # FastAPI app — all HTTP routes
│   ├── deps.py          # JWT verification (Supabase JWKS)
│   └── requirements.txt # API + frontend dependencies
├── frontend/
│   ├── index.html       # Single-page PWA (vanilla JS + Plotly.js)
│   ├── manifest.json    # PWA manifest
│   ├── sw.js            # Service worker (app shell cache)
│   └── icon-192.png     # App icon
├── Dockerfile           # Container for Render.com deployment
├── render.yaml          # Render service config
├── .env.example         # Template — copy to .env and fill in values
└── README.md
```

---

## Web app — development

### 1. Install API dependencies

```bash
pip install -r api/requirements.txt
```

### 2. Set environment variables

Copy the example and fill in your values:

```bash
cp .env.example .env
```

Minimum required for the web app:

```dotenv
# Supabase project (https://supabase.com — free tier)
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_KEY=your-service-role-key   # Settings → API → service_role
SUPABASE_JWT_SECRET=your-jwt-secret          # Settings → API → JWT Secret

# Optional — email alerts
EMAIL_SENDER=you@gmail.com
EMAIL_RECEIVER=you@gmail.com
EMAIL_PASSWORD=your-gmail-app-password
```

### 3. Run the dev server

```bash
uvicorn api.api:app --reload --port 8000
```

Open [http://localhost:8000](http://localhost:8000) in your browser. The frontend is served from `frontend/` by FastAPI's `StaticFiles` mount.

> **No Supabase?** The server starts and the map works without Supabase configured. Auth will fail (no JWT to verify), so `/check` and `/prefs` will return 401. Set `SUPABASE_URL` and keys to enable login.

### 4. Supabase setup (one-time)

Create a free project at [supabase.com](https://supabase.com), then run in the SQL editor:

```sql
CREATE TABLE user_prefs (
    user_id          UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    home_lat         DOUBLE PRECISION,
    home_lon         DOUBLE PRECISION,
    preferred_region TEXT DEFAULT 'bay_area',
    notify_email     BOOLEAN DEFAULT FALSE,
    cars             JSONB DEFAULT '[]',
    updated_at       TIMESTAMPTZ DEFAULT now()
);
ALTER TABLE user_prefs ENABLE ROW LEVEL SECURITY;
CREATE POLICY "own row" ON user_prefs
    USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);
```

Copy `SUPABASE_URL` and keys from **Project Settings → API**.

---

## Web app — deployment (Render.com)

### 1. Push to GitHub

The repo must be on GitHub (or GitLab) for Render to auto-deploy.

### 2. Create a Render Web Service

1. [render.com](https://render.com) → **New → Web Service** → connect your repo.
2. **Build command:** leave blank (no build step needed).
3. **Start command:**
   ```
   uvicorn api.api:app --host 0.0.0.0 --port $PORT
   ```
4. **Instance type:** Free (512 MB RAM, sufficient for two loaded GDFs).

### 3. Set environment variables on Render

Under **Environment → Environment Variables**, add:

| Key | Value |
|---|---|
| `SUPABASE_URL` | your Supabase project URL |
| `SUPABASE_SERVICE_KEY` | service role key |
| `SUPABASE_JWT_SECRET` | JWT secret |

### 4. Prevent spin-down (free tier)

Render free services sleep after 15 minutes of inactivity. City GDFs reload on wake (up to ~60 s for SF/Chicago). To keep it warm:

- [UptimeRobot](https://uptimerobot.com) (free) → add HTTP monitor → `https://your-app.onrender.com/health` → every 5 minutes.

### 5. Custom domain (optional)

Render Settings → Custom Domains → add your domain. HTTPS is automatic.

---

## Python CLI

### Setup

```bash
pip install -r requirements.txt   # or api/requirements.txt — same packages
cp .env.example .env              # optional, for GPS / email
```

### Run

```bash
cd src
python main.py
```

Opens a browser tab with the interactive map and prints the schedule to the console. No Supabase or internet account required.

### Configuration flags (top of `src/main.py`)

| Flag | Default | Description |
|---|---|---|
| `REGION` | `"bay_area"` | Region to load when `SINGLE_CITY_MODE = False` |
| `SINGLE_CITY_MODE` | `True` | `True` → load only `CITY` (faster); `False` → full region |
| `CITY` | `"oakland"` | City key when `SINGLE_CITY_MODE = True` |
| `USE_LIVE_GPS` | `False` | `True` → fetch from Traccar; `False` → use `MANUAL_LAT/LON` |
| `MANUAL_LAT` / `MANUAL_LON` | `None` | Fixed fallback (defaults to city/region centre) |
| `PLOT` | `True` | Open the interactive map after each check |
| `SEND_NOTIFICATION` | `False` | Email alert when sweeping is today or tomorrow |
| `CHECK_INTERVAL_H` | `1` | Hours between checks when running in a loop |

### Optional credentials (`.env`)

Only needed for live GPS or email alerts:

```dotenv
# Live GPS via Traccar
TRACCAR_URL=https://demo4.traccar.org
TRACCAR_USERNAME=you@example.com
TRACCAR_PASSWORD=your_traccar_password

# Email alerts (Gmail App Password)
EMAIL_SENDER=you@gmail.com
EMAIL_RECEIVER=you@gmail.com
EMAIL_PASSWORD=your_gmail_app_password
```

---

## Adding a city

### Bay Area

**Berkeley** — schedule published as a PDF at [berkeleyca.gov](https://berkeleyca.gov/city-services/streets-sidewalks-sewers-and-utilities/street-sweeping). Save PDFs to `data/berkeley/`, then run `scripts/build_berkeley_geojson.py`.

**Alameda** — schedule at [alamedaca.gov](https://www.alamedaca.gov/Residents/Transportation-and-Streets/Street-Sweeping-Schedule). Save as `data/alameda/street-sweeping-schedule.pdf`, then run `scripts/build_alameda_geojson.py`.

### Chicago

Data auto-downloads from the [Chicago Data Portal](https://data.cityofchicago.org) (Socrata dataset `utb4-q645`). Chicago publishes a new dataset each year (typically March/April) — update the ID in `cities.py → chicago_all` and delete the cached file to force a re-download.

---

## Data schema

All city datasets are normalised to a common column schema:

| Column | Description |
|---|---|
| `STREET_NAME` | Street name, upper-case |
| `DAY_EVEN` / `DAY_ODD` | Sweeping day code for even/odd address side |
| `DESC_EVEN` / `DESC_ODD` | Human-readable schedule description |
| `TIME_EVEN` / `TIME_ODD` | Sweeping time window (e.g. `8AM–10AM`) |
| `L_F_ADD` … `R_T_ADD` | Address-range bounds for each side of the block |

---

## Security

- All credentials are read from environment variables — never committed to source control.
- JWT verification uses Supabase's JWKS endpoint; tokens are validated on every authenticated request.
- No location history is stored; `/check` results are ephemeral (not persisted to the database).
