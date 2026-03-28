"""Buddy AI Desk Pet — Main Orchestrator.

Launches all subsystems and manages graceful shutdown.
"""

import logging
import os
import signal
import sys
import threading
import time

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("buddy")


def main() -> None:
    logger.info("=== Buddy AI Desk Pet starting ===")

    # Import after dotenv so env vars are available
    from src.cv_pipeline import CVPipeline
    from src.dispatcher import Dispatcher
    from src.events import Event, EventBus, EventType
    from src.llm_processor import LLMProcessor
    from src.pet_state import PetStateManager
    from src.rules import RuleEngine
    from src.serial_comm import SerialComm
    from src.stt import SpeechToText
    from src.tts import TextToSpeech
    from src.wake_word import WakeWordListener

    event_bus = EventBus()
    shutdown_event = threading.Event()

    # --- Initialize subsystems ---
    serial_port = os.getenv("ARDUINO_SERIAL_PORT", "")
    baud_rate = int(os.getenv("ARDUINO_BAUD_RATE", "9600"))
    serial_comm = SerialComm(port=serial_port, baud_rate=baud_rate)

    rule_engine = RuleEngine()
    dispatcher = Dispatcher(serial_comm)
    pet_state_manager = PetStateManager(
        dispatcher=dispatcher,
        rule_engine=rule_engine,
    )

    webcam_index = int(os.getenv("WEBCAM_INDEX", "0"))
    cv_pipeline = CVPipeline(webcam_index=webcam_index)

    stt = SpeechToText()
    tts = TextToSpeech()
    llm_processor = LLMProcessor(
        rule_engine=rule_engine,
        pet_state_manager=pet_state_manager,
    )

    # --- Voice command handler ---
    def handle_voice_command() -> None:
        """Record, transcribe, process via LLM, speak response, execute action."""
        logger.info("Listening for voice command...")
        dispatcher.update_emotion(pet_state_manager.state.stage, "listening")

        text = stt.listen_and_transcribe()
        if not text:
            logger.warning("No speech detected")
            dispatcher.update_emotion(
                pet_state_manager.state.stage, pet_state_manager.state.emotion
            )
            return

        logger.info("Transcribed: %s", text)
        result = llm_processor.process_command(text)

        action = result.get("action", "respond")
        reply = result.get("reply", "")

        if action == "add_rule":
            rule_data = result.get("rule", {})
            if rule_data:
                rule_engine.add_rule(
                    type=rule_data.get("type", "custom"),
                    description=rule_data.get("description", text),
                    threshold=rule_data.get("threshold", {}),
                    severity=rule_data.get("severity", "moderate"),
                )
                logger.info("Rule added via voice")
                event_bus.emit(Event(type=EventType.RULE_ADDED, timestamp=time.time()))
        elif action == "remove_rule":
            rule_id = result.get("rule", {}).get("id", "")
            if rule_id:
                rule_engine.remove_rule(rule_id)
                event_bus.emit(Event(type=EventType.RULE_REMOVED, timestamp=time.time()))
        elif action == "start_timer":
            duration = result.get("rule", {}).get("duration", 1500)
            _start_focus_timer(pet_state_manager, dispatcher, duration, shutdown_event)
        elif action == "stop_timer":
            pet_state_manager.stop_focus()

        if reply:
            tts.speak(reply)

        dispatcher.update_emotion(
            pet_state_manager.state.stage, pet_state_manager.state.emotion
        )

    wake_word_listener = WakeWordListener(on_wake=handle_voice_command)

    # --- Connect serial ---
    logger.info("Connecting to Arduino...")
    serial_comm.connect()
    serial_comm.start_reading()
    logger.info("Serial connected")

    # --- Start CV pipeline ---
    logger.info("Starting CV pipeline...")
    cv_pipeline.start()

    # --- Start wake word listener ---
    logger.info("Starting wake word listener...")
    wake_word_listener.start()

    # --- Boot animation ---
    dispatcher.update_emotion(0, "excited")
    time.sleep(1)
    dispatcher.update_emotion(
        pet_state_manager.state.stage, pet_state_manager.state.emotion
    )

    # --- Start dashboard in background thread ---
    def run_dashboard() -> None:
        from src.dashboard.app import start_server

        start_server(pet_state_manager, rule_engine)

    dashboard_thread = threading.Thread(target=run_dashboard, daemon=True)
    dashboard_thread.start()
    logger.info("Dashboard started on port %s", os.getenv("DASHBOARD_PORT", "8080"))

    # --- XP tick thread ---
    def xp_tick_loop() -> None:
        while not shutdown_event.is_set():
            pet_state_manager.tick()
            shutdown_event.wait(60)

    tick_thread = threading.Thread(target=xp_tick_loop, daemon=True)
    tick_thread.start()

    # --- Graceful shutdown ---
    def shutdown(signum: int, frame: object) -> None:
        logger.info("Shutting down (signal %d)...", signum)
        shutdown_event.set()
        wake_word_listener.stop()
        cv_pipeline.stop()
        serial_comm.disconnect()
        pet_state_manager.persist()
        logger.info("=== Buddy shut down cleanly ===")
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    logger.info("=== Buddy is alive! Say 'Hey Buddy' to interact ===")

    # Keep main thread alive
    while not shutdown_event.is_set():
        shutdown_event.wait(1)


def _start_focus_timer(
    pet_state_manager: "PetStateManager",
    dispatcher: "Dispatcher",
    duration_seconds: int,
    shutdown_event: threading.Event,
) -> None:
    """Start a focus timer in a background thread."""
    import time as _time

    from src.events import Event, EventBus, EventType

    pet_state_manager.start_focus()

    def timer_loop() -> None:
        remaining = duration_seconds
        while remaining > 0 and not shutdown_event.is_set():
            minutes = remaining // 60
            seconds = remaining % 60
            dispatcher.show_text(f"Focus: {minutes:02d}:{seconds:02d}", "Stay focused!")
            shutdown_event.wait(1)
            remaining -= 1

        if not shutdown_event.is_set():
            pet_state_manager.stop_focus()
            dispatcher.update_emotion(pet_state_manager.state.stage, "excited")
            EventBus().emit(Event(type=EventType.TIMER_END, timestamp=_time.time()))

    timer_thread = threading.Thread(target=timer_loop, daemon=True)
    timer_thread.start()


if __name__ == "__main__":
    main()
