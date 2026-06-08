export type Sport = "NHL" | "NBA" | "NFL" | "CFB" | "CBB" | "MLB";
export type SportLower = "nhl" | "nba" | "nfl" | "cfb" | "cbb" | "mlb";

export function toLowerSport(s: Sport): SportLower {
  return s.toLowerCase() as SportLower;
}

export interface AuthConfig {
  supabase_url: string;
  supabase_anon_key: string;
}

export interface AuthMe {
  email: string;
  is_admin: boolean;
}

// GET /api/games response
export interface GameListEntry {
  home_team: string;
  away_team: string;
  game_time_est: string;
  event_id: string;
  date_label: string;
  venue_name?: string;
  venue_city?: string;
  venue_state?: string;
  home_rank?: number | null;
  away_rank?: number | null;
}

export interface SlateInfo {
  game_count: number;
  has_today: boolean;
  has_tomorrow: boolean;
}

export interface GamesResponse {
  games: GameListEntry[];
  slate: SlateInfo;
}

// POST /api/scan response — one game
export interface ScanGame {
  home_team: string;
  away_team: string;
  event_id: string;
  game_date: string;
  game_time_est: string;
  date_label: string;
  confirmation_score: number;
  cover_pct: number;
  cover_pct_calibrated?: number | null;
  lean_team: string;
  action: string;
  recommendation: string;
  current_spread?: number | null;
  opening_spread?: number | null;
  historical_accuracy?: number;
  historical_sample_size?: number;
  venue_name?: string;
  venue_city?: string;
  venue_state?: string;
  home_rank?: number | null;
  away_rank?: number | null;
  slot_type?: string;
  // optional analysis objects
  b2b?: Record<string, unknown>;
  ats_record?: Record<string, unknown>;
  public_betting?: Record<string, unknown>;
  head_to_head?: Record<string, unknown>;
  vegas_trap?: Record<string, unknown>;
  rank_scam?: Record<string, unknown>;
  spread_discrepancy?: Record<string, unknown>;
  ev_model?: Record<string, unknown>;
  weather?: Record<string, unknown>;
  weather_alerts?: unknown[];
  weather_dome?: boolean;
  trend_discrepancy?: Record<string, unknown>;
  overunder?: Record<string, unknown>;
  // admin curation
  approval_status?: string;
  admin_notes?: string;
  admin_lean_override?: string;
  admin_confidence_override?: number;
}

export interface ScanResponse {
  success: boolean;
  games: ScanGame[];
  cached?: boolean;
  cache_age?: number;
  picks_pending_review?: boolean;
}

export interface ScanAllResponse {
  success: boolean;
  all_sports: Record<SportLower, ScanGame[]>;
  cached?: boolean;
}

// PickCard types
export type Tier = "STRONG PLAY" | "CONFIDENT" | "LEAN" | "MONITOR";

export interface Factor {
  label: string;
  icon: string;
  points: number;
  unvalidated?: boolean;
}

export interface PickData {
  id: string;
  tier: Tier;
  coverPct: number;
  compositeScore: number;
  awayTeam: string;
  homeTeam: string;
  gameTime: string;
  slotType: string;
  actionString: string;
  spreadLine: string;
  factors: Factor[];
  moneyline?: string;
  hasUnvalidated?: boolean;
  eventId?: string;
  sport?: SportLower;
}

// Props
export interface PropSignal {
  player_name: string;
  player_id?: string | null;
  stat_type: string;
  line: number;
  projection: number;
  edge: number;
  confidence: number;
  signal: string;
  matchup: string;
  event_id: string;
  team: string;
  opponent: string;
  is_home: boolean;
  slot_type: string;
  injury_impact?: Record<string, unknown> | null;
  b2b?: boolean | null;
  line_source?: string;
}

export interface PropsResponse {
  success: boolean;
  props: PropSignal[];
  cached?: boolean;
  refreshing?: boolean;
}

