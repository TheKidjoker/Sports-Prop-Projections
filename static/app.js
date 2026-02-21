document.addEventListener("DOMContentLoaded", function () {
    var form = document.getElementById("predict-form");
    var submitBtn = document.getElementById("submit-btn");
    var loading = document.getElementById("loading");
    var errorBanner = document.getElementById("error-banner");
    var results = document.getElementById("results");
    var scanBtn = document.getElementById("scan-btn");
    var scanLoading = document.getElementById("scan-loading");
    var scanResults = document.getElementById("scan-results");
    var teamInput = document.getElementById("team_name");
    var teamDropdown = document.getElementById("team-dropdown");

    var todaysGames = [];

    // Fetch today's games on page load for autocomplete + ticker
    fetch("/api/games")
        .then(function (res) { return res.json(); })
        .then(function (data) {
            todaysGames = data.games || [];
            buildTicker(todaysGames);
        })
        .catch(function () {
            todaysGames = [];
        });

    // Team autocomplete
    teamInput.addEventListener("input", function () {
        var query = teamInput.value.trim().toLowerCase();
        if (query.length < 2) {
            teamDropdown.classList.add("hidden");
            return;
        }

        var matches = todaysGames.filter(function (g) {
            return g.home_team.toLowerCase().indexOf(query) !== -1 ||
                   g.away_team.toLowerCase().indexOf(query) !== -1;
        });

        if (matches.length === 0) {
            teamDropdown.classList.add("hidden");
            return;
        }

        teamDropdown.innerHTML = "";
        matches.forEach(function (g) {
            var li = document.createElement("li");
            li.textContent = g.away_team + " vs " + g.home_team + " - " + g.game_time_est + " EST";
            li.addEventListener("click", function () {
                if (g.home_team.toLowerCase().indexOf(query) !== -1) {
                    teamInput.value = g.home_team;
                } else {
                    teamInput.value = g.away_team;
                }
                teamDropdown.classList.add("hidden");
            });
            teamDropdown.appendChild(li);
        });

        teamDropdown.classList.remove("hidden");
    });

    // Close dropdown when clicking outside
    document.addEventListener("click", function (e) {
        if (!teamInput.contains(e.target) && !teamDropdown.contains(e.target)) {
            teamDropdown.classList.add("hidden");
        }
    });

    // Quick Generate (Scan All Games)
    scanBtn.addEventListener("click", function () {
        scanBtn.disabled = true;
        scanLoading.classList.remove("hidden");
        scanResults.classList.add("hidden");

        fetch("/api/scan", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({})
        })
        .then(function (res) { return res.json(); })
        .then(function (data) {
            scanLoading.classList.add("hidden");
            scanBtn.disabled = false;

            if (!data.success) {
                showError(data.error || "Scan failed.");
                return;
            }

            renderScanResults(data.games || []);
        })
        .catch(function () {
            scanLoading.classList.add("hidden");
            scanBtn.disabled = false;
            showError("Network error during scan.");
        });
    });

    // Form submit
    form.addEventListener("submit", function (e) {
        e.preventDefault();

        results.classList.add("hidden");
        errorBanner.classList.add("hidden");

        var payload = {
            player_name: document.getElementById("player_name").value,
            vegas_line: parseFloat(document.getElementById("vegas_line").value),
            games: parseInt(document.getElementById("games").value, 10),
            team_name: document.getElementById("team_name").value
        };

        loading.classList.remove("hidden");
        submitBtn.disabled = true;

        fetch("/api/predict", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        })
        .then(function (res) {
            return res.json().then(function (data) {
                return { ok: res.ok, data: data };
            });
        })
        .then(function (result) {
            loading.classList.add("hidden");
            submitBtn.disabled = false;

            if (!result.ok || !result.data.success) {
                showError(result.data.error || "An unknown error occurred.");
                return;
            }

            renderResults(result.data);
        })
        .catch(function (err) {
            loading.classList.add("hidden");
            submitBtn.disabled = false;
            showError("Network error: could not reach the server.");
        });
    });

    function showError(message) {
        errorBanner.textContent = message;
        errorBanner.classList.remove("hidden");
    }

    function renderResults(data) {
        // Header
        var label = data.player_name || "Analysis";
        document.getElementById("result-player").textContent = label;

        // Recent games (player-dependent)
        var recentCard = document.getElementById("recent-games-card");
        if (data.recent_games) {
            recentCard.classList.remove("hidden");
            var gamesContainer = document.getElementById("recent-games-list");
            gamesContainer.innerHTML = '<div class="games-list">' +
                data.recent_games.map(function (pts) {
                    return '<span class="game-point">' + pts + '</span>';
                }).join("") +
                '</div>';
            document.getElementById("player-avg").textContent = data.player_avg;
        } else {
            recentCard.classList.add("hidden");
        }

        // Action card
        var leanCard = document.getElementById("lean-card");
        var leanBody = document.getElementById("lean-body");
        if (data.action) {
            leanCard.classList.remove("hidden");
            leanBody.innerHTML = '<div class="action-text">' + data.action + '</div>';
        } else {
            leanCard.classList.add("hidden");
        }

        // Prediction (player-dependent)
        var predictionCard = document.getElementById("prediction-card");
        if (data.prediction) {
            predictionCard.classList.remove("hidden");
            var decisionEl = document.getElementById("decision");
            var decision = data.prediction.decision;
            decisionEl.textContent = decision;
            decisionEl.className = "decision " + decision.toLowerCase();
            document.getElementById("confidence").textContent = data.prediction.confidence + "%";
        } else {
            predictionCard.classList.add("hidden");
        }

        // Cover rates (player-dependent)
        var coverCard = document.getElementById("cover-rates-card");
        if (data.cover_rates) {
            coverCard.classList.remove("hidden");
            document.getElementById("over-rate").textContent = data.cover_rates.over + "%";
            document.getElementById("under-rate").textContent = data.cover_rates.under + "%";
            document.getElementById("push-rate").textContent = data.cover_rates.push + "%";
        } else {
            coverCard.classList.add("hidden");
        }

        // Show results
        results.classList.remove("hidden");
    }

    function renderScanResults(games) {
        if (games.length === 0) {
            scanResults.innerHTML = '<p class="scan-empty">No games found today.</p>';
            scanResults.classList.remove("hidden");
            return;
        }

        var html = '<h2 class="scan-title">Today\'s Games</h2>';
        html += '<div class="scan-grid">';

        games.forEach(function (g) {
            var pct = g.cover_pct;
            var pctClass = "pct-low";
            if (pct >= 80) pctClass = "pct-high";
            else if (pct >= 65) pctClass = "pct-mid";

            html += '<div class="scan-card">';

            // Header: matchup + cover %
            html += '<div class="scan-card-header">';
            html += '<div class="scan-matchup">' + g.away_team + ' vs ' + g.home_team + '</div>';
            html += '<div class="scan-pct ' + pctClass + '">' + pct + '%</div>';
            html += '</div>';

            // Time
            html += '<div class="scan-time">' + g.game_time_est + ' EST</div>';

            // Action — what to do
            if (g.action) {
                html += '<div class="scan-action">' + g.action + '</div>';
            }

            // Recommendation
            var recClass = "rec-monitor";
            if (g.recommendation === "STRONG PLAY") recClass = "rec-strong";
            else if (g.recommendation === "LEAN") recClass = "rec-lean";
            html += '<div class="scan-rec ' + recClass + '">' + g.recommendation + '</div>';

            html += '</div>';
        });

        html += '</div>';
        scanResults.innerHTML = html;
        scanResults.classList.remove("hidden");
    }

    function buildTicker(games) {
        var track = document.getElementById("ticker-track");
        if (!games || games.length === 0) {
            track.innerHTML = '<span class="ticker-item">No games scheduled today</span>';
            return;
        }

        var items = "";
        games.forEach(function (g) {
            items += '<span class="ticker-item">' +
                '<span class="ticker-teams">' + g.away_team + ' @ ' + g.home_team + '</span>' +
                '<span class="ticker-time">' + g.game_time_est + ' EST</span>' +
                '</span>';
        });

        // Duplicate for seamless loop
        track.innerHTML = items + items;
    }

    function formatSpread(val) {
        var num = parseFloat(val);
        if (num > 0) return "+" + num.toFixed(1);
        return num.toFixed(1);
    }
});
