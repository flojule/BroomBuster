import requests, pyproj
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
import numpy as np

def get_GPS_traccar():
    # credentials and server
    TRACCAR_URL = "https://demo4.traccar.org"
    USERNAME = "florian.jule@gadz.org"
    PASSWORD = "knJNUIU676GFYVuhjbhjvgh667"

    session = requests.Session()

    # Authenticate
    resp = session.post(f"{TRACCAR_URL}/api/session", data={"email": USERNAME, "password": PASSWORD})
    resp.raise_for_status()

    # Get devices
    devices = session.get(f"{TRACCAR_URL}/api/devices").json()
    device_id = devices[0]['id']  # Use first device

    # Get position
    positions = session.get(f"{TRACCAR_URL}/api/positions").json()
    position = next((p for p in positions if p["deviceId"] == device_id), None)

    return position['latitude'], position['longitude'], position['fixTime']


def get_street_info(myCar): # gets street from nearest address, problem at corners

    # Initialize geocoder
    geolocator = Nominatim(user_agent="geoapi")

    # Get address
    location = geolocator.reverse((myCar.lat, myCar.lon), exactly_one=True)
    myStreetName = location.raw['address'].get('road')
    myNumber = int(location.raw['address'].get('house_number'))

    return myStreetName, myNumber

def get_nearby_streets(myCar):
    
    # Create transformer
    transformer = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)

    point = transformer.transform(myCar.lon, myCar.lat)
    radius = 100

    # Overpass QL query to get nearby roads (within 100 meters)
    query = f"""
    [out:json];
    way(around:{radius},{myCar.lat},{myCar.lon})["highway"];
    out geom;
    """

    url = "https://overpass-api.de/api/interpreter"
    response = requests.post(url, data={'data': query})
    data = response.json()

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
    # Create transformer
    transformer = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)

    for i in range(len(polyline) - 1):
        point1 = transformer.transform(polyline[i]['lon'], polyline[i]['lat'])
        point2 = transformer.transform(polyline[i + 1]['lon'], polyline[i + 1]['lat'])
        distance_temp = get_distance_point_line(point, point1, point2)
        distance = min(distance, distance_temp)

    return distance


