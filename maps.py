import geopandas as gpd
import plotly.express as px
import numpy as np
import shapely

def plot_map(myCar, myCity): # 3857 in meters, 4326 in degrees, EPSG:2227 cal zone 3

    format_EPSG="EPSG:4326"

    myCity_ = myCity.to_crs(format_EPSG)

    lats = []
    lons = []
    names = []

    for i, row in myCity.iterrows():
        street_line = row['geometry']
        name = f"{row['NAME']}\nEven side: {row['DescDayEve']}\nOdd side:  {row['DescDayOdd']}"
        if isinstance(street_line, shapely.geometry.linestring.LineString):
            linestrings = [street_line]
        elif isinstance(street_line, shapely.geometry.multilinestring.MultiLineString):
            linestrings = street_line.geoms
        else:
            continue
        for linestring in linestrings:
            x, y = linestring.xy
            lats = np.append(lats, y)
            lons = np.append(lons, x)
            names = np.append(names, [name]*len(y))
            lats = np.append(lats, None)
            lons = np.append(lons, None)
            names = np.append(names, None)

    fig = px.line_mapbox(
        lat=lats,
        lon=lons,
        hover_name=names
    )

    fig.update_layout(
        mapbox=dict(
            style="open-street-map",
            center=dict(lat=37.84600635927503, lon=-122.25966540705892),
            zoom=15  # realistic zoom level for a street
        ),
        margin={"r":0,"t":0,"l":0,"b":0}
    )

    fig.show()
