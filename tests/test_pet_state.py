"""Tests for the pet state manager."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from src.events import Event, EventBus, EventType
from src.pet_state import GROWTH_STAGES, PetState, PetStateManager
from src.rules import RuleEngine


@pytest.fixture()
def setup(tmp_path: Path) -> tuple[PetStateManager, RuleEngine, EventBus]:
    bus = EventBus()
    bus.clear()
    rules = RuleEngine(rules_path=tmp_path / "rules.json")
    manager = PetStateManager(
        dispatcher=None,
        rule_engine=rules,
        state_path=tmp_path / "pet_state.json",
    )
    return manager, rules, bus


class TestPetState:

    def test_default_state(self) -> None:
        state = PetState()
        assert state.stage == 0
        assert state.emotion == "neutral"
        assert state.xp == 0
        assert state.focus_active is False

    def test_state_is_frozen(self) -> None:
        state = PetState()
        with pytest.raises(AttributeError):
            state.xp = 10  # type: ignore


class TestPetStateManager:

    def test_initial_state(self, setup: tuple) -> None:
        manager, _, _ = setup
        assert manager.state.stage == 0
        assert manager.state.emotion == "neutral"

    def test_get_state_includes_stage_name(self, setup: tuple) -> None:
        manager, _, _ = setup
        state_dict = manager.get_state()
        assert state_dict["stage_name"] == "Egg"
        assert state_dict["next_stage_xp"] == 15

    def test_start_focus(self, setup: tuple) -> None:
        manager, _, _ = setup
        manager.start_focus()
        assert manager.state.focus_active is True
        assert manager.state.focus_start_time is not None
        assert manager.state.emotion == "excited"

    def test_stop_focus(self, setup: tuple) -> None:
        manager, _, _ = setup
        manager.start_focus()
        manager.stop_focus()
        assert manager.state.focus_active is False
        assert manager.state.focus_start_time is None

    def test_tick_gains_xp_during_focus(self, setup: tuple) -> None:
        manager, _, _ = setup
        manager.start_focus()
        initial_xp = manager.state.xp
        manager.tick()
        assert manager.state.xp == initial_xp + 1

    def test_tick_does_nothing_without_focus(self, setup: tuple) -> None:
        manager, _, _ = setup
        initial_xp = manager.state.xp
        manager.tick()
        assert manager.state.xp == initial_xp

    def test_posture_bad_event_with_rule(self, setup: tuple) -> None:
        manager, rules, bus = setup
        rules.add_rule(type="posture", description="Sit up", threshold={}, severity="moderate")

        bus.emit(Event(
            type=EventType.POSTURE_BAD,
            timestamp=time.time(),
            data={"score": 40, "severity": "moderate"},
        ))

        assert manager.state.emotion == "concerned"
        assert manager.state.violations_today["posture_count"] == 1

    def test_posture_bad_without_rule_uses_cv_severity(self, setup: tuple) -> None:
        manager, _, bus = setup

        bus.emit(Event(
            type=EventType.POSTURE_BAD,
            timestamp=time.time(),
            data={"score": 30, "severity": "strict"},
        ))

        # Even without rules, the CV severity triggers the emotion change
        assert manager.state.emotion == "sad"

    def test_phone_detected_with_rule(self, setup: tuple) -> None:
        manager, rules, bus = setup
        rules.add_rule(type="phone", description="No phone", threshold={}, severity="strict")

        bus.emit(Event(type=EventType.PHONE_DETECTED, timestamp=time.time()))

        assert manager.state.emotion == "angry"
        assert manager.state.violations_today["phone_count"] == 1

    def test_posture_good_resets_emotion(self, setup: tuple) -> None:
        manager, rules, bus = setup
        rules.add_rule(type="posture", description="Sit up", threshold={}, severity="moderate")

        bus.emit(Event(type=EventType.POSTURE_BAD, timestamp=time.time(), data={"score": 50}))
        bus.emit(Event(type=EventType.POSTURE_GOOD, timestamp=time.time()))

        assert manager.state.emotion == "happy"

    def test_stage_evolution(self, setup: tuple) -> None:
        manager, _, _ = setup
        manager.start_focus()
        # Simulate enough ticks to reach stage 1 (15 XP)
        for _ in range(16):
            manager.tick()
        assert manager.state.stage >= 1

    def test_persistence(self, tmp_path: Path) -> None:
        path = tmp_path / "pet_state.json"
        rules = RuleEngine(rules_path=tmp_path / "rules.json")

        m1 = PetStateManager(dispatcher=None, rule_engine=rules, state_path=path)
        m1.start_focus()
        for _ in range(5):
            m1.tick()
        m1.persist()

        m2 = PetStateManager(dispatcher=None, rule_engine=rules, state_path=path)
        assert m2.state.xp == 5
