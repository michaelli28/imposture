# Buddy: AI-Powered Desk Pet — Design Spec

**Date:** 2026-03-28
**Project:** Imposture (YHack 2026)
**Team:** 4 people
**Event:** YHack 2026 (Yale Hackathon)

---

## 1. Overview

Buddy is a Tamagotchi-style AI desk companion that watches you through a webcam, detects bad posture and phone usage, and reacts with emotions, voice, lights, and sounds. Users set rules via natural language voice commands ("Hey Buddy, don't let me go on my phone"), and the pet enforces them — getting sad when you slouch, angry when you pick up your phone, and evolving as you build good habits.

**Core value proposition:** Gamified productivity through emotional attachment to an AI pet that lives on your desk.

**Identity:** Hybrid — AI assistant (takes commands, enforces rules) with a pet personality (has emotions, grows over time, reacts to your behavior).

---

## 2. Track Strategy

**Primary tracks (build for these):**
- **Hardware (QNX)** — $2,000 / $1,000 / $500 — Physical device is the core product
- **Societal Impact (ASUS)** — Supercomputers + gear — Posture health, phone addiction, wellness

**Secondary tracks (targeted integrations):**
- **Best use of Snap Lens Studio** — $1,500 / $1,000 / $500 — Standalone AR posture lens (stretch goal)
- **Best use of Lava API** — $1,000 + $500 creative — Route LLM calls through Lava gateway
- **ElevenLabs (MLH Partner)** — TBD — Already using for TTS

**Free submissions (no extra work):**
- Most Creative Hack — $100
- Most on Theme/Love — $100 ("self-love through self-care")

---

## 3. System Architecture

**Architecture: Pi-Centric**

The Raspberry Pi 4B is the brain. The Arduino UNO R3 is the face/body.

```
┌──────────────────────────────────────────────────────────────┐
│                     Raspberry Pi 4B (Brain)                   │
│                                                               │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────────┐  │
│  │ OpenWakeWord │  │ MediaPipe    │  │ FastAPI             │  │
│  │ (wake word)  │  │ Pose Lite    │  │ (dashboard server)  │  │
│  │ ~10% CPU     │  │ (CV @ 1 FPS) │  │ + WebSocket         │  │
│  │ ~100MB RAM   │  │ ~15% CPU     │  │ ~5% CPU             │  │
│  └──────┬───────┘  │ ~300MB RAM   │  └─────────┬──────────┘  │
│         │          └──────┬───────┘            │              │
│         ▼                 ▼                    │              │
│  ┌──────────────────────────────┐              │              │
│  │      Pet State Manager       │◄─────────────┘              │
│  │  (rules, mood, XP, growth)   │                             │
│  └──────────────┬───────────────┘                             │
│                 │                                              │
│  ┌──────────────▼───────────────┐                             │
│  │    Serial Commander          │                             │
│  │    (JSON over USB serial)    │                             │
│  └──────────────┬───────────────┘                             │
│                 │                                              │
│  Cloud APIs:    │                                              │
│  - ElevenLabs TTS (turbo, streaming)                          │
│  - STT (Whisper API or Deepgram)                              │
│  - LLM via Lava gateway                                       │
└─────────────────┼────────────────────────────────────────────┘
                  │ USB Serial (9600 baud, JSON)
┌─────────────────▼────────────────────────────────────────────┐
│                   Arduino UNO R3 (Body)                       │
│                                                               │
│  ┌─────────────────┐  ┌──────────────┐  ┌─────────────────┐ │
│  │ 2.42" SSD1309   │  │ NeoPixel     │  │ Passive Buzzer  │ │
│  │ OLED (128x64)   │  │ LED Ring     │  │                 │ │
│  │ Pet face sprites │  │ (12 LEDs)    │  │ Alert sounds    │ │
│  └─────────────────┘  │ Mood colors   │  └─────────────────┘ │
│                        └──────────────┘                       │
│  ┌─────────────────┐  ┌──────────────┐  ┌─────────────────┐ │
│  │ Vibration Motor │  │ Light Sensor │  │ Temp Sensor     │ │
│  │ Haptic alerts   │  │ (photoresist)│  │ (DHT11)         │ │
│  └─────────────────┘  └──────────────┘  └─────────────────┘ │
│                                                               │
│  ┌─────────────────┐                                         │
│  │ Push Button     │                                         │
│  │ Manual interact │                                         │
│  └─────────────────┘                                         │
└──────────────────────────────────────────────────────────────┘

External peripherals (connected to Pi):
- USB Webcam (mounted inside 3D case, pointed at user)
- USB Microphone
- Speaker + PAM8403 amplifier (3.5mm from Pi)
```

