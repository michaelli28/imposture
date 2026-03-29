"""Computer vision pipeline for the Wamm AI Desk Pet.

Captures webcam frames at ~1 FPS and runs:
- MediaPipe PoseLandmarker (Tasks API) for posture scoring
- EfficientDet object detector for phone detection

Posture scoring adapted from teammate's posture_analyzer8.py — uses
calibration-based reference scoring blended with absolute geometry.

Emits events via EventBus for consumption by the pet state manager.
"""

from __future__ import annotations

import json
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

# -- Latest frame storage (thread-safe via GIL for single assignment) ------

_latest_jpeg: bytes | None = None
_latest_jpeg_lock = threading.Lock()

logger = logging.getLogger(__name__)

# -- Model paths -----------------------------------------------------------

_SCRIPT_DIR = Path(__file__).resolve().parent.parent
POSE_MODEL_PATH = str(_SCRIPT_DIR / "pose_landmarker.task")
DETECTOR_MODEL_PATH = str(_SCRIPT_DIR / "object_detector.tflite")

# -- Capture settings ------------------------------------------------------

_FRAME_INTERVAL_SEC: float = 0.033  # ~30 FPS capture matching test speed
_ANALYSIS_INTERVAL_SEC: float = 1.0  # Run pose/phone analysis every 1s
_JPEG_INTERVAL_SEC: float = 0.1  # Encode JPEG for dashboard at ~10 FPS
_CAPTURE_WIDTH: int = 1280
_CAPTURE_HEIGHT: int = 720
_ROTATE_FRAME: bool = True  # Webcam is mounted rotated 90°

# -- Calibration settings --------------------------------------------------

CALIB_FRAMES: int = 60
CALIB_COUNTDOWN_SEC: int = 3
CALIB_DATA_PATH = _SCRIPT_DIR / "data" / "calibration.json"
REF_WEIGHT: float = 0.8
ABS_WEIGHT: float = 0.2
REF_BAD_THRESHOLD: float = 20.0

# -- Posture thresholds ----------------------------------------------------

_SCORE_BAD_THRESHOLD: float = 70.0  # Below this = bad posture
_BAD_POSTURE_WARN_SEC: float = 0.0  # Emit POSTURE_BAD instantly (testing)
_BAD_POSTURE_STRIKE_SEC: float = 0.0  # Escalate instantly (testing)
_GOOD_POSTURE_RECOVERY_SEC: float = 0.0
_SMOOTH_WINDOW: int = 1

# -- Phone detection thresholds --------------------------------------------

_PHONE_WINDOW_SEC: float = 60.0
_PHONE_ALERT_SEC: float = 0.0  # Alert instantly (testing)
_PHONE_RECOVERY_SEC: float = 0.0

# -- Sleep detection thresholds --------------------------------------------

_SLEEP_NOSE_RATIO: float = 0.85  # nose_y / shoulder_y >= this = head down
_SLEEP_NECK_ANGLE: float = 50.0  # neck angle >= this = head drooping
_SLEEP_SUSTAIN_SEC: float = 5.0  # must sustain for this long to trigger
_SLEEP_RECOVERY_SEC: float = 3.0  # head up for this long to recover

# -- Landmark indices (PoseLandmarker) -------------------------------------

NOSE = 0
LEFT_EAR = 7
RIGHT_EAR = 8
LEFT_SHOULDER = 11
RIGHT_SHOULDER = 12
LEFT_HIP = 23
RIGHT_HIP = 24

_POSE_CONNECTIONS = [
    (NOSE, LEFT_EAR), (NOSE, RIGHT_EAR),
    (LEFT_EAR, LEFT_SHOULDER), (RIGHT_EAR, RIGHT_SHOULDER),
    (LEFT_SHOULDER, RIGHT_SHOULDER),
    (LEFT_SHOULDER, LEFT_HIP), (RIGHT_SHOULDER, RIGHT_HIP),
    (LEFT_HIP, RIGHT_HIP),
]

