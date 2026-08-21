# ============================================================
#  MHEWS — gis/cap_parser.py (SCHEMA-ALIGNED FINAL VERSION)
# ============================================================

from lxml import etree
import hashlib
import math
from datetime import datetime, timezone

CAP_NAMESPACES = {
    'cap':  'urn:oasis:names:tc:emergency:cap:1.2',
    'cap10': 'urn:oasis:names:tc:emergency:cap:1.0',
    'cap11': 'urn:oasis:names:tc:emergency:cap:1.1',
}

HAZARD_CATEGORIES = {
    'thunderstorm': 'meteorological', 'wind': 'meteorological', 'tornado': 'meteorological',
    'cyclone': 'meteorological', 'hurricane': 'meteorological', 'hail': 'meteorological',
    'snow': 'meteorological', 'blizzard': 'meteorological', 'fog': 'meteorological',
    'heat': 'meteorological', 'cold': 'meteorological', 'frost': 'meteorological',
    'flood': 'hydrological', 'flash flood': 'hydrological', 'storm surge': 'hydrological',
    'tsunami': 'hydrological', 'earthquake': 'geophysical', 'volcano': 'geophysical',
    'landslide': 'geophysical', 'fire': 'fire', 'wildfire': 'fire', 'drought': 'drought',
}

def get_hazard_category(event_text: str) -> str:
    if not event_text: return 'other'
    event_lower = event_text.lower()
    for keyword, category in HAZARD_CATEGORIES.items():
        if keyword in event_lower: return category
    return 'other'

def find_text(element, tag: str, namespaces: dict) -> str:
    for prefix in ['cap', 'cap10', 'cap11']:
        ns = namespaces.get(prefix)
        if ns:
            result = element.find(f'{{{ns}}}{tag}')
            if result is not None and result.text: return result.text.strip()
    result = element.find(tag)
    if result is not None and result.text: return result.text.strip()
    return ''

def parse_datetime(dt_str: str) -> datetime | None:
    """Parses ISO 8601 string into a timezone-aware datetime object."""
    if not dt_str:
        return None
    try:
        if dt_str.endswith('Z'):
            dt_str = dt_str[:-1] + '+00:00'
        return datetime.fromisoformat(dt_str)
    except Exception:
        return None

def parse_polygon_string(polygon_str: str) -> list:
    if not polygon_str: return []
    try:
        coords = []
        for pair in polygon_str.strip().split():
            parts = pair.split(',')
            if len(parts) >= 2:
                coords.append([float(parts[0]), float(parts[1])])
        if len(coords) < 3: return []
        if coords[0] != coords[-1]: coords.append(coords[0])
        return coords
    except (ValueError, IndexError):
        return []

def coords_to_wkt(coords: list) -> str:
    if not coords: return ''
    wkt_coords = ', '.join(f'{lon} {lat}' for lat, lon in coords)
    return f'POLYGON(({wkt_coords}))'

def circle_to_bbox_polygon(circle_str: str) -> str:
    try:
        parts = circle_str.strip().split()
        if len(parts) < 2: return ''
        lat, lon = map(float, parts[0].split(','))
        radius_km = float(parts[1])
        lat_offset = radius_km / 111.0
        lon_offset = radius_km / (111.0 * math.cos(math.radians(abs(lat))))
        return f'POLYGON(({lon-lon_offset} {lat-lat_offset}, {lon+lon_offset} {lat-lat_offset}, {lon+lon_offset} {lat+lat_offset}, {lon-lon_offset} {lat+lat_offset}, {lon-lon_offset} {lat-lat_offset}))'
    except Exception:
        return ''

