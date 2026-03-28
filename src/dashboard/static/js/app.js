/* Buddy Dashboard — vanilla JS client */

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

    /* ---- WebSocket ---- */

    function connectWS() {
        var protocol = location.protocol === "https:" ? "wss:" : "ws:";
        var url = protocol + "//" + location.host + "/ws";

        ws = new WebSocket(url);

        ws.onopen = function () {
            var dot = document.getElementById("ws-status");
            if (dot) {
                dot.classList.add("connected");
                dot.title = "WebSocket connected";
            }
        };

        ws.onmessage = function (event) {
            try {
                var state = JSON.parse(event.data);
                updateState(state);
            } catch (_) { /* ignore malformed frames */ }
        };

        ws.onclose = function () {
            var dot = document.getElementById("ws-status");
            if (dot) {
                dot.classList.remove("connected");
                dot.title = "WebSocket disconnected";
            }
            setTimeout(connectWS, RECONNECT_DELAY_MS);
        };

        ws.onerror = function () {
            if (ws) ws.close();
        };
    }

    /* ---- State updates ---- */

    function updateState(state) {
        var emotion = state.emotion || "neutral";
        var emoji = EMOTION_MAP[emotion] || EMOTION_MAP.neutral;

        setText("emotion-emoji", emoji);
        setText("emotion-label", capitalize(emotion));

        var stageName = state.stage_name || "Egg";
        var stageNum  = state.stage !== undefined ? state.stage : 0;
        setText("stage-badge", "Stage " + stageNum + ": " + stageName);

        var xp     = state.xp || 0;
        var xpNext = state.next_stage_xp || 1;
        var pct    = Math.min(100, (xp / xpNext) * 100);
        var fill   = document.getElementById("xp-fill");
        if (fill) fill.style.width = pct + "%";
        setText("xp-text", xp + " / " + (state.next_stage_xp || "MAX") + " XP");

        var postureDot = document.getElementById("posture-dot");
        if (postureDot) {
            postureDot.className = "dot";
            if (emotion === "sad" || emotion === "concerned") postureDot.classList.add("bad");
            else if (emotion === "angry") postureDot.classList.add("bad");
            else postureDot.classList.add("good");
        }
        var postureText = (emotion === "angry") ? "Phone Detected" :
            (emotion === "sad" || emotion === "concerned") ? "Posture: Bad" : "Posture: Good";
        setText("posture-label", postureText);

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
            if (!focusTimerInterval) startLocalTimer(elapsed);
        } else {
            stopLocalTimer();
        }

        var violations = state.violations_today || {};
        setText("stat-posture", violations.posture_count || 0);
        setText("stat-phone",   violations.phone_count || 0);

        if (state.focus_active && state.focus_start_time) {
            var elapsedSec = Math.floor(Date.now() / 1000 - state.focus_start_time);
            setText("stat-focus", Math.floor(elapsedSec / 60));
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

    /* ---- Rules CRUD ---- */

    function fetchRules() {
        fetch("/api/rules")
            .then(function (r) { return r.json(); })
            .then(renderRules)
            .catch(function () { /* silent */ });
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
                '<button class="rule-delete" onclick="deleteRule(\'' + rule.id + '\')" title="Delete rule">&times;</button>';

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

    /* ---- Init ---- */

    connectWS();
    fetchRules();
})();
