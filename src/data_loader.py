"""
Loads and normalises street-sweeping GeoDataFrames for any supported city.

After loading, every GeoDataFrame shares this standard column schema so that
analysis.py and maps.py work identically regardless of the data source:

  STREET_NAME    Full street name, upper-case, whitespace-normalised
  DAY_EVEN       Oakland-style sweep-day code for even-numbered addresses
                 (e.g. "M13", "FE", "WE").  None / NaN means no sweep.
  DAY_ODD        Same for odd-numbered addresses.
  DESC_EVEN      Human-readable schedule description – even side
  DESC_ODD       Human-readable schedule description – odd side
  TIME_EVEN      Sweep time window string – even side  (e.g. "8AM–10AM")
  TIME_ODD       Sweep time window string – odd side
  L_F_ADD        Left-side from-address number  (NaN if unavailable)
  L_T_ADD        Left-side to-address number
  R_F_ADD        Right-side from-address number
  R_T_ADD        Right-side to-address number

Oakland-style day codes understood by analysis.parse_sweeping_code():
  ME / TE / WE / THE / FE / SE = every Mon/Tue/Wed/Thu/Fri/Sat
  M13 / T24 / W13 / TH24 / F13 / F24 = 1st+3rd or 2nd+4th of month
  MWF / TTH / TTHS / MF / E = compound / every-day codes
  N / NS / O = no sweeping
"""

import io
import os
import zipfile

import geopandas
import numpy as np
import requests
from shapely.geometry import box as _shapely_box

from cities import CITIES


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_city_data(city_key: str) -> geopandas.GeoDataFrame:
    """Return a normalised GeoDataFrame for the given city key."""
    city = CITIES[city_key]
    local_path = city["local_path"]

    if not os.path.exists(local_path):
        url = city.get("url")
        if not url:
            raise FileNotFoundError(
                f"Data file not found: {local_path}\n"
                f"No automatic download is configured for '{city['name']}'.\n"
                f"Download the data manually and save it to: {local_path}\n"
                f"See cities.py for the data-portal URL."
            )
        print(f"Downloading {city['name']} data …")
        _download(url, local_path)
        print("Download complete.")

    gdf = geopandas.read_file(local_path)

    # Optional geographic clip (e.g. Edgewater neighbourhood only)
    if "bbox" in city:
        lat_min, lon_min, lat_max, lon_max = city["bbox"]
        clip = _shapely_box(lon_min, lat_min, lon_max, lat_max)
        gdf = gdf[gdf.geometry.intersects(clip)].copy()

    return _normalise(gdf, city["schema"])


def load_region_data(region_key: str) -> geopandas.GeoDataFrame:
    """
    Return a normalised GeoDataFrame covering all cities in the given region.

    Cities whose data files are missing (and have no auto-download URL) are
    skipped with a warning, so the rest of the region still loads.  Each row
    gets a ``_city`` column with the source city key.
    """
    import pandas as pd
    from cities import REGIONS

    region = REGIONS[region_key]
    print(f"Loading region '{region['name']}' …")
    gdfs = []
    for city_key in region["cities"]:
        try:
            gdf = load_city_data(city_key).copy()
            gdf["_city"] = city_key
            gdfs.append(gdf)
            print(f"  ✓ {CITIES[city_key]['name']} ({len(gdf)} segments)")
        except FileNotFoundError as exc:
            print(f"  ⚠  Skipping {CITIES[city_key]['name']}: {exc}")

    if not gdfs:
        raise RuntimeError(
            f"No city data could be loaded for region '{region_key}'.\n"
            "Place the required data files and retry (see cities.py for details)."
        )

    combined = geopandas.GeoDataFrame(
        pd.concat(
            [g.to_crs("EPSG:4326") for g in gdfs],
            ignore_index=True,
        ),
        crs="EPSG:4326",
    )
    print(f"Region ready — {len(combined)} total segments.")
    return combined


