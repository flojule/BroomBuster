import gps, notification
import calendar, re, datetime


# handle these times 
# {'3:00AM-6:00AM', '12:00AM-3:00AM', '12:30PM-3:30PM', '2:00AM-3:00AM', '6:00AM-8:00AM', 'NA', '9:00AM-12:00PM'}


# Map sweeping letter codes to weekday integers
weekday_map = {
    'M': 0, 'T': 1, 'W': 2, 'TH': 3, 'F': 4, 'S': 5, 'SU': 6
}

# Handle combinations like 'MWF', 'TTHS', etc.
compound_map = {
    'MWF': [0, 2, 4],
    'TTH': [1, 3],
    'TTHS': [1, 3, 5],
    'MF': [0, 1, 2, 3, 4],
    'E': list(range(7)),  # Every day
}

# Handle codes like M13, T2, F24
ordinals = {
    '1': [1],
    '2': [2],
    '3': [3],
    '4': [4],
    '13': [1, 3],
    '24': [2, 4],
}

myDay = datetime.date.today()
# myDay = datetime.date(2025, 5, 13)
myTomorrow = myDay + datetime.timedelta(days=1)
year = myDay.year
month = myDay.month

def check_street_sweeping(myCar, myCity):

    myCity = myCity.to_crs("EPSG:3857")

    myStreetName, myNumber = gps.get_street_info(myCar)
    myStreets_ = gps.get_nearby_streets(myCar)
    myStreets = [item[0] for item in myStreets_]

    schedule = set()
    if myStreetName == myStreets[0]:
        for i, street_section in myCity.iterrows():
            if street_section['NAME'] and street_section['TYPE']:
                street_section_name = street_section['NAME'].lower() + ' ' + street_section['TYPE'].lower()
                if myStreetName.lower().startswith(street_section_name):
                    if street_section['L_F_ADD'] and street_section['L_T_ADD'] and street_section['R_F_ADD'] and street_section['R_T_ADD']:
                        if myNumber:
                            L_F_ADD = int(street_section['L_F_ADD'])
                            L_T_ADD = int(street_section['L_T_ADD'])
                            R_F_ADD = int(street_section['R_F_ADD'])
                            R_T_ADD = int(street_section['R_T_ADD'])
                            if (myNumber > L_F_ADD and myNumber < L_T_ADD) or (myNumber > R_F_ADD and myNumber < R_T_ADD):
                                schedule.add(get_schedule(street_section, myNumber))
                        else:
                            for i in range(0,2):
                                schedule.add(get_schedule(street_section, i))
                            
                    else:

                        for i in range(0,2):
                            schedule.add(get_schedule(street_section, i))
    
    elif myStreetName == myStreets[1]:
        myActualStreet = myStreets[0]
        for i, street_section in myCity.iterrows():
            if street_section['NAME'] and street_section['TYPE']:
                street_section_name = street_section['NAME'].lower() + ' ' + street_section['TYPE'].lower()
                if myActualStreet.lower().startswith(street_section_name):
                    for i in range(0,2):
                        schedule.add(get_schedule(street_section, i))

    else:
        print(myStreetName, myStreets)

    schedule = list(schedule)

    message = notification.compose_message(myStreetName, myNumber, myStreets, schedule)

    return schedule, message

def check_day_street_sweeping(schedule):

    schedule_ymd = []

    for day in schedule:
        schedule_ymd.extend(parse_sweeping_code(day[0]))

    if myDay in schedule_ymd:
        message = 'There is street sweeping today!\n'
        return True
    elif myTomorrow in schedule_ymd:
        message = 'There is street sweeping tomorrow!\n'
        return True
    else:
        # print(myDay, myTomorrow, schedule)
        print('No sweeping today or tomorrow\n')
        return False
            
            
def get_schedule(street_section, myNumber):
    if myNumber %2 == 0:
        if street_section['DAY_EVEN']:
            schedule_days = street_section['DAY_EVEN']
            schedule_desc = street_section['DescDayEve']
            schedule_time = street_section['DescTimeEv']
            return schedule_days, schedule_desc, schedule_time
    else:
        if street_section['DAY_ODD']:
            schedule_days = street_section['DAY_ODD']
            schedule_desc = street_section['DescDayOdd']
            schedule_time = street_section['DescTimeOd']
            return schedule_days, schedule_desc, schedule_time
        

