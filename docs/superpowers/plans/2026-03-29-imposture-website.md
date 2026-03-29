# Imposture Website Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the landing page and dashboard CSS for Imposture, a warm & friendly Tamagotchi-style AI desk pet website.

**Architecture:** Static HTML/CSS/JS served by FastAPI + Jinja2. Landing page at `/` introduces the product with hero, features, and tech stack sections. Dashboard at `/dashboard` is restyled from space theme to warm theme. No new backend changes needed — only HTML templates, CSS, and JS.

**Tech Stack:** HTML5, CSS3 (vanilla, no framework), vanilla JavaScript, Google Fonts (Varela Round + Nunito Sans), Lucide Icons (CDN)

**Design Spec:** `docs/superpowers/specs/2026-03-29-imposture-website-design.md`

---

## File Structure

| Action | File | Responsibility |
|--------|------|----------------|
| Rewrite | `src/dashboard/templates/landing.html` | Landing page: nav, hero, features, tech stack |
| Rewrite | `src/dashboard/static/css/landing.css` | Landing page styles |
| Write | `src/dashboard/static/js/landing.js` | Landing page smooth scroll + mobile nav toggle |
| Rewrite | `src/dashboard/static/css/style.css` | Dashboard styles (warm rebrand) |
| Modify | `src/dashboard/templates/index.html` | Rename sections, remove space theme elements, update icon references |
| Modify | `src/dashboard/static/js/app.js` | Remove starfield, update color map to warm palette |

---

### Task 1: Add Google Fonts and Lucide Icons to both templates

**Files:**
- Modify: `src/dashboard/templates/landing.html`
- Modify: `src/dashboard/templates/index.html`

- [ ] **Step 1: Update `landing.html` with full HTML structure and font/icon imports**

Replace the entire file with:

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Imposture — Your AI Desk Buddy</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Nunito+Sans:wght@300;400;500;600;700&family=Varela+Round&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="/static/css/landing.css">
</head>
<body>
    <nav class="nav" id="nav">
        <div class="nav-inner">
            <a href="/" class="nav-logo">imposture</a>
            <button class="nav-toggle" id="nav-toggle" aria-label="Toggle menu">
                <span></span><span></span><span></span>
            </button>
            <div class="nav-links" id="nav-links">
                <a href="#features">Features</a>
                <a href="#tech-stack">Tech Stack</a>
                <a href="/dashboard" class="nav-cta">Open Dashboard</a>
            </div>
        </div>
    </nav>

    <section class="hero">
        <div class="hero-blobs" aria-hidden="true">
            <div class="blob blob-1"></div>
            <div class="blob blob-2"></div>
            <div class="blob blob-3"></div>
        </div>
        <div class="hero-content">
            <div class="hero-pet" aria-hidden="true">
                <div class="pet-circle">
                    <svg class="pet-pixel-art" viewBox="0 0 16 16" width="80" height="80">
                        <!-- Pixel art egg/hatchling -->
                        <rect x="5" y="2" width="6" height="8" rx="3" fill="#F97316"/>
                        <rect x="6" y="4" width="1" height="2" fill="#1E293B"/>
                        <rect x="9" y="4" width="1" height="2" fill="#1E293B"/>
                        <rect x="7" y="7" width="2" height="1" fill="#1E293B"/>
                        <rect x="4" y="10" width="2" height="2" fill="#F97316"/>
                        <rect x="10" y="10" width="2" height="2" fill="#F97316"/>
                    </svg>
                </div>
            </div>
            <h1>Your desk buddy that <span class="highlight">keeps you honest.</span></h1>
            <p class="hero-sub">An AI-powered Tamagotchi that watches your posture, guards against distractions, and grows the more you focus.</p>
            <a href="/dashboard" class="btn-primary">Meet Your Buddy</a>
        </div>
    </section>

    <section class="features" id="features">
        <h2>What Buddy Does</h2>
        <div class="features-grid">
            <div class="feature-card">
                <div class="feature-icon">
                    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5.2 20a13.4 13.4 0 0 1 0-16"/><path d="M18.8 4a13.4 13.4 0 0 1 0 16"/><circle cx="12" cy="12" r="2"/></svg>
                </div>
                <h3>Posture Watch</h3>
                <p>MediaPipe tracks your spine angle in real-time and nudges you to sit tall.</p>
            </div>
            <div class="feature-card">
                <div class="feature-icon">
                    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="5" y="2" width="14" height="20" rx="2"/><line x1="12" y1="18" x2="12" y2="18.01"/></svg>
                </div>
                <h3>Phone Guard</h3>
                <p>Detects when you pick up your phone and alerts your buddy — no cheating.</p>
            </div>
            <div class="feature-card">
                <div class="feature-icon">
                    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/></svg>
                </div>
                <h3>Growth System</h3>
                <p>Egg to Adult in 5 stages. Focus to level up, slack off and your buddy devolves.</p>
            </div>
            <div class="feature-card">
                <div class="feature-icon">
                    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><line x1="12" y1="19" x2="12" y2="23"/></svg>
                </div>
                <h3>Voice Commands</h3>
                <p>"Hey Buddy" — set rules, start timers, and chat with your pet using your voice.</p>
            </div>
        </div>
    </section>

    <section class="tech-stack" id="tech-stack">
        <h2>Built With</h2>
        <div class="tech-grid">
            <span class="tech-chip">Raspberry Pi 4B</span>
            <span class="tech-chip">Arduino UNO</span>
            <span class="tech-chip">MediaPipe Pose</span>
            <span class="tech-chip">OpenWakeWord</span>
            <span class="tech-chip">FastAPI</span>
            <span class="tech-chip">ElevenLabs TTS</span>
            <span class="tech-chip">Deepgram STT</span>
            <span class="tech-chip">Lava LLM</span>
            <span class="tech-chip">SSD1309 OLED</span>
            <span class="tech-chip">NeoPixel LEDs</span>
        </div>
    </section>

    <footer class="footer">
        <p>Imposture &mdash; YHack 2026</p>
    </footer>

    <script src="/static/js/landing.js"></script>
