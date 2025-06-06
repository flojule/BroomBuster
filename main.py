import car, gps, maps, notification, analysis

import time, geopandas
from datetime import datetime

# run twice a day, 8am and 6pm. Filter out day when running 6pm or later
# store all data in car class

if __name__ == "__main__":

    live_GPS = True
    plot = False

    myCar = car.Car()

    file_path = "oakland/StreetSweeping.shp"
    myCity = geopandas.read_file(file_path)
    
    interval = 1  # hours

    try:
        while True:

            if live_GPS:
                myCar.get_GPS()
                myCar.__str__()
            else:
                lat, lon = 37.821326, -122.280705
                myCar.set_location(lon, lat)

            if plot:
                maps.plot_map(myCar, myCity)

            schedule, message = analysis.check_street_sweeping(myCar, myCity)

            if analysis.check_day_street_sweeping(schedule):
                notification.send_email(message)
            
            # print('round over')
            break
            time.sleep(interval*3600)

    except KeyboardInterrupt:
        print(" Exiting...")

