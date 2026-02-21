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

    var welcomeHero = document.getElementById("welcome-hero");
    var dashboardSection = document.getElementById("dashboard-section");
    var ledgerBtn = document.getElementById("ledger-btn");
    var gradeBtn = document.getElementById("grade-btn");
    var dashboardSportFilter = document.getElementById("dashboard-sport-filter");
    var dashboardLoading = document.getElementById("dashboard-loading");
    var lottoBtn = document.getElementById("lotto-btn");
    var lottoLoading = document.getElementById("lotto-loading");
    var lottoResults = document.getElementById("lotto-results");

    var todaysGames = [];
    var currentSport = "nba";
    var currentSlate = { showing_tomorrow: false, game_count: 0 };
    var scanResultsVisible = false;
    var dashboardVisible = false;

    // Sidebar toggle
    var navSportBadge = document.getElementById("nav-sport-badge");

    function openSidebar() {
        document.body.classList.add("sidebar-open");
    }

    function closeSidebar() {
        document.body.classList.remove("sidebar-open");
    }

    document.getElementById("nav-hamburger").addEventListener("click", openSidebar);
    document.getElementById("sidebar-overlay").addEventListener("click", closeSidebar);
    document.getElementById("sidebar-close").addEventListener("click", closeSidebar);

    document.addEventListener("keydown", function (e) {
        if (e.key === "Escape") closeSidebar();
    });

    // Home button — reset to welcome hero
    document.getElementById("nav-home-btn").addEventListener("click", function () {
        scanResults.classList.add("hidden");
        scanResults.innerHTML = "";
        scanResultsVisible = false;
        results.classList.add("hidden");
        errorBanner.classList.add("hidden");
        dashboardSection.classList.add("hidden");
        dashboardVisible = false;
        lottoResults.classList.add("hidden");
        lottoResults.innerHTML = "";
        welcomeHero.classList.remove("hidden");
        closeSidebar();
    });

    // Hero sport card clicks
    document.querySelectorAll(".hero-sport-card").forEach(function (card) {
        card.addEventListener("click", function () {
            var sport = card.getAttribute("data-sport");
            currentSport = sport;
            sportBtns.forEach(function (b) { b.classList.remove("active"); });
            document.querySelector('.sport-btn[data-sport="' + sport + '"]').classList.add("active");
            navSportBadge.textContent = sport.toUpperCase();
            form.classList.remove("hidden");
            fetchGames();
            openSidebar();
        });
    });

    // Hero CTA button
    document.getElementById("hero-cta").addEventListener("click", openSidebar);

    // Sport toggle
    var sportBtns = document.querySelectorAll(".sport-btn");
    sportBtns.forEach(function (btn) {
        btn.addEventListener("click", function () {
            var newSport = btn.getAttribute("data-sport");
            if (newSport === currentSport) return;

            currentSport = newSport;
            sportBtns.forEach(function (b) { b.classList.remove("active"); });
            btn.classList.add("active");

            // Update nav badge
            navSportBadge.textContent = newSport.toUpperCase();

            // Clear existing results and show hero
            scanResults.classList.add("hidden");
            scanResults.innerHTML = "";
            scanResultsVisible = false;
            results.classList.add("hidden");
            errorBanner.classList.add("hidden");
            dashboardSection.classList.add("hidden");
            dashboardVisible = false;
            lottoResults.classList.add("hidden");
            lottoResults.innerHTML = "";
            welcomeHero.classList.remove("hidden");

            // Hide manual form when ALL is selected (it's sport-specific)
            if (newSport === "all") {
                form.classList.add("hidden");
            } else {
                form.classList.remove("hidden");
            }

            // Re-fetch games for ticker + autocomplete
            if (newSport !== "all") {
                fetchGames();
            }
        });
    });

    function fetchGames() {
        fetch("/api/games?sport=" + currentSport)
            .then(function (res) { return res.json(); })
            .then(function (data) {
                todaysGames = data.games || [];
                currentSlate = data.slate || { showing_tomorrow: false, game_count: 0 };
                buildTicker(todaysGames);

                // Silent scan re-fetch if scan results are currently visible
                if (scanResultsVisible && !scanResults.classList.contains("hidden")) {
                    fetch("/api/scan", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ sport: currentSport })
                    })
                    .then(function (res) { return res.json(); })
                    .then(function (scanData) {
                        if (scanData.success) {
                            renderScanResults(scanData.games || []);
                        }
                    })
                    .catch(function () { /* silent fail — next tick retries */ });
                }
            })
            .catch(function () {
                todaysGames = [];
            });
    }

    // Initial fetch
    fetchGames();

    // Auto-poll every 3 minutes
    setInterval(fetchGames, 3 * 60 * 1000);

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
            if ((currentSport === "nhl" || currentSport === "cfb" || currentSport === "cbb" || currentSport === "nfl") && g.venue_name) {
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
        dashboardSection.classList.add("hidden");
        dashboardVisible = false;
        lottoResults.classList.add("hidden");
        lottoResults.innerHTML = "";

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

            if (currentSport === "all" && data.all_sports) {
                renderAllSportsResults(data.all_sports);
            } else {
                renderScanResults(data.games || []);
            }

            closeSidebar();
        })
        .catch(function () {
            scanLoading.classList.add("hidden");
            scanBtn.disabled = false;
            showError("Gotham's signal went dark.");
        });
    });

    // Form submit
    form.addEventListener("submit", function (e) {
        e.preventDefault();

        results.classList.add("hidden");
        errorBanner.classList.add("hidden");
        dashboardSection.classList.add("hidden");
        dashboardVisible = false;
        lottoResults.classList.add("hidden");
        lottoResults.innerHTML = "";

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

            // Auto-close sidebar on mobile
            if (window.innerWidth <= 768) closeSidebar();
        })
        .catch(function (err) {
            loading.classList.add("hidden");
            submitBtn.disabled = false;
            showError("Lost connection to Gotham.");
        });
    });

    function showError(message) {
        errorBanner.textContent = message;
        errorBanner.classList.remove("hidden");
    }

    function renderResults(data) {
        welcomeHero.classList.add("hidden");
        // Handle NFL skip response
        if (data.skip) {
            document.getElementById("result-player").textContent = data.home_team + " vs " + data.away_team;
            document.getElementById("recent-games-card").classList.add("hidden");
            document.getElementById("prediction-card").classList.add("hidden");
            document.getElementById("cover-rates-card").classList.add("hidden");
            var leanCard = document.getElementById("lean-card");
            var leanBody = document.getElementById("lean-body");
            leanCard.classList.remove("hidden");
            leanBody.innerHTML = '<div class="scan-skip-badge">' + (data.message || "SKIP — Do not bet this game.") + '</div>';
            results.classList.remove("hidden");
            return;
        }

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
        welcomeHero.classList.add("hidden");
        if (games.length === 0) {
            scanResults.innerHTML = '<div class="scan-empty-state">' +
                '<div class="scan-empty-headline">Gotham\'s quiet tonight.</div>' +
                '<div class="scan-empty-sub">No ' + currentSport.toUpperCase() + ' games on the board right now. Check back closer to game time or try another sport.</div>' +
                '</div>';
            scanResults.classList.remove("hidden");
            return;
        }

        var filtered = games.filter(function (g) { return g.cover_pct >= 68.5 || g.skip; });
        var nonSkip = games.filter(function (g) { return !g.skip; });

        var sportLabel = currentSport.toUpperCase();
        var dayLabel = currentSlate.showing_tomorrow ? "Tomorrow's" : "Today's";

        if (filtered.length === 0) {
            // No strong plays — show top alternatives
            var alternatives = nonSkip.slice().sort(function (a, b) { return b.cover_pct - a.cover_pct; }).slice(0, 5);

            if (alternatives.length === 0) {
                scanResults.innerHTML = '<div class="scan-empty-state">' +
                    '<div class="scan-empty-headline">Even the Joker sits this one out.</div>' +
                    '<div class="scan-empty-sub">No ' + sportLabel + ' plays found. The house has the edge tonight — live to bet another day.</div>' +
                    '</div>';
                scanResults.classList.remove("hidden");
                return;
            }

            var html = '<h2 class="scan-title">' + dayLabel + ' ' + sportLabel + ' Games</h2>';
            html += '<div class="alt-picks-header">No strong plays today — here are the closest calls</div>';
            html += '<div class="scan-grid">';
            alternatives.forEach(function (g) {
                html += buildScanCard(g, currentSport, true);
            });
            html += '</div>';

            // Still build parlays from alternatives if thresholds met
            html += buildParlaySection(alternatives);

            scanResults.innerHTML = html;
            scanResults.classList.remove("hidden");
            scanResultsVisible = true;
            return;
        }

        var html = '<h2 class="scan-title">' + dayLabel + ' ' + sportLabel + ' Games</h2>';
        html += '<div class="scan-grid">';

        filtered.forEach(function (g) {
            html += buildScanCard(g, currentSport);
        });

        html += '</div>';

        // Parlays section
        html += buildParlaySection(filtered);

        // "Other Games to Watch" — below threshold but above 58%, not already shown
        var filteredIds = filtered.map(function (g) { return g.home_team + g.away_team; });
        var nearMisses = nonSkip.filter(function (g) {
            return g.cover_pct >= 58 && g.cover_pct < 68.5 && filteredIds.indexOf(g.home_team + g.away_team) === -1;
        }).sort(function (a, b) { return b.cover_pct - a.cover_pct; }).slice(0, 5);

        if (nearMisses.length > 0) {
            html += '<div class="alt-picks-section">';
            html += '<div class="alt-picks-header">Other Games to Watch</div>';
            html += '<div class="scan-grid">';
            nearMisses.forEach(function (g) {
                html += buildScanCard(g, currentSport, true);
            });
            html += '</div></div>';
        }

        scanResults.innerHTML = html;
        scanResults.classList.remove("hidden");
        scanResultsVisible = true;
    }

    function renderAllSportsResults(allSports) {
        welcomeHero.classList.add("hidden");
        var sportNames = { nba: "NBA", nhl: "NHL", cfb: "CFB", nfl: "NFL", cbb: "CBB" };
        var sportOrder = ["nba", "nhl", "cfb", "nfl", "cbb"];
        var html = '<h2 class="scan-title">All Sports — Full Deck</h2>';
        var allFiltered = [];

        sportOrder.forEach(function (sport) {
            var games = allSports[sport] || [];
            var filtered = games.filter(function (g) { return g.cover_pct >= 68.5 || g.skip; });

            html += '<div class="all-sport-section">';
            html += '<h3 class="all-sport-header">' + sportNames[sport] + '</h3>';

            if (filtered.length === 0) {
                html += '<p class="scan-empty-inline">The Joker passes on ' + sportNames[sport] + ' tonight — no high-confidence plays.</p>';
                html += '</div>';
                return;
            }

            // Tag each game with its sport for cross-sport parlays
            filtered.forEach(function (g) { g._sport = sport; });
            allFiltered = allFiltered.concat(filtered);

            html += '<div class="scan-grid">';
            filtered.forEach(function (g) {
                html += buildScanCard(g, sport);
            });
            html += '</div></div>';
        });

        // Cross-sport parlays
        if (allFiltered.length >= 2) {
            html += buildParlaySection(allFiltered);
        }

        scanResults.innerHTML = html;
        scanResults.classList.remove("hidden");
        scanResultsVisible = true;
    }

    function buildScanCard(g, sport, isAlt) {
        var pct = g.cover_pct;
        var pctClass = "pct-mid";
        if (pct >= 80) pctClass = "pct-high";
        if (isAlt) pctClass = "pct-low";

        var cardClass = g.skip ? "scan-card scan-card-skip" : "scan-card";
        if (isAlt) cardClass += " scan-card-alt";
        var html = '<div class="' + cardClass + '">';

        // Header: matchup + cover %
        var awayLabel = g.away_rank ? '<span class="scan-rank">#' + g.away_rank + '</span> ' + g.away_team : g.away_team;
        var homeLabel = g.home_rank ? '<span class="scan-rank">#' + g.home_rank + '</span> ' + g.home_team : g.home_team;
        html += '<div class="scan-card-header">';
        html += '<div class="scan-matchup">' + awayLabel + ' vs ' + homeLabel + '</div>';
        html += '<div class="scan-pct ' + pctClass + '">' + pct + '%</div>';
        html += '</div>';

        // Venue (NHL, CFB, and NFL)
        if ((sport === "nhl" || sport === "cfb" || sport === "cbb" || sport === "nfl") && g.venue_name) {
            var venueText = g.venue_name;
            if (g.venue_city) {
                venueText += " — " + g.venue_city;
                if (g.venue_state) venueText += ", " + g.venue_state;
            }
            html += '<div class="scan-venue">' + venueText + '</div>';
        }

        // Time
        html += '<div class="scan-time">' + g.game_time_est + ' EST</div>';

        // Slot type label (CFB and NFL)
        if ((sport === "cfb" || sport === "cbb" || sport === "nfl") && g.slot_type) {
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

        // NFL: Weather badge
        if (sport === "nfl") {
            if (g.weather_dome) {
                html += '<div class="scan-weather-alert dome">';
                html += '<span class="weather-label">DOME</span>';
                html += '</div>';
            } else if (g.weather_alerts && g.weather_alerts.length > 0) {
                html += '<div class="scan-weather-alert">';
                html += '<span class="weather-label">WEATHER ALERT</span> ';
                html += '<span class="weather-detail">' + g.weather_alerts.join(" | ") + '</span>';
                html += '</div>';
            } else if (g.weather) {
                var weatherParts = [];
                if (g.weather.temperature) weatherParts.push(g.weather.temperature + "°F");
                if (g.weather.wind_speed) weatherParts.push("Wind " + g.weather.wind_speed + " mph");
                if (g.weather.condition) weatherParts.push(g.weather.condition);
                if (weatherParts.length > 0) {
                    html += '<div class="scan-weather-info">';
                    html += '<span class="weather-detail">' + weatherParts.join(" | ") + '</span>';
                    html += '</div>';
                }
            }
        }

        // NFL: Trend Discrepancy badge
        if (g.trend_discrepancy && g.trend_discrepancy.applies) {
            var td = g.trend_discrepancy;
            html += '<div class="scan-trend-disc">';
            html += '<span class="trend-disc-label">TREND ALERT</span> ';
            if (td.home_signal) {
                var homeClass = td.home_signal === "bounce-back" ? "trend-bounce" : "trend-regress";
                html += '<span class="' + homeClass + '">Home (' + td.home_record + '): ' + td.home_signal.toUpperCase() + '</span> ';
            }
            if (td.away_signal) {
                var awayClass = td.away_signal === "bounce-back" ? "trend-bounce" : "trend-regress";
                html += '<span class="' + awayClass + '">Away (' + td.away_record + '): ' + td.away_signal.toUpperCase() + '</span> ';
            }
            if (td.strong_contrarian) {
                html += '<span class="trend-strong">STRONG CONTRARIAN</span>';
            }
            html += '</div>';
        }

        // NFL: O/U Alert badge
        if (g.overunder && g.overunder.applies) {
            var ou = g.overunder;
            html += '<div class="scan-ou-alert">';
            html += '<span class="ou-label">O/U ALERT</span> ';
            ou.flags.forEach(function (flag) {
                html += '<span class="ou-detail">' + flag + '</span> ';
            });
            html += '</div>';
        }

        // NFL: Skip badge
        if (g.skip) {
            html += '<div class="scan-skip-badge">SNF — Even the Joker passes</div>';
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
        return html;
    }

    function buildParlaySection(games) {
        if (games.length < 2) return "";

        // Sort by cover_pct descending for parlay building
        var sorted = games.slice().sort(function (a, b) { return b.cover_pct - a.cover_pct; });

        var html = '<div class="parlays-section">';
        html += '<h2 class="scan-title">The Joker\'s Parlays</h2>';

        // Safety Parlay: 2 legs, 80%+ each
        var safetyLegs = sorted.filter(function (g) { return g.cover_pct >= 80; }).slice(0, 2);
        if (safetyLegs.length >= 2) {
            var safetyOdds = calcParlayOdds(safetyLegs);
            var safetyProb = calcCombinedProb(safetyLegs);
            html += buildParlayCard("Two-Face's Safe Bet", safetyLegs, safetyOdds, safetyProb, "parlay-safety");
        }

        // Normal Parlay: 4-6 legs, 67.5%+ each
        var normalPool = sorted.filter(function (g) { return g.cover_pct >= 67.5; });
        var normalLegs = normalPool.slice(0, Math.min(6, Math.max(4, normalPool.length)));
        if (normalLegs.length >= 4) {
            var normalOdds = calcParlayOdds(normalLegs);
            var normalProb = calcCombinedProb(normalLegs);
            html += buildParlayCard("Gotham Gambit", normalLegs, normalOdds, normalProb, "parlay-normal");
        } else if (normalPool.length >= 2) {
            // Fallback: use what we have if less than 4
            var normalOdds = calcParlayOdds(normalPool);
            var normalProb = calcCombinedProb(normalPool);
            html += buildParlayCard("Gotham Gambit", normalPool, normalOdds, normalProb, "parlay-normal");
        }

        // YOLO Parlay: all qualifying legs
        var yoloPool = sorted.filter(function (g) { return g.cover_pct >= 60; });
        if (yoloPool.length >= 4) {
            var yoloLegs = yoloPool.slice(0, Math.min(10, yoloPool.length));
            var yoloOdds = calcParlayOdds(yoloLegs);
            var yoloProb = calcCombinedProb(yoloLegs);
            html += buildParlayCard("Gotham Breakout", yoloLegs, yoloOdds, yoloProb, "parlay-yolo");
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
            track.innerHTML = '<span class="ticker-item">Gotham is dark tonight</span>';
            return;
        }

        var items = "";

        // Prepend "TOMORROW'S GAMES" label if showing tomorrow's slate
        if (currentSlate.showing_tomorrow) {
            items += '<span class="ticker-item ticker-tomorrow">TOMORROW IN GOTHAM</span>';
        }

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

    // ─── Joker's Lotto (Cross-Sport Mega Parlay) ─────────────────────
    lottoBtn.addEventListener("click", function () {
        lottoBtn.disabled = true;
        lottoLoading.classList.remove("hidden");
        lottoResults.classList.add("hidden");
        lottoResults.innerHTML = "";
        scanResults.classList.add("hidden");
        scanResultsVisible = false;
        results.classList.add("hidden");
        errorBanner.classList.add("hidden");
        dashboardSection.classList.add("hidden");
        dashboardVisible = false;

        fetch("/api/scan", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ sport: "all" })
        })
        .then(function (res) { return res.json(); })
        .then(function (data) {
            lottoLoading.classList.add("hidden");
            lottoBtn.disabled = false;

            if (!data.success || !data.all_sports) {
                showError(data.error || "Lotto scan failed.");
                return;
            }

            renderLottoResults(data.all_sports);

            if (window.innerWidth <= 768) closeSidebar();
        })
        .catch(function () {
            lottoLoading.classList.add("hidden");
            lottoBtn.disabled = false;
            showError("Gotham's signal went dark.");
        });
    });

    function renderLottoResults(allSports) {
        welcomeHero.classList.add("hidden");
        var sportOrder = ["nba", "nhl", "cfb", "nfl", "cbb"];
        var sportNames = { nba: "NBA", nhl: "NHL", cfb: "CFB", nfl: "NFL", cbb: "CBB" };
        var picks = [];

        sportOrder.forEach(function (sport) {
            var games = allSports[sport] || [];
            // Filter: >= 72% cover, not skip
            var eligible = games.filter(function (g) {
                return g.cover_pct >= 72 && !g.skip;
            });
            if (eligible.length === 0) return;

            // Sort by cover_pct desc, tiebreak by confirmation_score desc
            eligible.sort(function (a, b) {
                if (b.cover_pct !== a.cover_pct) return b.cover_pct - a.cover_pct;
                return (b.confirmation_score || 0) - (a.confirmation_score || 0);
            });

            var best = eligible[0];
            best._sport = sport;
            picks.push(best);
        });

        if (picks.length < 2) {
            lottoResults.innerHTML = '<div class="scan-empty-state">' +
                '<div class="scan-empty-headline">The Joker keeps his cards close.</div>' +
                '<div class="scan-empty-sub">Not enough high-confidence cross-sport picks tonight. Need at least 2 sports with a 72%+ play — check back later.</div>' +
                '</div>';
            lottoResults.classList.remove("hidden");
            return;
        }

        // Build parlay card
        var parlayOdds = calcParlayOdds(picks);
        var combinedProb = calcCombinedProb(picks);

        var html = '<h2 class="scan-title">Joker\'s Lotto — Cross-Sport Mega Parlay</h2>';
        html += '<p class="lotto-subtitle">' + picks.length + ' sports, 1 ticket. The best pick from each sport at 72%+ cover.</p>';

        // Parlay summary card
        html += '<div class="parlay-card parlay-lotto">';
        html += '<div class="parlay-header">';
        html += '<span class="parlay-title">Joker\'s Lotto (' + picks.length + ' legs)</span>';
        html += '<span class="parlay-odds">' + parlayOdds + '</span>';
        html += '</div>';
        html += '<div class="parlay-prob">Combined probability: ' + combinedProb + '%</div>';
        html += '<div class="parlay-legs">';

        picks.forEach(function (g) {
            var legOdds = pctToAmericanOdds(g.cover_pct);
            var pickLabel = g.action || (g.lean_team ? g.lean_team : g.home_team);
            html += '<div class="parlay-leg">';
            html += '<span class="lotto-sport-badge lotto-badge-' + g._sport + '">' + sportNames[g._sport] + '</span>';
            html += '<span class="parlay-leg-pick">' + pickLabel + '</span>';
            html += '<span class="parlay-leg-odds">' + legOdds + '</span>';
            html += '<span class="parlay-leg-pct">' + g.cover_pct + '%</span>';
            html += '</div>';
        });

        html += '</div></div>';

        // Detail cards for each leg
        html += '<h3 class="lotto-detail-header">Leg Breakdown</h3>';
        html += '<div class="scan-grid">';
        picks.forEach(function (g) {
            html += '<div class="lotto-leg-wrapper">';
            html += '<div class="lotto-sport-badge lotto-badge-' + g._sport + ' lotto-badge-inline">' + sportNames[g._sport] + '</div>';
            html += buildScanCard(g, g._sport);
            html += '</div>';
        });
        html += '</div>';

        lottoResults.innerHTML = html;
        lottoResults.classList.remove("hidden");
    }

    // ─── Dashboard (The Ledger) ─────────────────────────────────────
    ledgerBtn.addEventListener("click", function () {
        welcomeHero.classList.add("hidden");
        scanResults.classList.add("hidden");
        scanResultsVisible = false;
        results.classList.add("hidden");
        errorBanner.classList.add("hidden");
        lottoResults.classList.add("hidden");
        lottoResults.innerHTML = "";
        dashboardSection.classList.remove("hidden");
        dashboardVisible = true;
        fetchDashboard();

        if (window.innerWidth <= 768) closeSidebar();
    });

    gradeBtn.addEventListener("click", function () {
        gradeBtn.disabled = true;
        gradeBtn.textContent = "Grading...";

        var body = {};
        var filterVal = dashboardSportFilter.value;
        if (filterVal) body.sport = filterVal;

        fetch("/api/grade", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body)
        })
        .then(function (res) { return res.json(); })
        .then(function (data) {
            gradeBtn.disabled = false;
            gradeBtn.textContent = "Grade Pending";
            if (data.success) {
                fetchDashboard();
            }
        })
        .catch(function () {
            gradeBtn.disabled = false;
            gradeBtn.textContent = "Grade Pending";
        });
    });

    dashboardSportFilter.addEventListener("change", function () {
        fetchDashboard();
    });

    function fetchDashboard() {
        dashboardLoading.classList.remove("hidden");
        document.getElementById("dashboard-stats").innerHTML = "";
        document.getElementById("dashboard-breakdowns").innerHTML = "";
        document.getElementById("dashboard-recent").innerHTML = "";

        var sportParam = dashboardSportFilter.value;
        var url = "/api/dashboard";
        if (sportParam) url += "?sport=" + sportParam;

        fetch(url)
            .then(function (res) { return res.json(); })
            .then(function (data) {
                dashboardLoading.classList.add("hidden");
                if (data.success) {
                    renderDashboard(data);
                }
            })
            .catch(function () {
                dashboardLoading.classList.add("hidden");
            });
    }

    function renderDashboard(data) {
        var o = data.overall;

        // Stat cards
        var rateClass = o.win_rate >= 55 ? "stat-green" : o.win_rate >= 45 ? "stat-yellow" : "stat-red";
        var statsHtml = '<div class="dash-stat-cards">';
        statsHtml += '<div class="dash-stat-card">';
        statsHtml += '<div class="dash-stat-label">Record</div>';
        statsHtml += '<div class="dash-stat-value">' + o.wins + '-' + o.losses + (o.pushes > 0 ? '-' + o.pushes : '') + '</div>';
        statsHtml += '</div>';
        statsHtml += '<div class="dash-stat-card">';
        statsHtml += '<div class="dash-stat-label">Win Rate</div>';
        statsHtml += '<div class="dash-stat-value ' + rateClass + '">' + o.win_rate + '%</div>';
        statsHtml += '</div>';
        statsHtml += '<div class="dash-stat-card">';
        statsHtml += '<div class="dash-stat-label">Total Picks</div>';
        statsHtml += '<div class="dash-stat-value">' + o.total + '</div>';
        statsHtml += '</div>';
        statsHtml += '<div class="dash-stat-card">';
        statsHtml += '<div class="dash-stat-label">Pending</div>';
        statsHtml += '<div class="dash-stat-value stat-muted">' + o.pending + '</div>';
        statsHtml += '</div>';
        statsHtml += '</div>';
        document.getElementById("dashboard-stats").innerHTML = statsHtml;

        // Breakdowns
        var breakHtml = '';

        if (data.by_sport && data.by_sport.length > 0) {
            breakHtml += '<div class="dash-breakdown">';
            breakHtml += '<h3 class="dash-section-title">By Sport</h3>';
            data.by_sport.forEach(function (s) {
                breakHtml += buildBreakdownRow(s.sport.toUpperCase(), s);
            });
            breakHtml += '</div>';
        }

        if (data.by_slot && data.by_slot.length > 0) {
            breakHtml += '<div class="dash-breakdown">';
            breakHtml += '<h3 class="dash-section-title">By Slot Type</h3>';
            data.by_slot.forEach(function (s) {
                breakHtml += buildBreakdownRow(s.slot_type.toUpperCase(), s);
            });
            breakHtml += '</div>';
        }

        if (data.by_recommendation && data.by_recommendation.length > 0) {
            breakHtml += '<div class="dash-breakdown">';
            breakHtml += '<h3 class="dash-section-title">By Recommendation</h3>';
            data.by_recommendation.forEach(function (s) {
                breakHtml += buildBreakdownRow(s.recommendation, s);
            });
            breakHtml += '</div>';
        }

        document.getElementById("dashboard-breakdowns").innerHTML = breakHtml;

        // Recent predictions
        var recentHtml = '';
        if (data.recent && data.recent.length > 0) {
            recentHtml += '<h3 class="dash-section-title">Recent Predictions</h3>';
            recentHtml += '<div class="dash-recent-list">';
            data.recent.forEach(function (p) {
                var statusClass = "status-pending";
                if (p.result === "HIT") statusClass = "status-hit";
                else if (p.result === "MISS") statusClass = "status-miss";
                else if (p.result === "PUSH") statusClass = "status-push";

                var borderClass = "dash-recent-border-pending";
                if (p.result === "HIT") borderClass = "dash-recent-border-hit";
                else if (p.result === "MISS") borderClass = "dash-recent-border-miss";
                else if (p.result === "PUSH") borderClass = "dash-recent-border-push";

                recentHtml += '<div class="dash-recent-item ' + borderClass + '">';
                recentHtml += '<div class="dash-recent-top">';
                recentHtml += '<span class="dash-recent-sport">' + p.sport.toUpperCase() + '</span>';
                recentHtml += '<span class="dash-recent-matchup">' + p.away_team + ' vs ' + p.home_team + '</span>';
                recentHtml += '<span class="dash-recent-status ' + statusClass + '">' + p.result + '</span>';
                recentHtml += '</div>';
                recentHtml += '<div class="dash-recent-bottom">';
                recentHtml += '<span class="dash-recent-action">' + (p.action || '') + '</span>';
                if (p.home_score !== null && p.away_score !== null) {
                    recentHtml += '<span class="dash-recent-score">' + p.away_score + '-' + p.home_score + '</span>';
                }
                recentHtml += '<span class="dash-recent-pct">' + p.cover_pct + '%</span>';
                recentHtml += '</div>';
                recentHtml += '</div>';
            });
            recentHtml += '</div>';
        }
        document.getElementById("dashboard-recent").innerHTML = recentHtml;
    }

    function buildBreakdownRow(label, stats) {
        var rateClass = stats.win_rate >= 55 ? "stat-green" : stats.win_rate >= 45 ? "stat-yellow" : "stat-red";
        var decided = stats.wins + stats.losses;
        var html = '<div class="dash-breakdown-row">';
        html += '<span class="dash-breakdown-label">' + label + '</span>';
        html += '<span class="dash-breakdown-record">' + stats.wins + '-' + stats.losses;
        if (stats.pushes > 0) html += '-' + stats.pushes;
        html += '</span>';
        html += '<span class="dash-breakdown-rate ' + rateClass + '">' + stats.win_rate + '%</span>';
        html += '</div>';
        return html;
    }
});
