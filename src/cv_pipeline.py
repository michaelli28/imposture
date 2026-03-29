"""Computer vision pipeline for the Buddy AI Desk Pet.

Captures webcam frames at ~1 FPS and runs:
- MediaPipe PoseLandmarker (Tasks API) for posture scoring
- EfficientDet object detector for phone detection

Posture scoring adapted from teammate's posture_analyzer8.py — uses
calibration-based reference scoring blended with absolute geometry.

Emits events via EventBus for consumption by the pet state manager.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from src.events import Event, EventBus, EventType

logger = logging.getLogger(__name__)

# -- Model paths -----------------------------------------------------------

_SCRIPT_DIR = Path(__file__).resolve().parent.parent
POSE_MODEL_PATH = str(_SCRIPT_DIR / "pose_landmarker.task")
DETECTOR_MODEL_PATH = str(_SCRIPT_DIR / "object_detector.tflite")

# -- Capture settings ------------------------------------------------------

_FRAME_INTERVAL_SEC: float = 1.0
_CAPTURE_WIDTH: int = 640
_CAPTURE_HEIGHT: int = 480
_ROTATE_FRAME: bool = False  # Set True if webcam feeds 90-deg rotated

# -- Calibration settings --------------------------------------------------

CALIB_FRAMES: int = 60
REF_WEIGHT: float = 0.8
ABS_WEIGHT: float = 0.2
REF_BAD_THRESHOLD: float = 20.0

# -- Posture thresholds ----------------------------------------------------

_SCORE_BAD_THRESHOLD: float = 70.0  # Below this = bad posture
_BAD_POSTURE_WARN_SEC: float = 5.0  # Emit POSTURE_BAD after this long
_BAD_POSTURE_STRIKE_SEC: float = 30.0  # Escalate severity
_GOOD_POSTURE_RECOVERY_SEC: float = 3.0
_SMOOTH_WINDOW: int = 15

# -- Phone detection thresholds --------------------------------------------

_PHONE_WINDOW_SEC: float = 10.0
_PHONE_ALERT_SEC: float = 5.0
_PHONE_RECOVERY_SEC: float = 2.0

# -- Landmark indices (PoseLandmarker) -------------------------------------

NOSE = 0
LEFT_EAR = 7
RIGHT_EAR = 8
LEFT_SHOULDER = 11
RIGHT_SHOULDER = 12
LEFT_HIP = 23
RIGHT_HIP = 24


# -- Geometry helpers (from posture_analyzer8) -----------------------------

def _midpoint(p1: tuple[float, float], p2: tuple[float, float]) -> tuple[float, float]:
    return ((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2)


def _lm_xy(landmarks: list, idx: int, w: int, h: int) -> tuple[float, float]:
    lm = landmarks[idx]
    return (lm.x * w, lm.y * h)


def _vertical_angle(p_top: tuple[float, float], p_bottom: tuple[float, float]) -> float:
    dx = p_bottom[0] - p_top[0]
    dy = p_bottom[1] - p_top[1]
    return float(np.degrees(np.arctan2(abs(dx), abs(dy) + 1e-6)))


def _score_from_deviation(deviation: float, bad_threshold: float) -> float:
    return max(0.0, 100.0 * (1.0 - abs(deviation) / bad_threshold))


def extract_features(landmarks: list, w: int, h: int) -> dict[str, float]:
    """Normalised posture features, scale-invariant via shoulder width."""
    l_ear = _lm_xy(landmarks, LEFT_EAR, w, h)
    r_ear = _lm_xy(landmarks, RIGHT_EAR, w, h)
    l_shoulder = _lm_xy(landmarks, LEFT_SHOULDER, w, h)
    r_shoulder = _lm_xy(landmarks, RIGHT_SHOULDER, w, h)
    l_hip = _lm_xy(landmarks, LEFT_HIP, w, h)
    r_hip = _lm_xy(landmarks, RIGHT_HIP, w, h)

    mid_shoulder = _midpoint(l_shoulder, r_shoulder)
    mid_hip = _midpoint(l_hip, r_hip)
    mid_ear = _midpoint(l_ear, r_ear)
    shoulder_width = max(abs(l_shoulder[0] - r_shoulder[0]), 10)

    return {
        "spine_angle": _vertical_angle(mid_shoulder, mid_hip),
        "ear_forward": (mid_shoulder[0] - mid_ear[0]) / shoulder_width * 100,
        "neck_angle": _vertical_angle(mid_ear, mid_shoulder),
        "shoulder_diff": abs(l_shoulder[1] - r_shoulder[1]) / shoulder_width * 100,
        "ear_height_diff": abs(l_ear[1] - r_ear[1]) / shoulder_width * 100,
    }


def absolute_score(features: dict[str, float]) -> float:
    """Score posture purely from geometry (no calibration needed)."""
    s1 = _score_from_deviation(features["spine_angle"], bad_threshold=20.0)
    s2 = _score_from_deviation(max(0.0, features["ear_forward"] - 30.0), bad_threshold=40.0)
    s3 = _score_from_deviation(features["neck_angle"], bad_threshold=40.0)
    s4 = _score_from_deviation(max(0.0, features["shoulder_diff"] - 5.0), bad_threshold=25.0)
    s5 = _score_from_deviation(max(0.0, features["ear_height_diff"] - 5.0), bad_threshold=25.0)
    weights = (0.30, 0.30, 0.20, 0.10, 0.10)
    return sum(w * s for w, s in zip(weights, (s1, s2, s3, s4, s5)))


def reference_score(features: dict[str, float], reference: dict[str, float]) -> float:
    """Score posture relative to a calibrated reference pose."""
    scores = []
    for key in features:
        dev = features[key] - reference[key]
        scores.append(_score_from_deviation(dev, bad_threshold=REF_BAD_THRESHOLD))
    return sum(scores) / len(scores) if scores else 0.0


def compute_posture_score(
    landmarks: list, w: int, h: int, reference: dict[str, float] | None = None
) -> tuple[float, dict[str, Any]]:
    """Compute 0-100 posture score and diagnostic metrics."""
    features = extract_features(landmarks, w, h)
    abs_s = absolute_score(features)
    if reference is not None:
        ref_s = reference_score(features, reference)
        total = ABS_WEIGHT * abs_s + REF_WEIGHT * ref_s
    else:
        total = abs_s
    metrics = {
        "spine_angle_deg": round(features["spine_angle"], 1),
        "ear_forward_norm": round(features["ear_forward"], 1),
        "neck_angle_deg": round(features["neck_angle"], 1),
        "shoulder_diff_norm": round(features["shoulder_diff"], 1),
    }
    return round(total, 1), metrics


def posture_label(score: float) -> str:
    if score >= 85:
        return "Excellent"
    if score >= 70:
        return "Good"
    if score >= 50:
        return "Fair"
    if score >= 30:
        return "Poor"
    return "Very Poor"


# -- Phone tracker (from posture_analyzer8) --------------------------------

@dataclass
class PhoneTracker:
    """Sliding-window phone usage tracker using object detection results."""
    window_start: float = 0.0
    phone_seconds: float = 0.0
    last_tick: float = 0.0
    phone_visible: bool = False
    alert_triggered: bool = False
    violation_count: int = 0
    _emitted_detected: bool = False
    _away_since: float | None = None

    def __post_init__(self) -> None:
        now = time.time()
        self.window_start = now
        self.last_tick = now

    def update(self, phone_detected: bool, bus: EventBus) -> None:
        now = time.time()
        elapsed = now - self.last_tick
        self.last_tick = now
        self.phone_visible = phone_detected

        if phone_detected:
            self.phone_seconds += elapsed
            self._away_since = None
        else:
            if self._emitted_detected:
                if self._away_since is None:
                    self._away_since = now
                elif now - self._away_since >= _PHONE_RECOVERY_SEC:
                    bus.emit(Event(type=EventType.PHONE_AWAY, timestamp=now))
                    self._emitted_detected = False
                    self._away_since = None
                    logger.info("PHONE_AWAY emitted")

        # Window reset
        if now - self.window_start >= _PHONE_WINDOW_SEC:
            violated = self.phone_seconds >= _PHONE_ALERT_SEC
            if violated:
                self.violation_count += 1
            self.window_start = now
            self.phone_seconds = 0.0
            self.alert_triggered = False

        # Alert within window
        if self.phone_seconds >= _PHONE_ALERT_SEC and not self.alert_triggered:
            self.alert_triggered = True
            if not self._emitted_detected:
                bus.emit(Event(
                    type=EventType.PHONE_DETECTED,
                    timestamp=now,
                    data={
                        "phone_seconds": round(self.phone_seconds, 1),
                        "violation_count": self.violation_count,
                    },
                ))
                self._emitted_detected = True
                logger.info(
                    "PHONE_DETECTED emitted (%.1fs in %.0fs window, violations=%d)",
                    self.phone_seconds, _PHONE_WINDOW_SEC, self.violation_count,
                )


# -- Posture strike tracker (from posture_analyzer8) -----------------------

@dataclass
class PostureStrikeTracker:
    """Tracks sustained bad posture and emits events with escalating severity."""
    bad_since: float | None = None
    bad_streak_secs: float = 0.0
    warn_emitted: bool = False
    strike_emitted: bool = False
    strike_count: int = 0
    _emitted_bad: bool = False
    _good_since: float | None = None

    def update(self, score: float, bus: EventBus, metrics: dict[str, Any]) -> None:
        now = time.time()
        is_bad = score < _SCORE_BAD_THRESHOLD

        if is_bad:
            self._good_since = None
            if self.bad_since is None:
                self.bad_since = now
            self.bad_streak_secs = now - self.bad_since

            # Emit POSTURE_BAD after warn threshold
            if self.bad_streak_secs >= _BAD_POSTURE_WARN_SEC and not self._emitted_bad:
                severity = "strict" if self.bad_streak_secs >= _BAD_POSTURE_STRIKE_SEC else "moderate"
                bus.emit(Event(
                    type=EventType.POSTURE_BAD,
                    timestamp=now,
                    data={
                        "score": score,
                        "label": posture_label(score),
                        "streak_seconds": round(self.bad_streak_secs, 1),
                        "severity": severity,
                        **metrics,
                    },
                ))
                self._emitted_bad = True
                self.warn_emitted = True
                logger.info(
                    "POSTURE_BAD emitted (score=%.1f, streak=%.1fs, severity=%s)",
                    score, self.bad_streak_secs, severity,
                )

            # Escalate to strike
            if self.bad_streak_secs >= _BAD_POSTURE_STRIKE_SEC and not self.strike_emitted:
                self.strike_emitted = True
                self.strike_count += 1
                logger.info("Posture strike #%d (%.0fs bad)", self.strike_count, self.bad_streak_secs)
        else:
            # Good posture — check for recovery
            self.bad_since = None
            self.bad_streak_secs = 0.0
            self.warn_emitted = False
            self.strike_emitted = False

            if self._emitted_bad:
                if self._good_since is None:
                    self._good_since = now
                elif now - self._good_since >= _GOOD_POSTURE_RECOVERY_SEC:
                    bus.emit(Event(
                        type=EventType.POSTURE_GOOD,
                        timestamp=now,
                        data={"score": score, "label": posture_label(score), **metrics},
                    ))
                    self._emitted_bad = False
                    self._good_since = None
                    logger.info("POSTURE_GOOD emitted (score=%.1f)", score)
            else:
                self._good_since = None


# -- Main pipeline class ---------------------------------------------------

class CVPipeline:
    """Webcam-based posture and phone detection pipeline.

    Uses MediaPipe Tasks API (PoseLandmarker + ObjectDetector) and emits
    EventBus events for the pet state manager.
    """

    def __init__(self, webcam_index: int = 0, rotate: bool = _ROTATE_FRAME) -> None:
        self._webcam_index = webcam_index
        self._rotate = rotate
        self._running = False
        self._capture: cv2.VideoCapture | None = None
        self._thread: threading.Thread | None = None
        self._bus = EventBus()

        self._landmarker: Any = None
        self._detector: Any = None
        self._frame_ts_ms: int = 0

        self._reference: dict[str, float] | None = None
        self._score_buffer: list[float] = []
        self._posture_tracker = PostureStrikeTracker()
        self._phone_tracker = PhoneTracker()

    @property
    def reference(self) -> dict[str, float] | None:
        return self._reference

    def calibrate_from_landmarks(self, landmarks: list, w: int, h: int) -> None:
        """Set the reference pose from a single set of landmarks."""
        self._reference = extract_features(landmarks, w, h)
        logger.info("Calibration set: %s", self._reference)

    def start(self) -> None:
        if self._running:
            logger.warning("CVPipeline is already running")
            return

        self._capture = cv2.VideoCapture(self._webcam_index)
        if not self._capture.isOpened():
            logger.error("Failed to open webcam at index %d", self._webcam_index)
            self._running = False
            return

        self._capture.set(cv2.CAP_PROP_FRAME_WIDTH, _CAPTURE_WIDTH)
        self._capture.set(cv2.CAP_PROP_FRAME_HEIGHT, _CAPTURE_HEIGHT)

        self._init_models()

        self._running = True
        self._thread = threading.Thread(
            target=self._process_loop, name="cv-pipeline", daemon=True
        )
        self._thread.start()
        logger.info("CVPipeline started (webcam=%d)", self._webcam_index)

    def stop(self) -> None:
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=5.0)
            self._thread = None
        if self._capture is not None:
            self._capture.release()
            self._capture = None
        if self._landmarker is not None:
            self._landmarker.close()
            self._landmarker = None
        if self._detector is not None:
            self._detector.close()
            self._detector = None
        logger.info("CVPipeline stopped")

    def _init_models(self) -> None:
        """Initialize MediaPipe Tasks models."""
        try:
            import mediapipe as mp
            from mediapipe.tasks import python as mp_python
            from mediapipe.tasks.python import vision as mp_vision

            if os.path.exists(POSE_MODEL_PATH):
                pose_options = mp_vision.PoseLandmarkerOptions(
                    base_options=mp_python.BaseOptions(
                        model_asset_path=POSE_MODEL_PATH,
                        delegate=mp_python.BaseOptions.Delegate.CPU,
                    ),
                    running_mode=mp_vision.RunningMode.VIDEO,
                    num_poses=1,
                    min_pose_detection_confidence=0.6,
                    min_pose_presence_confidence=0.6,
                    min_tracking_confidence=0.6,
                )
                self._landmarker = mp_vision.PoseLandmarker.create_from_options(pose_options)
                logger.info("PoseLandmarker initialized from %s", POSE_MODEL_PATH)
            else:
                logger.warning("Pose model not found at %s — posture detection disabled", POSE_MODEL_PATH)

            if os.path.exists(DETECTOR_MODEL_PATH):
                det_options = mp_vision.ObjectDetectorOptions(
                    base_options=mp_python.BaseOptions(
                        model_asset_path=DETECTOR_MODEL_PATH,
                        delegate=mp_python.BaseOptions.Delegate.CPU,
                    ),
                    running_mode=mp_vision.RunningMode.VIDEO,
                    score_threshold=0.4,
                    max_results=10,
                )
                self._detector = mp_vision.ObjectDetector.create_from_options(det_options)
                logger.info("ObjectDetector initialized from %s", DETECTOR_MODEL_PATH)
            else:
                logger.warning("Detector model not found at %s — phone detection disabled", DETECTOR_MODEL_PATH)

        except Exception:
            logger.exception("Failed to initialize MediaPipe models")

    def _read_frame(self) -> tuple[bool, Any]:
        """Read and optionally rotate a frame."""
        if self._capture is None:
            return False, None
        ret, frame = self._capture.read()
        if ret and self._rotate:
            frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
        return ret, frame

    def _process_loop(self) -> None:
        while self._running:
            ret, frame = self._read_frame()
            if not ret:
                if self._capture is None or not self._capture.isOpened():
                    logger.error("Webcam lost; stopping CVPipeline")
                    self._running = False
                    break
                time.sleep(_FRAME_INTERVAL_SEC)
                continue

            h, w = frame.shape[:2]
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            self._frame_ts_ms += int(_FRAME_INTERVAL_SEC * 1000)

            try:
                from mediapipe import Image, ImageFormat
                mp_img = Image(image_format=ImageFormat.SRGB, data=rgb)
            except Exception:
                logger.exception("Failed to create MediaPipe Image")
                time.sleep(_FRAME_INTERVAL_SEC)
                continue

            # -- Posture analysis --
            if self._landmarker is not None:
                try:
                    pose_result = self._landmarker.detect_for_video(mp_img, self._frame_ts_ms)
                    if pose_result.pose_landmarks and len(pose_result.pose_landmarks) > 0:
                        landmarks = pose_result.pose_landmarks[0]
                        score, metrics = compute_posture_score(landmarks, w, h, self._reference)

                        self._score_buffer.append(score)
                        if len(self._score_buffer) > _SMOOTH_WINDOW:
                            self._score_buffer.pop(0)
                        smoothed = round(sum(self._score_buffer) / len(self._score_buffer), 1)

                        self._posture_tracker.update(smoothed, self._bus, metrics)
                except Exception:
                    logger.exception("Pose analysis failed")

            # -- Phone detection (object detection) --
            if self._detector is not None:
                try:
                    det_result = self._detector.detect_for_video(mp_img, self._frame_ts_ms)
                    phone_detected = any(
                        "cell phone" in cat.category_name.lower()
                        for detection in det_result.detections
                        for cat in detection.categories
                    )
                    self._phone_tracker.update(phone_detected, self._bus)
                except Exception:
                    logger.exception("Phone detection failed")

            time.sleep(_FRAME_INTERVAL_SEC)
