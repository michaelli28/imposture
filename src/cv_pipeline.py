"""Computer vision pipeline for the Buddy AI Desk Pet.

Captures webcam frames at 1 FPS and runs MediaPipe Pose Lite to detect
posture slouching and phone usage, emitting events via the EventBus.
"""

from __future__ import annotations

import logging
import math
import threading
import time
from dataclasses import dataclass
from typing import Optional

import cv2

from src.events import Event, EventBus, EventType

logger = logging.getLogger(__name__)

_SLOUCH_ANGLE_THRESHOLD_DEG: float = 20.0
_BAD_POSTURE_SUSTAIN_SEC: float = 5.0
_GOOD_POSTURE_RECOVERY_SEC: float = 3.0
_PHONE_SUSTAIN_SEC: float = 3.0
_PHONE_RECOVERY_SEC: float = 2.0
_HEAD_TILT_OFFSET: float = 0.05
_FRAME_INTERVAL_SEC: float = 1.0
_CAPTURE_WIDTH: int = 640
_CAPTURE_HEIGHT: int = 480


@dataclass
class _PostureState:
    bad_since: Optional[float] = None
    good_since: Optional[float] = None
    emitted_bad: bool = False


@dataclass
class _PhoneState:
    detected_since: Optional[float] = None
    away_since: Optional[float] = None
    emitted_detected: bool = False


def _angle_from_vertical(dx: float, dy: float) -> float:
    """Return the angle in degrees between the vector (dx, dy) and the vertical (downward) axis.

    The vertical axis points downward because MediaPipe y increases downward.
    A perfectly upright torso produces an angle near 0.
    """
    magnitude = math.hypot(dx, dy)
    if magnitude < 1e-9:
        return 0.0
    cos_angle = abs(dy) / magnitude
    cos_angle = min(cos_angle, 1.0)
    return math.degrees(math.acos(cos_angle))


