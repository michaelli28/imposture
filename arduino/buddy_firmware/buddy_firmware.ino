// Buddy AI Desk Pet - Arduino UNO R3 Firmware
// Controlled by Raspberry Pi via USB Serial (9600 baud, JSON messages)

#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <Adafruit_NeoPixel.h>
#include <ArduinoJson.h>
#include <DHT.h>

// ---------------------------------------------------------------------------
// Pin definitions
// ---------------------------------------------------------------------------
#define OLED_CLK   13
#define OLED_MOSI  11
#define OLED_CS    10
#define OLED_DC     9
#define OLED_RST    8

#define NEOPIXEL_PIN   6
#define NEOPIXEL_COUNT 12

#define BUZZER_PIN     5
#define DHT_PIN        4
#define VIBRATE_PIN    3
#define BUTTON_PIN     2
#define PHOTO_PIN      A0

// ---------------------------------------------------------------------------
// Display
// ---------------------------------------------------------------------------
#define SCREEN_W 128
#define SCREEN_H  64

Adafruit_SSD1306 display(SCREEN_W, SCREEN_H,
                         OLED_MOSI, OLED_CLK, OLED_DC, OLED_RST, OLED_CS);

// ---------------------------------------------------------------------------
// NeoPixel
// ---------------------------------------------------------------------------
Adafruit_NeoPixel strip(NEOPIXEL_COUNT, NEOPIXEL_PIN, NEO_GRB + NEO_KHZ800);

// ---------------------------------------------------------------------------
// DHT sensor
// ---------------------------------------------------------------------------
DHT dht(DHT_PIN, DHT11);

// ---------------------------------------------------------------------------
// LED animation state
// ---------------------------------------------------------------------------
enum LedMode { LED_OFF, LED_SOLID, LED_FLASH, LED_PULSE, LED_BREATHE, LED_RAINBOW };

LedMode  ledMode        = LED_OFF;
uint8_t  ledR            = 0;
uint8_t  ledG            = 0;
uint8_t  ledB            = 0;
unsigned long ledPrevMs  = 0;
bool     ledFlashOn      = false;
uint8_t  ledPulseVal     = 0;
int8_t   ledPulseDir     = 1;
uint16_t ledRainbowHue   = 0;

// ---------------------------------------------------------------------------
// Buzzer state (non-blocking)
// ---------------------------------------------------------------------------
enum BuzzState { BUZZ_IDLE, BUZZ_SHORT, BUZZ_LONG, BUZZ_CELE_1, BUZZ_CELE_2, BUZZ_CELE_3 };

BuzzState    buzzState    = BUZZ_IDLE;
unsigned long buzzStartMs = 0;

// ---------------------------------------------------------------------------
// Vibration state
// ---------------------------------------------------------------------------
bool         vibrateActive   = false;
unsigned long vibrateStartMs = 0;
unsigned long vibrateDurMs   = 0;

// ---------------------------------------------------------------------------
// Button debounce
// ---------------------------------------------------------------------------
bool         lastButtonState   = HIGH;
bool         buttonState       = HIGH;
unsigned long lastDebounceMs   = 0;
const unsigned long debounceMs = 50;
bool         buttonEventSent   = false;

// ---------------------------------------------------------------------------
// Sensor reporting interval
// ---------------------------------------------------------------------------
const unsigned long sensorIntervalMs = 30000;
unsigned long lastSensorMs           = 0;

// ---------------------------------------------------------------------------
// Serial input buffer
// ---------------------------------------------------------------------------
char serialBuf[256];
uint8_t serialBufIdx = 0;

// ---------------------------------------------------------------------------
// Current face state
// ---------------------------------------------------------------------------
uint8_t faceStage = 2;
String  faceEmotion = "neutral";
bool    faceTextMode = false;
String  textLine1 = "";
String  textLine2 = "";

