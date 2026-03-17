import os
import sys
import threading
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

import geopandas
import pandas as pd
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# Allow importing from src/ and api/ regardless of working directory
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)                             # api/ — for deps.py
sys.path.insert(0, os.path.join(_HERE, "..", "src"))  # src/ — for all existing modules

import analysis
import car as car_module
import data_loader
import maps
from cities import CITIES, REGIONS
from deps import verify_jwt

# ---------------------------------------------------------------------------
# Optional Supabase client (for user prefs persistence)
# ---------------------------------------------------------------------------

_supabase = None
_SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
_SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")

if _SUPABASE_URL and _SUPABASE_SERVICE_KEY:
    try:
        from supabase import create_client
        _supabase = create_client(_SUPABASE_URL, _SUPABASE_SERVICE_KEY)
    except Exception as _e:
        print(f"Warning: could not initialise Supabase client — {_e}")

# ---------------------------------------------------------------------------
# City-level GDF cache — loaded in parallel background threads at startup.
# Each city gets its own threading.Event; a /check request waits only for
# the city (or cities) that overlap the user's location.
# ---------------------------------------------------------------------------

_city_gdfs: dict = {}       # city_key → GeoDataFrame (EPSG:4326)
_city_gdfs_3857: dict = {}  # city_key → GeoDataFrame (EPSG:3857)
_city_events: dict = {}     # city_key → threading.Event (set when done)
_region_combined: dict = {} # region_key → (frozenset(loaded_keys), gdf_4326, gdf_3857)