// Dashboard — matches actual Flask /api/dashboard response
export interface DashboardOverall {
  total: number;
  wins: number;
  losses: number;
  pushes: number;
  pending: number;
  win_rate: number;
  win_rate_ci?: { ci_lower: number; ci_upper: number; n: number; value: number; below_minimum?: boolean };
}

export interface DashboardRecent {
  event_id: string;
  home_team: string;
  away_team: string;
  lean_team: string;
  recommendation: string;
  result: string;
  cover_pct: number;
  sport: string;
  game_time_est: string;
  action: string;
  created_at: string;
  [key: string]: unknown;
}

export interface DashboardBreakdown {
  total: number;
  wins: number;
  losses: number;
  pushes: number;
  pending: number;
  win_rate: number;
  win_rate_ci?: Record<string, unknown>;
  [key: string]: unknown; // recommendation, slot_type, sport — varies by breakdown
}

export interface DashboardResponse {
  success: boolean;
  overall: DashboardOverall;
  recent: DashboardRecent[];
  by_recommendation: DashboardBreakdown[];
  by_slot: DashboardBreakdown[];
  by_sport: DashboardBreakdown[];
  clv?: Record<string, unknown>;
}

// Bets dashboard — matches actual Flask /api/bets/dashboard response
export interface BetDashboardOverall {
  total: number;
  wins: number;
  losses: number;
  pushes: number;
  pending: number;
  win_rate: number;
  roi: number;
  win_rate_ci?: { ci_lower: number; ci_upper: number };
}

// Bets
export interface TrackedBet {
  id: number;
  event_id: string;
  sport: string;
  bet_type: string;
  home_team: string;
  away_team: string;
  lean_team?: string | null;
  spread_at_pick?: number | null;
  action?: string | null;
  recommendation?: string | null;
  cover_pct?: number | null;
  slot_type?: string | null;
  player_name?: string | null;
  stat_type?: string | null;
  prop_line?: number | null;
  prop_direction?: string | null;
  projection?: number | null;
  edge?: number | null;
  confidence?: number | null;
  signal?: string | null;
  result: string;
  actual_value?: number | null;
  home_score?: number | null;
  away_score?: number | null;
  created_at: string;
  graded_at?: string | null;
  closing_line?: number | null;
  clv?: number | null;
}

export interface BetDashboardResponse {
  success: boolean;
  overall: BetDashboardOverall;
  recent: unknown[];
  by_sport: DashboardBreakdown[];
  by_type: DashboardBreakdown[];
  by_recommendation: DashboardBreakdown[];
  by_stat_type?: DashboardBreakdown[];
}

// Picks curation
export interface PendingPick {
  event_id: string;
  sport: string;
  date: string;
  home_team: string;
  away_team: string;
  lean_team: string;
  cover_pct: number;
  recommendation: string;
  approval_status: string;
}

// Model health
export interface ModelHealthSport {
  data_confidence: Record<string, unknown>;
  last_backtest_date?: string | null;
  last_walkforward_date?: string | null;
  in_sample?: {
    accuracy: number;
    roi: number;
    strong_accuracy: number;
    strong_n: number;
    strong_ci: [number, number];
  } | null;
  out_of_sample?: {
    accuracy: number;
    roi: number;
    strong_accuracy: number;
    strong_n: number;
    strong_ci: [number, number];
  } | null;
  overfit_gap?: number | null;
  calibration_ece?: number | null;
  clv_avg?: number | null;
}

export interface ModelHealthResponse {
  success: boolean;
  sports: Record<string, ModelHealthSport>;
}

// ─── Test Model Types ─────────────────────────────────
export interface TmJobProgress {
  status: string; // "idle" | "running" | "complete" | "error"
  pct?: number;
  message?: string;
  error?: string;
  metrics?: Record<string, unknown>;
}

