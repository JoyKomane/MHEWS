# Quick test to find the right way to load the GADM file
import json
import os

cache_file = '/usr/src/app/gis/boundaries/zaf_admin2.geojson'
print(f"File exists: {os.path.exists(cache_file)}")
print(f"File size: {os.path.getsize(cache_file) / 1e6:.1f} MB")

# Try reading first feature to see structure
with open(cache_file, 'r') as f:
    data = json.load(f)
    
print(f"Type: {data.get('type')}")
print(f"Features: {len(data.get('features', []))}")
if data.get('features'):
    first = data['features'][0]
    print(f"First feature geometry type: {first['geometry']['type']}")
    print(f"First feature properties keys: {list(first['properties'].keys())[:5]}")
