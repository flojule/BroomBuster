import sys, os
sys.path.insert(0, os.path.join(os.getcwd(), 'src'))
import data_loader, analysis
from car import Car

gdf = data_loader.load_region_data('bay_area')
print('loaded', len(gdf), 'rows')
norm = analysis._norm_name('CHESTNUT ST')
name_idx = analysis._get_name_index(gdf)
inds = name_idx.get(norm, [])
print('Found', len(inds), 'indices for', norm)
for i in inds[:20]:
    row = gdf.loc[i]
    print(i, row.get('STREET_NAME')[:60], row.get('DAY_EVEN'), row.get('DAY_ODD'), row.get('_city'))

# nearest segment
from shapely.geometry import Point
from pyproj import Transformer
trans = Transformer.from_crs('EPSG:4326', 'EPSG:3857', always_xy=True)
car_x, car_y = trans.transform(-122.280705, 37.821326)
car_pt = Point(car_x, car_y)
nearest_no_range = None
nearest_no_range_d = float('inf')
for i in inds:
    row = gdf.loc[i]
    geom = row.geometry
    if geom is not None and not geom.is_empty:
        d = car_pt.distance(geom)
        if d < nearest_no_range_d:
            nearest_no_range_d = d
            nearest_no_range = row
print('\nNearest segment:')
print(nearest_no_range['STREET_NAME'], nearest_no_range['DAY_EVEN'], nearest_no_range['DAY_ODD'], nearest_no_range.get('_city'))
