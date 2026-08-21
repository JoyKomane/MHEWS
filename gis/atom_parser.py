# gis/parsers/atom_parser.py
import xml.etree.ElementTree as ET
from gis.models import create_standard_alert
from datetime import datetime

def parse_atom(content: bytes, source_url: str, country: str) -> list:
    alerts = []
    root = ET.fromstring(content)
    ns = {'atom': 'http://www.w3.org/2005/Atom', 'cap': 'urn:oasis:names:tc:emergency:cap:1.2'}
    
    for entry in root.findall('.//atom:entry', ns) or root.findall('.//entry'):
        def get_text(tag, namespace='atom'):
            elem = entry.find(f'{namespace}:{tag}', ns) or entry.find(tag)
            return elem.text.strip() if elem is not None and elem.text else ""

        identifier = get_text('id') or get_text('identifier', 'cap')
        if not identifier: continue

        alerts.append(create_standard_alert(
            identifier=identifier, sender=get_text('author') or get_text('sender', 'cap'),
            event=get_text('title'), headline=get_text('title'),
            description=get_text('summary') or get_text('description', 'cap'),
            instruction=get_text('instruction', 'cap'), severity=get_text('severity', 'cap'),
            urgency=get_text('urgency', 'cap'), certainty=get_text('certainty', 'cap'),
            effective=get_text('published') or get_text('effective', 'cap'),
            expires=get_text('expires', 'cap'), language=get_text('language', 'cap') or 'en',
            polygon=None, # Atom often lacks polygon, can be extended if needed
            area=get_text('areaDesc', 'cap') or "", country=country, source_url=source_url
        ))
    return alerts