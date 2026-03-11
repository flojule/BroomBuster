import gps, notification
import calendar, re, datetime

# Street-type suffixes to strip before name comparison so "CHESTNUT ST" matches
# a segment stored as "CHESTNUT" (or vice-versa).
_STREET_SUFFIXES = re.compile(
    r"\b(ST|AVE|BLVD|DR|RD|CT|PL|LN|WAY|TER|TERR|CIR|HWY|PKWY|EXPY|"
    r"STREET|AVENUE|BOULEVARD|DRIVE|ROAD|COURT|PLACE|LANE|CIRCLE|HIGHWAY)\b\.?$",
    re.IGNORECASE,
)

def _norm_name(name: str) -> str:
    """Strip trailing street-type suffix and whitespace for comparison."""
    return _STREET_SUFFIXES.sub("", name).strip().upper()


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

def check_street_sweeping(myCar, myCity):

    myCity = myCity.to_crs("EPSG:3857")

    # Use cached street info if get_info() was already called; otherwise fetch now
    if getattr(myCar, "street_name", None) and getattr(myCar, "streets", None):
        myStreetName = myCar.street_name
        myNumber     = myCar.street_number
        myStreets    = [item[0] for item in myCar.streets]
    else:
        myStreetName, myNumber = gps.get_street_info(myCar)
        myStreets_ = gps.get_nearby_streets(myCar)
        myStreets  = [item[0] for item in myStreets_]

    schedule_even = set()
    schedule_odd  = set()

    def _collect(street_section):
        """Add both side schedules from a matching street section."""
        e = get_schedule(street_section, 0)  # even
        o = get_schedule(street_section, 1)  # odd
        if e:
            schedule_even.add(e)
        if o:
            schedule_odd.add(o)

    # City key for the car's location (used to restrict no-range fallback)
    car_city = getattr(myCar, "_city", None)

    def _name_matches(sec_name: str, target: str) -> bool:
        """True when the segment name and target refer to the same street."""
        return _norm_name(sec_name) == _norm_name(target)

    if myStreets and myStreetName == myStreets[0]:
        for _, street_section in myCity.iterrows():
            if not _is_str(street_section.get("STREET_NAME")):
                continue
            sec_name = street_section["STREET_NAME"]
            if not _name_matches(sec_name, myStreetName):
                continue
            # If the segment belongs to a different city than the car, skip it
            # unless we have address ranges to confirm a match.
            seg_city = street_section.get("_city")
            l_f = _safe_int(street_section.get("L_F_ADD"))
            l_t = _safe_int(street_section.get("L_T_ADD"))
            r_f = _safe_int(street_section.get("R_F_ADD"))
            r_t = _safe_int(street_section.get("R_T_ADD"))
            if l_f is not None and l_t is not None and r_f is not None and r_t is not None:
                if myNumber and (l_f <= myNumber <= l_t or r_f <= myNumber <= r_t):
                    _collect(street_section)
            else:
                # No address ranges — only use if city matches (or unknown)
                if car_city is None or seg_city is None or seg_city == car_city:
                    _collect(street_section)

    elif myStreets and len(myStreets) > 1 and myStreetName == myStreets[1]:
        myActualStreet = myStreets[0]
        for _, street_section in myCity.iterrows():
            if not _is_str(street_section.get("STREET_NAME")):
                continue
            if _name_matches(street_section["STREET_NAME"], myActualStreet):
                _collect(street_section)

    else:
        pass  # no segment match; zone fallback below covers area-based data

    # Zone/polygon fallback — for area-based datasets like Chicago ward sections.
    # If no schedule was found above, test whether the car sits inside a zone polygon.
    if not schedule_even and not schedule_odd:
        from shapely.geometry import Point, Polygon, MultiPolygon
        if any(
            isinstance(g, (Polygon, MultiPolygon))
            for g in myCity.geometry
            if g is not None
        ):
            import pyproj as _pyproj
            _xfm = _pyproj.Transformer.from_crs(
                "EPSG:4326", "EPSG:3857", always_xy=True
            )
            car_x, car_y = _xfm.transform(myCar.lon, myCar.lat)
            car_pt = Point(car_x, car_y)
            for _, row in myCity.iterrows():
                g = row.geometry
                if g is not None and not g.is_empty and g.contains(car_pt):
                    _collect(row)

    # Car side is determined by address parity
    if myNumber and myNumber % 2 == 0:
        schedule = list(schedule_even)
    else:
        schedule = list(schedule_odd)

    schedule_even = list(schedule_even)
    schedule_odd  = list(schedule_odd)

    car_side = "even" if (myNumber and myNumber % 2 == 0) else "odd"
    message = notification.compose_message(schedule_even, schedule_odd, car_side)

    return schedule, schedule_even, schedule_odd, message

