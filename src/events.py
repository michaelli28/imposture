"""Event system for the Wamm AI Desk Pet.

Provides an EventType enum, immutable Event dataclass, and a thread-safe
EventBus singleton for pub/sub communication between subsystems (CV,
serial, wake-word, timers, rules engine).
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Callable

logger = logging.getLogger(__name__)


class EventType(Enum):
    POSTURE_GOOD = auto()
    POSTURE_BAD = auto()
    PHONE_DETECTED = auto()
    PHONE_AWAY = auto()
    BUTTON_PRESS = auto()
    WAKE_WORD = auto()
    VOICE_COMMAND = auto()
    TIMER_START = auto()
    TIMER_END = auto()
    RULE_ADDED = auto()
    RULE_REMOVED = auto()
    SLEEPING = auto()
    AWAKE = auto()
    XP_GAINED = auto()
    XP_LOST = auto()


@dataclass(frozen=True)
class Event:
    type: EventType
    timestamp: float
    data: dict = field(default_factory=dict)


Callback = Callable[[Event], None]


class EventBus:
    """Thread-safe publish/subscribe event bus (singleton)."""

    _instance: EventBus | None = None
    _init_lock: threading.Lock = threading.Lock()

    def __new__(cls) -> EventBus:
        with cls._init_lock:
            if cls._instance is None:
                instance = super().__new__(cls)
                instance._lock = threading.Lock()
                instance._subscribers: dict[EventType, list[Callback]] = {}
                cls._instance = instance
            return cls._instance

    def subscribe(self, event_type: EventType, callback: Callback) -> None:
        with self._lock:
            self._subscribers.setdefault(event_type, []).append(callback)
        logger.debug("Subscribed %s to %s", callback.__name__, event_type.name)

    def unsubscribe(self, event_type: EventType, callback: Callback) -> None:
        with self._lock:
            listeners = self._subscribers.get(event_type, [])
            try:
                listeners.remove(callback)
                logger.debug("Unsubscribed %s from %s", callback.__name__, event_type.name)
            except ValueError:
                logger.warning(
                    "Callback %s was not subscribed to %s",
                    callback.__name__,
                    event_type.name,
                )

    def emit(self, event: Event) -> None:
        with self._lock:
            listeners = list(self._subscribers.get(event.type, []))

        logger.debug("Emitting %s to %d listener(s)", event.type.name, len(listeners))
        for callback in listeners:
            try:
                callback(event)
            except Exception:
                logger.exception(
                    "Error in callback %s for event %s",
                    callback.__name__,
                    event.type.name,
                )

    def clear(self) -> None:
        """Remove all subscribers. Useful for testing."""
        with self._lock:
            self._subscribers.clear()
        logger.debug("All subscribers cleared")
