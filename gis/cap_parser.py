# ============================================================
#  MHEWS — gis/cap_parser.py
#  B7: CAP XML Parser
#
#  What does this file do?
#  It takes a raw CAP (Common Alerting Protocol) XML string
#  from any source — SAWS, GDACS, WMO — and converts it
#  into a clean Python dictionary that matches our PostGIS
#  alerts table exactly.
#
#  CAP is an international standard (OASIS CAP 1.2) so the
#  XML structure is the same regardless of who issues it.
#  SAWS, GDACS, and WMO all use the same field names.
#
#  Input:  raw XML string (from a feed URL or a file)
#  Output: Python dict with all fields ready for PostGIS
#
#  Usage:
#    from gis.cap_parser import parse_cap_xml
#    alert = parse_cap_xml(xml_string)
# ============================================================

# lxml is a fast, powerful XML parser for Python.
# etree is the module inside lxml that reads XML trees.
from lxml import etree

# re is Python's regular expressions module.
# We use it to clean up polygon coordinate strings.
import re

# hashlib generates unique IDs from text.
# Used when a CAP alert has no identifier field.
import hashlib

# datetime for handling timezone-aware timestamps.
from datetime import datetime, timezone


# ============================================================
#  CAP XML Namespaces
# ============================================================
#  CAP XML uses namespaces — prefixes that identify which
#  standard a tag belongs to. SAWS uses CAP 1.2.
#  Without declaring these, lxml can't find the tags.
#
#  We define both with and without namespace so the parser
#  works on feeds that omit the namespace declaration.
# ============================================================
CAP_NAMESPACES = {
    'cap':  'urn:oasis:names:tc:emergency:cap:1.2',
    'cap10': 'urn:oasis:names:tc:emergency:cap:1.0',
    'cap11': 'urn:oasis:names:tc:emergency:cap:1.1',
}

# ============================================================
#  Hazard category mapping
# ============================================================
#  CAP uses a standard "event" field like "Thunderstorm" or
#  "Flash Flood". We map these to broader hazard categories
#  for the frontend icon system (F4).
#
#  This covers all major global hazard types — not just
#  the three original mock alerts.
# ============================================================
HAZARD_CATEGORIES = {
    # Meteorological
    'thunderstorm':     'meteorological',
    'wind':             'meteorological',
    'tornado':          'meteorological',
    'cyclone':          'meteorological',
    'hurricane':        'meteorological',
    'tropical storm':   'meteorological',
    'hail':             'meteorological',
    'snow':             'meteorological',
    'blizzard':         'meteorological',
    'fog':              'meteorological',
    'heat':             'meteorological',
    'cold':             'meteorological',
    'frost':            'meteorological',
    'lightning':        'meteorological',

    # Hydrological
    'flood':            'hydrological',
    'flash flood':      'hydrological',
    'storm surge':      'hydrological',
    'tsunami':          'hydrological',
    'dam':              'hydrological',

    # Geophysical
    'earthquake':       'geophysical',
    'seismic':          'geophysical',
    'volcano':          'geophysical',
    'volcanic':         'geophysical',
    'landslide':        'geophysical',
    'avalanche':        'geophysical',

    # Fire
    'fire':             'fire',
    'wildfire':         'fire',
    'veld fire':        'fire',
    'bush fire':        'fire',
    'forest fire':      'fire',

    # Biological / chemical / other
    'drought':          'drought',
    'dust':             'meteorological',
    'air quality':      'environmental',
    'chemical':         'technological',
    'nuclear':          'technological',
    'industrial':       'technological',
}


def get_hazard_category(event_text: str) -> str:
    """
    Maps a CAP event string to a hazard category.

    Checks if any keyword from our mapping appears in the
    event text (case-insensitive).

    Examples:
      "Severe Thunderstorm Warning" → "meteorological"
      "Flash Flood Watch"           → "hydrological"
      "Veld Fire Advisory"          → "fire"
      "Unknown Event"               → "other"
    """
    if not event_text:
        return 'other'

    # Convert to lowercase for case-insensitive matching
    event_lower = event_text.lower()

    for keyword, category in HAZARD_CATEGORIES.items():
        if keyword in event_lower:
            return category

    return 'other'


