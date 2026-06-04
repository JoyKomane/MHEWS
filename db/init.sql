-- ============================================================
--  MHEWS — db/init.sql
--  B3: Creates the database schema and seeds mock data.
--
--  This file runs AUTOMATICALLY when the PostGIS container
--  starts for the first time. Docker looks for any .sql file
--  placed in /docker-entrypoint-initdb.d/ and runs it.
--
--  If you ever need to reset the database:
--    docker compose down -v   (the -v deletes the volume)
--    docker compose up --build
--  Docker will re-run this file on a fresh database.
-- ============================================================


-- ============================================================
--  STEP 1: Enable the PostGIS extension
-- ============================================================
--  PostGIS is not enabled by default even on a PostGIS image.
--  This adds the spatial functions (ST_Contains, ST_GeomFromText
--  etc.) and the GEOMETRY data type to our database.
--  "IF NOT EXISTS" means it won't crash if already enabled.
-- ============================================================
CREATE EXTENSION IF NOT EXISTS postgis;


-- ============================================================
--  STEP 2: Create the alerts table
-- ============================================================
--  This table stores every hazard alert MHEWS knows about.
--  Each row is one alert from one source (SAWS, GDACS, etc.)
-- ============================================================
CREATE TABLE IF NOT EXISTS alerts (

  -- Unique identifier for this alert.
  -- We use the CAP message identifier directly as the primary key
  -- so that re-ingesting the same alert never creates a duplicate.
  -- Format: SOURCE-DATE-TYPE-NUMBER e.g. SAWS-20240525-THU-001
  id TEXT PRIMARY KEY,

  -- The human-readable name of the hazard event.
  -- Comes directly from the CAP <event> field.
  -- Examples: "Severe Thunderstorm Warning", "Flash Flood Watch"
  event TEXT NOT NULL,

  -- CAP severity level. One of:
  -- Extreme | Severe | Moderate | Minor | Unknown
  severity TEXT NOT NULL,

  -- CAP urgency. One of:
  -- Immediate | Expected | Future | Past | Unknown
  urgency TEXT NOT NULL,

  -- The technical CAP description — the raw official text.
  -- This is what we send to Claude API to translate into
  -- plain language in B9.
  description TEXT NOT NULL,

  -- Action instructions from the CAP alert.
  -- e.g. "Stay indoors, avoid rivers and low-lying areas."
  instruction TEXT NOT NULL,

  -- When the hazard starts.
  -- TIMESTAMPTZ = timestamp with timezone — always stores as UTC
  -- so we can correctly convert to SAST (UTC+2) for display.
  onset TIMESTAMPTZ NOT NULL,

  -- When the alert expires.
  -- We use this to filter out old alerts in our API queries.
  expires TIMESTAMPTZ NOT NULL,

  -- Where this alert came from.
  -- Examples: "South African Weather Service", "GDACS", "USGS"
  source TEXT NOT NULL,

  -- The CAP areaDesc field — a human-readable description
  -- of the affected area. e.g. "Tzaneen and Mopani districts"
  -- This was missing from the original schema — now added.
  area_desc TEXT,

  -- The plain-language translation produced by Claude API (B9).
  -- Stored here so we don't call Claude every time someone
  -- loads the page — only generate it once when ingesting.
  plain_text TEXT,

  -- The language of the plain_text above.
  -- Defaults to English. Updated by the /translate endpoint.
  plain_text_language TEXT DEFAULT 'en',

  -- The boundary accuracy metric produced by gis/accuracy.py (B8).
  -- This is the IoU (Intersection over Union) score comparing
  -- the alert polygon to the official StatsSA admin boundary.
  -- Range: 0-100. NOT hardcoded — computed by real spatial maths.
  accuracy_percent INTEGER,

  -- The hazard category — broader than event type.
  -- Useful for filtering and for the hazard icon system in F4.
  -- Examples: "meteorological", "hydrological", "geophysical", "fire"
  hazard_category TEXT,

  -- THE SPATIAL COLUMN — the most important field in the table.
  -- GEOMETRY(Polygon, 4326) means:
  --   Polygon = the shape type (could also be MultiPolygon)
  --   4326    = the coordinate system (WGS84 = standard lat/lon)
  -- PostGIS stores this as a binary blob and can run spatial
  -- queries on it extremely fast thanks to the GIST index below.
  polygon GEOMETRY(Polygon, 4326) NOT NULL,

  -- Automatically records when this row was inserted.
  -- Useful for debugging and for knowing when data was last refreshed.
  created_at TIMESTAMPTZ DEFAULT now()

);


-- ============================================================
--  STEP 3: Create the spatial index (GIST)
-- ============================================================
--  A GIST index is a special index for spatial data.
--  Without it, "find all alerts that contain this point"
--  would scan every row in the table one by one — very slow.
--  With the GIST index, PostGIS uses a spatial tree structure
--  and the same query runs in milliseconds even with thousands
--  of alerts stored.
--
--  "IF NOT EXISTS" prevents errors on re-runs.
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_alerts_polygon
  ON alerts USING GIST(polygon);


