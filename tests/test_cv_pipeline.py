"""Tests for the CVPipeline computer vision module."""

from __future__ import annotations

import math
import time
from types import SimpleNamespace
from typing import Optional
from unittest.mock import MagicMock, patch

import pytest

from src.cv_pipeline import (
    CVPipeline,
    _BAD_POSTURE_SUSTAIN_SEC,
    _GOOD_POSTURE_RECOVERY_SEC,
    _HEAD_TILT_OFFSET,
    _PHONE_RECOVERY_SEC,
    _PHONE_SUSTAIN_SEC,
    _SLOUCH_ANGLE_THRESHOLD_DEG,
    _angle_from_vertical,
    _PhoneState,
    _PostureState,
)
from src.events import Event, EventBus, EventType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_landmark(x: float = 0.0, y: float = 0.0, z: float = 0.0) -> SimpleNamespace:
    """Create a fake MediaPipe landmark with x, y, z attributes."""
    return SimpleNamespace(x=x, y=y, z=z)


def _make_landmarks(overrides: Optional[dict[int, SimpleNamespace]] = None) -> list:
    """Build a 33-element landmark list with sensible upright defaults.

    MediaPipe Pose has 33 landmarks (indices 0-32).  We fill them all
    with a default, then apply any caller-supplied overrides by index.
    """
    default = _make_landmark(x=0.5, y=0.5)
    landmarks = [default] * 33

    upright_defaults: dict[int, SimpleNamespace] = {
        0: _make_landmark(x=0.5, y=0.2),          # NOSE
        7: _make_landmark(x=0.45, y=0.22),         # LEFT_EAR
        8: _make_landmark(x=0.55, y=0.22),         # RIGHT_EAR
        11: _make_landmark(x=0.4, y=0.4),          # LEFT_SHOULDER
        12: _make_landmark(x=0.6, y=0.4),          # RIGHT_SHOULDER
        15: _make_landmark(x=0.35, y=0.65),        # LEFT_WRIST (below shoulders)
        16: _make_landmark(x=0.65, y=0.65),        # RIGHT_WRIST (below shoulders)
        23: _make_landmark(x=0.45, y=0.7),         # LEFT_HIP
        24: _make_landmark(x=0.55, y=0.7),         # RIGHT_HIP
    }

    for idx, lm in upright_defaults.items():
        landmarks[idx] = lm

    if overrides:
        for idx, lm in overrides.items():
            landmarks[idx] = lm

    return landmarks


def _collected_events(bus: EventBus) -> list[Event]:
    """Subscribe to all CV-relevant event types and return a shared list."""
    events: list[Event] = []

    def _collector(event: Event) -> None:
        events.append(event)

    for et in (
        EventType.POSTURE_BAD,
        EventType.POSTURE_GOOD,
        EventType.PHONE_DETECTED,
        EventType.PHONE_AWAY,
    ):
        bus.subscribe(et, _collector)
    return events


# ---------------------------------------------------------------------------
# Unit: _angle_from_vertical
# ---------------------------------------------------------------------------

class TestAngleFromVertical:

    def test_perfectly_vertical_is_zero(self) -> None:
        assert _angle_from_vertical(0.0, -1.0) == pytest.approx(0.0, abs=0.01)

    def test_horizontal_is_ninety(self) -> None:
        assert _angle_from_vertical(1.0, 0.0) == pytest.approx(90.0, abs=0.01)

    def test_forty_five_degrees(self) -> None:
        assert _angle_from_vertical(1.0, 1.0) == pytest.approx(45.0, abs=0.01)

    def test_zero_length_returns_zero(self) -> None:
        assert _angle_from_vertical(0.0, 0.0) == 0.0

    def test_negative_dy_still_works(self) -> None:
        assert _angle_from_vertical(0.0, 1.0) == pytest.approx(0.0, abs=0.01)


# ---------------------------------------------------------------------------
# Unit: _PostureState / _PhoneState defaults
# ---------------------------------------------------------------------------

