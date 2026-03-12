"""
Locust load test scenarios for Sports Prop Projections.

Three user classes weighted by realistic traffic patterns:
  - CasualVisitor (50%): Browse games, scan sports
  - PowerUser (30%): Browse + scan + load props
  - AdminUser (20%): Check bets, grade, dashboard

Usage:
    # Start mock server first (uses port 5055 to avoid conflicts):
    python tests/mock_server.py

    # Then in another terminal:
    python -m locust -f locustfile.py -H http://localhost:5055
    # Open http://localhost:8089 in browser

    # Or headless:
    python -m locust -f locustfile.py -H http://localhost:5055 --headless -u 50 -r 1 --run-time 3m
"""

import random
from locust import HttpUser, task, between


class CasualVisitor(HttpUser):
    """Casual user: browses games, triggers scans."""

    weight = 50
    wait_time = between(3, 8)

    @task(5)
    def browse_games(self):
        sport = random.choice(["nba", "nhl", "cbb", "cfb", "nfl"])
        self.client.get(f"/api/games?sport={sport}", name="/api/games")

    @task(3)
    def scan_sport(self):
        sport = random.choice(["nba", "nhl", "cbb"])
        self.client.post("/api/scan", json={"sport": sport}, name="/api/scan")

    @task(1)
    def check_dashboard(self):
        self.client.get("/api/dashboard?sport=nba", name="/api/dashboard")

    @task(1)
    def model_health(self):
        self.client.get("/api/model-health", name="/api/model-health")


class PowerUser(HttpUser):
    """Power user: browses + scans + loads props."""

    weight = 30
    wait_time = between(5, 15)

    @task(3)
    def browse_and_scan(self):
        sport = random.choice(["nba", "nhl", "cbb"])
        self.client.get(f"/api/games?sport={sport}", name="/api/games")
        self.client.post("/api/scan", json={"sport": sport}, name="/api/scan")

    @task(2)
    def load_single_props(self):
        event_id = str(400000 + random.randint(0, 7))
        sport = random.choice(["nba", "cbb"])
        self.client.get(
            f"/api/props?event_id={event_id}&sport={sport}",
            name="/api/props",
        )

    @task(1)
    def top_props_batch(self):
        sport = random.choice(["nba", "cbb", "nhl"])
        self.client.get(f"/api/top-props?sport={sport}", name="/api/top-props")

    @task(1)
    def ev_props(self):
        sport = random.choice(["nba", "cbb"])
        self.client.get(
            f"/api/ev/player-props?sport={sport}",
            name="/api/ev/player-props",
        )


class AdminUser(HttpUser):
    """Admin user: checks bets, grades, dashboard."""

    weight = 20
    wait_time = between(10, 30)

    @task(3)
    def check_bets_combined(self):
        self.client.get("/api/bets/combined", name="/api/bets/combined")

    @task(1)
    def bets_dashboard(self):
        self.client.get("/api/bets/dashboard", name="/api/bets/dashboard")

    @task(1)
    def grade_bets(self):
        sport = random.choice(["nba", "nhl", "cbb"])
        self.client.post(
            "/api/bets/grade",
            json={"sport": sport},
            name="/api/bets/grade",
        )