def get_all_dates_for_weekday(weekday):
    """Get all dates in a month for a specific weekday."""
    _, days_in_month = calendar.monthrange(year, month)
    return [
        datetime.date(year, month, day)
        for day in range(1, days_in_month + 1)
        if datetime.date(year, month, day).weekday() == weekday
    ]

def get_weekdays_by_ordinal(weekday, ordinals):
    """Get list of dates for a specific weekday and ordinal(s)."""
    dates = get_all_dates_for_weekday(weekday)
    return [dates[i - 1] for i in ordinals if i <= len(dates)]

def parse_sweeping_code(code):
    code = code.upper()

    # Handle compound sweep codes
    if code in compound_map:
        return [d for wd in compound_map[code] for d in get_all_dates_for_weekday(wd)]

    # Handle every <day> (e.g., 'ME' = every Mon, 'TE' = every Tues)
    if code.endswith('E'):
        day_code = code[:-1]
        wd = weekday_map.get(day_code)
        if wd is not None:
            return get_all_dates_for_weekday(wd)

    # Try matching ordinal part
    for suffix, ordinal_list in ordinals.items():
        if code.endswith(suffix):
            day_code = code[:len(code) - len(suffix)]
            wd = weekday_map.get(day_code)
            if wd is not None:
                return get_weekdays_by_ordinal(wd, ordinal_list)

    # 'E' = every day
    if code == 'E':
        _, days_in_month = calendar.monthrange(year, month)
        return [datetime.date(year, month, d) for d in range(1, days_in_month + 1)]

    return []  # Unknown code


    # {('MWF', 'Every Mon, Wed, Fri'), 
    #  ('N-S', 'No Sweeping (Within City Of Oakland Limit)'), 
    #  ('F2', '2nd Fri'), ('THFE', 'Every Thurs and Fri'), 
    #  ('TTH', 'Every Tues and Thurs'), 
    #  ('N', 'No Sweeping (Exempt)'), 
    #  ('O', 'There is no this side of the street'), 
    #  ('M24', '2nd and 4th Mon'), 
    #  ('TTHE', 'Every Tues and Thurs'), 
    #  ('N-E', 'No Even Addresses'), 
    #  ('F13', '1st and 3rd Fri'), 
    #  ('T2', '2nd Tues'), 
    #  ('TFE', 'Every Tues and Fri'), 
    #  ('W2', '2nd Wed'), 
    #  ('T24', '2nd and 4th Tues'), 
    #  ('missing', None), 
    #  ('F1', '1st Fri'), 
    #  ('E', 'Everyday'), 
    #  ('NS-UC', 'No Sweeping (Uncontrol Condition)'), 
    #  ('NS-A', 'No Sweeping(Alleyways)'), 
    #  ('T13', '1st and 3rd Tues'), 
    #  ('DM', 'It is shown in the different map.'), 
    #  ('S', 'Every Sat'), ('THE', 'Every Thurs'), 
    #  ('MTHE', 'Every Mon and Thurs'), 
    #  ('FE', 'Every Fri'), 
    #  ('N-O', 'No Odd Addresses'), 
    #  ('TTHS', 'Every Tues, Thurs, Sat'), 
    #  ('TH13', '1st and 3rd Thurs'), 
    #  ('MFE', 'Every Mon and Fri'), 
    #  ('M2', '2nd Mon'), 
    #  ('NS', 'No Signage'), 
    #  ('M13', '1st and 3rd Mon'), 
    #  ('MF', 'Every Mon to Fri'), 
    #  ('SU', 'Every Sun'), 
    #  ('NS', 'No Sweeping (Within City Of Oakland Limit)'), 
    #  ('TH2', '2nd Thurs'), 
    #  ('TE', 'Every Tues'), 
    #  ('ME', 'Every Mon'), 
    #  ('W13', '1st and 3rd Wed'), 
    #  ('MS', 'Major street uses 2 lines, not center line.'), 
    #  ('N-S', 'No Signage'), 
    #  ('NS-H', 'No Sweeping (HYW)'), 
    #  ('NS-O', 'No Sweeping (Outside Of The City Limit)')}
