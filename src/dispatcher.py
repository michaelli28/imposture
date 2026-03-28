"""Arduino command dispatcher.

Translates pet state changes into serial commands for the Arduino body
(OLED face, NeoPixel LEDs, buzzer, vibration motor).
"""

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.serial_comm import SerialComm

logger = logging.getLogger(__name__)

EMOTION_LED_MAP: dict[str, tuple[tuple[int, int, int], str]] = {
    "happy":     ((0, 255, 0),    "solid"),
    "neutral":   ((255, 255, 255), "solid"),
    "concerned": ((255, 255, 0),  "pulse"),
    "sad":       ((0, 100, 255),  "pulse"),
    "angry":     ((255, 0, 0),    "flash"),
    "sleeping":  ((255, 255, 255), "breathe"),
    "excited":   ((0, 0, 0),      "rainbow"),
    "listening": ((0, 200, 255),  "pulse"),
}

EMOTION_BUZZ_MAP: dict[str, str | None] = {
    "happy":     None,
    "neutral":   None,
    "concerned": None,
    "sad":       "short",
    "angry":     "long",
    "sleeping":  None,
    "excited":   "celebration",
    "listening": None,
}

EMOTION_VIBRATE_MAP: dict[str, int] = {
    "angry": 500,
}


class Dispatcher:
    """Translates pet state into Arduino serial commands."""

    def __init__(self, serial_comm: "SerialComm") -> None:
        self._serial = serial_comm
        self._current_emotion: str = ""
        self._current_stage: int = -1

    def update_emotion(self, stage: int, emotion: str) -> None:
        """Send face, LED, buzzer, and vibration commands for the given emotion."""
        face_changed = emotion != self._current_emotion or stage != self._current_stage
        self._current_emotion = emotion
        self._current_stage = stage

        if face_changed:
            self._serial.send_face(stage, emotion)
            logger.info("Dispatched face: stage=%d emotion=%s", stage, emotion)

        led_color, led_mode = EMOTION_LED_MAP.get(emotion, ((255, 255, 255), "solid"))
        self._serial.send_leds(*led_color, led_mode)

        buzz_pattern = EMOTION_BUZZ_MAP.get(emotion)
        if buzz_pattern is not None:
            self._serial.send_buzz(buzz_pattern)

        vibrate_ms = EMOTION_VIBRATE_MAP.get(emotion, 0)
        if vibrate_ms > 0:
            self._serial.send_vibrate(vibrate_ms)

    def show_text(self, line1: str, line2: str = "") -> None:
        """Display text on the OLED."""
        self._serial.send_text(line1, line2)

    def celebrate(self) -> None:
        """Play a celebration sequence for stage evolution."""
        self._serial.send_leds(0, 0, 0, "rainbow")
        self._serial.send_buzz("celebration")

    def alert_posture(self, severity: str) -> None:
        """Posture-specific alert based on rule severity."""
        if severity == "gentle":
            self._serial.send_buzz("short")
        elif severity == "moderate":
            self._serial.send_buzz("long")
            self._serial.send_leds(0, 100, 255, "pulse")
        else:  # strict
            self._serial.send_buzz("long")
            self._serial.send_vibrate(300)
            self._serial.send_leds(0, 100, 255, "flash")

    def alert_phone(self, severity: str) -> None:
        """Phone-specific alert based on rule severity."""
        if severity == "gentle":
            self._serial.send_buzz("short")
            self._serial.send_leds(255, 100, 0, "pulse")
        elif severity == "moderate":
            self._serial.send_buzz("long")
            self._serial.send_vibrate(500)
            self._serial.send_leds(255, 0, 0, "flash")
        else:  # strict
            self._serial.send_buzz("long")
            self._serial.send_vibrate(800)
            self._serial.send_leds(255, 0, 0, "flash")
