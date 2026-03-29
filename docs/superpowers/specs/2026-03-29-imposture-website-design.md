# Imposture Website Design Spec

**Date:** 2026-03-29
**Project:** Imposture (Buddy AI Desk Pet)
**Context:** YHack 2026 hackathon project

## Overview

Design system and page specifications for the Imposture website, covering both a marketing landing page and a functional dashboard. The visual direction is **Warm & Friendly** — soft gradients, rounded shapes, and a cream/orange palette that feels approachable and emotionally engaging, with pixel art character illustrations providing a nostalgic Tamagotchi nod.

## Design System

### Color Palette — "Pet Tech Warm"

| Token        | Hex       | Usage                                      |
|--------------|-----------|---------------------------------------------|
| Primary      | `#F97316` | Buttons, active states, brand accent        |
| Secondary    | `#FB923C` | Hover states, secondary highlights          |
| Accent       | `#2563EB` | Links, info badges, accent elements         |
| Success      | `#059669` | Connected status, positive indicators       |
| Destructive  | `#DC2626` | Delete actions, error states, alerts        |
| Background   | `#FFF7ED` | Page background (warm cream)                |
| Card         | `#FFFFFF` | Card surfaces                               |
| Text         | `#1E293B` | Primary text (slate-800)                    |
| Muted Text   | `#64748B` | Secondary/helper text (slate-500)           |
| Border       | `#FED7AA` | Card borders, dividers (orange-200)         |
| Foreground   | `#9A3412` | Logo, strong labels (orange-800)            |
| Dark Section | `#1E293B` | Tech stack section background (slate-800)   |

### Typography

**Font Pairing:** Varela Round (headings) + Nunito Sans (body)

```css
@import url('https://fonts.googleapis.com/css2?family=Nunito+Sans:wght@300;400;500;600;700&family=Varela+Round&display=swap');
```

| Element         | Font         | Size  | Weight | Line Height |
|-----------------|-------------|-------|--------|-------------|
| Hero heading    | Varela Round | 40px  | 400    | 1.2         |
| Section heading | Varela Round | 24px  | 400    | 1.3         |
| Card title      | Nunito Sans  | 14px  | 700    | 1.4         |
| Body text       | Nunito Sans  | 16px  | 400    | 1.6         |
| Small/label     | Nunito Sans  | 12px  | 600    | 1.4         |
| Nav links       | Nunito Sans  | 14px  | 600    | 1           |

### Icons

