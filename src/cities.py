"""
City configurations for street-sweeping data.

Each entry defines:
  name            Display name shown in the UI
  center          Default map center (lat/lon)
  manual_default  Fallback coordinates used when USE_LIVE_GPS = False
  local_path      Where the data file is cached on disk (relative to repo root)
  url             Download URL; None = file must be placed manually
  schema          Normalization schema key (handled by data_loader.py)
  bbox            Optional [lat_min, lon_min, lat_max, lon_max] clip after load

REGIONS groups cities geographically so the app can load several at once.
"""

CITIES = {
    # ------------------------------------------------------------------
    # Bay Area
    # ------------------------------------------------------------------
    "oakland": {
        "name": "Oakland, CA",
        "center": {"lat": 37.8044, "lon": -122.2712},
        "manual_default": {"lat": 37.821326, "lon": -122.280705},
        "local_path": "data/oakland/StreetSweeping.shp",
        # Bundled in the repo; no automatic download.
        "url": None,
        "schema": "oakland",
    },

    "san_francisco": {
        "name": "San Francisco, CA",
        "center": {"lat": 37.7749, "lon": -122.4194},
        "manual_default": {"lat": 37.7749, "lon": -122.4194},
        "local_path": "data/san_francisco/StreetSweeping.geojson",
        # DataSF – Street Sweeping Schedule (dataset yhqp-riqs)
        # The geospatial export endpoint returns 400; use the Socrata GeoJSON
        # resource API instead (supports up to ~200 k rows with $limit).
        "url": (
            "https://data.sfgov.org/resource/yhqp-riqs.geojson"
            "?$limit=200000"
        ),
        "schema": "sf",
    },

    "berkeley": {
        "name": "Berkeley, CA",
        "center": {"lat": 37.8716, "lon": -122.2727},
        "manual_default": {"lat": 37.8716, "lon": -122.2727},
        "local_path": "data/berkeley/StreetSweeping.geojson",
        # Berkeley Open Data – Street Sweeping Routes
        # Portal: https://data.cityofberkeley.info/Transportation/Street-Sweeping/s7pi-7kgv
        # Download: Export → GeoJSON, save to data/berkeley/StreetSweeping.geojson
        "url": None,
        "schema": "berkeley",
    },

    "alameda": {
        "name": "Alameda, CA",
        "center": {"lat": 37.7652, "lon": -122.2416},
        "manual_default": {"lat": 37.7652, "lon": -122.2416},
        "local_path": "data/alameda/StreetSweeping.geojson",
        # Alameda publishes sweeping schedules as PDFs; no GIS layer is known.
        # If a GeoJSON or Shapefile becomes available, set url here.
        # Otherwise digitise the PDF schedule into data/alameda/StreetSweeping.geojson
        # using the generic schema (see data_loader._normalise_generic for expected columns).
        "url": None,
        "schema": "generic",
    },

    # ------------------------------------------------------------------
    # Chicago
    # ------------------------------------------------------------------
    "chicago_all": {
        "name": "Chicago, IL",
        "center": {"lat": 41.8781, "lon": -87.6298},
        "manual_default": {"lat": 41.9951, "lon": -87.6593},
        "local_path": "data/chicago/StreetSweepingZones.geojson",
        # Chicago Data Portal – Street Sweeping Zones (tabular dataset utb4-q645).
        # Includes polygon geometry AND sweeping schedule as month columns
        # (april..november).  Update the dataset ID each year when Chicago
        # publishes new data (typically March/April).
        # Delete data/chicago/StreetSweepingZones.geojson to force a re-download.
        "url": (
            "https://data.cityofchicago.org/resource/utb4-q645.geojson"
            "?$limit=50000"
        ),
        "schema": "chicago",
        # Full Chicago city limits
        "bbox": [41.644, -87.848, 42.024, -87.524],
    },

}

# ---------------------------------------------------------------------------
# Regions – groups of cities loaded together when SINGLE_CITY_MODE = False
# ---------------------------------------------------------------------------

REGIONS = {
    "bay_area": {
        "name": "Bay Area",
        "cities": ["oakland", "san_francisco", "berkeley", "alameda"],
        # Wider center / zoom used for the overview inset only
        "center": {"lat": 37.820, "lon": -122.295},
        "manual_default": {"lat": 37.821326, "lon": -122.280705},
        "overview_zoom": 9,
    },
    "chicago": {
        "name": "Chicago",
        "cities": ["chicago_all"],
        "center": {"lat": 41.9100, "lon": -87.6700},
        "manual_default": {"lat": 41.996593, "lon": -87.665282},
        "overview_zoom": 10,
    },
}
