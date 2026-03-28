"""Wake word detection for the Buddy AI Desk Pet.

Listens for a wake word ("hey jarvis") using OpenWakeWord and emits a
WAKE_WORD event via the EventBus when detected with sufficient confidence.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Callable

import numpy as np
import sounddevice as sd
from openwakeword.model import Model

from src.events import Event, EventBus, EventType

logger = logging.getLogger(__name__)

WAKE_WORD_MODEL: str = "hey_jarvis"
CONFIDENCE_THRESHOLD: float = 0.5
COOLDOWN_SECONDS: float = 2.0
SAMPLE_RATE: int = 16000
CHUNK_SAMPLES: int = 1280


class WakeWordListener:
    """Continuously monitors the microphone for a wake word trigger."""

    def __init__(self, on_wake: Callable[[], None] | None = None) -> None:
        self._on_wake: Callable[[], None] | None = on_wake
        self._bus: EventBus = EventBus()
        self._running: bool = False
        self._thread: threading.Thread | None = None
        self._model: Model | None = None

        try:
            self._model = Model(wakeword_models=[WAKE_WORD_MODEL])
            logger.info("OpenWakeWord model '%s' loaded", WAKE_WORD_MODEL)
        except Exception:
            logger.exception("Failed to load OpenWakeWord model '%s'", WAKE_WORD_MODEL)

    def start(self) -> None:
        """Start the background wake word detection thread."""
        if self._model is None:
            logger.error("Cannot start: wake word model not loaded")
            return

        if self._thread is not None and self._thread.is_alive():
            logger.warning("Wake word listener already running")
            return

        self._running = True
        self._thread = threading.Thread(
            target=self._listen_loop,
            daemon=True,
            name="wake-word-listener",
        )
        self._thread.start()
        logger.info("Wake word listener started")

    def stop(self) -> None:
        """Stop the background thread and release resources."""
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=3)
            self._thread = None
        logger.info("Wake word listener stopped")

    def _listen_loop(self) -> None:
        last_trigger_time: float = 0.0

        try:
            with sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=1,
                dtype="int16",
                blocksize=CHUNK_SAMPLES,
            ) as stream:
                logger.info("Microphone stream opened for wake word detection")
                while self._running:
                    audio_chunk, overflowed = stream.read(CHUNK_SAMPLES)
                    if overflowed:
                        logger.debug("Audio buffer overflow detected")

                    samples = np.squeeze(audio_chunk).astype(np.int16)
                    self._model.predict(samples)  # type: ignore[union-attr]

                    scores = self._model.prediction_buffer.get(  # type: ignore[union-attr]
                        WAKE_WORD_MODEL, []
                    )
                    if not scores:
                        continue

                    current_score: float = scores[-1]
                    if current_score < CONFIDENCE_THRESHOLD:
                        continue

                    now = time.time()
                    if now - last_trigger_time < COOLDOWN_SECONDS:
                        continue

                    last_trigger_time = now
                    logger.info(
                        "Wake word detected (confidence=%.2f)", current_score
                    )
                    self._bus.emit(
                        Event(
                            type=EventType.WAKE_WORD,
                            timestamp=now,
                            data={"confidence": current_score},
                        )
                    )
                    if self._on_wake is not None:
                        try:
                            self._on_wake()
                        except Exception:
                            logger.exception("Error in on_wake callback")

        except sd.PortAudioError:
            logger.error(
                "Microphone not found or unavailable. "
                "Wake word detection cannot run without audio input."
            )
        except Exception:
            logger.exception("Unexpected error in wake word listen loop")