def check_day_street_sweeping(schedule):
    myDay = datetime.date.today()
    myTomorrow = myDay + datetime.timedelta(days=1)
    schedule_ymd = []

    for day in schedule:
        schedule_ymd.extend(parse_sweeping_code(day[0]))

    if myDay in schedule_ymd:
        return True
    elif myTomorrow in schedule_ymd:
        return True
    else:
        print('No sweeping today or tomorrow\n')
        return False
            
            
def _is_str(v):
    """True only for non-empty strings (filters NaN, None, floats)."""
    return isinstance(v, str) and v.strip() != ""


def _safe_int(v):
    """Parse a value as int, returning None on failure (handles NaN)."""
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def get_schedule(street_section, myNumber):
    if myNumber % 2 == 0:
        code = street_section.get("DAY_EVEN")
        if _is_str(code):
            return (
                code,
                street_section.get("DESC_EVEN") or "",
                street_section.get("TIME_EVEN") or "",
            )
    else:
        code = street_section.get("DAY_ODD")
        if _is_str(code):
            return (
                code,
                street_section.get("DESC_ODD") or "",
                street_section.get("TIME_ODD") or "",
            )
        

def get_all_dates_for_weekday(weekday, year, month):
    """Get all dates in a month for a specific weekday."""
    _, days_in_month = calendar.monthrange(year, month)
    return [
        datetime.date(year, month, day)
        for day in range(1, days_in_month + 1)
        if datetime.date(year, month, day).weekday() == weekday
    ]

def get_weekdays_by_ordinal(weekday, ordinals, year, month):
    """Get list of dates for a specific weekday and ordinal(s)."""
    dates = get_all_dates_for_weekday(weekday, year, month)
    return [dates[i - 1] for i in ordinals if i <= len(dates)]

def parse_sweeping_code(code):
    today = datetime.date.today()
    year, month = today.year, today.month

    # Chicago-style explicit date list: "DATES:2026-04-01,2026-04-02,..."
    if code.upper().startswith("DATES:"):
        return [
            datetime.date.fromisoformat(ds.strip())
            for ds in code[6:].split(",")
            if ds.strip()
        ]

    code = code.upper()

    # Handle compound sweep codes
    if code in compound_map:
        return [d for wd in compound_map[code] for d in get_all_dates_for_weekday(wd, year, month)]

    # Handle every <day> (e.g., 'ME' = every Mon, 'TE' = every Tues)
    if code.endswith('E'):
        day_code = code[:-1]
        wd = weekday_map.get(day_code)
        if wd is not None:
            return get_all_dates_for_weekday(wd, year, month)

    # Try matching ordinal part
    for suffix, ordinal_list in ordinals.items():
        if code.endswith(suffix):
            day_code = code[:len(code) - len(suffix)]
            wd = weekday_map.get(day_code)
            if wd is not None:
                return get_weekdays_by_ordinal(wd, ordinal_list, year, month)

    # 'E' = every day
    if code == 'E':
        _, days_in_month = calendar.monthrange(year, month)
        return [datetime.date(year, month, d) for d in range(1, days_in_month + 1)]

    return []  # Unknown code
