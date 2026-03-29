"""Rule engine for the Wamm AI Desk Pet.

Manages user-defined behavioral rules (posture, phone, timer, custom)
with JSON persistence. Rules are frozen dataclasses — updates produce
new instances rather than mutating existing ones.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.events import Event, EventType

logger = logging.getLogger(__name__)

RULES_PATH = Path(__file__).resolve().parent.parent / "data" / "rules.json"

VALID_TYPES = frozenset({"posture", "phone", "timer", "custom"})
VALID_SEVERITIES = frozenset({"gentle", "moderate", "strict"})

EVENT_TYPE_TO_RULE_TYPE: dict[EventType, str] = {
    EventType.POSTURE_BAD: "posture",
    EventType.POSTURE_GOOD: "posture",
    EventType.PHONE_DETECTED: "phone",
    EventType.PHONE_AWAY: "phone",
    EventType.TIMER_START: "timer",
    EventType.TIMER_END: "timer",
}


@dataclass(frozen=True)
class Rule:
    id: str
    type: str
    description: str
    threshold: dict[str, Any]
    severity: str
    active: bool
    created_at: str


class RuleEngine:
    """Manages behavioral rules with JSON file persistence."""

    def __init__(self, rules_path: Path = RULES_PATH) -> None:
        self._rules_path = rules_path
        self._rules: tuple[Rule, ...] = self._load()

    def add_rule(
        self,
        type: str,
        description: str,
        threshold: dict[str, Any],
        severity: str,
    ) -> Rule:
        if type not in VALID_TYPES:
            raise ValueError(f"Invalid rule type '{type}'. Must be one of {VALID_TYPES}")
        if severity not in VALID_SEVERITIES:
            raise ValueError(f"Invalid severity '{severity}'. Must be one of {VALID_SEVERITIES}")

        rule = Rule(
            id=str(uuid4()),
            type=type,
            description=description,
            threshold=dict(threshold),
            severity=severity,
            active=True,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self._rules = (*self._rules, rule)
        self._persist()
        logger.info("Added rule %s: %s", rule.id, rule.description)
        return rule

    def remove_rule(self, rule_id: str) -> None:
        original_count = len(self._rules)
        self._rules = tuple(r for r in self._rules if r.id != rule_id)
        if len(self._rules) == original_count:
            raise KeyError(f"Rule '{rule_id}' not found")
        self._persist()
        logger.info("Removed rule %s", rule_id)

    def update_rule(self, rule_id: str, **kwargs: Any) -> Rule:
        forbidden = {"id", "created_at"}
        invalid_keys = forbidden & set(kwargs)
        if invalid_keys:
            raise ValueError(f"Cannot update fields: {invalid_keys}")

        if "type" in kwargs and kwargs["type"] not in VALID_TYPES:
            raise ValueError(f"Invalid rule type '{kwargs['type']}'. Must be one of {VALID_TYPES}")
        if "severity" in kwargs and kwargs["severity"] not in VALID_SEVERITIES:
            raise ValueError(
                f"Invalid severity '{kwargs['severity']}'. Must be one of {VALID_SEVERITIES}"
            )

        updated_rules: list[Rule] = []
        found = False
        for rule in self._rules:
            if rule.id == rule_id:
                found = True
                fields = asdict(rule)
                fields.update(kwargs)
                updated_rules.append(Rule(**fields))
            else:
                updated_rules.append(rule)

        if not found:
            raise KeyError(f"Rule '{rule_id}' not found")

        self._rules = tuple(updated_rules)
        self._persist()
        updated = next(r for r in self._rules if r.id == rule_id)
        logger.info("Updated rule %s", rule_id)
        return updated

    def toggle_rule(self, rule_id: str) -> Rule:
        return self.update_rule(rule_id, active=not self._find_rule(rule_id).active)

    def get_rules(self) -> tuple[Rule, ...]:
        return self._rules

    def get_active_rules(self, type: str | None = None) -> tuple[Rule, ...]:
        return tuple(
            r
            for r in self._rules
            if r.active and (type is None or r.type == type)
        )

    def match_event(self, event: Event) -> tuple[Rule, ...]:
        rule_type = EVENT_TYPE_TO_RULE_TYPE.get(event.type)
        if rule_type is None:
            return ()
        return self.get_active_rules(type=rule_type)

    def _find_rule(self, rule_id: str) -> Rule:
        for rule in self._rules:
            if rule.id == rule_id:
                return rule
        raise KeyError(f"Rule '{rule_id}' not found")

    def _persist(self) -> None:
        self._rules_path.parent.mkdir(parents=True, exist_ok=True)
        payload = [asdict(r) for r in self._rules]
        self._rules_path.write_text(json.dumps(payload, indent=2))
        logger.debug("Persisted %d rules to %s", len(self._rules), self._rules_path)

    def _load(self) -> tuple[Rule, ...]:
        if not self._rules_path.exists():
            logger.info("No rules file at %s — starting with empty rule set", self._rules_path)
            return ()
        try:
            raw = json.loads(self._rules_path.read_text())
            rules = tuple(Rule(**entry) for entry in raw)
            logger.info("Loaded %d rules from %s", len(rules), self._rules_path)
            return rules
        except (json.JSONDecodeError, TypeError, KeyError) as exc:
            logger.error("Failed to load rules from %s: %s", self._rules_path, exc)
            return ()
