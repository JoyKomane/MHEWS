# gis/models.py
from datetime import datetime
from typing import Optional, Dict, Any


def _infer_hazard_category(event: str) -> str:
    if not event:
        return "other"

    ev = event.lower()
    if any(keyword in ev for keyword in ["fire", "wildfire", "burn"]):
        return "fire"
    if any(keyword in ev for keyword in ["flood", "storm", "surge", "rain"]):
        return "hydrological"
    if any(keyword in ev for keyword in ["wind", "tornado", "hurricane", "cyclone"]):
        return "meteorological"
    if any(keyword in ev for keyword in ["quake", "volcano", "tsunami", "earthquake"]):
        return "geophysical"
    if any(keyword in ev for keyword in ["drought", "heat"]):
        return "drought"
    return "other"


def create_standard_alert(
    identifier: str,
    sender: str,
    event: str,
    headline: str,
    description: str,
    instruction: str,
    severity: str,
    urgency: str,
    certainty: str,
    effective: Optional[datetime | str],
    expires: Optional[datetime | str],
    language: str,
    polygon: Optional[str],
    area: str,
    country: str,
    source_url: str,
) -> Dict[str, Any]:
    return {
        "identifier": identifier or "UNKNOWN_ID",
        "sender": sender or "Unknown",
        "event": event or "Unknown Event",
        "headline": headline or event or "Unknown",
        "description": description or "",
        "instruction": instruction or "",
        "severity": severity or "Unknown",
        "urgency": urgency or "Unknown",
        "certainty": certainty or "Unknown",
        "effective": effective,
        "expires": expires,
        "language": language or "en",
        "polygon": polygon,
        "area": area or "",
        "country": country or "Unknown",
        "source_url": source_url,
        "hazard_category": _infer_hazard_category(event),
    }