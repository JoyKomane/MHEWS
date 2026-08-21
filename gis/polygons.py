import xml.etree.ElementTree as ET
import json
import re

# Load your WMO Atom/RSS feed text file
with open('Pasted_Text_1786445980138.txt', 'r', encoding='utf-8') as f:
    xml_data = f.read()

# Clean up potential script tags or HTML comments that break XML parsers
xml_data = re.sub(r'<script.*?</script>', '', xml_data, flags=re.DOTALL)
xml_data = re.sub(r'<!--.*?-->', '', xml_data, flags=re.DOTALL)

# Parse XML
root = ET.fromstring(xml_data)

# Define namespaces used in WMO feeds
namespaces = {
    'cap': 'urn:oasis:names:tc:emergency:cap:1.2',
    'raa': 'http://wmo.int/raa',
    'iso': 'http://purl.org/dc/elements/1.1/' # Fallback based on your text
}

extracted_countries = []

# Iterate through all entries (Atom) or items (RSS)
for entry in root.findall('.//entry') or root.findall('.//item'):
    title = entry.find('title').text if entry.find('title') is not None else "Unknown"
    
    # Get ISO Code
    iso_code = "Unknown"
    iso_elem = entry.find('iso:countrycode')
    if iso_elem is not None:
        iso_code = iso_elem.text
    
    # Get Feed URL
    feed_url = "None"
    feed_elem = entry.find('.//raa:capAlertFeed')
    if feed_elem is not None:
        feed_url = feed_elem.text.strip()
        
    # Get Polygon
    polygon_elem = entry.find('.//cap:polygon')
    if polygon_elem is not None and polygon_elem.text:
        raw_coords = polygon_elem.text.strip().split()
        geojson_coords = []
        
        for coord in raw_coords:
            try:
                lat, lon = coord.split(',')
                # SWAP to [Longitude, Latitude] for Mapbox/Leaflet/GeoJSON
                geojson_coords.append([float(lon), float(lat)])
            except ValueError:
                continue
                
        if geojson_coords:
            extracted_countries.append({
                "country_name": title,
                "iso_code": iso_code,
                "feed_url": feed_url,
                "polygon_geojson": geojson_coords
            })

# Save to a JSON file for your App's Database
with open('wmo_countries_polygons.json', 'w', encoding='utf-8') as f:
    json.dump(extracted_countries, f, indent=4)

print(f"Successfully extracted {len(extracted_countries)} countries with polygons!")