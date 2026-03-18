import re as _re
from datetime import date, timedelta

import numpy as np
import plotly.graph_objects as go
import shapely

import analysis as _analysis


def _clean_desc(s: str) -> str:
    """Remove redundant phrases from schedule descriptions (e.g. SF '(every)')."""
    if not s or s == "N/A":
        return s
    s = _re.sub(r"\s*\(every\)", "", s, flags=_re.IGNORECASE)
    return _re.sub(r"\s+", " ", s).strip()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe(val):
    """Return a display-friendly string or 'N/A' for NaN / None / empty."""
    if val is None:
        return "N/A"
    s = str(val).strip()
    return s if s.upper() not in ("NAN", "NONE", "") else "N/A"


def _sweeping_color(row, local_now=None):
    """Return a Plotly color string based on sweeping schedule urgency."""
    today    = local_now.date() if local_now else date.today()
    tomorrow = today + timedelta(days=1)

    def has_sweep_on(day_code, check_date):
        s = _safe(day_code)
        if s in ("N/A", "N", "NS", "O"):
            return False
        try:
            return check_date in _analysis.parse_sweeping_code(s)
        except Exception:
            return False

    def is_done(time_key):
        if local_now is None:
            return False
        time_str = _safe(row.get(time_key))
        if time_str in ("N/A", ""):
            return False
        _, end_t = _analysis._parse_time_range(time_str)
        return end_t is not None and local_now.time() > end_t

    if has_sweep_on(row.get("DAY_EVEN"), today) and not is_done("TIME_EVEN"):
        return "tomato"
    if has_sweep_on(row.get("DAY_ODD"), today) and not is_done("TIME_ODD"):
        return "tomato"
    if has_sweep_on(row.get("DAY_EVEN"), tomorrow) or has_sweep_on(row.get("DAY_ODD"), tomorrow):
        return "orange"
    return "cornflowerblue"


def _geom_lines(geom):
    """Yield (x_arr, y_arr) coordinate pairs for any drawable geometry type."""
    if isinstance(geom, shapely.geometry.LineString):
        yield geom.xy
    elif isinstance(geom, shapely.geometry.MultiLineString):
        for ls in geom.geoms:
            yield ls.xy
    elif isinstance(geom, shapely.geometry.Polygon):
        yield geom.exterior.xy
    elif isinstance(geom, shapely.geometry.MultiPolygon):
        for poly in geom.geoms:
            yield poly.exterior.xy


CAR_NAME = "🚗 My Car"


def _car_address(myCar):
    name   = getattr(myCar, "street_name",   None)
    number = getattr(myCar, "street_number", None)
    if name:
        return f"{number or ''} {name}".strip()
    return f"Lat {myCar.lat:.4f}, Lon {myCar.lon:.4f}"


def _car_urgency_color(schedule_even, schedule_odd, car_side, local_now=None):
    """Return urgency color for the car based on its side's sweeping schedule."""
    today    = local_now.date() if local_now else date.today()
    tomorrow = today + timedelta(days=1)
    entries  = schedule_even if car_side == "even" else schedule_odd
    today_active    = False
    tomorrow_active = False
    for e in entries:
        if not e or len(e) < 1:
            continue
        try:
            dates = _analysis.parse_sweeping_code(e[0])
        except Exception:
            continue
        if today in dates:
            time_str = e[2] if len(e) >= 3 else ""
            if local_now and time_str:
                _, end_t = _analysis._parse_time_range(time_str)
                if end_t is None or local_now.time() <= end_t:
                    today_active = True
            else:
                today_active = True
        if tomorrow in dates:
            tomorrow_active = True
    if today_active:
        return "tomato"
    if tomorrow_active:
        return "orange"
    return "cornflowerblue"


# Annotation panel styles keyed by urgency color
_URGENCY_PANEL = {
    "tomato":         {"bgcolor": "rgba(255,200,190,0.95)", "bordercolor": "tomato"},
    "orange":         {"bgcolor": "rgba(255,235,190,0.95)", "bordercolor": "darkorange"},
    "cornflowerblue": {"bgcolor": "rgba(255,255,255,0.88)", "bordercolor": "#aaa"},
}

# Hover-label styles keyed by urgency color
_URGENCY_HOVER = {
    "tomato":         dict(bgcolor="tomato",  bordercolor="tomato",     font=dict(color="white")),
    "orange":         dict(bgcolor="orange",  bordercolor="darkorange", font=dict(color="black")),
    "cornflowerblue": dict(bgcolor="white",   bordercolor="#aaa",       font=dict(color="black")),
}

