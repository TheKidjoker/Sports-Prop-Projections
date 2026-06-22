"""
Automated Scheduler — runs scans, grading, and closing line fetches on a schedule.

Uses APScheduler BackgroundScheduler to run jobs inside the Flask app process.
Enabled via ENABLE_SCHEDULER=true environment variable.
"""

import os
import logging
from datetime import datetime, timezone

logger = logging.getLogger("scheduler")

_scheduler = None


def init_scheduler():
    """
    Create and start a BackgroundScheduler with 3 jobs:
    1. Morning scan (11:00 AM ET / 16:00 UTC)
    2. Closing lines (multiple windows: noon, 1pm, 6pm ET)
    3. Night grading (1:00 AM ET / 06:00 UTC)
    """
    global _scheduler
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
    except ImportError:
        logger.warning("APScheduler not installed — scheduler disabled")
        return

    _scheduler = BackgroundScheduler(timezone="UTC")

    # Morning scan: 11:00 AM ET = 16:00 UTC (15:00 UTC during DST)
    _scheduler.add_job(
        _morning_scan,
        "cron",
        hour=16, minute=0,
        id="morning_scan",
        name="Morning Scan (11 AM ET)",
        misfire_grace_time=3600,
    )

    # Closing lines: noon ET (17:00 UTC), 1pm ET (18:00 UTC), 6pm ET (23:00 UTC)
    for hour_utc, label in [(17, "Noon ET"), (18, "1 PM ET"), (23, "6 PM ET")]:
        _scheduler.add_job(
            _fetch_closing_lines,
            "cron",
            hour=hour_utc, minute=0,
            id=f"close_lines_{hour_utc}",
            name=f"Closing Lines ({label})",
            misfire_grace_time=3600,
        )

    # Night grading: 1:00 AM ET = 06:00 UTC
    _scheduler.add_job(
        _night_grade,
        "cron",
        hour=6, minute=0,
        id="night_grade",
        name="Night Grading (1 AM ET)",
        misfire_grace_time=3600,
    )

    _scheduler.start()
    logger.info("Scheduler started with %d jobs", len(_scheduler.get_jobs()))


def _morning_scan():
    """Scan all sports, save predictions, send Discord summary."""
    from game_scanner import scan_all_games
    import tracker

    SPORTS = ["nba", "nhl", "nfl", "cfb", "cbb", "mlb"]
    tracker.init_db()

    scan_results = {}
    for sport in SPORTS:
        try:
            results = scan_all_games(sport)
            tracker.save_predictions(results, sport)
            scan_results[sport] = results
            logger.info("[scan] %s: %d games", sport.upper(), len(results))
        except Exception:
            logger.exception("[scan] Error scanning %s", sport.upper())

    # Send Discord summary
    try:
        from notifications import DiscordWebhook
        webhook = DiscordWebhook()
        if webhook.is_configured():
            webhook.send_daily_summary(scan_results)
    except Exception:
        logger.exception("[scan] Discord notification failed")


def _fetch_closing_lines():
    """Fetch closing lines for all sports."""
    import tracker

    SPORTS = ["nba", "nhl", "nfl", "cfb", "cbb", "mlb"]
    tracker.init_db()

    for sport in SPORTS:
        try:
            result = tracker.fetch_closing_lines(sport)
            logger.info("[close] %s: %d updated", sport.upper(), result.get("updated", 0))
        except Exception:
            logger.exception("[close] Error for %s", sport.upper())


def _night_grade():
    """Grade predictions, send Discord results."""
    import tracker

    tracker.init_db()

    try:
        result = tracker.grade_predictions()
        logger.info(
            "[grade] Graded %d — H:%d M:%d P:%d",
            result.get("graded", 0),
            result.get("summary", {}).get("hit", 0),
            result.get("summary", {}).get("miss", 0),
            result.get("summary", {}).get("push", 0),
        )

        # Send Discord results
        try:
            from notifications import DiscordWebhook
            webhook = DiscordWebhook()
            if webhook.is_configured():
                webhook.send_grade_results(result)
        except Exception:
            logger.exception("[grade] Discord notification failed")

    except Exception:
        logger.exception("[grade] Error grading predictions")


def get_scheduler_status():
    """
    Return scheduler status and upcoming job schedule.

    Returns:
        Dict with enabled flag and list of jobs with next run times.
    """
    if _scheduler is None:
        return {"enabled": False, "jobs": []}

    jobs = []
    for job in _scheduler.get_jobs():
        next_run = job.next_run_time
        jobs.append({
            "id": job.id,
            "name": job.name,
            "next_run": next_run.isoformat() if next_run else None,
        })

    return {"enabled": True, "jobs": jobs}
