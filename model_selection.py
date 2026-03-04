"""
Model Selection — compares rules-based vs EV model OOS performance per sport
and provides a cached validation tier for production gating.
"""

import time
import json

# ─── Cache ────────────────────────────────────────────────────────────────
_tier_cache = {}  # sport -> (tier, best_oos, best_model, timestamp)
_TIER_TTL = 300   # 5 minutes


def get_model_comparison(sport):
    """
    Compare rules OOS vs EV OOS for a sport.

    Returns:
        {
            rules_oos: {accuracy, roi} or None,
            ev_oos: {accuracy, roi} or None,
            best_model: "ev" | "rules" | None,
            best_oos_accuracy: float or None,
            validation_tier: "validated" | "caution" | "degraded",
        }
    """
    from constants import BREAKEVEN_RATE

    try:
        from test_model import db as tm_db
    except ImportError:
        return {
            "rules_oos": None, "ev_oos": None,
            "best_model": None, "best_oos_accuracy": None,
            "validation_tier": "degraded",
        }

    # ── Rules OOS (from walkforward run) ──
    rules_oos = None
    wf_run = tm_db.get_latest_model_run(sport, "walkforward")
    if wf_run:
        rules_oos = {
            "accuracy": wf_run.get("accuracy"),
            "roi": wf_run.get("roi"),
        }

    # ── EV OOS (from ev_logistic run) ──
    ev_oos = None
    ev_run = tm_db.get_latest_model_run(sport, "ev_logistic")
    if ev_run:
        mp = ev_run.get("model_params") or {}
        rv = mp.get("rolling_validation") or {}
        ev_acc = rv.get("mean_accuracy") or ev_run.get("accuracy")
        ev_roi = rv.get("oos_roi") or ev_run.get("roi")
        if ev_acc is not None:
            ev_oos = {"accuracy": ev_acc, "roi": ev_roi}

    # ── Determine best model ──
    rules_acc = rules_oos["accuracy"] if rules_oos else None
    ev_acc_val = ev_oos["accuracy"] if ev_oos else None

    best_model = None
    best_oos = None

    if rules_acc is not None and ev_acc_val is not None:
        if ev_acc_val >= rules_acc:
            best_model = "ev"
            best_oos = ev_acc_val
        else:
            best_model = "rules"
            best_oos = rules_acc
    elif rules_acc is not None:
        best_model = "rules"
        best_oos = rules_acc
    elif ev_acc_val is not None:
        best_model = "ev"
        best_oos = ev_acc_val

    # ── Validation tier ──
    if best_oos is not None and best_oos >= 55.0:
        tier = "validated"
    elif best_oos is not None and best_oos >= BREAKEVEN_RATE:
        tier = "caution"
    else:
        tier = "degraded"

    return {
        "rules_oos": rules_oos,
        "ev_oos": ev_oos,
        "best_model": best_model,
        "best_oos_accuracy": best_oos,
        "validation_tier": tier,
    }


def get_validation_tier(sport):
    """
    Cached quick lookup for production use.

    Returns:
        (tier, best_oos_accuracy, best_model_type)
    """
    now = time.time()
    cached = _tier_cache.get(sport)
    if cached:
        tier, best_oos, best_model, ts = cached
        if now - ts < _TIER_TTL:
            return tier, best_oos, best_model

    try:
        comp = get_model_comparison(sport)
        tier = comp["validation_tier"]
        best_oos = comp["best_oos_accuracy"]
        best_model = comp["best_model"]
    except Exception:
        tier = "degraded"
        best_oos = None
        best_model = None

    _tier_cache[sport] = (tier, best_oos, best_model, now)
    return tier, best_oos, best_model