class TestStateDefaults:

    def test_posture_state_defaults(self) -> None:
        state = _PostureState()
        assert state.bad_since is None
        assert state.good_since is None
        assert state.emitted_bad is False

    def test_phone_state_defaults(self) -> None:
        state = _PhoneState()
        assert state.detected_since is None
        assert state.away_since is None
        assert state.emitted_detected is False


# ---------------------------------------------------------------------------
# Integration: posture analysis
# ---------------------------------------------------------------------------

class TestPostureAnalysis:

    @pytest.fixture(autouse=True)
    def _setup(self) -> None:
        self.bus = EventBus()
        self.bus.clear()
        self.events = _collected_events(self.bus)
        self.pipeline = CVPipeline()

    def test_upright_posture_emits_nothing(self) -> None:
        landmarks = _make_landmarks()
        self.pipeline._analyze_posture(landmarks)
        assert len(self.events) == 0

    def test_slouch_below_threshold_emits_nothing(self) -> None:
        angle_rad = math.radians(_SLOUCH_ANGLE_THRESHOLD_DEG - 5)
        dy = -0.3
        dx = abs(dy) * math.tan(angle_rad)
        mid_hip_x, mid_hip_y = 0.5, 0.7
        mid_sh_x = mid_hip_x + dx
        mid_sh_y = mid_hip_y + dy

        landmarks = _make_landmarks({
            11: _make_landmark(x=mid_sh_x - 0.1, y=mid_sh_y),
            12: _make_landmark(x=mid_sh_x + 0.1, y=mid_sh_y),
            23: _make_landmark(x=mid_hip_x - 0.05, y=mid_hip_y),
            24: _make_landmark(x=mid_hip_x + 0.05, y=mid_hip_y),
        })

        self.pipeline._analyze_posture(landmarks)
        assert len(self.events) == 0

    def test_slouch_requires_sustained_duration(self) -> None:
        """Slouching for less than the sustain threshold emits nothing."""
        landmarks = _make_landmarks({
            11: _make_landmark(x=0.2, y=0.4),
            12: _make_landmark(x=0.8, y=0.4),
            23: _make_landmark(x=0.45, y=0.7),
            24: _make_landmark(x=0.55, y=0.7),
        })

        self.pipeline._analyze_posture(landmarks)
        assert len(self.events) == 0
        assert self.pipeline._posture.bad_since is not None

    def test_sustained_slouch_emits_posture_bad(self) -> None:
        """Slouching sustained past the threshold emits exactly one POSTURE_BAD."""
        slouch_landmarks = _make_landmarks({
            11: _make_landmark(x=0.2, y=0.4),
            12: _make_landmark(x=0.8, y=0.4),
        })

        self.pipeline._analyze_posture(slouch_landmarks)
        self.pipeline._posture.bad_since = (
            time.time() - _BAD_POSTURE_SUSTAIN_SEC - 1.0
        )
        self.pipeline._analyze_posture(slouch_landmarks)

        assert len(self.events) == 1
        assert self.events[0].type == EventType.POSTURE_BAD
        assert "slouch_angle" in self.events[0].data

    def test_posture_bad_emits_only_once(self) -> None:
        slouch_landmarks = _make_landmarks({
            11: _make_landmark(x=0.2, y=0.4),
            12: _make_landmark(x=0.8, y=0.4),
        })

        self.pipeline._analyze_posture(slouch_landmarks)
        self.pipeline._posture.bad_since = (
            time.time() - _BAD_POSTURE_SUSTAIN_SEC - 1.0
        )
        self.pipeline._analyze_posture(slouch_landmarks)
        self.pipeline._analyze_posture(slouch_landmarks)

        bad_events = [e for e in self.events if e.type == EventType.POSTURE_BAD]
        assert len(bad_events) == 1

    def test_recovery_emits_posture_good(self) -> None:
        """Returning to good posture after emitting bad emits POSTURE_GOOD."""
        self.pipeline._posture.emitted_bad = True

        good_landmarks = _make_landmarks()
        self.pipeline._analyze_posture(good_landmarks)
        self.pipeline._posture.good_since = (
            time.time() - _GOOD_POSTURE_RECOVERY_SEC - 1.0
        )
        self.pipeline._analyze_posture(good_landmarks)

        good_events = [e for e in self.events if e.type == EventType.POSTURE_GOOD]
        assert len(good_events) == 1

    def test_recovery_resets_emitted_bad_flag(self) -> None:
        self.pipeline._posture.emitted_bad = True
        self.pipeline._posture.good_since = (
            time.time() - _GOOD_POSTURE_RECOVERY_SEC - 1.0
        )

        good_landmarks = _make_landmarks()
        self.pipeline._analyze_posture(good_landmarks)

        assert self.pipeline._posture.emitted_bad is False


