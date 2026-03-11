import requests
import pyproj
from geopy.geocoders import Nominatim
import numpy as np
import config

_TRANSFORMER = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
_GEOLOCATOR = Nominatim(user_agent="broombuster")


def get_GPS_traccar():
    """Fetch the latest position for the first registered Traccar device."""
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
    myStreetName = location.raw['address'].get('road')
    raw_num = location.raw['address'].get('house_number')
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


def get_distance_point_line(point, point1, point2): # input gps coord

    d12 = np.sqrt((point2[1] - point1[1])**2 + (point2[0] - point1[0])**2)
    area = np.abs((point2[1]-point1[1])*point[0] - (point2[0]-point1[0])*point[1] + point2[0]*point1[1] - point2[1]*point1[0])
    distance = float(area / d12)

    return distance

def get_distance_point_polyline(point, polyline):
    distance = float('inf')

    for i in range(len(polyline) - 1):
        point1 = _TRANSFORMER.transform(polyline[i]['lon'], polyline[i]['lat'])
        point2 = _TRANSFORMER.transform(polyline[i + 1]['lon'], polyline[i + 1]['lat'])
        distance_temp = get_distance_point_line(point, point1, point2)
        distance = min(distance, distance_temp)

    return distance


