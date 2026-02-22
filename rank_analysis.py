# ─── CFB / CBB Rank Analysis ──────────────────────────────────────────────────
# Rank tiers, expected spread tables, rank scam + spread discrepancy detection.


# ─── CFB RANK TIERS ──────────────────────────────────────────────────────────
# Frontend (#1-9):  Public perception darlings — NOT expected to cover big spreads
# Backend (#20-25): Under the radar — expected to cover
# Middle (#10-19):  In between — evaluate case by case

def _get_rank_tier(rank):
    """Returns 'frontend', 'middle', 'backend', or None for unranked."""
    if rank is None:
        return None
    if 1 <= rank <= 9:
        return "frontend"
    if 10 <= rank <= 19:
        return "middle"
    if 20 <= rank <= 25:
        return "backend"
    return None


# Expected spread ranges when a ranked team plays an unranked team
CFB_EXPECTED_SPREADS = {
    (1, 5): (24, 28),
    (6, 10): (18, 22),
    (11, 15): (14, 18),
    (16, 20): (10, 14),
    (21, 25): (7, 10),
}

CBB_EXPECTED_SPREADS = {
    (1, 5): (12, 16),
    (6, 10): (9, 12),
    (11, 15): (7, 9),
    (16, 20): (5, 7),
    (21, 25): (3, 5),
}

# Keep backward-compatible alias
EXPECTED_SPREADS = CFB_EXPECTED_SPREADS


def _get_expected_spread(rank, sport="cfb"):
    """Returns (low, high) expected spread for a rank tier, or None."""
    table = CBB_EXPECTED_SPREADS if sport == "cbb" else CFB_EXPECTED_SPREADS
    for (lo, hi), spread_range in table.items():
        if lo <= rank <= hi:
            return spread_range
    return None


def _detect_rank_scam(home_rank, away_rank, current_spread, slot_type):
    """
    Detect Rank Scam: both teams ranked, better-ranked team is at home
    but listed as the underdog (positive home spread).

    Trigger conditions (ALL must be true):
      1. Both teams are ranked
      2. The better-ranked team (lower number) is at home
      3. The better-ranked team is the underdog (positive spread)

    Slot confirmation:
      - Public slot → ranked underdog at home COVERS → take them on the spread
      - Vegas slot  → ranked underdog at home does NOT cover → fade them

    Returns dict with detection results.
    """
    result = {"is_rank_scam": False}

    if current_spread is None:
        return result

    # Both teams must be ranked
    if home_rank is None or away_rank is None:
        return result

    # Better-ranked team (lower number) must be at home
    if home_rank >= away_rank:
        return result

    # Home team must be the underdog (positive spread means home is underdog)
    if current_spread <= 0:
        return result

    # All conditions met — rank scam detected
    result["is_rank_scam"] = True
    result["scam_team"] = "home"
    result["home_rank"] = home_rank
    result["away_rank"] = away_rank
    result["spread"] = current_spread
    result["tier"] = _get_rank_tier(home_rank)

    if slot_type in ("public", "caution"):
        result["scam_action"] = (
            f"#{home_rank} at home as underdog vs #{away_rank} — "
            f"PUBLIC slot: expect them to COVER (+{current_spread})"
        )
    elif slot_type in ("vegas", "trap"):
        result["scam_action"] = (
            f"#{home_rank} at home as underdog vs #{away_rank} — "
            f"VEGAS slot: FADE the home underdog"
        )
    else:
        result["scam_action"] = (
            f"#{home_rank} at home as underdog vs #{away_rank} — "
            f"rank scam detected, investigate"
        )

    return result


def _detect_spread_discrepancy(home_rank, away_rank, current_spread, slot_type, sport="cfb"):
    """
    Detect spread discrepancy when a ranked team plays an unranked team.

    If the actual spread is far below the expected range for the rank tier, flag it.

    Returns dict with detection results.
    """
    result = {"is_discrepancy": False}

    if current_spread is None:
        return result

    # Determine which team is ranked vs unranked
    ranked_team = None
    rank = None
    if home_rank is not None and away_rank is None:
        ranked_team = "home"
        rank = home_rank
        spread_magnitude = abs(current_spread)
    elif away_rank is not None and home_rank is None:
        ranked_team = "away"
        rank = away_rank
        spread_magnitude = abs(current_spread)
    else:
        return result  # Both ranked or both unranked — not applicable

    expected = _get_expected_spread(rank, sport=sport)
    if expected is None:
        return result

    expected_low, expected_high = expected

    # Discrepancy: actual spread is significantly below expected low end
    if spread_magnitude < expected_low - 3:
        result["is_discrepancy"] = True
        result["ranked_team"] = ranked_team
        result["rank"] = rank
        result["expected_range"] = f"{expected_low}-{expected_high}"
        result["actual_spread"] = current_spread

        tier = _get_rank_tier(rank)
        if tier == "frontend":
            result["discrepancy_action"] = f"Line is suspiciously low for #{rank} — frontend team, don't expect cover"
        elif tier == "backend":
            result["discrepancy_action"] = f"Line looks off for #{rank} — backend team, expect cover"
        else:
            result["discrepancy_action"] = f"Spread discrepancy for #{rank} — investigate"

    return result
