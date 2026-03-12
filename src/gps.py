import numpy as np
import pyproj
import requests
from geopy.geocoders import Nominatim

import config

_TRANSFORMER = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
_GEOLOCATOR = Nominatim(user_agent="broombuster")


def get_GPS_traccar():
    """Fetch the latest position for the first registered Traccar device."""
    if not config.TRACCAR_URL:
        raise ValueError(
            "TRACCAR_URL not set. "
            "Export TRACCAR_URL or add it to .env."
        )
    if not config.TRACCAR_USERNAME or not config.TRACCAR_PASSWORD:
        raise ValueError(
            "Traccar credentials not set. "
            "Export TRACCAR_USERNAME and TRACCAR_PASSWORD environment variables "
            "or add them to a .env file."
        )

    session = requests.Session()

    resp = session.post(
        f"{config.TRACCAR_URL}/api/session",
        data={"email": config.TRACCAR_USERNAME, "password": config.TRACCAR_PASSWORD},
    )
    resp.raise_for_status()

    devices = session.get(f"{config.TRACCAR_URL}/api/devices").json()
    if not devices:
        raise RuntimeError("No devices found on Traccar account.")
    device_id = devices[0]["id"]

    positions = session.get(f"{config.TRACCAR_URL}/api/positions").json()
    position = next((p for p in positions if p["deviceId"] == device_id), None)
    if position is None:
        raise RuntimeError(f"No position available for device {device_id}.")

    return position["latitude"], position["longitude"], position["fixTime"]


def get_street_info(myCar): # gets street from nearest address, problem at corners

    location = _GEOLOCATOR.reverse((myCar.lat, myCar.lon), exactly_one=True)
    if location is None:
        return None, None
    myStreetName = location.raw['address'].get('road')  # type: ignore[union-attr]
    raw_num = location.raw['address'].get('house_number')  # type: ignore[union-attr]
    myNumber = None
    if raw_num:
        # house_number can be a range like "6321-6323"; take the first number
        try:
            myNumber = int(raw_num.split("-")[0].strip())
        except (ValueError, TypeError):
            pass

    return myStreetName, myNumber

def get_nearby_streets(myCar):

    point = _TRANSFORMER.transform(myCar.lon, myCar.lat)
    radius = 100

    # Overpass QL query to get nearby roads (within 100 meters)
    query = f"""
    [out:json];
    way(around:{radius},{myCar.lat},{myCar.lon})["highway"];
    out geom;
    """

    url = "https://overpass-api.de/api/interpreter"
    response = requests.post(url, data={'data': query})
    try:
        data = response.json()
    except Exception:
        data = {"elements": []}

    myStreets = []
    for road in data['elements']:
        name = road['tags'].get('name')
        polyline = road.get('geometry')
        if name and polyline:
            distance = get_distance_point_polyline(point, polyline)
            myStreets.append((name, distance))

    # Sort by distance
    myStreets.sort(key=lambda x: x[1])

    return myStreets


def get_distance_point_line(point, point1, point2):  # points are projected (EPSG:3857)

    d12 = np.sqrt((point2[1] - point1[1])**2 + (point2[0] - point1[0])**2)
    area = np.abs(
        (point2[1] - point1[1]) * point[0]
        - (point2[0] - point1[0]) * point[1]
        + point2[0] * point1[1]
        - point2[1] * point1[0]
    )
    distance = float(area / d12)

    return distance

def get_distance_point_polyline(point, polyline):
    if len(polyline) < 2:
        return float('inf')

    # Batch-transform all vertices in one pyproj call instead of one per vertex.
    lons = np.array([v['lon'] for v in polyline])
    lats = np.array([v['lat'] for v in polyline])
    xs, ys = _TRANSFORMER.transform(lons, lats)
    pts = np.column_stack([xs, ys])  # shape (N, 2)

    # Vectorised point-to-segment distances across all segments at once.
    p1s = pts[:-1]  # segment starts, shape (N-1, 2)
    p2s = pts[1:]   # segment ends,   shape (N-1, 2)
    d12 = np.hypot(p2s[:, 1] - p1s[:, 1], p2s[:, 0] - p1s[:, 0])
    areas = np.abs(
        (p2s[:, 1] - p1s[:, 1]) * point[0]
        - (p2s[:, 0] - p1s[:, 0]) * point[1]
        + p2s[:, 0] * p1s[:, 1]
        - p2s[:, 1] * p1s[:, 0]
    )
    with np.errstate(divide="ignore", invalid="ignore"):
        dists = np.where(d12 > 0, areas / d12, np.inf)
    return float(np.min(dists))


