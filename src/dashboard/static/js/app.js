/* Imposture Dashboard */

(function () {
    "use strict";

    var RECONNECT_DELAY_MS = 5000;

    var ws = null;
    var focusStartTime = null;
    var focusTimerInterval = null;

    var EMOTION_MAP = {
        happy:     "\uD83D\uDE0A",
        neutral:   "\uD83D\uDE10",
        concerned: "\uD83D\uDE1F",
        sad:       "\uD83D\uDE22",
        angry:     "\uD83D\uDE20",
        sleeping:  "\uD83D\uDE34",
        excited:   "\uD83E\uDD29"
    };

    /* Wamm avatar backgrounds — warm palette */
    var WAMM_BACKGROUNDS = {
        happy:     "#FFF2E6",
        neutral:   "#FFF7ED",
        concerned: "#FEF3C7",
        sad:       "#EFF6FF",
        angry:     "#FEF2F2",
        sleeping:  "#F5F3FF",
        excited:   "#ECFDF5"
    };

    /* ---- WebSocket ---- */

    function connectWS() {
        var protocol = location.protocol === "https:" ? "wss:" : "ws:";
        var url = protocol + "//" + location.host + "/ws";

        ws = new WebSocket(url);

        ws.onopen = function () {
            var dot = document.getElementById("ws-status");
            if (dot) {
                dot.classList.add("connected");
                dot.title = "Connected";
            }
        };

        ws.onmessage = function (event) {
            try {
                var state = JSON.parse(event.data);
                updateState(state);
            } catch (_) {}
        };

        ws.onclose = function () {
            var dot = document.getElementById("ws-status");
            if (dot) {
                dot.classList.remove("connected");
                dot.title = "Disconnected";
            }
            setTimeout(connectWS, RECONNECT_DELAY_MS);
        };

        ws.onerror = function () {
            if (ws) ws.close();
        };
    }

    /* ---- State ---- */

    function updateState(state) {
        var emotion = state.emotion || "neutral";
        var emoji = EMOTION_MAP[emotion] || EMOTION_MAP.neutral;

        setText("emotion-emoji", emoji);
        setText("emotion-label", capitalize(emotion));

        /* Wamm avatar background */
        var avatarBg = WAMM_BACKGROUNDS[emotion] || WAMM_BACKGROUNDS.neutral;
        var avatar = document.getElementById("wam-avatar");
        if (avatar) avatar.style.background = avatarBg;

        /* XP */
        var xp = state.xp || 0;
        setText("xp-text", xp + " XP");

        /* Posture */
        var postureDot = document.getElementById("posture-dot");
        if (postureDot) {
            postureDot.className = "status-light";
            if (emotion === "sad" || emotion === "concerned" || emotion === "angry") {
                postureDot.classList.add("bad");
            } else {
                postureDot.classList.add("good");
            }
        }
        var postureText = (emotion === "angry") ? "Phone Detected" :
            (emotion === "sad" || emotion === "concerned") ? "Posture: Poor" : "Posture: Good";
        setText("posture-label", postureText);

        /* Focus */
        var focusActive = !!state.focus_active;
        var timerEl     = document.getElementById("focus-timer");
        var startBtn    = document.getElementById("btn-focus-start");
        var stopBtn     = document.getElementById("btn-focus-stop");
        if (timerEl) timerEl.style.display = focusActive ? "flex" : "none";
        if (startBtn) startBtn.style.display = focusActive ? "none" : "inline-block";
        if (stopBtn)  stopBtn.style.display  = focusActive ? "inline-block" : "none";

        if (focusActive) {
            var elapsed = state.focus_elapsed || 0;
            setFocusTimer(elapsed);
            if (!focusTimerInterval) {
                startLocalTimer(elapsed);
            } else {
                focusStartTime = Date.now() - (elapsed * 1000);
            }
        } else {
            stopLocalTimer();
        }

        /* Stats */
        var violations = state.violations_today || {};
        setText("stat-posture", violations.posture_count || 0);
        setText("stat-phone",   violations.phone_count || 0);

        if (state.focus_active && state.focus_start_time) {
            var elapsedSec = Math.floor(Date.now() / 1000 - state.focus_start_time);
            setText("stat-focus", Math.floor(elapsedSec / 60));
        }

        /* CV Metrics */
        var cv = state.cv;
        if (cv) {
            var score = cv.posture_score;
            var scoreCircle = document.getElementById("score-circle");
            if (score !== null && score !== undefined) {
                setText("cv-score", score);
                setText("cv-score-label", cv.posture_label || "Unknown");
                if (scoreCircle) {
                    scoreCircle.className = "metric-score-circle";
                    if (score >= 70) scoreCircle.classList.add("good");
                    else if (score >= 50) scoreCircle.classList.add("fair");
                    else scoreCircle.classList.add("poor");
                }
            } else {
                setText("cv-score", "--");
                setText("cv-score-label", "Waiting...");
                if (scoreCircle) scoreCircle.className = "metric-score-circle";
            }

            setText("cv-streak", "Streak: " + (cv.posture_streak_secs || 0) + "s");
            setText("cv-strikes", "Strikes: " + (cv.posture_strike_count || 0));

            var m = cv.metrics || {};
            updateMetricBar("bar-spine", "cv-spine", m.spine_angle_deg, 40, "\u00B0");
            updateMetricBar("bar-neck", "cv-neck", m.neck_angle_deg, 40, "\u00B0");
            updateMetricBar("bar-ear", "cv-ear", m.ear_forward_norm, 80, "");
            updateMetricBar("bar-shoulder", "cv-shoulder", m.shoulder_diff_norm, 30, "");

            var phoneDot = document.getElementById("phone-dot");
            if (phoneDot) {
                phoneDot.className = "metric-phone-dot" + (cv.phone_visible ? " detected" : "");
            }
            setText("cv-phone-label", cv.phone_visible ? "Phone: DETECTED" : "Phone: Not detected");
            setText("cv-phone-time", cv.phone_seconds > 0 ? cv.phone_seconds + "s" : "");
        }

        /* Calibration */
        var calib = state.calibration;
        if (calib) {
            var calibBtn    = document.getElementById("btn-calibrate");
            var calibStatus = document.getElementById("calibration-status");
            var calibText   = document.getElementById("calibration-text");

            if (calib.active) {
                if (calibBtn) calibBtn.disabled = true;
                if (calibStatus) calibStatus.style.display = "block";
                if (calib.phase === "countdown") {
                    if (calibText) calibText.textContent = "Hold still\u2026 " + calib.countdown_remaining;
                } else if (calib.phase === "capturing") {
                    if (calibText) calibText.textContent = "Scanning " + calib.frames_captured + "/" + calib.frames_needed;
                }
            } else {
                if (calibBtn) {
                    calibBtn.disabled = false;
                    calibBtn.textContent = calib.calibrated ? "Recalibrate" : "Calibrate";
                }
                if (calibStatus) calibStatus.style.display = "none";
            }
        }
    }

    /* ---- Focus timer ---- */

    function startLocalTimer(initialElapsed) {
        focusStartTime = Date.now() - (initialElapsed * 1000);
        focusTimerInterval = setInterval(function () {
            var elapsed = Math.floor((Date.now() - focusStartTime) / 1000);
            setFocusTimer(elapsed);
        }, 1000);
    }

    function stopLocalTimer() {
        if (focusTimerInterval) {
            clearInterval(focusTimerInterval);
            focusTimerInterval = null;
        }
        focusStartTime = null;
        setFocusTimer(0);
    }

    function setFocusTimer(seconds) {
        var m = Math.floor(seconds / 60);
        var s = seconds % 60;
        setText("focus-time", pad(m) + ":" + pad(s));
    }

    /* ---- Rules ---- */

    function fetchRules() {
        fetch("/api/rules")
            .then(function (r) { return r.json(); })
            .then(renderRules)
            .catch(function () {});
    }

    function renderRules(rules) {
        var list = document.getElementById("rules-list");
        if (!list) return;
        list.innerHTML = "";

        rules.forEach(function (rule) {
            var li = document.createElement("li");
            li.className = "rule-item" + (rule.active ? "" : " inactive");

            li.innerHTML =
                '<label class="toggle">' +
                    '<input type="checkbox"' + (rule.active ? " checked" : "") + ' onchange="toggleRule(\'' + rule.id + '\')">' +
                    '<span class="toggle-slider"></span>' +
                '</label>' +
                '<span class="badge badge-' + esc(rule.type) + '">' + esc(rule.type) + '</span>' +
                '<span class="rule-desc" title="' + esc(rule.description) + '">' + esc(rule.description) + '</span>' +
                '<span class="badge badge-' + esc(rule.severity) + '">' + esc(rule.severity) + '</span>' +
                '<button class="rule-delete" onclick="deleteRule(\'' + rule.id + '\')" title="Delete" aria-label="Delete rule">&times;</button>';

            list.appendChild(li);
        });
    }

    window.toggleRule = function (id) {
        fetch("/api/rules/" + id + "/toggle", { method: "PUT" })
            .then(function () { fetchRules(); });
    };

    window.deleteRule = function (id) {
        fetch("/api/rules/" + id, { method: "DELETE" })
            .then(function () { fetchRules(); });
    };

    window.toggleAddForm = function () {
        var form = document.getElementById("add-rule-form");
        if (form) form.style.display = form.style.display === "none" ? "flex" : "none";
    };

    window.addRule = function (event) {
        event.preventDefault();

        var typeEl     = document.getElementById("rule-type");
        var descEl     = document.getElementById("rule-desc");
        var severityEl = document.getElementById("rule-severity");

        var body = {
            type:        typeEl.value,
            description: descEl.value,
            threshold:   {},
            severity:    severityEl.value
        };

        fetch("/api/rules", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body)
        })
        .then(function (r) {
            if (r.ok) {
                typeEl.value     = "";
                descEl.value     = "";
                severityEl.value = "";
                document.getElementById("add-rule-form").style.display = "none";
                fetchRules();
            }
        });
    };

    /* ---- Focus controls ---- */

    window.startFocus = function () {
        fetch("/api/focus/start", { method: "POST" });
    };

    window.stopFocus = function () {
        fetch("/api/focus/stop", { method: "POST" });
    };

    /* ---- Calibration ---- */

    window.startCalibration = function () {
        var btn = document.getElementById("btn-calibrate");
        if (btn) btn.disabled = true;
        fetch("/api/calibrate", { method: "POST" });
    };

    window.resetAll = function () {
        fetch("/api/reset", { method: "POST" }).then(function () {
            setText("stat-posture", "0");
            setText("stat-phone", "0");
            setText("stat-focus", "0");
        });
    };

    /* ---- Helpers ---- */

    function setText(id, value) {
        var el = document.getElementById(id);
        if (el) el.textContent = String(value);
    }

    function capitalize(s) {
        return s.charAt(0).toUpperCase() + s.slice(1);
    }

    function pad(n) {
        return n < 10 ? "0" + n : String(n);
    }

    function esc(s) {
        var el = document.createElement("span");
        el.textContent = s;
        return el.innerHTML;
    }

    function updateMetricBar(barId, valId, value, maxVal, suffix) {
        var bar = document.getElementById(barId);
        var valEl = document.getElementById(valId);
        if (value === null || value === undefined) {
            if (bar) { bar.style.width = "0%"; bar.className = "metric-bar"; }
            if (valEl) valEl.textContent = "--" + suffix;
            return;
        }
        var pct = Math.min(100, (Math.abs(value) / maxVal) * 100);
        if (bar) {
            bar.style.width = pct + "%";
            bar.className = "metric-bar";
            if (pct > 70) bar.classList.add("poor");
            else if (pct > 40) bar.classList.add("fair");
        }
        if (valEl) valEl.textContent = (typeof value === "number" ? value.toFixed(1) : value) + suffix;
    }

    /* ---- Camera ---- */

    function refreshCamera() {
        var img = document.getElementById("camera-img");
        if (!img) return;
        var newImg = new Image();
        newImg.onload = function () {
            img.src = newImg.src;
            setTimeout(refreshCamera, 100);
        };
        newImg.onerror = function () {
            setTimeout(refreshCamera, 500);
        };
        newImg.src = "/api/camera_frame?" + Date.now();
    }

    /* ---- Init ---- */

    connectWS();
    fetchRules();
    refreshCamera();
})();
