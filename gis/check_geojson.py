# gis/check_geojson.py
import json
import sys
import os

try:
    with open("gis/data/countries.geojson", "r", encoding="utf-8") as f:
        data = json.load(f)
    
    features = data.get("features", [])
    print(f"✅ SUCCESS! Loaded {len(features)} countries from the GeoJSON file.")
    print("💡 The file is valid and ready to use.")
    
except FileNotFoundError:
    print("❌ ERROR: File not found at gis/data/countries.geojson")
    print("Please make sure you downloaded or saved the file to that exact location.")
except json.JSONDecodeError:
    print("❌ ERROR: The file is not valid JSON. The download might have failed.")