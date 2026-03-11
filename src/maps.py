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

# (fill_alpha, border_alpha) per urgency level
_URGENCY_ALPHA = {
    "tomato":         (0.85, 0.95),
    "orange":         (0.75, 0.92),
    "cornflowerblue": (0.30, 0.55),
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


def _interior_points(geom, max_pts: int = 16):
    """
    Return a list of (lat, lon) points guaranteed to lie inside *geom*.
    Uses a coarse grid over the bounding box, filtered by containment, with a
    hard cap so large polygons don't generate thousands of markers.
    Always includes representative_point() as a fast, guaranteed fallback.
    """
    pts = []
    polys = (
        list(geom.geoms)
        if isinstance(geom, shapely.geometry.MultiPolygon)
        else [geom]
    )
    for poly in polys:
        rp = poly.representative_point()
        pts.append((rp.y, rp.x))
        minx, miny, maxx, maxy = poly.bounds
        w, h = maxx - minx, maxy - miny
        # Choose a grid resolution that gives ~16 cells per polygon
        n = max(2, int((max_pts ** 0.5)))
        xs = [minx + (i + 0.5) * w / n for i in range(n)]
        ys = [miny + (j + 0.5) * h / n for j in range(n)]
        for x in xs:
            for y in ys:
                if len(pts) >= max_pts:
                    break
                p = shapely.geometry.Point(x, y)
                if poly.contains(p):
                    pts.append((y, x))
            if len(pts) >= max_pts:
                break
    return pts


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

    COLORS    = ("tomato", "orange", "cornflowerblue")
    _PRIORITY = {"tomato": 2, "orange": 1, "cornflowerblue": 0}

    color_meta = {
        "tomato":         ("Sweeping today",    5.0),
        "orange":         ("Sweeping tomorrow", 2.5),
        "cornflowerblue": ("No sweeping soon",  1.5),
    }

    _POLY_TYPES = (shapely.geometry.Polygon, shapely.geometry.MultiPolygon)

    def _hover_side(desc, time, label):
        """Format one side of the hover: omit time if already in the description."""
        d, t = _safe(desc), _safe(time)
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

        color = _sweeping_color(row)
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
            hlabel = dict(bgcolor="white", bordercolor="#aaa",
                          font=dict(color="black"))
            hover_pts[color] = {"lats": [], "lons": [], "texts": [],
                                 "hlabel": hlabel}
        hover_pts[color]["lats"].append(rp.y)
        hover_pts[color]["lons"].append(rp.x)
        hover_pts[color]["texts"].append(hover)

    # -----------------------------------------------------------------------
    # Line street rendering  (Oakland / SF — two-pass dedup)
    # -----------------------------------------------------------------------
    buckets = {c: {"lats": [], "lons": [], "texts": []} for c in COLORS}

    def _seg_key(x, y):
        return frozenset({
            (round(x[0], 5), round(y[0], 5)),
            (round(x[-1], 5), round(y[-1], 5)),
        })

    # Pass 1: best priority per segment key (line geometries only)
    best_pri_per_key: dict = {}
    for _, row in myCity_.iterrows():
        geom = row["geometry"]
        if not hasattr(geom, "is_empty") or geom.is_empty:
            continue
        if isinstance(geom, _POLY_TYPES):
            continue
        pri = _PRIORITY[_sweeping_color(row)]
        for x, y in _geom_lines(geom):
            x, y = list(x), list(y)
            k = _seg_key(x, y)
            if pri > best_pri_per_key.get(k, -1):
                best_pri_per_key[k] = pri

    # Pass 2: render each line segment at its best colour, exactly once
    rendered_keys: set = set()
    for _, row in myCity_.iterrows():
        geom  = row["geometry"]
        if not hasattr(geom, "is_empty") or geom.is_empty:
            continue
        if isinstance(geom, _POLY_TYPES):
            continue
        color = _sweeping_color(row)
        pri   = _PRIORITY[color]
        de  = _safe(row.get("DESC_EVEN"))
        te  = _safe(row.get("TIME_EVEN"))
        do_ = _safe(row.get("DESC_ODD"))
        to_ = _safe(row.get("TIME_ODD"))
        body_e = de  if (te  in ("N/A", "") or te  in de)  else f"{de} \u2014 {te}"
        body_o = do_ if (to_ in ("N/A", "") or to_ in do_) else f"{do_} \u2014 {to_}"
        na = "N/A"
        if body_e != na and body_e == body_o:
            sched_html = f"Street: {body_e}"
        elif body_e == na and body_o == na:
            sched_html = "No sweeping data"
        else:
            sched_html = (
                _hover_side(row.get("DESC_EVEN"), row.get("TIME_EVEN"), "Even") + "<br>"
                + _hover_side(row.get("DESC_ODD"),  row.get("TIME_ODD"),  "Odd")
            )
        hover = (
            f"<b>{_safe(row.get('STREET_NAME'))}</b><br>"
            + sched_html
        )
        for x, y in _geom_lines(geom):
            x, y = list(x), list(y)
            k = _seg_key(x, y)
            if pri < best_pri_per_key.get(k, 0):
                continue
            if k in rendered_keys:
                continue
            rendered_keys.add(k)
            dx, dy = _densify(x, y)
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
            hoverlabel=dict(bgcolor="white", bordercolor="#aaa",
                            font=dict(color="black")),
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
        marker=dict(size=10, color=car_color),
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