class CVPipeline:
    """Webcam-based posture and phone detection pipeline.

    Opens a webcam, captures frames at ~1 FPS, runs MediaPipe Pose Lite,
    and emits EventBus events when bad posture or phone usage is detected.
    """

    def __init__(self, webcam_index: int = 0) -> None:
        self._webcam_index = webcam_index
        self._running = False
        self._capture: Optional[cv2.VideoCapture] = None
        self._thread: Optional[threading.Thread] = None
        self._bus = EventBus()
        self._pose: Optional[object] = None

        self._posture = _PostureState()
        self._phone = _PhoneState()

    def start(self) -> None:
        """Open the webcam and begin processing frames in a background thread."""
        if self._running:
            logger.warning("CVPipeline is already running")
            return

        self._capture = cv2.VideoCapture(self._webcam_index)
        if not self._capture.isOpened():
            logger.error(
                "Failed to open webcam at index %d", self._webcam_index
            )
            return

        self._capture.set(cv2.CAP_PROP_FRAME_WIDTH, _CAPTURE_WIDTH)
        self._capture.set(cv2.CAP_PROP_FRAME_HEIGHT, _CAPTURE_HEIGHT)

        try:
            import mediapipe as mp
            self._pose = mp.solutions.pose.Pose(
                static_image_mode=False,
                model_complexity=0,
                min_detection_confidence=0.5,
                min_tracking_confidence=0.5,
            )
        except Exception:
            logger.exception(
                "Failed to initialize MediaPipe Pose; "
                "CV pipeline will run without pose detection"
            )
            self._pose = None

        self._running = True
        self._thread = threading.Thread(
            target=self._process_loop, name="cv-pipeline", daemon=True
        )
        self._thread.start()
        logger.info("CVPipeline started (webcam=%d)", self._webcam_index)

    def stop(self) -> None:
        """Signal the processing loop to stop and release resources."""
        self._running = False

        if self._thread is not None:
            self._thread.join(timeout=5.0)
            self._thread = None

        if self._capture is not None:
            self._capture.release()
            self._capture = None

        if self._pose is not None:
            try:
                self._pose.close()  # type: ignore[union-attr]
            except Exception:
                logger.debug("Pose close raised; ignoring", exc_info=True)
            self._pose = None

        logger.info("CVPipeline stopped")

    def _process_loop(self) -> None:
        """Main loop: capture a frame every ~1 second and analyze it."""
        while self._running:
            if self._capture is None or not self._capture.isOpened():
                logger.error("Webcam lost; stopping CVPipeline")
                self._running = False
                break

            success, frame = self._capture.read()
            if not success:
                logger.warning("Failed to read frame; skipping cycle")
                time.sleep(_FRAME_INTERVAL_SEC)
                continue

            if self._pose is not None:
                self._run_pose_analysis(frame)

            time.sleep(_FRAME_INTERVAL_SEC)

    def _run_pose_analysis(self, frame: cv2.typing.MatLike) -> None:
        """Run MediaPipe Pose on a single frame and dispatch to analyzers."""
        try:
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = self._pose.process(rgb_frame)  # type: ignore[union-attr]
        except Exception:
            logger.exception("MediaPipe processing failed")
            return

        if results.pose_landmarks is None:
            return

        landmarks = results.pose_landmarks.landmark
        self._analyze_posture(landmarks)
        self._analyze_phone(landmarks)

    def _analyze_posture(self, landmarks: list) -> None:  # noqa: ANN001
        """Detect slouching based on the torso lean angle."""
        now = time.time()

        left_shoulder = landmarks[11]
        right_shoulder = landmarks[12]
        left_hip = landmarks[23]
        right_hip = landmarks[24]

        mid_shoulder_x = (left_shoulder.x + right_shoulder.x) / 2.0
        mid_shoulder_y = (left_shoulder.y + right_shoulder.y) / 2.0
        mid_hip_x = (left_hip.x + right_hip.x) / 2.0
        mid_hip_y = (left_hip.y + right_hip.y) / 2.0

        dx = mid_shoulder_x - mid_hip_x
        dy = mid_shoulder_y - mid_hip_y

        slouch_angle = _angle_from_vertical(dx, dy)

        if slouch_angle > _SLOUCH_ANGLE_THRESHOLD_DEG:
            self._posture.good_since = None

            if self._posture.bad_since is None:
                self._posture.bad_since = now

            elapsed = now - self._posture.bad_since
            if elapsed >= _BAD_POSTURE_SUSTAIN_SEC and not self._posture.emitted_bad:
                self._bus.emit(
                    Event(
                        type=EventType.POSTURE_BAD,
                        timestamp=now,
                        data={"slouch_angle": round(slouch_angle, 1)},
                    )
                )
                self._posture.emitted_bad = True
                logger.info(
                    "POSTURE_BAD emitted (angle=%.1f deg, sustained=%.1f s)",
                    slouch_angle,
                    elapsed,
                )
        else:
            self._posture.bad_since = None

            if self._posture.emitted_bad:
                if self._posture.good_since is None:
                    self._posture.good_since = now

                elapsed = now - self._posture.good_since
                if elapsed >= _GOOD_POSTURE_RECOVERY_SEC:
                    self._bus.emit(
                        Event(
                            type=EventType.POSTURE_GOOD,
                            timestamp=now,
                            data={"slouch_angle": round(slouch_angle, 1)},
                        )
                    )
                    self._posture.emitted_bad = False
                    self._posture.good_since = None
                    logger.info(
                        "POSTURE_GOOD emitted (angle=%.1f deg, recovered=%.1f s)",
                        slouch_angle,
                        elapsed,
                    )
            else:
                self._posture.good_since = None

    def _analyze_phone(self, landmarks: list) -> None:  # noqa: ANN001
        """Detect phone usage based on head tilt and wrist position."""
        now = time.time()

        nose = landmarks[0]
        left_ear = landmarks[7]
        right_ear = landmarks[8]
        left_wrist = landmarks[15]
        right_wrist = landmarks[16]
        left_shoulder = landmarks[11]
        right_shoulder = landmarks[12]

        avg_ear_y = (left_ear.y + right_ear.y) / 2.0
        head_tilted_down = nose.y > avg_ear_y + _HEAD_TILT_OFFSET

        avg_shoulder_y = (left_shoulder.y + right_shoulder.y) / 2.0
        wrist_raised = (
            left_wrist.y < avg_shoulder_y or right_wrist.y < avg_shoulder_y
        )

        phone_detected = head_tilted_down and wrist_raised

        if phone_detected:
            self._phone.away_since = None

            if self._phone.detected_since is None:
                self._phone.detected_since = now

            elapsed = now - self._phone.detected_since
            if elapsed >= _PHONE_SUSTAIN_SEC and not self._phone.emitted_detected:
                self._bus.emit(
                    Event(
                        type=EventType.PHONE_DETECTED,
                        timestamp=now,
                        data={
                            "head_tilted_down": head_tilted_down,
                            "wrist_raised": wrist_raised,
                        },
                    )
                )
                self._phone.emitted_detected = True
                logger.info(
                    "PHONE_DETECTED emitted (sustained=%.1f s)", elapsed
                )
        else:
            self._phone.detected_since = None

            if self._phone.emitted_detected:
                if self._phone.away_since is None:
                    self._phone.away_since = now

                elapsed = now - self._phone.away_since
                if elapsed >= _PHONE_RECOVERY_SEC:
                    self._bus.emit(
                        Event(
                            type=EventType.PHONE_AWAY,
                            timestamp=now,
                            data={
                                "head_tilted_down": head_tilted_down,
                                "wrist_raised": wrist_raised,
                            },
                        )
                    )
                    self._phone.emitted_detected = False
                    self._phone.away_since = None
                    logger.info(
                        "PHONE_AWAY emitted (recovered=%.1f s)", elapsed
                    )
            else:
                self._phone.away_since = None