def find_text(element, tag: str, namespaces: dict) -> str:
    """
    Helper function to find a tag's text in XML,
    trying multiple CAP namespace versions.

    CAP feeds sometimes use different namespace prefixes,
    so we try cap, cap10, and cap11 before giving up.

    Returns the text content or empty string if not found.
    """
    # Try each namespace version
    for prefix in ['cap', 'cap10', 'cap11']:
        ns = namespaces.get(prefix)
        if ns:
            result = element.find(f'{{{ns}}}{tag}')
            if result is not None and result.text:
                return result.text.strip()

    # Try without namespace (some feeds omit it)
    result = element.find(tag)
    if result is not None and result.text:
        return result.text.strip()

    return ''


def parse_polygon_string(polygon_str: str) -> list:
    """
    Converts a CAP polygon string into a list of [lat, lon] pairs.

    CAP polygon format: "lat,lon lat,lon lat,lon ..."
    Example: "-23.4,30.0 -23.4,31.2 -24.2,31.2 -24.2,30.0"

    Returns a list of coordinate pairs:
    [[-23.4, 30.0], [-23.4, 31.2], ...]

    Returns empty list if the string is invalid.
    """
    if not polygon_str:
        return []

    try:
        coords = []
        # Split by whitespace to get individual "lat,lon" pairs
        pairs = polygon_str.strip().split()

        for pair in pairs:
            # Split each pair by comma
            parts = pair.split(',')
            if len(parts) >= 2:
                lat = float(parts[0])
                lon = float(parts[1])
                coords.append([lat, lon])

        # CAP polygon must have at least 3 points to be valid
        if len(coords) < 3:
            return []

        # Ensure the polygon is closed (first point = last point)
        # PostGIS requires closed polygons
        if coords[0] != coords[-1]:
            coords.append(coords[0])

        return coords

    except (ValueError, IndexError):
        # If anything goes wrong, return empty list
        return []


def coords_to_wkt(coords: list) -> str:
    """
    Converts a list of [lat, lon] coordinate pairs to
    Well-Known Text (WKT) format for PostGIS.

    IMPORTANT: PostGIS uses (longitude latitude) order — x, y.
    CAP uses (latitude, longitude) order.
    We must swap them here.

    Input:  [[-23.4, 30.0], [-23.4, 31.2], ...]
    Output: "POLYGON((30.0 -23.4, 31.2 -23.4, ...))"
    """
    if not coords:
        return ''

    # Swap lat,lon to lon,lat for PostGIS
    # PostGIS wants: POLYGON((lon lat, lon lat, ...))
    wkt_coords = ', '.join(f'{lon} {lat}' for lat, lon in coords)
    return f'POLYGON(({wkt_coords}))'