# ---------------------------------------------------------------------------
# Integration: phone analysis
# ---------------------------------------------------------------------------

class TestPhoneAnalysis:

    @pytest.fixture(autouse=True)
    def _setup(self) -> None:
        self.bus = EventBus()
        self.bus.clear()
        self.events = _collected_events(self.bus)
        self.pipeline = CVPipeline()

    def _phone_landmarks(self) -> list:
        """Landmarks simulating phone usage: head tilted, wrist raised."""
        avg_ear_y = 0.22
        return _make_landmarks({
            0: _make_landmark(x=0.5, y=avg_ear_y + _HEAD_TILT_OFFSET + 0.05),
            7: _make_landmark(x=0.45, y=avg_ear_y),
            8: _make_landmark(x=0.55, y=avg_ear_y),
            11: _make_landmark(x=0.4, y=0.4),
            12: _make_landmark(x=0.6, y=0.4),
            15: _make_landmark(x=0.45, y=0.3),   # wrist above shoulder y=0.4
            16: _make_landmark(x=0.55, y=0.65),   # other wrist below
        })

    def test_no_phone_emits_nothing(self) -> None:
        landmarks = _make_landmarks()
        self.pipeline._analyze_phone(landmarks)
        assert len(self.events) == 0

    def test_head_tilt_only_not_enough(self) -> None:
        """Head tilt without wrist raised does not trigger phone detection."""
        avg_ear_y = 0.22
        landmarks = _make_landmarks({
            0: _make_landmark(x=0.5, y=avg_ear_y + _HEAD_TILT_OFFSET + 0.05),
            7: _make_landmark(x=0.45, y=avg_ear_y),
            8: _make_landmark(x=0.55, y=avg_ear_y),
            15: _make_landmark(x=0.35, y=0.65),
            16: _make_landmark(x=0.65, y=0.65),
        })

        self.pipeline._analyze_phone(landmarks)
        assert len(self.events) == 0

    def test_wrist_raised_only_not_enough(self) -> None:
        """Raised wrist without head tilt does not trigger phone detection."""
        landmarks = _make_landmarks({
            0: _make_landmark(x=0.5, y=0.2),      # nose not tilted
            15: _make_landmark(x=0.45, y=0.3),     # wrist above shoulder
        })

        self.pipeline._analyze_phone(landmarks)
        assert len(self.events) == 0

    def test_phone_requires_sustained_duration(self) -> None:
        landmarks = self._phone_landmarks()
        self.pipeline._analyze_phone(landmarks)
        assert len(self.events) == 0
        assert self.pipeline._phone.detected_since is not None

    def test_sustained_phone_emits_phone_detected(self) -> None:
        landmarks = self._phone_landmarks()
        self.pipeline._analyze_phone(landmarks)
        self.pipeline._phone.detected_since = (
            time.time() - _PHONE_SUSTAIN_SEC - 1.0
        )
        self.pipeline._analyze_phone(landmarks)

        detected = [e for e in self.events if e.type == EventType.PHONE_DETECTED]
        assert len(detected) == 1

    def test_phone_detected_emits_only_once(self) -> None:
        landmarks = self._phone_landmarks()
        self.pipeline._analyze_phone(landmarks)
        self.pipeline._phone.detected_since = (
            time.time() - _PHONE_SUSTAIN_SEC - 1.0
        )
        self.pipeline._analyze_phone(landmarks)
        self.pipeline._analyze_phone(landmarks)

        detected = [e for e in self.events if e.type == EventType.PHONE_DETECTED]
        assert len(detected) == 1

    def test_phone_away_emits_after_recovery(self) -> None:
        self.pipeline._phone.emitted_detected = True

        normal_landmarks = _make_landmarks()
        self.pipeline._analyze_phone(normal_landmarks)
        self.pipeline._phone.away_since = (
            time.time() - _PHONE_RECOVERY_SEC - 1.0
        )
        self.pipeline._analyze_phone(normal_landmarks)

        away = [e for e in self.events if e.type == EventType.PHONE_AWAY]
        assert len(away) == 1

    def test_phone_away_resets_emitted_flag(self) -> None:
        self.pipeline._phone.emitted_detected = True
        self.pipeline._phone.away_since = (
            time.time() - _PHONE_RECOVERY_SEC - 1.0
        )

        normal_landmarks = _make_landmarks()
        self.pipeline._analyze_phone(normal_landmarks)

        assert self.pipeline._phone.emitted_detected is False


