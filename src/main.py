import car, maps, notification, analysis, data_loader
from cities import CITIES, REGIONS

import time

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Regional mode: load all cities in a region together.
# Available regions: "bay_area", "chicago"  (see src/cities.py → REGIONS)
REGION = "chicago"

# Set SINGLE_CITY_MODE = True to load only the city named in CITY below.
# Useful while developing or when other cities' data files aren't available yet.
SINGLE_CITY_MODE = False

# City used when SINGLE_CITY_MODE = True.
# Available keys: "oakland", "san_francisco", "berkeley", "alameda", "chicago_edgewater"
CITY = "oakland"

# Set USE_LIVE_GPS = True to fetch the car's position from Traccar.
# Set USE_LIVE_GPS = False to use fixed manual coordinates defined below.
USE_LIVE_GPS = False

# Manual location override (uses region manual_default when None).
# Set to your car's position to override.
# bay_area example: 37.821326, -122.280705  (2931 Chestnut St, Oakland)
# chicago example:  41.9951,   -87.6593     (near 6321 N Glenwood Ave)
MANUAL_LAT = None
MANUAL_LON = None

PLOT              = True   # Open an interactive map in the browser
SEND_NOTIFICATION = False  # Send an email when sweeping is today or tomorrow
CHECK_INTERVAL_H  = 1     # Hours between checks when running continuously

# ---------------------------------------------------------------------------

if __name__ == "__main__":

    if SINGLE_CITY_MODE:
        city_cfg = CITIES[CITY]
        myCity   = data_loader.load_city_data(CITY)
        myCity["_city"] = CITY
        default_lat = city_cfg["manual_default"]["lat"]
        default_lon = city_cfg["manual_default"]["lon"]
    else:
        region_cfg  = REGIONS[REGION]
        myCity      = data_loader.load_region_data(REGION)
        _rdefault   = region_cfg.get("manual_default", region_cfg["center"])
        default_lat = _rdefault["lat"]
        default_lon = _rdefault["lon"]

    lat = MANUAL_LAT if MANUAL_LAT is not None else default_lat
    lon = MANUAL_LON if MANUAL_LON is not None else default_lon

    myCar = car.Car(lat=lat, lon=lon)

    # Pre-compute the city key closest to the car's starting position so that
    # analysis.py can filter cross-city name collisions.
    def _nearest_city(lat, lon):
        active = (
            [CITY] if SINGLE_CITY_MODE
            else REGIONS[REGION]["cities"]
        )
        best, best_d = active[0], float("inf")
        for ck in active:
            c = CITIES[ck]["center"]
            d = (c["lat"] - lat) ** 2 + (c["lon"] - lon) ** 2
            if d < best_d:
                best, best_d = ck, d
        return best

    try:
        while True:

            # 1. Update car location
            if USE_LIVE_GPS:
                print("Fetching GPS position from Traccar…")
                myCar.get_GPS()
            else:
                myCar.set_location(lat, lon)

            # 2. Tag the car with its nearest city key (used in analysis)
            myCar._city = _nearest_city(myCar.lat, myCar.lon)

            # 3. Reverse-geocode to get street name, number, and nearby streets
            myCar.get_info()
            print()
            print(myCar)

            # 4. Analyse street-sweeping schedule for the car's current block
            schedule, schedule_even, schedule_odd, message = analysis.check_street_sweeping(myCar, myCity)
            print(message)

            # 5. Show interactive map with car position and schedule info
            if PLOT:
                maps.plot_map(myCar, myCity, schedule_even=schedule_even,
                              schedule_odd=schedule_odd, message=message)

            # 6. Notify if sweeping is today or tomorrow
            if SEND_NOTIFICATION and analysis.check_day_street_sweeping(schedule):  # noqa: E501
                notification.send_email(message)

            break  # remove this line to run continuously on a timer
            time.sleep(CHECK_INTERVAL_H * 3600)

    except KeyboardInterrupt:
        print("\nExiting…")


