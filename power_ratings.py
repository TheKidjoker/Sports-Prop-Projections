"""
Power Ratings System — Elo-based team strength ratings.

Feeds into EV models (elo_diff feature) and PRISM projections.
Built from historical game data in test_model.db — no new API calls.

Sport-specific configs for K-factor, home advantage, MOV multiplier,
and season regression. 24-hour memory cache.
"""

import math
import time

# ─── Sport-Specific Configuration ─────────────────────────────────────────────

ELO_CONFIG = {
    "nba": {
        "k_factor": 20,
        "home_advantage": 100,
        "season_carry": 0.75,       # 75% Elo carry between seasons
        "initial_elo": 1500,
        "mov_multiplier": True,     # Use margin-of-victory adjustment
    },
    "nhl": {
        "k_factor": 12,
        "home_advantage": 50,
        "season_carry": 0.80,
        "initial_elo": 1500,
        "mov_multiplier": True,
    },
    "cbb": {
        "k_factor": 24,
        "home_advantage": 150,
        "season_carry": 0.60,       # Higher roster turnover
        "initial_elo": 1500,
        "mov_multiplier": True,
    },
    "nfl": {
        "k_factor": 20,
        "home_advantage": 65,
        "season_carry": 0.70,
        "initial_elo": 1500,
        "mov_multiplier": True,
    },
    "cfb": {
        "k_factor": 24,
        "home_advantage": 100,
        "season_carry": 0.55,
        "initial_elo": 1500,
        "mov_multiplier": True,
    },
    "mlb": {
        "k_factor": 8,
        "home_advantage": 30,
        "season_carry": 0.65,
        "initial_elo": 1500,
        "mov_multiplier": True,
    },
}

# ─── Module-Level Cache ───────────────────────────────────────────────────────

_elo_ratings = {}       # {sport: {team: elo_value}}
_elo_cache_ts = 0       # Unix timestamp of last build
_ELO_CACHE_TTL = 86400  # 24 hours


# ─── Core Elo Math ────────────────────────────────────────────────────────────

def _expected_score(rating_a, rating_b):
    """Expected score for team A given ratings."""
    return 1.0 / (1.0 + 10 ** ((rating_b - rating_a) / 400.0))


def _mov_multiplier(margin, elo_diff):
    """
    FiveThirtyEight-style margin-of-victory multiplier.
    Diminishing returns for blowouts, adjusted for pre-game Elo gap.
    Formula: ln(|mov| + 1) * 2.2 / (elo_diff * 0.001 + 2.2)
    """
    mov = abs(margin)
    multiplier = math.log(mov + 1) * 2.2 / (elo_diff * 0.001 + 2.2)
    return max(multiplier, 0.5)  # Floor at 0.5 to prevent near-zero updates


def _update_elo(winner_elo, loser_elo, margin, k_factor, use_mov=True):
    """
    Update Elo ratings after a game.

    Args:
        winner_elo: current Elo of winning team
        loser_elo: current Elo of losing team
        margin: point differential (positive)
        k_factor: sport-specific K-factor
        use_mov: whether to apply margin-of-victory multiplier

    Returns:
        (new_winner_elo, new_loser_elo) tuple
    """
    expected_w = _expected_score(winner_elo, loser_elo)
    expected_l = 1.0 - expected_w

    if use_mov and margin > 0:
        elo_diff = winner_elo - loser_elo
        mov_mult = _mov_multiplier(margin, elo_diff)
    else:
        mov_mult = 1.0

    k_adj = k_factor * mov_mult

    new_winner = winner_elo + k_adj * (1.0 - expected_w)
    new_loser = loser_elo + k_adj * (0.0 - expected_l)

    return round(new_winner, 1), round(new_loser, 1)


# ─── Rating Builder ───────────────────────────────────────────────────────────