def parse_cap_xml(xml_bytes: bytes) -> dict | None:
    try:
        parser = etree.XMLParser(recover=True, no_network=True)
        root = etree.fromstring(xml_bytes, parser)
        if root is None: return None

        ns = {}
        for prefix, uri in root.nsmap.items():
            if 'emergency:cap' in uri or 'cap' in uri:
                ns = {'cap': uri}
                break
        full_ns = {**CAP_NAMESPACES, **ns}

        # 1. Try to find standard CAP fields
        identifier = find_text(root, 'identifier', full_ns)
        sender = find_text(root, 'sender', full_ns)
        sent = find_text(root, 'sent', full_ns)

        # Fallback for Atom feeds: use <id>, <author>, <updated>
        if not identifier: identifier = find_text(root, 'id', full_ns)
        if not sender: sender = find_text(root, 'name', full_ns)
        if not sent: sent = find_text(root, 'updated', full_ns) or find_text(root, 'published', full_ns)

        if not identifier:
            identifier = hashlib.md5(f"{sender}{sent}".encode()).hexdigest()[:16]

        # 2. Find the <info> block (Standard CAP)
        info = None
        for prefix, uri in full_ns.items():
            infos = root.findall(f'{{{uri}}}info')
            if infos:
                for i in infos:
                    if 'en' in find_text(i, 'language', full_ns).lower():
                        info = i
                        break
                if info is None: info = infos[0]
                break

        # 3. If no <info> block, use a flat Atom entry as the info block.
        if info is None:
            infos = root.findall('info')
            info = infos[0] if infos else root

        if info is None: return None

        # 4. Extract event (standard CAP, then Atom title)
        event = find_text(info, 'event', full_ns)
        if not event:
            event = find_text(root, 'title', full_ns)
        if not event: return None

        area_desc, polygon_wkt = '', ''
        area = None
        for prefix in ['cap', 'cap10', 'cap11', '']:
            uri = full_ns.get(prefix, '')
            try:
                area = info.find(f'{{{uri}}}area') if uri else info.find('area')
                if area is not None:
                    break
            except Exception:
                continue

        if area is not None:
            area_desc = find_text(area, 'areaDesc', full_ns)
            polygon_str = find_text(area, 'polygon', full_ns)

            if polygon_str:
                coords = parse_polygon_string(polygon_str)
                if coords: polygon_wkt = coords_to_wkt(coords)

            if not polygon_wkt:
                circle_str = find_text(area, 'circle', full_ns)
                if circle_str: polygon_wkt = circle_to_bbox_polygon(circle_str)

        # --- SEVERITY EXTRACTION WITH FALLBACK ---
        raw_severity = find_text(info, 'severity', full_ns)

        # If it is missing, empty, or literally says "Unknown", guess from the event title
        if not raw_severity or raw_severity == 'Unknown' or raw_severity == '':
            event_lower = event.lower()
            if 'red' in event_lower or 'extreme' in event_lower:
                raw_severity = 'Extreme'
            elif 'orange' in event_lower or 'severe' in event_lower:
                raw_severity = 'Severe'
            elif 'yellow' in event_lower or 'moderate' in event_lower:
                raw_severity = 'Moderate'
            elif 'green' in event_lower or 'minor' in event_lower:
                raw_severity = 'Minor'
            else:
                raw_severity = 'Moderate'  # Safe default

        return {
            'identifier': identifier,
            'event': event,
            'severity': raw_severity,
            'urgency': find_text(info, 'urgency', full_ns) or 'Unknown',
            'description': find_text(info, 'description', full_ns) or find_text(root, 'summary', full_ns),
            'instruction': find_text(info, 'instruction', full_ns),
            'effective': parse_datetime(find_text(info, 'onset', full_ns) or sent),
            'expires': parse_datetime(find_text(info, 'expires', full_ns)),
            'sender': sender or 'Unknown',
            'area': area_desc,
            'hazard_category': get_hazard_category(event),
            'polygon': polygon_wkt,
            'polygon_wkt': polygon_wkt,
            'plain_text': None,
            'plain_text_language': 'en',
            'accuracy_percent': None,
        }
    except Exception as e:
        return None

def parse_feed(xml_bytes: bytes, feed_url: str, country: str) -> list:
    alerts = []
    try:
        parser = etree.XMLParser(recover=True, no_network=True)
        root = etree.fromstring(xml_bytes, parser)
        if root is None:
            return []

        ns = {'atom': 'http://www.w3.org/2005/Atom', 'cap': 'urn:oasis:names:tc:emergency:cap:1.2'}
        entries = root.findall('.//atom:entry', ns) or root.findall('.//{*}entry') or root.findall('.//entry') or []
        
        for entry in entries:
            cap_alert = entry.find('.//cap:alert', ns) or entry.find('.//{*}alert') or entry.find('.//alert')
            
            if cap_alert is not None:
                alert_xml = etree.tostring(cap_alert, encoding='utf-8')
                parsed = parse_cap_xml(alert_xml)
            else:
                entry_xml = etree.tostring(entry, encoding='utf-8')
                parsed = parse_cap_xml(entry_xml)
                
            if parsed:
                parsed['feed_url'] = feed_url
                parsed['country'] = country
                alerts.append(parsed)
        
        if not entries:
            raw_alerts = root.findall('.//{*}alert') or root.findall('.//alert')
            for alert in raw_alerts:
                alert_xml = etree.tostring(alert, encoding='utf-8')
                parsed = parse_cap_xml(alert_xml)
                if parsed:
                    parsed['feed_url'] = feed_url
                    parsed['country'] = country
                    alerts.append(parsed)
            
            if not raw_alerts:
                parsed = parse_cap_xml(xml_bytes)
                if parsed:
                    parsed['feed_url'] = feed_url
                    parsed['country'] = country
                    alerts.append(parsed)
                
    except Exception:
        pass
        
    return alerts