# ---------------------------------------------------------------------------
# Download helpers
# ---------------------------------------------------------------------------

def _download(url: str, local_path: str) -> None:
    os.makedirs(os.path.dirname(local_path), exist_ok=True)
    resp = requests.get(url, timeout=120)
    resp.raise_for_status()
    content_type = resp.headers.get("content-type", "")
    if "zip" in content_type or "Shapefile" in url or local_path.endswith(".zip"):
        z = zipfile.ZipFile(io.BytesIO(resp.content))
        z.extractall(os.path.dirname(local_path))
    else:
        with open(local_path, "wb") as fh:
            fh.write(resp.content)


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

def _normalise(gdf: geopandas.GeoDataFrame, schema: str) -> geopandas.GeoDataFrame:
    dispatch = {
        "oakland":  _normalise_oakland,
        "sf":       _normalise_sf,
        "chicago":  _normalise_chicago,
        "berkeley": _normalise_berkeley,
        "alameda":  _normalise_alameda,
        "generic":  _normalise_generic,
    }
    fn = dispatch.get(schema)
    if fn is None:
        raise ValueError(f"Unknown schema '{schema}'")
    return fn(gdf)


# ---------------------------------------------------------------------------
# Oakland
# ---------------------------------------------------------------------------

def _normalise_oakland(gdf: geopandas.GeoDataFrame) -> geopandas.GeoDataFrame:
    """
    Oakland shapefile already uses Oakland codes for DAY_EVEN / DAY_ODD.
    We only need to build STREET_NAME and create the DESC_* / TIME_* aliases.
    """
    out = gdf.copy()
    out["STREET_NAME"] = (
        out["NAME"].fillna("").str.strip()
        + " "
        + out["TYPE"].fillna("").str.strip()
    ).str.strip()
    out["DESC_EVEN"] = out.get("DescDayEve", pd_series_none(out))
    out["DESC_ODD"]  = out.get("DescDayOdd", pd_series_none(out))
    out["TIME_EVEN"] = out.get("DescTimeEv", pd_series_none(out))
    out["TIME_ODD"]  = out.get("DescTimeOd", pd_series_none(out))
    # DAY_EVEN, DAY_ODD, L_F_ADD, L_T_ADD, R_F_ADD, R_T_ADD already correct.
    return out


def pd_series_none(ref_gdf):
    """Return a Series of None values with the same index as ref_gdf."""
    import pandas as pd
    return pd.Series([None] * len(ref_gdf), index=ref_gdf.index)


# ---------------------------------------------------------------------------
# San Francisco  (DataSF – Street Sweeping Schedule, yhqp-riqs)
# ---------------------------------------------------------------------------
# Key columns (from DataSF metadata):
#   corridor       street name  e.g. "MARKET ST"
#   blockside      "ODD", "EVEN", or "BOTH"
#   week_day       integer 1–7  (1 = Monday … 7 = Sunday)
#   from_hour      integer hour (24-h)
#   to_hour        integer hour (24-h)
#   week_1_of_month … week_5_of_month   integer 1 or 0

_SF_DAY_MAP = {
    "1": "M",  "2": "T",  "3": "W",  "4": "TH", "5": "F", "6": "S", "7": "SU",
    "monday": "M", "tuesday": "T", "wednesday": "W", "thursday": "TH",
    "friday": "F", "saturday": "S", "sunday": "SU",
    # 3-4 letter abbreviations used by DataSF (e.g. "Tues", "Thurs")
    "mon": "M", "tue": "T", "tues": "T", "wed": "W", "weds": "W",
    "thu": "TH", "thur": "TH", "thurs": "TH",
    "fri": "F", "sat": "S", "sun": "SU",
}

_SF_DAY_LABEL = {
    "M": "Mon", "T": "Tue", "W": "Wed", "TH": "Thu",
    "F": "Fri", "S": "Sat", "SU": "Sun",
}


