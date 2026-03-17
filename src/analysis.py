import calendar
import datetime
import functools
import re

import pyproj as _pyproj
from shapely.geometry import MultiPolygon, Point, Polygon

import gps
import notification

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


# Matches time ranges like "8AM–10AM", "7:30AM-9AM", "8AM to 10AM"
_TIME_RANGE_RE = re.compile(
    r'(\d{1,2})(?::(\d{2}))?\s*(AM|PM)\s*(?:[-\u2013\u2014]|to)\s*'
    r'(\d{1,2})(?::(\d{2}))?\s*(AM|PM)',
    re.IGNORECASE,
)


def _parse_time_range(time_str: str):
    """Parse '8AM–10AM', '7:30AM-9AM', '8AM to 10AM' → (start, end) datetime.time or (None, None)."""
    if not isinstance(time_str, str) or not time_str.strip():
        return None, None
    m = _TIME_RANGE_RE.search(time_str)
    if not m:
        return None, None
    h1, m1, ap1, h2, m2, ap2 = m.groups()

    def _t(h, mn, ap):
        h, mn = int(h), int(mn or 0)
        ap = ap.upper()
        if ap == 'PM' and h != 12:
            h += 12
        elif ap == 'AM' and h == 12:
            h = 0
        return datetime.time(h, mn)

    try:
        return _t(h1, m1, ap1), _t(h2, m2, ap2)
    except Exception:
        return None, None


# Map sweeping letter codes to weekday integers
weekday_map = {
    'M': 0, 'T': 1, 'W': 2, 'TH': 3, 'F': 4, 'S': 5, 'SU': 6
}

# Handle combinations like 'MWF', 'TTHS', etc.
compound_map = {
    'MWF': [0, 2, 4],
    'TTH': [1, 3],
    'TTHS': [1, 3, 5],
    'MF': [0, 4],
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

# Pre-built CRS transformer reused across all calls (avoids repeated construction)
_CRS_TRANSFORMER = _pyproj.Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)

# Module-level cache: id(gdf) → {normalized_street_name: [row_labels]}
_name_index_cache: dict[int, dict] = {}
# Module-level cache: id(gdf) → bool (True if any polygon geometry present)
_has_polygons_cache: dict[int, bool] = {}


def check_street_sweeping(myCar, myCity):
    # myCity must already be projected to EPSG:3857 by the caller.

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

    # Name index enables O(1) street lookups instead of O(n) full iteration.
    # The index is built once per unique GDF object and cached at module level.
    name_idx = _get_name_index(myCity)

    if myStreetName and myStreets and myStreetName == myStreets[0]:
        car_x, car_y = _CRS_TRANSFORMER.transform(myCar.lon, myCar.lat)
        car_pt = Point(car_x, car_y)
        ranged_match        = False
        nearest_no_range    = None
        nearest_no_range_d  = float('inf')

        for i in name_idx.get(_norm_name(myStreetName), []):
            street_section = myCity.loc[i]
            seg_city = street_section.get("_city")
            # Skip segments from a different city when city is known
            if car_city and seg_city and seg_city != car_city:
                continue

            l_f = _safe_int(street_section.get("L_F_ADD"))
            l_t = _safe_int(street_section.get("L_T_ADD"))
            r_f = _safe_int(street_section.get("R_F_ADD"))
            r_t = _safe_int(street_section.get("R_T_ADD"))

            if l_f is not None and l_t is not None and r_f is not None and r_t is not None:
                # Address ranges present — match only if car's number is in range
                if myNumber and (l_f <= myNumber <= l_t or r_f <= myNumber <= r_t):
                    _collect(street_section)
                    ranged_match = True
            else:
                # No address ranges — track the nearest segment only
                geom = street_section.geometry
                if geom is not None and not geom.is_empty:
                    d = car_pt.distance(geom)
                    if d < nearest_no_range_d:
                        nearest_no_range_d = d
                        nearest_no_range   = street_section

        # If no range-based match was found, use the geometrically nearest segment
        if not ranged_match and nearest_no_range is not None:
            _collect(nearest_no_range)

    elif myStreetName and myStreets and len(myStreets) > 1 and myStreetName == myStreets[1]:
        # Corner case: car is on myStreets[0] but geocoder returned myStreets[1].
        # Use the nearest segment on the actual street (no house number available).
        myActualStreet = myStreets[0]
        car_x, car_y = _CRS_TRANSFORMER.transform(myCar.lon, myCar.lat)
        car_pt = Point(car_x, car_y)
        nearest_row, nearest_dist = None, float('inf')
        for i in name_idx.get(_norm_name(myActualStreet), []):
            row  = myCity.loc[i]
            geom = row.geometry
            if geom is not None and not geom.is_empty:
                d = car_pt.distance(geom)
                if d < nearest_dist:
                    nearest_dist = d
                    nearest_row  = row
        if nearest_row is not None:
            _collect(nearest_row)

    # Zone/polygon fallback — for area-based datasets like Chicago ward sections.
    # If no schedule was found above, test whether the car sits inside a zone polygon.
    if not schedule_even and not schedule_odd:
        gdf_id = id(myCity)
        if gdf_id not in _has_polygons_cache:
            _has_polygons_cache[gdf_id] = any(
                isinstance(g, (Polygon, MultiPolygon))
                for g in myCity.geometry
                if g is not None
            )
        if _has_polygons_cache[gdf_id]:
            car_x, car_y = _CRS_TRANSFORMER.transform(myCar.lon, myCar.lat)
            car_pt = Point(car_x, car_y)
            # Spatial index filters to candidate bounding boxes first,
            # then exact containment is checked — much faster than iterrows.
            for i in myCity.sindex.query(car_pt):
                row = myCity.iloc[i]
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

