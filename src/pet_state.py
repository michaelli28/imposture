"""Pet state manager for the Buddy AI Desk Pet.

Tracks the pet's growth stage, emotion, XP, focus sessions, and daily
violation counts. Subscribes to EventBus events and coordinates
Arduino display output through a Dispatcher reference.

All state transitions produce new PetState instances (frozen dataclass).
State is persisted to data/pet_state.json.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, NamedTuple

from src.events import Event, EventBus, EventType
from src.rules import RuleEngine

if TYPE_CHECKING:
    from src.dispatcher import Dispatcher

logger = logging.getLogger(__name__)

STATE_PATH = Path(__file__).resolve().parent.parent / "data" / "pet_state.json"


class GrowthStage(NamedTuple):
    index: int
    name: str
    xp_threshold: int


GROWTH_STAGES: tuple[GrowthStage, ...] = (
    GrowthStage(index=0, name="Egg", xp_threshold=0),
    GrowthStage(index=1, name="Hatchling", xp_threshold=15),
    GrowthStage(index=2, name="Kid", xp_threshold=60),
    GrowthStage(index=3, name="Teen", xp_threshold=180),
    GrowthStage(index=4, name="Adult", xp_threshold=360),
)

VALID_EMOTIONS = frozenset({
    "happy", "neutral", "concerned", "sad", "angry",
    "sleeping", "excited", "listening",
})

XP_LOSS_POSTURE = -5
XP_LOSS_PHONE = -10
XP_GAIN_FOCUS_TICK = 1


@dataclass(frozen=True)
class PetState:
    stage: int = 0
    emotion: str = "neutral"
    xp: int = 0
    focus_active: bool = False
    focus_start_time: float | None = None
    violations_today: dict[str, int] = field(
        default_factory=lambda: {"posture_count": 0, "phone_count": 0}
    )


class PetStateManager:
    """Core brain of the Buddy desk pet."""

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
            EventType.TIMER_START: self._on_timer_start,
            EventType.TIMER_END: self._on_timer_end,
            EventType.LIGHT_LOW: self._on_light_low,
            EventType.TEMP_COLD: self._on_temp_cold,
            EventType.TEMP_HOT: self._on_temp_hot,
        }
        for event_type, handler in handler_map.items():
            bus.subscribe(event_type, handler)

        logger.info(
            "PetStateManager initialized — stage=%d, xp=%d, emotion=%s",
            self._state.stage,
            self._state.xp,
            self._state.emotion,
        )

    # -- Public API ----------------------------------------------------------

    @property
    def state(self) -> PetState:
        return self._state

    def get_state(self) -> dict[str, Any]:
        state_dict = asdict(self._state)
        state_dict["stage_name"] = GROWTH_STAGES[self._state.stage].name
        state_dict["next_stage_xp"] = (
            GROWTH_STAGES[self._state.stage + 1].xp_threshold
            if self._state.stage < len(GROWTH_STAGES) - 1
            else None
        )
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
        self._check_stage()
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
            emotion="happy",
        )
        self._persist()
        self._dispatch_emotion()
        logger.info("Focus session stopped")

    def persist(self) -> None:
        """Public persistence hook for graceful shutdown."""
        self._persist()

    # -- Event handlers ------------------------------------------------------

    def _on_posture_bad(self, event: Event) -> None:
        matching_rules = self._rule_engine.match_event(event)
        if not matching_rules:
            return

        worst_severity = self._worst_severity(matching_rules)
        emotion = "sad" if worst_severity == "strict" else "concerned"

        new_xp = max(0, self._state.xp + XP_LOSS_POSTURE)
        violations = {
            **self._state.violations_today,
            "posture_count": self._state.violations_today.get("posture_count", 0) + 1,
        }

        self._state = self._update_state(emotion=emotion, xp=new_xp, violations_today=violations)
        self._check_stage()
        self._persist()

        EventBus().emit(Event(
            type=EventType.XP_LOST,
            timestamp=time.time(),
            data={"amount": abs(XP_LOSS_POSTURE)},
        ))
        logger.info("Posture bad — emotion=%s, xp=%d, severity=%s", emotion, new_xp, worst_severity)

        if self._dispatcher is not None:
            self._dispatcher.update_emotion(self._state.stage, emotion)
            self._dispatcher.alert_posture(worst_severity)

    def _on_posture_good(self, event: Event) -> None:
        self._state = self._update_state(emotion="happy")
        self._persist()
        self._dispatch_emotion()
        logger.info("Posture good — emotion=happy")

    def _on_phone_detected(self, event: Event) -> None:
        matching_rules = self._rule_engine.match_event(event)
        if not matching_rules:
            return

        worst_severity = self._worst_severity(matching_rules)
        new_xp = max(0, self._state.xp + XP_LOSS_PHONE)
        violations = {
            **self._state.violations_today,
            "phone_count": self._state.violations_today.get("phone_count", 0) + 1,
        }

        self._state = self._update_state(emotion="angry", xp=new_xp, violations_today=violations)
        self._check_stage()
        self._persist()

        EventBus().emit(Event(
            type=EventType.XP_LOST,
            timestamp=time.time(),
            data={"amount": abs(XP_LOSS_PHONE)},
        ))
        logger.info("Phone detected — emotion=angry, xp=%d", new_xp)

        if self._dispatcher is not None:
            self._dispatcher.update_emotion(self._state.stage, "angry")
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

    def _on_timer_start(self, event: Event) -> None:
        self.start_focus()

    def _on_timer_end(self, event: Event) -> None:
        self.stop_focus()
        if self._dispatcher is not None:
            self._dispatcher.celebrate()

    def _on_light_low(self, event: Event) -> None:
        self._state = self._update_state(emotion="concerned")
        self._persist()
        self._dispatch_emotion()
        logger.info("Light low — emotion=concerned")

    def _on_temp_cold(self, event: Event) -> None:
        self._state = self._update_state(emotion="concerned")
        self._persist()
        self._dispatch_emotion()
        logger.info("Temp cold — emotion=concerned")

    def _on_temp_hot(self, event: Event) -> None:
        self._state = self._update_state(emotion="concerned")
        self._persist()
        self._dispatch_emotion()
        logger.info("Temp hot — emotion=concerned")

    # -- Internal helpers ----------------------------------------------------

    def _dispatch_emotion(self) -> None:
        """Send current emotion to the Arduino via dispatcher."""
        if self._dispatcher is not None:
            self._dispatcher.update_emotion(self._state.stage, self._state.emotion)

    def _update_state(self, **kwargs: Any) -> PetState:
        current = asdict(self._state)
        current.update(kwargs)
        return PetState(**current)

    def _check_stage(self) -> None:
        current_stage = self._state.stage
        xp = self._state.xp

        if current_stage < len(GROWTH_STAGES) - 1:
            next_threshold = GROWTH_STAGES[current_stage + 1].xp_threshold
            if xp >= next_threshold:
                new_stage = current_stage + 1
                self._state = self._update_state(stage=new_stage, emotion="excited")
                self._persist()
                logger.info(
                    "Stage UP: %s -> %s (xp=%d)",
                    GROWTH_STAGES[current_stage].name,
                    GROWTH_STAGES[new_stage].name,
                    xp,
                )
                EventBus().emit(Event(
                    type=EventType.STAGE_UP,
                    timestamp=time.time(),
                    data={"old_stage": current_stage, "new_stage": new_stage},
                ))
                if self._dispatcher is not None:
                    self._dispatcher.celebrate()
                return

        if current_stage > 0:
            current_threshold = GROWTH_STAGES[current_stage].xp_threshold
            if xp < current_threshold:
                new_stage = current_stage - 1
                self._state = self._update_state(stage=new_stage, emotion="sad")
                self._persist()
                logger.info(
                    "Stage DOWN: %s -> %s (xp=%d)",
                    GROWTH_STAGES[current_stage].name,
                    GROWTH_STAGES[new_stage].name,
                    xp,
                )
                EventBus().emit(Event(
                    type=EventType.STAGE_DOWN,
                    timestamp=time.time(),
                    data={"old_stage": current_stage, "new_stage": new_stage},
                ))
                self._dispatch_emotion()

    def _worst_severity(self, rules: tuple[Any, ...]) -> str:
        severity_rank = {"gentle": 0, "moderate": 1, "strict": 2}
        return max((r.severity for r in rules), key=lambda s: severity_rank.get(s, 0))

    def _build_info_screens(self) -> list[dict[str, str]]:
        stage = GROWTH_STAGES[self._state.stage]
        if self._state.focus_active and self._state.focus_start_time is not None:
            elapsed = int(time.time() - self._state.focus_start_time)
            minutes, seconds = divmod(elapsed, 60)
            focus_time = f"{minutes}m {seconds}s"
        else:
            focus_time = "Not active"

        return [
            {"title": "XP", "body": f"{self._state.xp} XP"},
            {"title": "Stage", "body": f"{stage.name} ({stage.index}/4)"},
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
            state = PetState(**raw)
            logger.info("Loaded pet state from %s", self._state_path)
            return state
        except (json.JSONDecodeError, TypeError, KeyError) as exc:
            logger.error("Failed to load pet state from %s: %s", self._state_path, exc)
            return PetState()