export interface TmCollectStatusResponse {
  success: boolean;
  progress: TmJobProgress;
  db_progress: Record<string, unknown>;
  total_games: number;
  games_with_spreads: number;
}

export interface TmBacktestStatusResponse {
  success: boolean;
  progress: TmJobProgress;
}

export interface TmThresholdEntry {
  threshold: number;
  count: number;
  accuracy: number;
  roi: number;
  ci_lower?: number;
  ci_upper?: number;
}

export interface TmFactorEntry {
  factor: string;
  fired: number;
  acc_fired: number;
  acc_not_fired: number;
  lift: number;
}

export interface TmFactorHealth {
  standalone_lift: { factor: string; standalone_acc: number; marginal_lift: number; n: number }[];
  vif: { factor: string; vif: number }[];
  marginal_lift: { factor: string; marginal_lift: number }[];
  correlations: { pair: string; corr: number }[];
  clusters: { cluster: string; factors: string[] }[];
  recommendations: string[];
}

export interface TmRulesMetrics {
  total_games: number;
  total_qualified: number;
  accuracy: number;
  roi: number;
  clv_avg?: number;
  by_threshold: TmThresholdEntry[];
  by_factor: TmFactorEntry[];
  by_slot: { slot: string; count: number; accuracy: number; roi: number }[];
  by_recommendation: { recommendation: string; count: number; accuracy: number; roi: number }[];
  factor_health?: TmFactorHealth;
  comparison?: {
    rules_accuracy: number;
    rules_roi: number;
    ml_accuracy?: number;
    ml_roi?: number;
    ml_clv?: number;
  };
  calibration?: TmCalibration;
}

export interface TmRulesMetricsResponse {
  success: boolean;
  rules_metrics: { model_params: TmRulesMetrics } | null;
  ml_metrics: { model_params: Record<string, unknown> } | null;
}

export interface TmCalibration {
  type: string;
  bins: { bin: number; predicted: number; actual: number; count: number }[];
  brier: number;
  ece: number;
  logistic?: { L: number; k: number; x0: number; b: number };
}

export interface TmCalibrationResponse {
  success: boolean;
  calibration: TmCalibration | null;
}

export interface TmScanGame {
  home_team: string;
  away_team: string;
  event_id: string;
  game_time_est: string;
  lean_team: string;
  confirmation_score: number;
  cover_pct: number;
  recommendation: string;
  current_spread?: number | null;
  slot_type?: string;
  ml_overlay?: {
    model_prob?: number;
    edge?: number;
    ev?: number;
    cluster?: string;
    sentiment?: string;
  };
}

export interface TmScanResponse {
  success: boolean;
  games: TmScanGame[];
}

export interface TmFeaturesResponse {
  success: boolean;
  features_computed: number;
}

export interface TmMetricsResponse {
  success: boolean;
  metrics: Record<string, unknown> | null;
  total_games: number;
  total_features: number;
}

export interface TmEvMetricsResponse {
  success: boolean;
  ev_metrics: {
    model_params: {
      auc?: number;
      accuracy?: number;
      roi?: number;
      n_games?: number;
      feature_importances?: { feature: string; importance: number }[];
      walk_forward?: {
        oos_accuracy: number;
        oos_roi: number;
        oos_n: number;
        ci_lower: number;
        ci_upper: number;
        folds: Record<string, unknown>[];
      };
      [key: string]: unknown;
    };
  } | null;
  model_active: boolean;
}

