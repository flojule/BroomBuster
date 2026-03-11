import car, maps, notification, analysis, data_loader
from cities import CITIES

import time

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# City to analyse — see src/cities.py for available keys.
# "oakland" is bundled; "san_francisco" auto-downloads on first run.
CITY = "oakland"

# Set USE_LIVE_GPS = True to fetch the car's position from Traccar.
# Set USE_LIVE_GPS = False to use fixed manual coordinates defined below.
USE_LIVE_GPS = False

# Manual location override (defaults to the city's built-in example location).
MANUAL_LAT = None
MANUAL_LON = None

PLOT              = True   # Open an interactive map in the browser
SEND_NOTIFICATION = False  # Send an email when sweeping is today or tomorrow
CHECK_INTERVAL_H  = 1     # Hours between checks when running continuously

# ---------------------------------------------------------------------------

if __name__ == "__main__":

    city_cfg = CITIES[CITY]

    # Load (and normalise) city street-sweeping data
    myCity = data_loader.load_city_data(CITY)

    # Resolve manual location: explicit override > city default
    lat = MANUAL_LAT if MANUAL_LAT is not None else city_cfg["manual_default"]["lat"]
    lon = MANUAL_LON if MANUAL_LON is not None else city_cfg["manual_default"]["lon"]

    myCar = car.Car(lat=lat, lon=lon)

    try:
        while True:

            # 1. Update car location
            if USE_LIVE_GPS:
                print("Fetching GPS position from Traccar…")
                myCar.get_GPS()
            else:
                myCar.set_location(lat, lon)

            # 2. Reverse-geocode to get street name, number, and nearby streets
            myCar.get_info()
            print(myCar)

            # 3. Analyse street-sweeping schedule for the car's current block
            schedule, schedule_even, schedule_odd, message = analysis.check_street_sweeping(myCar, myCity)
            print(message)

            # 4. Show interactive map with car position and schedule info
            if PLOT:
                maps.plot_map(myCar, myCity, schedule_even=schedule_even,
                              schedule_odd=schedule_odd, message=message)

            # 5. Notify if sweeping is today or tomorrow
            if SEND_NOTIFICATION and analysis.check_day_street_sweeping(schedule):  # noqa: E501
                notification.send_email(message)

            break  # remove this line to run continuously on a timer
            time.sleep(CHECK_INTERVAL_H * 3600)

    except KeyboardInterrupt:
        print("\nExiting…")


