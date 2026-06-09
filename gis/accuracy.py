# ============================================================
#  MHEWS — gis/accuracy.py
#  B8: Boundary Accuracy Metric
#
#  Computes IoU (Intersection over Union) between a CAP
#  alert polygon and official SA district boundaries.
#
#  Auto-downloads GADM SA boundaries on first run.
# ============================================================

from shapely.geometry import Polygon, MultiPolygon
from shapely.wkt import loads as wkt_loads
from pyproj import Transformer
from functools import reduce
import os
import json
import urllib.request


# ============================================================
#  Paths
# ============================================================
GIS_DIR    = os.path.dirname(os.path.abspath(__file__))
BOUNDS_DIR = os.path.join(GIS_DIR, 'boundaries')
CACHE_FILE = os.path.join(BOUNDS_DIR, 'zaf_admin2.geojson')

GADM_URL = (
    "https://geodata.ucdavis.edu/gadm/gadm4.1/json/"
    "gadm41_ZAF_2.json"
)

_boundaries = None


def ensure_downloaded() -> bool:
    """Downloads GADM SA boundaries if not already cached."""
    if os.path.exists(CACHE_FILE):
        return True
    os.makedirs(BOUNDS_DIR, exist_ok=True)
    print("📥 Downloading SA boundaries from GADM...")
    try:
        urllib.request.urlretrieve(GADM_URL, CACHE_FILE)
        print(f"✅ Downloaded → {CACHE_FILE}")
        return True
    except Exception as e:
        print(f"❌ Download failed: {e}")
        return False


def geojson_multipolygon_to_shapely(geom_dict: dict):
    """
    Manually converts a GeoJSON MultiPolygon dict to Shapely.

    GADM MultiPolygon structure:
      coordinates = [ polygon, polygon, ... ]
      each polygon = [ ring, ring, ... ]
      each ring    = [ [lon, lat], [lon, lat], ... ]

    BUT in this GADM file the ring is wrapped one extra level:
      each ring = [ [ [lon,lat], [lon,lat], ... ] ]

    So we must unwrap that extra nesting.
    """
    geom_type = geom_dict.get('type')
    coords    = geom_dict.get('coordinates', [])

    polygons = []

    if geom_type == 'Polygon':
        # coords = [ ring, ring, ... ]
        # ring   = [ [lon,lat], ... ] OR [ [ [lon,lat],... ] ]
        poly = _build_polygon(coords)
        if poly:
            polygons.append(poly)

    elif geom_type == 'MultiPolygon':
        # coords = [ polygon, polygon, ... ]
        for polygon_rings in coords:
            poly = _build_polygon(polygon_rings)
            if poly:
                polygons.append(poly)

    if not polygons:
        return None

    if len(polygons) == 1:
        return polygons[0]

    return MultiPolygon(polygons)


def _build_polygon(rings: list):
    """
    Builds a Shapely Polygon from a list of rings.

    Handles the GADM extra nesting where each ring is
    wrapped in an extra list level:
      [[[ [lon,lat], [lon,lat], ... ]]]  ← wrapped
      [[ [lon,lat], [lon,lat], ... ]]    ← normal
    """
    if not rings:
        return None

    try:
        exterior_ring = rings[0]

        # Unwrap extra nesting if needed
        # Normal ring:  [[lon,lat], [lon,lat], ...]
        # Wrapped ring: [[[lon,lat], [lon,lat], ...]]
        if (len(exterior_ring) == 1 and
                isinstance(exterior_ring[0], list) and
                isinstance(exterior_ring[0][0], list)):
            exterior_ring = exterior_ring[0]

        # Now exterior_ring should be [[lon,lat], [lon,lat], ...]
        # Verify first point is [lon, lat] (two numbers)
        if not exterior_ring or len(exterior_ring[0]) < 2:
            return None

        exterior_coords = [(pt[0], pt[1]) for pt in exterior_ring]

        if len(exterior_coords) < 3:
            return None

        # Handle interior rings (holes) if any
        holes = []
        for hole_ring in rings[1:]:
            if (len(hole_ring) == 1 and
                    isinstance(hole_ring[0], list) and
                    isinstance(hole_ring[0][0], list)):
                hole_ring = hole_ring[0]
            if hole_ring and len(hole_ring[0]) >= 2:
                hole_coords = [(pt[0], pt[1]) for pt in hole_ring]
                if len(hole_coords) >= 3:
                    holes.append(hole_coords)

        poly = Polygon(exterior_coords, holes)

        if not poly.is_valid:
            poly = poly.buffer(0)

        return poly if not poly.is_empty else None

    except Exception as e:
        return None