**Communication protocol (Pi → Arduino):**

JSON messages over USB serial at 9600 baud:

```json
{ "cmd": "face", "stage": 2, "emotion": "happy" }
{ "cmd": "leds", "color": [0, 255, 0], "mode": "solid" }
{ "cmd": "buzz", "pattern": "short" }
{ "cmd": "vibrate", "duration": 500 }
{ "cmd": "display_text", "line1": "Focus: 25m", "line2": "Stay strong!" }
```

Arduino → Pi (sensor readings):

```json
{ "sensor": "light", "value": 342 }
{ "sensor": "temp", "value": 22.5, "humidity": 45 }
{ "sensor": "button", "pressed": true }
```

---

## 4. Pet Life System

### 4.1 Growth Stages (Long-Term)

| Stage | Name | Cumulative Focus Time | Sprite Description |
|-------|------|-----------------------|--------------------|
| 0 | Egg | 0 min (start) | Wobbling egg |
| 1 | Hatchling | 15 min | Tiny blob with eyes |
| 2 | Kid | 1 hour | Small character with arms |
| 3 | Teen | 3 hours | Bigger, more detailed |
| 4 | Adult | 6 hours | Full character with accessories |

**XP system:**
- +1 XP per minute of good posture during a focus session
- -5 XP per posture violation event
- -10 XP per phone usage event
- Stage thresholds: 0 → 15 → 60 → 180 → 360 XP
- Devolution: dropping below threshold devolves the pet one stage

### 4.2 Emotional States (Short-Term)

| State | Trigger | OLED Face | LEDs | Sound |
|-------|---------|-----------|------|-------|
| Happy | Good posture, focused | Smile, bouncing | Green, solid | — |
| Neutral | Idle, no input | Relaxed, slow blink | White, dim | — |
| Concerned | Mild slouch (<5s) | Worried brows | Yellow, pulse | — |
| Sad | Sustained slouch (>5s) | Frown, tear | Blue, pulse | Soft buzzer |
| Angry | Phone detected (>3s) | Angry face, shaking | Red, flash | Loud buzzer + vibrate |
| Sleeping | Pomodoro break | Zzz, closed eyes | Dim white, breathe | Silence |
| Excited | Level up / milestone | Stars around face | Rainbow, cycle | Celebration chime |

### 4.3 Rule System

Users create rules via voice commands. The LLM interprets natural language and maps to structured rules:

**Rule structure:**
```json
{
  "id": "uuid",
  "type": "posture | phone | timer | custom",
  "description": "Don't let me go on my phone",
  "threshold": { "duration_seconds": 3 },
  "severity": "gentle | moderate | strict",
  "active": true,
  "created_at": "2026-03-28T14:00:00Z"
}
```

**Example voice commands → rules:**
- "Don't let me go on my phone" → `{ type: "phone", threshold: { duration_seconds: 3 }, severity: "strict" }`
- "Remind me to sit up straight" → `{ type: "posture", threshold: { duration_seconds: 5 }, severity: "gentle" }`
- "Start a 25-minute focus session" → `{ type: "timer", threshold: { duration_seconds: 1500 }, severity: "moderate" }`
- "No more than 3 phone checks per hour" → `{ type: "phone", threshold: { count: 3, period_seconds: 3600 }, severity: "moderate" }`

---

## 5. Voice Interaction Pipeline

```
[Always running] Mic → OpenWakeWord (local on Pi)
                        │
                        ▼ wake word detected ("Hey Buddy")
                  Pi plays "listening" chime
                  OLED shows listening face (big ear animation)
                        │
                        ▼
                  Record audio until 2s silence detected
                        │
                        ▼
                  Audio → STT API (Whisper API or Deepgram)
                        │
                        ▼
                  Text → LLM via Lava gateway
                     System prompt includes:
                     - Pet personality ("You are Buddy, a helpful and cute desk pet")
                     - Current mood, growth stage, health
                     - Active rules list
                     - Recent events (last 5 posture/phone events)
                     - Available actions: add_rule, remove_rule, start_timer, respond
                        │
                        ▼
                  LLM returns structured response:
                  { "action": "add_rule", "rule": {...}, "reply": "OK! I'll watch for that!" }
                        │
                        ▼
                  Reply text → ElevenLabs TTS (eleven_turbo_v2, streaming)
                        │
                        ▼
                  Audio stream → Speaker (via Pi 3.5mm + amp)
                  Action → Pet state manager → Serial command to Arduino
```