// ===========================================================================
// Setup
// ===========================================================================
void setup() {
  Serial.begin(9600);

  pinMode(BUZZER_PIN, OUTPUT);
  pinMode(VIBRATE_PIN, OUTPUT);
  pinMode(BUTTON_PIN, INPUT_PULLUP);
  pinMode(PHOTO_PIN, INPUT);

  digitalWrite(BUZZER_PIN, LOW);
  digitalWrite(VIBRATE_PIN, LOW);

  if (!display.begin(SSD1306_SWITCHCAPVCC)) {
    Serial.println(F("{\"error\":\"OLED init failed\"}"));
  }
  display.clearDisplay();
  display.display();

  strip.begin();
  strip.setBrightness(50);
  strip.show();

  dht.begin();

  drawFace(faceStage, faceEmotion);
}

// ===========================================================================
// Main loop
// ===========================================================================
void loop() {
  unsigned long now = millis();

  readSerial();
  updateButton(now);
  updateLeds(now);
  updateBuzzer(now);
  updateVibrate(now);
  reportSensors(now);
}

// ===========================================================================
// Serial command processing
// ===========================================================================
void readSerial() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n' || c == '\r') {
      if (serialBufIdx > 0) {
        serialBuf[serialBufIdx] = '\0';
        processCommand(serialBuf);
        serialBufIdx = 0;
      }
    } else if (serialBufIdx < sizeof(serialBuf) - 1) {
      serialBuf[serialBufIdx++] = c;
    }
  }
}

void processCommand(const char* json) {
  StaticJsonDocument<256> doc;
  DeserializationError err = deserializeJson(doc, json);
  if (err) {
    return;
  }

  const char* cmd = doc["cmd"];
  if (!cmd) return;

  if (strcmp(cmd, "face") == 0) {
    faceStage   = doc["stage"] | 2;
    faceEmotion = doc["emotion"] | "neutral";
    faceTextMode = false;
    drawFace(faceStage, faceEmotion);
  }
  else if (strcmp(cmd, "leds") == 0) {
    JsonArray color = doc["color"];
    if (color) {
      ledR = color[0];
      ledG = color[1];
      ledB = color[2];
    }
    const char* mode = doc["mode"];
    if (mode) {
      if (strcmp(mode, "solid") == 0)        ledMode = LED_SOLID;
      else if (strcmp(mode, "flash") == 0)   ledMode = LED_FLASH;
      else if (strcmp(mode, "pulse") == 0)   ledMode = LED_PULSE;
      else if (strcmp(mode, "breathe") == 0) ledMode = LED_BREATHE;
      else if (strcmp(mode, "rainbow") == 0) ledMode = LED_RAINBOW;
      else                                   ledMode = LED_OFF;
    }
    ledPulseVal = 0;
    ledPulseDir = 1;
    ledFlashOn  = false;
    ledPrevMs   = millis();
    applyLeds();
  }
  else if (strcmp(cmd, "buzz") == 0) {
    const char* pattern = doc["pattern"];
    if (pattern) {
      if (strcmp(pattern, "short") == 0)           startBuzz(BUZZ_SHORT);
      else if (strcmp(pattern, "long") == 0)       startBuzz(BUZZ_LONG);
      else if (strcmp(pattern, "celebration") == 0) startBuzz(BUZZ_CELE_1);
    }
  }
  else if (strcmp(cmd, "vibrate") == 0) {
    vibrateDurMs   = doc["duration"] | 500;
    vibrateStartMs = millis();
    vibrateActive  = true;
    digitalWrite(VIBRATE_PIN, HIGH);
  }
  else if (strcmp(cmd, "display_text") == 0) {
    textLine1    = doc["line1"] | "";
    textLine2    = doc["line2"] | "";
    faceTextMode = true;
    drawText(textLine1, textLine2);
  }
}

