import plotly.graph_objects as go
import shapely
from datetime import date, timedelta

import analysis as _analysis


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe(val):
    """Return a display-friendly string or 'N/A' for NaN / None / empty."""
    if val is None:
        return "N/A"
    s = str(val).strip()
    return s if s.upper() not in ("NAN", "NONE", "") else "N/A"


def _sweeping_color(row):
    """Return a Plotly color string based on sweeping schedule urgency."""
    today    = date.today()
    tomorrow = today + timedelta(days=1)

    def has_sweep_on(day_code, check_date):
        s = _safe(day_code)
        if s in ("N/A", "N", "NS", "O"):
            return False
        try:
            return check_date in _analysis.parse_sweeping_code(s)
        except Exception:
            return False

    if has_sweep_on(row.get("DAY_EVEN"), today) or has_sweep_on(row.get("DAY_ODD"), today):
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


def _car_urgency_color(schedule_even, schedule_odd, car_side):
    """Return urgency color for the car based on its side's sweeping schedule."""
    today    = date.today()
    tomorrow = today + timedelta(days=1)
    entries  = schedule_even if car_side == "even" else schedule_odd
    dates: list = []
    for e in entries:
        if e and len(e) >= 1:
            try:
                dates.extend(_analysis.parse_sweeping_code(e[0]))
            except Exception:
                pass
    if today in dates:
        return "tomato"
    if tomorrow in dates:
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


def _densify(xs, ys, max_step=0.0003):
    """
    Insert intermediate points between every pair of vertices so that hover
    events fire anywhere along the line, not just at the original vertices.
    max_step is in degrees (~30 m at 37 N).
    """
    out_x, out_y = [xs[0]], [ys[0]]
    for i in range(1, len(xs)):
        dx = xs[i] - xs[i - 1]
        dy = ys[i] - ys[i - 1]
        n  = max(1, int(((dx * dx + dy * dy) ** 0.5) / max_step))
        for j in range(1, n):
            t = j / n
            out_x.append(xs[i - 1] + t * dx)
            out_y.append(ys[i - 1] + t * dy)
        out_x.append(xs[i])
        out_y.append(ys[i])
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
            parts.append(f"{entry[1]} \u2014 {entry[2]}")
            seen.add(key)
    return f"{bold_label} {' / '.join(parts)}"


def _build_info_panel(myCar, schedule_even, schedule_odd):
    """HTML string for the bottom-left annotation overlay."""
    today   = date.today()
    addr    = _car_address(myCar)
    number  = getattr(myCar, "street_number", None)
    car_side = "even" if (number and number % 2 == 0) else "odd"

    lines = [
        f"<b>{CAR_NAME}:</b> {addr}",
        f"<b>Date:</b> {today.strftime('%A, %B %-d %Y')}",
        "",
        _fmt_schedule(schedule_even, "Even side", highlight=(car_side == "even")),
        _fmt_schedule(schedule_odd,  "Odd side",  highlight=(car_side == "odd")),
    ]
    return "<br>".join(lines)


# ---------------------------------------------------------------------------
# Main plotting function
# ---------------------------------------------------------------------------

