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
    "chicago_edgewater": {
        "name": "Chicago – Edgewater, IL",
        "center": {"lat": 41.9952, "lon": -87.6597},
        # Near 6321 N Glenwood Ave, Chicago (Edgewater)
        "manual_default": {"lat": 41.9951, "lon": -87.6593},
        "local_path": "data/chicago/StreetSweepingZones.geojson",
        # Zone geometry \u2014 Chicago Data Portal \u201cStreet Sweeping Zones\u201d GeoJSON export.
        # Dataset ID 52z7-wvp2 is the 2025 edition.  Update the ID in both
        # 'url' and 'schedule_url' each year once the new datasets are
        # published at data.cityofchicago.org (search \"Street Sweeping\").
        # Delete data/chicago/StreetSweepingZones.geojson to force a re-download.
        # Dataset utb4-q645 is the 2025 zones — includes polygon geometry AND
        # the sweeping schedule embedded as month columns (april..november).
        # The map-view sibling 52z7-wvp2 has no geometry; always use the
        # tabular dataset.  Update both IDs each year once new data is published
        # (typically March/April) at data.cityofchicago.org.
        "url": (
            "https://data.cityofchicago.org/resource/utb4-q645.geojson"
            "?$limit=50000"
        ),
        "schema": "chicago",
        # Bounding box: Edgewater – Rogers Park area (Wards 40, 48, 49 + neighbours)
        "bbox": [41.960, -87.700, 42.020, -87.630],
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
        "cities": ["chicago_edgewater"],
        "center": {"lat": 41.997, "lon": -87.6650},
        "manual_default": {"lat": 41.997024, "lon": -87.6650475},
        "overview_zoom": 11,
    },
}