**Library:** Lucide Icons (https://lucide.dev)
- Stroke width: 1.5px
- Size: 20-24px for feature icons, 16px for inline
- Color: primary (#F97316) or muted (#64748B) depending on context

### Border Radius Scale

| Element      | Radius |
|-------------|--------|
| Buttons     | 24px (pill)  |
| Cards       | 14px         |
| Feature icons| 12px        |
| XP bar      | 4px          |
| Toggle      | 8px          |

### Shadows

- Cards: `0 2px 8px rgba(249, 115, 22, 0.06)`
- Buttons: `0 4px 14px rgba(249, 115, 22, 0.35)`
- Pet avatar: `0 6px 20px rgba(249, 115, 22, 0.15)`

### Decorative Elements

- **Floating blobs**: Soft peach/orange gradient blobs in hero section, slow drifting animation
- **Dot grid**: Subtle dot pattern on background sections
- **Rounded corners**: Consistent use of the radius scale above

## Pages

### 1. Landing Page (`/`)

Sections in order:

#### Navigation Bar
- Left: Logo text "imposture" in Foreground color (#9A3412), font-weight 800
- Right: "Features", "Tech Stack", "GitHub" links
- Background: #FFF7ED with bottom border #FED7AA
- Sticky on scroll

#### Hero Section
- Background: gradient from #FFF7ED to #FFFFFF
- Center: Pixel art pet character in a circular container (120px, #FFF2E6 background)
- Heading: "Your desk buddy that **keeps you honest.**" (orange span on "keeps you honest")
- Subtext: "An AI-powered Tamagotchi that watches your posture, guards against distractions, and grows the more you focus."
- CTA button: "Meet Your Buddy" — pill shape, orange, with shadow

#### Features Section
- Background: #FFFFFF
- Heading: "What Buddy Does"
- 4-column card grid (responsive: 2x2 on mobile, 4x1 on desktop):
  1. **Posture Watch** — "MediaPipe tracks your spine angle and nudges you to sit tall."
  2. **Phone Guard** — "Detects when you pick up your phone and alerts your buddy."
  3. **Growth System** — "Egg to Adult in 5 stages. Focus to level up, slack off and devolve."
  4. **Voice Commands** — "'Hey Buddy' — set rules, start timers, and chat with your pet."
- Each card: #FFF7ED background, #FED7AA border, 16px radius
- Icon container: 44x44px, #F97316 background, white Lucide icon, 12px radius

#### Tech Stack Section
- Background: #1E293B (dark, for contrast)
- Heading: "Built With" in white
- Chip grid of technologies: Raspberry Pi 4B, Arduino UNO, MediaPipe Pose, OpenWakeWord, FastAPI, ElevenLabs TTS, Deepgram STT, Lava LLM, SSD1309 OLED, NeoPixel LEDs
- Chip style: rgba(255,255,255,0.08) background, rgba(255,255,255,0.1) border, #FED7AA text, 10px radius

### 2. Dashboard (`/dashboard`)

#### Section Renaming

| Old (Space Theme)    | New (Warm Theme) |
|---------------------|------------------|
| Crewmate Status     | Your Buddy       |
| Ship Rules          | Rules            |
| Security            | Camera           |
| Vital Signs         | Stats            |

#### Navigation Bar
- Left: "imposture" logo in #9A3412
- Right: Connection status indicator (green dot + "Connected")
- Background: #FFF7ED, border-bottom: #FED7AA

#### Layout
- Background: #FFFBF5 (slightly warmer than landing)
- Card-based layout with flexible grid
- Cards: white background, #FED7AA border, 14px radius, subtle orange shadow

#### Your Buddy Card
- Pixel art pet character in circular container
- Pet name and stage label below
- XP progress bar: #FED7AA track, #F97316 fill, 8px height
- Posture status indicator
- Focus timer with start/stop controls

#### Rules Card
- List of rules with colored dot indicators (orange/blue/green by type)
- Toggle switches for each rule (#F97316 active color)
- Add rule form with type dropdown, description input, severity selector
- Delete button (destructive red on hover)

#### Camera Card
- Live webcam frame display
- Calibrate button
- Status overlay

#### Stats Card
- Key metrics: Focus Today, Posture Alerts, Phone Alerts
- Values colored by sentiment (green for good, orange for warning, red for alert)

## Imagery

### Pet Character
- **Style:** Pixel art sprites, same aesthetic as the OLED display but higher resolution for web
- **Emotions:** happy, neutral, concerned, sad, angry, sleeping, excited — matching the 7 emotional states
- **Rendering:** `image-rendering: pixelated` CSS for crisp pixel edges
- **Source:** Custom pixel art (can use Piskel, Aseprite, or similar tool to create)

### Photos / Media
- No stock photography needed
- Hardware photos of the actual device can be added later if available
- Hero illustration is the pixel art pet character, not a photo

## Responsive Breakpoints

| Breakpoint | Layout                                      |
|-----------|----------------------------------------------|
| < 640px   | Single column, stacked cards, hamburger nav  |
| 640-1024px| 2-column feature grid, stacked dashboard     |
| > 1024px  | 4-column features, side-by-side dashboard    |

Max content width: 1200px (centered)

## Accessibility

- Text contrast: minimum 4.5:1 ratio (verified: #1E293B on #FFF7ED = 11.4:1)
- Focus rings: 2px solid #2563EB on all interactive elements
- Alt text on all images
- Keyboard navigable
- `prefers-reduced-motion`: disable floating blob animations
- Minimum touch target: 44x44px
