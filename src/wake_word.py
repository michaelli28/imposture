"""Wake word detection for the Wamm AI Desk Pet.

Listens for a wake word ("Hey Wamm") using OpenWakeWord and emits a
WAKE_WORD event via the EventBus when detected with sufficient confidence.

Note: Uses the "hey_jarvis" pre-trained model under the hood since
OpenWakeWord has no built-in "hey wamm" model. A custom model can be
trained later for a true "Hey Wamm" trigger.
"""

from __future__ import annotations

import logging
import os
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


def _get_input_device() -> int | str | None:
    """Return the configured audio input device, or None for system default."""
    raw = os.getenv("AUDIO_INPUT_DEVICE", "")
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return raw


class WakeWordListener:
    """Continuously monitors the microphone for a wake word trigger."""

    def __init__(self, on_wake: Callable[[], None] | None = None) -> None:
        self._on_wake: Callable[[], None] | None = on_wake
        self._bus: EventBus = EventBus()
        self._running: bool = False
        self._paused: bool = False
        self._pause_event: threading.Event = threading.Event()
        self._pause_event.set()  # Start unpaused
        self._thread: threading.Thread | None = None
        self._model: Model | None = None

        try:
            self._model = Model(wakeword_models=[WAKE_WORD_MODEL], inference_framework="onnx")
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
        self._pause_event.set()  # Unblock if paused
        if self._thread is not None:
            self._thread.join(timeout=3)
            self._thread = None
        logger.info("Wake word listener stopped")

    def pause(self) -> None:
        """Pause listening to release the microphone for STT."""
        self._paused = True
        self._pause_event.clear()
        logger.info("Wake word listener paused")

    def resume(self) -> None:
        """Resume listening after STT is done."""
        self._paused = False
        self._pause_event.set()
        logger.info("Wake word listener resumed")

    def _listen_loop(self) -> None:
        last_trigger_time: float = 0.0

        while self._running:
            # Wait if paused (mic released for STT)
            self._pause_event.wait()
            if not self._running:
                break

            try:
                with sd.InputStream(
                    samplerate=SAMPLE_RATE,
                    channels=1,
                    dtype="int16",
                    blocksize=CHUNK_SAMPLES,
                    device=_get_input_device(),
                ) as stream:
                    logger.info("Microphone stream opened for wake word detection")
                    while self._running and not self._paused:
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

                        # Clear the prediction buffer so old scores don't re-trigger
                        self._model.prediction_buffer[WAKE_WORD_MODEL] = []  # type: ignore[union-attr]

                        self._bus.emit(
                            Event(
                                type=EventType.WAKE_WORD,
                                timestamp=now,
                                data={"confidence": current_score},
                            )
                        )
                        if self._on_wake is not None:
                            # Pause listening, run voice command, then resume
                            self.pause()
                            threading.Thread(
                                target=self._run_wake_callback,
                                daemon=True,
                                name="voice-command",
                            ).start()

            except sd.PortAudioError:
                logger.error("Microphone not available, retrying in 2s...")
                time.sleep(2)
            except Exception:
                logger.exception("Error in wake word listen loop, retrying in 2s...")
                time.sleep(2)

    def _run_wake_callback(self) -> None:
        """Run the wake callback then resume listening."""
        try:
            self._on_wake()  # type: ignore[misc]
        except Exception:
            logger.exception("Error in on_wake callback")
        finally:
            self.resume()
