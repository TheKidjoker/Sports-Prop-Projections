"""
Joker's Edge - Automated Daily Job

Two modes:
  scan   (11 AM)  - Scan all sports, save qualifying predictions
  grade  (1 AM)   - Grade all pending predictions with final scores

Usage:
  python daily_job.py scan
  python daily_job.py grade
"""

import argparse
import logging
import sys
import os
from logging.handlers import RotatingFileHandler

# Ensure project root is on path so imports work from Task Scheduler
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_DIR)

from game_scanner import scan_all_games
import tracker

SPORTS = ["nba", "nhl", "nfl", "cfb", "cbb"]
LOG_PATH = os.path.join(PROJECT_DIR, "daily_job.log")
IS_PRODUCTION = bool(os.environ.get("DATABASE_URL"))


def setup_logging():
    """Configure logging. File + console locally, stdout-only in production."""
    logger = logging.getLogger("daily_job")
    logger.setLevel(logging.INFO)

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

    if not IS_PRODUCTION:
        file_handler = RotatingFileHandler(
            LOG_PATH, maxBytes=1_000_000, backupCount=30
        )
        file_handler.setFormatter(fmt)
        logger.addHandler(file_handler)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(fmt)
    logger.addHandler(console_handler)

    return logger


def run_scan(logger):
    """Scan all sports and save predictions."""
    logger.info("=== SCAN START ===")
    tracker.init_db()

    total_saved = 0
    for sport in SPORTS:
        try:
            results = scan_all_games(sport)
            games_scanned = len(results)

            # Count qualifying predictions (same filter as tracker.save_predictions)
            qualifying = [
                g for g in results
                if not g.get("skip")
                and (g.get("cover_pct") or 0) >= 68.5
                and g.get("lean_team")
                and g.get("action")
            ]

            tracker.save_predictions(results, sport)
            total_saved += len(qualifying)

            logger.info(
                "%s: %d games scanned, %d predictions saved",
                sport.upper(), games_scanned, len(qualifying),
            )
        except Exception:
            logger.exception("Error scanning %s", sport.upper())

    logger.info("=== SCAN COMPLETE - %d total predictions saved ===", total_saved)


def run_grade(logger):
    """Grade all pending predictions."""
    logger.info("=== GRADE START ===")
    tracker.init_db()

    try:
        result = tracker.grade_predictions()
        graded = result.get("graded", 0)
        summary = result.get("summary", {})

        hits = summary.get("hit", 0)
        misses = summary.get("miss", 0)
        pushes = summary.get("push", 0)
        not_final = summary.get("not_final", 0)

        logger.info(
            "Graded %d predictions - HIT: %d, MISS: %d, PUSH: %d, Not Final: %d",
            graded, hits, misses, pushes, not_final,
        )
    except Exception:
        logger.exception("Error grading predictions")
        raise

    logger.info("=== GRADE COMPLETE ===")


def main():
    parser = argparse.ArgumentParser(
        description="Joker's Edge - Automated daily scan & grade",
    )
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("scan", help="Scan all sports and save predictions (11 AM)")
    sub.add_parser("grade", help="Grade all pending predictions (1 AM)")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    logger = setup_logging()

    try:
        if args.command == "scan":
            run_scan(logger)
        elif args.command == "grade":
            run_grade(logger)
    except Exception:
        logger.exception("Fatal error in %s", args.command)
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
