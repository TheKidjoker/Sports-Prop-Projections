"""
Discord Webhook Notifications — fire-and-forget alerts for picks and grading results.

Sends embedded messages to a Discord channel via webhook URL.
Configured via DISCORD_WEBHOOK_URL environment variable.
"""

import os
import requests
from datetime import datetime, timezone


class DiscordWebhook:
    """Sends formatted pick alerts and summaries to Discord."""

    def __init__(self, webhook_url=None):
        self._url = webhook_url or os.environ.get("DISCORD_WEBHOOK_URL", "")

    def is_configured(self):
        """Returns True if a webhook URL is set."""
        return bool(self._url)

    def send_picks(self, picks, sport):
        """
        Send individual pick embeds to Discord.

        Args:
            picks: List of game result dicts from scan_all_games
            sport: Sport key (e.g. "nba")
        """
        if not self.is_configured() or not picks:
            return

        embeds = []
        for pick in picks[:10]:  # Discord limits to 10 embeds per message
            rec = pick.get("recommendation", "MONITOR")
            lean = pick.get("lean_team", "TBD")
            cover = pick.get("cover_pct", 0)
            action = pick.get("action", "")
            spread = pick.get("current_spread")
            home = pick.get("home_team", "")
            away = pick.get("away_team", "")
            game_time = pick.get("game_time_est", "")

            # Color by tier
            color = {
                "STRONG PLAY": 0x00FF00,  # Green
                "CONFIDENT": 0xFFD700,    # Gold
                "LEAN": 0x87CEEB,         # Light blue
            }.get(rec, 0x808080)

            spread_str = f"{spread:+.1f}" if spread is not None else "N/A"

            embed = {
                "title": f"{rec}: {lean}",
                "description": action or f"Lean {lean} {spread_str}",
                "color": color,
                "fields": [
                    {"name": "Matchup", "value": f"{away} @ {home}", "inline": True},
                    {"name": "Spread", "value": spread_str, "inline": True},
                    {"name": "Cover %", "value": f"{cover:.1f}%", "inline": True},
                    {"name": "Time", "value": game_time or "TBD", "inline": True},
                ],
                "footer": {"text": f"Joker's Edge | {sport.upper()}"},
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            # Add best line if available
            best_line = pick.get("best_line")
            if best_line:
                embed["fields"].append({
                    "name": "Best Line",
                    "value": f"{best_line['book']} {best_line['spread']:+.1f}",
                    "inline": True,
                })

            embeds.append(embed)

        if embeds:
            self._send({"embeds": embeds})

    def send_daily_summary(self, scan_results_by_sport):
        """
        Send a summary embed after daily scan.

        Args:
            scan_results_by_sport: Dict mapping sport -> list of game results
        """
        if not self.is_configured():
            return

        total_picks = 0
        sport_lines = []
        top_pick = None
        top_cover = 0

        for sport, results in scan_results_by_sport.items():
            qualifying = [
                g for g in results
                if not g.get("skip")
                and (g.get("cover_pct") or 0) >= 68.5
                and g.get("lean_team")
                and g.get("recommendation") in ("STRONG PLAY", "CONFIDENT", "LEAN")
            ]
            total_picks += len(qualifying)
            if qualifying:
                sport_lines.append(f"**{sport.upper()}**: {len(qualifying)} picks")

            for g in qualifying:
                if (g.get("cover_pct") or 0) > top_cover:
                    top_cover = g.get("cover_pct", 0)
                    top_pick = g

        if total_picks == 0:
            self._send({
                "embeds": [{
                    "title": "Daily Scan Complete",
                    "description": "No qualifying picks found today.",
                    "color": 0x808080,
                    "footer": {"text": "Joker's Edge"},
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }]
            })
            return

        description = "\n".join(sport_lines)
        if top_pick:
            description += (
                f"\n\n**Top Pick**: {top_pick.get('lean_team', '?')} "
                f"({top_pick.get('recommendation', '?')}) — "
                f"{top_cover:.1f}% cover"
            )

        self._send({
            "embeds": [{
                "title": f"Daily Scan: {total_picks} Picks Across {len(scan_results_by_sport)} Sports",
                "description": description,
                "color": 0x00FF00 if total_picks > 0 else 0x808080,
                "footer": {"text": "Joker's Edge"},
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }]
        })

    def send_grade_results(self, grade_summary):
        """
        Send grading results embed.

        Args:
            grade_summary: Dict with graded, summary (hit/miss/push counts)
        """
        if not self.is_configured():
            return

        graded = grade_summary.get("graded", 0)
        summary = grade_summary.get("summary", {})
        hits = summary.get("hit", 0)
        misses = summary.get("miss", 0)
        pushes = summary.get("push", 0)
        not_final = summary.get("not_final", 0)

        total_decided = hits + misses
        win_rate = round(hits / total_decided * 100, 1) if total_decided > 0 else 0
        roi = round((hits * (100 / 110) - misses) / total_decided * 100, 1) if total_decided > 0 else 0

        color = 0x00FF00 if win_rate >= 55 else (0xFFD700 if win_rate >= 50 else 0xFF0000)

        self._send({
            "embeds": [{
                "title": f"Grading Complete: {hits}-{misses}-{pushes}",
                "description": f"Win Rate: **{win_rate}%** | ROI: **{roi:+.1f}%**",
                "color": color,
                "fields": [
                    {"name": "Graded", "value": str(graded), "inline": True},
                    {"name": "Hits", "value": str(hits), "inline": True},
                    {"name": "Misses", "value": str(misses), "inline": True},
                    {"name": "Pushes", "value": str(pushes), "inline": True},
                    {"name": "Not Final", "value": str(not_final), "inline": True},
                ],
                "footer": {"text": "Joker's Edge"},
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }]
        })

    def _send(self, payload):
        """POST to webhook URL. Never raises (fire-and-forget)."""
        if not self._url:
            return
        try:
            requests.post(self._url, json=payload, timeout=10)
        except Exception:
            pass  # Fire and forget — don't break caller
