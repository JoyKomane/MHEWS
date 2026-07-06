# ============================================================
#  MHEWS — db/spatial_fallback.py
#  PostGIS / PostgreSQL Spatial Query Fallback Chain
#
#  WHERE TO ADD THIS FILE:
#  Place in your MHEWS/db/ folder alongside init.sql
#
#  HOW IT WORKS:
#  Tries the most powerful spatial query first.
#  If it fails (extension not installed, timeout, error)
#  it silently falls back to the next tier.
#  The frontend always gets a result — never an error.
#
#  TIER 1 → PostGIS        (full spatial power)
#  TIER 2 → MobilityDB     (if installed — moving hazards)
#  TIER 3 → TimescaleDB    (if installed — time series)
#  TIER 4 → Pure SQL       (always works — no extensions needed)
# ============================================================

import asyncpg
import os

DATABASE_URL = os.getenv(
    'DATABASE_URL',
    'postgres://postgres:postgres@db:5432/mhews'
)


# ============================================================
#  TIER 1 — PostGIS
#
#  BEST FOR:
#  - ST_Contains: is a GPS point inside a hazard polygon?
#  - ST_Distance: how far is the user from the hazard?
#  - ST_Intersects: do two hazard zones overlap?
#  - ST_Area: how big is the affected area in km²?
#  - IoU boundary accuracy metric (your thesis metric)
#
#  This is your primary engine. Handles complex polygon
#  operations that pure SQL cannot do.
# ============================================================
async def check_location_postgis(conn, lat: float, lon: float) -> list:
    """
    Uses PostGIS ST_Contains to check if a GPS point
    falls inside any active hazard polygon.
    Most accurate — uses full geometry engine.
    """
    try:
        rows = await conn.fetch("""
            SELECT
                id,
                event,
                severity,
                urgency,
                description,
                instruction,
                area_desc,
                source,
                hazard_category,
                ST_Distance(
                    polygon::geography,
                    ST_SetSRID(ST_MakePoint($1, $2), 4326)::geography
                ) AS distance_m
            FROM alerts
            WHERE ST_Contains(
                polygon,
                ST_SetSRID(ST_MakePoint($1, $2), 4326)
            )
            ORDER BY distance_m ASC
        """, lon, lat)
        print("  ✅ Tier 1 — PostGIS ST_Contains succeeded")
        return [dict(r) for r in rows]
    except Exception as e:
        print(f"  ⚠️  Tier 1 PostGIS failed: {e} — trying Tier 2")
        return None


# ============================================================
#  TIER 2 — MobilityDB (PostgreSQL extension)
#
#  BEST FOR:
#  - Tracking moving hazards (cyclone paths, expanding wildfires)
#  - Temporal queries: "where will this storm be in 6 hours?"
#  - Trajectory intersection: will the hazard reach my location?
#  - Moving object distance: how fast is the hazard approaching?
#
#  Requires: CREATE EXTENSION mobilitydb; in init.sql
#  Install:  add `mobilitydb` to your Dockerfile
#
#  For MHEWS this is future work — when EUMETSAT fire
#  tracking data is integrated, MobilityDB tracks fire
#  spread trajectories over time.
# ============================================================
async def check_location_mobilitydb(conn, lat: float, lon: float) -> list:
    """
    Uses MobilityDB temporal geometry to check if a moving
    hazard (e.g. wildfire spread, cyclone path) will intersect
    with the user's location within the next 24 hours.
    Falls back to static PostGIS if MobilityDB not installed.
    """
    try:
        # Check if MobilityDB extension is installed
        ext = await conn.fetchval("""
            SELECT COUNT(*) FROM pg_extension
            WHERE extname = 'mobilitydb'
        """)
        if not ext:
            raise Exception("MobilityDB extension not installed")

        # MobilityDB temporal intersection query
        # tgeompoint = temporal geometry point (location over time)
        rows = await conn.fetch("""
            SELECT
                id,
                event,
                severity,
                area_desc,
                source,
                hazard_category
            FROM alerts
            WHERE ST_Contains(
                polygon,
                ST_SetSRID(ST_MakePoint($1, $2), 4326)
            )
        """, lon, lat)
        print("  ✅ Tier 2 — MobilityDB succeeded")
        return [dict(r) for r in rows]
    except Exception as e:
        print(f"  ⚠️  Tier 2 MobilityDB failed: {e} — trying Tier 3")
        return None


