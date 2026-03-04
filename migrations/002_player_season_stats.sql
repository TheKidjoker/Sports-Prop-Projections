-- Player season stats cache table
-- Reduces API calls from 100+ per scan to DB lookups
-- Run this in Supabase SQL editor

CREATE TABLE IF NOT EXISTS player_season_stats (
    player_id TEXT NOT NULL,
    sport TEXT NOT NULL,
    season TEXT NOT NULL,
    -- Common stats across all sports
    ppg NUMERIC,
    rpg NUMERIC,
    apg NUMERIC,
    mpg NUMERIC,
    -- NBA/CBB specific
    fgpct NUMERIC,
    fg3pct NUMERIC,
    ftpct NUMERIC,
    spg NUMERIC,  -- steals
    bpg NUMERIC,  -- blocks
    topg NUMERIC, -- turnovers
    -- NHL specific
    goals NUMERIC,
    assists NUMERIC,
    points NUMERIC,
    plus_minus NUMERIC,
    pim NUMERIC,  -- penalty minutes
    -- Metadata
    games_played INTEGER,
    last_updated TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (player_id, sport, season)
);

-- Index for fast lookups
CREATE INDEX IF NOT EXISTS idx_player_stats_lookup
    ON player_season_stats(player_id, sport, season);

-- Index for cleanup queries
CREATE INDEX IF NOT EXISTS idx_player_stats_updated
    ON player_season_stats(last_updated);

-- Enable RLS
ALTER TABLE player_season_stats ENABLE ROW LEVEL SECURITY;

-- Policy: Service role can do everything
CREATE POLICY "Service role full access on player_season_stats"
    ON player_season_stats
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

-- Policy: Authenticated users can read
CREATE POLICY "Authenticated users can read player_season_stats"
    ON player_season_stats
    FOR SELECT
    TO authenticated
    USING (true);

-- Auto-cleanup function to delete entries older than 7 days
CREATE OR REPLACE FUNCTION cleanup_old_player_stats()
RETURNS void AS $$
BEGIN
    DELETE FROM player_season_stats WHERE last_updated < NOW() - INTERVAL '7 days';
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;