</body>
</html>
```

- [ ] **Step 2: Update `index.html` head to include Google Fonts**

In `src/dashboard/templates/index.html`, add font imports after the viewport meta tag (before the stylesheet link):

```html
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Nunito+Sans:wght@300;400;500;600;700&family=Varela+Round&display=swap" rel="stylesheet">
```

- [ ] **Step 3: Verify both files load correctly**

Run: `cd /Users/possible/Documents/Imposture && python3 -c "from src.dashboard.app import create_app; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add src/dashboard/templates/landing.html src/dashboard/templates/index.html
git commit -m "feat: add landing page HTML structure and Google Fonts imports"
```

---

### Task 2: Write landing page CSS

**Files:**
- Create: `src/dashboard/static/css/landing.css`

- [ ] **Step 1: Write the complete landing page stylesheet**

Write the following to `src/dashboard/static/css/landing.css`:

```css
/* ============================================
   Imposture Landing Page — Warm & Friendly
   Design spec: docs/superpowers/specs/2026-03-29-imposture-website-design.md
   ============================================ */

/* ---- Reset & Base ---- */

*,
*::before,
*::after {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
}

html {
    scroll-behavior: smooth;
}

body {
    font-family: 'Nunito Sans', sans-serif;
    color: #1E293B;
    background: #FFF7ED;
    line-height: 1.6;
    -webkit-font-smoothing: antialiased;
}

h1, h2, h3 {
    font-family: 'Varela Round', sans-serif;
}

a {
    text-decoration: none;
    color: inherit;
}

/* ---- Navigation ---- */

.nav {
    position: sticky;
    top: 0;
    z-index: 100;
    background: #FFF7ED;
    border-bottom: 1px solid #FED7AA;
    backdrop-filter: blur(8px);
}

.nav-inner {
    max-width: 1200px;
    margin: 0 auto;
    padding: 16px 24px;
    display: flex;
    align-items: center;
    justify-content: space-between;
}

.nav-logo {
    font-family: 'Varela Round', sans-serif;
    font-size: 20px;
    font-weight: 400;
    color: #9A3412;
    letter-spacing: -0.5px;
}

.nav-links {
    display: flex;
    align-items: center;
    gap: 28px;
}

.nav-links a {
    font-size: 14px;
    font-weight: 600;
    color: #9A3412;
    opacity: 0.7;
    transition: opacity 0.2s;
}

.nav-links a:hover {
    opacity: 1;
}

.nav-cta {
    background: #F97316;
    color: #fff !important;
    opacity: 1 !important;
    padding: 8px 20px;
    border-radius: 24px;
    font-weight: 700;
    transition: transform 0.15s, box-shadow 0.15s;
}

