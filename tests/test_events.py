"""Tests for the EventBus system."""

from __future__ import annotations

import time

from src.events import Event, EventBus, EventType


class TestEventBus:

    def setup_method(self) -> None:
        bus = EventBus()
        bus.clear()

    def test_subscribe_and_emit(self) -> None:
        bus = EventBus()
        received: list[Event] = []
        bus.subscribe(EventType.POSTURE_BAD, received.append)

        event = Event(type=EventType.POSTURE_BAD, timestamp=time.time())
        bus.emit(event)

        assert len(received) == 1
        assert received[0] is event

    def test_emit_only_notifies_matching_subscribers(self) -> None:
        bus = EventBus()
        posture_events: list[Event] = []
        phone_events: list[Event] = []
        bus.subscribe(EventType.POSTURE_BAD, posture_events.append)
        bus.subscribe(EventType.PHONE_DETECTED, phone_events.append)

        bus.emit(Event(type=EventType.POSTURE_BAD, timestamp=time.time()))

        assert len(posture_events) == 1
        assert len(phone_events) == 0

    def test_unsubscribe(self) -> None:
        bus = EventBus()
        received: list[Event] = []
        bus.subscribe(EventType.POSTURE_BAD, received.append)
        bus.unsubscribe(EventType.POSTURE_BAD, received.append)

        bus.emit(Event(type=EventType.POSTURE_BAD, timestamp=time.time()))
        assert len(received) == 0

    def test_callback_exception_does_not_crash_bus(self) -> None:
        bus = EventBus()
        good: list[Event] = []

        def bad_callback(event: Event) -> None:
            raise ValueError("boom")

        bus.subscribe(EventType.POSTURE_BAD, bad_callback)
        bus.subscribe(EventType.POSTURE_BAD, good.append)

        bus.emit(Event(type=EventType.POSTURE_BAD, timestamp=time.time()))
        assert len(good) == 1

    def test_event_data_defaults_to_empty(self) -> None:
        event = Event(type=EventType.POSTURE_GOOD, timestamp=1.0)
        assert event.data == {}

    def test_event_is_frozen(self) -> None:
        event = Event(type=EventType.POSTURE_GOOD, timestamp=1.0)
        with __import__("pytest").raises(AttributeError):
            event.type = EventType.POSTURE_BAD  # type: ignore