def _sf_code(row, day_col, week_cols) -> str | None:
    """Convert an SF row's week_day + week_N_of_month flags to an Oakland code."""
    raw = str(row.get(day_col, "")).strip().lower() if day_col else ""
    letter = _SF_DAY_MAP.get(raw)
    if not letter:
        return None
    on = [
        n for n, wc in week_cols
        if wc and str(row.get(wc, "0")).strip() in ("1", "1.0", "true", "True")
    ]
    if not on or set(on) >= {1, 2, 3, 4}:
        return letter + "E"  # every week
    return letter + "".join(str(w) for w in sorted(on))


def _sf_time(row, fh_col, th_col) -> str:
    try:
        fh = int(float(row.get(fh_col, "")))
        th = int(float(row.get(th_col, "")))

        def fmt(h):
            return f"{h % 12 or 12}{'AM' if h < 12 else 'PM'}"

        return f"{fmt(fh)}–{fmt(th)}"
    except (TypeError, ValueError):
        return "N/A"


def _sf_desc(code, time) -> str:
    if not isinstance(code, str):
        return "N/A"
    letter = code.rstrip("0123456789E")
    day_label = _SF_DAY_LABEL.get(letter, code)
    suffix = code[len(letter):]
    ordinal = {"E": "every", "1": "1st", "2": "2nd", "3": "3rd", "4": "4th",
               "13": "1st & 3rd", "24": "2nd & 4th"}.get(suffix, suffix)
    return f"Every {day_label} ({ordinal}), {time}" if ordinal == "every" else \
           f"{day_label} {ordinal} of month, {time}"


def _normalise_sf(gdf: geopandas.GeoDataFrame) -> geopandas.GeoDataFrame:
    out = gdf.copy()

    # Case-insensitive column lookup
    c = {col.lower(): col for col in out.columns}

    def col(*alts):
        for n in alts:
            if n.lower() in c:
                return c[n.lower()]
        return None

    name_col  = col("corridor", "cnn", "street_name")
    side_col  = col("blockside", "block_side")
    day_col   = col("week_day", "weekday")
    fh_col    = col("from_hour", "fromhour")
    th_col    = col("to_hour", "tohour")
    week_cols = [(n, col(f"week_{n}_of_month", f"week{n}ofmonth", f"week{n}")) for n in range(1, 6)]

    out["STREET_NAME"] = (
        out[name_col].fillna("").str.strip().str.upper() if name_col else ""
    )
    for cn in ("DAY_EVEN", "DAY_ODD", "DESC_EVEN", "DESC_ODD",
               "TIME_EVEN", "TIME_ODD"):
        out[cn] = None
    for addr_cn in ("L_F_ADD", "L_T_ADD", "R_F_ADD", "R_T_ADD"):
        out[addr_cn] = np.nan

    for idx, row in out.iterrows():
        code = _sf_code(row, day_col, week_cols)
        time = _sf_time(row, fh_col, th_col)
        desc = _sf_desc(code, time)
        # SF blockside uses compass directions ("SouthEast", "West", …) which
        # don't map to even/odd.  Treat anything that isn't explicitly EVEN or
        # ODD as applying to BOTH sides.
        raw_side = str(row.get(side_col, "") if side_col else "").upper()
        if raw_side == "EVEN":
            side = "EVEN"
        elif raw_side == "ODD":
            side = "ODD"
        else:
            side = "BOTH"
        if side in ("EVEN", "BOTH"):
            out.at[idx, "DAY_EVEN"]  = code
            out.at[idx, "DESC_EVEN"] = desc
            out.at[idx, "TIME_EVEN"] = time
        if side in ("ODD", "BOTH"):
            out.at[idx, "DAY_ODD"]  = code
            out.at[idx, "DESC_ODD"] = desc
            out.at[idx, "TIME_ODD"] = time

    return out


