"""
Test Model Sentiment — fetches pre-game headlines via GNews/NewsAPI
and scores with VADER.  Graceful degradation when no API keys set.
"""

import os
import requests

_GNEWS_KEY = os.environ.get("GNEWS_API_KEY")
_NEWSAPI_KEY = os.environ.get("NEWSAPI_KEY")

# Lazy-loaded VADER singleton
_vader = None


def _get_vader():
    global _vader
    if _vader is None:
        try:
            from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
            _vader = SentimentIntensityAnalyzer()
        except ImportError:
            _vader = False  # Sentinel: library not installed
    return _vader if _vader is not False else None


def _fetch_gnews(query, max_results=10):
    """Fetch headlines from GNews API."""
    if not _GNEWS_KEY:
        return []
    try:
        resp = requests.get(
            "https://gnews.io/api/v4/search",
            params={
                "q": query,
                "lang": "en",
                "max": max_results,
                "apikey": _GNEWS_KEY,
            },
            timeout=8,
        )
        if resp.status_code != 200:
            return []
        data = resp.json()
        return [a.get("title", "") for a in data.get("articles", [])]
    except Exception:
        return []


def _fetch_newsapi(query, max_results=10):
    """Fetch headlines from NewsAPI.org as fallback."""
    if not _NEWSAPI_KEY:
        return []
    try:
        resp = requests.get(
            "https://newsapi.org/v2/everything",
            params={
                "q": query,
                "language": "en",
                "pageSize": max_results,
                "sortBy": "publishedAt",
                "apiKey": _NEWSAPI_KEY,
            },
            timeout=8,
        )
        if resp.status_code != 200:
            return []
        data = resp.json()
        return [a.get("title", "") for a in data.get("articles", [])]
    except Exception:
        return []


def _score_headlines(headlines):
    """Average VADER compound score for a list of headlines."""
    analyzer = _get_vader()
    if not analyzer or not headlines:
        return 0.0

    scores = []
    for headline in headlines:
        if headline:
            compound = analyzer.polarity_scores(headline)["compound"]
            scores.append(compound)

    return sum(scores) / len(scores) if scores else 0.0


def get_team_sentiment(team_name):
    """
    Get sentiment score for a team from news headlines.

    Returns:
        Float in [-1.0, 1.0] or None if unavailable
    """
    if not _GNEWS_KEY and not _NEWSAPI_KEY:
        return None

    if not _get_vader():
        return None

    query = f"{team_name} sports"

    # Try GNews first, then NewsAPI
    headlines = _fetch_gnews(query)
    if not headlines:
        headlines = _fetch_newsapi(query)

    if not headlines:
        return None

    return round(_score_headlines(headlines), 4)


def get_game_sentiment(home_team, away_team):
    """
    Get sentiment data for both teams in a game.

    Returns:
        Dict with {home_sentiment, away_sentiment, sentiment_diff, has_sentiment}
        or None if no API keys / VADER unavailable.
    """
    if not _GNEWS_KEY and not _NEWSAPI_KEY:
        return None

    if not _get_vader():
        return None

    home_sent = get_team_sentiment(home_team)
    away_sent = get_team_sentiment(away_team)

    if home_sent is None and away_sent is None:
        return None

    home_val = home_sent if home_sent is not None else 0.0
    away_val = away_sent if away_sent is not None else 0.0

    return {
        "home_sentiment": home_val,
        "away_sentiment": away_val,
        "sentiment_diff": round(home_val - away_val, 4),
        "has_sentiment": 1,
    }
