# Street Sweeping

An interactive tool that shows where your car is parked on a live map and tells you whether street sweeping applies to that block — today, tomorrow, or not at all.  Supports multiple cities across the Bay Area and Chicago.

![Map screenshot — Oakland](images/oakland.png)

## Features

- **Two location modes** — pull live GPS from a [Traccar](https://www.traccar.org/) client (phone app or OBD dongle) _or_ set coordinates manually.
- **Interactive map** — an OpenStreetMap-backed Plotly figure colour-codes every street segment by sweeping urgency:
  - 🔴 **Red** — sweeping today
  - 🟠 **Orange** — sweeping tomorrow
  - 🔵 **Blue** — no sweeping soon
- **Car marker** — coloured dot matches the urgency of the block where your car is parked; hover to see the address.
- **Summary panel** (bottom-left) — shows the address, date, and next sweeping times for both address sides, with an arrow marking your side.
- **Overview inset** (lower-right) — zoomed-out mini-map so you always know where the main view is.
- **Multi-city / regional loading** — load an entire region (e.g. all Bay Area cities) in one run, or switch to single-city mode for faster iteration.
- **Email notification** — opt-in alert when sweeping is same-day or next-day.
- **Credentials via environment variables** — no passwords in source code.

## Supported cities

| City | Data source | Status |
|---|---|---|
| Oakland, CA | Bundled shapefile | ✅ Ready |
| San Francisco, CA | Auto-download from DataSF on first run | ✅ Ready |
| Chicago (Edgewater), IL | Zones auto-download; schedule fetched live from Socrata API | ✅ Ready |
| Berkeley, CA | Manual download from Berkeley Open Data | ⚠️ Data file required |
| Alameda, CA | No public GIS layer — requires manual digitisation | ⚠️ Data file required |

## Project layout

```
street_sweeping/
├── data/
│   └── oakland/
│       └── StreetSweeping.shp      # Bundled Oakland shapefile
├── images/
│   └── oakland.png                 # Screenshot used in this README
├── src/
│   ├── main.py          # Entry point — configure and run here
│   ├── cities.py        # City and region configuration (URLs, paths, schemas)
│   ├── data_loader.py   # Downloads, caches, and normalises city data
│   ├── car.py           # Car object: location, geocoding, GeoDataFrame helpers
│   ├── gps.py           # Traccar API + Nominatim reverse-geocoding + Overpass streets
│   ├── maps.py          # Interactive Plotly map (car marker + colour-coded streets)
│   ├── analysis.py      # Sweeping schedule parsing and day-matching logic
│   ├── notification.py  # Email alert via Gmail SMTP
│   └── config.py        # Credentials loaded from environment variables / .env
├── .env.example         # Template — copy to .env and fill in your values
└── README.md
```

## Setup

### 1. Install dependencies

```bash
pip install geopandas shapely pyproj plotly geopy requests python-dotenv
```

### 2. Configure credentials

Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
```

```dotenv
# Traccar server (only needed when USE_LIVE_GPS = True)
TRACCAR_URL=https://demo4.traccar.org
TRACCAR_USERNAME=you@example.com
TRACCAR_PASSWORD=your_traccar_password

# Gmail notification (only needed when SEND_NOTIFICATION = True)
# Use a Gmail App Password, not your account password
EMAIL_SENDER=you@gmail.com
EMAIL_RECEIVER=you@gmail.com
EMAIL_PASSWORD=your_gmail_app_password
```

Alternatively, export the variables in your shell before running.

### 3. Run

```bash
cd src
python main.py
```

The script opens a browser tab with the interactive map and prints the schedule to the console.

## Configuration flags (top of `main.py`)

| Flag | Default | Description |
|---|---|---|
| `REGION` | `"bay_area"` | Region to load when `SINGLE_CITY_MODE = False` — see `cities.py` for available regions |
| `SINGLE_CITY_MODE` | `True` | `True` → load only `CITY` (faster); `False` → load the full region |
| `CITY` | `"oakland"` | City key used when `SINGLE_CITY_MODE = True` |
| `USE_LIVE_GPS` | `False` | `True` → fetch from Traccar; `False` → use `MANUAL_LAT/LON` |
| `MANUAL_LAT` / `MANUAL_LON` | `None` | Fixed fallback used when `USE_LIVE_GPS = False` (defaults to city/region centre) |
| `PLOT` | `True` | Open the interactive map after each check |
| `SEND_NOTIFICATION` | `False` | Email alert when sweeping is today or tomorrow |
| `CHECK_INTERVAL_H` | `1` | Hours between checks (remove the `break` in main loop to run continuously) |

## Adding a city

### Bay Area

**Berkeley** — download the GeoJSON from [Berkeley Open Data](https://data.cityofberkeley.info/Transportation/Street-Sweeping/s7pi-7kgv) (Export → GeoJSON) and save to `data/berkeley/StreetSweeping.geojson`.  Then update `_normalise_berkeley` in `data_loader.py` once you've inspected the column names:
```python
import geopandas
print(geopandas.read_file("data/berkeley/StreetSweeping.geojson").columns.tolist())
```

**Alameda** — no public GIS layer is currently known; the city publishes sweeping schedules as PDF maps only.  If a GeoJSON or Shapefile becomes available, save it to `data/alameda/StreetSweeping.geojson` and update `_normalise_alameda` in `data_loader.py`.

### Chicago

Chicago's data is split across two annual datasets on the [Chicago Data Portal](https://data.cityofchicago.org):

| Dataset | Purpose | How used |
|---|---|---|
| **Street Sweeping Zones** (`52z7-wvp2`) | Ward-section polygon boundaries | Downloaded once, cached to `data/chicago/StreetSweepingZones.geojson` |
| **Street Sweeping Schedule** (`a2xx-z2ja`) | Sweeping dates per ward-section | Fetched live from the Socrata JSON API every run |

Both dataset IDs and the schedule API URL are configured in `cities.py → chicago_edgewater`.  Chicago publishes new datasets each year (typically March/April) — update those IDs when that happens, then delete the cached zones file to force a re-download.

## Traccar GPS setup

1. Install the **Traccar Client** app on your phone ([Android](https://play.google.com/store/apps/details?id=org.traccar.client) / [iOS](https://apps.apple.com/app/traccar-client/id843156974)).
2. Point it at your Traccar server URL and create a device.
3. Set `USE_LIVE_GPS = True` and ensure `TRACCAR_URL`, `TRACCAR_USERNAME`, and `TRACCAR_PASSWORD` are in `.env`.

## Data schema

All city datasets are normalised to a common column schema before analysis and display:

| Column | Description |
|---|---|
| `STREET_NAME` | Street name, upper-case |
| `DAY_EVEN` / `DAY_ODD` | Sweeping day code for even/odd address side (Oakland-style: `ME`, `M13`, `DATES:…`) |
| `DESC_EVEN` / `DESC_ODD` | Human-readable schedule description |
| `TIME_EVEN` / `TIME_ODD` | Sweeping time window (e.g. `8AM–10AM`) |
| `L_F_ADD` … `R_T_ADD` | Address-range bounds for each side of the block |

## Security

- All credentials (Traccar, email) are read from environment variables — never committed to version control.
- Add `.env` to your `.gitignore` to prevent accidental exposure.