def _load_city_bg(city_key: str) -> None:
    """Load one city in a background thread and signal completion."""
    try:
        gdf = data_loader.load_city_data(city_key)
        gdf = gdf.copy()
        gdf["_city"] = city_key
        _city_gdfs[city_key] = gdf.to_crs("EPSG:4326")
        _city_gdfs_3857[city_key] = gdf.to_crs("EPSG:3857")
    except Exception as exc:
        print(f"  WARNING: could not load '{city_key}': {exc}", flush=True)
    finally:
        _city_events[city_key].set()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Kick off all city loads in parallel — server is immediately ready.
    for rv in REGIONS.values():
        for ck in rv["cities"]:
            _city_events[ck] = threading.Event()
            threading.Thread(target=_load_city_bg, args=(ck,), daemon=True).start()
    yield


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(title="BroomBuster API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _in_city_bbox(lat: float, lon: float, city_key: str) -> bool:
    bbox = CITIES[city_key].get("bbox")
    if not bbox:
        return False
    lat_min, lon_min, lat_max, lon_max = bbox
    return lat_min <= lat <= lat_max and lon_min <= lon <= lon_max


def _priority_cities(lat: float, lon: float, region_key: str) -> list:
    """Cities whose bbox contains (lat, lon) first; rest after."""
    city_keys = REGIONS[region_key]["cities"]
    priority = [ck for ck in city_keys if _in_city_bbox(lat, lon, ck)]
    rest     = [ck for ck in city_keys if ck not in priority]
    return priority + rest


def _get_region_gdfs(lat: float, lon: float, region_key: str):
    """
    Wait for the priority city (the one whose bbox contains lat/lon) to load,
    then return combined GDFs from all cities that are already in cache.
    The combined GDF is cached until the set of loaded cities changes, so the
    analysis.py name-index cache (keyed by id(gdf)) is reused across requests.
    """
    ordered = _priority_cities(lat, lon, region_key)

    # Wait for at least the first priority city (up to 120 s).
    for ck in ordered:
        ev = _city_events.get(ck)
        if ev:
            ev.wait(timeout=120)
        if ck in _city_gdfs:
            break  # have data for the user's city; good enough to proceed

    loaded = frozenset(ck for ck in REGIONS[region_key]["cities"] if ck in _city_gdfs)
    if not loaded:
        return None, None

    # Return cached combined GDF if the set of loaded cities hasn't changed.
    cached = _region_combined.get(region_key)
    if cached and cached[0] == loaded:
        return cached[1], cached[2]

    gdfs_4326 = [_city_gdfs[ck] for ck in REGIONS[region_key]["cities"] if ck in _city_gdfs]
    gdfs_3857 = [_city_gdfs_3857[ck] for ck in REGIONS[region_key]["cities"] if ck in _city_gdfs]

    c4 = geopandas.GeoDataFrame(pd.concat(gdfs_4326, ignore_index=True), crs="EPSG:4326")
    c3 = geopandas.GeoDataFrame(pd.concat(gdfs_3857, ignore_index=True), crs="EPSG:3857")
    _region_combined[region_key] = (loaded, c4, c3)
    return c4, c3


def _nearest_city_key(lat: float, lon: float, region_key: str) -> str:
    city_keys = REGIONS[region_key]["cities"]
    best, best_d = city_keys[0], float("inf")
    for ck in city_keys:
        c = CITIES[ck]["center"]
        d = (c["lat"] - lat) ** 2 + (c["lon"] - lon) ** 2
        if d < best_d:
            best, best_d = ck, d
    return best


def _auto_region(lat: float, lon: float) -> str:
    """Pick the region whose center is closest to (lat, lon)."""
    best, best_d = "bay_area", float("inf")
    for rk, rv in REGIONS.items():
        c = rv["center"]
        d = (c["lat"] - lat) ** 2 + (c["lon"] - lon) ** 2
        if d < best_d:
            best, best_d = rk, d
    return best


# ---------------------------------------------------------------------------
# Routes — public
# ---------------------------------------------------------------------------


@app.get("/health")
def health():
    loaded  = [ck for ck, ev in _city_events.items() if ev.is_set() and ck in _city_gdfs]
    loading = [ck for ck, ev in _city_events.items() if not ev.is_set()]
    failed  = [ck for ck, ev in _city_events.items() if ev.is_set() and ck not in _city_gdfs]
    return {"status": "ok", "loaded": loaded, "loading": loading, "failed": failed}


@app.get("/cities")
def cities():
    return {
        "regions": {
            k: {"name": v["name"], "cities": v["cities"], "center": v["center"]}
            for k, v in REGIONS.items()
        },
        "cities": {
            k: {"name": v["name"], "center": v["center"]}
            for k, v in CITIES.items()
        },
    }


# ---------------------------------------------------------------------------
# Routes — authenticated
# ---------------------------------------------------------------------------


class CheckRequest(BaseModel):
    lat: float
    lon: float
    region: Optional[str] = None


@app.post("/check")
def check(req: CheckRequest, user_id: str = Depends(verify_jwt)):
    region    = req.region if req.region in REGIONS else _auto_region(req.lat, req.lon)
    local_now = datetime.now(ZoneInfo(REGIONS[region].get("tz", "UTC")))

    myCity_4326, myCity_3857 = _get_region_gdfs(req.lat, req.lon, region)
    if myCity_4326 is None:
        raise HTTPException(
            status_code=503,
            detail=f"No data available for region '{region}' yet — try again shortly.",
        )

    myCar = car_module.Car(lat=req.lat, lon=req.lon)
    myCar._city = _nearest_city_key(req.lat, req.lon, region)
    myCar.get_info()

    schedule, schedule_even, schedule_odd, message = analysis.check_street_sweeping(
        myCar, myCity_3857
    )
    urgency = analysis.check_day_street_sweeping(schedule, local_now=local_now)

    number = getattr(myCar, "street_number", None)
    car_side = "even" if (number and number % 2 == 0) else "odd"
    address = (
        f"{number or ''} {myCar.street_name or ''}".strip()
        or f"{req.lat:.4f}, {req.lon:.4f}"
    )

    figure_dict = maps.plot_map_dict(
        myCar, myCity_4326,
        schedule_even=schedule_even,
        schedule_odd=schedule_odd,
        message=message,
        local_now=local_now,
    )

    return {
        "message": message,
        "urgency": urgency,
        "schedule_even": schedule_even,
        "schedule_odd": schedule_odd,
        "car_side": car_side,
        "address": address,
        "figure": figure_dict,
    }


class PrefsRequest(BaseModel):
    home_lat: Optional[float] = None
    home_lon: Optional[float] = None
    preferred_region: Optional[str] = "bay_area"
    notify_email: Optional[bool] = False
    cars: Optional[list] = []


_PREFS_DEFAULT = {
    "home_lat": None, "home_lon": None,
    "preferred_region": "bay_area", "notify_email": False, "cars": [],
}


@app.get("/prefs")
def get_prefs(user_id: str = Depends(verify_jwt)):
    if _supabase is None:
        return _PREFS_DEFAULT
    result = _supabase.table("user_prefs").select("*").eq("user_id", user_id).execute()
    rows = result.data
    if not rows:
        return _PREFS_DEFAULT
    row = rows[0]
    return {
        "home_lat": row.get("home_lat"),
        "home_lon": row.get("home_lon"),
        "preferred_region": row.get("preferred_region", "bay_area"),
        "notify_email": row.get("notify_email", False),
        "cars": row.get("cars") or [],
    }


@app.post("/prefs")
def save_prefs(req: PrefsRequest, user_id: str = Depends(verify_jwt)):
    if _supabase is None:
        return {"saved": True}  # no-op when no DB configured
    _supabase.table("user_prefs").upsert({
        "user_id": user_id,
        "home_lat": req.home_lat,
        "home_lon": req.home_lon,
        "preferred_region": req.preferred_region,
        "notify_email": req.notify_email,
        "cars": req.cars,
    }).execute()
    return {"saved": True}


# ---------------------------------------------------------------------------
# Static frontend (mounted last so API routes take priority)
# ---------------------------------------------------------------------------

_frontend_dir = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.isdir(_frontend_dir):
    app.mount("/", StaticFiles(directory=_frontend_dir, html=True), name="frontend")
