import httpx
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

def get_france_live_alerts():
    url = "https://feeds.meteoalarm.org/feeds/meteoalarm-legacy-atom-france/"
    print(f"Fetching live alerts for France from: {url}\n")
    
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(url)
            resp.raise_for_status()
            
        # Parse the XML
        root = ET.fromstring(resp.content)
        
        # Namespaces used in Atom + CAP feeds
        ns = {
            'atom': 'http://www.w3.org/2005/Atom',
            'cap': 'urn:oasis:names:tc:emergency:cap:1.2'
        }
        
        now = datetime.now(timezone.utc)
        live_count = 0
        
        # Look for every entry (alert) in the feed
        for entry in root.findall('atom:entry', ns):
            event = entry.find('cap:event', ns)
            expires = entry.find('cap:expires', ns)
            area = entry.find('cap:areaDesc', ns)
            
            if event is None: continue
            
            event_name = event.text.strip()
            area_name = area.text.strip() if area is not None else "Unknown Area"
            
            # THE CRITICAL FILTER: Check if it's expired
            if expires is not None and expires.text:
                # Parse the expiry time (handling different formats)
                exp_str = expires.text.strip()
                try:
                    # Handle Zulu time format
                    if exp_str.endswith('Z'):
                        exp_str = exp_str[:-1] + '+00:00'
                    exp_time = datetime.fromisoformat(exp_str)
                    
                    # If it has a timezone, make it UTC. If not, assume UTC.
                    if exp_time.tzinfo is None:
                        exp_time = exp_time.replace(tzinfo=timezone.utc)
                        
                    # ONLY PRINT IF IT HAS NOT EXPIRED YET
                    if exp_time > now:
                        print(f"✅ LIVE: {event_name} in {area_name} (Expires: {exp_time})")
                        live_count += 1
                except Exception:
                    pass # Skip if date parsing fails
                    
        print(f"\n🇫🇷 Total active alerts in France right now: {live_count}")
        
    except Exception as e:
        print(f"Error fetching feed: {e}")

if __name__ == "__main__":
    get_france_live_alerts()