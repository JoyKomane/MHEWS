# Test which union method works with this Shapely version
from shapely.geometry import Polygon
from shapely.ops import unary_union

# Two simple polygons
p1 = Polygon([(0,0),(1,0),(1,1),(0,1)])
p2 = Polygon([(0.5,0),(1.5,0),(1.5,1),(0.5,1)])

print("Testing unary_union with list...")
try:
    result = unary_union([p1, p2])
    print(f"✅ unary_union([list]) works: {result.geom_type}")
except Exception as e:
    print(f"❌ Failed: {e}")

print("Testing union_all...")
try:
    from shapely.ops import union_all
    result = union_all([p1, p2])
    print(f"✅ union_all works: {result.geom_type}")
except Exception as e:
    print(f"❌ Failed: {e}")

print("Testing reduce...")
try:
    from functools import reduce
    result = reduce(lambda a, b: a.union(b), [p1, p2])
    print(f"✅ reduce union works: {result.geom_type}")
except Exception as e:
    print(f"❌ Failed: {e}")

print("Testing GeometryCollection...")
try:
    from shapely.geometry import GeometryCollection
    gc = GeometryCollection([p1, p2])
    result = gc.buffer(0)
    print(f"✅ GeometryCollection works: {result.geom_type}")
except Exception as e:
    print(f"❌ Failed: {e}")

# Check shapely version
import shapely
print(f"\nShapely version: {shapely.__version__}")
