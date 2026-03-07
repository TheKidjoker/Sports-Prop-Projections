-- =============================================================================
-- Supabase SQL Setup — Run this in the Supabase SQL Editor BEFORE code changes
-- =============================================================================

-- ─── 1. Create Tables ───────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS predictions (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_id TEXT NOT NULL,
    sport TEXT NOT NULL,
    home_team TEXT NOT NULL,
    away_team TEXT NOT NULL,
    game_date TEXT,
    game_time_est TEXT,
    lean_team TEXT,
    action TEXT,
    slot_type TEXT,
    recommendation TEXT,
    confirmation_score REAL,
    cover_pct REAL,
    current_spread REAL,
    line_at_pick REAL,       -- spread (home perspective) when prediction first created
    closing_line REAL,       -- spread (home perspective) at/near game time
    clv REAL,                -- closing line value: positive = got better number
    clv_direction INTEGER,   -- 1 = line moved in your favor, 0 = against
    result TEXT DEFAULT 'PENDING',
    home_score INTEGER,
    away_score INTEGER,
    created_at TEXT,
    graded_at TEXT,
    UNIQUE(event_id, sport)
);

-- For existing Supabase DBs, run these ALTER TABLEs manually:
-- ALTER TABLE predictions ADD COLUMN IF NOT EXISTS line_at_pick REAL;
-- ALTER TABLE predictions ADD COLUMN IF NOT EXISTS closing_line REAL;
-- ALTER TABLE predictions ADD COLUMN IF NOT EXISTS clv REAL;
-- ALTER TABLE predictions ADD COLUMN IF NOT EXISTS clv_direction INTEGER;

CREATE TABLE IF NOT EXISTS tm_historical_games (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_id TEXT NOT NULL,
    sport TEXT NOT NULL,
    game_date TEXT NOT NULL,
    home_team TEXT NOT NULL,
    away_team TEXT NOT NULL,
    home_team_id TEXT,
    away_team_id TEXT,
    home_rank INTEGER,
    away_rank INTEGER,
    closing_spread REAL,
    opening_spread REAL,
    over_under REAL,
    home_score INTEGER,
    away_score INTEGER,
    home_covered INTEGER,
    game_status TEXT,
    UNIQUE(event_id, sport)
);

CREATE TABLE IF NOT EXISTS tm_game_features (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_id TEXT NOT NULL,
    sport TEXT NOT NULL,
    features_json TEXT NOT NULL,
    cluster_id INTEGER,
    target INTEGER,
    UNIQUE(event_id, sport)
);

CREATE TABLE IF NOT EXISTS tm_collection_progress (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sport TEXT NOT NULL,
    date_str TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING',
    games_found INTEGER DEFAULT 0,
    error_msg TEXT,
    UNIQUE(sport, date_str)
);

CREATE TABLE IF NOT EXISTS tm_model_runs (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sport TEXT NOT NULL,
    run_type TEXT NOT NULL,
    run_date TEXT NOT NULL,
    accuracy REAL,
    roi REAL,
    clv_avg REAL,
    calibration_error REAL,
    total_predictions INTEGER,
    qualified_bets INTEGER,
    feature_importances TEXT,
    model_params TEXT,
    threshold_analysis TEXT,
    predictions_json TEXT
);

CREATE TABLE IF NOT EXISTS tm_tracked_bets (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_email TEXT NOT NULL,
    bet_type TEXT NOT NULL,
    sport TEXT NOT NULL,
    event_id TEXT NOT NULL,
    game_date TEXT,
    home_team TEXT NOT NULL,
    away_team TEXT NOT NULL,
    lean_team TEXT,
    spread_at_pick REAL,
    action TEXT,
    recommendation TEXT,
    cover_pct REAL,
    slot_type TEXT,
    player_name TEXT NOT NULL DEFAULT '',
    stat_type TEXT NOT NULL DEFAULT '',
    prop_line REAL,
    prop_direction TEXT,
    projection REAL,
    edge REAL,
    confidence REAL,
    signal TEXT,
    result TEXT DEFAULT 'PENDING',
    actual_value REAL,
    home_score INTEGER,
    away_score INTEGER,
    created_at TEXT NOT NULL,
    graded_at TEXT,
    notes TEXT,
    closing_line REAL,
    clv REAL,
    clv_direction INTEGER,
    kelly_fraction REAL,
    suggested_units REAL,
    model_probability REAL,
    implied_probability REAL,
    over_odds INTEGER,
    under_odds INTEGER,
    expected_value REAL,
    closing_odds INTEGER,
    clv_prob_delta REAL,
    UNIQUE(user_email, event_id, bet_type, player_name, stat_type)
);

