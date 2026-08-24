-- backend/init.sql
-- Reproducible Database Initialization for MHEWS

-- 1. Enable PostGIS extension
CREATE EXTENSION IF NOT EXISTS postgis;

-- 2. Create country_polygons table (for WMO fallback boundaries)
CREATE TABLE IF NOT EXISTS country_polygons (
    id SERIAL PRIMARY KEY,
    country_name VARCHAR(100) UNIQUE NOT NULL,
    polygon_wkt TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_country_name ON country_polygons(country_name);

-- 3. Create cap_sources table
CREATE TABLE IF NOT EXISTS cap_sources (
    id SERIAL PRIMARY KEY,
    country VARCHAR(100) NOT NULL,
    organisation VARCHAR(100),
    feed_url TEXT UNIQUE NOT NULL,
    enabled BOOLEAN DEFAULT TRUE,
    last_checked TIMESTAMP WITH TIME ZONE
);
CREATE INDEX IF NOT EXISTS idx_cap_sources_enabled ON cap_sources(enabled);

-- 4. Create alerts table (matching your current working schema)
CREATE TABLE IF NOT EXISTS alerts (
    id VARCHAR(255) PRIMARY KEY,
    event TEXT NOT NULL,
    severity VARCHAR(50),
    urgency VARCHAR(50),
    description TEXT,
    instruction TEXT,
    source VARCHAR(255),
    area_desc TEXT,
    hazard_category VARCHAR(50),
    onset TIMESTAMP WITH TIME ZONE,
    expires TIMESTAMP WITH TIME ZONE,
    polygon geometry(Polygon, 4326),
    plain_text TEXT,
    plain_text_language VARCHAR(10) DEFAULT 'en',
    accuracy_percent INTEGER,
    last_seen_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_alerts_expires ON alerts(expires);
CREATE INDEX IF NOT EXISTS idx_alerts_onset ON alerts(onset);
CREATE INDEX IF NOT EXISTS idx_alerts_polygon ON alerts USING GIST(polygon);

-- 5. Seed the curated, high-quality feeds
INSERT INTO cap_sources (country, organisation, feed_url, enabled) VALUES
('Cyprus', 'MeteoAlarm', 'https://feeds.meteoalarm.org/feeds/meteoalarm-legacy-atom-cyprus', TRUE),
('Finland', 'MeteoAlarm', 'https://feeds.meteoalarm.org/feeds/meteoalarm-legacy-atom-finland', TRUE),
('Croatia', 'MeteoAlarm', 'https://feeds.meteoalarm.org/feeds/meteoalarm-legacy-atom-croatia', TRUE),
('Hungary', 'MeteoAlarm', 'https://feeds.meteoalarm.org/feeds/meteoalarm-legacy-atom-hungary', TRUE),
('Montenegro', 'MeteoAlarm', 'https://feeds.meteoalarm.org/feeds/meteoalarm-legacy-atom-montenegro', TRUE),
('Netherlands', 'MeteoAlarm', 'https://feeds.meteoalarm.org/feeds/meteoalarm-legacy-atom-netherlands', TRUE),
('Lithuania', 'MeteoAlarm', 'https://feeds.meteoalarm.org/feeds/meteoalarm-legacy-atom-lithuania', TRUE),
('Bosnia and Herzegovina', 'MeteoAlarm', 'https://feeds.meteoalarm.org/feeds/meteoalarm-legacy-atom-bosnia-herzegovina', TRUE),
('United Kingdom', 'MeteoAlarm', 'https://feeds.meteoalarm.org/feeds/meteoalarm-legacy-atom-united-kingdom', TRUE),
('Ukraine', 'MeteoAlarm', 'https://feeds.meteoalarm.org/feeds/meteoalarm-legacy-atom-ukraine', TRUE),
('Italy', 'MeteoAlarm', 'https://feeds.meteoalarm.org/feeds/meteoalarm-legacy-atom-italy', TRUE),
('Moldova', 'MeteoAlarm', 'https://feeds.meteoalarm.org/feeds/meteoalarm-legacy-atom-moldova', TRUE),
('Serbia', 'MeteoAlarm', 'https://feeds.meteoalarm.org/feeds/meteoalarm-legacy-atom-serbia', TRUE),
('Slovenia', 'MeteoAlarm', 'https://feeds.meteoalarm.org/feeds/meteoalarm-legacy-atom-slovenia', TRUE),
('Slovakia', 'MeteoAlarm', 'https://feeds.meteoalarm.org/feeds/meteoalarm-legacy-atom-slovakia', TRUE),
('Switzerland', 'MeteoAlarm', 'https://feeds.meteoalarm.org/feeds/meteoalarm-legacy-atom-switzerland', TRUE),
('France', 'MeteoAlarm', 'https://feeds.meteoalarm.org/feeds/meteoalarm-legacy-atom-france', TRUE),
('Romania', 'MeteoAlarm', 'https://feeds.meteoalarm.org/feeds/meteoalarm-legacy-atom-romania', TRUE),
('Austria', 'MeteoAlarm', 'https://feeds.meteoalarm.org/feeds/meteoalarm-legacy-atom-austria', TRUE),
('Poland', 'MeteoAlarm', 'https://feeds.meteoalarm.org/feeds/meteoalarm-legacy-atom-poland', TRUE),
('Czechia', 'MeteoAlarm', 'https://feeds.meteoalarm.org/feeds/meteoalarm-legacy-atom-czechia', TRUE),
('Spain', 'MeteoAlarm', 'https://feeds.meteoalarm.org/feeds/meteoalarm-legacy-atom-spain', TRUE),
('Germany', 'MeteoAlarm', 'https://feeds.meteoalarm.org/feeds/meteoalarm-legacy-atom-germany', TRUE),
('Greece', 'MeteoAlarm', 'https://feeds.meteoalarm.org/feeds/meteoalarm-legacy-atom-greece', TRUE),
('Bulgaria', 'MeteoAlarm', 'https://feeds.meteoalarm.org/feeds/meteoalarm-legacy-atom-bulgaria', TRUE),
('Estonia', 'MeteoAlarm', 'https://feeds.meteoalarm.org/feeds/meteoalarm-legacy-atom-estonia', TRUE),
('Latvia', 'MeteoAlarm', 'https://feeds.meteoalarm.org/feeds/meteoalarm-legacy-atom-latvia', TRUE),
('South Africa', 'Enviroflash', 'http://feeds.enviroflash.info/cap/aggregate.xml', TRUE),
('Uruguay', 'INUMET', 'https://www.inumet.gub.uy/', TRUE),
('Trinidad and Tobago', 'Met Office', 'http://www.metoffice.gov.tt/forecast', TRUE)
ON CONFLICT (feed_url) DO NOTHING;