def check_day_street_sweeping(schedule, local_now=None):
    myDay      = local_now.date() if local_now else datetime.date.today()
    myTomorrow = myDay + datetime.timedelta(days=1)
    schedule_ymd: set = set()
    date_times: dict  = {}  # date → [time_str, ...]

    for day in schedule:
        if not day:
            continue
        code     = day[0]
        time_str = day[2] if len(day) >= 3 else ""
        try:
            dates = parse_sweeping_code(code)
            for d in dates:
                schedule_ymd.add(d)
                if time_str:
                    date_times.setdefault(d, []).append(time_str)
        except Exception:
            pass

    def _day_active(d):
        """True if sweeping is scheduled on d and has not yet ended."""
        if d not in schedule_ymd:
            return False
        if local_now is None:
            return True
        times = date_times.get(d, [])
        if not times:
            return True  # no time info — assume still active
        for ts in times:
            _, end_t = _parse_time_range(ts)
            if end_t is None or local_now.time() <= end_t:
                return True  # at least one window still open
        return False  # all windows have closed

    if _day_active(myDay):
        return "today"
    elif myTomorrow in schedule_ymd:
        return "tomorrow"
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


def _get_name_index(gdf) -> dict:
    """Build and cache a {normalized_name: [row_labels]} lookup for fast street matching."""
    gdf_id = id(gdf)
    if gdf_id not in _name_index_cache:
        idx: dict[str, list] = {}
        for i, row in gdf.iterrows():
            n = row.get("STREET_NAME")
            if _is_str(n):
                idx.setdefault(_norm_name(n), []).append(i)
        _name_index_cache[gdf_id] = idx
    return _name_index_cache[gdf_id]


def get_schedule(street_section, side):
    """Return a (code, desc, time) tuple for the given side (0 = even, 1 = odd)."""
    if side % 2 == 0:
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

@functools.lru_cache(maxsize=512)
def _parse_sweeping_code_cached(code: str, year: int, month: int) -> tuple:
    """
    Expand a sweep code into a tuple of dates for (year, month).
    Results are cached; since inputs include (year, month) the cache stays
    correct across month boundaries.
    """
    code = code.upper()

    # Handle compound sweep codes
    if code in compound_map:
        return tuple(
            d for wd in compound_map[code]
            for d in get_all_dates_for_weekday(wd, year, month)
        )

    # Handle every <day> (e.g., 'ME' = every Mon, 'TE' = every Tues)
    if code.endswith('E'):
        day_code = code[:-1]
        wd = weekday_map.get(day_code)
        if wd is not None:
            return tuple(get_all_dates_for_weekday(wd, year, month))

    # Try matching ordinal part
    for suffix, ordinal_list in ordinals.items():
        if code.endswith(suffix):
            day_code = code[:len(code) - len(suffix)]
            wd = weekday_map.get(day_code)
            if wd is not None:
                return tuple(get_weekdays_by_ordinal(wd, ordinal_list, year, month))

    # 'E' = every day
    if code == 'E':
        _, days_in_month = calendar.monthrange(year, month)
        return tuple(datetime.date(year, month, d) for d in range(1, days_in_month + 1))

    return ()  # Unknown code


def parse_sweeping_code(code: str) -> list:
    """
    Expand a sweep code into a list of dates.
    Covers the current month, plus the next month on the last day of the
    current month so the tomorrow-check is never silently missed.
    """
    # Chicago-style explicit date list: "DATES:2026-04-01,2026-04-02,..."
    if code.upper().startswith("DATES:"):
        return [
            datetime.date.fromisoformat(ds.strip())
            for ds in code[6:].split(",")
            if ds.strip()
        ]

    today = datetime.date.today()
    dates = list(_parse_sweeping_code_cached(code, today.year, today.month))

    # When today is the last day of the month, tomorrow falls in the next
    # month — expand that month too so we never miss a next-day alert.
    tomorrow = today + datetime.timedelta(days=1)
    if tomorrow.month != today.month:
        dates.extend(_parse_sweeping_code_cached(code, tomorrow.year, tomorrow.month))

    return dates
