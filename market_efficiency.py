# ─── Market Efficiency Analysis ───────────────────────────────────────────────
# Tools for analyzing market efficiency: opener vs closer accuracy,
# stale line detection, and cross-book market width.

from vig_analysis import compute_market_width


def compute_opener_closer_efficiency(historical_games, sport):
    """
    Analyze whether opening or closing lines are more predictive.

    Compares opening spreads vs closing spreads against actual results
    to determine which is a better predictor.

    Args:
        historical_games: list of game dicts with opening_spread, closing_spread, result
        sport: sport key

    Returns:
        dict with opener_accuracy, closer_accuracy, recommendation
    """
    if not historical_games:
        return {
            "opener_accuracy": None,
            "closer_accuracy": None,
            "sample_size": 0,
            "recommendation": "insufficient_data",
        }

    opener_correct = 0
    closer_correct = 0
    total = 0

    for game in historical_games:
        opening = game.get("opening_spread")
        closing = game.get("closing_spread")
        margin = game.get("home_margin")

        if opening is None or closing is None or margin is None:
            continue

        total += 1

        # Did opening spread predict correctly?
        if (opening < 0 and margin > abs(opening)) or (opening > 0 and margin < -opening):
            opener_correct += 1

        # Did closing spread predict correctly?
        if (closing < 0 and margin > abs(closing)) or (closing > 0 and margin < -closing):
            closer_correct += 1

    if total == 0:
        return {
            "opener_accuracy": None,
            "closer_accuracy": None,
            "sample_size": 0,
            "recommendation": "insufficient_data",
        }

    opener_acc = round(opener_correct / total * 100, 1)
    closer_acc = round(closer_correct / total * 100, 1)

    if closer_acc > opener_acc + 2:
        recommendation = "use_closing"
    elif opener_acc > closer_acc + 2:
        recommendation = "use_opening"
    else:
        recommendation = "no_difference"

    return {
        "opener_accuracy": opener_acc,
        "closer_accuracy": closer_acc,
        "sample_size": total,
        "recommendation": recommendation,
    }


def find_stale_lines(odds_data, sharp_book="pinnacle"):
    """
    Identify lines that are 1+ points off Pinnacle = potential +EV.

    Args:
        odds_data: list of bookmaker odds dicts
        sharp_book: which book to use as the sharp reference

    Returns:
        list of stale line opportunities
    """
    stale = []

    if not odds_data:
        return stale

    for game in odds_data:
        bookmakers = game.get("bookmakers", [])
        if not bookmakers:
            continue

        # Find sharp book's line
        sharp_line = None
        for bm in bookmakers:
            if bm.get("key", "").lower() == sharp_book:
                for market in bm.get("markets", []):
                    if market.get("key") == "spreads":
                        outcomes = market.get("outcomes", [])
                        if outcomes:
                            sharp_line = outcomes[0].get("point")
                break

        if sharp_line is None:
            continue

        # Compare all other books
        for bm in bookmakers:
            if bm.get("key", "").lower() == sharp_book:
                continue

            for market in bm.get("markets", []):
                if market.get("key") == "spreads":
                    outcomes = market.get("outcomes", [])
                    for outcome in outcomes:
                        book_line = outcome.get("point")
                        if book_line is not None:
                            diff = abs(book_line - sharp_line)
                            if diff >= 1.0:
                                stale.append({
                                    "game": f"{game.get('home_team', '?')} vs {game.get('away_team', '?')}",
                                    "book": bm.get("title", bm.get("key")),
                                    "book_line": book_line,
                                    "sharp_line": sharp_line,
                                    "difference": round(diff, 1),
                                    "team": outcome.get("name"),
                                })

    return stale
