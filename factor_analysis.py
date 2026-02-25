"""
Factor Analysis Module — identifies multicollinearity, double-counting,
and redundancy among scoring factors.

For each factor, computes:
  - Standalone lift: accuracy when factor fires vs doesn't fire
  - Marginal lift (leave-one-out): accuracy change when factor's score
    contribution is removed from all games
  - Correlation matrix: pairwise Pearson correlation of binary factor firings
  - VIF: variance inflation factor (VIF > 5 = serious multicollinearity)

Identifies factor clusters — groups that fire together — and generates
actionable recommendations when double-counting is detected.
"""

import numpy as np

# Lean thresholds (minimum score to be "actionable") per sport
_LEAN_THRESHOLDS = {
    "nba": 5,
    "nhl": 3,
    "cbb": 10,
    "cfb": 12,
    "nfl": 10,
}

# Known cluster templates for labeling discovered clusters
_CLUSTER_TEMPLATES = [
    {
        "name": "Market Signals",
        "factors": {"slot_public", "line_movement", "line_toward_dog", "line_toward_fav"},
    },
    {
        "name": "Spread Adjustments",
        "factors": {"spread_sweet_spot", "spread_penalty"},
    },
    {
        "name": "Team Form",
        "factors": {"b2b_bonus", "b2b_penalty", "ats_bonus", "ats_penalty", "vegas_trap"},
    },
    {
        "name": "Matchup Context",
        "factors": {"rank_scam", "spread_discrepancy", "h2h_revenge", "h2h_dominance"},
    },
]

# Factor tracker name -> breakdown key mapping
_FACTOR_TO_BREAKDOWN = {
    "slot_public": "slot",
    "line_movement": "line_movement",
    "line_toward_dog": "line_direction",
    "line_toward_fav": "line_direction",
    "rank_scam": "rank_scam",
    "spread_discrepancy": "spread_discrepancy",
    "home_away_split": "home_away_split",
    "b2b_bonus": "b2b",
    "b2b_penalty": "b2b",
    "h2h_revenge": "head_to_head",
    "h2h_dominance": "head_to_head",
    "vegas_trap": "vegas_trap",
    "trend_discrepancy": "trend_discrepancy",
    "ou_discrepancy": "overunder",
    "ats_bonus": "ats_record",
    "ats_penalty": "ats_record",
    "spread_sweet_spot": "spread_penalty",
    "spread_penalty": "spread_penalty",
    "day_penalty": "day_penalty",
}

MIN_FIRE_COUNT = 5  # Minimum fires to include a factor
MIN_RECORDS = 30    # Minimum games for meaningful analysis


def run_factor_analysis(factor_records, sport):
    """
    Full factor analysis from per-game backtest records.

    Args:
        factor_records: list of dicts, each with:
            - score (int): total confirmation score
            - correct (bool): did the lean team cover?
            - breakdown (dict): score contributions from _calculate_score
            - factors (dict): binary flags for each tracked factor
        sport: sport string

    Returns:
        dict with standalone_lift, marginal_lift, correlation_matrix,
        vif_scores, clusters, recommendations, factor_names.
        None if insufficient data.
    """
    if len(factor_records) < MIN_RECORDS:
        return None

    # Get factor names that fired at least MIN_FIRE_COUNT times
    fire_counts = {}
    for r in factor_records:
        for k, v in r["factors"].items():
            if v:
                fire_counts[k] = fire_counts.get(k, 0) + 1

    factor_names = sorted(n for n, c in fire_counts.items() if c >= MIN_FIRE_COUNT)

    if len(factor_names) < 2:
        return None

    # Build binary matrix (n_games x n_factors)
    n = len(factor_records)
    binary_matrix = np.zeros((n, len(factor_names)), dtype=float)
    for i, r in enumerate(factor_records):
        for j, name in enumerate(factor_names):
            if r["factors"].get(name, False):
                binary_matrix[i, j] = 1.0

    standalone = _compute_standalone_lift(factor_records, factor_names)
    marginal = _compute_marginal_lift(factor_records, sport)
    corr = _compute_correlation_matrix(binary_matrix, factor_names)
    vif = _compute_vif(binary_matrix, factor_names)
    clusters = _identify_clusters(corr, factor_names, factor_records, sport)
    recommendations = _generate_recommendations(
        standalone, marginal, vif, clusters, corr, factor_names
    )

    return {
        "standalone_lift": standalone,
        "marginal_lift": marginal,
        "correlation_matrix": corr,
        "vif_scores": vif,
        "clusters": clusters,
        "recommendations": recommendations,
        "factor_names": factor_names,
    }


