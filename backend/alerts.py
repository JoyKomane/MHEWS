# ============================================================
#  MHEWS — backend/alerts.py
#  B5: GET /alerts endpoint
#  B6: POST /alerts/check endpoint
#
#  This file contains the two most important endpoints:
#
#  B5 — GET /alerts
#    Queries PostGIS for all active (non-expired) alerts
#    and returns them as GeoJSON. This replaces the hardcoded
#    alertQueue JavaScript array in your frontend.
#
#  B6 — POST /alerts/check
#    Takes a lat/lon from the user's GPS, runs a real
#    spatial query in PostGIS using ST_Contains, and returns
#    which alerts (if any) contain that point.
#    This replaces the client-side pointInPolygon() JS function.
# ============================================================

# --- FastAPI imports ---
from fastapi import APIRouter, HTTPException

# --- Pydantic for request/response data models ---
from pydantic import BaseModel

# --- Standard library ---
from datetime import datetime, timezone
from typing import Optional
import json

# --- Import the database connection from main.py ---
# We use the same connection pool created in main.py
from backend.main import database

# ============================================================
#  Create a router
# ============================================================
#  Instead of adding routes directly to app in main.py,
#  we use a router here and register it in main.py.
#  This keeps the code organised as the project grows.
#  Think of it as a mini-app for alert-related endpoints.
# ============================================================
router = APIRouter(
    prefix="/alerts",   # All endpoints here start with /alerts
    tags=["Alerts"]     # Groups them together in /docs
)

# ============================================================
#  B5 — GET /alerts
# ============================================================
#  Returns all currently active alerts from PostGIS.
#
#  "Active" means: expires > right now (UTC).
#  Expired alerts are still in the database but not returned.
#
#  The polygon is returned as GeoJSON so Leaflet can draw it
#  directly on the map without any conversion.
#
#  Test it:
#    curl http://localhost:8000/alerts
#    or open http://localhost:8000/docs and try it there
# ============================================================

@router.get("/", summary="Get all active alerts")
async def get_alerts():
    """
    Returns all non-expired alerts from PostGIS as GeoJSON.
    The frontend calls this on page load to populate the map.
    """

    # ----------------------------------------------------------
    #  The SQL query
    # ----------------------------------------------------------
    #  ST_AsGeoJSON(polygon) converts the PostGIS geometry
    #  into a GeoJSON string that Leaflet understands.
    #
    #  We filter by expires > NOW() to only return active alerts.
    #  NOW() in PostgreSQL returns the current UTC timestamp.
    #
    #  ORDER BY onset DESC puts the most recent alert first.
    # ----------------------------------------------------------
    query = """
        SELECT
            id,
            event,
            severity,
            urgency,
            description,
            instruction,
            onset,
            expires,
            source,
            area_desc,
            plain_text,
            plain_text_language,
            accuracy_percent,
            hazard_category,
            ST_AsGeoJSON(polygon) AS polygon_geojson
        FROM alerts
        WHERE expires > NOW()
        ORDER BY onset DESC
    """

    # Execute the query asynchronously.
    # fetch_all returns a list of rows (like a list of dicts).
    rows = await database.fetch_all(query)

    # ----------------------------------------------------------
    #  Build the response
    # ----------------------------------------------------------
    #  We format each row as a clean Python dict.
    #  The frontend expects the same fields that were previously
    #  hardcoded in the alertQueue JavaScript array.
    #
    #  polygon_geojson is a JSON string from PostGIS —
    #  we parse it into a real dict so the response is proper
    #  nested JSON, not a string-inside-JSON.
    # ----------------------------------------------------------
    alerts = []
    for row in rows:

        # Parse the GeoJSON string into a Python dict.
        # json.loads() converts a JSON string to a Python dict.
        # If polygon is somehow null, we use None safely.
        polygon_geojson = json.loads(row["polygon_geojson"]) if row["polygon_geojson"] else None

        alerts.append({
            "id":                   row["id"],
            "event":                row["event"],
            "severity":             row["severity"],
            "urgency":              row["urgency"],
            "description":          row["description"],
            "instruction":          row["instruction"],

            # Convert timestamps to ISO 8601 strings.
            # isoformat() gives "2024-05-25T14:00:00+00:00"
            # The frontend's formatDate() function handles this.
            "onset":                row["onset"].isoformat() if row["onset"] else None,
            "expires":              row["expires"].isoformat() if row["expires"] else None,

            "source":               row["source"],
            "area_desc":            row["area_desc"],
            "plain_text":           row["plain_text"],
            "plain_text_language":  row["plain_text_language"],
            "accuracy_percent":     row["accuracy_percent"],
            "hazard_category":      row["hazard_category"],

            # The polygon as a GeoJSON geometry object.
            # Type will be "Polygon" with a "coordinates" array.
            # Leaflet's L.geoJSON() can render this directly.
            "polygon":              polygon_geojson,
        })

    # Return the list of alerts.
    # FastAPI automatically converts this to a JSON response.
    return {
        "count":  len(alerts),
        "alerts": alerts
    }