// ===========================================================================
// Button handling (debounced, immediate event on press)
// ===========================================================================
void updateButton(unsigned long now) {
  bool reading = digitalRead(BUTTON_PIN);

  if (reading != lastButtonState) {
    lastDebounceMs = now;
    buttonEventSent = false;
  }

  if ((now - lastDebounceMs) >= debounceMs) {
    if (reading != buttonState) {
      buttonState = reading;
      if (buttonState == LOW && !buttonEventSent) {
        Serial.println(F("{\"sensor\":\"button\",\"pressed\":true}"));
        buttonEventSent = true;
      }
    }
  }

  lastButtonState = reading;
}

// ===========================================================================
// Sensor reporting (every 30 seconds)
// ===========================================================================
void reportSensors(unsigned long now) {
  if (now - lastSensorMs < sensorIntervalMs) return;
  lastSensorMs = now;

  int lightVal = analogRead(PHOTO_PIN);
  Serial.print(F("{\"sensor\":\"light\",\"value\":"));
  Serial.print(lightVal);
  Serial.println(F("}"));

  float temp = dht.readTemperature();
  float hum  = dht.readHumidity();
  if (!isnan(temp) && !isnan(hum)) {
    Serial.print(F("{\"sensor\":\"temp\",\"value\":"));
    Serial.print(temp, 1);
    Serial.print(F(",\"humidity\":"));
    Serial.print(hum, 1);
    Serial.println(F("}"));
  }
}

// ===========================================================================
// LED animations (non-blocking)
// ===========================================================================
void updateLeds(unsigned long now) {
  switch (ledMode) {
    case LED_OFF:
      break;

    case LED_SOLID:
      break;

    case LED_FLASH:
      if (now - ledPrevMs >= 200) {
        ledPrevMs  = now;
        ledFlashOn = !ledFlashOn;
        applyLeds();
      }
      break;

    case LED_PULSE:
      if (now - ledPrevMs >= 15) {
        ledPrevMs = now;
        ledPulseVal += 3 * ledPulseDir;
        if (ledPulseVal >= 255) { ledPulseVal = 255; ledPulseDir = -1; }
        if (ledPulseVal <= 0)   { ledPulseVal = 0;   ledPulseDir =  1; }
        applyLeds();
      }
      break;

    case LED_BREATHE:
      if (now - ledPrevMs >= 40) {
        ledPrevMs = now;
        ledPulseVal += 2 * ledPulseDir;
        if (ledPulseVal >= 255) { ledPulseVal = 255; ledPulseDir = -1; }
        if (ledPulseVal <= 0)   { ledPulseVal = 0;   ledPulseDir =  1; }
        applyLeds();
      }
      break;

    case LED_RAINBOW:
      if (now - ledPrevMs >= 30) {
        ledPrevMs = now;
        ledRainbowHue += 512;
        for (int i = 0; i < NEOPIXEL_COUNT; i++) {
          uint16_t pixelHue = ledRainbowHue + (i * 65536L / NEOPIXEL_COUNT);
          strip.setPixelColor(i, strip.gamma32(strip.ColorHSV(pixelHue)));
        }
        strip.show();
      }
      break;
  }
}

void applyLeds() {
  switch (ledMode) {
    case LED_OFF:
      strip.clear();
      break;

    case LED_SOLID:
      for (int i = 0; i < NEOPIXEL_COUNT; i++) {
        strip.setPixelColor(i, strip.Color(ledR, ledG, ledB));
      }
      break;

    case LED_FLASH:
      for (int i = 0; i < NEOPIXEL_COUNT; i++) {
        if (ledFlashOn) strip.setPixelColor(i, strip.Color(ledR, ledG, ledB));
        else            strip.setPixelColor(i, 0);
      }
      break;

    case LED_PULSE:
    case LED_BREATHE: {
      uint8_t r = (uint16_t)ledR * ledPulseVal / 255;
      uint8_t g = (uint16_t)ledG * ledPulseVal / 255;
      uint8_t b = (uint16_t)ledB * ledPulseVal / 255;
      for (int i = 0; i < NEOPIXEL_COUNT; i++) {
        strip.setPixelColor(i, strip.Color(r, g, b));
      }
      break;
    }

    case LED_RAINBOW:
      break;
  }
  strip.show();
}