_OVERLAY_LANDMARKS = [NOSE, LEFT_EAR, RIGHT_EAR, LEFT_SHOULDER, RIGHT_SHOULDER, LEFT_HIP, RIGHT_HIP]


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
            self.violation_count += 1
            bus.emit(Event(
                type=EventType.PHONE_DETECTED,
                timestamp=now,
                data={
                    "phone_seconds": round(self.phone_seconds, 1),
                    "violation_count": self.violation_count,
                },
            ))
            self._emitted_detected = True
            logger.info("PHONE_DETECTED emitted — phone_seconds=%.1f", self.phone_seconds)
        else:
            if self._emitted_detected:
                if self._away_since is None:
                    self._away_since = now
                elif now - self._away_since >= _PHONE_RECOVERY_SEC:
                    bus.emit(Event(type=EventType.PHONE_AWAY, timestamp=now))
                    self._emitted_detected = False
                    self._away_since = None
                    self.phone_seconds = 0.0
                    logger.info("PHONE_AWAY emitted")


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


# -- Sleep tracker ---------------------------------------------------------

def _detect_head_down(landmarks: list, w: int, h: int) -> bool:
    """Return True if the head appears to be down (sleeping position).

    Checks two signals:
    1. Nose Y is close to or below shoulder Y (head on desk)
    2. Neck angle is very steep (head drooping forward)
    Either condition triggers.
    """
    nose = _lm_xy(landmarks, NOSE, w, h)
    l_shoulder = _lm_xy(landmarks, LEFT_SHOULDER, w, h)
    r_shoulder = _lm_xy(landmarks, RIGHT_SHOULDER, w, h)
    mid_shoulder = _midpoint(l_shoulder, r_shoulder)

    # In image coords, Y increases downward. nose_y >= shoulder_y * ratio = head down.
    nose_ratio = nose[1] / max(mid_shoulder[1], 1.0)
    if nose_ratio >= _SLEEP_NOSE_RATIO:
        return True

    # Steep neck angle = head drooping
    mid_ear = _midpoint(
        _lm_xy(landmarks, LEFT_EAR, w, h),
        _lm_xy(landmarks, RIGHT_EAR, w, h),
    )
    neck_angle = _vertical_angle(mid_ear, mid_shoulder)
    return neck_angle >= _SLEEP_NECK_ANGLE