# ---------------------------------------------------------------------------
# Zone colour palette
# ---------------------------------------------------------------------------

# 20 perceptually distinct named colours.  Urgency is communicated by fill
# opacity and border vividness; the chosen hue signals zone identity.
_ZONE_PALETTE = [
    ("Crimson",    220, 50,  60),
    ("Coral",      255, 100, 80),
    ("Tomato",     255, 70,  47),
    ("Salmon",     248, 138, 105),
    ("Amber",      255, 185, 15),
    ("Goldenrod",  218, 160, 30),
    ("Tangerine",  255, 145, 0),
    ("Khaki",      195, 170, 65),
    ("Lime",       128, 190, 48),
    ("Olive",      120, 150, 52),
    ("Teal",       38,  155, 140),
    ("Turquoise",  52,  182, 168),
    ("Sky",        75,  175, 215),
    ("Steelblue",  70,  130, 180),
    ("Royalblue",  60,  100, 220),
    ("Periwinkle", 118, 138, 218),
    ("Lavender",   148, 112, 202),
    ("Plum",       172, 72,  168),
    ("Orchid",     192, 92,  172),
    ("Rose",       225, 82,  112),
]

# (fill_alpha, border_alpha) per urgency level — fills are ~10% to keep map readable
_URGENCY_ALPHA = {
    "tomato":         (0.10, 0.75),
    "orange":         (0.10, 0.60),
    "cornflowerblue": (0.08, 0.22),
}

# Border darkening factor per urgency (multiplied with zone's base rgb)
_URGENCY_BORDER_DARKEN = {
    "tomato":         0.45,
    "orange":         0.55,
    "cornflowerblue": 0.65,
}


def _zone_fill_color(w: int, s: int, urgency: str):
    """Return (fill_rgba, border_rgba, color_name) for a zone."""
    idx = (w * 100 + s) % len(_ZONE_PALETTE)
    name, r, g, b = _ZONE_PALETTE[idx]
    fa, ba = _URGENCY_ALPHA[urgency]
    dk = _URGENCY_BORDER_DARKEN[urgency]
    br, bg_, bb = int(r * dk), int(g * dk), int(b * dk)
    fill   = f"rgba({r},{g},{b},{fa:.2f})"
    border = f"rgba({br},{bg_},{bb},{ba:.2f})"
    return fill, border, name


def _densify(xs, ys, max_step=0.0003):
    """
    Insert intermediate points between every pair of vertices so that hover
    events fire anywhere along the line, not just at the original vertices.
    max_step is in degrees (~30 m at 37 N).
    """
    xs = np.asarray(xs, dtype=float)
    ys = np.asarray(ys, dtype=float)
    dx = np.diff(xs)
    dy = np.diff(ys)
    segs = np.maximum(1, (np.hypot(dx, dy) / max_step).astype(int))

    out_x = [xs[0]]
    out_y = [ys[0]]
    for i, n in enumerate(segs):
        ts = np.linspace(0, 1, n + 1)[1:]   # skip t=0 (already added)
        out_x.extend((xs[i] + ts * dx[i]).tolist())
        out_y.extend((ys[i] + ts * dy[i]).tolist())
    return out_x, out_y


def _fmt_schedule(entries, label, highlight=False):
    """Return a single HTML line: bold label, plain schedule text."""
    valid = [e for e in entries if e and len(e) >= 3]
    # Leading indicator keeps both rows aligned: highlighted gets ►, others
    # get a same-width invisible spacer so text columns line up.
    prefix     = "&#9658;&nbsp;" if highlight else "&nbsp;&nbsp;&nbsp;"
    bold_label = f"<b>{prefix}{label}:</b>"
    if not valid:
        return f"{bold_label} no sweeping"
    seen = set()
    parts = []
    for entry in valid:
        key = (entry[1], entry[2])
        if key not in seen:
            t = entry[2]
            body = entry[1] if not t else f"{entry[1]} \u2014 {t}"
            parts.append(body)
            seen.add(key)
    return f"{bold_label} {' / '.join(parts)}"


