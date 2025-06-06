import geopandas, shapely
import gps
from datetime import datetime 

class Car:
    def __init__(self, lat=37.84609980886195, lon=-122.25964399184454, time=datetime.now()):
        self.name = 'my car'
        self.set_location(lat, lon, time)
        self.get_info()

    def set_location(self, lat, lon, time=datetime.now()):
        self.lat = lat
        self.lon = lon
        self.time = time
        self.set_gdf()
        
    def get_GPS(self):
        lat, lon, time = gps.get_GPS_traccar()
        self.set_location(lat, lon, time)

    def get_info(self):
        self.street_name, self.street_number = gps.get_street_info(self)
        self.streets = gps.get_nearby_streets

    def set_gdf(self):
        # Create a GeoDataFrame for the car WGS84 = EPSG:4326 GPS, in degrees
        self.gdf = geopandas.GeoDataFrame(
            geometry=[shapely.Point(self.lon, self.lat)],
            crs="EPSG:4326"  # WGS84 (lat/lon)
        )
       
        # Convert to CRS 3857 Web Mercator, projected CRS in meters (32610 is UTM Zone 10N)
        self.gdf_meters = self.gdf.to_crs("EPSG:3857")
        self.x = self.gdf_meters.geometry.x[0]
        self.y = self.gdf_meters.geometry.y[0]

    def __str__(self):
        return f"Car Location: Latitude {self.lat}, Longitude {self.lon}, Time {self.time}"