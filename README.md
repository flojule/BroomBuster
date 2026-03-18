# BroomBuster

![GrimSweeper](frontend/grim_sweeper_rect.png)

Know before the grim sweeper comes. An interactive map that shows your parked car and tells you whether street sweeping applies to that block — today, tomorrow, or not at all.

**Bay Area**

![Map screenshot — Bay Area](images/bay_area.png)

**Chicago, IL**

![Map screenshot — Chicago](images/chicago.png)

---

## Features

- **Multi-car tracking** — save multiple cars, each with its own name, color, and location.
- **GPS** — one tap to move a car to your phone's current GPS position.
- **Manual placement** — tap anywhere on the map to place a car, or double-click a car card to type an address.
- **Urgency color coding** — streets and car cards color-coded by sweeping urgency:
  - Red — sweeping today
  - Orange — sweeping tomorrow
  - Blue — no sweeping soon
- **Live status banner** — top bar shows which cars need to move.
- **Multi-city / multi-region** — Bay Area (Oakland, SF, Berkeley, Alameda) and Chicago.
- **PWA** — installable on iPhone via "Add to Home Screen" in Safari.
- **Python CLI** — the original command-line tool still works independently.

---

## How to run

### Web app (local)

```bash
pip install -r requirements.txt -r api/requirements.txt
DEV_MODE=true uvicorn api.api:app --host 0.0.0.0 --port 8000
```

Open `http://localhost:8000` in a browser. `DEV_MODE=true` skips JWT verification so you can use the app without a Supabase project.

### Python CLI

```bash
pip install -r requirements.txt
cd src
python main.py
```

Opens a browser tab with the interactive map and prints the schedule to the console.

#### CLI configuration flags (top of `src/main.py`)

| Flag | Default | Description |
|---|---|---|
| `REGION` | `"bay_area"` | Region to load when `SINGLE_CITY_MODE = False` |
| `SINGLE_CITY_MODE` | `True` | `True` loads only `CITY` (faster); `False` loads the full region |
| `CITY` | `"oakland"` | City to load when `SINGLE_CITY_MODE = True` |
| `USE_LIVE_GPS` | `False` | `True` fetches location from Traccar |
| `MANUAL_LAT` / `MANUAL_LON` | `None` | Fixed fallback coordinates |
| `PLOT` | `True` | Open the map after each check |
| `SEND_NOTIFICATION` | `False` | Email alert when sweeping is today or tomorrow |
| `CHECK_INTERVAL_H` | `1` | Hours between checks when running in a loop |

---

## Deployment

The app is containerised and deployed to Render.com.

```
uvicorn api.api:app --host 0.0.0.0 --port $PORT
```

---

## Project layout

```
BroomBuster/
├── src/
│   ├── analysis.py      Schedule parsing; day-matching; urgency
│   ├── car.py           Car: spatial join to find street segment
│   ├── cities.py        City and region definitions (URLs, schemas, bboxes)
│   ├── config.py        Credentials from environment variables
│   ├── data_loader.py   Downloads, caches, and normalises city datasets
│   ├── gps.py           Traccar API + Nominatim reverse-geocoding (CLI)
│   ├── maps.py          Plotly map builder
│   ├── notification.py  Email alert via Gmail SMTP (CLI)
│   └── main.py          CLI entry point
├── api/
│   ├── api.py           FastAPI app: routes, startup loading, static mount
│   ├── deps.py          JWT verification (ES256 / HS256)
│   └── requirements.txt
├── frontend/
│   ├── index.html       Single-page PWA
│   ├── manifest.json    PWA manifest
│   ├── sw.js            Service worker
│   └── icon-*.png/svg   App icons
├── data/
│   └── oakland/         Oakland shapefile (bundled; other cities auto-downloaded)
├── scripts/
│   ├── build_berkeley_geojson.py
│   └── build_alameda_geojson.py
├── tests/
├── documentation/
│   ├── architecture.md            How the app works and its dependencies
│   ├── performance_plan.md        Current bottlenecks and free optimisation options
│   ├── user_database_options.md   Options for persisting user data
│   └── web_hosting_options.md     Options for hosting the backend
├── Dockerfile
├── render.yaml
└── .env.example
```
