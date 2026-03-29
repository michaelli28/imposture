"""Pet state manager for the Wamm AI Desk Pet.

Tracks the pet's emotion, XP, focus sessions, and daily violation counts.
Subscribes to EventBus events and coordinates Arduino display output
through a Dispatcher reference.

All state transitions produce new PetState instances (frozen dataclass).
State is persisted to data/pet_state.json.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from src.events import Event, EventBus, EventType
from src.rules import RuleEngine

if TYPE_CHECKING:
    from src.dispatcher import Dispatcher

logger = logging.getLogger(__name__)

STATE_PATH = Path(__file__).resolve().parent.parent / "data" / "pet_state.json"


VALID_EMOTIONS = frozenset({
    "happy", "neutral", "concerned", "sad", "angry",
    "sleeping", "excited", "listening",
})

XP_LOSS_POSTURE = -5
XP_LOSS_PHONE = -10
XP_GAIN_FOCUS_TICK = 1


@dataclass(frozen=True)
class PetState:
    emotion: str = "neutral"
    xp: int = 0
    focus_active: bool = False
    focus_start_time: float | None = None
    break_active: bool = False
    violations_today: dict[str, int] = field(
        default_factory=lambda: {"posture_count": 0, "phone_count": 0}
    )


class PetStateManager:
    """Core brain of the Wamm desk pet."""

    def __init__(
        self,
        dispatcher: Dispatcher | None = None,
        rule_engine: RuleEngine | None = None,
        state_path: Path = STATE_PATH,
    ) -> None:
        self._dispatcher = dispatcher
        self._rule_engine = rule_engine or RuleEngine()
        self._state_path = state_path
        self._state: PetState = self._load()
        self._info_screen_index: int = 0

        bus = EventBus()
        handler_map: dict[EventType, Any] = {
            EventType.POSTURE_BAD: self._on_posture_bad,
            EventType.POSTURE_GOOD: self._on_posture_good,
            EventType.PHONE_DETECTED: self._on_phone_detected,
            EventType.PHONE_AWAY: self._on_phone_away,
            EventType.BUTTON_PRESS: self._on_button_press,
            EventType.SLEEPING: self._on_sleeping,
            EventType.AWAKE: self._on_awake,
            EventType.TIMER_START: self._on_timer_start,
            EventType.TIMER_END: self._on_timer_end,
        }
        for event_type, handler in handler_map.items():
            bus.subscribe(event_type, handler)

        logger.info(
            "PetStateManager initialized — xp=%d, emotion=%s",
            self._state.xp,
            self._state.emotion,
        )

    # -- Public API ----------------------------------------------------------

    @property
    def state(self) -> PetState:
        return self._state

    def get_state(self) -> dict[str, Any]:
        state_dict = asdict(self._state)
        if self._state.focus_active and self._state.focus_start_time is not None:
            state_dict["focus_elapsed"] = int(time.time() - self._state.focus_start_time)
        else:
            state_dict["focus_elapsed"] = 0
        state_dict["break_active"] = self._state.break_active
        return state_dict

    def tick(self) -> None:
        """Called periodically (every ~60s) to award focus XP and check stage."""
        if not self._state.focus_active:
            return

        new_xp = self._state.xp + XP_GAIN_FOCUS_TICK
        self._state = self._update_state(xp=new_xp)
        logger.debug("Focus tick: +%d XP (total %d)", XP_GAIN_FOCUS_TICK, new_xp)

        EventBus().emit(Event(
            type=EventType.XP_GAINED,
            timestamp=time.time(),
            data={"amount": XP_GAIN_FOCUS_TICK},
        ))
        self._persist()

    def start_focus(self) -> None:
        """Start a focus session."""
        self._state = self._update_state(
            focus_active=True,
            focus_start_time=time.time(),
            emotion="excited",
        )
        self._persist()
        self._dispatch_emotion()
        logger.info("Focus session started")

    def stop_focus(self) -> None:
        """Stop the current focus session."""
        self._state = self._update_state(
            focus_active=False,
            focus_start_time=None,
            break_active=False,
            emotion="happy",
        )
        self._persist()
        self._dispatch_emotion()
        logger.info("Focus session stopped")

    def start_break(self) -> None:
        """Start a break period (e.g. after Pomodoro focus)."""
        self._state = self._update_state(
            focus_active=False,
            break_active=True,
            emotion="happy",
        )
        self._persist()
        self._dispatch_emotion()
        logger.info("Break started")

    def stop_break(self) -> None:
        """End the break period."""
        self._state = self._update_state(
            break_active=False,
            emotion="happy",
        )
        self._persist()
        self._dispatch_emotion()
        logger.info("Break ended")

    def reset(self) -> None:
        """Reset all state to defaults."""
        self._state = PetState()
        self._persist()
        self._dispatch_emotion()
        logger.info("Pet state reset to defaults")

    def persist(self) -> None:
        """Public persistence hook for graceful shutdown."""
        self._persist()

    # -- Event handlers ------------------------------------------------------

    def _on_posture_bad(self, event: Event) -> None:
        matching_rules = self._rule_engine.match_event(event)

        # Use severity from CV pipeline if available, else from rules
        cv_severity = event.data.get("severity", "")
        if matching_rules:
            rule_severity = self._worst_severity(matching_rules)
        else:
            rule_severity = cv_severity or "moderate"

        severity = cv_severity or rule_severity
        score = event.data.get("score", 0)
        emotion = "sad" if severity == "strict" or score < 30 else "concerned"

        new_xp = max(0, self._state.xp + XP_LOSS_POSTURE)
        violations = {
            **self._state.violations_today,
            "posture_count": self._state.violations_today.get("posture_count", 0) + 1,
        }

        self._state = self._update_state(emotion=emotion, xp=new_xp, violations_today=violations)
        self._persist()

        EventBus().emit(Event(
            type=EventType.XP_LOST,
            timestamp=time.time(),
            data={"amount": abs(XP_LOSS_POSTURE)},
        ))
        logger.info(
            "Posture bad — score=%s, emotion=%s, xp=%d, severity=%s",
            score, emotion, new_xp, severity,
        )

        # Don't let posture alerts overwrite the phone alert on the display
        if self._dispatcher is not None and self._state.emotion != "angry":
            self._dispatcher.update_emotion(emotion)
            self._dispatcher.alert_posture(severity)

    def _on_posture_good(self, event: Event) -> None:
        # Don't override phone anger with posture good
        if self._state.emotion == "angry":
            logger.info("Posture good but phone still detected — keeping angry")
            return
        self._state = self._update_state(emotion="happy")
        self._persist()
        self._dispatch_emotion()
        logger.info("Posture good — emotion=happy")

    def _on_phone_detected(self, event: Event) -> None:
        matching_rules = self._rule_engine.match_event(event)
        worst_severity = self._worst_severity(matching_rules) if matching_rules else "moderate"

        # Only count as a new violation on the first detection (not already angry).
        # Subsequent detections while phone is still visible just keep alerting.
        if self._state.emotion != "angry":
            new_xp = max(0, self._state.xp + XP_LOSS_PHONE)
            violations = {
                **self._state.violations_today,
                "phone_count": self._state.violations_today.get("phone_count", 0) + 1,
            }

            self._state = self._update_state(emotion="angry", xp=new_xp, violations_today=violations)
            self._persist()

            EventBus().emit(Event(
                type=EventType.XP_LOST,
                timestamp=time.time(),
                data={"amount": abs(XP_LOSS_PHONE)},
            ))
            logger.info("Phone detected — emotion=angry, xp=%d", new_xp)

        # Always alert Arduino for continuous feedback while phone is visible
        if self._dispatcher is not None:
            self._dispatcher.update_emotion("angry")
            self._dispatcher.alert_phone(worst_severity)

    def _on_phone_away(self, event: Event) -> None:
        emotion = "happy" if self._state.xp > 0 else "neutral"
        self._state = self._update_state(emotion=emotion)
        self._persist()
        self._dispatch_emotion()
        logger.info("Phone away — emotion=%s", emotion)

    def _on_button_press(self, event: Event) -> None:
        screens = self._build_info_screens()
        self._info_screen_index = (self._info_screen_index + 1) % len(screens)
        screen = screens[self._info_screen_index]
        logger.info("Button press — showing screen %d: %s", self._info_screen_index, screen["title"])

        if self._dispatcher is not None:
            self._dispatcher.show_text(screen["title"], screen["body"])

    def _on_sleeping(self, event: Event) -> None:
        self._state = self._update_state(emotion="sleeping")
        self._persist()
        self._dispatch_emotion()
        logger.info("Sleeping detected — emotion=sleeping")

    def _on_awake(self, event: Event) -> None:
        self._state = self._update_state(emotion="happy")
        self._persist()
        self._dispatch_emotion()
        logger.info("Awake — emotion=happy")

    def _on_timer_start(self, event: Event) -> None:
        self.start_focus()

    def _on_timer_end(self, event: Event) -> None:
        self.stop_focus()
        if self._dispatcher is not None:
            self._dispatcher.celebrate()

    # -- Internal helpers ----------------------------------------------------

    def _dispatch_emotion(self) -> None:
        """Send current emotion to the Arduino via dispatcher."""
        if self._dispatcher is not None:
            self._dispatcher.update_emotion(self._state.emotion)

    def _update_state(self, **kwargs: Any) -> PetState:
        current = asdict(self._state)
        current.update(kwargs)
        return PetState(**current)

    def _worst_severity(self, rules: tuple[Any, ...]) -> str:
        severity_rank = {"gentle": 0, "moderate": 1, "strict": 2}
        return max((r.severity for r in rules), key=lambda s: severity_rank.get(s, 0))

    def _build_info_screens(self) -> list[dict[str, str]]:
        if self._state.focus_active and self._state.focus_start_time is not None:
            elapsed = int(time.time() - self._state.focus_start_time)
            minutes, seconds = divmod(elapsed, 60)
            focus_time = f"{minutes}m {seconds}s"
        elif self._state.break_active:
            focus_time = "On break"
        else:
            focus_time = "Not active"

        return [
            {"title": "XP", "body": f"{self._state.xp} XP"},
            {"title": "Focus", "body": focus_time},
        ]

    # -- Persistence ---------------------------------------------------------

    def _persist(self) -> None:
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = asdict(self._state)
        self._state_path.write_text(json.dumps(payload, indent=2))
        logger.debug("Persisted pet state to %s", self._state_path)

    def _load(self) -> PetState:
        if not self._state_path.exists():
            logger.info("No state file at %s — starting with defaults", self._state_path)
            return PetState()
        try:
            raw = json.loads(self._state_path.read_text())
            # Clear stale focus/break sessions that survived a restart
            if raw.get("focus_active"):
                raw["focus_active"] = False
                raw["focus_start_time"] = None
                logger.info("Cleared stale focus session from previous run")
            if raw.get("break_active"):
                raw["break_active"] = False
                logger.info("Cleared stale break session from previous run")
            raw.pop("stage", None)
            raw.setdefault("break_active", False)
            state = PetState(**raw)
            logger.info("Loaded pet state from %s", self._state_path)
            return state
        except (json.JSONDecodeError, TypeError, KeyError) as exc:
            logger.error("Failed to load pet state from %s: %s", self._state_path, exc)
            return PetState()