def parse_cap_xml(xml_string: str) -> dict | None:
    """
    Main function — parses a CAP XML string into a dict.

    Takes the raw XML text from a SAWS, GDACS, or any
    CAP-compliant feed and returns a Python dictionary
    with all the fields our PostGIS table needs.

    Returns None if the XML is invalid or missing critical fields.

    The returned dict matches the alerts table columns:
    {
        'id':               str,   # CAP identifier
        'event':            str,   # e.g. "Severe Thunderstorm Warning"
        'severity':         str,   # Extreme/Severe/Moderate/Minor
        'urgency':          str,   # Immediate/Expected/Future
        'description':      str,   # Technical description
        'instruction':      str,   # Action instructions
        'onset':            str,   # ISO timestamp
        'expires':          str,   # ISO timestamp
        'source':           str,   # Issuing organisation
        'area_desc':        str,   # Human-readable area name
        'hazard_category':  str,   # fire/flood/meteorological etc.
        'polygon_wkt':      str,   # WKT polygon for PostGIS
        'plain_text':       None,  # Filled by B9 (Claude API)
    }
    """
    try:
        # ----------------------------------------------------------
        #  Step 1: Parse the XML string into an element tree
        # ----------------------------------------------------------
        #  etree.fromstring() parses XML text into a tree of elements.
        #  We encode to bytes first because lxml prefers bytes input.
        # ----------------------------------------------------------
        if isinstance(xml_string, str):
            xml_bytes = xml_string.encode('utf-8')
        else:
            xml_bytes = xml_string

        root = etree.fromstring(xml_bytes)

        # ----------------------------------------------------------
        #  Step 2: Detect which CAP namespace this feed uses
        # ----------------------------------------------------------
        #  The namespace is declared in the root element's tag.
        #  Example: {urn:oasis:names:tc:emergency:cap:1.2}alert
        # ----------------------------------------------------------
        ns = {}
        root_tag = root.tag

        if 'cap:1.2' in root_tag or 'cap:1.2' in str(root.nsmap):
            ns = {'cap': 'urn:oasis:names:tc:emergency:cap:1.2'}
        elif 'cap:1.1' in root_tag or 'cap:1.1' in str(root.nsmap):
            ns = {'cap': 'urn:oasis:names:tc:emergency:cap:1.1'}
        elif 'cap:1.0' in root_tag or 'cap:1.0' in str(root.nsmap):
            ns = {'cap': 'urn:oasis:names:tc:emergency:cap:1.0'}
        else:
            # Try to detect namespace from root element's nsmap
            for prefix, uri in root.nsmap.items():
                if 'emergency:cap' in uri:
                    ns = {'cap': uri}
                    break

        # Merge with our full namespace dict for find_text()
        full_ns = {**CAP_NAMESPACES, **ns}

        # ----------------------------------------------------------
        #  Step 3: Extract alert-level fields
        # ----------------------------------------------------------
        #  These fields are at the top level of the <alert> element.
        # ----------------------------------------------------------
        identifier = find_text(root, 'identifier', full_ns)
        sender     = find_text(root, 'sender',     full_ns)
        sent       = find_text(root, 'sent',        full_ns)

        # If no identifier, generate one from sender + sent time
        # This ensures every alert has a unique ID
        if not identifier:
            raw = f"{sender}{sent}"
            identifier = hashlib.md5(raw.encode()).hexdigest()[:16]

        # ----------------------------------------------------------
        #  Step 4: Find the <info> block
        # ----------------------------------------------------------
        #  A CAP alert can have multiple <info> blocks for different
        #  languages. We take the first English one, or just the first.
        # ----------------------------------------------------------
        info = None

        # Try with namespace
        for prefix, uri in full_ns.items():
            infos = root.findall(f'{{{uri}}}info')
            if infos:
                # Prefer English language block
                for i in infos:
                    lang = find_text(i, 'language', full_ns)
                    if not lang or 'en' in lang.lower():
                        info = i
                        break
                # Fall back to first block if no English found
                if info is None:
                    info = infos[0]
                break

        # Try without namespace
        if info is None:
            infos = root.findall('info')
            if infos:
                info = infos[0]

        if info is None:
            print(f"⚠️  No <info> block found in CAP alert {identifier}")
            return None

        # ----------------------------------------------------------
        #  Step 5: Extract info-level fields
        # ----------------------------------------------------------
        event       = find_text(info, 'event',       full_ns)
        severity    = find_text(info, 'severity',    full_ns)
        urgency     = find_text(info, 'urgency',     full_ns)
        description = find_text(info, 'description', full_ns)
        instruction = find_text(info, 'instruction', full_ns)
        onset       = find_text(info, 'onset',       full_ns)
        expires     = find_text(info, 'expires',     full_ns)

        # ----------------------------------------------------------
        #  Step 6: Extract area information
        # ----------------------------------------------------------
        #  The <area> block contains the geographic information —
        #  the human-readable area description and the polygon.
        # ----------------------------------------------------------
        area_desc   = ''
        polygon_wkt = ''

        # Find <area> element (try with and without namespace)
        area = None
        for prefix, uri in full_ns.items():
            area = info.find(f'{{{uri}}}area')
            if area is not None:
                break
        if area is None:
            area = info.find('area')

        if area is not None:
            area_desc = find_text(area, 'areaDesc', full_ns)

            # Extract polygon coordinates
            polygon_str = find_text(area, 'polygon', full_ns)
            if polygon_str:
                coords = parse_polygon_string(polygon_str)
                if coords:
                    polygon_wkt = coords_to_wkt(coords)

            # Some CAP feeds use <circle> instead of <polygon>
            # We convert circle to a bounding box polygon
            if not polygon_wkt:
                circle_str = find_text(area, 'circle', full_ns)
                if circle_str:
                    polygon_wkt = circle_to_bbox_polygon(circle_str)

        # ----------------------------------------------------------
        #  Step 7: Validate critical fields
        # ----------------------------------------------------------
        #  We need at minimum: event, severity, and a polygon.
        #  Without these the alert is useless for our system.
        # ----------------------------------------------------------
        if not event:
            print(f"⚠️  No event field in CAP alert {identifier}")
            return None

        if not polygon_wkt:
            print(f"⚠️  No polygon in CAP alert {identifier} — skipping")
            return None

        # ----------------------------------------------------------
        #  Step 8: Build and return the final dict
        # ----------------------------------------------------------
        return {
            'id':               identifier,
            'event':            event,
            'severity':         severity    or 'Unknown',
            'urgency':          urgency     or 'Unknown',
            'description':      description or '',
            'instruction':      instruction or '',
            'onset':            onset       or sent or '',
            'expires':          expires     or '',
            'source':           sender      or 'Unknown',
            'area_desc':        area_desc   or '',
            'hazard_category':  get_hazard_category(event),
            'polygon_wkt':      polygon_wkt,
            # plain_text is None here — filled by Claude API in B9
            'plain_text':       None,
            'plain_text_language': 'en',
            # accuracy_percent is None here — computed by B8
            'accuracy_percent': None,
        }

    except etree.XMLSyntaxError as e:
        print(f"❌ Invalid XML: {e}")
        return None
    except Exception as e:
        print(f"❌ Unexpected error parsing CAP XML: {e}")
        return None