// ===========================================================================
// Buzzer (non-blocking state machine)
// ===========================================================================
void startBuzz(BuzzState state) {
  buzzState   = state;
  buzzStartMs = millis();

  switch (state) {
    case BUZZ_SHORT:  tone(BUZZER_PIN, 1000); break;
    case BUZZ_LONG:   tone(BUZZER_PIN, 1000); break;
    case BUZZ_CELE_1: tone(BUZZER_PIN,  523); break;
    case BUZZ_CELE_2: tone(BUZZER_PIN,  659); break;
    case BUZZ_CELE_3: tone(BUZZER_PIN,  784); break;
    default: break;
  }
}

void updateBuzzer(unsigned long now) {
  if (buzzState == BUZZ_IDLE) return;

  unsigned long elapsed = now - buzzStartMs;

  switch (buzzState) {
    case BUZZ_SHORT:
      if (elapsed >= 100) { noTone(BUZZER_PIN); buzzState = BUZZ_IDLE; }
      break;

    case BUZZ_LONG:
      if (elapsed >= 500) { noTone(BUZZER_PIN); buzzState = BUZZ_IDLE; }
      break;

    case BUZZ_CELE_1:
      if (elapsed >= 150) { noTone(BUZZER_PIN); startBuzz(BUZZ_CELE_2); }
      break;

    case BUZZ_CELE_2:
      if (elapsed >= 150) { noTone(BUZZER_PIN); startBuzz(BUZZ_CELE_3); }
      break;

    case BUZZ_CELE_3:
      if (elapsed >= 300) { noTone(BUZZER_PIN); buzzState = BUZZ_IDLE; }
      break;

    default:
      break;
  }
}

// ===========================================================================
// Vibration motor (non-blocking)
// ===========================================================================
void updateVibrate(unsigned long now) {
  if (vibrateActive && (now - vibrateStartMs >= vibrateDurMs)) {
    digitalWrite(VIBRATE_PIN, LOW);
    vibrateActive = false;
  }
}

// ===========================================================================
// Text display
// ===========================================================================
void drawText(const String& line1, const String& line2) {
  display.clearDisplay();
  display.setTextSize(2);
  display.setTextColor(SSD1306_WHITE);

  int16_t x1, y1;
  uint16_t w1, h1;
  display.getTextBounds(line1, 0, 0, &x1, &y1, &w1, &h1);
  display.setCursor((SCREEN_W - w1) / 2, 10);
  display.print(line1);

  display.getTextBounds(line2, 0, 0, &x1, &y1, &w1, &h1);
  display.setCursor((SCREEN_W - w1) / 2, 38);
  display.print(line2);

  display.display();
}

// ===========================================================================
// Face rendering with GFX primitives
// ===========================================================================

// Eye size scales with evolution stage (0=egg, 4=fully evolved)
uint8_t eyeRadius(uint8_t stage) {
  const uint8_t radii[] = {3, 5, 6, 7, 8};
  return (stage <= 4) ? radii[stage] : radii[4];
}

// Mouth width scales with stage
uint8_t mouthWidth(uint8_t stage) {
  const uint8_t widths[] = {6, 10, 14, 18, 22};
  return (stage <= 4) ? widths[stage] : widths[4];
}