@dataclass
class SleepTracker:
    """Detects sustained head-down posture and emits SLEEPING/AWAKE events."""
    _down_since: float | None = None
    _up_since: float | None = None
    _emitted_sleeping: bool = False

    def update(self, landmarks: list, w: int, h: int, bus: EventBus) -> None:
        now = time.time()
        head_down = _detect_head_down(landmarks, w, h)

        if head_down:
            self._up_since = None
            if self._down_since is None:
                self._down_since = now
            elif not self._emitted_sleeping and now - self._down_since >= _SLEEP_SUSTAIN_SEC:
                bus.emit(Event(type=EventType.SLEEPING, timestamp=now))
                self._emitted_sleeping = True
                logger.info("SLEEPING emitted (head down for %.1fs)", now - self._down_since)
        else:
            self._down_since = None
            if self._emitted_sleeping:
                if self._up_since is None:
                    self._up_since = now
                elif now - self._up_since >= _SLEEP_RECOVERY_SEC:
                    bus.emit(Event(type=EventType.AWAKE, timestamp=now))
                    self._emitted_sleeping = False
                    self._up_since = None
                    logger.info("AWAKE emitted")
            else:
                self._up_since = None


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
        self._sleep_tracker = SleepTracker()

        # Last analysis results for drawing overlay on every frame
        self._last_landmarks: list | None = None
        self._last_score: float | None = None
        self._last_metrics: dict[str, Any] | None = None
        self._last_phone_boxes: list[tuple[int, int, int, int, float]] = []

        # Calibration state
        self._calib_active = False
        self._calib_phase = "idle"
        self._calib_start_time = 0.0
        self._calib_accumulated: dict[str, float] = {}
        self._calib_captured = 0

        self._load_calibration()

    @property
    def reference(self) -> dict[str, float] | None:
        return self._reference

    def calibrate_from_landmarks(self, landmarks: list, w: int, h: int) -> None:
        """Set the reference pose from a single set of landmarks."""
        self._reference = extract_features(landmarks, w, h)
        logger.info("Calibration set: %s", self._reference)

    def start_calibration(self) -> bool:
        """Begin a calibration sequence (countdown then capture)."""
        if self._calib_active:
            return False
        self._calib_active = True
        self._calib_phase = "countdown"
        self._calib_start_time = time.time()
        self._calib_accumulated = {
            k: 0.0 for k in ("spine_angle", "ear_forward", "neck_angle", "shoulder_diff", "ear_height_diff")
        }
        self._calib_captured = 0
        logger.info("Calibration started (countdown=%ds, frames=%d)", CALIB_COUNTDOWN_SEC, CALIB_FRAMES)
        return True

    def get_calibration_status(self) -> dict[str, Any]:
        """Return current calibration progress."""
        remaining = 0
        if self._calib_phase == "countdown":
            remaining = max(0, CALIB_COUNTDOWN_SEC - int(time.time() - self._calib_start_time))
        return {
            "active": self._calib_active,
            "phase": self._calib_phase,
            "countdown_remaining": remaining,
            "frames_captured": self._calib_captured,
            "frames_needed": CALIB_FRAMES,
            "calibrated": self._reference is not None,
        }

    def reset_trackers(self) -> None:
        """Reset all posture and phone trackers to initial state.

        Sets emitted flags so events don't immediately re-trigger — the
        trackers will only fire again after posture/phone transitions
        naturally (good→bad, away→detected).
        """
        self._posture_tracker = PostureStrikeTracker()
        self._posture_tracker._emitted_bad = True  # suppress immediate re-emit
        self._phone_tracker = PhoneTracker()
        self._phone_tracker._emitted_detected = False
        self._sleep_tracker = SleepTracker()
        self._score_buffer.clear()
        self._last_score = None
        self._last_metrics = None
        self._last_phone_boxes = []
        logger.info("CV trackers reset")

    def get_analysis_data(self) -> dict[str, Any]:
        """Return the latest analysis results for dashboard display."""
        return {
            "posture_score": self._last_score,
            "posture_label": posture_label(self._last_score) if self._last_score is not None else None,
            "metrics": self._last_metrics,
            "phone_visible": self._phone_tracker.phone_visible,
            "phone_seconds": round(self._phone_tracker.phone_seconds, 1),
            "posture_streak_secs": round(self._posture_tracker.bad_streak_secs, 1),
            "posture_strike_count": self._posture_tracker.strike_count,
        }

    def _save_calibration(self) -> None:
        """Persist calibration reference to disk."""
        if self._reference is None:
            return
        CALIB_DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
        CALIB_DATA_PATH.write_text(json.dumps(self._reference, indent=2))
        logger.info("Calibration saved to %s", CALIB_DATA_PATH)

    def _load_calibration(self) -> None:
        """Load calibration reference from disk if available."""
        if not CALIB_DATA_PATH.exists():
            return
        try:
            self._reference = json.loads(CALIB_DATA_PATH.read_text())
            logger.info("Loaded calibration from %s", CALIB_DATA_PATH)
        except (json.JSONDecodeError, TypeError) as exc:
            logger.error("Failed to load calibration: %s", exc)

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
                    score_threshold=0.25,
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
        last_analysis = 0.0
        last_jpeg = 0.0

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
            now = time.time()

            # Calibration state machine: countdown → capturing
            if self._calib_active and self._calib_phase == "countdown":
                if now - self._calib_start_time >= CALIB_COUNTDOWN_SEC:
                    self._calib_phase = "capturing"
                    logger.info("Calibration: countdown done, capturing frames")

            # Run analysis at ~1 FPS, or every frame during calibration capture
            capturing = self._calib_active and self._calib_phase == "capturing"
            if now - last_analysis >= _ANALYSIS_INTERVAL_SEC or capturing:
                if now - last_analysis >= _ANALYSIS_INTERVAL_SEC:
                    last_analysis = now

                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                self._frame_ts_ms += 33

                try:
                    from mediapipe import Image, ImageFormat
                    mp_img = Image(image_format=ImageFormat.SRGB, data=rgb)
                except Exception:
                    logger.exception("Failed to create MediaPipe Image")
                    _store_jpeg(frame)
                    time.sleep(_FRAME_INTERVAL_SEC)
                    continue

                # -- Posture analysis / calibration capture --
                if self._landmarker is not None:
                    try:
                        pose_result = self._landmarker.detect_for_video(mp_img, self._frame_ts_ms)
                        if pose_result.pose_landmarks and len(pose_result.pose_landmarks) > 0:
                            landmarks = pose_result.pose_landmarks[0]
                            self._last_landmarks = landmarks

                            if capturing:
                                features = extract_features(landmarks, w, h)
                                for k in self._calib_accumulated:
                                    self._calib_accumulated[k] += features[k]
                                self._calib_captured += 1
                                if self._calib_captured >= CALIB_FRAMES:
                                    self._reference = {
                                        k: v / self._calib_captured
                                        for k, v in self._calib_accumulated.items()
                                    }
                                    self._save_calibration()
                                    self._calib_phase = "done"
                                    self._calib_active = False
                                    self._score_buffer.clear()
                                    logger.info("Calibration complete: %s", self._reference)
                            else:
                                score, metrics = compute_posture_score(landmarks, w, h, self._reference)
                                self._score_buffer.append(score)
                                if len(self._score_buffer) > _SMOOTH_WINDOW:
                                    self._score_buffer.pop(0)
                                smoothed = round(sum(self._score_buffer) / len(self._score_buffer), 1)
                                self._last_score = smoothed
                                self._last_metrics = metrics
                                self._posture_tracker.update(smoothed, self._bus, metrics)
                                self._sleep_tracker.update(landmarks, w, h, self._bus)
                        else:
                            self._last_landmarks = None
                    except Exception:
                        logger.exception("Pose analysis failed")

                # -- Phone detection (skip during calibration) --
                if self._detector is not None and not self._calib_active:
                    try:
                        det_result = self._detector.detect_for_video(mp_img, self._frame_ts_ms)
                        phone_detected = False
                        phone_boxes: list[tuple[int, int, int, int, float]] = []
                        _PHONE_LABELS = {"cell phone", "remote", "mobile phone"}
                        for detection in det_result.detections:
                            for cat in detection.categories:
                                if cat.category_name.lower() in _PHONE_LABELS:
                                    phone_detected = True
                                    bb = detection.bounding_box
                                    phone_boxes.append((
                                        bb.origin_x, bb.origin_y,
                                        bb.width, bb.height, cat.score,
                                    ))
                        self._last_phone_boxes = phone_boxes
                        self._phone_tracker.update(phone_detected, self._bus)
                    except Exception:
                        logger.exception("Phone detection failed")

            # Encode JPEG at ~10 FPS
            if now - last_jpeg >= _JPEG_INTERVAL_SEC:
                last_jpeg = now
                display = frame.copy()
                if self._calib_active:
                    _draw_overlay(display, self._last_landmarks, w, h, None, None, [])
                    _draw_calibration_overlay(
                        display, self._calib_phase,
                        max(0, CALIB_COUNTDOWN_SEC - int(now - self._calib_start_time)),
                        self._calib_captured, CALIB_FRAMES, w, h,
                    )
                else:
                    _draw_overlay(
                        display, self._last_landmarks, w, h,
                        self._last_score, self._last_metrics,
                        self._last_phone_boxes,
                    )
                _store_jpeg(display)

            time.sleep(_FRAME_INTERVAL_SEC)


