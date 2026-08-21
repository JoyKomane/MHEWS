# ============================================================
#  MHEWS — backend/alerts.py
#  FINAL VERSION: Kills zombies, parses polygons correctly
# ============================================================

from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel
from typing import Optional
import json

from backend.main import database

router = APIRouter(
    prefix="/alerts",
    tags=["Alerts"]
)

@router.get("", summary="Get all active alerts")
async def get_alerts(country: Optional[str] = Query(None)):
    """
    Returns ONLY alerts that:
    1. Haven't expired yet
    2. Were seen in the last 24 hours
    3. Started in the last 3 days (Kills old zombie onsets)
    """
    
    # THE ANTI-ZOMBIE QUERY
    query = """
        SELECT
            id, event, severity, urgency, description, instruction,
            source, area_desc, hazard_category, onset, expires,
            plain_text, accuracy_percent,
            ST_AsGeoJSON(polygon)::json AS polygon
        FROM alerts
        WHERE 
            (expires IS NULL OR expires > NOW())
            AND (last_seen_at > NOW() - INTERVAL '24 hours')
            AND (onset > NOW() - INTERVAL '3 days')
    """
    
    values = {}
    if country:
        query += " AND (area_desc ILIKE :country OR source ILIKE :country)"
        values = {"country": f"%{country}%"}
        
    query += " ORDER BY last_seen_at DESC"

    try:
        rows = await database.fetch_all(query, values=values)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

    alerts_list = []
    for row in rows:
        # Parse polygon from JSON string to JSON object
        polygon = row["polygon"]
        if polygon is None:
            polygon_data = None
        elif isinstance(polygon, str):
            try:
                polygon_data = json.loads(polygon)
            except json.JSONDecodeError:
                polygon_data = None
        else:
            polygon_data = polygon

        alerts_list.append({
            "id": row["id"], 
            "event": row["event"], 
            "severity": row["severity"] or "Unknown",
            "urgency": row["urgency"] or "Unknown", 
            "description": row["description"] or "",
            "instruction": row["instruction"] or "", 
            "source": row["source"] or "Unknown",
            "area_desc": row["area_desc"] or "", 
            "hazard_category": row["hazard_category"] or "other",
            "onset": row["onset"].isoformat() if row["onset"] else None,
            "expires": row["expires"].isoformat() if row["expires"] else None,
            "plain_text": row["plain_text"] or "", 
            "accuracy_percent": row["accuracy_percent"],
            "polygon": polygon_data
        })

    print(f" Returning {len(alerts_list)} fresh alerts (zombies filtered out)")
    return {"alerts": alerts_list}


# ============================================================
#  POST /alerts/check
# ============================================================

class LocationCheck(BaseModel):
    lat: float
    lon: float

@router.post("/check", summary="Check if location is in hazard zone")
async def check_location(location: LocationCheck):
    query = """
        SELECT id, event, severity, area_desc, plain_text, hazard_category, expires
        FROM alerts
        WHERE 
            (expires IS NULL OR expires > NOW())
            AND (last_seen_at > NOW() - INTERVAL '24 hours')
            AND ST_Contains(polygon, ST_SetSRID(ST_Point(:lon, :lat), 4326))
    """
    
    try:
        rows = await database.fetch_all(
            query,
            values={"lat": location.lat, "lon": location.lon}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

    matching_alerts = []
    for row in rows:
        matching_alerts.append({
            "id": row["id"], "event": row["event"], "severity": row["severity"],
            "area_desc": row["area_desc"], "plain_text": row["plain_text"],
            "hazard_category": row["hazard_category"],
            "expires": row["expires"].isoformat() if row["expires"] else None,
        })

    return {
        "lat": location.lat, "lon": location.lon,
        "inside": len(matching_alerts) > 0,
        "alert_count": len(matching_alerts),
        "matching_alerts": matching_alerts,
        "message": (
            f"You are inside {len(matching_alerts)} active hazard zone(s)."
            if matching_alerts
            else "You are outside all current hazard zones."
        )
    }