void drawFace(uint8_t stage, const String& emotion) {
  display.clearDisplay();

  // Stage 0: egg -- just an oval with simple face
  if (stage == 0) {
    drawEggFace(emotion);
    display.display();
    return;
  }

  int16_t cx = SCREEN_W / 2;
  int16_t cy = SCREEN_H / 2;
  uint8_t er = eyeRadius(stage);
  uint8_t mw = mouthWidth(stage);
  int16_t eyeSpacing = er + 6 + stage;
  int16_t leftEyeX  = cx - eyeSpacing;
  int16_t rightEyeX = cx + eyeSpacing;
  int16_t eyeY      = cy - 6 - stage;
  int16_t mouthY    = cy + 8 + stage;

  if (emotion == "happy") {
    drawEyes(leftEyeX, rightEyeX, eyeY, er, true);
    drawSmile(cx, mouthY, mw);
    drawCheeks(leftEyeX - er - 2, rightEyeX + er + 2, eyeY + er, 2);
  }
  else if (emotion == "sad") {
    drawEyes(leftEyeX, rightEyeX, eyeY, er, false);
    drawFrown(cx, mouthY, mw);
    drawTearDrop(rightEyeX, eyeY + er + 2);
  }
  else if (emotion == "angry") {
    drawAngryEyes(leftEyeX, rightEyeX, eyeY, er);
    drawFrown(cx, mouthY, mw / 2);
  }
  else if (emotion == "concerned") {
    drawEyes(leftEyeX, rightEyeX, eyeY, er, false);
    drawWavyMouth(cx, mouthY, mw);
    drawSweatDrop(rightEyeX + er + 3, eyeY - er);
  }
  else if (emotion == "sleeping") {
    drawSleepingEyes(leftEyeX, rightEyeX, eyeY, er);
    drawSleepMouth(cx, mouthY);
    drawZzz(cx + 25, cy - 20);
  }
  else if (emotion == "excited") {
    drawStarEyes(leftEyeX, rightEyeX, eyeY, er);
    drawBigSmile(cx, mouthY, mw);
    drawSparkles(cx, cy);
  }
  else if (emotion == "listening") {
    drawEyes(leftEyeX, rightEyeX, eyeY, er, false);
    drawListenMouth(cx, mouthY);
    drawSoundWaves(cx + 30, cy);
  }
  else {
    // neutral
    drawEyes(leftEyeX, rightEyeX, eyeY, er, false);
    drawNeutralMouth(cx, mouthY, mw);
  }

  display.display();
}

// ---------------------------------------------------------------------------
// Eye drawing helpers
// ---------------------------------------------------------------------------
void drawEyes(int16_t lx, int16_t rx, int16_t y, uint8_t r, bool happy) {
  if (happy) {
    // Upward arc eyes (happy squint)
    for (int8_t offset = -1; offset <= 1; offset++) {
      display.drawCircleHelper(lx, y + r / 2 + offset, r, 0x03, SSD1306_WHITE);
      display.drawCircleHelper(rx, y + r / 2 + offset, r, 0x03, SSD1306_WHITE);
    }
  } else {
    // Normal round eyes with pupils
    display.drawCircle(lx, y, r, SSD1306_WHITE);
    display.drawCircle(rx, y, r, SSD1306_WHITE);
    display.fillCircle(lx + 1, y, r / 2, SSD1306_WHITE);
    display.fillCircle(rx + 1, y, r / 2, SSD1306_WHITE);
  }
}

void drawAngryEyes(int16_t lx, int16_t rx, int16_t y, uint8_t r) {
  display.fillCircle(lx, y, r, SSD1306_WHITE);
  display.fillCircle(rx, y, r, SSD1306_WHITE);
  // Angry eyebrow lines
  display.drawLine(lx - r - 2, y - r - 4, lx + r, y - r + 1, SSD1306_WHITE);
  display.drawLine(rx - r, y - r + 1, rx + r + 2, y - r - 4, SSD1306_WHITE);
  // Cut out top of eyes for angry look (black triangles)
  display.fillTriangle(lx - r - 1, y - r - 1, lx + r + 1, y - r - 1,
                       lx + r + 1, y - r / 2, SSD1306_BLACK);
  display.fillTriangle(rx - r - 1, y - r - 1, rx + r + 1, y - r - 1,
                       rx - r - 1, y - r / 2, SSD1306_BLACK);
}

