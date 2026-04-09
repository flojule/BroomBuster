#!/usr/bin/env python3
import sys, os
sys.path.insert(0, os.path.join(os.getcwd(), 'src'))
from data_loader import load_region_data
import normalize, analysis
from shapely.geometry import Point
from pyproj import Transformer


def main():
    gdf = load_region_data('bay_area').to_crs('EPSG:3857')
    lat, lon = 37.83006, -122.26107
    street='TELEGRAPH AVE'
    num=4201
    city='oakland'
    transformer = Transformer.from_crs('EPSG:4326','EPSG:3857', always_xy=True)
    px, py = transformer.transform(lon, lat)
    pt = Point(px, py)
    key = normalize.street_name(street)
    if 'STREET_KEY' in gdf.columns:
        cand = gdf[gdf['STREET_KEY']==key]
    else:
        cand = gdf[gdf['STREET_NAME'].str.upper()==street.upper()]
    if len(cand)==0:
        print('No candidate segments found for', street)
        return
    cand = cand.copy()
    cand['dist'] = cand.geometry.distance(pt)
    nearest = cand.sort_values('dist').iloc[0]
    print('nearest STREET_NAME:', nearest.get('STREET_NAME'))
    print('nearest STREET_DISPLAY:', nearest.get('STREET_DISPLAY'))
    print('nearest index label:', nearest.name)
    print('expected_e:', analysis.get_schedule(nearest,0))
    print('expected_o:', analysis.get_schedule(nearest,1))
    from car import Car
    c = Car(lat=lat, lon=lon)
    c.street_name=street
    c.street_number=num
    c.streets=[(street,5.0)]
    c._city=city
    schedule, schedule_even, schedule_odd, msg = analysis.check_street_sweeping(c, gdf)
    print('pipeline schedule_even len:', len(schedule_even))
    print('pipeline schedule_odd len:', len(schedule_odd))
    print('pipeline schedule_even sample:', schedule_even[:3])
    print('pipeline schedule_odd sample:', schedule_odd[:3])

if __name__=='__main__':
    main()