**Optimizations:**
- Pre-cache frequent phrases as local .mp3 files (saves API calls + eliminates latency):
  - "Good posture!"
  - "Hey, sit up straight!"
  - "Put your phone down!"
  - "Focus time! Let's go!"
  - "Break time! You earned it!"
  - "I'm getting sleepy..." (idle)
- ElevenLabs settings: stability 0.3-0.4 (expressive), similarity 0.6, turbo model
- STT: Deepgram preferred for speed (~300ms), Whisper API as fallback

---

## 6. Computer Vision Pipeline

**Running on Pi 4B as a continuous background process:**

```
USB Webcam (640x480) → Frame capture every 1 second
    │
    ▼
MediaPipe Pose Lite → 33 body landmarks
    │
    ├── Posture Analysis
    │   • Calculate angle: mid-shoulder to mid-hip vs vertical axis
    │   • Slouch threshold: >20 degrees from vertical
    │   • Head droop: nose-to-shoulder vertical distance ratio
    │   • Debounce: 5 seconds sustained before triggering POSTURE_BAD
    │   • Recovery: 3 seconds good posture → POSTURE_GOOD
    │
    ├── Phone Detection
    │   • Nose drops significantly below ear landmarks (head tilt down)
    │   • Wrist landmarks rise to chest/face level
    │   • Both conditions must be true simultaneously
    │   • Debounce: 3 seconds sustained before triggering PHONE_DETECTED
    │   • Recovery: wrist down + head up → PHONE_AWAY
    │
    └── Events emitted to Pet State Manager:
        POSTURE_GOOD | POSTURE_BAD | PHONE_DETECTED | PHONE_AWAY
```

**Resource usage:**
- MediaPipe Pose Lite at 1 FPS: ~15-20% CPU, ~300MB RAM
- No GPU on Pi — all CPU inference (Lite model is designed for this)
- Frame rate intentionally low — posture changes slowly

---

## 7. Dashboard (Web UI)

**Tech:** FastAPI (Python) + Jinja2 templates + vanilla JS + WebSocket for real-time updates

**URL:** `http://<pi-ip>:8080`

### 7.1 Live Status Page (Home)

- Large pet avatar (current growth stage + emotion)
- Health/XP bar with stage progress
- Active rules list with toggle switches
- Current status indicators: posture (good/bad), phone (away/detected)
- Active focus session timer (if running)

### 7.2 Rules Management

- Add rules via text form (backup to voice)
- Edit/delete existing rules
- Toggle rules on/off
- Severity slider per rule

### 7.3 Session History

- Today's total focus time
- Posture violation count
- Phone check count
- Growth progress visualization
- Simple bar chart of hourly activity

---

## 8. Environmental Awareness

**Light Sensor (Photoresistor):**
- Arduino reads analog value every 30 seconds
- Sends to Pi: `{ "sensor": "light", "value": 342 }`
- Pi thresholds: <200 = "too dark" → pet says "Turn on a light, I can barely see you!"
- Adds personality and demonstrates multi-sensor integration

**Temperature Sensor (DHT11):**
- Arduino reads every 30 seconds
- Sends to Pi: `{ "sensor": "temp", "value": 22.5, "humidity": 45 }`
- Pi thresholds: <18°C = "cold", >28°C = "hot"
- Pet comments: "Brrr, it's chilly! Grab a sweater!" or "It's warm in here, stay hydrated!"

---

## 9. Hardware Bill of Materials

### Must Buy

| Item | Purpose | Est. Cost |
|------|---------|-----------|
| 2.42" SSD1309 OLED (128x64, SPI) | Pet face display (large, visible) | ~$12-15 |
| NeoPixel LED ring (12 LEDs, WS2812B) | Mood lighting | ~$8 |
| Speaker + PAM8403 amplifier | Pet voice output | ~$5 |
| Vibration motor (coin type) | Haptic alerts | ~$2 |
| **Total** | | **~$27-30** |

### From Elegoo Super Starter Kit (No Cost)

