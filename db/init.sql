-- ============================================================
--  MHEWS — db/init.sql
--  Database Schema Initialization
-- ============================================================

-- 1. Enable PostGIS for spatial data (polygons, location checks)
CREATE EXTENSION IF NOT EXISTS postgis;

-- ============================================================
--  TABLE: cap_sources
--  Stores the WMO S3 CAP feed URLs and polling metadata.
-- ============================================================
CREATE TABLE IF NOT EXISTS cap_sources (
    id SERIAL PRIMARY KEY,
    country VARCHAR(100),
    organisation VARCHAR(255),
    language VARCHAR(50),
    feed_url VARCHAR(500) UNIQUE NOT NULL,
    region VARCHAR(50),
    enabled BOOLEAN DEFAULT TRUE,
    poll_interval_minutes INTEGER DEFAULT 60,
    last_checked TIMESTAMP WITH TIME ZONE,
    last_updated TIMESTAMP WITH TIME ZONE,
    etag VARCHAR(255),
    last_modified VARCHAR(255)
);

-- Index to quickly find feeds that are due for polling
CREATE INDEX IF NOT EXISTS idx_cap_sources_due ON cap_sources (enabled, last_checked);


-- ============================================================
--  TABLE: alerts
--  Stores the parsed hazard alerts.
-- ============================================================
CREATE TABLE IF NOT EXISTS alerts (
    id VARCHAR(255) PRIMARY KEY, -- CAP identifiers are strings (e.g., 'NWS-...', '2.49.0...')
    event VARCHAR(255),
    severity VARCHAR(50),
    urgency VARCHAR(50),
    description TEXT,
    instruction TEXT,
    source VARCHAR(255),
    area_desc TEXT,
    hazard_category VARCHAR(50),
    onset TIMESTAMP WITH TIME ZONE,
    expires TIMESTAMP WITH TIME ZONE,
    polygon geometry(Polygon, 4326), -- PostGIS geometry (allows NULL for feeds without polygons)
    plain_text TEXT,
    plain_text_language VARCHAR(10) DEFAULT 'en',
    accuracy_percent INTEGER,
    original_language VARCHAR(10) DEFAULT 'en',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_seen_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Spatial index for fast "is my location inside this polygon?" queries
CREATE INDEX IF NOT EXISTS idx_alerts_polygon ON alerts USING GIST (polygon);

-- Index for quickly filtering active, non-expired alerts
CREATE INDEX IF NOT EXISTS idx_alerts_active ON alerts (is_active, expires);

-- ============================================================
--  TABLE: country_polygons
--  Fallback country boundaries for alerts without geometry.
-- ============================================================
CREATE TABLE IF NOT EXISTS country_polygons (
    iso_code VARCHAR(3) PRIMARY KEY,
    country_name VARCHAR(100) NOT NULL,
    polygon_wkt TEXT NOT NULL
);


-- ============================================================
--  TABLE: user_settings
--  Stores user preferences for dynamic feed polling priorities.
-- ============================================================
CREATE TABLE IF NOT EXISTS user_settings (
    id SERIAL PRIMARY KEY,
    country VARCHAR(100),
    home_lat DOUBLE PRECISION,
    home_lon DOUBLE PRECISION,
    language VARCHAR(10) DEFAULT 'en',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);