/** Transform a ScanGame from the API into PickData for the UI */
export function scanGameToPickData(game: ScanGame, sport: SportLower): PickData {
  const factors: Factor[] = [];

  // Line movement
  if (game.opening_spread != null && game.current_spread != null) {
    const diff = game.current_spread - game.opening_spread;
    if (diff !== 0) {
      factors.push({
        label: diff > 0 ? "Line \u2197" : "Line \u2198",
        icon: "chart",
        points: diff > 0 ? 2 : -1,
      });
    }
  }

  // B2B
  if (game.b2b) {
    const b2b = game.b2b as Record<string, unknown>;
    if (b2b.lean_b2b === false && b2b.opponent_b2b === true) {
      factors.push({ label: "B2B Edge", icon: "rest", points: 2 });
    } else if (b2b.lean_b2b === true) {
      factors.push({ label: "B2B Risk", icon: "rest", points: -1 });
    }
  }

  // ATS
  if (game.ats_record) {
    const ats = game.ats_record as Record<string, unknown>;
    if (typeof ats.ats_pct === "number" && ats.ats_pct >= 55) {
      factors.push({ label: "ATS Strong", icon: "chart", points: 2 });
    }
  }

  // Vegas trap
  if (game.vegas_trap) {
    const trap = game.vegas_trap as Record<string, unknown>;
    if (trap.is_trap) {
      factors.push({ label: "Vegas Trap", icon: "target", points: 3 });
    }
  }

  // Rank scam (CFB/CBB)
  if (game.rank_scam) {
    const rs = game.rank_scam as Record<string, unknown>;
    if (rs.is_scam) {
      factors.push({ label: "Rank Scam", icon: "alert", points: 3 });
    }
  }

  // Spread discrepancy
  if (game.spread_discrepancy) {
    const sd = game.spread_discrepancy as Record<string, unknown>;
    if (sd.discrepancy) {
      factors.push({ label: "Spread Gap", icon: "chart", points: 2 });
    }
  }

  // EV model
  if (game.ev_model) {
    const ev = game.ev_model as Record<string, unknown>;
    if (typeof ev.ev_edge === "number" && ev.ev_edge > 3) {
      factors.push({ label: `EV +${(ev.ev_edge as number).toFixed(1)}%`, icon: "zap", points: 3, unvalidated: false });
    }
  }

  // Weather (NFL)
  if (game.weather) {
    const w = game.weather as Record<string, unknown>;
    if (w.wind_mph && (w.wind_mph as number) > 15) {
      factors.push({ label: "Wind", icon: "cloud", points: 2 });
    }
  }

  // Public betting
  if (game.public_betting) {
    const pb = game.public_betting as Record<string, unknown>;
    if (typeof pb.public_pct === "number" && pb.public_pct >= 70) {
      factors.push({ label: "Public Fade", icon: "users", points: 2 });
    }
  }

  // Slot type bonus
  if (game.slot_type) {
    factors.push({
      label: game.slot_type,
      icon: "clock",
      points: 0,
    });
  }

  // If no factors extracted, add composite score as a factor
  if (factors.length === 0) {
    factors.push({
      label: "Composite",
      icon: "chart",
      points: game.confirmation_score,
    });
  }

  const hasUnvalidated = factors.some((f) => f.unvalidated);
  const coverPct = game.cover_pct_calibrated ?? game.cover_pct;

  let spreadStr = "";
  if (game.lean_team && game.current_spread != null) {
    spreadStr = `${game.lean_team} ${game.current_spread > 0 ? "+" : ""}${game.current_spread}`;
  } else if (game.lean_team) {
    spreadStr = game.lean_team;
  }

  // Map recommendation to valid tier (backend can return SKIP, MONITOR, etc.)
  const validTiers: Tier[] = ["STRONG PLAY", "CONFIDENT", "LEAN", "MONITOR"];
  const tier: Tier = validTiers.includes(game.recommendation as Tier)
    ? (game.recommendation as Tier)
    : "MONITOR";

  return {
    id: game.event_id,
    tier,
    coverPct,
    compositeScore: game.confirmation_score,
    awayTeam: game.away_team,
    homeTeam: game.home_team,
    gameTime: game.game_time_est,
    slotType: game.slot_type ?? "",
    actionString: game.action ?? "",
    spreadLine: spreadStr,
    factors,
    hasUnvalidated,
    eventId: game.event_id,
    sport,
  };
}