def plot_map(myCar, myCity, schedule_even=None, schedule_odd=None, message=None):
    """
    Render an interactive Plotly map showing:
      • All Oakland street-sweeping segments (colour-coded by schedule urgency)
      • The car's current position as an emoji marker
      • A summary panel with address and both-side sweeping schedules
    """
    schedule_even = schedule_even or []
    schedule_odd  = schedule_odd  or []

    number    = getattr(myCar, "street_number", None)
    car_side  = "even" if (number and number % 2 == 0) else "odd"
    car_color = _car_urgency_color(schedule_even, schedule_odd, car_side)

    myCity_ = myCity.to_crs("EPSG:4326")

    # Bucket street segments by colour so each colour is a single trace.
    # Two-pass deduplication: pass 1 finds the highest-urgency colour for each
    # unique segment; pass 2 renders only that colour, once per segment.
    # This prevents duplicate lines when SF/Oakland have multiple rows for the
    # same block (e.g. one row per sweep day).
    COLORS    = ("tomato", "orange", "cornflowerblue")
    _PRIORITY = {"tomato": 2, "orange": 1, "cornflowerblue": 0}
    buckets   = {c: {"lats": [], "lons": [], "texts": []} for c in COLORS}

    def _seg_key(x, y):
        return frozenset({
            (round(x[0], 5), round(y[0], 5)),
            (round(x[-1], 5), round(y[-1], 5)),
        })

    # Pass 1: determine the best (highest) priority for each segment key
    best_pri_per_key: dict = {}
    for _, row in myCity_.iterrows():
        pri = _PRIORITY[_sweeping_color(row)]
        for x, y in _geom_lines(row["geometry"]):
            x, y = list(x), list(y)
            k = _seg_key(x, y)
            if pri > best_pri_per_key.get(k, -1):
                best_pri_per_key[k] = pri

    def _hover_side(desc, time, label):
        """Format one side of the hover: omit time if already in the description."""
        d, t = _safe(desc), _safe(time)
        body = d if (t in ("N/A", "") or t in d) else f"{d} \u2014 {t}"
        return f"{label}: {body}"

    # Pass 2: render each segment at its best colour, exactly once
    rendered_keys: set = set()
    for _, row in myCity_.iterrows():
        geom  = row["geometry"]
        color = _sweeping_color(row)
        pri   = _PRIORITY[color]
        hover = (
            f"<b>{_safe(row.get('STREET_NAME'))}</b><br>"
            + _hover_side(row.get("DESC_EVEN"), row.get("TIME_EVEN"), "Even") + "<br>"
            + _hover_side(row.get("DESC_ODD"),  row.get("TIME_ODD"),  "Odd")
        )
        for x, y in _geom_lines(geom):
            x, y = list(x), list(y)
            k = _seg_key(x, y)
            if pri < best_pri_per_key.get(k, 0):
                continue          # a more urgent colour applies to this segment
            if k in rendered_keys:
                continue          # already plotted this geometry
            rendered_keys.add(k)
            dx, dy = _densify(x, y)
            buckets[color]["lats"].extend(dy + [None])
            buckets[color]["lons"].extend(dx + [None])
            buckets[color]["texts"].extend([hover] * len(dx) + [None])

    fig = go.Figure()

    color_meta = {
        "tomato":         ("Sweeping today",    5.0),
        "orange":         ("Sweeping tomorrow", 2.5),
        "cornflowerblue": ("No sweeping soon",  1.5),
    }
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
            name=label,
        ))

    # --- Car position marker (dark outline ring + coloured inner dot) ---
    # Scattermapbox markers don't support marker.line, so we use two traces:
    # a larger dark ring underneath for contrast, and the coloured dot on top.
    addr      = _car_address(myCar)
    car_hover = f"<b>{CAR_NAME}</b><br>{addr}"

    fig.add_trace(go.Scattermapbox(
        lat=[myCar.lat], lon=[myCar.lon],
        mode="markers",
        marker=dict(size=28, color="#111111", opacity=0.85),
        hoverinfo="skip",
        showlegend=False,
    ))

    fig.add_trace(go.Scattermapbox(
        lat=[myCar.lat], lon=[myCar.lon],
        mode="markers",
        marker=dict(size=20, color=car_color, opacity=1.0),
        hoverinfo="text", hovertext=car_hover,
        hoverlabel=_URGENCY_HOVER[car_color],
        name=CAR_NAME,
    ))

    # --- Info annotation (bottom-left overlay) ---
    panel_html = _build_info_panel(myCar, schedule_even, schedule_odd)

    # --- Inset overview map (lower-right): car position only ---
    fig.add_trace(go.Scattermapbox(
        lat=[myCar.lat], lon=[myCar.lon],
        mode="markers",
        marker=dict(size=10, color="red"),
        hoverinfo="skip",
        subplot="mapbox2",
        showlegend=False,
    ))

    # Inset sits at lower-right; main map explicitly owns the full canvas so it
    # doesn't split the figure with the second mapbox subplot.
    INSET_X0, INSET_X1 = 0.79, 1.0
    INSET_Y0, INSET_Y1 = 0.0,  0.24

    fig.update_layout(
        mapbox=dict(
            style="open-street-map",
            center=dict(lat=myCar.lat, lon=myCar.lon),
            zoom=15,
            domain=dict(x=[0.0, 1.0], y=[0.0, 1.0]),
        ),
        mapbox2=dict(
            style="open-street-map",
            center=dict(lat=myCar.lat, lon=myCar.lon),
            zoom=11,
            domain=dict(x=[INSET_X0, INSET_X1], y=[INSET_Y0, INSET_Y1]),
        ),
        margin={"r": 0, "t": 0, "l": 0, "b": 0},
        legend=dict(
            x=0.01, y=0.99,
            bgcolor="rgba(255,255,255,0.88)",
            bordercolor="#aaa", borderwidth=1,
        ),
        shapes=[dict(
            type="rect", xref="paper", yref="paper",
            x0=INSET_X0, y0=INSET_Y0, x1=INSET_X1, y1=INSET_Y1,
            line=dict(color="#888", width=1),
            fillcolor="rgba(0,0,0,0)", layer="above",
        )],
        annotations=[
            dict(
                text=panel_html,
                align="left", showarrow=False,
                xref="paper", yref="paper",
                x=0.01, y=0.01,
                bgcolor=_URGENCY_PANEL[car_color]["bgcolor"],
                bordercolor=_URGENCY_PANEL[car_color]["bordercolor"],
                borderwidth=1,
                font=dict(size=13),
            ),
            dict(
                text="Overview",
                showarrow=False,
                xref="paper", yref="paper",
                x=(INSET_X0 + INSET_X1) / 2,
                y=INSET_Y1 - 0.005,
                yanchor="top",
                font=dict(size=10, color="#555"),
                bgcolor="rgba(255,255,255,0.70)",
            ),
        ],
    )

    fig.show(config=dict(scrollZoom=True, displayModeBar=True, displaylogo=False))

