"""Text-to-speech for the Wamm AI Desk Pet.

Converts text responses to audio using the ElevenLabs API, with local
caching of common phrases to reduce latency and API calls.
"""

from __future__ import annotations

import io
import logging
import os
from pathlib import Path

import numpy as np
import sounddevice as sd
from dotenv import load_dotenv
from elevenlabs import ElevenLabs
from pydub import AudioSegment

load_dotenv()

logger = logging.getLogger(__name__)

SAMPLE_RATE: int = 24000


def _get_output_device() -> int | str | None:
    """Return the configured audio output device, or None for system default."""
    raw = os.getenv("AUDIO_OUTPUT_DEVICE", "")
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return raw


CACHED_PHRASES: tuple[str, ...] = (
    "Good posture!",
    "Hey, sit up straight!",
    "Put your phone down!",
    "Focus time! Let's go!",
    "Break time! You earned it!",
    "I'm getting sleepy...",
)

ASSETS_DIR: Path = Path(__file__).resolve().parent.parent / "assets" / "audio"


def _sanitize_filename(text: str) -> str:
    """Convert a phrase to a safe filename (lowercase, underscored)."""
    safe = text.lower()
    safe = safe.replace("'", "").replace("!", "").replace("...", "")
    safe = safe.replace(",", "").replace("?", "").replace(".", "")
    return "_".join(safe.split()) + ".mp3"


class TextToSpeech:
    """Generate and play speech audio using ElevenLabs."""

    def __init__(self) -> None:
        api_key = os.getenv("ELEVENLABS_API_KEY", "")
        if not api_key:
            logger.warning(
                "ELEVENLABS_API_KEY not set; TTS will be unavailable"
            )

        self._voice_id: str = os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")
        self._client: ElevenLabs = ElevenLabs(api_key=api_key)
        self._cache_dir: Path = ASSETS_DIR

    def speak(self, text: str) -> None:
        """Speak the given text, using a cached file if available."""
        if not text.strip():
            return

        cached_path = self._find_cached(text)
        if cached_path is not None:
            logger.info("Playing cached audio for: %s", text)
            self._play_audio(cached_path)
            return

        logger.info("Generating TTS for: %s", text)
        audio_data = self._generate(text)
        if audio_data:
            self._play_audio(audio_data)

    def pre_cache_phrases(self) -> None:
        """Generate and save common phrases as .mp3 files."""
        self._cache_dir.mkdir(parents=True, exist_ok=True)

        for phrase in CACHED_PHRASES:
            filename = _sanitize_filename(phrase)
            filepath = self._cache_dir / filename

            if filepath.exists():
                logger.debug("Already cached: %s", filename)
                continue

            logger.info("Pre-caching phrase: %s", phrase)
            audio_data = self._generate(phrase)
            if audio_data:
                try:
                    filepath.write_bytes(audio_data)
                    logger.info("Saved cached audio: %s", filepath)
                except OSError:
                    logger.exception("Failed to save cached audio: %s", filepath)

    def _find_cached(self, text: str) -> Path | None:
        """Check if the text matches a cached phrase and return its path."""
        filename = _sanitize_filename(text)
        filepath = self._cache_dir / filename
        if filepath.exists():
            return filepath
        return None

    def _generate(self, text: str) -> bytes | None:
        """Call ElevenLabs API to generate speech audio."""
        try:
            audio_iterator = self._client.text_to_speech.convert(
                voice_id=self._voice_id,
                text=text,
                model_id="eleven_turbo_v2",
                voice_settings={
                    "stability": 0.4,
                    "similarity_boost": 0.6,
                },
            )
            chunks: list[bytes] = list(audio_iterator)
            return b"".join(chunks)

        except Exception:
            logger.exception("ElevenLabs TTS generation failed for: %s", text)
            return None

    def _play_audio(self, audio_data_or_path: bytes | Path) -> None:
        """Play audio through the default speaker.

        Accepts either raw mp3 bytes or a Path to an mp3 file.
        """
        try:
            if isinstance(audio_data_or_path, Path):
                segment = AudioSegment.from_mp3(str(audio_data_or_path))
            else:
                segment = AudioSegment.from_mp3(io.BytesIO(audio_data_or_path))

            segment = segment.set_frame_rate(SAMPLE_RATE).set_channels(1)
            # Fade in/out to prevent popping
            segment = segment.fade_in(50).fade_out(50)
            samples = np.array(segment.get_array_of_samples(), dtype=np.float32)
            samples = samples / 32768.0

            sd.play(samples, samplerate=SAMPLE_RATE, device=_get_output_device())
            sd.wait()

        except sd.PortAudioError:
            logger.error("Audio output device not available for playback")
        except Exception:
            logger.exception("Failed to play audio")