# ---------------------------------------------------------------------------
# Integration: CVPipeline lifecycle
# ---------------------------------------------------------------------------

class TestCVPipelineLifecycle:

    @pytest.fixture(autouse=True)
    def _setup(self) -> None:
        self.bus = EventBus()
        self.bus.clear()

    @patch("src.cv_pipeline.cv2")
    def test_start_opens_webcam_and_sets_resolution(self, mock_cv2: MagicMock) -> None:
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.read.return_value = (False, None)
        mock_cv2.VideoCapture.return_value = mock_cap

        pipeline = CVPipeline(webcam_index=1)

        with patch("src.cv_pipeline.threading.Thread") as mock_thread_cls:
            mock_thread = MagicMock()
            mock_thread_cls.return_value = mock_thread
            pipeline.start()

        mock_cv2.VideoCapture.assert_called_once_with(1)
        mock_cap.set.assert_any_call(mock_cv2.CAP_PROP_FRAME_WIDTH, 640)
        mock_cap.set.assert_any_call(mock_cv2.CAP_PROP_FRAME_HEIGHT, 480)

        pipeline._running = False

    @patch("src.cv_pipeline.cv2")
    def test_start_when_webcam_fails_does_not_crash(self, mock_cv2: MagicMock) -> None:
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = False
        mock_cv2.VideoCapture.return_value = mock_cap

        pipeline = CVPipeline()
        pipeline.start()

        assert pipeline._running is False

    def test_stop_releases_resources(self) -> None:
        pipeline = CVPipeline()
        mock_cap = MagicMock()
        pipeline._capture = mock_cap
        pipeline._running = False

        mock_pose = MagicMock()
        pipeline._pose = mock_pose

        pipeline.stop()

        mock_cap.release.assert_called_once()
        mock_pose.close.assert_called_once()
        assert pipeline._capture is None
        assert pipeline._pose is None

    def test_start_when_already_running_is_noop(self) -> None:
        pipeline = CVPipeline()
        pipeline._running = True

        pipeline.start()

        assert pipeline._capture is None

    @patch("src.cv_pipeline.cv2")
    def test_mediapipe_init_failure_does_not_crash(self, mock_cv2: MagicMock) -> None:
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cv2.VideoCapture.return_value = mock_cap

        with patch("src.cv_pipeline.threading.Thread") as mock_thread_cls:
            mock_thread = MagicMock()
            mock_thread_cls.return_value = mock_thread

            with patch.dict("sys.modules", {"mediapipe": None}):
                pipeline = CVPipeline()
                pipeline.start()

                assert pipeline._running is True
                assert pipeline._pose is None

        pipeline._running = False