def _compute_standalone_lift(factor_records, factor_names):
    """Accuracy when factor fires vs doesn't fire."""
    result = {}

    for name in factor_names:
        fired_correct = 0
        fired_total = 0
        not_fired_correct = 0
        not_fired_total = 0

        for r in factor_records:
            if r["factors"].get(name, False):
                fired_total += 1
                if r["correct"]:
                    fired_correct += 1
            else:
                not_fired_total += 1
                if r["correct"]:
                    not_fired_correct += 1

        acc_fired = round(fired_correct / fired_total * 100, 2) if fired_total > 0 else 0
        acc_not = round(not_fired_correct / not_fired_total * 100, 2) if not_fired_total > 0 else 0
        lift = round(acc_fired - acc_not, 2) if fired_total > 0 and not_fired_total > 0 else 0

        result[name] = {
            "fired": fired_total,
            "accuracy_fired": acc_fired,
            "accuracy_not_fired": acc_not,
            "lift": lift,
        }

    return result


def _compute_marginal_lift(factor_records, sport):
    """
    Leave-one-out analysis: for each breakdown key, remove its score
    contribution and measure how accuracy of actionable games changes.

    marginal_lift = full_accuracy - without_accuracy
      > 0: removing the factor hurts accuracy (factor helps)
      < 0: removing the factor helps accuracy (factor hurts)
      ~ 0: factor is redundant
    """
    threshold = _LEAN_THRESHOLDS.get(sport, 5)

    # Full model
    actionable = [r for r in factor_records if r["score"] >= threshold]
    full_count = len(actionable)
    full_correct = sum(1 for r in actionable if r["correct"])
    full_acc = round(full_correct / full_count * 100, 2) if full_count > 0 else 0

    # Discover active breakdown keys
    breakdown_keys = set()
    for r in factor_records:
        for k, v in r["breakdown"].items():
            if v != 0:
                breakdown_keys.add(k)

    result = {}
    for key in sorted(breakdown_keys):
        without_correct = 0
        without_count = 0
        tipped_correct = 0
        tipped_count = 0

        for r in factor_records:
            contribution = r["breakdown"].get(key, 0)
            modified_score = max(0, r["score"] - contribution)
            is_actionable = r["score"] >= threshold
            would_be = modified_score >= threshold

            if would_be:
                without_count += 1
                if r["correct"]:
                    without_correct += 1

            # Games tipped in by this factor (actionable only because of it)
            if is_actionable and not would_be:
                tipped_count += 1
                if r["correct"]:
                    tipped_correct += 1

        without_acc = round(without_correct / without_count * 100, 2) if without_count > 0 else 0
        tipped_acc = round(tipped_correct / tipped_count * 100, 2) if tipped_count > 0 else 0
        marginal = round(full_acc - without_acc, 2)

        result[key] = {
            "full_accuracy": full_acc,
            "full_count": full_count,
            "without_accuracy": without_acc,
            "without_count": without_count,
            "marginal_lift": marginal,
            "games_tipped_in": tipped_count,
            "tipped_accuracy": tipped_acc,
        }

    return result


def _compute_correlation_matrix(binary_matrix, factor_names):
    """Pairwise Pearson correlation of binary factor firings."""
    n_factors = len(factor_names)
    variances = np.var(binary_matrix, axis=0)
    valid = variances > 0

    matrix = np.zeros((n_factors, n_factors))
    valid_indices = np.where(valid)[0]

    if len(valid_indices) >= 2:
        valid_data = binary_matrix[:, valid_indices]
        corr = np.corrcoef(valid_data, rowvar=False)

        for i, vi in enumerate(valid_indices):
            for j, vj in enumerate(valid_indices):
                val = corr[i, j]
                matrix[vi, vj] = round(float(val), 3) if not np.isnan(val) else 0.0

    for i in range(n_factors):
        matrix[i, i] = 1.0

    return {
        "factors": factor_names,
        "matrix": matrix.tolist(),
    }