def _build_ratings(sport):
    """
    Build Elo ratings from historical games for a sport.
    Processes games chronologically. Applies season regression at year boundaries.

    Returns:
        dict of {team_name: elo_value}
    """
    try:
        from test_model import db as tm_db
        games = tm_db.get_historical_games(sport)
    except Exception:
        return {}

    if not games:
        return {}

    config = ELO_CONFIG.get(sport, ELO_CONFIG["nba"])
    k = config["k_factor"]
    home_adv = config["home_advantage"]
    carry = config["season_carry"]
    initial = config["initial_elo"]
    use_mov = config["mov_multiplier"]

    # Filter to final games with scores
    eligible = [
        g for g in games
        if g.get("game_status") == "STATUS_FINAL"
        and g.get("home_score") is not None
        and g.get("away_score") is not None
    ]
    eligible.sort(key=lambda g: g.get("game_date", ""))

    if not eligible:
        return {}

    ratings = {}
    current_year = None

    for game in eligible:
        home = game["home_team"]
        away = game["away_team"]
        home_score = game["home_score"]
        away_score = game["away_score"]
        game_date = game.get("game_date", "")

        # Detect season boundary (year change) and apply regression
        game_year = game_date[:4] if len(game_date) >= 4 else None
        if game_year and game_year != current_year and current_year is not None:
            # Regress all ratings toward mean
            mean_elo = sum(ratings.values()) / len(ratings) if ratings else initial
            for team in ratings:
                ratings[team] = carry * ratings[team] + (1 - carry) * mean_elo
            current_year = game_year
        elif game_year:
            current_year = game_year

        # Initialize teams if needed
        if home not in ratings:
            ratings[home] = initial
        if away not in ratings:
            ratings[away] = initial

        # Apply home advantage for expected score calculation
        home_elo_adj = ratings[home] + home_adv
        away_elo_adj = ratings[away]

        # Determine winner and update
        margin = abs(home_score - away_score)
        if margin == 0:
            # Tie (rare in basketball, possible in regulation NHL)
            # Small update toward draw
            expected_h = _expected_score(home_elo_adj, away_elo_adj)
            ratings[home] += k * 0.3 * (0.5 - expected_h)
            ratings[away] -= k * 0.3 * (0.5 - expected_h)
        elif home_score > away_score:
            # Home won
            new_home, new_away = _update_elo(
                home_elo_adj, away_elo_adj, margin, k, use_mov
            )
            # Remove home advantage from stored rating
            ratings[home] = new_home - home_adv
            ratings[away] = new_away
        else:
            # Away won
            new_away, new_home = _update_elo(
                away_elo_adj, home_elo_adj, margin, k, use_mov
            )
            # Remove home advantage from stored rating
            ratings[home] = new_home - home_adv
            ratings[away] = new_away

    return ratings


# ─── Public API ───────────────────────────────────────────────────────────────

def load_elo_ratings():
    """
    Build/refresh Elo ratings for all sports. Called at app startup.
    Results cached for 24 hours.
    """
    global _elo_ratings, _elo_cache_ts

    for sport in ELO_CONFIG:
        try:
            ratings = _build_ratings(sport)
            if ratings:
                _elo_ratings[sport] = ratings
                print(f"[power_ratings] {sport.upper()}: {len(ratings)} teams rated "
                      f"(range {min(ratings.values()):.0f}-{max(ratings.values()):.0f})",
                      flush=True)
        except Exception as e:
            print(f"[power_ratings] {sport} build failed: {e}", flush=True)

    _elo_cache_ts = time.time()


def get_elo(team, sport="nba"):
    """
    Get current Elo rating for a team.

    Returns:
        float Elo rating, or 1500.0 (initial) if team not found.
    """
    _ensure_loaded()
    sport_ratings = _elo_ratings.get(sport, {})
    return sport_ratings.get(team, ELO_CONFIG.get(sport, {}).get("initial_elo", 1500))


def get_elo_diff(home_team, away_team, sport="nba"):
    """
    Get Elo difference (home - away) adjusted for home advantage.
    Positive = home team stronger after home bonus.

    Returns:
        float Elo difference
    """
    _ensure_loaded()
    config = ELO_CONFIG.get(sport, ELO_CONFIG["nba"])
    home_elo = get_elo(home_team, sport) + config["home_advantage"]
    away_elo = get_elo(away_team, sport)
    return round(home_elo - away_elo, 1)


def get_elo_win_prob(home_team, away_team, sport="nba"):
    """
    Get Elo-implied win probability for home team.

    Returns:
        float probability (0-1) that home team wins
    """
    _ensure_loaded()
    config = ELO_CONFIG.get(sport, ELO_CONFIG["nba"])
    home_elo = get_elo(home_team, sport) + config["home_advantage"]
    away_elo = get_elo(away_team, sport)
    return round(_expected_score(home_elo, away_elo), 4)


def get_all_ratings(sport="nba"):
    """Get all team ratings for a sport. Returns dict {team: elo}."""
    _ensure_loaded()
    return dict(_elo_ratings.get(sport, {}))


# ─── Internal Helpers ─────────────────────────────────────────────────────────

def _ensure_loaded():
    """Ensure ratings are loaded, rebuild if cache expired."""
    global _elo_cache_ts
    now = time.time()
    if not _elo_ratings or (now - _elo_cache_ts > _ELO_CACHE_TTL):
        load_elo_ratings()
