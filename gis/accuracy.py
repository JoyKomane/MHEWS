# ============================================================
#  MHEWS — gis/accuracy.py
#  B8: Boundary Accuracy & Geometry Precision Metric
# ============================================================

from shapely.geometry import Polygon
from shapely.wkt import loads as wkt_loads
from shapely.ops import unary_union
import geopandas as gpd
from pyproj import Transformer
import os
import math

GIS_DIR = os.path.dirname(os.path.abspath(__file__))

BOUNDARY_FILE_CANDIDATES = [
    os.path.join(GIS_DIR, 'boundaries', 'zaf_admin2.shp'),
    os.path.join(GIS_DIR, 'boundaries', 'zaf_admin3.shp'),
    os.path.join(GIS_DIR, 'boundaries', 'sa_municipalities.geojson'),
]

_boundaries_gdf = None

def load_boundaries() -> gpd.GeoDataFrame | None:
    global _boundaries_gdf
    if _boundaries_gdf is not None:
        return _boundaries_gdf

    for path in BOUNDARY_FILE_CANDIDATES:
        if os.path.exists(path):
            try:
                gdf = gpd.read_file(path)
                if gdf.crs is None:
                    gdf = gdf.set_crs('EPSG:4326')
                elif gdf.crs.to_epsg() != 4326:
                    gdf = gdf.to_crs('EPSG:4326')
                _boundaries_gdf = gdf
                return _boundaries_gdf
            except Exception:
                continue
    return None

def polygon_wkt_to_shapely(polygon_wkt: str) -> Polygon | None:
    try:
        geom = wkt_loads(polygon_wkt)
        if geom.is_empty or not geom.is_valid:
            geom = geom.buffer(0)
        if geom.geom_type not in ['Polygon', 'MultiPolygon']:
            return None
        return geom
    except Exception:
        return None

def reproject_to_equal_area(geom):
    try:
        # Check if centroid is roughly in South Africa to use UTM 35S
        # Otherwise, use a generic global equal-area projection (Mollweide EPSG:54009)
        centroid = geom.centroid
        if -35 < centroid.y < -22 and 16 < centroid.x < 33:
            target_crs = 'EPSG:32735' # UTM Zone 35S for SA
        else:
            target_crs = 'EPSG:54009' # Mollweide for global area accuracy
            
        transformer = Transformer.from_crs('EPSG:4326', target_crs, always_xy=True)
        from shapely.ops import transform as shapely_transform
        return shapely_transform(transformer.transform, geom)
    except Exception:
        return geom

def compute_geometry_precision(alert_geom) -> int:
    """
    Universal metric for global CAP alerts.
    Measures how "precise" the polygon is vs a lazy bounding box.
    - Perfect rectangle (lazy CAP box) -> ~40-50%
    - Irregular, precise contour -> ~80-95%
    """
    try:
        bounds = alert_geom.bounds
        bbox_area = (bounds[2] - bounds[0]) * (bounds[3] - bounds[1])
        if bbox_area == 0 or alert_geom.area == 0:
            return 50
            
        # Rectangularity: 1.0 = perfect rectangle, <1.0 = irregular
        rectangularity = alert_geom.area / bbox_area
        
        # Score: Lower rectangularity (more irregular/precise) = Higher score
        score = 95 - (rectangularity * 50)
        return max(30, min(95, round(score)))
    except Exception:
        return 50

def compute_accuracy(alert_polygon_wkt: str) -> int:
    """
    Main function. Tries Gold Standard IoU for SA, 
    falls back to Geometry Precision Score for global alerts.
    """
    alert_geom = polygon_wkt_to_shapely(alert_polygon_wkt)
    if alert_geom is None:
        return 0

    boundaries = load_boundaries()
    
    # If we have SA boundaries AND the alert is in SA, do Gold Standard IoU
    if boundaries is not None:
        try:
            overlapping = boundaries[boundaries.geometry.intersects(alert_geom)]
            if not overlapping.empty:
                reference_geom = unary_union(overlapping.geometry)
                alert_proj = reproject_to_equal_area(alert_geom)
                reference_proj = reproject_to_equal_area(reference_geom)
                
                intersection_area = alert_proj.intersection(reference_proj).area
                union_area = alert_proj.union(reference_proj).area
                
                if union_area > 0:
                    iou = (intersection_area / union_area) * 100
                    return max(0, min(100, round(iou)))
        except Exception:
            pass # Fall through to precision score

    # Universal Fallback: Geometry Precision Score
    return compute_geometry_precision(alert_geom)

if __name__ == '__main__':
    print("Testing Accuracy Metric...")
    test_wkt = "POLYGON((30.0 -23.4, 31.2 -23.4, 31.2 -24.2, 30.0 -24.2, 30.0 -23.4))"
    print(f"Score: {compute_accuracy(test_wkt)}%")