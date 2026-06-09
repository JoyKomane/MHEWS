# Debug exactly why shape() loads 0 features
import json
from shapely.geometry import shape

cache_file = '/usr/src/app/gis/boundaries/zaf_admin2.geojson'

with open(cache_file, 'r', encoding='utf-8') as f:
    data = json.load(f)

features = data['features']
print(f"Total features: {len(features)}")
print()

# Try loading first 3 features and show exact error
success = 0
for i, feature in enumerate(features[:5]):
    try:
        geom_dict = feature['geometry']
        print(f"Feature {i}: type={geom_dict['type']}, coords_length={len(geom_dict['coordinates'])}")
        geom = shape(geom_dict)
        print(f"  ✅ Loaded OK: {geom.geom_type}, valid={geom.is_valid}")
        success += 1
    except Exception as e:
        print(f"  ❌ Failed: {e}")
        # Show the raw coordinate structure
        coords = geom_dict.get('coordinates', [])
        print(f"  Coords structure: {len(coords)} rings")
        if coords:
            print(f"  First ring type: {type(coords[0])}")
            if isinstance(coords[0], list):
                print(f"  First ring length: {len(coords[0])}")
                if coords[0]:
                    print(f"  First point: {coords[0][0]}")

print(f"\nSuccessfully loaded: {success}/5")