def _compute_vif(binary_matrix, factor_names):
    """
    Variance Inflation Factor for each factor.
    VIF > 5 = serious multicollinearity.
    VIF > 10 = extreme multicollinearity.
    """
    n_samples, n_factors = binary_matrix.shape

    if n_factors < 2 or n_samples < n_factors + 1:
        return {name: None for name in factor_names}

    result = {}
    for i, name in enumerate(factor_names):
        y = binary_matrix[:, i]

        if np.std(y) == 0:
            result[name] = 1.0
            continue

        X = np.delete(binary_matrix, i, axis=1)
        X = np.column_stack([np.ones(n_samples), X])

        try:
            beta, _, _, _ = np.linalg.lstsq(X, y, rcond=None)
            y_pred = X @ beta
            ss_res = np.sum((y - y_pred) ** 2)
            ss_tot = np.sum((y - np.mean(y)) ** 2)

            if ss_tot == 0:
                result[name] = 1.0
                continue

            r_sq = max(0.0, 1.0 - ss_res / ss_tot)
            result[name] = round(1.0 / (1.0 - r_sq), 2) if r_sq < 0.999 else 999.0
        except Exception:
            result[name] = None

    return result


def _factors_to_breakdown_keys(names):
    """Map factor tracker names to unique breakdown keys."""
    keys = set()
    for name in names:
        if name in _FACTOR_TO_BREAKDOWN:
            keys.add(_FACTOR_TO_BREAKDOWN[name])
    return keys


def _identify_clusters(corr_data, factor_names, factor_records, sport):
    """
    Discover clusters from correlation matrix using union-find.
    Any pair with |correlation| > 0.3 gets grouped together.
    """
    matrix = corr_data["matrix"]
    n = len(factor_names)
    threshold = _LEAN_THRESHOLDS.get(sport, 5)

    # Union-find
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x, y):
        px, py = find(x), find(y)
        if px != py:
            parent[px] = py

    CORR_THRESHOLD = 0.3
    for i in range(n):
        for j in range(i + 1, n):
            if abs(matrix[i][j]) > CORR_THRESHOLD:
                union(i, j)

    # Group by root
    groups = {}
    for i in range(n):
        root = find(i)
        if root not in groups:
            groups[root] = []
        groups[root].append(i)

    # Full model accuracy (for cluster marginal lift)
    actionable = [r for r in factor_records if r["score"] >= threshold]
    full_count = len(actionable)
    full_correct = sum(1 for r in actionable if r["correct"])
    full_acc = round(full_correct / full_count * 100, 2) if full_count > 0 else 0

    clusters = []
    for root, indices in groups.items():
        if len(indices) < 2:
            continue

        names = [factor_names[i] for i in indices]

        # Average pairwise correlation
        pair_corrs = []
        for i_idx in range(len(indices)):
            for j_idx in range(i_idx + 1, len(indices)):
                pair_corrs.append(abs(matrix[indices[i_idx]][indices[j_idx]]))
        avg_corr = round(sum(pair_corrs) / len(pair_corrs), 3) if pair_corrs else 0

        # Cluster marginal lift: remove ALL factors in the cluster at once
        cluster_bk_keys = _factors_to_breakdown_keys(names)

        without_count = 0
        without_correct = 0
        for r in factor_records:
            total_contrib = sum(r["breakdown"].get(bk, 0) for bk in cluster_bk_keys)
            modified = max(0, r["score"] - total_contrib)
            if modified >= threshold:
                without_count += 1
                if r["correct"]:
                    without_correct += 1

        without_acc = round(without_correct / without_count * 100, 2) if without_count > 0 else 0
        cluster_marginal = round(full_acc - without_acc, 2)

        # Combined weight: max possible contribution from this cluster
        combined_weight = 0
        for r in factor_records:
            w = sum(r["breakdown"].get(bk, 0) for bk in cluster_bk_keys)
            if w > combined_weight:
                combined_weight = w

        # Match against known templates
        matched_template = None
        for template in _CLUSTER_TEMPLATES:
            overlap = set(names) & template["factors"]
            if len(overlap) >= 2:
                matched_template = template["name"]
                break

        clusters.append({
            "factors": names,
            "avg_correlation": avg_corr,
            "cluster_marginal_lift": cluster_marginal,
            "combined_max_weight": combined_weight,
            "template_match": matched_template,
        })

    # Sort by avg_correlation descending
    clusters.sort(key=lambda c: c["avg_correlation"], reverse=True)
    return clusters


