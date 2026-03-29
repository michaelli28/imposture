"""Tests for the CV pipeline posture scoring and trackers."""

from __future__ import annotations

import time
from types import SimpleNamespace

import pytest

from src.cv_pipeline import (
    PostureStrikeTracker,
    PhoneTracker,
    _GOOD_POSTURE_RECOVERY_SEC,
    _BAD_POSTURE_WARN_SEC,
    _PHONE_ALERT_SEC,
    _PHONE_RECOVERY_SEC,
    _SCORE_BAD_THRESHOLD,
    _vertical_angle,
    absolute_score,
    compute_posture_score,
    extract_features,
    posture_label,
)
from src.events import Event, EventBus, EventType


# -- Helpers ---------------------------------------------------------------

def _make_landmark(x: float = 0.5, y: float = 0.5) -> SimpleNamespace:
    return SimpleNamespace(x=x, y=y, z=0.0)


def _upright_landmarks() -> list:
    """33-element list simulating upright posture."""
    default = _make_landmark(0.5, 0.5)
    lms = [default] * 33
    lms[0] = _make_landmark(0.5, 0.15)       # NOSE
    lms[7] = _make_landmark(0.45, 0.18)       # LEFT_EAR
    lms[8] = _make_landmark(0.55, 0.18)       # RIGHT_EAR
    lms[11] = _make_landmark(0.35, 0.35)      # LEFT_SHOULDER
    lms[12] = _make_landmark(0.65, 0.35)      # RIGHT_SHOULDER
    lms[23] = _make_landmark(0.40, 0.70)      # LEFT_HIP
    lms[24] = _make_landmark(0.60, 0.70)      # RIGHT_HIP
    return lms


def _slouching_landmarks() -> list:
    """Landmarks with significant forward lean and head droop."""
    lms = _upright_landmarks()
    lms[11] = _make_landmark(0.20, 0.35)      # LEFT_SHOULDER shifted far left
    lms[12] = _make_landmark(0.50, 0.35)      # RIGHT_SHOULDER shifted left
    lms[0] = _make_landmark(0.15, 0.30)       # NOSE far forward
    lms[7] = _make_landmark(0.10, 0.28)       # LEFT_EAR forward
    lms[8] = _make_landmark(0.20, 0.28)       # RIGHT_EAR forward
    return lms


def _collected_events(bus: EventBus) -> list[Event]:
    events: list[Event] = []
    for et in (EventType.POSTURE_BAD, EventType.POSTURE_GOOD,
               EventType.PHONE_DETECTED, EventType.PHONE_AWAY):
        bus.subscribe(et, events.append)
    return events


# -- Scoring tests ---------------------------------------------------------

class TestPostureScoring:

    def test_upright_posture_scores_high(self) -> None:
        lms = _upright_landmarks()
        score, _ = compute_posture_score(lms, 640, 480)
        assert score >= 70, f"Upright should score >= 70, got {score}"

    def test_slouching_scores_low(self) -> None:
        lms = _slouching_landmarks()
        score, _ = compute_posture_score(lms, 640, 480)
        assert score < 70, f"Slouching should score < 70, got {score}"

    def test_score_returns_metrics(self) -> None:
        lms = _upright_landmarks()
        _, metrics = compute_posture_score(lms, 640, 480)
        assert "spine_angle_deg" in metrics
        assert "neck_angle_deg" in metrics
        assert "ear_forward_norm" in metrics

    def test_reference_improves_scoring(self) -> None:
        lms = _upright_landmarks()
        ref = extract_features(lms, 640, 480)
        score_with_ref, _ = compute_posture_score(lms, 640, 480, reference=ref)
        assert score_with_ref >= 95, "Perfect match to reference should score ~100"


class TestPostureLabel:

    def test_excellent(self) -> None:
        assert posture_label(90) == "Excellent"

    def test_good(self) -> None:
        assert posture_label(75) == "Good"

    def test_fair(self) -> None:
        assert posture_label(55) == "Fair"

    def test_poor(self) -> None:
        assert posture_label(35) == "Poor"

    def test_very_poor(self) -> None:
        assert posture_label(10) == "Very Poor"