-- ─── 2. Disable RLS on all tables (private backend-only access) ─────────────

ALTER TABLE predictions ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Allow all for service key" ON predictions FOR ALL USING (true) WITH CHECK (true);

ALTER TABLE tm_historical_games ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Allow all for service key" ON tm_historical_games FOR ALL USING (true) WITH CHECK (true);

ALTER TABLE tm_game_features ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Allow all for service key" ON tm_game_features FOR ALL USING (true) WITH CHECK (true);

ALTER TABLE tm_collection_progress ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Allow all for service key" ON tm_collection_progress FOR ALL USING (true) WITH CHECK (true);

ALTER TABLE tm_model_runs ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Allow all for service key" ON tm_model_runs FOR ALL USING (true) WITH CHECK (true);

ALTER TABLE tm_tracked_bets ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Allow all for service key" ON tm_tracked_bets FOR ALL USING (true) WITH CHECK (true);

-- ─── 3. RPC Functions ───────────────────────────────────────────────────────

-- 3a. Aggregate prediction stats (used by dashboard)
CREATE OR REPLACE FUNCTION aggregate_prediction_stats(
    p_where_column TEXT DEFAULT NULL,
    p_where_value TEXT DEFAULT NULL,
    p_sport TEXT DEFAULT NULL
)
RETURNS TABLE(wins BIGINT, losses BIGINT, pushes BIGINT, pending BIGINT, total BIGINT)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY EXECUTE format(
        'SELECT
            SUM(CASE WHEN result = ''HIT'' THEN 1 ELSE 0 END)::BIGINT as wins,
            SUM(CASE WHEN result = ''MISS'' THEN 1 ELSE 0 END)::BIGINT as losses,
            SUM(CASE WHEN result = ''PUSH'' THEN 1 ELSE 0 END)::BIGINT as pushes,
            SUM(CASE WHEN result = ''PENDING'' THEN 1 ELSE 0 END)::BIGINT as pending,
            COUNT(*)::BIGINT as total
         FROM predictions
         WHERE 1=1
           %s
           %s',
        CASE WHEN p_sport IS NOT NULL
            THEN format(' AND sport = %L', p_sport)
            ELSE ''
        END,
        CASE WHEN p_where_column IS NOT NULL AND p_where_value IS NOT NULL
            THEN format(' AND %I = %L', p_where_column, p_where_value)
            ELSE ''
        END
    );
END;
$$;

-- 3b. Collection progress counts (used by test_model/db.py)
CREATE OR REPLACE FUNCTION get_collection_progress_counts(
    p_sport TEXT
)
RETURNS TABLE(status TEXT, cnt BIGINT)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
        SELECT cp.status, COUNT(*)::BIGINT as cnt
        FROM tm_collection_progress cp
        WHERE cp.sport = p_sport
        GROUP BY cp.status;
END;
$$;

-- 3c. Game features for training (JOIN query used by test_model/db.py)
CREATE OR REPLACE FUNCTION get_game_features_for_training(
    p_sport TEXT,
    p_before_date TEXT DEFAULT NULL
)
RETURNS TABLE(features_json TEXT, target INTEGER, cluster_id INTEGER, game_date TEXT)
LANGUAGE plpgsql
AS $$
BEGIN
    IF p_before_date IS NOT NULL THEN
        RETURN QUERY
            SELECT f.features_json, f.target, f.cluster_id, g.game_date
            FROM tm_game_features f
            JOIN tm_historical_games g ON f.event_id = g.event_id AND f.sport = g.sport
            WHERE f.sport = p_sport AND g.game_date < p_before_date AND f.target IS NOT NULL
            ORDER BY g.game_date ASC;
    ELSE
        RETURN QUERY
            SELECT f.features_json, f.target, f.cluster_id, g.game_date
            FROM tm_game_features f
            JOIN tm_historical_games g ON f.event_id = g.event_id AND f.sport = g.sport
            WHERE f.sport = p_sport AND f.target IS NOT NULL
            ORDER BY g.game_date ASC;
    END IF;
END;
$$;