# ============================================================
#  B6 — POST /alerts/check
# ============================================================
#  Takes a GPS coordinate and checks which active alerts
#  contain that point using PostGIS ST_Contains.
#
#  Why do this on the server instead of the browser?
#  1. PostGIS ST_Contains is more accurate than our JS version
#  2. The spatial index (GIST) makes it extremely fast
#  3. The browser doesn't need to download all polygon data
#
#  Request body (JSON):
#    { "lat": -23.8, "lon": 30.5 }
#
#  Test it:
#    curl -X POST http://localhost:8000/alerts/check \
#      -H "Content-Type: application/json" \
#      -d '{"lat": -23.8, "lon": 30.5}'
# ============================================================

# --- Request body model ---
# Pydantic validates that lat and lon are floats.
# If the user sends a string, FastAPI returns a 422 error
# automatically — we don't need to write any validation code.
class LocationCheck(BaseModel):
    lat: float  # Latitude  e.g. -23.8 (negative = south)
    lon: float  # Longitude e.g. 30.5  (positive = east)


@router.post("/check", summary="Check if a location is inside a hazard zone")
async def check_location(location: LocationCheck):
    """
    Takes a GPS lat/lon and returns all active alerts
    whose polygon contains that point.

    Returns inside=True if the point is in any hazard zone,
    plus the list of matching alerts.
    """

    # ----------------------------------------------------------
    #  The spatial SQL query
    # ----------------------------------------------------------
    #  ST_Contains(polygon, ST_Point(lon, lat, 4326)):
    #    polygon   = the alert's geometry column
    #    ST_Point  = creates a geometry point from lon/lat
    #                NOTE: PostGIS uses lon/lat order (x, y)!
    #                      NOT lat/lon like most people expect.
    #    4326      = WGS84 coordinate system (standard GPS)
    #
    #  This query uses the GIST index automatically,
    #  so it's extremely fast even with thousands of alerts.
    #
    #  :lat and :lon are parameterised placeholders —
    #  this prevents SQL injection attacks.
    # ----------------------------------------------------------
    query = """
        SELECT
            id,
            event,
            severity,
            area_desc,
            plain_text,
            hazard_category,
            expires
        FROM alerts
        WHERE
            expires > NOW()
            AND ST_Contains(
                polygon,
                ST_SetSRID(ST_Point(:lon, :lat), 4326)
            )
        ORDER BY severity DESC
    """

    # Execute the query with the user's coordinates.
    # The :lat and :lon placeholders are replaced safely
    # by asyncpg — no SQL injection possible.
    rows = await database.fetch_all(
        query,
        values={"lat": location.lat, "lon": location.lon}
    )

    # ----------------------------------------------------------
    #  Build the response
    # ----------------------------------------------------------
    #  matching_alerts = list of alerts that contain the point
    #  inside = True if at least one alert was found
    # ----------------------------------------------------------
    matching_alerts = []
    for row in rows:
        matching_alerts.append({
            "id":               row["id"],
            "event":            row["event"],
            "severity":         row["severity"],
            "area_desc":        row["area_desc"],
            "plain_text":       row["plain_text"],
            "hazard_category":  row["hazard_category"],
            "expires":          row["expires"].isoformat() if row["expires"] else None,
        })

    # Return the result.
    # The frontend uses "inside" to show the warning message
    # and "matching_alerts" to list which hazards affect the user.
    return {
        "lat":              location.lat,
        "lon":              location.lon,
        "inside":           len(matching_alerts) > 0,
        "alert_count":      len(matching_alerts),
        "matching_alerts":  matching_alerts,

        # Human-readable message for the frontend to display
        "message": (
            f"⚠️ You are inside {len(matching_alerts)} hazard zone(s)."
            if matching_alerts
            else "✅ You are outside all current hazard zones."
        )
    }