void drawSleepingEyes(int16_t lx, int16_t rx, int16_t y, uint8_t r) {
  // Closed eyes -- horizontal lines
  display.drawLine(lx - r, y, lx + r, y, SSD1306_WHITE);
  display.drawLine(rx - r, y, rx + r, y, SSD1306_WHITE);
  // Small lashes
  display.drawLine(lx - r, y, lx - r + 2, y + 2, SSD1306_WHITE);
  display.drawLine(lx + r, y, lx + r - 2, y + 2, SSD1306_WHITE);
  display.drawLine(rx - r, y, rx - r + 2, y + 2, SSD1306_WHITE);
  display.drawLine(rx + r, y, rx + r - 2, y + 2, SSD1306_WHITE);
}

void drawStarEyes(int16_t lx, int16_t rx, int16_t y, uint8_t r) {
  drawStar(lx, y, r);
  drawStar(rx, y, r);
}

void drawStar(int16_t cx, int16_t cy, uint8_t r) {
  // Simple 4-point star
  display.drawLine(cx, cy - r, cx, cy + r, SSD1306_WHITE);
  display.drawLine(cx - r, cy, cx + r, cy, SSD1306_WHITE);
  uint8_t d = r * 7 / 10;
  display.drawLine(cx - d, cy - d, cx + d, cy + d, SSD1306_WHITE);
  display.drawLine(cx + d, cy - d, cx - d, cy + d, SSD1306_WHITE);
  display.fillCircle(cx, cy, r / 3, SSD1306_WHITE);
}

// ---------------------------------------------------------------------------
// Mouth drawing helpers
// ---------------------------------------------------------------------------
void drawSmile(int16_t cx, int16_t cy, uint8_t w) {
  // Upward curve
  for (int8_t i = -1; i <= 1; i++) {
    display.drawCircleHelper(cx, cy - w / 3 + i, w / 2, 0x08, SSD1306_WHITE);
    display.drawCircleHelper(cx, cy - w / 3 + i, w / 2, 0x04, SSD1306_WHITE);
  }
}

void drawBigSmile(int16_t cx, int16_t cy, uint8_t w) {
  // Wide open smile
  display.fillCircle(cx, cy, w / 3, SSD1306_WHITE);
  display.fillRect(cx - w / 3, cy - w / 3, w * 2 / 3, w / 3, SSD1306_BLACK);
}

void drawFrown(int16_t cx, int16_t cy, uint8_t w) {
  // Downward curve
  for (int8_t i = -1; i <= 1; i++) {
    display.drawCircleHelper(cx, cy + w / 3 + i, w / 2, 0x01, SSD1306_WHITE);
    display.drawCircleHelper(cx, cy + w / 3 + i, w / 2, 0x02, SSD1306_WHITE);
  }
}

void drawNeutralMouth(int16_t cx, int16_t cy, uint8_t w) {
  display.drawLine(cx - w / 2, cy, cx + w / 2, cy, SSD1306_WHITE);
}

void drawWavyMouth(int16_t cx, int16_t cy, uint8_t w) {
  int16_t startX = cx - w / 2;
  for (int16_t x = startX; x < startX + w; x += 4) {
    int16_t y1 = cy + ((x - startX) % 8 < 4 ? -2 : 2);
    int16_t y2 = cy + (((x + 2) - startX) % 8 < 4 ? -2 : 2);
    display.drawLine(x, y1, x + 2, y2, SSD1306_WHITE);
  }
}

void drawSleepMouth(int16_t cx, int16_t cy) {
  // Small 'o' for sleeping
  display.drawCircle(cx, cy, 3, SSD1306_WHITE);
}

