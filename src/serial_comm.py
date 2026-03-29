"""Serial communication between Raspberry Pi and Arduino for Buddy AI Desk Pet.

Handles bidirectional JSON-over-serial messaging: sends face/LED/buzzer
commands to the Arduino and reads sensor data (light, temperature, button)
back, emitting events via the EventBus.
"""

from __future__ import annotations

import glob
import json
import logging
import os
import threading
import time
from typing import Any

import serial
from dotenv import load_dotenv

from src.events import Event, EventBus, EventType

load_dotenv()

logger = logging.getLogger(__name__)

DEFAULT_PORT: str = os.getenv("SERIAL_PORT", "")
DEFAULT_BAUD: int = int(os.getenv("SERIAL_BAUD", "9600"))

LIGHT_THRESHOLD: int = 200
TEMP_COLD_THRESHOLD: float = 18.0
TEMP_HOT_THRESHOLD: float = 28.0

MAX_CONNECT_ATTEMPTS: int = 3
RETRY_DELAY_SECONDS: float = 2.0


def _detect_arduino_port() -> str | None:
    """Scan common serial paths and return the first match, or None."""
    candidates = sorted(
        glob.glob("/dev/ttyACM*")
        + glob.glob("/dev/ttyUSB*")
        + glob.glob("/dev/cu.usbmodem*")
        + glob.glob("/dev/tty.usbmodem*")
    )
    if candidates:
        logger.info("Auto-detected Arduino port: %s", candidates[0])
        return candidates[0]
    return None


class SerialComm:
    """Manage serial link to the Arduino and relay sensor events."""

    def __init__(
        self,
        port: str = DEFAULT_PORT,
        baud_rate: int = DEFAULT_BAUD,
    ) -> None:
        self._port: str = port or _detect_arduino_port() or ""
        self._baud_rate: int = baud_rate
        self._serial: serial.Serial | None = None
        self._reading: bool = False
        self._read_thread: threading.Thread | None = None
        self._bus: EventBus = EventBus()
        self._write_lock: threading.Lock = threading.Lock()

    @property
    def is_connected(self) -> bool:
        return self._serial is not None and self._serial.is_open

    def connect(self) -> bool:
        if not self._port:
            logger.error("No serial port specified and auto-detect failed")
            return False

        for attempt in range(1, MAX_CONNECT_ATTEMPTS + 1):
            try:
                self._serial = serial.Serial(
                    port=self._port,
                    baudrate=self._baud_rate,
                    timeout=1,
                )
                logger.info(
                    "Connected to %s @ %d baud (attempt %d)",
                    self._port,
                    self._baud_rate,
                    attempt,
                )
                return True
            except serial.SerialException:
                logger.warning(
                    "Connection attempt %d/%d to %s failed",
                    attempt,
                    MAX_CONNECT_ATTEMPTS,
                    self._port,
                )
                if attempt < MAX_CONNECT_ATTEMPTS:
                    time.sleep(RETRY_DELAY_SECONDS)

        logger.error("Failed to connect after %d attempts", MAX_CONNECT_ATTEMPTS)
        return False

    def disconnect(self) -> None:
        self._reading = False
        if self._read_thread is not None:
            self._read_thread.join(timeout=3)
            self._read_thread = None
        if self._serial is not None and self._serial.is_open:
            self._serial.close()
            logger.info("Serial connection closed")
        self._serial = None

    def send_command(self, cmd_dict: dict[str, Any]) -> bool:
        if not self.is_connected:
            logger.warning("Cannot send command: not connected")
            return False

        payload = json.dumps(cmd_dict, separators=(",", ":")) + "\n"
        try:
            with self._write_lock:
                self._serial.write(payload.encode("utf-8"))  # type: ignore[union-attr]
            logger.debug("Sent: %s", payload.strip())
            return True
        except serial.SerialException:
            logger.warning("Write failed, device may have disconnected")
            return False

    # -- Convenience helpers --------------------------------------------------

    def send_face(self, stage: int, emotion: str) -> bool:
        return self.send_command({"cmd": "face", "stage": stage, "emotion": emotion})

    def send_leds(self, r: int, g: int, b: int, mode: str = "solid") -> bool:
        return self.send_command({"cmd": "leds", "r": r, "g": g, "b": b, "mode": mode})

    def send_buzz(self, pattern: str) -> bool:
        return self.send_command({"cmd": "buzz", "pattern": pattern})

    def send_vibrate(self, duration: int) -> bool:
        return self.send_command({"cmd": "vibrate", "duration": duration})

    def send_text(self, line1: str, line2: str = "") -> bool:
        return self.send_command({"cmd": "text", "line1": line1, "line2": line2})

    # -- Background reader ----------------------------------------------------

    def start_reading(self) -> None:
        if self._read_thread is not None and self._read_thread.is_alive():
            logger.warning("Reader thread already running")
            return

        self._reading = True
        self._read_thread = threading.Thread(
            target=self._read_loop,
            daemon=True,
            name="serial-reader",
        )
        self._read_thread.start()
        logger.info("Serial reader thread started")

    def _read_loop(self) -> None:
        while self._reading:
            if not self.is_connected:
                logger.warning("Serial disconnected during read loop, stopping")
                break
            try:
                raw = self._serial.readline()  # type: ignore[union-attr]
                if not raw:
                    continue
                line = raw.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                self._process_line(line)
            except serial.SerialException:
                logger.warning("Serial read error, stopping reader")
                break
            except Exception:
                logger.exception("Unexpected error in read loop")

    def _process_line(self, line: str) -> None:
        try:
            data: dict[str, Any] = json.loads(line)
        except json.JSONDecodeError:
            logger.debug("Non-JSON line from Arduino: %s", line)
            return

        now = time.time()
        sensor = data.get("sensor")

        if sensor == "light":
            value = data.get("value", 0)
            event_type = EventType.LIGHT_LOW if value < LIGHT_THRESHOLD else EventType.LIGHT_OK
            self._bus.emit(Event(type=event_type, timestamp=now, data={"value": value}))

        elif sensor == "temp":
            value = data.get("value", 20.0)
            if value < TEMP_COLD_THRESHOLD:
                event_type = EventType.TEMP_COLD
            elif value > TEMP_HOT_THRESHOLD:
                event_type = EventType.TEMP_HOT
            else:
                event_type = EventType.TEMP_OK
            self._bus.emit(Event(type=event_type, timestamp=now, data={"value": value}))

        elif sensor == "button":
            self._bus.emit(Event(type=EventType.BUTTON_PRESS, timestamp=now, data=data))

        else:
            logger.debug("Unknown sensor payload: %s", line)