def _draw_overlay(
    frame: Any,
    landmarks: list | None,
    w: int,
    h: int,
    score: float | None,
    metrics: dict[str, Any] | None,
    phone_boxes: list[tuple[int, int, int, int, float]],
) -> None:
    """Draw skeleton, posture score, and phone boxes on the frame in-place."""
    # -- Skeleton --
    if landmarks is not None:
        pts = {i: _lm_xy(landmarks, i, w, h) for i in _OVERLAY_LANDMARKS}
        for a, b in _POSE_CONNECTIONS:
            if a in pts and b in pts:
                cv2.line(
                    frame,
                    (int(pts[a][0]), int(pts[a][1])),
                    (int(pts[b][0]), int(pts[b][1])),
                    (200, 200, 200), 2,
                )
        for x, y in pts.values():
            cv2.circle(frame, (int(x), int(y)), 5, (0, 255, 180), -1)

    # -- Posture score --
    if score is not None:
        label = posture_label(score)
        color = (
            (0, 200, 0) if score >= 70 else
            (0, 165, 255) if score >= 50 else
            (0, 0, 220)
        )
        cv2.putText(
            frame, f"Posture: {score}/100  {label}",
            (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.85, color, 2, cv2.LINE_AA,
        )

    if metrics is not None:
        cv2.putText(
            frame,
            f"spine={metrics.get('spine_angle_deg', 0)}°  "
            f"neck={metrics.get('neck_angle_deg', 0)}°  "
            f"fwd={metrics.get('ear_forward_norm', 0)}",
            (20, 75), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (180, 180, 180), 1, cv2.LINE_AA,
        )

    # -- Phone boxes --
    for (x, y, bw, bh, conf) in phone_boxes:
        cv2.rectangle(frame, (x, y), (x + bw, y + bh), (0, 100, 255), 2)
        cv2.putText(
            frame, f"Phone {conf:.0%}", (x, max(y - 8, 10)),
            cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 100, 255), 2,
        )