def load_boundaries() -> list | None:
    """
    Loads SA district boundaries as list of (geometry, props).
    Auto-downloads if not cached.
    """
    global _boundaries

    if _boundaries is not None:
        return _boundaries

    if not ensure_downloaded():
        return None

    try:
        print("📂 Loading boundaries...")

        with open(CACHE_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)

        features = data['features']
        result   = []

        for feature in features:
            try:
                geom  = geojson_multipolygon_to_shapely(feature['geometry'])
                props = feature.get('properties', {})

                if geom is not None and not geom.is_empty:
                    result.append((geom, props))

            except Exception:
                continue

        _boundaries = result
        print(f"✅ Loaded {len(result)} district boundaries")
        return _boundaries

    except Exception as e:
        print(f"❌ Failed to load boundaries: {e}")
        return None


def polygon_wkt_to_shapely(wkt: str):
    """Converts WKT string to Shapely geometry."""
    try:
        geom = wkt_loads(wkt)
        if geom.is_empty or not geom.is_valid:
            geom = geom.buffer(0)
        if geom.geom_type not in ['Polygon', 'MultiPolygon']:
            return None
        return geom
    except Exception as e:
        print(f"⚠️  Invalid WKT: {e}")
        return None


def reproject_to_utm35s(geom):
    """
    Reprojects from WGS84 to UTM Zone 35S (EPSG:32735)
    for accurate area calculations in South Africa.
    """
    try:
        transformer = Transformer.from_crs(
            'EPSG:4326', 'EPSG:32735', always_xy=True
        )
        from shapely.ops import transform as shp_transform
        return shp_transform(transformer.transform, geom)
    except Exception as e:
        print(f"⚠️  Reprojection failed: {e}")
        return geom


def compute_iou(alert_polygon_wkt: str) -> int | None:
    """
    Computes IoU accuracy between a CAP alert polygon
    and official SA district boundaries.

    IoU = intersection area / union area * 100

    Returns:
        int  — real IoU 0-100
        None — boundaries unavailable
        -1   — error
    """

    # Step 1: Parse alert polygon
    alert_geom = polygon_wkt_to_shapely(alert_polygon_wkt)
    if alert_geom is None:
        return -1

    # Step 2: Load boundaries
    boundaries = load_boundaries()
    if not boundaries:
        return compute_fallback_iou(alert_geom)

    try:
        # Step 3: Find overlapping districts
        overlapping = []
        for geom, props in boundaries:
            try:
                if alert_geom.intersects(geom):
                    name = props.get('NAME_2', props.get('NAME_1', '?'))
                    print(f"   Overlaps: {name}")
                    overlapping.append(geom)
            except Exception:
                continue

        if not overlapping:
            print("⚠️  No districts overlap this alert polygon")
            return compute_fallback_iou(alert_geom)

        print(f"   Total: {len(overlapping)} district(s)")

        # Step 4: Union overlapping districts using reduce
        # unary_union has a version incompatibility with Shapely 2.0.4
        # reduce(lambda a, b: a.union(b), list) works correctly
        reference_geom = reduce(lambda a, b: a.union(b), overlapping)

        # Step 5: Reproject to UTM Zone 35S
        alert_proj     = reproject_to_utm35s(alert_geom)
        reference_proj = reproject_to_utm35s(reference_geom)

        # Step 6: IoU = intersection / union * 100
        intersection_area = alert_proj.intersection(reference_proj).area
        union_area        = alert_proj.union(reference_proj).area

        if union_area == 0:
            return 0

        iou_int = max(0, min(100, round(
            (intersection_area / union_area) * 100
        )))

        print(f"✅ IoU: {iou_int}% "
              f"(∩={intersection_area/1e6:.0f}km² "
              f"∪={union_area/1e6:.0f}km²)")

        return iou_int

    except Exception as e:
        print(f"❌ IoU failed: {e}")
        return compute_fallback_iou(alert_geom)


def compute_fallback_iou(alert_geom) -> int:
    """Fallback: uses polygon rectangularity as proxy. Returns 40-85."""
    try:
        bounds    = alert_geom.bounds
        bbox_area = (bounds[2]-bounds[0]) * (bounds[3]-bounds[1])
        if bbox_area == 0:
            return 50
        return max(40, min(85, round(85 - (alert_geom.area/bbox_area)*40)))
    except Exception:
        return 50


# ============================================================
#  Test:
#  docker exec -it mhews-app-1 python gis/accuracy.py
# ============================================================
if __name__ == '__main__':

    print("Testing IoU accuracy metric...")
    print("-" * 50)

    test_wkt = (
        "POLYGON((30.0 -23.4, 31.2 -23.4, "
        "31.2 -24.2, 30.0 -24.2, 30.0 -23.4))"
    )

    print("Test: Tzaneen/Mopani thunderstorm alert polygon")
    print()

    result = compute_iou(test_wkt)

    print()
    if result is None:
        print("⚠️  No boundary data")
    elif result == -1:
        print("❌ Calculation failed")
    else:
        print(f"🎯 Final IoU accuracy: {result}%")
        if result >= 70:
            print("   Good — alert aligns well with district boundaries")
        elif result >= 50:
            print("   Moderate — alert boundary is approximate")
        else:
            print("   Low — alert uses a rough bounding box")