| Item | Purpose |
|------|---------|
| Arduino UNO R3 | Physical I/O controller |
| Passive buzzer | Alert sounds |
| Photoresistor + 10K resistor | Light level sensing |
| DHT11 temperature sensor | Temperature/humidity |
| Push button + 10K resistor | Manual interaction |
| Breadboard + jumper wires | Prototyping connections |
| USB cable (A to B) | Pi ↔ Arduino serial |

### Already Owned

| Item | Purpose |
|------|---------|
| Raspberry Pi 4B | Main compute (CV, AI, web server) |
| USB Webcam | Posture/phone detection |
| USB Microphone | Wake word + voice commands |
| 3D Printer + filament | Custom case |

---

## 10. 3D Printed Case

**Design approach:**
- Two-part shell (front plate + back plate, snap-fit or screw mount)
- Character-shaped or BMO-style rectangular body
- Cutouts for: OLED display window, camera lens, speaker grill, USB ports, ventilation
- NeoPixel ring mounted behind translucent/perforated front section for glow effect
- Material: PLA (any fun color — blue-green for BMO, yellow for Tamagotchi)

**Sourcing:**
- Search Printables/Thingiverse for "BMO raspberry pi" or "tamagotchi case"
- Modify in TinkerCAD to fit exact component dimensions
- Print time: 3-6 hours at 0.2mm layer height, 15-20% infill

**Timeline:** Design and start printing the night before the hackathon. Minor modifications can be done day-of.

---

## 11. Snap Lens Studio Integration (Stretch Goal)

**Scope:** Standalone AR lens, no live Pi data connection required.

**Option A — Posture AR Overlay:**
- Snap lens uses body tracking to overlay a skeleton on the user
- Skeleton turns green when posture is good, red when slouching
- Uses Lens Studio's built-in body tracking (no external data needed)

**Option B — AR Pet on Desk:**
- Snap lens places a 3D pet character on a flat surface (desk) via surface tracking
- Pet idles, bounces, reacts to user's facial expressions (smile = pet dances)

**Effort:** ~4-6 hours for one person with Lens Studio tutorials.
**Submission:** Either option qualifies for Best use of Snap Lens Studio track.

---

## 12. Demo Flow (3-5 Minutes)

| Time | Segment | What Happens |
|------|---------|--------------|
| 0:00-0:30 | Intro | "Meet Buddy — an AI desk pet that keeps you productive and healthy" |
| 0:30-1:00 | Voice command | "Hey Buddy, don't let me go on my phone" → pet acknowledges with voice + face change + green LEDs |
| 1:00-1:45 | Posture demo | Slouch → pet gets sad → blue LEDs → buzzer → voice: "Sit up straight!" → fix posture → happy face + green LEDs |
| 1:45-2:15 | Phone demo | Pick up phone → angry face → red LEDs → vibration → voice: "Put that down!" → put phone away → relief animation |
| 2:15-2:45 | Pomodoro | "Hey Buddy, start a 25-minute focus session" → timer on display → show break notification |
| 2:45-3:15 | Dashboard | Pull up web dashboard on laptop → show live status, rules, session stats |
| 3:15-3:30 | Growth | Show evolution stages → explain long-term reward loop |
| 3:30-3:45 | Environment | Cover light sensor → pet says "Turn on a light!" → show temp reading |
| 3:45-4:00 | Close | "Buddy combines AI, computer vision, and hardware to make wellness fun and personal" |

---

## 13. Tech Stack Summary

| Layer | Technology |
|-------|-----------|
| Hardware brain | Raspberry Pi 4B (Python) |
| Hardware body | Arduino UNO R3 (C++/Arduino) |
| Display | 2.42" SSD1309 OLED (Adafruit GFX library) |
| LEDs | NeoPixel WS2812B (Adafruit NeoPixel library) |
| Wake word | OpenWakeWord (Python, local on Pi) |
| STT | Deepgram API (or Whisper API) |
| LLM | Via Lava API gateway |
| TTS | ElevenLabs (eleven_turbo_v2, streaming) |
| Computer vision | MediaPipe Pose Lite (Python, local on Pi) |
| Dashboard | FastAPI + Jinja2 + vanilla JS + WebSocket |
| Serial comm | PySerial (Pi) ↔ Arduino Serial library |
| Case | 3D printed PLA, modified from open-source STL |
