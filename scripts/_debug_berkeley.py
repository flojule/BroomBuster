import sys, re, datetime
sys.path.insert(0, "src")
import car, data_loader, analysis, notification

myCity = data_loader.load_city_data("berkeley")

lat, lon = 37.86607, -122.28332
myCar = car.Car(lat=lat, lon=lon)
myCar.set_location(lat, lon)
myCar.get_info()
print("street_name  :", myCar.street_name)
print("street_number:", myCar.street_number)
print()

schedule, schedule_even, schedule_odd, message = analysis.check_street_sweeping(myCar, myCity)
print("schedule_even:", schedule_even)
print("schedule_odd :", schedule_odd)
print("message:\n", message)
print()

if schedule_even:
    code = schedule_even[0][0]
    if code.upper().startswith("DATES:"):
        all_dates = [datetime.date.fromisoformat(d) for d in code[6:].split(",")]
        today = datetime.date.today()
        print(f"Today: {today}  |  in schedule: {today in all_dates}")
        print(f"Tomorrow: {today + datetime.timedelta(days=1)}  |  in schedule: {(today + datetime.timedelta(days=1)) in all_dates}")
        print("All sweeping dates:", all_dates)