-- ============================================================
--  STEP 4: Create an index on expires
-- ============================================================
--  We will often query: "give me all alerts that haven't
--  expired yet". An index on expires makes this fast.
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_alerts_expires
  ON alerts (expires);


-- ============================================================
--  STEP 5: Seed mock alerts
-- ============================================================
--  These are your three original mock alerts, now stored
--  in PostGIS instead of a JavaScript array.
--
--  ST_GeomFromText(wkt, srid):
--    wkt  = Well-Known Text format for a polygon.
--           POLYGON((lon lat, lon lat, ...))
--           NOTE: PostGIS uses lon/lat order (x, y), NOT lat/lon!
--    srid = 4326 = WGS84 coordinate system
--
--  ON CONFLICT DO NOTHING:
--    If this file is run twice, don't crash — just skip
--    the rows that already exist (matched by primary key id).
-- ============================================================

INSERT INTO alerts (
  id, event, severity, urgency,
  description, instruction,
  onset, expires, source,
  area_desc, plain_text, plain_text_language,
  accuracy_percent, hazard_category, polygon
)
VALUES

  -- ── Alert 1: Severe Thunderstorm ──────────────────────────
  (
    'SAWS-20240525-THU-001',
    'Severe Thunderstorm Warning',
    'Severe',
    'Expected',
    'Heavy rainfall and strong winds expected in Tzaneen and Mopani districts.',
    'Stay indoors, avoid rivers and low-lying areas, and keep an eye on moving water.',
    '2024-05-25T14:00:00+02:00',
    '2024-05-25T22:00:00+02:00',
    'South African Weather Service',
    'Tzaneen and Mopani districts, Limpopo',
    -- Plain text seeded here so the frontend works immediately.
    -- In production this will be generated by Claude API (B9).
    'Heavy rain and strong winds are expected around Tzaneen and Mopani. Stay indoors and keep away from rivers and streams.',
    'en',
    -- Accuracy seeded as NULL — the real IoU value will be
    -- computed and updated by gis/accuracy.py (B8).
    NULL,
    'meteorological',
    -- POLYGON((lon lat, lon lat, ...)) — note lon comes FIRST
    ST_GeomFromText(
      'POLYGON((30.0 -23.4, 31.2 -23.4, 31.2 -24.2, 30.0 -24.2, 30.0 -23.4))',
      4326
    )
  ),

  -- ── Alert 2: Flash Flood Watch ────────────────────────────
  (
    'SAWS-20240525-FLD-002',
    'Flash Flood Watch',
    'Moderate',
    'Expected',
    'Flash flooding possible in low-lying areas of Polokwane and surrounding districts.',
    'Avoid crossing flooded roads, move to higher ground if a river is nearby, and prepare for sudden water rise.',
    '2024-05-25T16:00:00+02:00',
    '2024-05-26T08:00:00+02:00',
    'South African Weather Service',
    'Polokwane and surrounding districts, Limpopo',
    'Flash flooding may happen around Polokwane and lower areas. Do not drive through floodwater and get to higher ground if needed.',
    'en',
    NULL,
    'hydrological',
    ST_GeomFromText(
      'POLYGON((29.3 -23.8, 30.1 -23.8, 30.1 -24.5, 29.3 -24.5, 29.3 -23.8))',
      4326
    )
  ),

  -- ── Alert 3: High Wind Advisory ───────────────────────────
  (
    'SAWS-20240525-WIND-003',
    'High Wind Advisory',
    'Minor',
    'Expected',
    'Strong gusts of 60–80 km/h are expected across Limpopo Highveld.',
    'Secure loose outdoor items and avoid unnecessary travel on exposed roads during the strongest winds.',
    '2024-05-25T18:00:00+02:00',
    '2024-05-26T06:00:00+02:00',
    'South African Weather Service',
    'Limpopo Highveld',
    'Strong wind gusts are possible over the Limpopo highveld. Secure loose items outside and avoid driving if conditions worsen.',
    'en',
    NULL,
    'meteorological',
    ST_GeomFromText(
      'POLYGON((28.5 -24.0, 29.8 -24.0, 29.8 -25.0, 28.5 -25.0, 28.5 -24.0))',
      4326
    )
  )

ON CONFLICT (id) DO NOTHING;


-- ============================================================
--  Confirmation message
-- ============================================================
--  This appears in Docker logs when the init script finishes.
--  Useful to confirm the script ran successfully.
-- ============================================================
DO $$
BEGIN
  RAISE NOTICE 'MHEWS database initialised — alerts table ready with % rows.',
    (SELECT COUNT(*) FROM alerts);
END $$;