# ---------------------------------------------------------------------------
# Chicago  (zones from geospatial export + schedule from Socrata JSON API)
# ---------------------------------------------------------------------------

def _normalise_chicago(gdf: geopandas.GeoDataFrame) -> geopandas.GeoDataFrame:
    """
    Chicago normaliser: joins the Ward-Section zone polygons (from the
    geospatial export) with the sweeping schedule (fetched live from the
    Socrata JSON API).  No manual download is needed.

    Chicago publishes new datasets each year (typically March/April).
    Update the 'url' and 'schedule_url' IDs in cities.py when that happens.
    """
    import datetime as _dt
    from collections import defaultdict
    from cities import CITIES as _cit

    # ------------------------------------------------------------------
    # 1. Fetch the sweeping schedule from the Socrata API
    # ------------------------------------------------------------------
    schedule_url = _cit["chicago_edgewater"].get("schedule_url")
    sched_by_ws: dict = defaultdict(list)
    if schedule_url:
        print("  Fetching Chicago schedule from Socrata API...")
        resp = requests.get(schedule_url, timeout=60)
        resp.raise_for_status()
        for row in resp.json():
            ws = str(row.get("ward_section_concatenated", "")).zfill(4)
            try:
                month_n = int(row.get("month_number", 0))
            except (TypeError, ValueError):
                continue
            dates_csv = str(row.get("dates", "")).strip()
            if ws and month_n and dates_csv:
                sched_by_ws[ws].append((month_n, dates_csv))

    # ------------------------------------------------------------------
    # 2. Detect ward / section columns in the zones GeoDataFrame
    # ------------------------------------------------------------------
    c = {col.lower(): col for col in gdf.columns}

    def _col(*alts):
        for n in alts:
            if n in c:
                return c[n]
        return None

    ws_col   = _col("ward_section_concatenated", "wardsection",
                    "ward_section", "ws_concat")
    ward_col = _col("ward", "ward_no", "wardno")
    sect_col = _col("section", "section_no", "sectionno", "sect")

    def _ws_key(row):
        if ws_col and ws_col in row.index:
            return str(row[ws_col]).zfill(4)
        if ward_col and sect_col:
            return (
                str(row.get(ward_col, "")).zfill(2)
                + str(row.get(sect_col, "")).zfill(2)
            )
        return ""

    # ------------------------------------------------------------------
    # 3. Build schedule strings for each zone
    # ------------------------------------------------------------------
    today_year = _dt.date.today().year
    month_abbr = {
        1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr",
        5: "May", 6: "Jun", 7: "Jul", 8: "Aug",
        9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec",
    }

    def _build_schedule(month_days_list):
        """Return (dates_code, human_desc) from [(month_n, days_csv), ...]."""
        iso_parts, desc_parts = [], []
        for m, days_csv in sorted(month_days_list):
            for d_str in days_csv.split(","):
                d_str = d_str.strip()
                try:
                    iso_parts.append(
                        _dt.date(today_year, m, int(d_str)).isoformat()
                    )
                except (ValueError, TypeError):
                    pass
            desc_parts.append(f"{month_abbr.get(m, str(m))} {days_csv}")
        code = f"DATES:{','.join(iso_parts)}" if iso_parts else None
        desc = "; ".join(desc_parts) or None
        return code, desc

    out = gdf.copy()
    day_codes, descs, names = [], [], []
    for _, row in out.iterrows():
        ws = _ws_key(row)
        code, desc = _build_schedule(sched_by_ws.get(ws, []))
        day_codes.append(code)
        descs.append(desc)
        w = str(row.get(ward_col, "?") if ward_col else "?").zfill(2)
        s = str(row.get(sect_col, "?") if sect_col else "?").zfill(2)
        names.append(f"Ward {w}, Section {s}")

    out["STREET_NAME"] = names
    out["DAY_EVEN"]    = day_codes   # same zone-wide schedule for both sides
    out["DAY_ODD"]     = day_codes
    out["DESC_EVEN"]   = descs
    out["DESC_ODD"]    = descs
    out["TIME_EVEN"]   = None
    out["TIME_ODD"]    = None
    out["L_F_ADD"]     = np.nan
    out["L_T_ADD"]     = np.nan
    out["R_F_ADD"]     = np.nan
    out["R_T_ADD"]     = np.nan
    return out


