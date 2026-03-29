"""Tests for the rule engine."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from src.events import Event, EventType
from src.rules import Rule, RuleEngine


@pytest.fixture()
def engine(tmp_path: Path) -> RuleEngine:
    return RuleEngine(rules_path=tmp_path / "rules.json")


class TestRuleEngine:

    def test_add_rule(self, engine: RuleEngine) -> None:
        rule = engine.add_rule(
            type="posture",
            description="Sit up straight",
            threshold={"duration_seconds": 5},
            severity="moderate",
        )
        assert rule.type == "posture"
        assert rule.active is True
        assert len(engine.get_rules()) == 1

    def test_remove_rule(self, engine: RuleEngine) -> None:
        rule = engine.add_rule(type="phone", description="No phone", threshold={}, severity="strict")
        engine.remove_rule(rule.id)
        assert len(engine.get_rules()) == 0

    def test_remove_nonexistent_raises(self, engine: RuleEngine) -> None:
        with pytest.raises(KeyError):
            engine.remove_rule("nonexistent-id")

    def test_toggle_rule(self, engine: RuleEngine) -> None:
        rule = engine.add_rule(type="posture", description="Test", threshold={}, severity="gentle")
        toggled = engine.toggle_rule(rule.id)
        assert toggled.active is False
        toggled_again = engine.toggle_rule(rule.id)
        assert toggled_again.active is True

    def test_get_active_rules_filters(self, engine: RuleEngine) -> None:
        engine.add_rule(type="posture", description="A", threshold={}, severity="gentle")
        r2 = engine.add_rule(type="phone", description="B", threshold={}, severity="moderate")
        engine.toggle_rule(r2.id)

        active = engine.get_active_rules()
        assert len(active) == 1
        assert active[0].type == "posture"

    def test_get_active_rules_by_type(self, engine: RuleEngine) -> None:
        engine.add_rule(type="posture", description="A", threshold={}, severity="gentle")
        engine.add_rule(type="phone", description="B", threshold={}, severity="moderate")

        posture_rules = engine.get_active_rules(type="posture")
        assert len(posture_rules) == 1

    def test_match_event(self, engine: RuleEngine) -> None:
        engine.add_rule(type="posture", description="A", threshold={}, severity="gentle")
        engine.add_rule(type="phone", description="B", threshold={}, severity="moderate")

        event = Event(type=EventType.POSTURE_BAD, timestamp=time.time())
        matches = engine.match_event(event)
        assert len(matches) == 1
        assert matches[0].type == "posture"

    def test_invalid_type_raises(self, engine: RuleEngine) -> None:
        with pytest.raises(ValueError):
            engine.add_rule(type="invalid", description="X", threshold={}, severity="gentle")

    def test_invalid_severity_raises(self, engine: RuleEngine) -> None:
        with pytest.raises(ValueError):
            engine.add_rule(type="posture", description="X", threshold={}, severity="extreme")

    def test_persistence_survives_reload(self, tmp_path: Path) -> None:
        path = tmp_path / "rules.json"
        engine1 = RuleEngine(rules_path=path)
        engine1.add_rule(type="posture", description="Persist me", threshold={}, severity="strict")

        engine2 = RuleEngine(rules_path=path)
        assert len(engine2.get_rules()) == 1
        assert engine2.get_rules()[0].description == "Persist me"
