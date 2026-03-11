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
        "oakland": _normalise_oakland,
        "sf":      _normalise_sf,
        "chicago": _normalise_chicago,
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
    "mon": "M", "tue": "T", "wed": "W", "thu": "TH",
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
    week_cols = [(n, col(f"week_{n}_of_month", f"week{n}ofmonth")) for n in range(1, 6)]

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
        side = str(row.get(side_col, "BOTH") if side_col else "BOTH").upper()
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
# Chicago  (placeholder – update once you have the actual shapefile)
# ---------------------------------------------------------------------------

def _normalise_chicago(gdf: geopandas.GeoDataFrame) -> geopandas.GeoDataFrame:
    """
    Chicago street-sweeping data normaliser.

    Chicago does not publish a single GIS layer with standardised even/odd
    sweeping codes, so this function guesses column names and does a best-effort
    mapping.  Once you have the actual file, inspect its columns with
    `geopandas.read_file(path).columns` and update the column names below.
    """
    out = gdf.copy()
    c = {col.lower(): col for col in out.columns}

    def col(*alts):
        for n in alts:
            if n.lower() in c:
                return c[n.lower()]
        return None

    name_col = col("street_name", "streetname", "name", "st_name", "stname")
    out["STREET_NAME"] = (
        out[name_col].fillna("").str.strip().str.upper() if name_col else ""
    )

    # Map whatever schedule columns exist; update these once you inspect the file
    for src, dst in [
        ("day_even", "DAY_EVEN"), ("day_odd", "DAY_ODD"),
        ("desc_even", "DESC_EVEN"), ("desc_odd", "DESC_ODD"),
        ("time_even", "TIME_EVEN"), ("time_odd", "TIME_ODD"),
    ]:
        out[dst] = out[c[src]] if src in c else None

    for addr_cn in ("L_F_ADD", "L_T_ADD", "R_F_ADD", "R_T_ADD"):
        out[addr_cn] = out[c[addr_cn.lower()]] if addr_cn.lower() in c else np.nan

    return out