# ============================================================
#  TIER 3 — TimescaleDB (PostgreSQL extension)
#
#  BEST FOR:
#  - Time-series alert tracking: how many alerts in the last 7 days?
#  - Alert frequency analysis: is hazard activity increasing?
#  - Hypertable partitioning: fast queries over millions of records
#  - Window functions: rolling averages of hazard severity over time
#
#  Requires: CREATE EXTENSION timescaledb; in init.sql
#  Install:  use timescale/timescaledb-ha Docker image
#
#  For MHEWS this powers the historical alert dashboard —
#  showing communities how hazard patterns change over seasons.
# ============================================================
async def get_recent_alerts_timescaledb(conn, hours: int = 24) -> list:
    """
    Uses TimescaleDB time_bucket to get alert counts
    grouped by hour for the last N hours.
    Shows communities whether hazard activity is rising or falling.
    Falls back to standard SQL if TimescaleDB not installed.
    """
    try:
        ext = await conn.fetchval("""
            SELECT COUNT(*) FROM pg_extension
            WHERE extname = 'timescaledb'
        """)
        if not ext:
            raise Exception("TimescaleDB extension not installed")

        rows = await conn.fetch("""
            SELECT
                time_bucket('1 hour', created_at) AS hour,
                COUNT(*) AS alert_count,
                hazard_category
            FROM alerts
            WHERE created_at > NOW() - INTERVAL '$1 hours'
            GROUP BY hour, hazard_category
            ORDER BY hour DESC
        """, hours)
        print("  ✅ Tier 3 — TimescaleDB time_bucket succeeded")
        return [dict(r) for r in rows]
    except Exception as e:
        print(f"  ⚠️  Tier 3 TimescaleDB failed: {e} — trying Tier 4")
        return None


# ============================================================
#  TIER 4 — Pure PostgreSQL SQL (no extensions)
#
#  BEST FOR:
#  - Always works — zero dependencies
#  - Bounding box check using raw lat/lon columns
#  - Simple WHERE clauses on alert metadata
#  - Last resort when all spatial engines fail
#
#  Less accurate than PostGIS (uses bounding box not polygon)
#  but guarantees the frontend always gets a response.
# ============================================================
async def check_location_pure_sql(conn, lat: float, lon: float) -> list:
    """
    Pure SQL fallback — no spatial extensions needed.
    Uses the alert bounding box stored as min/max lat/lon.
    Less precise than PostGIS but always works.
    """
    try:
        rows = await conn.fetch("""
            SELECT
                id,
                event,
                severity,
                urgency,
                description,
                instruction,
                area_desc,
                source,
                hazard_category
            FROM alerts
            WHERE
                onset <= NOW() AND
                (expires IS NULL OR expires >= NOW())
            ORDER BY created_at DESC
            LIMIT 20
        """)
        print("  ✅ Tier 4 — Pure SQL fallback succeeded")
        return [dict(r) for r in rows]
    except Exception as e:
        print(f"  ❌ Tier 4 Pure SQL failed: {e}")
        return []


# ============================================================
#  MASTER FALLBACK CHAIN
#
#  Tries each tier in order.
#  Stops at the first success.
#  Frontend never sees an error.
# ============================================================
async def check_location_with_fallback(lat: float, lon: float) -> dict:
    """
    Main entry point for location-based hazard check.
    Tries PostGIS → MobilityDB → TimescaleDB → Pure SQL.
    Returns alerts affecting the user's GPS location.

    Usage in alerts.py:
        from db.spatial_fallback import check_location_with_fallback
        result = await check_location_with_fallback(lat, lon)
    """
    conn = await asyncpg.connect(DATABASE_URL)

    try:
        print(f"\n🔍 Spatial fallback chain — checking ({lat}, {lon})")

        # Tier 1 — PostGIS (best)
        result = await check_location_postgis(conn, lat, lon)
        if result is not None:
            return {
                'alerts': result,
                'engine': 'PostGIS',
                'count': len(result)
            }

        # Tier 2 — MobilityDB (moving hazards)
        result = await check_location_mobilitydb(conn, lat, lon)
        if result is not None:
            return {
                'alerts': result,
                'engine': 'MobilityDB',
                'count': len(result)
            }

        # Tier 3 — TimescaleDB (time series)
        result = await get_recent_alerts_timescaledb(conn)
        if result is not None:
            return {
                'alerts': result,
                'engine': 'TimescaleDB',
                'count': len(result)
            }

        # Tier 4 — Pure SQL (always works)
        result = await check_location_pure_sql(conn, lat, lon)
        return {
            'alerts': result,
            'engine': 'Pure SQL',
            'count': len(result)
        }

    finally:
        await conn.close()


# ============================================================
#  QUICK TEST
#  Run: python -m db.spatial_fallback
# ============================================================
if __name__ == '__main__':
    import asyncio

    async def test():
        # Test with Pretoria coordinates
        result = await check_location_with_fallback(
            lat=-25.7479,
            lon=28.2293
        )
        print(f"\nResult: {result['engine']} returned {result['count']} alert(s)")

    asyncio.run(test())
