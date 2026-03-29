// Wamm AI Desk Pet - Arduino UNO R3 Firmware
// Controlled by Raspberry Pi via USB Serial (9600 baud, JSON messages)
// Display: 16x2 character LCD (LiquidCrystal, parallel interface)

#include <LiquidCrystal.h>
#include <Adafruit_NeoPixel.h>

// ---------------------------------------------------------------------------
// Pin definitions
// ---------------------------------------------------------------------------
// LCD pins: RS=12, E=11, D4=5, D5=4, D6=3, D7=2
#define LCD_RS 12
#define LCD_E  11
#define LCD_D4  5
#define LCD_D5  4
#define LCD_D6  3
#define LCD_D7  2

#define NEOPIXEL_PIN   6
#define NEOPIXEL_COUNT 12

#define BUZZER_PIN     9
#define VIBRATE_PIN    8
#define BUTTON_PIN     7
#define PHOTO_PIN      A0

// ---------------------------------------------------------------------------
// Display (16 columns x 2 rows)
// ---------------------------------------------------------------------------
LiquidCrystal lcd(LCD_RS, LCD_E, LCD_D4, LCD_D5, LCD_D6, LCD_D7);

// ---------------------------------------------------------------------------
// NeoPixel
// ---------------------------------------------------------------------------
Adafruit_NeoPixel strip(NEOPIXEL_COUNT, NEOPIXEL_PIN, NEO_GRB + NEO_KHZ800);

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
int16_t  ledPulseVal     = 0;
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
char    faceEmotion[16] = "neutral";
bool    faceTextMode = false;
char    textLine1[17] = "";
char    textLine2[17] = "";

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

  lcd.begin(16, 2);
  lcd.clear();

  strip.begin();
  strip.setBrightness(50);
  strip.show();

  drawFace(faceEmotion);
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

// Extract a JSON string value for a given key into dst. Returns false if not found.
bool jsonStr(const char* json, const char* key, char* dst, uint8_t maxLen) {
  char needle[32];
  snprintf(needle, sizeof(needle), "\"%s\":\"", key);
  const char* p = strstr(json, needle);
  if (!p) return false;
  p += strlen(needle);
  uint8_t i = 0;
  while (*p && *p != '"' && i < maxLen - 1) dst[i++] = *p++;
  dst[i] = '\0';
  return true;
}

// Extract a JSON integer value for a given key. Returns defaultVal if not found.
long jsonInt(const char* json, const char* key, long defaultVal) {
  char needle[32];
  snprintf(needle, sizeof(needle), "\"%s\":", key);
  const char* p = strstr(json, needle);
  if (!p) return defaultVal;
  p += strlen(needle);
  while (*p == ' ') p++;
  if (*p == '"' || *p == '{' || *p == '[') return defaultVal;
  return strtol(p, NULL, 10);
}

// Extract a JSON array of 3 ints: "key":[r,g,b]
bool jsonArr3(const char* json, const char* key, uint8_t* r, uint8_t* g, uint8_t* b) {
  char needle[32];
  snprintf(needle, sizeof(needle), "\"%s\":[", key);
  const char* p = strstr(json, needle);
  if (!p) return false;
  p += strlen(needle);
  *r = (uint8_t)strtol(p, (char**)&p, 10); if (*p == ',') p++;
  *g = (uint8_t)strtol(p, (char**)&p, 10); if (*p == ',') p++;
  *b = (uint8_t)strtol(p, NULL, 10);
  return true;
}

void processCommand(const char* json) {
  char val[32];

  if (!jsonStr(json, "cmd", val, sizeof(val))) return;

  if (strcmp(val, "face") == 0) {
    if (!jsonStr(json, "emotion", faceEmotion, sizeof(faceEmotion)))
      strlcpy(faceEmotion, "neutral", sizeof(faceEmotion));
    faceTextMode = false;
    drawFace(faceEmotion);
  }
  else if (strcmp(val, "leds") == 0) {
    jsonArr3(json, "color", &ledR, &ledG, &ledB);
    char mode[12];
    if (jsonStr(json, "mode", mode, sizeof(mode))) {
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
  else if (strcmp(val, "buzz") == 0) {
    char pattern[16];
    if (jsonStr(json, "pattern", pattern, sizeof(pattern))) {
      if (strcmp(pattern, "short") == 0)           startBuzz(BUZZ_SHORT);
      else if (strcmp(pattern, "long") == 0)       startBuzz(BUZZ_LONG);
      else if (strcmp(pattern, "celebration") == 0) startBuzz(BUZZ_CELE_1);
    }
  }
  else if (strcmp(val, "vibrate") == 0) {
    vibrateDurMs   = jsonInt(json, "duration", 500);
    vibrateStartMs = millis();
    vibrateActive  = true;
    digitalWrite(VIBRATE_PIN, HIGH);
  }
  else if (strcmp(val, "display_text") == 0) {
    if (!jsonStr(json, "line1", textLine1, sizeof(textLine1))) textLine1[0] = '\0';
    if (!jsonStr(json, "line2", textLine2, sizeof(textLine2))) textLine2[0] = '\0';
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
// LCD display helpers
// ===========================================================================

// Center a string on a 16-char line
void lcdPrintCentered(uint8_t row, const char* text) {
  lcd.setCursor(0, row);
  lcd.print(F("                ")); // clear row
  uint8_t len = strlen(text);
  uint8_t pad = (len < 16) ? (16 - len) / 2 : 0;
  lcd.setCursor(pad, row);
  lcd.print(text);
}

void drawText(const char* line1, const char* line2) {
  lcdPrintCentered(0, line1);
  lcdPrintCentered(1, line2);
}

// ===========================================================================
// Face rendering on 16x2 LCD
// ===========================================================================
void drawFace(const char* emotion) {
  const char* face;
  const char* label;

  if (strcmp(emotion, "happy") == 0)          { face = "(^_^)"; label = "Happy!"; }
  else if (strcmp(emotion, "sad") == 0)       { face = "(T_T)"; label = "Sad..."; }
  else if (strcmp(emotion, "angry") == 0)     { face = "(>_<) Angry!"; label = "Phone Away!"; }
  else if (strcmp(emotion, "concerned") == 0) { face = "(o_o)?"; label = "Concerned"; }
  else if (strcmp(emotion, "sleeping") == 0)  { face = "(-_-) Zzz"; label = "Sleeping"; }
  else if (strcmp(emotion, "excited") == 0)   { face = "(*_*)!"; label = "Excited!"; }
  else if (strcmp(emotion, "listening") == 0) { face = "(o_o)~"; label = "Listening"; }
  else                                       { face = "(o_o)"; label = "Neutral"; }

  lcdPrintCentered(0, face);
  lcdPrintCentered(1, label);
}