def _build_info_panel(myCar, schedule_even, schedule_odd):
    """HTML string for the bottom-left annotation overlay."""
    today   = date.today()
    addr    = _car_address(myCar)
    number  = getattr(myCar, "street_number", None)
    car_side = "even" if (number and number % 2 == 0) else "odd"

    def _sched_parts(entries):
        valid = [e for e in entries if e and len(e) >= 3]
        seen, parts = set(), []
        for entry in valid:
            key = (entry[1], entry[2])
            if key not in seen:
                t    = entry[2]
                body = entry[1] if not t else f"{entry[1]} \u2014 {t}"
                parts.append(body)
                seen.add(key)
        return parts

    even_parts = _sched_parts(schedule_even)
    odd_parts  = _sched_parts(schedule_odd)

    header = [
        f"<b>{CAR_NAME}:</b> {addr}",
        f"<b>Date:</b> {today.strftime('%A, %B %-d %Y')}",
        "",
    ]

    if even_parts and even_parts == odd_parts:
        sched = [f"&#9658;&nbsp;<b>Street:</b> {' / '.join(even_parts)}"]
    else:
        sched = [
            _fmt_schedule(schedule_even, "Even side", highlight=(car_side == "even")),
            _fmt_schedule(schedule_odd,  "Odd side",  highlight=(car_side == "odd")),
        ]

    return "<br>".join(header + sched)


# ---------------------------------------------------------------------------
# Main plotting function
# ---------------------------------------------------------------------------

