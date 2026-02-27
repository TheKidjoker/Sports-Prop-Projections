document.addEventListener("DOMContentLoaded", function () {
    // ─── Constants ──────────────────────────────────────────────────────
    var COVER_PCT = {
        actionable: 68.5,
        nearMiss: 58,
        lotto: 72,
        parlaySafety: 80,
        parlayNormal: 67.5,
        parlayYolo: 60,
    };
    var POLL_INTERVAL = 5000;

    // ─── Helpers ─────────────────────────────────────────────────────────
    function getSignalClass(signal) {
        if (signal === "STRONG OVER") return "prism-strong-over";
        if (signal === "STRONG UNDER") return "prism-strong-under";
        if (signal === "LEAN OVER") return "prism-lean-over";
        if (signal === "LEAN UNDER") return "prism-lean-under";
        return "prism-skip";
    }

    function formatTeamLabel(team, rank) {
        return rank ? '#' + rank + ' ' + team : team;
    }

    // ─── Auth State ─────────────────────────────────────────────────────
    var _supabaseClient = null;
    var _accessToken = null;
    var _isAdmin = false;

    function authFetch(url, opts) {
        opts = opts || {};
        if (_accessToken) {
            opts.headers = opts.headers || {};
            opts.headers["Authorization"] = "Bearer " + _accessToken;
        }
        return fetch(url, opts).then(function (res) {
            if (res.status === 401) {
                // Token expired or invalid — sign out
                if (_supabaseClient) {
                    _supabaseClient.auth.signOut();
                }
                showAuthGate();
            }
            return res;
        });
    }

    function showAuthGate() {
        document.getElementById("auth-gate").classList.remove("hidden");
        document.getElementById("app-container").classList.add("hidden");
    }

    function updateAdminUI() {
        var btn = document.getElementById("testmodel-btn");
        if (!btn) return;
        if (_isAdmin) {
            btn.disabled = false;
            btn.title = "";
        } else {
            btn.disabled = true;
            btn.title = "Admin only";
        }
    }

    function showApp() {
        document.getElementById("auth-gate").classList.add("hidden");
        document.getElementById("app-container").classList.remove("hidden");
        // Check admin status
        authFetch("/api/auth/me")
            .then(function (res) { return res.json(); })
            .then(function (data) {
                _isAdmin = !!data.is_admin;
                updateAdminUI();
            })
            .catch(function () {
                _isAdmin = false;
                updateAdminUI();
            });
        // Kick off initial data loads
        fetchGames();
        tmPollCollect();
    }

    function initAuth() {
        fetch("/api/auth/config")
            .then(function (res) { return res.json(); })
            .then(function (cfg) {
                if (!cfg.supabase_url || !cfg.supabase_anon_key) {
                    // Auth not configured — skip login, show app directly
                    _isAdmin = true;
                    showApp();
                    return;
                }

                _supabaseClient = supabase.createClient(cfg.supabase_url, cfg.supabase_anon_key);

                // Listen for auth state changes
                _supabaseClient.auth.onAuthStateChange(function (event, session) {
                    if (session) {
                        _accessToken = session.access_token;
                        showApp();
                    } else {
                        _accessToken = null;
                        showAuthGate();
                    }
                });

                // Check existing session
                _supabaseClient.auth.getSession().then(function (result) {
                    var session = result.data.session;
                    if (session) {
                        _accessToken = session.access_token;
                        showApp();
                    } else {
                        showAuthGate();
                    }
                });

                // Wire up auth form
                var authForm = document.getElementById("auth-form");
                var authError = document.getElementById("auth-error");
                var authSubmit = document.getElementById("auth-submit");
                var authToggleBtn = document.getElementById("auth-toggle-btn");
                var authToggleText = document.getElementById("auth-toggle-text");
                var isSignUp = false;

                authToggleBtn.addEventListener("click", function () {
                    isSignUp = !isSignUp;
                    authSubmit.textContent = isSignUp ? "Sign Up" : "Sign In";
                    authToggleText.textContent = isSignUp ? "Already have an account?" : "Don't have an account?";
                    authToggleBtn.textContent = isSignUp ? "Sign In" : "Sign Up";
                    authError.classList.add("hidden");
                });

                authForm.addEventListener("submit", function (e) {
                    e.preventDefault();
                    var email = document.getElementById("auth-email").value.trim();
                    var password = document.getElementById("auth-password").value;
                    authSubmit.disabled = true;
                    authError.classList.add("hidden");

                    var authPromise;
                    if (isSignUp) {
                        authPromise = _supabaseClient.auth.signUp({ email: email, password: password });
                    } else {
                        authPromise = _supabaseClient.auth.signInWithPassword({ email: email, password: password });
                    }

                    authPromise.then(function (result) {
                        authSubmit.disabled = false;
                        if (result.error) {
                            authError.textContent = result.error.message;
                            authError.classList.remove("hidden");
                            return;
                        }
                        if (isSignUp && result.data.user && !result.data.session) {
                            authError.textContent = "Check your email to confirm your account.";
                            authError.classList.remove("hidden");
                            authError.style.color = "var(--accent-green)";
                            authError.style.borderColor = "rgba(76, 175, 80, 0.3)";
                            authError.style.background = "rgba(76, 175, 80, 0.1)";
                        }
                    }).catch(function () {
                        authSubmit.disabled = false;
                        authError.textContent = "Connection error. Try again.";
                        authError.classList.remove("hidden");
                    });
                });

                // Logout button
                document.getElementById("nav-logout-btn").addEventListener("click", function () {
                    _supabaseClient.auth.signOut();
                });
            })
            .catch(function () {
                // Config fetch failed — allow through (local dev fallback)
                showApp();
            });
    }

    // ─── Main App ───────────────────────────────────────────────────────
    var form = document.getElementById("predict-form");
    var submitBtn = document.getElementById("submit-btn");
    var loading = document.getElementById("predict-loading");
    var errorBanner = document.getElementById("error-banner");
    var results = document.getElementById("results");
    var scanBtn = document.getElementById("scan-btn");
    var scanLoading = document.getElementById("scan-loading");
    var scanResults = document.getElementById("scan-results");
    var teamInput = document.getElementById("team_name");
    var teamDropdown = document.getElementById("team-dropdown");
    var playerSearchBtn = document.getElementById("player-search-btn");
    var playerSearchSection = document.getElementById("player-search-section");

    var welcomeHero = document.getElementById("welcome-hero");
    var dashboardSection = document.getElementById("dashboard-section");
    var ledgerBtn = document.getElementById("ledger-btn");
    var gradeBtn = document.getElementById("grade-btn");
    var dashboardSportFilter = document.getElementById("dashboard-sport-filter");
    var dashboardLoading = document.getElementById("dashboard-loading");
    var lottoBtn = document.getElementById("lotto-btn");
    var lottoLoading = document.getElementById("lotto-loading");
    var lottoResults = document.getElementById("lotto-results");

    var scanSonar = document.getElementById("scan-sonar");

    var todaysGames = [];
    var currentSport = "nba";
    var currentSlate = { game_count: 0, has_today: true, has_tomorrow: false };
    var scanResultsVisible = false;
    var dashboardVisible = false;
    var loadedProps = {};       // event_id -> props array
    var lastScanGames = [];    // games from last scan (for parlay rebuild)

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
        scanSonar.classList.add("hidden");
        results.classList.add("hidden");
        errorBanner.classList.add("hidden");
        dashboardSection.classList.add("hidden");
        dashboardVisible = false;
        lottoResults.classList.add("hidden");
        lottoResults.innerHTML = "";
        playerSearchSection.classList.add("hidden");
        welcomeHero.classList.remove("hidden");
        closeSidebar();
    });

    // Hero sport card clicks — auto-scan on click
    document.querySelectorAll(".hero-sport-card").forEach(function (card) {
        card.addEventListener("click", function () {
            var sport = card.getAttribute("data-sport");
            currentSport = sport;
            sportBtns.forEach(function (b) { b.classList.remove("active"); });
            document.querySelector('.sport-btn[data-sport="' + sport + '"]').classList.add("active");
            navSportBadge.textContent = sport.toUpperCase();
            fetchGames();
            runScan();
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
            scanSonar.classList.add("hidden");
            results.classList.add("hidden");
            errorBanner.classList.add("hidden");
            dashboardSection.classList.add("hidden");
            dashboardVisible = false;
            lottoResults.classList.add("hidden");
            lottoResults.innerHTML = "";
            loadedProps = {};
            lastScanGames = [];
            if (testmodelSection) testmodelSection.classList.add("hidden");
            playerSearchSection.classList.add("hidden");
            welcomeHero.classList.remove("hidden");

            // Re-fetch games for ticker + autocomplete
            if (newSport !== "all") {
                fetchGames();
            }
        });
    });

    function fetchGames() {
        authFetch("/api/games?sport=" + currentSport)
            .then(function (res) { return res.json(); })
            .then(function (data) {
                todaysGames = data.games || [];
                currentSlate = data.slate || { game_count: 0, has_today: true, has_tomorrow: false };
                buildTicker(todaysGames);

                // Silent scan re-fetch if scan results are currently visible
                if (scanResultsVisible && !scanResults.classList.contains("hidden")) {
                    authFetch("/api/scan", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ sport: currentSport })
                    })
                    .then(function (res) { return res.json(); })
                    .then(function (scanData) {
                        if (scanData.success) {
                            renderScanResults(scanData.games || []);
                            // Hide cache indicator — fresh data arrived
                            var ci = document.getElementById("cache-indicator");
                            if (ci) ci.classList.add("hidden");
                        }
                    })
                    .catch(function () { /* silent fail — next tick retries */ });
                }
            })
            .catch(function () {
                todaysGames = [];
            });
    }

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
            var awayLabel = formatTeamLabel(g.away_team, g.away_rank);
            var homeLabel = formatTeamLabel(g.home_team, g.home_rank);
            var text = awayLabel + " vs " + homeLabel + " - ";
            if (g.date_label) text += g.date_label + " ";
            text += g.game_time_est + " EST";
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
    function runScan() {
        scanBtn.disabled = true;
        scanLoading.classList.remove("hidden");
        scanSonar.classList.remove("hidden");
        scanResults.classList.add("hidden");
        results.classList.add("hidden");
        errorBanner.classList.add("hidden");
        dashboardSection.classList.add("hidden");
        dashboardVisible = false;
        lottoResults.classList.add("hidden");
        lottoResults.innerHTML = "";
        if (testmodelSection) testmodelSection.classList.add("hidden");
        playerSearchSection.classList.add("hidden");
        welcomeHero.classList.add("hidden");

        authFetch("/api/scan", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ sport: currentSport })
        })
        .then(function (res) { return res.json(); })
        .then(function (data) {
            scanLoading.classList.add("hidden");
            scanSonar.classList.add("hidden");
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

            // Show cache indicator if results came from cache
            if (data.cached && data.cache_age) {
                var mins = Math.round(data.cache_age / 60);
                var label = mins < 1 ? "just now" : mins + " min ago";
                var indicator = document.getElementById("cache-indicator");
                if (indicator) {
                    indicator.textContent = "Updated " + label + " \u2022 Refreshing...";
                    indicator.classList.remove("hidden");
                    // Hide after fresh data arrives (next poll)
                    setTimeout(function () { indicator.classList.add("hidden"); }, 180000);
                }
            } else {
                var indicator = document.getElementById("cache-indicator");
                if (indicator) indicator.classList.add("hidden");
            }

            closeSidebar();
        })
        .catch(function () {
            scanLoading.classList.add("hidden");
            scanSonar.classList.add("hidden");
            scanBtn.disabled = false;
            showError("Gotham's signal went dark.");
        });
    }

    scanBtn.addEventListener("click", runScan);

    // Player Search sidebar button
    playerSearchBtn.addEventListener("click", function () {
        welcomeHero.classList.add("hidden");
        scanResults.classList.add("hidden");
        scanResultsVisible = false;
        scanSonar.classList.add("hidden");
        results.classList.add("hidden");
        errorBanner.classList.add("hidden");
        dashboardSection.classList.add("hidden");
        dashboardVisible = false;
        lottoResults.classList.add("hidden");
        lottoResults.innerHTML = "";
        if (testmodelSection) testmodelSection.classList.add("hidden");
        playerSearchSection.classList.remove("hidden");

        if (window.innerWidth <= 768) closeSidebar();
    });

    // Form submit
    form.addEventListener("submit", function (e) {
        e.preventDefault();

        results.classList.add("hidden");
        errorBanner.classList.add("hidden");
        scanResults.classList.add("hidden");
        scanResultsVisible = false;
        dashboardSection.classList.add("hidden");
        dashboardVisible = false;
        lottoResults.classList.add("hidden");
        lottoResults.innerHTML = "";
        if (testmodelSection) testmodelSection.classList.add("hidden");

        var payload = {
            player_name: document.getElementById("player_name").value,
            vegas_line: parseFloat(document.getElementById("vegas_line").value),
            games: parseInt(document.getElementById("games").value, 10),
            team_name: document.getElementById("team_name").value,
            sport: currentSport
        };

        loading.classList.remove("hidden");
        submitBtn.disabled = true;

        authFetch("/api/predict", {
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
            var aParts = data.action.split(' | ');
            if (aParts.length === 2) {
                leanBody.innerHTML = '<div class="action-text">' + aParts[0] + '</div>'
                    + '<div class="action-text action-text-secondary">' + aParts[1] + '</div>';
            } else {
                leanBody.innerHTML = '<div class="action-text">' + data.action + '</div>';
            }
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
        loadedProps = {};  // Reset loaded props on new scan
        lastScanGames = games;  // Store for parlay rebuilding

        // Sort: Today's games first, then Tomorrow's, by score within each group
        games.sort(function (a, b) {
            var aDay = a.date_label === "Today" ? 0 : 1;
            var bDay = b.date_label === "Today" ? 0 : 1;
            if (aDay !== bDay) return aDay - bDay;
            return b.confirmation_score - a.confirmation_score;
        });

        if (games.length === 0) {
            scanResults.innerHTML = '<div class="scan-empty-state">' +
                '<div class="scan-empty-headline">Gotham\'s quiet tonight.</div>' +
                '<div class="scan-empty-sub">No ' + currentSport.toUpperCase() + ' games on the board right now. Check back closer to game time or try another sport.</div>' +
                '</div>';
            scanResults.classList.remove("hidden");
            return;
        }

        var filtered = games.filter(function (g) {
            return getEffectivePct(g) >= getActionableThreshold(currentSport, g) || g.skip;
        });
        var nonSkip = games.filter(function (g) { return !g.skip; });

        var sportLabel = currentSport.toUpperCase();
        var dayLabel = (currentSlate.has_today && currentSlate.has_tomorrow) ? "Today & Tomorrow's"
            : currentSlate.has_tomorrow ? "Tomorrow's" : "Today's";

        if (filtered.length === 0) {
            // No strong plays — show top alternatives
            var alternatives = nonSkip.slice().sort(function (a, b) {
                var aDay = a.date_label === "Today" ? 0 : 1;
                var bDay = b.date_label === "Today" ? 0 : 1;
                if (aDay !== bDay) return aDay - bDay;
                return getEffectivePct(b) - getEffectivePct(a);
            }).slice(0, 5);

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

        // "Generate Top Props" button (NBA only, when today's games exist)
        if (currentSport === "nba" && currentSlate.has_today) {
            html += '<button id="generate-top-props-btn" class="generate-top-props-btn">Generate Top Props</button>';
        }

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
            var ep = getEffectivePct(g);
            var threshold = getActionableThreshold(currentSport, g);
            var nearMissFloor = isEvModelGame(g) ? 52.4 : COVER_PCT.nearMiss;
            return ep >= nearMissFloor && ep < threshold && filteredIds.indexOf(g.home_team + g.away_team) === -1;
        }).sort(function (a, b) {
            var aDay = a.date_label === "Today" ? 0 : 1;
            var bDay = b.date_label === "Today" ? 0 : 1;
            if (aDay !== bDay) return aDay - bDay;
            return getEffectivePct(b) - getEffectivePct(a);
        }).slice(0, 5);

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
            var games = (allSports[sport] || []).slice().sort(function (a, b) {
                var aDay = a.date_label === "Today" ? 0 : 1;
                var bDay = b.date_label === "Today" ? 0 : 1;
                if (aDay !== bDay) return aDay - bDay;
                return b.confirmation_score - a.confirmation_score;
            });
            var filtered = games.filter(function (g) { return getEffectivePct(g) >= getActionableThreshold(sport, g) || g.skip; });

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

    function buildCardMetadata(g, sport) {
        var html = '';
        // Venue
        if ((sport === "nhl" || sport === "cfb" || sport === "cbb" || sport === "nfl") && g.venue_name) {
            var venueText = g.venue_name;
            if (g.venue_city) {
                venueText += " — " + g.venue_city;
                if (g.venue_state) venueText += ", " + g.venue_state;
            }
            html += '<div class="scan-venue">' + venueText + '</div>';
        }
        // Time + Date label
        var timeText = '';
        if (g.date_label) timeText += '<span class="scan-date-label">' + g.date_label + '</span> — ';
        timeText += g.game_time_est + ' EST';
        html += '<div class="scan-time">' + timeText + '</div>';
        // Slot type label
        if ((sport === "cfb" || sport === "cbb" || sport === "nfl") && g.slot_type) {
            html += '<div class="scan-slot slot-' + g.slot_type + '">' + g.slot_type.toUpperCase() + '</div>';
        }
        return html;
    }

    function buildCardFactors(g, sport) {
        var html = '';
        // Rank Scam
        if (g.rank_scam && g.rank_scam.is_rank_scam) {
            var tierLabel = g.rank_scam.tier ? g.rank_scam.tier.toUpperCase() : '';
            html += '<div class="scan-rank-scam"><span class="rank-scam-label">RANK SCAM — ' + tierLabel + '</span> <span class="rank-scam-detail">' + g.rank_scam.scam_action + '</span></div>';
        }
        // Spread Discrepancy
        if (g.spread_discrepancy && g.spread_discrepancy.is_discrepancy) {
            html += '<div class="scan-spread-disc"><span class="spread-disc-label">SPREAD ALERT</span> <span class="spread-disc-detail">#' + g.spread_discrepancy.rank + ' expected ' + g.spread_discrepancy.expected_range + ' pts — ' + g.spread_discrepancy.discrepancy_action + '</span></div>';
        }
        // NFL Weather
        if (sport === "nfl") {
            if (g.weather_dome) {
                html += '<div class="scan-weather-alert dome"><span class="weather-label">DOME</span></div>';
            } else if (g.weather_alerts && g.weather_alerts.length > 0) {
                html += '<div class="scan-weather-alert"><span class="weather-label">WEATHER ALERT</span> <span class="weather-detail">' + g.weather_alerts.join(" | ") + '</span></div>';
            } else if (g.weather) {
                var wp = [];
                if (g.weather.temperature) wp.push(g.weather.temperature + "°F");
                if (g.weather.wind_speed) wp.push("Wind " + g.weather.wind_speed + " mph");
                if (g.weather.condition) wp.push(g.weather.condition);
                if (wp.length > 0) html += '<div class="scan-weather-info"><span class="weather-detail">' + wp.join(" | ") + '</span></div>';
            }
        }
        // NFL Trend Discrepancy
        if (g.trend_discrepancy && g.trend_discrepancy.applies) {
            var td = g.trend_discrepancy;
            html += '<div class="scan-trend-disc"><span class="trend-disc-label">TREND ALERT</span> ';
            if (td.home_signal) html += '<span class="' + (td.home_signal === "bounce-back" ? "trend-bounce" : "trend-regress") + '">Home (' + td.home_record + '): ' + td.home_signal.toUpperCase() + '</span> ';
            if (td.away_signal) html += '<span class="' + (td.away_signal === "bounce-back" ? "trend-bounce" : "trend-regress") + '">Away (' + td.away_record + '): ' + td.away_signal.toUpperCase() + '</span> ';
            if (td.strong_contrarian) html += '<span class="trend-strong">STRONG CONTRARIAN</span>';
            html += '</div>';
        }
        // NFL O/U
        if (g.overunder && g.overunder.applies) {
            html += '<div class="scan-ou-alert"><span class="ou-label">O/U ALERT</span> ';
            g.overunder.flags.forEach(function (flag) { html += '<span class="ou-detail">' + flag + '</span> '; });
            html += '</div>';
        }
        // B2B
        if (g.b2b) {
            html += '<div class="' + (g.b2b.b2b_bonus ? "scan-b2b-alert bonus" : "scan-b2b-alert penalty") + '"><span class="b2b-label">REST ALERT</span> <span class="b2b-detail">' + g.b2b.detail + '</span></div>';
        }
        // ATS
        if (g.ats_record) {
            html += '<div class="' + (g.ats_record.ats_bonus ? "scan-ats-record strong" : "scan-ats-record weak") + '"><span class="ats-label">ATS RECORD</span> <span class="ats-detail">' + g.ats_record.detail + '</span></div>';
        }
        // Sharp Money
        if (g.public_betting && g.public_betting.public_betting_bonus > 0) {
            html += '<div class="scan-sharp-money"><span class="sharp-label">SHARP MONEY</span> <span class="sharp-detail">' + g.public_betting.detail + '</span></div>';
        }
        // H2H
        if (g.head_to_head) {
            var h2hClass = g.head_to_head.h2h_revenge_bonus ? "scan-h2h revenge" : "scan-h2h dominance";
            var h2hLabel = g.head_to_head.h2h_revenge_bonus ? "REVENGE GAME" : "PRIOR MATCHUP";
            html += '<div class="' + h2hClass + '"><span class="h2h-label">' + h2hLabel + '</span> <span class="h2h-detail">' + g.head_to_head.detail + '</span></div>';
        }
        // Vegas Trap
        if (g.vegas_trap && g.vegas_trap.is_vegas_trap) {
            html += '<div class="scan-vegas-trap"><span class="vegas-trap-label">VEGAS TRAP</span> <span class="vegas-trap-detail">' + g.vegas_trap.detail + '</span></div>';
        }
        return html;
    }

    function buildCardProps(g, sport) {
        if (sport !== "nba" || g.date_label !== "Today" || g.skip) return '';
        var alreadyLoaded = loadedProps[g.event_id] && loadedProps[g.event_id].length > 0;
        var html = '<div class="scan-prism-section' + (alreadyLoaded ? ' prism-expanded' : '') + '" id="prism-section-' + g.event_id + '">';
        html += '<div class="prism-dropdown-toggle" data-event-id="' + g.event_id + '">';
        html += '<span class="prism-dropdown-label">Player Props</span>';
        html += '<span class="prism-dropdown-chevron">&#9660;</span>';
        html += '</div>';
        html += '<div class="prism-dropdown-body" id="prism-body-' + g.event_id + '">';
        if (alreadyLoaded) html += buildPrismInner(loadedProps[g.event_id]);
        html += '</div></div>';
        return html;
    }

    function getEffectivePct(g) {
        // EV model probability takes precedence for NBA
        if (g.ev_model && g.ev_model.active) return g.ev_model.probability;
        return g.cover_pct_calibrated != null ? g.cover_pct_calibrated : g.cover_pct;
    }

    function isEvModelGame(g) {
        return g.ev_model && g.ev_model.active;
    }

    function getActionableThreshold(sport, g) {
        // EV models: probabilities cluster 48-62%, use ~55.4% (3% edge over 52.38%)
        if ((sport === "nba" || sport === "nhl") && g && isEvModelGame(g)) return 55.4;
        return COVER_PCT.actionable;
    }

    function buildScanCard(g, sport, isAlt) {
        var pct = getEffectivePct(g);
        var pctClass = "pct-mid";
        if (pct >= COVER_PCT.parlaySafety) pctClass = "pct-high";
        if (isAlt) pctClass = "pct-low";

        var cardClass = g.skip ? "scan-card scan-card-skip" : "scan-card";
        if (isAlt) cardClass += " scan-card-alt";
        var html = '<div class="' + cardClass + '">';

        // Header: matchup + cover %
        var awayLabel = g.away_rank ? '<span class="scan-rank">#' + g.away_rank + '</span> ' + g.away_team : g.away_team;
        var homeLabel = g.home_rank ? '<span class="scan-rank">#' + g.home_rank + '</span> ' + g.home_team : g.home_team;
        html += '<div class="scan-card-header">';
        html += '<div class="scan-matchup">' + awayLabel + ' vs ' + homeLabel + '</div>';
        html += '<div class="scan-pct ' + pctClass + '">' + pct + '%';
        if (g.cover_pct_calibrated != null) {
            html += '<div class="scan-pct-raw">raw: ' + g.cover_pct + '%</div>';
        }
        html += '</div>';
        html += '</div>';

        html += buildCardMetadata(g, sport);
        html += buildCardFactors(g, sport);
        html += buildCardProps(g, sport);

        // Skip badge
        if (g.skip) html += '<div class="scan-skip-badge">SNF — Even the Joker passes</div>';

        // Action
        if (g.action) {
            var parts = g.action.split(' | ');
            if (parts.length === 2) {
                html += '<div class="scan-action scan-action-dual">';
                html += '<div class="scan-action-primary">' + parts[0] + '</div>';
                html += '<div class="scan-action-secondary">' + parts[1] + '</div>';
                html += '</div>';
            } else {
                html += '<div class="scan-action">' + g.action + '</div>';
            }
        }

        // Recommendation
        var recClass = "rec-monitor";
        if (g.recommendation === "STRONG PLAY") recClass = "rec-strong";
        else if (g.recommendation === "CONFIDENT") recClass = "rec-confident";
        else if (g.recommendation === "LEAN") recClass = "rec-lean";
        html += '<div class="scan-rec ' + recClass + '">' + g.recommendation + '</div>';

        // EV model edge badge (NBA only)
        if (isEvModelGame(g)) {
            var evEdge = g.ev_model.edge;
            var evEv = g.ev_model.ev_per_unit;
            var evClass = evEdge > 0 ? "ev-badge-pos" : "ev-badge-neg";
            html += '<div class="scan-ev-badge ' + evClass + '">';
            html += '<span class="ev-edge">' + (evEdge > 0 ? '+' : '') + evEdge + '% edge</span>';
            html += '<span class="ev-value">EV: ' + (evEv > 0 ? '+' : '') + evEv + 'c/$</span>';
            html += '</div>';
        }

        // Historical accuracy badge
        if (g.historical_accuracy && g.historical_sample_size) {
            html += '<div class="scan-backtest-badge"><span class="backtest-rate">' + g.historical_accuracy + '% hit rate</span><span class="backtest-sample">(' + g.historical_sample_size + ' similar picks)</span></div>';
        }

        html += '</div>';
        return html;
    }

    function buildPrismInner(props) {
        if (!props || props.length === 0) return '<div class="prism-empty">No actionable props found</div>';
        var actionable = props.filter(function (p) { return p.signal && p.signal !== "SKIP"; });
        if (actionable.length === 0) return '<div class="prism-empty">No actionable props found</div>';

        var html = '';
        actionable.forEach(function (p) {
            var signalClass = getSignalClass(p.signal);

            html += '<div class="prism-prop">';
            html += '<div class="prism-prop-info">';
            html += '<span class="prism-player-name">' + p.player_name + '</span>';
            html += '<span class="prism-stat-line">' + p.stat_type + ': ' + p.projection + ' proj vs ' + p.line + ' line (' + (p.edge > 0 ? '+' : '') + p.edge + ')</span>';
            html += '</div>';
            html += '<div class="prism-prop-signal">';
            html += '<span class="prism-signal-badge ' + signalClass + '">' + p.signal + '</span>';
            html += '<span class="prism-confidence">' + p.confidence + '%</span>';
            if (p.streak && p.streak.count >= 3) {
                html += '<span class="prism-streak-badge">' + p.streak.count + '/5 ' + p.streak.direction + '</span>';
            }
            if (p.minutes_volatile) {
                html += '<span class="prism-minutes-warn">MIN VOLATILE</span>';
            }
            html += '</div>';
            html += '</div>';
        });

        return html;
    }

    function loadPropsForGame(eventId) {
        var body = document.getElementById("prism-body-" + eventId);
        if (!body) return;

        // Already loaded
        if (loadedProps[eventId]) return;

        // Show loading state
        body.innerHTML = '<div class="prism-loading"><div class="spinner" style="display:inline-block;width:14px;height:14px;margin-right:6px;vertical-align:middle"></div><span style="font-size:0.8rem;color:var(--text-muted)">Loading props...</span></div>';

        authFetch("/api/props?event_id=" + eventId + "&sport=" + currentSport)
            .then(function (res) { return res.json(); })
            .then(function (data) {
                if (data.success) {
                    var props = data.props || [];
                    loadedProps[eventId] = props;
                    body.innerHTML = buildPrismInner(props);
                    // Update the toggle label with count
                    var section = document.getElementById("prism-section-" + eventId);
                    if (section) {
                        var label = section.querySelector(".prism-dropdown-label");
                        var actionable = props.filter(function (p) { return p.signal && p.signal !== "SKIP"; });
                        if (label && actionable.length > 0) {
                            label.innerHTML = 'Player Props <span class="prism-count">' + actionable.length + '</span>';
                        }
                    }
                    rebuildParlays();
                } else {
                    body.innerHTML = '<div class="prism-empty">Failed to load props</div>';
                }
            })
            .catch(function () {
                body.innerHTML = '<div class="prism-empty">Connection error</div>';
            });
    }

    // Delegate click handler for dropdown toggle
    document.addEventListener("click", function (e) {
        var toggle = e.target.closest(".prism-dropdown-toggle");
        if (toggle) {
            var eventId = toggle.getAttribute("data-event-id");
            var section = document.getElementById("prism-section-" + eventId);
            if (!section) return;

            var isExpanded = section.classList.contains("prism-expanded");
            if (isExpanded) {
                // Collapse
                section.classList.remove("prism-expanded");
            } else {
                // Expand — load props if not yet loaded
                section.classList.add("prism-expanded");
                if (!loadedProps[eventId]) {
                    loadPropsForGame(eventId);
                }
            }
        }
    });

    function generateTopProps() {
        var btn = document.getElementById("generate-top-props-btn");
        if (!btn) return;

        // Show loading state
        btn.disabled = true;
        btn.innerHTML = '<div class="spinner" style="display:inline-block;width:14px;height:14px;margin-right:6px;vertical-align:middle"></div>Generating Props...';

        authFetch("/api/top-props?sport=" + currentSport)
            .then(function (res) { return res.json(); })
            .then(function (data) {
                if (data.success) {
                    var props = data.props || [];
                    // Populate loadedProps by event_id
                    loadedProps = {};
                    props.forEach(function (p) {
                        if (!loadedProps[p.event_id]) loadedProps[p.event_id] = [];
                        loadedProps[p.event_id].push(p);
                    });
                    // Inject props into per-game dropdown bodies
                    Object.keys(loadedProps).forEach(function (eid) {
                        var body = document.getElementById("prism-body-" + eid);
                        if (body) body.innerHTML = buildPrismInner(loadedProps[eid]);
                        // Expand and update label
                        var section = document.getElementById("prism-section-" + eid);
                        if (section) {
                            section.classList.add("prism-expanded");
                            var label = section.querySelector(".prism-dropdown-label");
                            var actionable = (loadedProps[eid] || []).filter(function (p) { return p.signal && p.signal !== "SKIP"; });
                            if (label && actionable.length > 0) {
                                label.innerHTML = 'Player Props <span class="prism-count">' + actionable.length + '</span>';
                            }
                        }
                    });
                    // Render top props section
                    renderTopProps(props);
                    // Rebuild parlays to include prop legs
                    rebuildParlays();
                    // Replace button with success state
                    btn.innerHTML = 'Props Generated (' + props.length + ' signals)';
                    btn.classList.add("top-props-done");
                } else {
                    btn.disabled = false;
                    btn.innerHTML = 'Generate Top Props';
                    alert("Failed to generate props: " + (data.error || "Unknown error"));
                }
            })
            .catch(function () {
                btn.disabled = false;
                btn.innerHTML = 'Generate Top Props';
                alert("Connection error generating props.");
            });
    }

    // Delegate click handler for Generate Top Props button
    document.addEventListener("click", function (e) {
        if (e.target.closest("#generate-top-props-btn")) {
            generateTopProps();
        }
    });

    function rebuildParlays() {
        if (!lastScanGames.length) return;

        // Inject loaded props into game objects for parlay builder
        var gamesWithProps = lastScanGames.map(function (g) {
            var copy = Object.assign({}, g);
            if (loadedProps[g.event_id]) {
                copy.player_props = loadedProps[g.event_id];
            }
            return copy;
        });

        // Rebuild parlays section
        var parlaysEl = document.querySelector(".parlays-section");
        if (parlaysEl) {
            var filtered = gamesWithProps.filter(function (g) { return getEffectivePct(g) >= getActionableThreshold(currentSport, g) || g.skip; });
            if (filtered.length < 2) filtered = gamesWithProps;
            var newParlayHtml = buildParlaySection(filtered);
            if (newParlayHtml) {
                parlaysEl.outerHTML = newParlayHtml;
            }
        }
    }

    function renderTopProps(allProps) {
        if (!allProps || allProps.length === 0) {
            var existing = document.getElementById("top-props-section");
            if (existing) existing.remove();
            return;
        }

        // Already sorted by confidence from backend; show top 15
        var topProps = allProps.slice(0, 15);

        var html = '<div id="top-props-section" class="top-props-section">';
        html += '<h2 class="scan-title">Top Player Props</h2>';
        html += '<div class="top-props-grid">';

        topProps.forEach(function (prop) {
            var signalClass = getSignalClass(prop.signal);

            html += '<div class="top-prop-card">';
            html += '<div class="prism-prop-info">';
            html += '<span class="prism-player-name">' + prop.player_name + ' <span class="top-prop-team">(' + (prop.matchup || prop.team || '') + ')</span></span>';
            html += '<span class="prism-stat-line">' + prop.stat_type + ': ' + prop.projection + ' proj vs ' + prop.line + ' line (' + (prop.edge > 0 ? '+' : '') + prop.edge + ')</span>';
            html += '</div>';
            html += '<div class="prism-prop-signal">';
            html += '<span class="prism-signal-badge ' + signalClass + '">' + prop.signal + '</span>';
            html += '<span class="prism-confidence">' + prop.confidence + '%</span>';
            if (prop.streak) {
                html += '<span class="prism-streak-badge">' + prop.streak.count + '/5 ' + prop.streak.direction + '</span>';
            }
            if (prop.minutes_unstable) {
                html += '<span class="prism-minutes-warn">MIN VOLATILE</span>';
            }
            html += '</div>';
            html += '</div>';
        });

        html += '</div></div>';

        // Insert before parlays section (or after scan grid)
        var existing = document.getElementById("top-props-section");
        if (existing) {
            existing.outerHTML = html;
        } else {
            var parlaysEl = document.querySelector(".parlays-section");
            if (parlaysEl) {
                parlaysEl.insertAdjacentHTML("beforebegin", html);
            } else {
                scanResults.insertAdjacentHTML("beforeend", html);
            }
        }
    }

    function buildParlaySection(games) {
        if (games.length < 2) return "";

        // Spread legs only for parlays (use calibrated pct when available)
        var spreadLegs = games.slice().sort(function (a, b) { return getEffectivePct(b) - getEffectivePct(a); });

        // Collect all props across games (today only) to find Best Prop of the Day
        var allProps = [];
        games.forEach(function (g) {
            var props = g.player_props || loadedProps[g.event_id] || [];
            if (!props.length) return;
            if (g.date_label === "Tomorrow") return;
            props.forEach(function (p) {
                allProps.push({
                    player_name: p.player_name,
                    team: p.team || '',
                    matchup: p.matchup || g.away_team + ' @ ' + g.home_team,
                    stat_type: p.stat_type,
                    projection: p.projection,
                    line: p.line,
                    edge: p.edge,
                    signal: p.signal,
                    confidence: p.confidence,
                    streak: p.streak
                });
            });
        });
        allProps.sort(function (a, b) { return b.confidence - a.confidence; });

        var html = '<div class="parlays-section">';
        html += '<h2 class="scan-title">The Joker\'s Parlays</h2>';

        // Best Prop of the Day — top prop across all games
        if (allProps.length > 0) {
            var best = allProps[0];
            var direction = best.signal.indexOf("OVER") !== -1 ? "OVER" : "UNDER";
            var bestOdds = pctToAmericanOdds(best.confidence);
            var signalClass = getSignalClass(best.signal);

            html += '<div class="best-prop-card">';
            html += '<div class="best-prop-header">';
            html += '<span class="best-prop-label">Best Prop of the Day</span>';
            html += '<span class="best-prop-odds">' + bestOdds + '</span>';
            html += '</div>';
            html += '<div class="best-prop-pick">' + best.player_name + ' ' + direction + ' ' + best.line + ' ' + best.stat_type + '</div>';
            html += '<div class="best-prop-details">';
            html += '<span class="best-prop-matchup">' + best.matchup + '</span>';
            html += '<span class="prism-signal-badge ' + signalClass + '">' + best.signal + '</span>';
            html += '<span class="best-prop-confidence">' + best.confidence + '%</span>';
            html += '</div>';
            html += '<div class="best-prop-line">Proj ' + best.projection + ' vs Line ' + best.line + ' (' + (best.edge > 0 ? '+' : '') + best.edge + ' edge)</div>';
            if (best.streak && best.streak.count >= 3) {
                html += '<div class="best-prop-streak">' + best.streak.count + '/5 ' + best.streak.direction + '</div>';
            }
            html += '</div>';
        }

        // Safety Parlay: 2 legs, 80%+ each (spreads only)
        var safetyLegs = spreadLegs.filter(function (g) { return getEffectivePct(g) >= COVER_PCT.parlaySafety; }).slice(0, 2);
        if (safetyLegs.length >= 2) {
            var safetyOdds = calcParlayOdds(safetyLegs);
            var safetyProb = calcCombinedProb(safetyLegs);
            html += buildParlayCard("Two-Face's Safe Bet", safetyLegs, safetyOdds, safetyProb, "parlay-safety");
        }

        // Normal Parlay: 4-6 legs, 67.5%+ each (spreads only)
        var normalPool = spreadLegs.filter(function (g) { return getEffectivePct(g) >= COVER_PCT.parlayNormal; });
        var normalLegs = normalPool.slice(0, Math.min(6, Math.max(4, normalPool.length)));
        if (normalLegs.length >= 4) {
            var normalOdds = calcParlayOdds(normalLegs);
            var normalProb = calcCombinedProb(normalLegs);
            html += buildParlayCard("Gotham Gambit", normalLegs, normalOdds, normalProb, "parlay-normal");
        } else if (normalPool.length >= 2) {
            var normalOdds = calcParlayOdds(normalPool);
            var normalProb = calcCombinedProb(normalPool);
            html += buildParlayCard("Gotham Gambit", normalPool, normalOdds, normalProb, "parlay-normal");
        }

        // YOLO Parlay: spread legs 60%+ (spreads only)
        var yoloSpreads = spreadLegs.filter(function (g) { return getEffectivePct(g) >= COVER_PCT.parlayYolo; });
        if (yoloSpreads.length >= 3) {
            var yoloLegs = yoloSpreads.slice(0, Math.min(10, yoloSpreads.length));
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
            var effPct = getEffectivePct(g);
            var legOdds = pctToAmericanOdds(effPct);
            var pickLabel = g.action || (g.lean_team ? g.lean_team : g.home_team);
            var legClass = g.is_prop ? "parlay-leg parlay-leg-prop" : "parlay-leg";
            html += '<div class="' + legClass + '">';
            if (g.is_prop) {
                html += '<span class="parlay-leg-tag">PROP</span>';
            }
            html += '<span class="parlay-leg-pick">' + pickLabel + '</span>';
            html += '<span class="parlay-leg-odds">' + legOdds + '</span>';
            html += '<span class="parlay-leg-pct">' + effPct + '%</span>';
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
            var prob = getEffectivePct(g) / 100;
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
            prob *= (getEffectivePct(g) / 100);
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

        games.forEach(function (g) {
            var awayLabel = formatTeamLabel(g.away_team, g.away_rank);
            var homeLabel = formatTeamLabel(g.home_team, g.home_rank);
            var tickerTime = '';
            if (g.date_label) {
                tickerTime += g.date_label + ' — ';
            }
            tickerTime += g.game_time_est + ' EST';
            items += '<span class="ticker-item">' +
                '<span class="ticker-teams">' + awayLabel + ' @ ' + homeLabel + '</span>' +
                '<span class="ticker-time">' + tickerTime + '</span>' +
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
        if (testmodelSection) testmodelSection.classList.add("hidden");
        playerSearchSection.classList.add("hidden");

        authFetch("/api/scan", {
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
                return getEffectivePct(g) >= COVER_PCT.lotto && !g.skip;
            });
            if (eligible.length === 0) return;

            // Sort by effective pct desc, tiebreak by confirmation_score desc
            eligible.sort(function (a, b) {
                var pa = getEffectivePct(a), pb = getEffectivePct(b);
                if (pb !== pa) return pb - pa;
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
            var effPct = getEffectivePct(g);
            var legOdds = pctToAmericanOdds(effPct);
            var pickLabel = g.action || (g.lean_team ? g.lean_team : g.home_team);
            html += '<div class="parlay-leg">';
            html += '<span class="lotto-sport-badge lotto-badge-' + g._sport + '">' + sportNames[g._sport] + '</span>';
            html += '<span class="parlay-leg-pick">' + pickLabel + '</span>';
            html += '<span class="parlay-leg-odds">' + legOdds + '</span>';
            html += '<span class="parlay-leg-pct">' + effPct + '%</span>';
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
        if (testmodelSection) testmodelSection.classList.add("hidden");
        playerSearchSection.classList.add("hidden");
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

        authFetch("/api/grade", {
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

        authFetch(url)
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

    function formatCi(ci) {
        if (!ci || ci.ci_lower == null) return '';
        return '<span class="dash-ci">[' + ci.ci_lower + '-' + ci.ci_upper + '%]</span>';
    }

    function renderDashboardStats(o) {
        var rateClass = o.win_rate >= 55 ? "stat-green" : o.win_rate >= 45 ? "stat-yellow" : "stat-red";
        var ciHtml = o.win_rate_ci ? formatCi(o.win_rate_ci) : '';
        var html = '<div class="dash-stat-cards">';
        html += '<div class="dash-stat-card">';
        html += '<div class="dash-stat-label">Record</div>';
        html += '<div class="dash-stat-value">' + o.wins + '-' + o.losses + (o.pushes > 0 ? '-' + o.pushes : '') + '</div>';
        html += '</div>';
        html += '<div class="dash-stat-card">';
        html += '<div class="dash-stat-label">Win Rate</div>';
        html += '<div class="dash-stat-value ' + rateClass + '">' + o.win_rate + '%' + ciHtml + '</div>';
        html += '</div>';
        html += '<div class="dash-stat-card">';
        html += '<div class="dash-stat-label">Total Picks</div>';
        html += '<div class="dash-stat-value">' + o.total + '</div>';
        html += '</div>';
        html += '<div class="dash-stat-card">';
        html += '<div class="dash-stat-label">Pending</div>';
        html += '<div class="dash-stat-value stat-muted">' + o.pending + '</div>';
        html += '</div>';
        html += '</div>';
        return html;
    }

    function renderDashboardBreakdowns(data) {
        var html = '';
        if (data.by_sport && data.by_sport.length > 0) {
            html += '<div class="dash-breakdown">';
            html += '<h3 class="dash-section-title">By Sport</h3>';
            data.by_sport.forEach(function (s) {
                html += buildBreakdownRow(s.sport.toUpperCase(), s);
            });
            html += '</div>';
        }
        if (data.by_slot && data.by_slot.length > 0) {
            html += '<div class="dash-breakdown">';
            html += '<h3 class="dash-section-title">By Slot Type</h3>';
            data.by_slot.forEach(function (s) {
                html += buildBreakdownRow(s.slot_type.toUpperCase(), s);
            });
            html += '</div>';
        }
        if (data.by_recommendation && data.by_recommendation.length > 0) {
            html += '<div class="dash-breakdown">';
            html += '<h3 class="dash-section-title">By Recommendation</h3>';
            data.by_recommendation.forEach(function (s) {
                html += buildBreakdownRow(s.recommendation, s);
            });
            html += '</div>';
        }
        return html;
    }

    function formatDateLabel(dateKey) {
        if (dateKey === "Unknown" || dateKey.length < 10) return dateKey;
        try {
            var parts = dateKey.split("-");
            var dt = new Date(parseInt(parts[0]), parseInt(parts[1]) - 1, parseInt(parts[2]));
            var today = new Date();
            today.setHours(0, 0, 0, 0);
            var yesterday = new Date(today);
            yesterday.setDate(yesterday.getDate() - 1);
            var dtDay = new Date(dt);
            dtDay.setHours(0, 0, 0, 0);
            if (dtDay.getTime() === today.getTime()) return "Today";
            if (dtDay.getTime() === yesterday.getTime()) return "Yesterday";
            var days = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
            var months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
            return days[dt.getDay()] + ", " + months[dt.getMonth()] + " " + dt.getDate();
        } catch (e) {
            return dateKey;
        }
    }

    function renderDashboardHistory(recent) {
        if (!recent || recent.length === 0) return '';
        var html = '<h3 class="dash-section-title">Pick History</h3>';

        // Group by game_date (fall back to created_at date)
        var groups = {};
        var groupOrder = [];
        recent.forEach(function (p) {
            var dateKey = p.game_date || "";
            if (!dateKey && p.created_at) dateKey = p.created_at.substring(0, 10);
            if (!dateKey) dateKey = "Unknown";
            if (!groups[dateKey]) { groups[dateKey] = []; groupOrder.push(dateKey); }
            groups[dateKey].push(p);
        });

        groupOrder.forEach(function (dateKey) {
            var preds = groups[dateKey];
            var dayW = 0, dayL = 0, dayP = 0, dayPend = 0;
            preds.forEach(function (p) {
                if (p.result === "HIT") dayW++;
                else if (p.result === "MISS") dayL++;
                else if (p.result === "PUSH") dayP++;
                else dayPend++;
            });
            var dayRecord = dayW + "-" + dayL;
            if (dayP > 0) dayRecord += "-" + dayP;
            if (dayPend > 0) dayRecord += " (" + dayPend + " pending)";

            html += '<div class="dash-date-group">';
            html += '<div class="dash-date-header">';
            html += '<span class="dash-date-label">' + formatDateLabel(dateKey) + '</span>';
            html += '<span class="dash-date-record">' + dayRecord + '</span>';
            html += '</div>';

            html += '<div class="dash-recent-list">';
            preds.forEach(function (p) {
                var statusClass = "status-pending";
                if (p.result === "HIT") statusClass = "status-hit";
                else if (p.result === "MISS") statusClass = "status-miss";
                else if (p.result === "PUSH") statusClass = "status-push";

                var borderClass = "dash-recent-border-pending";
                if (p.result === "HIT") borderClass = "dash-recent-border-hit";
                else if (p.result === "MISS") borderClass = "dash-recent-border-miss";
                else if (p.result === "PUSH") borderClass = "dash-recent-border-push";

                html += '<div class="dash-recent-item ' + borderClass + '">';
                html += '<div class="dash-recent-top">';
                html += '<span class="dash-recent-sport">' + p.sport.toUpperCase() + '</span>';
                html += '<span class="dash-recent-matchup">' + p.away_team + ' vs ' + p.home_team + '</span>';
                html += '<span class="dash-recent-status ' + statusClass + '">' + p.result + '</span>';
                html += '</div>';
                html += '<div class="dash-recent-bottom">';
                html += '<span class="dash-recent-action">' + (p.action || '') + '</span>';
                if (p.home_score !== null && p.away_score !== null) {
                    html += '<span class="dash-recent-score">' + p.away_score + '-' + p.home_score + '</span>';
                }
                html += '<span class="dash-recent-pct">' + p.cover_pct + '%</span>';
                if (p.clv !== null && p.clv !== undefined) {
                    var clvClass = p.clv > 0 ? 'clv-positive' : p.clv < 0 ? 'clv-negative' : 'clv-neutral';
                    html += '<span class="dash-recent-clv ' + clvClass + '">' + (p.clv > 0 ? '+' : '') + p.clv + ' CLV</span>';
                }
                html += '</div>';
                html += '</div>';
            });
            html += '</div>';
            html += '</div>';
        });
        return html;
    }

    function renderDashboardCLV(clv) {
        if (!clv || !clv.clv_total) return '';
        var html = '<h3 class="dash-section-title">Closing Line Value (CLV)</h3>';

        // Sport summary cards
        if (clv.clv_by_sport && clv.clv_by_sport.length > 0) {
            html += '<div class="dash-stat-cards">';
            clv.clv_by_sport.forEach(function (s) {
                var clvClass = s.avg_clv > 0 ? 'clv-positive' : s.avg_clv < 0 ? 'clv-negative' : 'clv-neutral';
                var hrClass = s.clv_hit_rate >= 55 ? 'clv-positive' : s.clv_hit_rate < 45 ? 'clv-negative' : 'clv-neutral';
                html += '<div class="dash-stat-card clv-sport-card">';
                html += '<div class="dash-stat-label">' + s.sport.toUpperCase() + '</div>';
                html += '<div class="dash-stat-value ' + clvClass + '">' + (s.avg_clv > 0 ? '+' : '') + s.avg_clv + ' pts</div>';
                html += '<div class="clv-substat ' + hrClass + '">' + s.clv_hit_rate + '% beat close (' + s.count + ')</div>';
                html += '</div>';
            });
            html += '</div>';
        }

        // By tier table
        if (clv.clv_by_tier && clv.clv_by_tier.length > 0) {
            html += '<div class="tm-feat-section"><table class="tm-feat-table"><thead><tr>';
            html += '<th>Tier</th><th>Picks</th><th>Avg CLV</th><th>Beat Close</th>';
            html += '</tr></thead><tbody>';
            clv.clv_by_tier.forEach(function (t) {
                var clvClass = t.avg_clv > 0 ? 'clv-positive' : t.avg_clv < 0 ? 'clv-negative' : 'clv-neutral';
                var hrClass = t.clv_hit_rate >= 55 ? 'clv-positive' : t.clv_hit_rate < 45 ? 'clv-negative' : 'clv-neutral';
                html += '<tr><td>' + t.tier + '</td><td>' + t.count + '</td>';
                html += '<td class="' + clvClass + '">' + (t.avg_clv > 0 ? '+' : '') + t.avg_clv + '</td>';
                html += '<td class="' + hrClass + '">' + t.clv_hit_rate + '%</td></tr>';
            });
            html += '</tbody></table></div>';
        }

        // Overall summary
        var avgClass = clv.avg_clv > 0 ? 'clv-positive' : clv.avg_clv < 0 ? 'clv-negative' : 'clv-neutral';
        html += '<div class="clv-summary">';
        html += '<span class="' + avgClass + '">Overall: ' + (clv.avg_clv > 0 ? '+' : '') + clv.avg_clv + ' pts avg CLV</span>';
        html += ' | <span>' + clv.clv_hit_rate + '% beat the close (' + clv.clv_total + ' picks)</span>';
        html += '</div>';

        html += '<div class="clv-guide">Positive avg CLV = genuine edge. CLV is more reliable than win rate for small samples.</div>';
        return html;
    }

    function renderDashboard(data) {
        document.getElementById("dashboard-stats").innerHTML = renderDashboardStats(data.overall);
        document.getElementById("dashboard-clv").innerHTML = renderDashboardCLV(data.clv);
        document.getElementById("dashboard-breakdowns").innerHTML = renderDashboardBreakdowns(data);
        document.getElementById("dashboard-recent").innerHTML = renderDashboardHistory(data.recent);
        document.getElementById("dashboard-model-health").innerHTML = "";
        fetchModelHealth();
    }

    function fetchModelHealth() {
        authFetch("/api/model-health")
            .then(function (res) { return res.json(); })
            .then(function (data) {
                if (data.success && data.sports) {
                    document.getElementById("dashboard-model-health").innerHTML = renderModelHealth(data.sports);
                    wireMethodologyModal();
                }
            })
            .catch(function () {});
    }

    function renderModelHealth(sports) {
        var sportKeys = ["nba", "nhl", "cbb", "nfl", "cfb"];
        var sportLabels = { nba: "NBA", nhl: "NHL", cbb: "CBB", nfl: "NFL", cfb: "CFB" };
        var hasAny = false;
        for (var i = 0; i < sportKeys.length; i++) {
            if (sports[sportKeys[i]] && sports[sportKeys[i]].in_sample) { hasAny = true; break; }
        }
        if (!hasAny) return '';

        var html = '<div class="mh-header">';
        html += '<h3>Model Health</h3>';
        html += '<button type="button" class="mh-methodology-link" id="mh-methodology-btn">Methodology</button>';
        html += '</div>';
        html += '<div class="mh-grid">';

        for (var i = 0; i < sportKeys.length; i++) {
            var key = sportKeys[i];
            var s = sports[key];
            if (!s) continue;
            var conf = s.data_confidence || {};
            var badgeClass = "mh-badge-" + (conf.level || "medium");

            html += '<div class="mh-card">';
            html += '<div class="mh-card-header">';
            html += '<span class="mh-sport-name">' + sportLabels[key] + '</span>';
            html += '<span class="mh-confidence-badge ' + badgeClass + '">' + (conf.label || "?") + ' (' + (conf.games || "?") + ' games)</span>';
            html += '</div>';

            // In-sample accuracy
            if (s.in_sample) {
                html += '<div class="mh-metric-row">';
                html += '<span class="mh-metric-label">In-Sample Acc</span>';
                html += '<span class="mh-metric-value">' + (s.in_sample.accuracy != null ? s.in_sample.accuracy + '%' : '--') + '</span>';
                html += '</div>';
                if (s.in_sample.roi != null) {
                    html += '<div class="mh-metric-row">';
                    html += '<span class="mh-metric-label">In-Sample ROI</span>';
                    html += '<span class="mh-metric-value">' + (s.in_sample.roi >= 0 ? '+' : '') + s.in_sample.roi + '%</span>';
                    html += '</div>';
                }
                if (s.in_sample.strong_accuracy != null) {
                    html += '<div class="mh-metric-row">';
                    html += '<span class="mh-metric-label">STRONG PLAY</span>';
                    html += '<span class="mh-metric-value">' + s.in_sample.strong_accuracy + '%';
                    if (s.in_sample.strong_ci) {
                        html += '<span class="mh-ci">[' + s.in_sample.strong_ci[0] + '-' + s.in_sample.strong_ci[1] + '%]</span>';
                    }
                    html += ' <span class="mh-ci">(n=' + s.in_sample.strong_n + ')</span></span>';
                    html += '</div>';
                }
            } else {
                html += '<div class="mh-no-data">No backtest data</div>';
            }

            // Out-of-sample accuracy
            if (s.out_of_sample) {
                html += '<div class="mh-metric-row">';
                html += '<span class="mh-metric-label">Out-of-Sample Acc</span>';
                html += '<span class="mh-metric-value">' + (s.out_of_sample.accuracy != null ? s.out_of_sample.accuracy + '%' : '--') + '</span>';
                html += '</div>';
                if (s.out_of_sample.strong_accuracy != null) {
                    html += '<div class="mh-metric-row">';
                    html += '<span class="mh-metric-label">OOS STRONG</span>';
                    html += '<span class="mh-metric-value">' + s.out_of_sample.strong_accuracy + '%';
                    if (s.out_of_sample.strong_ci) {
                        html += '<span class="mh-ci">[' + s.out_of_sample.strong_ci[0] + '-' + s.out_of_sample.strong_ci[1] + '%]</span>';
                    }
                    if (s.out_of_sample.strong_n != null) {
                        html += ' <span class="mh-ci">(n=' + s.out_of_sample.strong_n + ')</span>';
                    }
                    html += '</span></div>';
                }
            } else {
                html += '<div class="mh-metric-row"><span class="mh-metric-label">Out-of-Sample</span><span class="mh-no-data">Not run yet</span></div>';
            }

            // Overfit gap
            if (s.overfit_gap != null) {
                var gapClass = s.overfit_gap <= 3 ? "mh-gap-green" : s.overfit_gap <= 8 ? "mh-gap-yellow" : "mh-gap-red";
                html += '<div class="mh-metric-row">';
                html += '<span class="mh-metric-label">Overfit Gap</span>';
                html += '<span class="mh-metric-value ' + gapClass + '">' + s.overfit_gap + '%</span>';
                html += '</div>';
            }

            // Calibration ECE
            if (s.calibration_ece != null) {
                var eceClass = s.calibration_ece < 5 ? "mh-gap-green" : s.calibration_ece < 10 ? "mh-gap-yellow" : "mh-gap-red";
                html += '<div class="mh-metric-row">';
                html += '<span class="mh-metric-label">Calibration ECE</span>';
                html += '<span class="mh-metric-value ' + eceClass + '">' + s.calibration_ece.toFixed(1) + '%</span>';
                html += '</div>';
            }

            // CLV
            if (s.clv_avg != null) {
                var clvClass = s.clv_avg > 0 ? "clv-positive" : s.clv_avg < 0 ? "clv-negative" : "clv-neutral";
                html += '<div class="mh-metric-row">';
                html += '<span class="mh-metric-label">CLV Avg</span>';
                html += '<span class="mh-metric-value ' + clvClass + '">' + (s.clv_avg >= 0 ? '+' : '') + s.clv_avg.toFixed(1) + '</span>';
                html += '</div>';
            }

            // Last updated
            if (s.last_backtest_date) {
                var dt = s.last_backtest_date.substring(0, 10);
                html += '<div class="mh-updated">Last backtest: ' + dt + '</div>';
            }

            html += '</div>';
        }

        html += '</div>';
        return html;
    }

    function wireMethodologyModal() {
        var btn = document.getElementById("mh-methodology-btn");
        var modal = document.getElementById("methodology-modal");
        var closeBtn = document.getElementById("methodology-close");
        if (!btn || !modal) return;

        // Populate content on first click
        var body = document.getElementById("methodology-body");
        if (body && !body.innerHTML) {
            body.innerHTML = renderMethodology();
        }

        btn.onclick = function () { modal.classList.remove("hidden"); };
        closeBtn.onclick = function () { modal.classList.add("hidden"); };
        modal.onclick = function (e) {
            if (e.target === modal) modal.classList.add("hidden");
        };
    }

    function renderMethodology() {
        var html = '';
        html += '<h2>How Scores Work</h2>';
        html += '<p>Each game receives a composite score from confirmation factors (line movement, injuries, ATS records, sharp money, etc). The score maps linearly to a cover percentage: <strong>cover% = 50 + (score / max_score) * 45</strong>. Sport-specific weights were calibrated through historical backtesting.</p>';

        html += '<h2>Walk-Forward Validation</h2>';
        html += '<p>Walk-forward validation splits historical data chronologically &mdash; train on older games, test on newer ones. This prevents look-ahead bias that inflates in-sample numbers.</p>';
        html += '<p><strong>Out-of-sample numbers are the honest measure.</strong> In-sample accuracy is always optimistic because the model was tuned on that data. A typical accuracy drop from in-sample to out-of-sample is 5-15% for sports betting models.</p>';

        html += '<h2>Closing Line Value (CLV)</h2>';
        html += '<p>CLV measures whether you got a better number than the market close. Positive CLV indicates a genuine edge &mdash; the market moved toward your position after you would have bet.</p>';
        html += '<ul>';
        html += '<li>Long-term profitability correlates more with CLV than raw win rate</li>';
        html += '<li>A model with +0.5 CLV that wins 52% is better than one with -0.3 CLV that wins 55%</li>';
        html += '<li>Negative CLV means the market is consistently smarter than the model</li>';
        html += '</ul>';

        html += '<h2>Confidence Intervals</h2>';
        html += '<p>All accuracy metrics use <strong>Wilson score intervals</strong> (95% CI). Unlike simple percentages, CIs communicate how reliable a number is given the sample size.</p>';
        html += '<p>Example: "74% accuracy on 19 bets" has a CI of [56%-92%]. The true accuracy could easily be near coin-flip levels. CIs widen dramatically below ~50 samples.</p>';

        html += '<h2>Current Limitations</h2>';
        html += '<ul>';
        html += '<li><strong>Non-replayable factors:</strong> Trell Rule (+5), public betting signals (+3/+5), feedback loop, and NFL weather cannot be replayed in backtests. Their actual contribution is unknown.</li>';
        html += '<li><strong>Small samples:</strong> NFL (105 games) and CFB (51 games) lack sufficient data for reliable weight tuning. Their overrides fall back to universal defaults.</li>';
        html += '<li><strong>Estimated prop lines:</strong> When The-Odds-API lines are unavailable, PRISM uses estimated lines (season avg * discount), which are less accurate.</li>';
        html += '<li><strong>Hand-tuned multipliers:</strong> PRISM matchup/pace/rest multipliers are set by domain knowledge, not data-derived.</li>';
        html += '</ul>';

        return html;
    }

    function buildBreakdownRow(label, stats) {
        var rateClass = stats.win_rate >= 55 ? "stat-green" : stats.win_rate >= 45 ? "stat-yellow" : "stat-red";
        var decided = stats.wins + stats.losses;
        var ciHtml = stats.win_rate_ci ? formatCi(stats.win_rate_ci) : '';
        var html = '<div class="dash-breakdown-row">';
        html += '<span class="dash-breakdown-label">' + label + '</span>';
        html += '<span class="dash-breakdown-record">' + stats.wins + '-' + stats.losses;
        if (stats.pushes > 0) html += '-' + stats.pushes;
        html += '</span>';
        html += '<span class="dash-breakdown-rate ' + rateClass + '">' + stats.win_rate + '%' + ciHtml + '</span>';
        html += '</div>';
        return html;
    }

    // ─── Test Model ─────────────────────────────────────────────────────

    var testmodelBtn = document.getElementById("testmodel-btn");
    var testmodelLoading = document.getElementById("testmodel-loading");
    var testmodelSection = document.getElementById("testmodel-section");
    var tmPollTimers = { collect: null, backtest: null, rules: null };
    var tmSport = "nba";

    function clearAllPolls() {
        Object.keys(tmPollTimers).forEach(function (key) {
            if (tmPollTimers[key]) {
                clearInterval(tmPollTimers[key]);
                tmPollTimers[key] = null;
            }
        });
    }

    function startPoll(name, fn, interval) {
        if (tmPollTimers[name]) clearInterval(tmPollTimers[name]);
        tmPollTimers[name] = setInterval(fn, interval || POLL_INTERVAL);
        fn();
    }

    function stopPoll(name) {
        if (tmPollTimers[name]) {
            clearInterval(tmPollTimers[name]);
            tmPollTimers[name] = null;
        }
    }

    // TM Sport switcher
    var tmSportBtns = document.querySelectorAll(".tm-sport-btn");
    tmSportBtns.forEach(function (btn) {
        btn.addEventListener("click", function () {
            var newSport = btn.getAttribute("data-tm-sport");
            if (newSport === tmSport) return;
            tmSport = newSport;
            tmSportBtns.forEach(function (b) { b.classList.remove("active"); });
            btn.classList.add("active");
            // Clear progress/results in all panels
            document.getElementById("tm-scan-results").innerHTML = "";
            document.getElementById("tm-backtest-progress").innerHTML = "";
            document.getElementById("tm-backtest-results").innerHTML = "";
            document.getElementById("tm-rules-progress").innerHTML = "";
            document.getElementById("tm-rules-results").innerHTML = "";
            document.getElementById("tm-collect-progress").innerHTML = "";
            document.getElementById("tm-collect-status").innerHTML = "";
            document.getElementById("tm-metrics-content").innerHTML = "";
            document.getElementById("tm-calibration-results").innerHTML = "";
            // Stop any active poll timers
            clearAllPolls();
            // Re-enable buttons
            document.getElementById("tm-collect-btn").disabled = false;
            document.getElementById("tm-collect-btn").textContent = "Start Collection";
            document.getElementById("tm-backtest-btn").disabled = false;
            document.getElementById("tm-backtest-btn").textContent = "Run Backtest";
            document.getElementById("tm-rules-btn").disabled = false;
            document.getElementById("tm-rules-btn").textContent = "Run Rules Replay";
            // Reload data for active tab
            var activeTab = document.querySelector(".tm-tab.active");
            var target = activeTab ? activeTab.getAttribute("data-tm-tab") : "scan";
            if (target === "metrics") tmLoadMetrics();
            if (target === "rules") tmLoadRulesMetrics();
            if (target === "collect") tmPollCollect();
            if (target === "calibration") tmLoadCalibration();
        });
    });

    // TM Legend toggle
    var tmLegendBtn = document.getElementById("tm-legend-btn");
    if (tmLegendBtn) {
        tmLegendBtn.addEventListener("click", function () {
            document.getElementById("tm-legend-panel").classList.toggle("hidden");
        });
    }

    // Show Test Model section
    testmodelBtn.addEventListener("click", function () {
        if (!_isAdmin) return;
        welcomeHero.classList.add("hidden");
        scanResults.classList.add("hidden");
        scanResultsVisible = false;
        results.classList.add("hidden");
        errorBanner.classList.add("hidden");
        dashboardSection.classList.add("hidden");
        dashboardVisible = false;
        lottoResults.classList.add("hidden");
        lottoResults.innerHTML = "";
        playerSearchSection.classList.add("hidden");
        testmodelSection.classList.remove("hidden");

        // Load metrics on first open
        tmLoadMetrics();

        if (window.innerWidth <= 768) closeSidebar();
    });

    // Hide testmodel section on home/sport change
    document.getElementById("nav-home-btn").addEventListener("click", function () {
        testmodelSection.classList.add("hidden");
    });

    // Tab switching
    document.querySelectorAll(".tm-tab").forEach(function (tab) {
        tab.addEventListener("click", function () {
            document.querySelectorAll(".tm-tab").forEach(function (t) { t.classList.remove("active"); });
            tab.classList.add("active");
            var target = tab.getAttribute("data-tm-tab");
            document.querySelectorAll(".tm-panel").forEach(function (p) { p.classList.add("hidden"); });
            document.getElementById("tm-panel-" + target).classList.remove("hidden");

            if (target === "metrics") tmLoadMetrics();
            if (target === "rules") tmLoadRulesMetrics();
            if (target === "calibration") tmLoadCalibration();
        });
    });

    // ── Collection ──
    document.getElementById("tm-collect-btn").addEventListener("click", function () {
        var btn = document.getElementById("tm-collect-btn");
        btn.disabled = true;
        btn.textContent = "Collecting...";

        authFetch("/api/tm/collect", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ sport: tmSport })
        })
        .then(function (res) { return res.json(); })
        .then(function (data) {
            if (data.success) {
                tmStartCollectPoll();
            } else {
                btn.disabled = false;
                btn.textContent = "Start Collection";
                document.getElementById("tm-collect-status").innerHTML = '<div class="tm-progress-text" style="color:var(--accent-red)">' + (data.error || 'Collection failed') + '</div>';
            }
        })
        .catch(function () {
            btn.disabled = false;
            btn.textContent = "Start Collection";
            document.getElementById("tm-collect-status").innerHTML = '<div class="tm-progress-text" style="color:var(--accent-red)">Connection error</div>';
        });
    });

    function tmStartCollectPoll() {
        startPoll("collect", tmPollCollect);
    }

    function tmPollCollect() {
        authFetch("/api/tm/collect/status?sport=" + tmSport)
            .then(function (res) { return res.json(); })
            .then(function (data) {
                if (!data.success) return;
                var prog = data.progress || {};
                var el = document.getElementById("tm-collect-progress");
                var status = document.getElementById("tm-collect-status");

                if (prog.status === "running") {
                    var pct = prog.total_dates > 0 ? Math.round(prog.done_dates / prog.total_dates * 100) : 0;
                    el.innerHTML = '<div class="tm-progress-bar-container"><div class="tm-progress-bar" style="width:' + pct + '%"></div></div>';
                    status.innerHTML = '<div class="tm-progress-text">Collecting ' + tmSport.toUpperCase() + ': ' + prog.done_dates + '/' + prog.total_dates + ' dates (' + (prog.games_collected || 0) + ' games) — ' + (prog.current_date || '') + '</div>';
                } else if (prog.status === "complete") {
                    el.innerHTML = '';
                    status.innerHTML = '<div class="tm-progress-text" style="color:var(--accent-green)">Collection complete! ' + (data.total_games || 0) + ' games collected.</div>';
                    document.getElementById("tm-collect-btn").disabled = false;
                    document.getElementById("tm-collect-btn").textContent = "Start Collection";
                    stopPoll("collect");
                } else {
                    // Not started or unknown — stop polling if timer is active
                    stopPoll("collect");
                    var dbProg = data.db_progress || {};
                    var doneCount = dbProg["DONE"] || 0;
                    var withSpreads = data.games_with_spreads || 0;
                    var totalGames = data.total_games || 0;
                    var txt = totalGames + ' games in DB';
                    if (withSpreads < totalGames) {
                        txt += ' (' + withSpreads + ' with spread data)';
                    }
                    txt += ', ' + doneCount + ' dates collected.';
                    status.innerHTML = '<div class="tm-progress-text">' + txt + '</div>';
                }
            })
            .catch(function () {});
    }

    // ── Compute Features ──
    document.getElementById("tm-features-btn").addEventListener("click", function () {
        var btn = document.getElementById("tm-features-btn");
        btn.disabled = true;
        btn.textContent = "Computing...";

        authFetch("/api/tm/features", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ sport: tmSport })
        })
        .then(function (res) { return res.json(); })
        .then(function (data) {
            btn.disabled = false;
            btn.textContent = "Compute Features";
            var status = document.getElementById("tm-collect-status");
            if (data.success) {
                status.innerHTML = '<div class="tm-progress-text" style="color:var(--accent-green)">Features computed: ' + data.features_computed + ' games processed.</div>';
            } else {
                status.innerHTML = '<div class="tm-progress-text" style="color:var(--accent-red)">' + (data.error || 'Error computing features') + '</div>';
            }
        })
        .catch(function () {
            btn.disabled = false;
            btn.textContent = "Compute Features";
        });
    });

    // ── Backtest ──
    document.getElementById("tm-backtest-btn").addEventListener("click", function () {
        var btn = document.getElementById("tm-backtest-btn");
        btn.disabled = true;
        btn.textContent = "Running Backtest...";
        document.getElementById("tm-backtest-results").innerHTML = "";

        authFetch("/api/tm/backtest", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ sport: tmSport })
        })
        .then(function (res) { return res.json(); })
        .then(function (data) {
            if (data.success) {
                tmStartBacktestPoll();
            } else {
                btn.disabled = false;
                btn.textContent = "Run Backtest";
                document.getElementById("tm-backtest-results").innerHTML = '<div class="tm-progress-text" style="color:var(--accent-red)">' + (data.error || 'Backtest failed') + '</div>';
            }
        })
        .catch(function () {
            btn.disabled = false;
            btn.textContent = "Run Backtest";
            document.getElementById("tm-backtest-results").innerHTML = '<div class="tm-progress-text" style="color:var(--accent-red)">Connection error</div>';
        });
    });

    function tmStartBacktestPoll() {
        startPoll("backtest", tmPollBacktest);
    }

    function tmPollBacktest() {
        authFetch("/api/tm/backtest/status?sport=" + tmSport)
            .then(function (res) { return res.json(); })
            .then(function (data) {
                if (!data.success) return;
                var prog = data.progress || {};
                var el = document.getElementById("tm-backtest-progress");
                var resEl = document.getElementById("tm-backtest-results");

                if (prog.status === "running") {
                    var pct = prog.total_games > 0 ? Math.round(prog.processed / prog.total_games * 100) : 0;
                    el.innerHTML = '<div class="tm-progress-bar-container"><div class="tm-progress-bar" style="width:' + pct + '%"></div></div>' +
                        '<div class="tm-progress-text">Backtesting: ' + prog.processed + '/' + prog.total_games + ' games — ' + (prog.current_date || '') + '</div>';
                } else if (prog.status === "complete") {
                    el.innerHTML = '';
                    document.getElementById("tm-backtest-btn").disabled = false;
                    document.getElementById("tm-backtest-btn").textContent = "Run Backtest";
                    stopPoll("backtest");

                    if (prog.metrics) {
                        resEl.innerHTML = tmRenderMetrics(prog.metrics);
                    }
                    tmLoadMetrics();
                } else if (prog.status === "error") {
                    el.innerHTML = '<div class="tm-progress-text" style="color:var(--accent-red)">' + (prog.message || 'Backtest error') + '</div>';
                    document.getElementById("tm-backtest-btn").disabled = false;
                    document.getElementById("tm-backtest-btn").textContent = "Run Backtest";
                    stopPoll("backtest");
                }
            })
            .catch(function () {});
    }

    // ── Rules Replay ──
    document.getElementById("tm-rules-btn").addEventListener("click", function () {
        var btn = document.getElementById("tm-rules-btn");
        btn.disabled = true;
        btn.textContent = "Running Replay...";
        document.getElementById("tm-rules-results").innerHTML = "";

        authFetch("/api/tm/rules-backtest", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ sport: tmSport })
        })
        .then(function (res) { return res.json(); })
        .then(function (data) {
            if (data.success) {
                tmStartRulesPoll();
            } else {
                btn.disabled = false;
                btn.textContent = "Run Rules Replay";
                document.getElementById("tm-rules-results").innerHTML = '<div class="tm-progress-text" style="color:var(--accent-red)">' + (data.error || 'Rules replay failed') + '</div>';
            }
        })
        .catch(function () {
            btn.disabled = false;
            btn.textContent = "Run Rules Replay";
            document.getElementById("tm-rules-results").innerHTML = '<div class="tm-progress-text" style="color:var(--accent-red)">Connection error</div>';
        });
    });

    function tmStartRulesPoll() {
        startPoll("rules", tmPollRules);
    }

    function tmPollRules() {
        authFetch("/api/tm/rules-backtest/status?sport=" + tmSport)
            .then(function (res) { return res.json(); })
            .then(function (data) {
                if (!data.success) return;
                var prog = data.progress || {};
                var el = document.getElementById("tm-rules-progress");
                var resEl = document.getElementById("tm-rules-results");

                if (prog.status === "running") {
                    var pct = prog.total_games > 0 ? Math.round(prog.processed / prog.total_games * 100) : 0;
                    el.innerHTML = '<div class="tm-progress-bar-container"><div class="tm-progress-bar" style="width:' + pct + '%"></div></div>' +
                        '<div class="tm-progress-text">Rules Replay: ' + prog.processed + '/' + prog.total_games + ' games — ' + (prog.current_date || '') + '</div>';
                } else if (prog.status === "complete") {
                    el.innerHTML = '';
                    document.getElementById("tm-rules-btn").disabled = false;
                    document.getElementById("tm-rules-btn").textContent = "Run Rules Replay";
                    stopPoll("rules");

                    if (prog.metrics) {
                        resEl.innerHTML = tmRenderRulesMetrics(prog.metrics);
                    }
                } else if (prog.status === "error") {
                    el.innerHTML = '<div class="tm-progress-text" style="color:var(--accent-red)">' + (prog.message || 'Rules replay error') + '</div>';
                    document.getElementById("tm-rules-btn").disabled = false;
                    document.getElementById("tm-rules-btn").textContent = "Run Rules Replay";
                    stopPoll("rules");
                }
            })
            .catch(function () {});
    }

    function tmLoadRulesMetrics() {
        var resEl = document.getElementById("tm-rules-results");
        authFetch("/api/tm/rules-backtest/metrics?sport=" + tmSport)
            .then(function (res) { return res.json(); })
            .then(function (data) {
                if (!data.success) return;
                if (!data.rules_metrics && !data.ml_metrics) {
                    resEl.innerHTML = '<div class="tm-progress-text">No rules replay results yet. Collect data first, then run a rules replay.</div>';
                    return;
                }
                var html = '';
                if (data.rules_metrics && data.ml_metrics) {
                    html += tmRenderComparison(data.rules_metrics, data.ml_metrics);
                }
                if (data.rules_metrics) {
                    var mp = data.rules_metrics.model_params || {};
                    html += tmRenderRulesMetrics(data.rules_metrics.feature_importances ? {
                        accuracy: data.rules_metrics.accuracy,
                        roi: data.rules_metrics.roi,
                        clv_avg: data.rules_metrics.clv_avg,
                        total_predictions: data.rules_metrics.total_predictions,
                        qualified_bets: data.rules_metrics.qualified_bets,
                        factor_breakdown: data.rules_metrics.feature_importances,
                        threshold_analysis: data.rules_metrics.threshold_analysis,
                        slot_breakdown: {},
                        rec_breakdown: {},
                        factor_health: mp.factor_health || null,
                    } : {});
                }
                resEl.innerHTML = html;
            })
            .catch(function () {});
    }

    function tmRenderComparison(rules, ml) {
        var html = '<div class="tm-feat-section"><h3 class="tm-feat-title">Rules Engine vs ML Model</h3>';
        html += '<table class="tm-table"><thead><tr><th>Metric</th><th>Rules Engine</th><th>ML Model</th></tr></thead><tbody>';
        html += '<tr><td>Accuracy</td><td>' + (rules.accuracy || 0) + '%</td><td>' + (ml.accuracy || 0) + '%</td></tr>';
        html += '<tr><td>ROI</td><td>' + (rules.roi > 0 ? '+' : '') + (rules.roi || 0) + '%</td><td>' + (ml.roi > 0 ? '+' : '') + (ml.roi || 0) + '%</td></tr>';
        html += '<tr><td>CLV</td><td>' + (rules.clv_avg > 0 ? '+' : '') + (rules.clv_avg || 0) + '%</td><td>' + (ml.clv_avg > 0 ? '+' : '') + (ml.clv_avg || 0) + '%</td></tr>';
        html += '<tr><td>Total Predictions</td><td>' + (rules.total_predictions || 0) + '</td><td>' + (ml.total_predictions || 0) + '</td></tr>';
        html += '<tr><td>Qualified Bets</td><td>' + (rules.qualified_bets || 0) + '</td><td>' + (ml.qualified_bets || 0) + '</td></tr>';
        html += '</tbody></table></div>';
        return html;
    }

    function tmRenderRulesMetrics(m) {
        if (!m || !m.accuracy) return '';
        var html = '';

        // Stat cards
        var accClass = m.accuracy >= 55 ? "stat-green" : m.accuracy >= 50 ? "stat-yellow" : "stat-red";
        var roiClass = m.roi > 0 ? "stat-green" : m.roi >= -3 ? "stat-yellow" : "stat-red";

        html += '<div class="tm-stat-cards">';
        html += '<div class="tm-stat-card"><div class="tm-stat-label">Accuracy</div><div class="tm-stat-value ' + accClass + '">' + (m.accuracy || 0) + '%</div></div>';
        html += '<div class="tm-stat-card"><div class="tm-stat-label">ROI</div><div class="tm-stat-value ' + roiClass + '">' + (m.roi > 0 ? '+' : '') + (m.roi || 0) + '%</div></div>';
        var clvClass = m.clv_avg > 0 ? "stat-green" : m.clv_avg < 0 ? "stat-red" : "";
        html += '<div class="tm-stat-card"><div class="tm-stat-label">CLV (avg pts)</div><div class="tm-stat-value ' + clvClass + '">' + (m.clv_avg > 0 ? '+' : '') + (m.clv_avg || 0) + '</div></div>';
        if (m.clv_hit_rate !== undefined) {
            var clvHrClass = m.clv_hit_rate >= 55 ? "stat-green" : m.clv_hit_rate < 45 ? "stat-red" : "stat-yellow";
            html += '<div class="tm-stat-card"><div class="tm-stat-label">CLV Beat %</div><div class="tm-stat-value ' + clvHrClass + '">' + m.clv_hit_rate + '%</div></div>';
        }
        html += '<div class="tm-stat-card"><div class="tm-stat-label">Predictions</div><div class="tm-stat-value">' + (m.total_predictions || 0) + '</div></div>';
        html += '<div class="tm-stat-card"><div class="tm-stat-label">Bets (10+)</div><div class="tm-stat-value">' + (m.qualified_bets || 0) + '</div></div>';
        html += '</div>';

        // CLV by tier
        if (m.clv_by_tier && m.clv_by_tier.length > 0) {
            html += '<div class="tm-feat-section">';
            html += '<h3 class="tm-feat-title">CLV by Tier</h3>';
            html += '<table class="tm-feat-table"><thead><tr><th>Tier</th><th>Picks</th><th>Avg CLV</th><th>Beat Close</th></tr></thead><tbody>';
            m.clv_by_tier.forEach(function (t) {
                var tc = t.avg_clv > 0 ? 'stat-green' : t.avg_clv < 0 ? 'stat-red' : '';
                var hc = t.clv_hit_rate >= 55 ? 'stat-green' : t.clv_hit_rate < 45 ? 'stat-red' : 'stat-yellow';
                html += '<tr><td>' + t.tier + '</td><td>' + t.count + '</td>';
                html += '<td class="' + tc + '">' + (t.avg_clv > 0 ? '+' : '') + t.avg_clv + '</td>';
                html += '<td class="' + hc + '">' + t.clv_hit_rate + '%</td></tr>';
            });
            html += '</tbody></table></div>';
        }

        // Threshold analysis
        if (m.threshold_analysis && Object.keys(m.threshold_analysis).length > 0) {
            html += '<div class="tm-feat-section">';
            html += '<h3 class="tm-feat-title">Score Threshold Analysis</h3>';
            html += '<table class="tm-table"><thead><tr><th>Score &ge;</th><th>Bets</th><th>Accuracy</th><th>ROI</th></tr></thead><tbody>';
            Object.keys(m.threshold_analysis).sort(function (a, b) { return Number(a) - Number(b); }).forEach(function (key) {
                var t = m.threshold_analysis[key];
                var trClass = t.roi > 0 ? 'style="color:var(--accent-green)"' : '';
                html += '<tr ' + trClass + '><td>' + t.threshold + '</td><td>' + t.bet_count + '</td><td>' + t.accuracy + '%</td><td>' + (t.roi > 0 ? '+' : '') + t.roi + '%</td></tr>';
            });
            html += '</tbody></table></div>';
        }

        // Factor breakdown
        if (m.factor_breakdown && Object.keys(m.factor_breakdown).length > 0) {
            html += '<div class="tm-feat-section">';
            html += '<h3 class="tm-feat-title">Factor Performance</h3>';
            html += '<table class="tm-table"><thead><tr><th>Factor</th><th>Fired</th><th>Acc (Fired)</th><th>Acc (Not)</th><th>Lift</th></tr></thead><tbody>';
            var factors = Object.keys(m.factor_breakdown).sort(function (a, b) {
                return (m.factor_breakdown[b].lift || 0) - (m.factor_breakdown[a].lift || 0);
            });
            factors.forEach(function (key) {
                var f = m.factor_breakdown[key];
                if (f.fired === 0) return;
                var liftClass = f.lift > 2 ? 'style="color:var(--accent-green)"' : f.lift < -2 ? 'style="color:var(--accent-red)"' : '';
                html += '<tr ' + liftClass + '><td>' + key.replace(/_/g, ' ') + '</td><td>' + f.fired + '</td><td>' + f.accuracy_when_fired + '%</td><td>' + f.accuracy_when_not_fired + '%</td><td>' + (f.lift > 0 ? '+' : '') + f.lift + '%</td></tr>';
            });
            html += '</tbody></table></div>';
        }

        // Slot breakdown
        if (m.slot_breakdown && Object.keys(m.slot_breakdown).length > 0) {
            html += '<div class="tm-feat-section">';
            html += '<h3 class="tm-feat-title">By Slot Type</h3>';
            html += '<table class="tm-table"><thead><tr><th>Slot</th><th>Games</th><th>Correct</th><th>Accuracy</th></tr></thead><tbody>';
            Object.keys(m.slot_breakdown).forEach(function (key) {
                var s = m.slot_breakdown[key];
                html += '<tr><td>' + key + '</td><td>' + s.total + '</td><td>' + s.correct + '</td><td>' + s.accuracy + '%</td></tr>';
            });
            html += '</tbody></table></div>';
        }

        // Recommendation breakdown
        if (m.rec_breakdown && Object.keys(m.rec_breakdown).length > 0) {
            html += '<div class="tm-feat-section">';
            html += '<h3 class="tm-feat-title">By Recommendation</h3>';
            html += '<table class="tm-table"><thead><tr><th>Rec</th><th>Games</th><th>Correct</th><th>Accuracy</th></tr></thead><tbody>';
            ["STRONG PLAY", "CONFIDENT", "LEAN", "MONITOR"].forEach(function (key) {
                var r = m.rec_breakdown[key];
                if (!r) return;
                var accClass = r.accuracy >= 55 ? 'style="color:var(--accent-green)"' : r.accuracy < 50 ? 'style="color:var(--accent-red)"' : '';
                html += '<tr ' + accClass + '><td>' + key + '</td><td>' + r.total + '</td><td>' + r.correct + '</td><td>' + r.accuracy + '%</td></tr>';
            });
            html += '</tbody></table></div>';
        }

        // Factor Health Report
        if (m.factor_health) {
            html += tmRenderFactorHealth(m.factor_health);
        }

        return html;
    }

    function tmRenderFactorHealth(fh) {
        if (!fh) return '';
        var html = '<div class="tm-feat-section">';
        html += '<h3 class="tm-feat-title" style="border-bottom:2px solid var(--accent-red);padding-bottom:6px">Factor Health Report</h3>';

        var ABBREV = {
            slot_public: "Slot (Pub)", line_movement: "Line Mvmt", line_toward_dog: "Line→Dog",
            line_toward_fav: "Line→Fav", rank_scam: "Rank Scam", spread_discrepancy: "Sprd Disc",
            home_away_split: "H/A Split", b2b_bonus: "B2B+", b2b_penalty: "B2B-",
            h2h_revenge: "H2H Rev", h2h_dominance: "H2H Dom", vegas_trap: "Trap",
            trend_discrepancy: "Trend Disc", ou_discrepancy: "O/U Disc",
            ats_bonus: "ATS+", ats_penalty: "ATS-", spread_penalty: "Sprd Pen",
            spread_sweet_spot: "Sprd Sweet", day_penalty: "Day Pen",
        };
        var BK_ABBREV = {
            slot: "Slot", line_movement: "Line Mvmt", line_direction: "Line Dir",
            rank_scam: "Rank Scam", spread_discrepancy: "Sprd Disc",
            home_away_split: "H/A Split", b2b: "B2B", head_to_head: "H2H",
            vegas_trap: "Trap", trend_discrepancy: "Trend Disc", overunder: "O/U Disc",
            ats_record: "ATS", spread_penalty: "Spread Adj", day_penalty: "Day Pen",
            trell: "Trell", public_betting: "Public $", feedback: "Feedback", weather: "Weather",
        };

        // Factor comparison table: standalone lift, marginal lift, VIF
        var names = fh.factor_names || [];
        if (names.length > 0 && fh.standalone_lift && fh.vif_scores) {
            html += '<h4 style="color:var(--text-secondary);margin:12px 0 6px">Factor Comparison</h4>';
            html += '<table class="tm-table"><thead><tr><th>Factor</th><th>Fired</th><th>Standalone Lift</th><th>VIF</th><th>Status</th></tr></thead><tbody>';
            // Sort by standalone lift descending
            var sorted = names.slice().sort(function(a,b) {
                return (fh.standalone_lift[b]||{}).lift - (fh.standalone_lift[a]||{}).lift;
            });
            sorted.forEach(function(name) {
                var sl = fh.standalone_lift[name] || {};
                var vif = fh.vif_scores[name];
                var liftVal = sl.lift || 0;
                var liftClass = liftVal > 3 ? 'color:var(--accent-green)' : liftVal < -3 ? 'color:var(--accent-red)' : '';
                var vifClass = '';
                var vifStr = vif != null ? vif.toFixed(1) : '-';
                if (vif > 10) vifClass = 'color:var(--accent-red)';
                else if (vif > 5) vifClass = 'color:var(--accent-yellow)';
                // Status
                var status = '';
                if (vif > 5) status = '<span style="color:var(--accent-red)">Multicoll.</span>';
                else if (liftVal < -3) status = '<span style="color:var(--accent-red)">Harmful</span>';
                else if (liftVal > 5) status = '<span style="color:var(--accent-green)">Strong</span>';
                else status = '<span style="color:var(--text-secondary)">OK</span>';

                html += '<tr><td>' + (ABBREV[name] || name) + '</td>';
                html += '<td>' + (sl.fired || 0) + '</td>';
                html += '<td style="' + liftClass + '">' + (liftVal > 0 ? '+' : '') + liftVal + '%</td>';
                html += '<td style="' + vifClass + '">' + vifStr + '</td>';
                html += '<td>' + status + '</td></tr>';
            });
            html += '</tbody></table>';
        }

        // Marginal lift table (by breakdown key)
        if (fh.marginal_lift && Object.keys(fh.marginal_lift).length > 0) {
            html += '<h4 style="color:var(--text-secondary);margin:12px 0 6px">Marginal Lift (Leave-One-Out)</h4>';
            html += '<table class="tm-table"><thead><tr><th>Factor</th><th>Full Acc</th><th>Without</th><th>Marginal</th><th>Tipped In</th><th>Tipped Acc</th></tr></thead><tbody>';
            var mlKeys = Object.keys(fh.marginal_lift).sort(function(a,b) {
                return (fh.marginal_lift[b].marginal_lift||0) - (fh.marginal_lift[a].marginal_lift||0);
            });
            mlKeys.forEach(function(key) {
                var m = fh.marginal_lift[key];
                var ml = m.marginal_lift || 0;
                var mlClass = ml > 2 ? 'color:var(--accent-green)' : ml < -2 ? 'color:var(--accent-red)' : '';
                var tippedClass = m.tipped_accuracy < m.full_accuracy ? 'color:var(--accent-red)' : m.tipped_accuracy > m.full_accuracy ? 'color:var(--accent-green)' : '';
                html += '<tr><td>' + (BK_ABBREV[key] || key) + '</td>';
                html += '<td>' + m.full_accuracy + '%</td>';
                html += '<td>' + m.without_accuracy + '%</td>';
                html += '<td style="' + mlClass + '">' + (ml > 0 ? '+' : '') + ml + '%</td>';
                html += '<td>' + (m.games_tipped_in || 0) + '</td>';
                html += '<td style="' + tippedClass + '">' + m.tipped_accuracy + '%</td></tr>';
            });
            html += '</tbody></table>';
        }

        // Notable correlations
        if (fh.correlation_matrix && fh.correlation_matrix.matrix) {
            var cm = fh.correlation_matrix;
            var pairs = [];
            for (var i = 0; i < cm.factors.length; i++) {
                for (var j = i + 1; j < cm.factors.length; j++) {
                    var corr = cm.matrix[i][j];
                    if (Math.abs(corr) > 0.2) {
                        pairs.push({ a: cm.factors[i], b: cm.factors[j], corr: corr });
                    }
                }
            }
            if (pairs.length > 0) {
                pairs.sort(function(a,b) { return Math.abs(b.corr) - Math.abs(a.corr); });
                html += '<h4 style="color:var(--text-secondary);margin:12px 0 6px">Notable Correlations (|r| &gt; 0.2)</h4>';
                html += '<table class="tm-table"><thead><tr><th>Factor A</th><th>Factor B</th><th>Correlation</th></tr></thead><tbody>';
                pairs.slice(0, 15).forEach(function(p) {
                    var corrClass = Math.abs(p.corr) > 0.5 ? 'color:var(--accent-red)' : Math.abs(p.corr) > 0.3 ? 'color:var(--accent-yellow)' : '';
                    html += '<tr><td>' + (ABBREV[p.a] || p.a) + '</td>';
                    html += '<td>' + (ABBREV[p.b] || p.b) + '</td>';
                    html += '<td style="' + corrClass + '">' + (p.corr > 0 ? '+' : '') + p.corr.toFixed(3) + '</td></tr>';
                });
                html += '</tbody></table>';
            }
        }

        // Cluster analysis
        if (fh.clusters && fh.clusters.length > 0) {
            html += '<h4 style="color:var(--text-secondary);margin:12px 0 6px">Factor Clusters</h4>';
            fh.clusters.forEach(function(cl) {
                var label = cl.template_match || 'Cluster';
                var factorsStr = cl.factors.map(function(f) { return ABBREV[f] || f; }).join(', ');
                var corrClass = cl.avg_correlation > 0.5 ? 'var(--accent-red)' : cl.avg_correlation > 0.3 ? 'var(--accent-yellow)' : 'var(--text-secondary)';
                html += '<div class="fh-cluster-card">';
                html += '<div class="fh-cluster-header"><strong>' + label + '</strong> <span style="color:' + corrClass + '">(avg r=' + cl.avg_correlation.toFixed(2) + ')</span></div>';
                html += '<div class="fh-cluster-factors">' + factorsStr + '</div>';
                html += '<div class="fh-cluster-stats">';
                html += 'Cluster marginal lift: <span style="' + (cl.cluster_marginal_lift > 0 ? 'color:var(--accent-green)' : cl.cluster_marginal_lift < -2 ? 'color:var(--accent-red)' : '') + '">' + (cl.cluster_marginal_lift > 0 ? '+' : '') + cl.cluster_marginal_lift + '%</span>';
                html += ' &middot; Max combined weight: ' + cl.combined_max_weight;
                html += '</div></div>';
            });
        }

        // Recommendations
        if (fh.recommendations && fh.recommendations.length > 0) {
            html += '<h4 style="color:var(--text-secondary);margin:12px 0 6px">Recommendations</h4>';
            fh.recommendations.forEach(function(rec) {
                var sevColor = rec.severity === 'high' ? 'var(--accent-red)' : rec.severity === 'medium' ? 'var(--accent-yellow)' : 'var(--text-secondary)';
                var typeLabel = rec.type.replace(/_/g, ' ').toUpperCase();
                html += '<div class="fh-rec-item">';
                html += '<span class="fh-rec-badge" style="background:' + sevColor + '">' + typeLabel + '</span> ';
                html += '<span class="fh-rec-msg">' + rec.message + '</span>';
                html += '</div>';
            });
        }

        html += '</div>';
        return html;
    }

    // ── Calibration ──
    document.getElementById("tm-calibration-btn").addEventListener("click", function () {
        tmLoadCalibration();
    });

    function tmLoadCalibration() {
        var resEl = document.getElementById("tm-calibration-results");
        resEl.innerHTML = '<div class="tm-progress-text">Loading calibration data...</div>';
        authFetch("/api/tm/calibration?sport=" + tmSport)
            .then(function (res) { return res.json(); })
            .then(function (data) {
                if (!data.success) {
                    resEl.innerHTML = '<div class="tm-progress-text" style="color:var(--accent-red)">' + (data.error || 'Failed') + '</div>';
                    return;
                }
                if (!data.calibration) {
                    resEl.innerHTML = '<div class="tm-progress-text">No calibration data yet. Run a Rules Replay first to generate calibration analysis.</div>';
                    return;
                }
                resEl.innerHTML = tmRenderCalibration(data.calibration);
            })
            .catch(function () {
                resEl.innerHTML = '<div class="tm-progress-text" style="color:var(--accent-red)">Failed to load calibration data.</div>';
            });
    }

    function tmRenderCalibration(cal) {
        if (!cal) return '';
        var html = '';

        // Stat cards
        var eceClass = "stat-green";
        if (cal.ece > 10) eceClass = "stat-red";
        else if (cal.ece > 5) eceClass = "stat-yellow";

        var brierClass = cal.brier_score <= 0.2 ? "stat-green" : cal.brier_score <= 0.25 ? "stat-yellow" : "stat-red";

        html += '<div class="tm-stat-cards">';
        html += '<div class="tm-stat-card"><div class="tm-stat-label">Brier Score</div><div class="tm-stat-value ' + brierClass + '">' + (cal.brier_score != null ? cal.brier_score : 'N/A') + '</div></div>';
        html += '<div class="tm-stat-card"><div class="tm-stat-label">ECE</div><div class="tm-stat-value ' + eceClass + '">' + (cal.ece != null ? cal.ece + '%' : 'N/A') + '</div></div>';
        html += '<div class="tm-stat-card"><div class="tm-stat-label">Sample Size</div><div class="tm-stat-value">' + (cal.sample_size || 0) + '</div></div>';
        html += '<div class="tm-stat-card"><div class="tm-stat-label">Adjustment Needed</div><div class="tm-stat-value ' + (cal.adjustment_needed ? 'stat-red' : 'stat-green') + '">' + (cal.adjustment_needed ? 'YES' : 'NO') + '</div></div>';
        html += '</div>';

        // Calibration bins table
        if (cal.bins && cal.bins.length > 0) {
            html += '<div class="tm-feat-section"><h3 class="tm-feat-title">Calibration Bins</h3>';
            html += '<table class="tm-table"><thead><tr><th>Range</th><th>Count</th><th>Avg Predicted</th><th>Actual Rate</th><th>Gap</th></tr></thead><tbody>';
            cal.bins.forEach(function (b) {
                var gapClass = '';
                var absGap = Math.abs(b.gap);
                if (absGap > 10) gapClass = 'style="color:var(--accent-red)"';
                else if (absGap > 5) gapClass = 'style="color:var(--accent-yellow)"';
                else if (b.count > 0) gapClass = 'style="color:var(--accent-green)"';
                var gapStr = b.gap > 0 ? '+' + b.gap : b.gap;
                html += '<tr><td>' + b.range + '</td><td>' + b.count + '</td>';
                html += '<td>' + b.avg_predicted + '%</td>';
                html += '<td>' + b.actual_rate + '%</td>';
                html += '<td ' + gapClass + '>' + (b.count > 0 ? gapStr + '%' : '-') + '</td></tr>';
            });
            html += '</tbody></table></div>';
        }

        // Isotonic breakpoints table
        if (cal.isotonic_breakpoints && cal.isotonic_breakpoints.x) {
            var bp = cal.isotonic_breakpoints;
            html += '<div class="tm-feat-section"><h3 class="tm-feat-title">Isotonic Correction Curve</h3>';
            html += '<table class="tm-table"><thead><tr><th>Raw %</th><th>Calibrated %</th><th>Adjustment</th></tr></thead><tbody>';
            for (var i = 0; i < bp.x.length; i++) {
                var adj = (bp.y[i] - bp.x[i]).toFixed(2);
                var adjStr = adj > 0 ? '+' + adj : adj;
                var adjClass = '';
                if (Math.abs(adj) > 5) adjClass = 'style="color:var(--accent-yellow)"';
                if (Math.abs(adj) > 10) adjClass = 'style="color:var(--accent-red)"';
                html += '<tr><td>' + bp.x[i] + '%</td><td>' + bp.y[i] + '%</td><td ' + adjClass + '>' + adjStr + '%</td></tr>';
            }
            html += '</tbody></table></div>';
        }

        return html;
    }

    // ── Model Scan ──
    document.getElementById("tm-scan-btn").addEventListener("click", function () {
        var btn = document.getElementById("tm-scan-btn");
        var loadEl = document.getElementById("tm-scan-loading");
        btn.disabled = true;
        loadEl.classList.remove("hidden");
        document.getElementById("tm-scan-results").innerHTML = "";

        authFetch("/api/tm/scan", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ sport: tmSport })
        })
        .then(function (res) { return res.json(); })
        .then(function (data) {
            btn.disabled = false;
            loadEl.classList.add("hidden");
            if (data.success) {
                tmRenderScanResults(data.games || []);
            } else {
                document.getElementById("tm-scan-results").innerHTML =
                    '<div class="tm-progress-text" style="color:var(--accent-red)">' + (data.error || 'Scan failed') + '</div>';
            }
        })
        .catch(function () {
            btn.disabled = false;
            loadEl.classList.add("hidden");
        });
    });

    function tmRenderScanResults(games) {
        var el = document.getElementById("tm-scan-results");
        if (games.length === 0) {
            el.innerHTML = '<div class="scan-empty-state"><div class="scan-empty-headline">No games to scan.</div></div>';
            return;
        }

        var html = '<h3 class="scan-title">' + tmSport.toUpperCase() + ' Model Scan</h3>';
        html += '<div class="scan-grid">';

        games.forEach(function (g) {
            html += buildScanCard(g, tmSport);

            // Add model overlay
            var tm = g.tm_overlay || {};
            if (tm.available) {
                // Remove closing </div> of the scan card and append overlay
                html = html.slice(0, html.lastIndexOf('</div>'));
                html += tmBuildOverlay(g, tm);
                html += '</div>';
            }
        });

        html += '</div>';
        el.innerHTML = html;
    }

    function tmBuildOverlay(game, tm) {
        var html = '<div class="tm-model-overlay">';
        html += '<div class="tm-overlay-header">ML MODEL OVERLAY</div>';

        // Model probability
        var probPct = (tm.model_prob * 100).toFixed(1);
        var probClass = tm.model_prob >= 0.6 ? "tm-prob-high" : tm.model_prob >= 0.53 ? "tm-prob-mid" : "tm-prob-low";
        html += '<div class="tm-prob ' + probClass + '">Model: ' + probPct + '% home covers</div>';

        // Edge metrics
        var edgeClass = tm.model_edge > 0 ? "tm-edge-pos" : "tm-edge-neg";
        html += '<div class="tm-edge-row">';
        html += '<div class="tm-edge-item ' + edgeClass + '">Edge: <span>' + (tm.model_edge > 0 ? '+' : '') + (tm.model_edge * 100).toFixed(1) + '%</span></div>';
        html += '<div class="tm-edge-item ' + edgeClass + '">EV: <span>' + (tm.model_ev > 0 ? '+' : '') + (tm.model_ev * 100).toFixed(1) + 'c</span></div>';
        html += '<div class="tm-edge-item ' + edgeClass + '">ROI: <span>' + (tm.model_roi > 0 ? '+' : '') + tm.model_roi + '%</span></div>';
        html += '</div>';

        // Comparison: model vs rules
        var rulesPct = game.cover_pct || 0;
        html += '<div class="tm-comparison">';
        html += '<span class="tm-vs-label">Rules: ' + rulesPct + '%</span>';
        html += '<span class="tm-vs-label">vs</span>';
        html += '<span class="tm-vs-label">Model: ' + probPct + '%</span>';
        html += '</div>';

        // Cluster
        if (tm.cluster_id >= 0) {
            html += '<div class="tm-cluster-row">';
            html += '<span class="tm-cluster-badge">Cluster ' + tm.cluster_id + '</span>';
            html += '<span class="tm-alignment">Hit Rate: ' + tm.cluster_hit_rate + '% | Alignment: ' + tm.alignment_confidence + '%</span>';
            html += '</div>';
        }

        // Sentiment
        if (tm.sentiment && tm.sentiment.has_sentiment) {
            html += '<div class="tm-sentiment-row">';
            var hClass = tm.sentiment.home_sentiment > 0 ? "tm-sentiment-pos" : tm.sentiment.home_sentiment < 0 ? "tm-sentiment-neg" : "tm-sentiment-neutral";
            var aClass = tm.sentiment.away_sentiment > 0 ? "tm-sentiment-pos" : tm.sentiment.away_sentiment < 0 ? "tm-sentiment-neg" : "tm-sentiment-neutral";
            html += '<span class="' + hClass + '">Home: ' + tm.sentiment.home_sentiment.toFixed(2) + '</span>';
            html += '<span class="' + aClass + '">Away: ' + tm.sentiment.away_sentiment.toFixed(2) + '</span>';
            html += '</div>';
        }

        html += '</div>';
        return html;
    }

    // ── Metrics ──
    function tmLoadMetrics() {
        var loadEl = document.getElementById("tm-metrics-loading");
        var contentEl = document.getElementById("tm-metrics-content");
        loadEl.classList.remove("hidden");
        contentEl.innerHTML = "";

        authFetch("/api/tm/metrics?sport=" + tmSport)
            .then(function (res) { return res.json(); })
            .then(function (data) {
                loadEl.classList.add("hidden");
                if (!data.success) return;

                var html = '<div class="tm-progress-text">Games: ' + (data.total_games || 0) + ' | Features: ' + (data.total_features || 0) + '</div>';

                if (data.metrics) {
                    html += tmRenderMetrics(data.metrics);
                } else {
                    html += '<div class="tm-progress-text">No backtest results yet. Collect data, compute features, then run a backtest.</div>';
                }

                contentEl.innerHTML = html;
            })
            .catch(function () {
                loadEl.classList.add("hidden");
            });
    }

    function tmRenderMetrics(m) {
        if (!m) return '';

        var html = '';

        // Stat cards
        var accClass = m.accuracy >= 55 ? "stat-green" : m.accuracy >= 50 ? "stat-yellow" : "stat-red";
        var roiClass = m.roi > 0 ? "stat-green" : m.roi >= -3 ? "stat-yellow" : "stat-red";
        var clvClass = m.clv_avg > 0 ? "stat-green" : "stat-red";

        html += '<div class="tm-stat-cards">';
        html += '<div class="tm-stat-card"><div class="tm-stat-label">Accuracy</div><div class="tm-stat-value ' + accClass + '">' + (m.accuracy || 0) + '%</div></div>';
        html += '<div class="tm-stat-card"><div class="tm-stat-label">ROI</div><div class="tm-stat-value ' + roiClass + '">' + (m.roi > 0 ? '+' : '') + (m.roi || 0) + '%</div></div>';
        html += '<div class="tm-stat-card"><div class="tm-stat-label">CLV</div><div class="tm-stat-value ' + clvClass + '">' + (m.clv_avg > 0 ? '+' : '') + (m.clv_avg || 0) + '%</div></div>';
        html += '<div class="tm-stat-card"><div class="tm-stat-label">ECE</div><div class="tm-stat-value">' + (m.calibration_error || 0) + '</div></div>';
        html += '<div class="tm-stat-card"><div class="tm-stat-label">Total</div><div class="tm-stat-value">' + (m.total_predictions || 0) + '</div></div>';
        html += '<div class="tm-stat-card"><div class="tm-stat-label">Bets</div><div class="tm-stat-value">' + (m.qualified_bets || 0) + '</div></div>';
        html += '</div>';

        // Threshold analysis table
        if (m.threshold_analysis && Object.keys(m.threshold_analysis).length > 0) {
            html += '<div class="tm-feat-section">';
            html += '<h3 class="tm-feat-title">Threshold Analysis</h3>';
            html += '<table class="tm-table"><thead><tr><th>Threshold</th><th>Bets</th><th>Accuracy</th><th>ROI</th></tr></thead><tbody>';
            Object.keys(m.threshold_analysis).sort().forEach(function (key) {
                var t = m.threshold_analysis[key];
                var trClass = t.roi > 0 ? 'style="color:var(--accent-green)"' : '';
                html += '<tr ' + trClass + '><td>' + (t.threshold * 100).toFixed(0) + '%</td><td>' + t.bet_count + '</td><td>' + t.accuracy + '%</td><td>' + (t.roi > 0 ? '+' : '') + t.roi + '%</td></tr>';
            });
            html += '</tbody></table></div>';
        }

        // Confidence buckets table
        if (m.confidence_buckets && Object.keys(m.confidence_buckets).length > 0) {
            html += '<div class="tm-feat-section">';
            html += '<h3 class="tm-feat-title">Confidence Buckets</h3>';
            html += '<table class="tm-table"><thead><tr><th>Range</th><th>Count</th><th>Hit Rate</th></tr></thead><tbody>';
            Object.keys(m.confidence_buckets).forEach(function (key) {
                var b = m.confidence_buckets[key];
                html += '<tr><td>' + key + '</td><td>' + b.count + '</td><td>' + b.hit_rate + '%</td></tr>';
            });
            html += '</tbody></table></div>';
        }

        // Feature importances
        if (m.feature_importances) {
            var feats = m.feature_importances;
            var keys = Object.keys(feats).sort(function (a, b) { return feats[b] - feats[a]; }).slice(0, 15);
            if (keys.length > 0) {
                var maxVal = feats[keys[0]] || 0.01;
                html += '<div class="tm-feat-section">';
                html += '<h3 class="tm-feat-title">Top Feature Importances</h3>';
                keys.forEach(function (k) {
                    var pct = Math.round(feats[k] / maxVal * 100);
                    html += '<div class="tm-feat-row">';
                    html += '<span class="tm-feat-name">' + k + '</span>';
                    html += '<div class="tm-feat-bar-container"><div class="tm-feat-bar" style="width:' + pct + '%"></div></div>';
                    html += '<span class="tm-feat-value">' + (feats[k] * 100).toFixed(1) + '%</span>';
                    html += '</div>';
                });
                html += '</div>';
            }
        }

        return html;
    }

    // Start auth flow — fetchGames() and tmPollCollect() are called from showApp() after auth
    initAuth();
});