void drawListenMouth(int16_t cx, int16_t cy) {
  // Small open circle (attentive)
  display.drawCircle(cx, cy + 2, 4, SSD1306_WHITE);
  display.fillCircle(cx, cy + 2, 2, SSD1306_WHITE);
}

// ---------------------------------------------------------------------------
// Decorative elements
// ---------------------------------------------------------------------------
void drawCheeks(int16_t lx, int16_t rx, int16_t y, uint8_t r) {
  display.drawCircle(lx, y, r, SSD1306_WHITE);
  display.drawCircle(rx, y, r, SSD1306_WHITE);
}

void drawTearDrop(int16_t x, int16_t y) {
  display.fillCircle(x, y + 4, 2, SSD1306_WHITE);
  display.drawLine(x, y, x - 1, y + 3, SSD1306_WHITE);
  display.drawLine(x, y, x + 1, y + 3, SSD1306_WHITE);
}

void drawSweatDrop(int16_t x, int16_t y) {
  display.drawCircle(x, y + 3, 2, SSD1306_WHITE);
  display.drawLine(x, y, x, y + 1, SSD1306_WHITE);
}

void drawZzz(int16_t x, int16_t y) {
  display.setTextSize(1);
  display.setTextColor(SSD1306_WHITE);
  display.setCursor(x, y);
  display.print(F("Z"));
  display.setCursor(x + 5, y - 7);
  display.print(F("z"));
  display.setCursor(x + 9, y - 12);
  display.print(F("z"));
}

void drawSparkles(int16_t cx, int16_t cy) {
  // Small crosses around the face
  int16_t pts[][2] = {{cx - 30, cy - 22}, {cx + 30, cy - 22},
                      {cx - 34, cy + 10}, {cx + 34, cy + 10}};
  for (uint8_t i = 0; i < 4; i++) {
    int16_t px = pts[i][0];
    int16_t py = pts[i][1];
    display.drawLine(px - 2, py, px + 2, py, SSD1306_WHITE);
    display.drawLine(px, py - 2, px, py + 2, SSD1306_WHITE);
  }
}

void drawSoundWaves(int16_t x, int16_t cy) {
  display.drawCircleHelper(x, cy, 5, 0x06, SSD1306_WHITE);
  display.drawCircleHelper(x, cy, 9, 0x06, SSD1306_WHITE);
  display.drawCircleHelper(x, cy, 13, 0x06, SSD1306_WHITE);
}

// ---------------------------------------------------------------------------
// Egg face (stage 0)
// ---------------------------------------------------------------------------
void drawEggFace(const String& emotion) {
  int16_t cx = SCREEN_W / 2;
  int16_t cy = SCREEN_H / 2;

  // Egg outline
  display.drawRoundRect(cx - 16, cy - 22, 32, 44, 14, SSD1306_WHITE);

  // Tiny eyes
  display.fillCircle(cx - 5, cy - 4, 2, SSD1306_WHITE);
  display.fillCircle(cx + 5, cy - 4, 2, SSD1306_WHITE);

  if (emotion == "happy") {
    display.drawPixel(cx - 1, cy + 5, SSD1306_WHITE);
    display.drawPixel(cx,     cy + 6, SSD1306_WHITE);
    display.drawPixel(cx + 1, cy + 5, SSD1306_WHITE);
  } else if (emotion == "sleeping") {
    // Closed eyes
    display.fillCircle(cx - 5, cy - 4, 2, SSD1306_BLACK);
    display.fillCircle(cx + 5, cy - 4, 2, SSD1306_BLACK);
    display.drawLine(cx - 7, cy - 4, cx - 3, cy - 4, SSD1306_WHITE);
    display.drawLine(cx + 3, cy - 4, cx + 7, cy - 4, SSD1306_WHITE);
    drawZzz(cx + 14, cy - 10);
  } else {
    // neutral dot mouth
    display.drawPixel(cx, cy + 5, SSD1306_WHITE);
  }
}