def _draw_calibration_overlay(
    frame: Any,
    phase: str,
    countdown_remaining: int,
    frames_captured: int,
    frames_needed: int,
    w: int,
    h: int,
) -> None:
    """Draw calibration countdown or capture progress on the frame."""
    overlay = frame.copy()
    cv2.rectangle(overlay, (0, 0), (w, h), (0, 0, 0), -1)
    cv2.addWeighted(overlay, 0.4, frame, 0.6, 0, frame)

    if phase == "countdown":
        cv2.putText(
            frame, "CALIBRATION",
            (w // 2 - 160, h // 2 - 80),
            cv2.FONT_HERSHEY_SIMPLEX, 1.4, (255, 255, 255), 3, cv2.LINE_AA,
        )
        cv2.putText(
            frame, "Sit in your best posture and hold still.",
            (w // 2 - 270, h // 2 - 30),
            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (200, 200, 200), 2, cv2.LINE_AA,
        )
        if countdown_remaining > 0:
            cv2.putText(
                frame, str(countdown_remaining),
                (w // 2 - 30, h // 2 + 70),
                cv2.FONT_HERSHEY_SIMPLEX, 3.0, (0, 220, 255), 5, cv2.LINE_AA,
            )
    elif phase == "capturing":
        progress = int((frames_captured / max(frames_needed, 1)) * (w - 80))
        cv2.rectangle(frame, (40, h - 50), (w - 40, h - 20), (60, 60, 60), -1)
        cv2.rectangle(frame, (40, h - 50), (40 + progress, h - 20), (0, 220, 120), -1)
        cv2.putText(
            frame, f"Capturing reference... {frames_captured}/{frames_needed}",
            (40, h - 60), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (200, 200, 200), 2, cv2.LINE_AA,
        )


def _store_jpeg(frame: Any) -> None:
    global _latest_jpeg  # noqa: PLW0603
    ret, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
    if ret:
        with _latest_jpeg_lock:
            _latest_jpeg = buf.tobytes()


def get_latest_jpeg() -> bytes | None:
    with _latest_jpeg_lock:
        return _latest_jpeg
