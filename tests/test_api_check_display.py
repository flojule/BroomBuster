"""
API-level tests to ensure `/check` returns an `address` that matches the
nearest segment's persisted `STREET_DISPLAY` (prevents mismatch between
car card and map hover labels).

These tests run the FastAPI app with `DEV_MODE=1` so authentication is
skipped.  Since M2 removed the Nominatim call from the critical path, the
address is derived purely from the resolved segment — no network mocks needed.
"""
import os
os.environ.setdefault("DEV_MODE", "1")

import pytest
from fastapi.testclient import TestClient

import data_loader
import normalize


def _nearest_row_for_point(gdf_3857, lat, lon):
    from pyproj import Transformer
    from shapely.geometry import Point
    t = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
    x, y = t.transform(lon, lat)
    pt = Point(x, y)
    best_row, best_d = None, float("inf")
    for i, row in gdf_3857.iterrows():
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue
        d = pt.distance(geom)
        if d < best_d:
            best_d = d
            best_row = row
    return best_row


def test_api_check_address_matches_street_display():
    # Choose a point known to be in the bay area dataset
    lat, lon = 37.821326, -122.280705  # Chestnut St, Oakland (used in other tests)

    # Preload region data for deterministic access
    gdf_3857 = data_loader.load_region_data("bay_area").to_crs("EPSG:3857")
    nearest = _nearest_row_for_point(gdf_3857, lat, lon)
    if nearest is None:
        pytest.skip("No segment found to test against")

    row_display = (nearest.get("STREET_DISPLAY") or nearest.get("STREET_NAME") or "").strip()
    if not row_display:
        pytest.skip("Nearest segment has no display/name")

    import api.api as api_mod

    # Use context manager so FastAPI lifespan startup runs (loads cities).
    with TestClient(api_mod.app) as client:
        payload = {"lat": lat, "lon": lon, "region": "bay_area"}
        resp = client.post("/check", json=payload)
    assert resp.status_code == 200, resp.text
    data = resp.json()

    addr = data.get("address") or ""
    # Address is now derived directly from the resolved segment — compare
    # canonical keys to tolerate minor punctuation/casing differences.
    assert normalize.street_name(addr) == normalize.street_name(row_display), (
        f"API address {addr!r} does not match STREET_DISPLAY {row_display!r}"
    )
