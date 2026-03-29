"""Speech-to-text for the Wamm AI Desk Pet.

Records audio from the microphone, detects silence to auto-stop, and
transcribes speech via the Deepgram Nova-2 API.
"""

from __future__ import annotations

import logging
import os
import struct

import numpy as np
import sounddevice as sd
from deepgram import DeepgramClient, PrerecordedOptions
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

SAMPLE_RATE: int = 16000
CHANNELS: int = 1
DTYPE: str = "int16"
BYTES_PER_SAMPLE: int = 2
CHUNK_DURATION_SECONDS: float = 0.1
CHUNK_SAMPLES: int = int(SAMPLE_RATE * CHUNK_DURATION_SECONDS)
SILENCE_RMS_THRESHOLD: int = 500

def _get_input_device() -> int | str | None:
    """Return the configured audio input device, or None for system default."""
    raw = os.getenv("AUDIO_INPUT_DEVICE", "")
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return raw


def _rms(audio_chunk: np.ndarray) -> float:
    """Compute root-mean-square of an int16 audio chunk."""
    samples = audio_chunk.astype(np.float64)
    return float(np.sqrt(np.mean(samples ** 2)))


class SpeechToText:
    """Record audio and transcribe via Deepgram."""

    def __init__(self) -> None:
        api_key = os.getenv("DEEPGRAM_API_KEY", "")
        if not api_key:
            logger.warning(
                "DEEPGRAM_API_KEY not set; transcription will fail"
            )
        self._client: DeepgramClient = DeepgramClient(api_key=api_key)

    def record_audio(
        self,
        max_duration: float = 10.0,
        silence_threshold: float = 2.0,
    ) -> bytes:
        """Record from the microphone until silence or max duration.

        Returns raw PCM bytes (16 kHz, 16-bit, mono).
        """
        frames: list[bytes] = []
        silent_seconds: float = 0.0
        elapsed: float = 0.0

        try:
            with sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=CHANNELS,
                dtype=DTYPE,
                blocksize=CHUNK_SAMPLES,
                device=_get_input_device(),
            ) as stream:
                logger.info("Recording started (max %.1fs)", max_duration)
                while elapsed < max_duration:
                    chunk, overflowed = stream.read(CHUNK_SAMPLES)
                    if overflowed:
                        logger.debug("Audio buffer overflow during recording")

                    samples = np.squeeze(chunk).astype(np.int16)
                    raw_bytes = samples.tobytes()
                    frames.append(raw_bytes)

                    level = _rms(samples)
                    if level < SILENCE_RMS_THRESHOLD:
                        silent_seconds += CHUNK_DURATION_SECONDS
                    else:
                        silent_seconds = 0.0

                    elapsed += CHUNK_DURATION_SECONDS

                    if silent_seconds >= silence_threshold and elapsed > 1.0:
                        logger.info(
                            "Silence detected after %.1fs, stopping recording",
                            elapsed,
                        )
                        break

                logger.info("Recording finished (%.1fs captured)", elapsed)

        except sd.PortAudioError:
            logger.error("Microphone not available for recording")
            return b""
        except Exception:
            logger.exception("Unexpected error during audio recording")
            return b""

        return b"".join(frames)

    def transcribe(self, audio_bytes: bytes) -> str:
        """Send raw PCM audio to Deepgram and return the transcript."""
        if not audio_bytes:
            return ""

        wav_bytes = _pcm_to_wav(audio_bytes, SAMPLE_RATE, CHANNELS)

        try:
            options = PrerecordedOptions(
                model="nova-2",
                language="en",
                smart_format=True,
            )
            response = self._client.listen.rest.v("1").transcribe_file(
                {"buffer": wav_bytes, "mimetype": "audio/wav"},
                options,
            )
            transcript: str = (
                response.results.channels[0].alternatives[0].transcript  # type: ignore[union-attr]
            )
            logger.info("Transcription: %s", transcript)
            return transcript

        except Exception:
            logger.exception("Deepgram transcription failed")
            return ""

    def listen_and_transcribe(self) -> str:
        """Convenience: record audio then transcribe."""
        audio = self.record_audio()
        return self.transcribe(audio)


def _pcm_to_wav(
    pcm_data: bytes, sample_rate: int, channels: int
) -> bytes:
    """Wrap raw PCM data in a minimal WAV header."""
    data_size = len(pcm_data)
    bits_per_sample = 16
    byte_rate = sample_rate * channels * (bits_per_sample // 8)
    block_align = channels * (bits_per_sample // 8)

    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + data_size,
        b"WAVE",
        b"fmt ",
        16,
        1,
        channels,
        sample_rate,
        byte_rate,
        block_align,
        bits_per_sample,
        b"data",
        data_size,
    )
    return header + pcm_data