.nav-cta:hover {
    transform: translateY(-1px);
    box-shadow: 0 4px 14px rgba(249, 115, 22, 0.35);
}

/* Mobile hamburger */
.nav-toggle {
    display: none;
    flex-direction: column;
    gap: 5px;
    background: none;
    border: none;
    cursor: pointer;
    padding: 4px;
}

.nav-toggle span {
    display: block;
    width: 24px;
    height: 2px;
    background: #9A3412;
    border-radius: 2px;
    transition: transform 0.2s, opacity 0.2s;
}

/* ---- Hero ---- */

.hero {
    position: relative;
    overflow: hidden;
    background: linear-gradient(180deg, #FFF7ED 0%, #FFFFFF 100%);
    padding: 80px 24px 60px;
    text-align: center;
}

.hero-content {
    position: relative;
    z-index: 1;
    max-width: 600px;
    margin: 0 auto;
}

.hero-pet {
    margin-bottom: 24px;
}

.pet-circle {
    width: 120px;
    height: 120px;
    margin: 0 auto;
    background: #FFF2E6;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    box-shadow: 0 6px 20px rgba(249, 115, 22, 0.15);
}

.pet-pixel-art {
    image-rendering: pixelated;
    image-rendering: crisp-edges;
}

.hero h1 {
    font-size: 40px;
    line-height: 1.2;
    margin-bottom: 16px;
    color: #1E293B;
}

.highlight {
    color: #F97316;
}

.hero-sub {
    font-size: 16px;
    color: #64748B;
    max-width: 480px;
    margin: 0 auto 28px;
    line-height: 1.7;
}

.btn-primary {
    display: inline-block;
    background: #F97316;
    color: #fff;
    padding: 14px 32px;
    border-radius: 24px;
    font-family: 'Nunito Sans', sans-serif;
    font-size: 16px;
    font-weight: 700;
    box-shadow: 0 4px 14px rgba(249, 115, 22, 0.35);
    transition: transform 0.15s, box-shadow 0.15s;
    cursor: pointer;
}

.btn-primary:hover {
    transform: translateY(-2px);
    box-shadow: 0 6px 20px rgba(249, 115, 22, 0.45);
}

.btn-primary:active {
    transform: translateY(0);
}

/* Floating blobs */
.hero-blobs {
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    pointer-events: none;
    overflow: hidden;
}

.blob {
    position: absolute;
    border-radius: 50%;
    filter: blur(60px);
    opacity: 0.25;
}

.blob-1 {
    width: 300px;
    height: 300px;
    background: #FED7AA;
    top: -60px;
    right: -80px;
    animation: drift 8s ease-in-out infinite alternate;
}

.blob-2 {
    width: 200px;
    height: 200px;
    background: #FB923C;
    bottom: -40px;
    left: -60px;
    animation: drift 10s ease-in-out infinite alternate-reverse;
}

.blob-3 {
    width: 150px;
    height: 150px;
    background: #BFDBFE;
    top: 40%;
    left: 60%;
    animation: drift 12s ease-in-out infinite alternate;
}

@keyframes drift {
    from { transform: translate(0, 0); }
    to   { transform: translate(20px, -20px); }
}

@media (prefers-reduced-motion: reduce) {
    .blob { animation: none; }
}

/* ---- Features ---- */

.features {
    background: #FFFFFF;
    padding: 64px 24px;
}

.features h2 {
    text-align: center;
    font-size: 28px;
    color: #1E293B;
    margin-bottom: 40px;
}

.features-grid {
    max-width: 1000px;
    margin: 0 auto;
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 20px;
}

.feature-card {
    background: #FFF7ED;
    border: 1px solid #FED7AA;
    border-radius: 16px;
    padding: 24px 20px;
    text-align: center;
    transition: transform 0.2s;
}

.feature-card:hover {
    transform: translateY(-4px);
}

.feature-icon {
    width: 48px;
    height: 48px;
    margin: 0 auto 14px;
    background: #F97316;
    border-radius: 12px;
    display: flex;
    align-items: center;
    justify-content: center;
    color: #fff;
}

.feature-card h3 {
    font-family: 'Nunito Sans', sans-serif;
    font-size: 15px;
    font-weight: 700;
    color: #1E293B;
    margin-bottom: 8px;
}

.feature-card p {
    font-size: 13px;
    color: #64748B;
    line-height: 1.5;
}

/* ---- Tech Stack ---- */

.tech-stack {
    background: #1E293B;
    padding: 64px 24px;
    text-align: center;
}

.tech-stack h2 {
    color: #F8FAFC;
    font-size: 28px;
    margin-bottom: 32px;
}

.tech-grid {
    max-width: 800px;
    margin: 0 auto;
    display: flex;
    flex-wrap: wrap;
    gap: 12px;
    justify-content: center;
}

.tech-chip {
    background: rgba(255, 255, 255, 0.08);
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 10px;
    padding: 10px 20px;
    font-size: 14px;
    font-weight: 600;
    color: #FED7AA;
    transition: background 0.2s;
}

.tech-chip:hover {
    background: rgba(255, 255, 255, 0.14);
}

/* ---- Footer ---- */

.footer {
    background: #1E293B;
    border-top: 1px solid rgba(255, 255, 255, 0.06);
    padding: 24px;
    text-align: center;
    font-size: 13px;
    color: #64748B;
}

/* ---- Responsive ---- */

@media (max-width: 768px) {
    .nav-toggle {
        display: flex;
    }

    .nav-links {
        display: none;
        position: absolute;
        top: 100%;
        left: 0;
        right: 0;
        background: #FFF7ED;
        border-bottom: 1px solid #FED7AA;
        flex-direction: column;
        padding: 16px 24px;
        gap: 16px;
    }

    .nav-links.open {
        display: flex;
    }

    .hero {
        padding: 48px 24px 40px;
    }

    .hero h1 {
        font-size: 28px;
    }

    .features-grid {
        grid-template-columns: repeat(2, 1fr);
        gap: 16px;
    }
}

@media (max-width: 480px) {
    .features-grid {
        grid-template-columns: 1fr;
    }

    .hero h1 {
        font-size: 24px;
    }

    .hero-sub {
        font-size: 14px;
    }
}
```

- [ ] **Step 2: Open landing page in browser to visually verify**

Run: `cd /Users/possible/Documents/Imposture && python3 -m uvicorn src.dashboard.app:create_app --factory --host 0.0.0.0 --port 8080 &`

Open `http://localhost:8080` and verify: nav bar with orange logo, hero with pixel art circle, 4 feature cards, dark tech stack section, footer.

- [ ] **Step 3: Commit**

```bash
git add src/dashboard/static/css/landing.css
git commit -m "feat: add landing page CSS with warm & friendly design system"
```

---

### Task 3: Write landing page JavaScript

**Files:**
- Create: `src/dashboard/static/js/landing.js`

- [ ] **Step 1: Write landing page JS for mobile nav and smooth scroll**

Write to `src/dashboard/static/js/landing.js`:

```javascript
(function () {
    "use strict";

    /* ---- Mobile nav toggle ---- */

    var toggle = document.getElementById("nav-toggle");
    var links = document.getElementById("nav-links");

    if (toggle && links) {
        toggle.addEventListener("click", function () {
            links.classList.toggle("open");
        });

        /* Close menu when a link is clicked */
        links.querySelectorAll("a").forEach(function (link) {
            link.addEventListener("click", function () {
                links.classList.remove("open");
            });
        });
    }

    /* ---- Sticky nav shadow on scroll ---- */

    var nav = document.getElementById("nav");
    if (nav) {
        window.addEventListener("scroll", function () {
            if (window.scrollY > 10) {
                nav.style.boxShadow = "0 2px 12px rgba(249, 115, 22, 0.08)";
            } else {
                nav.style.boxShadow = "none";
            }
        }, { passive: true });
    }
})();
```

- [ ] **Step 2: Verify mobile nav toggle works**

Open `http://localhost:8080` on a narrow viewport (< 768px). Tap the hamburger icon — nav links should slide open. Tap a link — it should close and smooth-scroll.

- [ ] **Step 3: Commit**

```bash
git add src/dashboard/static/js/landing.js
git commit -m "feat: add landing page JS for mobile nav and scroll shadow"
```

---

### Task 4: Rebrand dashboard HTML from space theme to warm theme

**Files:**
- Modify: `src/dashboard/templates/index.html`

- [ ] **Step 1: Remove the starfield div and space-themed SVG logo**

In `index.html`, remove the starfield div (line 10):
```html
    <div class="stars" id="stars"></div>
```

Replace the entire header (lines 12-28) with:
```html
    <header>
        <div class="header-inner">
            <a href="/" class="header-logo">imposture</a>
            <div class="header-status">
                <span class="connection-label">Status</span>
                <span class="connection-dot" id="ws-status" title="Disconnected"></span>
            </div>
        </div>
    </header>
```

- [ ] **Step 2: Rename section headings**

Replace `<h2>Crewmate Status</h2>` with `<h2>Your Buddy</h2>`.

Replace the Crewmate Status card icon:
```html
                <span class="card-icon" aria-hidden="true">&#9733;</span>
```
with:
```html
                <span class="card-icon" aria-hidden="true">
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><circle cx="12" cy="12" r="10"/><path d="M8 14s1.5 2 4 2 4-2 4-2"/><line x1="9" y1="9" x2="9.01" y2="9"/><line x1="15" y1="9" x2="15.01" y2="9"/></svg>
                </span>
```

Replace `<h2>Ship Rules</h2>` with `<h2>Rules</h2>`.

Replace the Ship Rules icon `&#9888;` with:
```html
                    <span class="card-icon" aria-hidden="true">
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>
                    </span>
```

Replace `<h2>Security</h2>` with `<h2>Camera</h2>`.

Replace the Security icon `&#128249;` with:
```html
                    <span class="card-icon" aria-hidden="true">
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/><circle cx="12" cy="13" r="4"/></svg>
                    </span>
```

Replace `<h2>Vital Signs</h2>` with `<h2>Stats</h2>`.

Replace the Vital Signs icon `&#128200;` with:
```html
                <span class="card-icon" aria-hidden="true">
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><path d="M18 20V10"/><path d="M12 20V4"/><path d="M6 20v-6"/></svg>
                </span>
```

- [ ] **Step 3: Replace the crewmate SVG body with a simple pixel art container**

Replace the entire `crewmate-display` div (lines 39-52) with:
```html
            <div class="buddy-display">
                <div class="buddy-avatar" id="buddy-avatar">
                    <span class="emotion-emoji" id="emotion-emoji">&#128578;</span>
                </div>
            </div>
```

- [ ] **Step 4: Rename remaining space-themed labels**

Replace `<div class="taskbar-label">Task Progress</div>` with `<div class="taskbar-label">XP Progress</div>`.

Replace `<span class="comms-label">Comms</span>` — this was already removed in Step 1.

- [ ] **Step 5: Verify the HTML is valid**

Run: `python3 -c "
from src.dashboard.app import create_app
app = create_app()
print('Template loads OK')
"`

- [ ] **Step 6: Commit**

```bash
git add src/dashboard/templates/index.html
git commit -m "feat: rebrand dashboard HTML from space theme to warm theme"
```

---

### Task 5: Write dashboard CSS

**Files:**
- Create: `src/dashboard/static/css/style.css`

- [ ] **Step 1: Write the complete dashboard stylesheet**

Write to `src/dashboard/static/css/style.css`:

```css
/* ============================================
   Imposture Dashboard — Warm & Friendly Theme
   Design spec: docs/superpowers/specs/2026-03-29-imposture-website-design.md
   ============================================ */

/* ---- Reset & Base ---- */

*,
*::before,
*::after {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
}

body {
    font-family: 'Nunito Sans', sans-serif;
    color: #1E293B;
    background: #FFFBF5;
    line-height: 1.6;
    -webkit-font-smoothing: antialiased;
    min-height: 100vh;
}

h1, h2, h3 {
    font-family: 'Varela Round', sans-serif;
}

/* Screen reader only */
.sr-only {
    position: absolute;
    width: 1px;
    height: 1px;
    padding: 0;
    margin: -1px;
    overflow: hidden;
    clip: rect(0, 0, 0, 0);
    border: 0;
}

/* ---- Header ---- */

header {
    background: #FFF7ED;
    border-bottom: 1px solid #FED7AA;
    position: sticky;
    top: 0;
    z-index: 100;
}

.header-inner {
    max-width: 1200px;
    margin: 0 auto;
    padding: 14px 24px;
    display: flex;
    align-items: center;
    justify-content: space-between;
}

.header-logo {
    font-family: 'Varela Round', sans-serif;
    font-size: 20px;
    color: #9A3412;
    text-decoration: none;
    letter-spacing: -0.5px;
}

.header-status {
    display: flex;
    align-items: center;
    gap: 8px;
}

.connection-label {
    font-size: 12px;
    font-weight: 600;
    color: #64748B;
}

.connection-dot {
    width: 10px;
    height: 10px;
    border-radius: 50%;
    background: #DC2626;
    transition: background 0.3s;
}

.connection-dot.connected {
    background: #059669;
}

/* ---- Main Grid ---- */

.grid {
    max-width: 1200px;
    margin: 0 auto;
    padding: 20px;
    display: grid;
    grid-template-columns: 260px 1fr 200px;
    grid-template-rows: auto auto;
    gap: 16px;
}

.pet-status { grid-column: 1; grid-row: 1 / 3; }
.rules-panel { grid-column: 2; grid-row: 1; }
.camera-feed { grid-column: 2; grid-row: 2; }
.stats-bar { grid-column: 3; grid-row: 1 / 3; }

/* ---- Cards ---- */

.card {
    background: #FFFFFF;
    border: 1px solid #FED7AA;
    border-radius: 14px;
    padding: 20px;
    box-shadow: 0 2px 8px rgba(249, 115, 22, 0.06);
}

.card-header {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 16px;
}

.card-header h2 {
    font-family: 'Nunito Sans', sans-serif;
    font-size: 13px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 1px;
    color: #9A3412;
    opacity: 0.8;
}

.card-icon {
    color: #F97316;
    display: flex;
    align-items: center;
}

/* ---- Buddy (Pet) Display ---- */

.buddy-display {
    text-align: center;
    padding: 12px 0;
}

.buddy-avatar {
    width: 80px;
    height: 80px;
    margin: 0 auto 12px;
    background: #FFF2E6;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    box-shadow: 0 6px 20px rgba(249, 115, 22, 0.15);
    transition: background 0.3s;
}

.emotion-emoji {
    font-size: 36px;
    line-height: 1;
}

.emotion-label {
    font-size: 14px;
    font-weight: 600;
    color: #64748B;
    margin-bottom: 8px;
}

/* Growth / Stage */
.growth-info {
    text-align: center;
    margin-bottom: 12px;
}

.stage-badge {
    display: inline-block;
    font-size: 12px;
    font-weight: 700;
    color: #F97316;
    background: #FFF2E6;
    padding: 4px 12px;
    border-radius: 12px;
}

/* XP Bar */
.taskbar-wrapper {
    margin-bottom: 14px;
}

.taskbar-label {
    font-size: 11px;
    font-weight: 600;
    color: #64748B;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-bottom: 6px;
}

.taskbar {
    height: 8px;
    background: #FED7AA;
    border-radius: 4px;
    overflow: hidden;
}

.taskbar-fill {
    height: 100%;
    background: #F97316;
    border-radius: 4px;
    transition: width 0.5s ease;
}

.taskbar-text {
    font-size: 11px;
    color: #64748B;
    display: block;
    text-align: right;
    margin-top: 4px;
}

/* Status */
.status-row {
    margin-bottom: 12px;
}

.status-indicator {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 13px;
    color: #64748B;
}

.status-light {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: #64748B;
}

.status-light.good {
    background: #059669;
}

.status-light.bad {
    background: #DC2626;
    animation: pulse-red 1.5s ease-in-out infinite;
}

@keyframes pulse-red {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.4; }
}

/* Focus section */
.focus-section {
    border-top: 1px solid #FFF2E6;
    padding-top: 14px;
}

.focus-timer {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    font-size: 28px;
    font-weight: 700;
    color: #F97316;
    font-family: 'Nunito Sans', sans-serif;
    margin-bottom: 10px;
    font-variant-numeric: tabular-nums;
}

.focus-icon {
    font-size: 20px;
}

.focus-controls {
    display: flex;
    gap: 8px;
    justify-content: center;
}

/* ---- Buttons ---- */

.btn {
    display: inline-block;
    padding: 8px 18px;
    border: none;
    border-radius: 24px;
    font-family: 'Nunito Sans', sans-serif;
    font-size: 13px;
    font-weight: 700;
    cursor: pointer;
    transition: transform 0.15s, box-shadow 0.15s, background 0.15s;
}

.btn:hover {
    transform: translateY(-1px);
}

.btn:active {
    transform: translateY(0);
}

.btn-primary {
    background: #F97316;
    color: #fff;
    box-shadow: 0 2px 8px rgba(249, 115, 22, 0.25);
}

.btn-primary:hover {
    box-shadow: 0 4px 12px rgba(249, 115, 22, 0.35);
}

.btn-secondary {
    background: #FFF2E6;
    color: #9A3412;
}

.btn-secondary:hover {
    background: #FED7AA;
}

.btn-muted {
    background: #F1F0F0;
    color: #64748B;
}

.btn-small {
    padding: 5px 12px;
    font-size: 12px;
}

/* ---- Rules ---- */

.rules-header {
    justify-content: space-between;
}

.add-rule-form {
    display: flex;
    gap: 8px;
    margin-bottom: 14px;
    flex-wrap: wrap;
}

.add-rule-form select,
.add-rule-form input {
    font-family: 'Nunito Sans', sans-serif;
    font-size: 13px;
    padding: 8px 12px;
    border: 1px solid #FED7AA;
    border-radius: 10px;
    background: #FFF7ED;
    color: #1E293B;
    outline: none;
    transition: border-color 0.15s;
}

.add-rule-form select:focus,
.add-rule-form input:focus {
    border-color: #F97316;
    box-shadow: 0 0 0 2px rgba(249, 115, 22, 0.15);
}

.add-rule-form input {
    flex: 1;
    min-width: 140px;
}

.rules-list {
    list-style: none;
}

.rule-item {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 10px 0;
    border-bottom: 1px solid #FFF2E6;
    font-size: 13px;
}

.rule-item.inactive {
    opacity: 0.5;
}

.rule-desc {
    flex: 1;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}

/* Toggle switch */
.toggle {
    position: relative;
    width: 36px;
    height: 20px;
    flex-shrink: 0;
}

.toggle input {
    opacity: 0;
    width: 0;
    height: 0;
}

.toggle-slider {
    position: absolute;
    inset: 0;
    background: #E2E8F0;
    border-radius: 10px;
    cursor: pointer;
    transition: background 0.2s;
}

.toggle-slider::after {
    content: '';
    position: absolute;
    top: 2px;
    left: 2px;
    width: 16px;
    height: 16px;
    background: #fff;
    border-radius: 50%;
    transition: transform 0.2s;
}

.toggle input:checked + .toggle-slider {
    background: #F97316;
}

.toggle input:checked + .toggle-slider::after {
    transform: translateX(16px);
}

/* Badges */
.badge {
    display: inline-block;
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    padding: 2px 8px;
    border-radius: 6px;
    flex-shrink: 0;
}

.badge-posture { background: #FFF2E6; color: #9A3412; }
.badge-phone   { background: #EFF6FF; color: #1D4ED8; }
.badge-timer   { background: #ECFDF5; color: #065F46; }
.badge-custom  { background: #F5F3FF; color: #5B21B6; }

.badge-gentle   { background: #ECFDF5; color: #065F46; }
.badge-moderate { background: #FFF7ED; color: #9A3412; }
.badge-strict   { background: #FEF2F2; color: #991B1B; }

.rule-delete {
    background: none;
    border: none;
    color: #CBD5E1;
    font-size: 18px;
    cursor: pointer;
    padding: 0 4px;
    line-height: 1;
    transition: color 0.15s;
    flex-shrink: 0;
}

.rule-delete:hover {
    color: #DC2626;
}

/* ---- Camera ---- */

.camera-header {
    justify-content: space-between;
}

.camera-viewport {
    position: relative;
    border-radius: 10px;
    overflow: hidden;
    background: #1E293B;
    aspect-ratio: 4 / 3;
}

.camera-viewport img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: block;
}

.camera-overlay {
    position: absolute;
    inset: 0;
    border: 2px solid rgba(249, 115, 22, 0.2);
    border-radius: 10px;
    pointer-events: none;
}

.calibration-status {
    margin-top: 10px;
    font-size: 12px;
    font-weight: 600;
    color: #F97316;
    text-align: center;
}

/* ---- Stats ---- */

.stats-row {
    display: flex;
    flex-direction: column;
    gap: 0;
}

.stat {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 12px 0;
    border-bottom: 1px solid #FFF2E6;
}

.stat:last-child {
    border-bottom: none;
}

.stat-label {
    font-size: 12px;
    color: #64748B;
}

.stat-value {
    font-size: 18px;
    font-weight: 700;
    color: #1E293B;
    font-variant-numeric: tabular-nums;
}

.stat-danger {
    color: #F97316;
}

.stat-divider {
    display: none;
}

/* ---- Responsive ---- */

@media (max-width: 1024px) {
    .grid {
        grid-template-columns: 1fr 1fr;
        grid-template-rows: auto auto auto;
    }

    .pet-status { grid-column: 1; grid-row: 1; }
    .stats-bar  { grid-column: 2; grid-row: 1; }
    .rules-panel { grid-column: 1 / 3; grid-row: 2; }
    .camera-feed { grid-column: 1 / 3; grid-row: 3; }
}

@media (max-width: 640px) {
    .grid {
        grid-template-columns: 1fr;
    }

    .pet-status  { grid-column: 1; grid-row: 1; }
    .stats-bar   { grid-column: 1; grid-row: 2; }
    .rules-panel { grid-column: 1; grid-row: 3; }
    .camera-feed { grid-column: 1; grid-row: 4; }

    .stats-row {
        flex-direction: row;
        flex-wrap: wrap;
        justify-content: space-around;
    }

    .stat {
        flex-direction: column;
        text-align: center;
        border-bottom: none;
        padding: 8px 16px;
    }
}
```

- [ ] **Step 2: Verify dashboard renders with new styles**

Open `http://localhost:8080/dashboard` and verify: warm cream background, orange accents, Varela Round headings, white cards with peach borders.

- [ ] **Step 3: Commit**

```bash
git add src/dashboard/static/css/style.css
git commit -m "feat: add dashboard CSS with warm & friendly theme"
```

---

### Task 6: Update dashboard JavaScript — remove space theme, update colors

**Files:**
- Modify: `src/dashboard/static/js/app.js`

- [ ] **Step 1: Remove the starfield code and update the color map**

In `app.js`, remove the entire `CREWMATE_COLORS` object (lines 22-31) and the `generateStars` function (lines 35-53).

Replace the `CREWMATE_COLORS` object with a warm-palette emotion background map:

```javascript
    /* Buddy avatar backgrounds — warm palette */
    var BUDDY_BACKGROUNDS = {
        happy:     "#FFF2E6",
        neutral:   "#FFF7ED",
        concerned: "#FEF3C7",
        sad:       "#EFF6FF",
        angry:     "#FEF2F2",
        sleeping:  "#F5F3FF",
        excited:   "#ECFDF5"
    };
```

In the `updateState` function, replace the crewmate color block (lines 101-103):
```javascript
        /* Crewmate color */
        var color = CREWMATE_COLORS[emotion] || CREWMATE_COLORS.neutral;
        document.documentElement.style.setProperty("--crewmate-color", color);
```

with:
```javascript
        /* Buddy avatar background */
        var avatarBg = BUDDY_BACKGROUNDS[emotion] || BUDDY_BACKGROUNDS.neutral;
        var avatar = document.getElementById("buddy-avatar");
        if (avatar) avatar.style.background = avatarBg;
```

- [ ] **Step 2: Remove the generateStars() call from the init block**

At the bottom of the IIFE (line 347), remove:
```javascript
    generateStars();
```

- [ ] **Step 3: Verify dashboard JS works without errors**

Open `http://localhost:8080/dashboard`, open browser console. Verify no errors. Check that the WebSocket connects and emoji/stage/XP update correctly.

- [ ] **Step 4: Commit**

```bash
git add src/dashboard/static/js/app.js
git commit -m "refactor: replace space theme JS with warm buddy palette"
```

---

### Task 7: Final visual QA and responsive check

**Files:** None (read-only verification)

- [ ] **Step 1: Verify landing page at 1440px, 768px, and 375px widths**

Check:
- Nav: logo left, links right (desktop) / hamburger (mobile)
- Hero: centered pet circle, heading, subtext, CTA button
- Features: 4 columns (desktop) / 2 columns (tablet) / 1 column (mobile)
- Tech stack: dark section with wrapped chips
- Footer visible

- [ ] **Step 2: Verify dashboard at 1440px, 768px, and 375px widths**

Check:
- Header: "imposture" logo, connection dot
- Cards: 3-column (desktop) / 2-column (tablet) / stacked (mobile)
- Buddy avatar: emoji in circle, XP bar fills
- Rules: toggle switches, badges, delete buttons
- Stats: vertical list (desktop) / horizontal row (mobile)

- [ ] **Step 3: Check color contrast**

Verify #1E293B text on #FFF7ED background (11.4:1 ratio — passes WCAG AAA).
Verify #64748B muted text on #FFFFFF card (4.7:1 ratio — passes WCAG AA).

- [ ] **Step 4: Check focus states**

Tab through the landing page — all links and buttons should show a visible focus ring.

- [ ] **Step 5: Commit any fixes if needed**

```bash
git add -A
git commit -m "fix: visual QA adjustments for landing and dashboard"
```
