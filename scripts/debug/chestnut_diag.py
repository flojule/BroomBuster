#!/usr/bin/env python3
import sys, os
sys.path.insert(0, os.path.join(os.getcwd(), 'src'))
from data_loader import load_region_data
import normalize, analysis
from shapely.geometry import Point
from pyproj import Transformer


def main():
    gdf = load_region_data('bay_area').to_crs('EPSG:3857')
    lat, lon = 37.821326, -122.280705
    street='CHESTNUT ST'
    num=2931
    city='oakland'
    transformer = Transformer.from_crs('EPSG:4326','EPSG:3857', always_xy=True)
    px, py = transformer.transform(lon, lat)
    pt = Point(px, py)
    key = normalize.street_name(street)
    name_idx = analysis._get_name_index(gdf)
    rows = name_idx.get(normalize.street_name(street), [])
    print('found rows count:', len(rows))
    details = []
    for i in rows:
        row = gdf.loc[i]
        geom = row.geometry
        d = pt.distance(geom) if geom is not None and not geom.is_empty else None
        l_f = analysis._safe_int(row.get('L_F_ADD'))
        l_t = analysis._safe_int(row.get('L_T_ADD'))
        r_f = analysis._safe_int(row.get('R_F_ADD'))
        r_t = analysis._safe_int(row.get('R_T_ADD'))
        e = analysis.get_schedule(row,0)
        o = analysis.get_schedule(row,1)
        details.append((i,d,l_f,l_t,r_f,r_t,e,o))
    details.sort(key=lambda x: (x[1] if x[1] is not None else 1e9))
    for det in details:
        print(det)
    # print what check_street_sweeping returns
    from car import Car
    c = Car(lat=lat, lon=lon)
    c.street_name=street
    c.street_number=num
    c.streets=[(street,5.0)]
    c._city=city
    schedule, schedule_even, schedule_odd, msg = analysis.check_street_sweeping(c, gdf)
    print('\npipeline schedule_even:', schedule_even)
    print('pipeline schedule_odd:', schedule_odd)
    print('pipeline schedule:', schedule)

if __name__=='__main__':
    main()
