# street_sweeping

An interactive tool for Oakland residents that shows where your car is parked on a live map and tells you whether street sweeping applies to that block — today, tomorrow, or not at all.

## Features

- **Two location modes** — pull live GPS from a [Traccar](https://www.traccar.org/) client (phone app or OBD dongle) _or_ set coordinates manually.
- **Interactive map** — an OpenStreetMap-backed Plotly figure colour-codes every street segment by sweeping urgency:
  - 🔴 **Red** — sweeping today
  - 🟠 **Orange** — sweeping tomorrow
  - 🔵 **Blue** — no sweeping soon
  - A red dot marks the car's position; hover over it to see the full schedule for that block.
  - A summary panel (bottom-left) shows the address and next sweeping times.
- **Email notification** — opt-in alert sent when sweeping is same-day or next-day.
- **Credentials via environment variables** — no passwords stored in source code.

## Project layout

```
street_sweeping/
├── data/
│   └── oakland/
│       └── StreetSweeping.shp   # Oakland street-sweeping shapefile
├── src/
│   ├── main.py          # Entry point — configure and run here
│   ├── car.py           # Car object: location, geocoding, GeoDataFrame helpers
│   ├── gps.py           # Traccar API + Nominatim reverse-geocoding + Overpass nearby streets
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
| `USE_LIVE_GPS` | `False` | `True` → fetch from Traccar; `False` → use `MANUAL_LAT/LON` |
| `MANUAL_LAT` / `MANUAL_LON` | Oakland coords | Fixed location used when `USE_LIVE_GPS = False` |
| `PLOT` | `True` | Open the interactive map after each check |
| `SEND_NOTIFICATION` | `False` | Email alert when sweeping is today or tomorrow |
| `CHECK_INTERVAL_H` | `1` | Hours between checks (remove the `break` in main loop to run continuously) |

## Traccar GPS setup

1. Install the **Traccar Client** app on your phone ([Android](https://play.google.com/store/apps/details?id=org.traccar.client) / [iOS](https://apps.apple.com/app/traccar-client/id843156974)).
2. Point it at your Traccar server URL and create a device.
3. Set `USE_LIVE_GPS = True` and ensure `TRACCAR_URL`, `TRACCAR_USERNAME`, and `TRACCAR_PASSWORD` are in `.env`.

## Data

The Oakland street-sweeping shapefile is sourced from the [Oakland Open Data portal](https://data.oaklandca.gov/). Key columns used:

| Column | Description |
|---|---|
| `NAME` / `TYPE` | Street name and type (Ave, St, Blvd, …) |
| `DAY_EVEN` / `DAY_ODD` | Sweeping day code for even/odd address side |
| `DescDayEve` / `DescDayOdd` | Human-readable day description |
| `DescTimeEv` / `DescTimeOd` | Sweeping time window |
| `L_F_ADD` … `R_T_ADD` | Address range for each side of the block |

## Security

- All credentials (Traccar, email) are read from environment variables — never committed to version control.
- Add `.env` to your `.gitignore` to prevent accidental exposure.
