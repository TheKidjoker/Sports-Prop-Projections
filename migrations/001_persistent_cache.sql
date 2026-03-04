-- Persistent cache tables for scan results and props
-- Run this in Supabase SQL editor

-- Scan cache table
CREATE TABLE IF NOT EXISTS scan_cache (
    id BIGSERIAL PRIMARY KEY,
    sport TEXT NOT NULL,
    results JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Index for fast lookups
CREATE INDEX IF NOT EXISTS idx_scan_cache_sport_created
    ON scan_cache(sport, created_at DESC);

-- Props cache table
CREATE TABLE IF NOT EXISTS props_cache (
    id BIGSERIAL PRIMARY KEY,
    sport TEXT NOT NULL,
    results JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Index for fast lookups
CREATE INDEX IF NOT EXISTS idx_props_cache_sport_created
    ON props_cache(sport, created_at DESC);

-- Enable RLS (Row Level Security)
ALTER TABLE scan_cache ENABLE ROW LEVEL SECURITY;
ALTER TABLE props_cache ENABLE ROW LEVEL SECURITY;

-- Policy: Service role can do everything
CREATE POLICY "Service role full access on scan_cache"
    ON scan_cache
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

CREATE POLICY "Service role full access on props_cache"
    ON props_cache
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

-- Policy: Authenticated users can read (for future direct client access)
CREATE POLICY "Authenticated users can read scan_cache"
    ON scan_cache
    FOR SELECT
    TO authenticated
    USING (true);

CREATE POLICY "Authenticated users can read props_cache"
    ON props_cache
    FOR SELECT
    TO authenticated
    USING (true);

-- Auto-cleanup function to delete entries older than 24 hours
CREATE OR REPLACE FUNCTION cleanup_old_cache_entries()
RETURNS void AS $$
BEGIN
    DELETE FROM scan_cache WHERE created_at < NOW() - INTERVAL '24 hours';
    DELETE FROM props_cache WHERE created_at < NOW() - INTERVAL '24 hours';
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Optional: Schedule auto-cleanup (requires pg_cron extension)
-- SELECT cron.schedule('cleanup-cache', '0 2 * * *', 'SELECT cleanup_old_cache_entries()');
