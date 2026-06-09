# Quick debug — check what's actually in the downloaded file
import json

cache_file = '/usr/src/app/gis/boundaries/zaf_admin2.geojson'

with open(cache_file, 'r', encoding='utf-8') as f:
    data = json.load(f)

print(f"Top-level keys: {list(data.keys())}")
print(f"Type: {data.get('type')}")

features = data.get('features', [])
print(f"Features count: {len(features)}")

if features:
    f0 = features[0]
    print(f"\nFirst feature keys: {list(f0.keys())}")
    print(f"Geometry type: {f0.get('geometry', {}).get('type')}")
    print(f"Properties: {f0.get('properties', {})}")
else:
    # Maybe features are nested differently
    print("\nNo 'features' key — checking other keys...")
    for key in data.keys():
        val = data[key]
        print(f"  {key}: type={type(val).__name__}, ", end="")
        if isinstance(val, list):
            print(f"length={len(val)}")
            if val:
                print(f"    first item type: {type(val[0]).__name__}")
                if isinstance(val[0], dict):
                    print(f"    first item keys: {list(val[0].keys())}")
        elif isinstance(val, dict):
            print(f"keys={list(val.keys())[:5]}")
        else:
            print(f"value={str(val)[:50]}")
