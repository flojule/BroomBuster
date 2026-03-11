"""
City configurations for street-sweeping data.

Each key maps to a dict with:
  name            Display name shown in the UI
  center          Default map center (lat/lon)
  manual_default  Fallback coordinates used when USE_LIVE_GPS = False
  local_path      Where the data file is cached on disk (relative to repo root)
  url             Download URL; None means the file must be present already
  schema          Normalization schema key (handled by data_loader.py)
  bbox            Optional [lat_min, lon_min, lat_max, lon_max] clip after load

Adding a new city:
  1. Obtain a GIS file (Shapefile or GeoJSON) with street segments and
     sweeping-schedule columns.
  2. Add an entry below.
  3. Implement a _normalise_<schema> function in data_loader.py that maps
     the city's columns to the standard schema (see data_loader.py header).
"""

CITIES = {
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
        # DataSF Socrata GeoJSON export (Street Sweeping Schedule, dataset yhqp-riqs)
        "url": (
            "https://data.sfgov.org/api/geospatial/yhqp-riqs"
            "?method=export&type=GeoJSON"
        ),
        "schema": "sf",
    },

    "chicago_edgewater": {
        "name": "Chicago – Edgewater, IL",
        "center": {"lat": 41.9952, "lon": -87.6597},
        "manual_default": {"lat": 41.9952, "lon": -87.6597},
        "local_path": "data/chicago/StreetSweeping.geojson",
        # Chicago does not publish a geometric sweeping-schedule layer with an
        # open download URL.  Download from the Chicago Data Portal and save to
        # data/chicago/StreetSweeping.geojson, then implement _normalise_chicago
        # in data_loader.py once you inspect the actual column names.
        # Portal: https://data.cityofchicago.org/browse?q=street+sweeping
        "url": None,
        "schema": "chicago",
        # Bounding box for the Edgewater neighbourhood only
        "bbox": [41.970, -87.675, 42.010, -87.640],
    },
}