def _build_map_figure(myCar, myCity, schedule_even=None, schedule_odd=None, message=None, local_now=None):
    """Build and return the Plotly Figure (does not display it)."""
    schedule_even = schedule_even or []
    schedule_odd  = schedule_odd  or []

    number    = getattr(myCar, "street_number", None)
    car_side  = "even" if (number and number % 2 == 0) else "odd"
    car_color = _car_urgency_color(schedule_even, schedule_odd, car_side, local_now=local_now)

    myCity_ = myCity.to_crs("EPSG:4326")

    COLORS    = ("tomato", "orange", "cornflowerblue")
    _PRIORITY = {"tomato": 2, "orange": 1, "cornflowerblue": 0}

    color_meta = {
        "tomato":         ("Sweeping today",    5.0),
        "orange":         ("Sweeping tomorrow", 2.5),
        "cornflowerblue": ("No sweeping soon",  1.5),
    }

    _POLY_TYPES = (shapely.geometry.Polygon, shapely.geometry.MultiPolygon)

    # Pre-compute urgency color for every row once; reused in all three passes.
    _row_color: dict = {}
    for _idx, _row in myCity_.iterrows():
        _row_color[_idx] = _sweeping_color(_row, local_now=local_now)

    # Override colors for the car's own street: use the car's specific side only,
    # so the street color matches what the car card shows.
    today    = local_now.date() if local_now else date.today()
    tomorrow = today + timedelta(days=1)
    _car_norm     = _analysis._norm_name(getattr(myCar, "street_name", "") or "")
    _car_day_key  = "DAY_EVEN"  if car_side == "even" else "DAY_ODD"
    _car_time_key = "TIME_EVEN" if car_side == "even" else "TIME_ODD"
    if _car_norm:
        for _idx, _row in myCity_.iterrows():
            rn = _safe(_row.get("STREET_NAME"))
            if _analysis._norm_name(rn) != _car_norm:
                continue
            s = _safe(_row.get(_car_day_key))
            if s not in ("N/A", "N", "NS", "O", ""):
                try:
                    dates = _analysis.parse_sweeping_code(s)
                    if today in dates:
                        sweep_done = False
                        if local_now:
                            time_str = _safe(_row.get(_car_time_key))
                            if time_str not in ("N/A", ""):
                                _, end_t = _analysis._parse_time_range(time_str)
                                if end_t is not None and local_now.time() > end_t:
                                    sweep_done = True
                        if not sweep_done:
                            _row_color[_idx] = "tomato"; continue
                    if tomorrow in dates:
                        _row_color[_idx] = "orange"; continue
                except Exception:
                    pass
            _row_color[_idx] = "cornflowerblue"

    # Transparent hoverlabel — preserves Plotly hover hit detection so plotly_hover
    # events fire, while the custom HTML tooltip (#custom-hover) handles display.
    _HOVERLABEL = dict(
        bgcolor="rgba(0,0,0,0)",
        bordercolor="rgba(0,0,0,0)",
        namelength=0,
        font=dict(
            family='-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
            size=1, color="rgba(0,0,0,0)",
        ),
    )

    def _hover_side(desc, time, label):
        """Format one side of the hover: omit time if already in the description."""
        d, t = _clean_desc(_safe(desc)), _safe(time)
        body = d if (t in ("N/A", "") or t in d) else f"{d} \u2014 {t}"
        return f"{label}: {body}"

    def _zone_hover(row):
        name = _safe(row.get("STREET_NAME"))
        return (
            f"<b>{name}</b><br>"
            + _hover_side(row.get("DESC_EVEN"), row.get("TIME_EVEN"), "Sweeping") + "<br>"
        )

    # -----------------------------------------------------------------------
    # Polygon zone rendering  (e.g. Chicago ward sections)
    # Zones are bucketed by (palette_index × urgency) — at most 60 buckets —
    # so the figure has far fewer traces than one-per-zone.  Interior hover
    # coverage is provided by a single invisible marker trace per urgency.
    # -----------------------------------------------------------------------
    # outline_buckets: (fill_rgba, border_rgba, urgency) -> {lats, lons, texts}
    outline_buckets: dict = {}
    # hover_pts: urgency -> {lats, lons, texts, hoverlabel}
    hover_pts: dict = {}
    poly_legend_added: set = set()

    for _, row in myCity_.iterrows():
        geom = row["geometry"]
        if not hasattr(geom, "is_empty") or geom.is_empty:
            continue
        if not isinstance(geom, _POLY_TYPES):
            continue

        color = _row_color[_]
        try:
            w = int(float(row.get("ward_id") or row.get("ward") or 0))
            s = int(float(row.get("section_id") or row.get("section") or 0))
        except (TypeError, ValueError):
            w, s = 0, 0

        fill_color, border_color, _color_name = _zone_fill_color(w, s, color)
        hover = _zone_hover(row)

        okey = (fill_color, border_color, color)
        if okey not in outline_buckets:
            outline_buckets[okey] = {"lats": [], "lons": [], "texts": []}
        ob = outline_buckets[okey]
        for x, y in _geom_lines(geom):
            xs, ys = list(x), list(y)
            ob["lats"].extend(ys + [None])
            ob["lons"].extend(xs + [None])
            ob["texts"].extend([hover] * len(xs) + [None])

        # Interior representative point for reliable hover anywhere inside
        rp = geom.representative_point()
        if color not in hover_pts:
            hover_pts[color] = {"lats": [], "lons": [], "texts": [],
                                 "hlabel": _HOVERLABEL}
        hover_pts[color]["lats"].append(rp.y)
        hover_pts[color]["lons"].append(rp.x)
        hover_pts[color]["texts"].append(hover)

    # -----------------------------------------------------------------------
    # Line street rendering  (Oakland / SF — single-pass, merges hover per key)
    # SF has one row per blockside (EVEN/ODD), same geometry for both sides of a
    # block. We accumulate schedule text from ALL rows sharing the same endpoint
    # key and colour at the highest urgency seen across those rows.
    # -----------------------------------------------------------------------
    buckets = {c: {"lats": [], "lons": [], "texts": []} for c in COLORS}

    def _seg_key(x, y):
        return frozenset({
            (round(x[0], 5), round(y[0], 5)),
            (round(x[-1], 5), round(y[-1], 5)),
        })

    def _side_body(desc, time):
        d, t = _clean_desc(_safe(desc)), _safe(time)
        if d in ("N/A", ""):
            return None
        return d if t in ("N/A", "") or t in d else f"{d} \u2014 {t}"

    # key → {color, pri, dx, dy, name, even: [...], odd: [...]}
    seg_data: dict = {}

    for _, row in myCity_.iterrows():
        geom = row["geometry"]
        if not hasattr(geom, "is_empty") or geom.is_empty:
            continue
        if isinstance(geom, _POLY_TYPES):
            continue
        color = _row_color[_]
        pri   = _PRIORITY[color]
        be    = _side_body(row.get("DESC_EVEN"), row.get("TIME_EVEN"))
        bo    = _side_body(row.get("DESC_ODD"),  row.get("TIME_ODD"))
        name  = _safe(row.get("STREET_NAME"))

        for x, y in _geom_lines(geom):
            x, y = list(x), list(y)
            k = _seg_key(x, y)
            if k not in seg_data:
                dx, dy = _densify(x, y)
                seg_data[k] = {
                    "color": color, "pri": pri,
                    "dx": dx, "dy": dy, "name": name,
                    "even": [be] if be else [],
                    "odd":  [bo] if bo else [],
                }
            else:
                sd = seg_data[k]
                if pri > sd["pri"]:
                    sd["pri"] = pri
                    sd["color"] = color
                    dx, dy = _densify(x, y)
                    sd["dx"] = dx
                    sd["dy"] = dy
                    # Higher-priority row takes precedence; keep any already-set side
                    if be:
                        sd["even"] = [be]
                    if bo:
                        sd["odd"] = [bo]
                else:
                    # Same/lower priority: only fill a side that hasn't been set yet.
                    # This merges even+odd rows (same geometry, different sides) without
                    # stacking multiple address-range schedules for the same side.
                    if be and not sd["even"]:
                        sd["even"] = [be]
                    if bo and not sd["odd"]:
                        sd["odd"] = [bo]

    for sd in seg_data.values():
        evens = sd["even"]
        odds  = sd["odd"]
        color = sd["color"]
        if evens and odds and evens == odds:
            sched_html = f"Street: {' / '.join(evens)}"
        elif not evens and not odds:
            sched_html = "No sweeping data"
        else:
            parts = []
            if evens: parts.append("Even: " + " / ".join(evens))
            if odds:  parts.append("Odd: "  + " / ".join(odds))
            sched_html = "<br>".join(parts)
        hover = f"<b>{sd['name']}</b><br>{sched_html}"
        dx, dy = sd["dx"], sd["dy"]
        buckets[color]["lats"].extend(dy + [None])
        buckets[color]["lons"].extend(dx + [None])
        buckets[color]["texts"].extend([hover] * len(dx) + [None])

    # -----------------------------------------------------------------------
    # Build figure — polygons first (behind) then lines then markers
    # -----------------------------------------------------------------------
    fig = go.Figure()

    # -- Polygon zone fills (batched by palette×urgency — ~60 traces max) --
    for (fill_color, border_color, urgency), ob in outline_buckets.items():
        label, _ = color_meta[urgency]
        show_legend = urgency not in poly_legend_added
        if show_legend:
            poly_legend_added.add(urgency)
        fig.add_trace(go.Scattermapbox(
            lat=ob["lats"], lon=ob["lons"],
            mode="lines",
            fill="toself",
            fillcolor=fill_color,
            line=dict(width=1.5, color=border_color),
            hoverinfo="text", text=ob["texts"],
            hoverlabel=_HOVERLABEL,
            name=label,
            showlegend=show_legend,
        ))

    # -- Invisible interior markers: one trace per urgency for zone hover --
    for urgency, hp in hover_pts.items():
        fig.add_trace(go.Scattermapbox(
            lat=hp["lats"], lon=hp["lons"],
            mode="markers",
            marker=dict(size=30, opacity=0),
            hoverinfo="text", text=hp["texts"],
            hoverlabel=hp["hlabel"],
            showlegend=False,
        ))

    # -- Line street traces --
    for color in COLORS:
        b = buckets[color]
        if not b["lats"]:
            continue
        label, width = color_meta[color]
        fig.add_trace(go.Scattermapbox(
            lat=b["lats"], lon=b["lons"],
            mode="lines",
            line=dict(width=width, color=color),
            hoverinfo="text", text=b["texts"],
            hoverlabel=_HOVERLABEL,
            name=label,
            showlegend=True,
        ))

    fig.update_layout(
        mapbox=dict(
            style="open-street-map",
            center=dict(lat=myCar.lat, lon=myCar.lon),
            zoom=15,
        ),
        margin={"r": 0, "t": 0, "l": 0, "b": 0},
        showlegend=False,
    )

    return fig


def plot_map(myCar, myCity, schedule_even=None, schedule_odd=None, message=None, local_now=None):
    """Render the map and open it in a browser tab."""
    fig = _build_map_figure(myCar, myCity, schedule_even, schedule_odd, message, local_now=local_now)
    fig.show(config=dict(scrollZoom=True, displayModeBar=True, displaylogo=False))


def plot_map_dict(myCar, myCity, schedule_even=None, schedule_odd=None, message=None, local_now=None) -> dict:
    """Return the Plotly figure as a JSON-serialisable dict (for API responses)."""
    fig = _build_map_figure(myCar, myCity, schedule_even, schedule_odd, message, local_now=local_now)
    return fig.to_dict()