# ---------------------------------------------------------------------------
# Generic  (best-effort auto-detection for unknown schemas)
# ---------------------------------------------------------------------------

def _normalise_generic(gdf: geopandas.GeoDataFrame) -> geopandas.GeoDataFrame:
    """
    Best-effort normaliser for cities whose schema is not yet mapped.

    Detects STREET_NAME and address-range columns from common naming patterns
    and leaves all schedule fields empty.  Once you have the actual data, run
        geopandas.read_file(path).columns
    and write a dedicated normaliser (like _normalise_oakland) for accurate
    sweeping schedule information.
    """
    out = gdf.copy()
    c = {col.lower(): col for col in out.columns}

    def _col(*alts):
        for n in alts:
            if n in c:
                return c[n]
        return None

    name_col = _col(
        "street_name", "stname", "streetname", "name", "fullname",
        "st_name", "full_name", "label", "street",
    )
    out["STREET_NAME"] = (
        out[name_col].fillna("").str.strip().str.upper() if name_col else ""
    )

    for dst, alts in [
        ("L_F_ADD", ["l_f_add", "lfromadd", "l_fromaddr", "leftfrom"]),
        ("L_T_ADD", ["l_t_add", "ltoadd",   "l_toaddr",   "leftto"  ]),
        ("R_F_ADD", ["r_f_add", "rfromadd", "r_fromaddr", "rightfrom"]),
        ("R_T_ADD", ["r_t_add", "rtoadd",   "r_toaddr",   "rightto"  ]),
    ]:
        found = _col(*alts)
        out[dst] = out[found] if found else np.nan

    for col_name in ("DAY_EVEN", "DAY_ODD", "DESC_EVEN", "DESC_ODD",
                     "TIME_EVEN", "TIME_ODD"):
        out[col_name] = None

    return out


# ---------------------------------------------------------------------------
# Berkeley  (placeholder — update once data is obtained)
# ---------------------------------------------------------------------------

def _normalise_berkeley(gdf: geopandas.GeoDataFrame) -> geopandas.GeoDataFrame:
    """
    Berkeley street-sweeping normaliser.

    Download the data from:
      https://data.cityofberkeley.info/Transportation/Street-Sweeping/s7pi-7kgv
    Export as GeoJSON and save to data/berkeley/StreetSweeping.geojson.

    Then inspect the columns with:
      geopandas.read_file("data/berkeley/StreetSweeping.geojson").columns

    Once the column names are known, replace this function with a proper
    mapping (see _normalise_oakland for a reference).  Until then, the
    generic auto-detector is used (schedule info will be empty).
    """
    return _normalise_generic(gdf)


# ---------------------------------------------------------------------------
# Alameda  (placeholder — no public GIS layer known yet)
# ---------------------------------------------------------------------------

def _normalise_alameda(gdf: geopandas.GeoDataFrame) -> geopandas.GeoDataFrame:
    """
    Alameda street-sweeping normaliser.

    Alameda currently publishes sweeping schedules as PDFs only.  If a GeoJSON
    or Shapefile becomes available, save it to data/alameda/StreetSweeping.geojson
    and update this function.

    Alternatively, digitise the PDF schedule manually:
      1. Load the PDF route map in QGIS alongside an OSM base layer.
      2. Trace the street segments and tag each with day/time/side attributes.
      3. Export as GeoJSON using the column names expected by _normalise_generic.

    Until proper data exists, the generic auto-detector is used (schedule info
    will be empty).
    """
    return _normalise_generic(gdf)

