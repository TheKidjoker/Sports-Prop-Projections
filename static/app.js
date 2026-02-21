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
    var currentSport = "nba";

    // Sport toggle
    var sportBtns = document.querySelectorAll(".sport-btn");
    sportBtns.forEach(function (btn) {
        btn.addEventListener("click", function () {
            var newSport = btn.getAttribute("data-sport");
            if (newSport === currentSport) return;

            currentSport = newSport;
            sportBtns.forEach(function (b) { b.classList.remove("active"); });
            btn.classList.add("active");

            // Clear existing results
            scanResults.classList.add("hidden");
            scanResults.innerHTML = "";
            results.classList.add("hidden");
            errorBanner.classList.add("hidden");

            // Re-fetch games for ticker + autocomplete
            fetchGames();
        });
    });

    function fetchGames() {
        fetch("/api/games?sport=" + currentSport)
            .then(function (res) { return res.json(); })
            .then(function (data) {
                todaysGames = data.games || [];
                buildTicker(todaysGames);
            })
            .catch(function () {
                todaysGames = [];
            });
    }

    // Initial fetch
    fetchGames();

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
            var awayLabel = g.away_rank ? '#' + g.away_rank + ' ' + g.away_team : g.away_team;
            var homeLabel = g.home_rank ? '#' + g.home_rank + ' ' + g.home_team : g.home_team;
            var text = awayLabel + " vs " + homeLabel + " - " + g.game_time_est + " EST";
            if ((currentSport === "nhl" || currentSport === "cfb") && g.venue_name) {
                text += " | " + g.venue_name;
            }
            li.textContent = text;
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
            body: JSON.stringify({ sport: currentSport })
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
            team_name: document.getElementById("team_name").value,
            sport: currentSport
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

        var filtered = games.filter(function (g) { return g.cover_pct >= 68.5; });

        if (filtered.length === 0) {
            scanResults.innerHTML = '<p class="scan-empty">No high-confidence plays found today.</p>';
            scanResults.classList.remove("hidden");
            return;
        }

        var sportLabel = currentSport.toUpperCase();
        var html = '<h2 class="scan-title">Today\'s ' + sportLabel + ' Games</h2>';
        html += '<div class="scan-grid">';

        filtered.forEach(function (g) {
            var pct = g.cover_pct;
            var pctClass = "pct-mid";
            if (pct >= 80) pctClass = "pct-high";

            html += '<div class="scan-card">';

            // Header: matchup + cover %
            var awayLabel = g.away_rank ? '<span class="scan-rank">#' + g.away_rank + '</span> ' + g.away_team : g.away_team;
            var homeLabel = g.home_rank ? '<span class="scan-rank">#' + g.home_rank + '</span> ' + g.home_team : g.home_team;
            html += '<div class="scan-card-header">';
            html += '<div class="scan-matchup">' + awayLabel + ' vs ' + homeLabel + '</div>';
            html += '<div class="scan-pct ' + pctClass + '">' + pct + '%</div>';
            html += '</div>';

            // Venue (NHL and CFB)
            if ((currentSport === "nhl" || currentSport === "cfb") && g.venue_name) {
                var venueText = g.venue_name;
                if (g.venue_city) {
                    venueText += " — " + g.venue_city;
                    if (g.venue_state) venueText += ", " + g.venue_state;
                }
                html += '<div class="scan-venue">' + venueText + '</div>';
            }

            // Time
            html += '<div class="scan-time">' + g.game_time_est + ' EST</div>';

            // Slot type label (CFB)
            if (currentSport === "cfb" && g.slot_type) {
                var slotLabel = g.slot_type.toUpperCase();
                var slotClass = "slot-" + g.slot_type;
                html += '<div class="scan-slot ' + slotClass + '">' + slotLabel + '</div>';
            }

            // Rank Scam badge (CFB)
            if (g.rank_scam && g.rank_scam.is_rank_scam) {
                var tierLabel = g.rank_scam.tier ? g.rank_scam.tier.toUpperCase() : '';
                html += '<div class="scan-rank-scam">';
                html += '<span class="rank-scam-label">RANK SCAM — ' + tierLabel + '</span> ';
                html += '<span class="rank-scam-detail">' + g.rank_scam.scam_action + '</span>';
                html += '</div>';
            }

            // Spread Discrepancy badge (CFB)
            if (g.spread_discrepancy && g.spread_discrepancy.is_discrepancy) {
                html += '<div class="scan-spread-disc">';
                html += '<span class="spread-disc-label">SPREAD ALERT</span> ';
                html += '<span class="spread-disc-detail">#' + g.spread_discrepancy.rank + ' expected ' + g.spread_discrepancy.expected_range + ' pts — ' + g.spread_discrepancy.discrepancy_action + '</span>';
                html += '</div>';
            }

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

        // Parlays section
        html += buildParlaySection(filtered);

        scanResults.innerHTML = html;
        scanResults.classList.remove("hidden");
    }

    function buildParlaySection(games) {
        if (games.length < 2) return "";

        // Sort by cover_pct descending for parlay building
        var sorted = games.slice().sort(function (a, b) { return b.cover_pct - a.cover_pct; });

        var html = '<div class="parlays-section">';
        html += '<h2 class="scan-title">Parlay Suggestions</h2>';

        // Safety Parlay: 2 legs, 80%+ each
        var safetyLegs = sorted.filter(function (g) { return g.cover_pct >= 80; }).slice(0, 2);
        if (safetyLegs.length >= 2) {
            var safetyOdds = calcParlayOdds(safetyLegs);
            var safetyProb = calcCombinedProb(safetyLegs);
            html += buildParlayCard("Safety Parlay", safetyLegs, safetyOdds, safetyProb, "parlay-safety");
        }

        // Normal Parlay: 4-6 legs, 67.5%+ each
        var normalPool = sorted.filter(function (g) { return g.cover_pct >= 67.5; });
        var normalLegs = normalPool.slice(0, Math.min(6, Math.max(4, normalPool.length)));
        if (normalLegs.length >= 4) {
            var normalOdds = calcParlayOdds(normalLegs);
            var normalProb = calcCombinedProb(normalLegs);
            html += buildParlayCard("Normal Parlay", normalLegs, normalOdds, normalProb, "parlay-normal");
        } else if (normalPool.length >= 2) {
            // Fallback: use what we have if less than 4
            var normalOdds = calcParlayOdds(normalPool);
            var normalProb = calcCombinedProb(normalPool);
            html += buildParlayCard("Normal Parlay", normalPool, normalOdds, normalProb, "parlay-normal");
        }

        // YOLO Parlay: all qualifying legs
        var yoloPool = sorted.filter(function (g) { return g.cover_pct >= 60; });
        if (yoloPool.length >= 4) {
            var yoloLegs = yoloPool.slice(0, Math.min(10, yoloPool.length));
            var yoloOdds = calcParlayOdds(yoloLegs);
            var yoloProb = calcCombinedProb(yoloLegs);
            html += buildParlayCard("YOLO Parlay", yoloLegs, yoloOdds, yoloProb, "parlay-yolo");
        }

        html += '</div>';
        return html;
    }

    function buildParlayCard(title, legs, parlayOdds, combinedProb, cssClass) {
        var html = '<div class="parlay-card ' + cssClass + '">';
        html += '<div class="parlay-header">';
        html += '<span class="parlay-title">' + title + ' (' + legs.length + ' legs)</span>';
        html += '<span class="parlay-odds">' + parlayOdds + '</span>';
        html += '</div>';
        html += '<div class="parlay-prob">Combined probability: ' + combinedProb + '%</div>';
        html += '<div class="parlay-legs">';

        legs.forEach(function (g) {
            var legOdds = pctToAmericanOdds(g.cover_pct);
            var pickLabel = g.action || (g.lean_team ? g.lean_team : g.home_team);
            html += '<div class="parlay-leg">';
            html += '<span class="parlay-leg-pick">' + pickLabel + '</span>';
            html += '<span class="parlay-leg-odds">' + legOdds + '</span>';
            html += '<span class="parlay-leg-pct">' + g.cover_pct + '%</span>';
            html += '</div>';
        });

        html += '</div></div>';
        return html;
    }

    function pctToAmericanOdds(pct) {
        // Convert cover percentage to implied American odds
        var prob = pct / 100;
        if (prob >= 0.5) {
            var odds = -Math.round((prob / (1 - prob)) * 100);
            return odds.toString();
        } else {
            var odds = Math.round(((1 - prob) / prob) * 100);
            return "+" + odds.toString();
        }
    }

    function calcParlayOdds(legs) {
        // Multiply decimal odds, then convert to American
        var decimalProduct = 1;
        legs.forEach(function (g) {
            var prob = g.cover_pct / 100;
            var decOdds = 1 / prob;
            decimalProduct *= decOdds;
        });

        // Convert decimal parlay odds to American
        if (decimalProduct >= 2) {
            return "+" + Math.round((decimalProduct - 1) * 100);
        } else {
            return "-" + Math.round(100 / (decimalProduct - 1));
        }
    }

    function calcCombinedProb(legs) {
        var prob = 1;
        legs.forEach(function (g) {
            prob *= (g.cover_pct / 100);
        });
        return (prob * 100).toFixed(1);
    }

    function buildTicker(games) {
        var track = document.getElementById("ticker-track");
        if (!games || games.length === 0) {
            track.innerHTML = '<span class="ticker-item">No games scheduled today</span>';
            return;
        }

        var items = "";
        games.forEach(function (g) {
            var awayLabel = g.away_rank ? '#' + g.away_rank + ' ' + g.away_team : g.away_team;
            var homeLabel = g.home_rank ? '#' + g.home_rank + ' ' + g.home_team : g.home_team;
            items += '<span class="ticker-item">' +
                '<span class="ticker-teams">' + awayLabel + ' @ ' + homeLabel + '</span>' +
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