class TestVerticalAngle:

    def test_vertical_is_zero(self) -> None:
        angle = _vertical_angle((0, 0), (0, 10))
        assert angle == pytest.approx(0.0, abs=0.5)

    def test_horizontal_is_ninety(self) -> None:
        angle = _vertical_angle((0, 0), (10, 0))
        assert angle == pytest.approx(90.0, abs=0.5)


# -- Posture tracker tests ------------------------------------------------

class TestPostureStrikeTracker:

    @pytest.fixture(autouse=True)
    def _setup(self) -> None:
        self.bus = EventBus()
        self.bus.clear()
        self.events = _collected_events(self.bus)

    def test_good_score_emits_nothing(self) -> None:
        tracker = PostureStrikeTracker()
        tracker.update(85.0, self.bus, {})
        assert len(self.events) == 0

    def test_bad_score_under_threshold_emits_nothing(self) -> None:
        tracker = PostureStrikeTracker()
        tracker.update(50.0, self.bus, {})
        assert len(self.events) == 0
        assert tracker.bad_since is not None

    def test_sustained_bad_emits_posture_bad(self) -> None:
        tracker = PostureStrikeTracker()
        tracker.update(50.0, self.bus, {})
        tracker.bad_since = time.time() - _BAD_POSTURE_WARN_SEC - 1
        tracker.update(50.0, self.bus, {"spine_angle_deg": 25.0})

        bad_events = [e for e in self.events if e.type == EventType.POSTURE_BAD]
        assert len(bad_events) == 1
        assert bad_events[0].data["score"] == 50.0

    def test_posture_bad_emits_only_once(self) -> None:
        tracker = PostureStrikeTracker()
        tracker.update(50.0, self.bus, {})
        tracker.bad_since = time.time() - _BAD_POSTURE_WARN_SEC - 1
        tracker.update(50.0, self.bus, {})
        tracker.update(50.0, self.bus, {})

        bad_events = [e for e in self.events if e.type == EventType.POSTURE_BAD]
        assert len(bad_events) == 1

    def test_recovery_emits_posture_good(self) -> None:
        tracker = PostureStrikeTracker()
        tracker._emitted_bad = True
        tracker.update(85.0, self.bus, {})
        tracker._good_since = time.time() - _GOOD_POSTURE_RECOVERY_SEC - 1
        tracker.update(85.0, self.bus, {"spine_angle_deg": 5.0})

        good_events = [e for e in self.events if e.type == EventType.POSTURE_GOOD]
        assert len(good_events) == 1

    def test_recovery_resets_emitted_flag(self) -> None:
        tracker = PostureStrikeTracker()
        tracker._emitted_bad = True
        tracker._good_since = time.time() - _GOOD_POSTURE_RECOVERY_SEC - 1
        tracker.update(85.0, self.bus, {})
        assert tracker._emitted_bad is False


# -- Phone tracker tests ---------------------------------------------------

class TestPhoneTracker:

    @pytest.fixture(autouse=True)
    def _setup(self) -> None:
        self.bus = EventBus()
        self.bus.clear()
        self.events = _collected_events(self.bus)

    def test_no_phone_emits_nothing(self) -> None:
        tracker = PhoneTracker()
        tracker.update(False, self.bus)
        assert len(self.events) == 0

    def test_sustained_phone_emits_detected(self) -> None:
        tracker = PhoneTracker()
        tracker.last_tick = time.time() - _PHONE_ALERT_SEC - 1
        tracker.update(True, self.bus)

        detected = [e for e in self.events if e.type == EventType.PHONE_DETECTED]
        assert len(detected) == 1

    def test_phone_away_after_detection(self) -> None:
        tracker = PhoneTracker()
        tracker._emitted_detected = True
        tracker._away_since = time.time() - _PHONE_RECOVERY_SEC - 1
        tracker.update(False, self.bus)

        away = [e for e in self.events if e.type == EventType.PHONE_AWAY]
        assert len(away) == 1