def _generate_recommendations(standalone, marginal, vif, clusters, corr_data, factor_names):
    """Generate actionable recommendations based on all analyses."""
    recs = []
    matrix = corr_data["matrix"]

    # 1. High VIF (multicollinearity)
    for name, vif_val in vif.items():
        if vif_val is None or vif_val <= 5:
            continue

        idx = factor_names.index(name) if name in factor_names else -1
        correlated_with = []
        if idx >= 0:
            for j, other in enumerate(factor_names):
                if j != idx and abs(matrix[idx][j]) > 0.3:
                    correlated_with.append(other)

        sl = standalone.get(name, {}).get("lift", 0)
        bk_keys = _factors_to_breakdown_keys([name])
        ml = 0
        for bk in bk_keys:
            if bk in marginal:
                ml = marginal[bk].get("marginal_lift", 0)
                break

        corr_str = ", ".join(correlated_with[:3]) if correlated_with else "other factors"
        severity = "high" if vif_val > 10 else "medium"

        msg = (
            f"{name} has VIF {vif_val} (correlated with {corr_str}). "
            f"Standalone lift: {sl:+.1f}%, marginal lift: {ml:+.1f}%. "
        )
        if abs(ml) < abs(sl) * 0.3 and abs(sl) > 3:
            msg += "Consider reducing weight or merging with correlated factors."
        else:
            msg += "Marginal contribution is meaningful despite correlation."

        recs.append({
            "factor": name,
            "type": "multicollinearity",
            "severity": severity,
            "message": msg,
        })

    # 2. Double-counting: high standalone but low marginal
    for key, m in marginal.items():
        # Reverse-map breakdown key to a representative factor name
        reverse_map = {
            "slot": "slot_public", "line_movement": "line_movement",
            "line_direction": "line_toward_dog", "rank_scam": "rank_scam",
            "spread_discrepancy": "spread_discrepancy",
            "home_away_split": "home_away_split", "b2b": "b2b_bonus",
            "head_to_head": "h2h_revenge", "vegas_trap": "vegas_trap",
            "trend_discrepancy": "trend_discrepancy", "overunder": "ou_discrepancy",
            "ats_record": "ats_bonus", "spread_penalty": "spread_penalty",
            "day_penalty": "day_penalty", "trell": "trell",
            "public_betting": "public_betting", "feedback": "feedback",
            "weather": "weather",
        }
        factor_name = reverse_map.get(key, key)
        sl = standalone.get(factor_name, {})
        standalone_lift = sl.get("lift", 0)
        marginal_lift = m.get("marginal_lift", 0)

        if abs(standalone_lift) > 5 and abs(marginal_lift) < abs(standalone_lift) * 0.2:
            recs.append({
                "factor": key,
                "type": "double_counting",
                "severity": "medium",
                "message": (
                    f"{key} has standalone lift {standalone_lift:+.1f}% but marginal lift "
                    f"of only {marginal_lift:+.1f}% after controlling for other factors. "
                    f"This suggests overlap with other signals. Consider reducing weight."
                ),
            })

    # 3. Cluster overlap
    for cluster in clusters:
        if len(cluster["factors"]) < 2:
            continue

        individual_sum = 0
        for fname in cluster["factors"]:
            bk_keys = _factors_to_breakdown_keys([fname])
            for bk in bk_keys:
                if bk in marginal:
                    individual_sum += abs(marginal[bk].get("marginal_lift", 0))
                    break

        cluster_ml = abs(cluster.get("cluster_marginal_lift", 0))

        if individual_sum > 0 and cluster_ml < individual_sum * 0.6:
            overlap_pct = round((1 - cluster_ml / individual_sum) * 100)
            factors_str = ", ".join(cluster["factors"])
            label = cluster.get("template_match") or "Cluster"

            recs.append({
                "factor": factors_str,
                "type": "cluster_overlap",
                "severity": "high" if overlap_pct > 50 else "medium",
                "message": (
                    f"{label} [{factors_str}] (avg corr {cluster['avg_correlation']:.2f}): "
                    f"individual marginal lifts sum to {individual_sum:.1f}% but cluster "
                    f"marginal lift is only {cluster_ml:.1f}% — ~{overlap_pct}% overlap. "
                    f"Consider using highest-weighted factor and reducing others."
                ),
            })

    # 4. Harmful factors (negative marginal lift with enough tipped games)
    for key, m in marginal.items():
        if m.get("marginal_lift", 0) < -2 and m.get("games_tipped_in", 0) >= 5:
            recs.append({
                "factor": key,
                "type": "harmful",
                "severity": "high",
                "message": (
                    f"{key} has negative marginal lift ({m['marginal_lift']:+.1f}%): "
                    f"it tips in {m['games_tipped_in']} games with only "
                    f"{m['tipped_accuracy']:.1f}% accuracy (below baseline "
                    f"{m['full_accuracy']:.1f}%). Consider removing or reducing weight."
                ),
            })

    severity_order = {"high": 0, "medium": 1, "low": 2}
    recs.sort(key=lambda r: severity_order.get(r["severity"], 2))
    return recs