def circle_to_bbox_polygon(circle_str: str) -> str:
    """
    Converts a CAP <circle> element to an approximate
    bounding box polygon for PostGIS.

    CAP circle format: "lat,lon radius"
    Example: "-23.8,30.5 50" (50km radius)

    Some alerts use circles instead of polygons —
    we convert to a square bounding box as an approximation.
    """
    try:
        parts = circle_str.strip().split()
        if len(parts) < 2:
            return ''

        lat_lon = parts[0].split(',')
        lat = float(lat_lon[0])
        lon = float(lat_lon[1])
        radius_km = float(parts[1])

        # Approximate degrees per km
        # 1 degree latitude ≈ 111km everywhere
        # 1 degree longitude ≈ 111km * cos(latitude)
        import math
        lat_offset = radius_km / 111.0
        lon_offset = radius_km / (111.0 * math.cos(math.radians(lat)))

        # Build bounding box
        min_lat = lat - lat_offset
        max_lat = lat + lat_offset
        min_lon = lon - lon_offset
        max_lon = lon + lon_offset

        return (
            f'POLYGON(('
            f'{min_lon} {min_lat}, '
            f'{max_lon} {min_lat}, '
            f'{max_lon} {max_lat}, '
            f'{min_lon} {max_lat}, '
            f'{min_lon} {min_lat}'
            f'))'
        )
    except Exception:
        return ''


# ============================================================
#  Test function — run this file directly to test the parser
# ============================================================
#  Run from your MHEWS folder:
#    docker exec -it mhews-app-1 python gis/cap_parser.py
# ============================================================
if __name__ == '__main__':

    # A sample SAWS-style CAP XML alert for testing
    # This follows the official CAP 1.2 standard
    SAMPLE_CAP_XML = """<?xml version="1.0" encoding="UTF-8"?>
<alert xmlns="urn:oasis:names:tc:emergency:cap:1.2">
  <identifier>SAWS-20260609-THU-TEST</identifier>
  <sender>noreply@weathersa.co.za</sender>
  <sent>2026-06-09T10:00:00+02:00</sent>
  <status>Actual</status>
  <msgType>Alert</msgType>
  <scope>Public</scope>
  <info>
    <language>en-ZA</language>
    <category>Met</category>
    <event>Severe Thunderstorm Warning</event>
    <urgency>Expected</urgency>
    <severity>Severe</severity>
    <certainty>Likely</certainty>
    <onset>2026-06-09T14:00:00+02:00</onset>
    <expires>2026-06-09T22:00:00+02:00</expires>
    <description>Heavy rainfall and strong winds expected in Tzaneen and Mopani districts. Rainfall accumulations of 30-50mm possible.</description>
    <instruction>Stay indoors, avoid rivers and low-lying areas, and keep an eye on moving water.</instruction>
    <area>
      <areaDesc>Tzaneen and Mopani districts, Limpopo</areaDesc>
      <polygon>-23.4,30.0 -23.4,31.2 -24.2,31.2 -24.2,30.0 -23.4,30.0</polygon>
    </area>
  </info>
</alert>"""

    print("Testing CAP XML parser...")
    print("-" * 50)

    result = parse_cap_xml(SAMPLE_CAP_XML)

    if result:
        print("✅ Parser SUCCESS — fields extracted:")
        for key, value in result.items():
            # Truncate long values for display
            display = str(value)[:80] + '...' if len(str(value)) > 80 else str(value)
            print(f"  {key:25} = {display}")
    else:
        print("❌ Parser FAILED — check errors above")
