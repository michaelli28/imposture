"""LLM command processing for the Wamm AI Desk Pet.

Sends voice-transcribed text to a Lava API gateway (OpenAI-compatible)
and parses structured JSON responses describing actions Wamm should take.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import openai
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

DEFAULT_MODEL: str = "default"


class LLMProcessor:
    """Process natural-language commands for Wamm via a Lava-hosted LLM."""

    def __init__(
        self,
        rule_engine: Any,
        pet_state_manager: Any,
    ) -> None:
        self._rule_engine = rule_engine
        self._pet_state = pet_state_manager

        api_key = os.getenv("OPENAI_API_KEY", "") or os.getenv("LAVA_API_KEY", "")
        base_url = os.getenv("LAVA_BASE_URL", "") or None

        if not api_key:
            logger.warning(
                "OPENAI_API_KEY (or LAVA_API_KEY) not set; LLM calls will fail"
            )

        self._client: openai.OpenAI = openai.OpenAI(
            api_key=api_key,
            base_url=base_url,
        )
        self._model: str = os.getenv("LLM_MODEL", "") or os.getenv("LAVA_MODEL", "") or "gpt-4o-mini"

    def process_command(self, text: str) -> dict[str, Any]:
        """Send a user command to the LLM and return a structured action dict.

        Returns a dict with at least:
            - "action": one of "add_rule", "remove_rule", "start_timer",
                        "stop_timer", "respond"
            - "reply": a text response from Wamm
            - "rule": (optional) rule payload for add/remove actions
        """
        if not text.strip():
            return {"action": "respond", "reply": "I didn't catch that. Could you say it again?"}

        system_prompt = self._build_system_prompt()

        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": text},
                ],
                response_format={"type": "json_object"},
                temperature=0.7,
                max_tokens=300,
            )

            raw_content: str = response.choices[0].message.content or ""
            logger.debug("LLM raw response: %s", raw_content)

            return _parse_llm_response(raw_content)

        except openai.APIError:
            logger.exception("Lava API error while processing command")
            return {"action": "respond", "reply": "Hmm, my brain is fuzzy right now. Try again in a sec!"}
        except Exception:
            logger.exception("Unexpected error during LLM processing")
            return {"action": "respond", "reply": "Something went wrong on my end. Sorry!"}

    def _build_system_prompt(self) -> str:
        """Construct the system prompt with Wamm's personality and context."""
        pet_state = _safe_get_state(self._pet_state)
        active_rules = _safe_get_rules(self._rule_engine)

        return (
            "You are Wamm, a cute and helpful AI desk pet that lives on your "
            "owner's desk. You help them stay productive, maintain good posture, "
            "and take breaks. You speak in short, friendly sentences. You are "
            "enthusiastic but not annoying.\n\n"
            f"Current state:\n"
            f"- Mood: {pet_state.get('mood', 'happy')}\n"
            f"- XP: {pet_state.get('xp', 0)}\n\n"
            f"Active rules:\n{_format_rules(active_rules)}\n\n"
            "Available actions you can take (return as JSON):\n"
            "- add_rule: Add a new rule. Include a 'rule' object with "
            "'type' (posture/phone/timer/custom), 'description', "
            "'threshold' (dict), and 'severity' (gentle/moderate/strict).\n"
            "- remove_rule: Remove a rule. Include a 'rule' object with 'id'.\n"
            "- start_timer: Start a focus timer. Include 'rule' with 'duration' "
            "(seconds, default 1500 for 25 min).\n"
            "- start_pomodoro: Start a Pomodoro session (25 min focus + 5 min break). "
            "No extra parameters needed.\n"
            "- stop_timer: Stop the current timer.\n"
            "- respond: Just reply with a message, no special action.\n\n"
            "Always respond with valid JSON:\n"
            '  {"action": "<action>", "reply": "<spoken response>", '
            '"rule": {...} (if applicable)}'
        )


def _safe_get_state(pet_state_manager: Any) -> dict[str, Any]:
    """Retrieve pet state, returning defaults on failure."""
    try:
        if hasattr(pet_state_manager, "get_state"):
            return dict(pet_state_manager.get_state())
        if hasattr(pet_state_manager, "to_dict"):
            return dict(pet_state_manager.to_dict())
    except Exception:
        logger.warning("Could not read pet state, using defaults")
    return {"mood": "happy", "xp": 0}


def _safe_get_rules(rule_engine: Any) -> list[Any]:
    """Retrieve active rules, returning empty list on failure."""
    try:
        if hasattr(rule_engine, "get_active_rules"):
            return list(rule_engine.get_active_rules())
    except Exception:
        logger.warning("Could not read rules, using empty list")
    return []


def _format_rules(rules: list[Any]) -> str:
    """Format a list of Rule objects for the system prompt."""
    if not rules:
        return "  (none active)"
    lines: list[str] = []
    for rule in rules:
        rule_type = getattr(rule, "type", "custom")
        desc = getattr(rule, "description", str(rule))
        severity = getattr(rule, "severity", "moderate")
        lines.append(f"  - [{rule_type}/{severity}] {desc}")
    return "\n".join(lines)


def _parse_llm_response(raw: str) -> dict[str, Any]:
    """Parse the LLM response as JSON, falling back gracefully."""
    if not raw.strip():
        return {"action": "respond", "reply": "..."}

    try:
        parsed: dict[str, Any] = json.loads(raw)
        if "action" not in parsed:
            parsed["action"] = "respond"
        if "reply" not in parsed:
            parsed["reply"] = raw
        return parsed
    except json.JSONDecodeError:
        logger.warning("LLM returned non-JSON response, wrapping as text")
        return {"action": "respond", "reply": raw}
