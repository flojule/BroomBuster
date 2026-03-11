import math
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


def _car_address(myCar):
    name   = getattr(myCar, "street_name",   None)
    number = getattr(myCar, "street_number", None)
    if name:
        return f"{number or ''} {name}".strip()
    return f"Lat {myCar.lat:.4f}, Lon {myCar.lon:.4f}"


def _fmt_schedule(entries, label, highlight=False):
    """Return a single HTML line for one side's schedule."""
    valid = [e for e in entries if e and len(e) >= 3]
    lbl = f"<b>{label}</b>" if highlight else label
    if not valid:
        return f"{lbl}: no sweeping"
    seen = set()
    parts = []
    for entry in valid:
        key = (entry[1], entry[2])
        if key not in seen:
            parts.append(f"{entry[1]} \u2014 {entry[2]}")
            seen.add(key)
    return f"{lbl}: {' / '.join(parts)}"


def _build_info_panel(myCar, schedule_even, schedule_odd):
    """HTML string for the bottom-left annotation overlay."""
    today   = date.today()
    addr    = _car_address(myCar)
    number  = getattr(myCar, "street_number", None)
    car_side = "even" if (number and number % 2 == 0) else "odd"

    lines = [
        f"<b>Car:</b> {addr}",
        f"<b>Date:</b> {today.strftime('%A, %B %-d %Y')}",
        "",
        _fmt_schedule(schedule_even, "Even side", highlight=(car_side == "even")),
        _fmt_schedule(schedule_odd,  "Odd side",  highlight=(car_side == "odd")),
    ]
    return "<br>".join(lines)


def _view_circle(lat, lon, zoom=15, px_half=400, n=64):
    """Lat/lon points of a circle approximating the main map's view extent."""
    deg_per_px = 360.0 / (256 * (2 ** zoom))
    r_lon = deg_per_px * px_half
    r_lat = r_lon * math.cos(math.radians(lat))
    angles = [2 * math.pi * i / n for i in range(n + 1)]
    lats = [lat + r_lat * math.cos(a) for a in angles]
    lons = [lon + r_lon * math.sin(a) for a in angles]
    return lats, lons


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
    myCity_ = myCity.to_crs("EPSG:4326")

    # Bucket street segments by colour so each colour is a single trace
    COLORS = ("tomato", "orange", "cornflowerblue")
    buckets = {c: {"lats": [], "lons": [], "texts": []} for c in COLORS}

    for _, row in myCity_.iterrows():
        geom  = row["geometry"]
        color = _sweeping_color(row)
        hover = (
            f"<b>{_safe(row.get('STREET_NAME'))}</b><br>"
            f"Even: {_safe(row.get('DESC_EVEN'))} \u2014 {_safe(row.get('TIME_EVEN'))}<br>"
            f"Odd:  {_safe(row.get('DESC_ODD'))} \u2014 {_safe(row.get('TIME_ODD'))}"
        )
        linestrings = (
            [geom]            if isinstance(geom, shapely.geometry.LineString)
            else list(geom.geoms) if isinstance(geom, shapely.geometry.MultiLineString)
            else []
        )
        for ls in linestrings:
            x, y = ls.xy
            buckets[color]["lats"].extend(list(y) + [None])
            buckets[color]["lons"].extend(list(x) + [None])
            buckets[color]["texts"].extend([hover] * len(y) + [None])

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

    # --- Car position marker (large red dot) ---
    addr = _car_address(myCar)
    car_hover = (
        f"<b>🚗 My Car</b><br>"
        f"Address: {addr}<br>"
        f"Lat: {myCar.lat:.5f} / Lon: {myCar.lon:.5f}"
    )
    if message:
        car_hover += "<br><br>" + message.replace("\n", "<br>")

    fig.add_trace(go.Scattermapbox(
        lat=[myCar.lat], lon=[myCar.lon],
        mode="markers",
        marker=dict(size=20, color="#FF2200", opacity=1.0),
        hoverinfo="text", hovertext=car_hover,
        name="My Car",
    ))

    # --- Info annotation (bottom-left overlay) ---
    panel_html = _build_info_panel(myCar, schedule_even, schedule_odd)

    # --- Inset overview map (lower-right): car position + view-extent circle ---
    circle_lats, circle_lons = _view_circle(myCar.lat, myCar.lon)
    fig.add_trace(go.Scattermapbox(
        lat=[myCar.lat], lon=[myCar.lon],
        mode="markers",
        marker=dict(size=10, color="red"),
        hoverinfo="skip",
        subplot="mapbox2",
        showlegend=False,
    ))
    fig.add_trace(go.Scattermapbox(
        lat=circle_lats, lon=circle_lons,
        mode="lines",
        line=dict(color="red", width=2),
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
                bgcolor="rgba(255,255,255,0.88)",
                bordercolor="#aaa", borderwidth=1,
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
        # Zoom buttons sit just above the inset, aligned to its right edge
        updatemenus=[dict(
            type="buttons",
            direction="left",
            showactive=False,
            x=INSET_X1 - 0.005, xanchor="right",
            y=INSET_Y1 + 0.005, yanchor="bottom",
            bgcolor="white", bordercolor="#888", borderwidth=1,
            font=dict(size=18),
            pad=dict(r=6, l=6, t=3, b=3),
            buttons=[
                dict(label="\u2212", method="relayout",
                     args=[{"mapbox.zoom": 12}]),
                dict(label="\u233e", method="relayout",
                     args=[{"mapbox.zoom": 15,
                            "mapbox.center": {"lat": myCar.lat,
                                              "lon": myCar.lon}}]),
                dict(label="+", method="relayout",
                     args=[{"mapbox.zoom": 17}]),
            ],
        )],
    )

    fig.show(config=dict(scrollZoom=True, displayModeBar=True, displaylogo=False))

