"""API routes for the Buddy AI Desk Pet dashboard.

Provides REST endpoints for pet state, rule CRUD, and focus session
controls, plus the main HTML template route.
"""

from __future__ import annotations

import logging
from dataclasses import asdict
from typing import Any, Callable

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class RuleCreateRequest(BaseModel):
    type: str = Field(..., description="Rule type: posture, phone, timer, or custom")
    description: str = Field(..., description="Human-readable rule description")
    threshold: dict[str, Any] = Field(
        default_factory=dict, description="Threshold parameters for the rule"
    )
    severity: str = Field(..., description="Severity: gentle, moderate, or strict")


class RuleUpdateRequest(BaseModel):
    type: str | None = None
    description: str | None = None
    threshold: dict[str, Any] | None = None
    severity: str | None = None


class RuleResponse(BaseModel):
    id: str
    type: str
    description: str
    threshold: dict[str, Any]
    severity: str
    active: bool
    created_at: str


def create_router(
    templates: Jinja2Templates,
    get_pet_state_manager: Callable[[], Any],
    get_rule_engine: Callable[[], Any],
) -> APIRouter:
    """Build and return an APIRouter wired to the given dependencies."""
    router = APIRouter()

    @router.get("/", response_class=HTMLResponse)
    async def index(request: Request) -> HTMLResponse:
        psm = get_pet_state_manager()
        state = psm.get_state() if psm is not None else _default_state()
        return templates.TemplateResponse(
            "index.html",
            {"request": request, "state": state},
        )

    @router.get("/api/state")
    async def get_state() -> dict[str, Any]:
        psm = get_pet_state_manager()
        if psm is None:
            return _default_state()
        return psm.get_state()

    @router.get("/api/rules")
    async def get_rules() -> list[dict[str, Any]]:
        engine = get_rule_engine()
        if engine is None:
            return []
        return [asdict(r) for r in engine.get_rules()]

    @router.post("/api/rules", status_code=201)
    async def add_rule(body: RuleCreateRequest) -> dict[str, Any]:
        engine = get_rule_engine()
        if engine is None:
            raise HTTPException(status_code=503, detail="Rule engine not available")
        try:
            rule = engine.add_rule(
                type=body.type,
                description=body.description,
                threshold=body.threshold,
                severity=body.severity,
            )
            logger.info("Rule created via API: %s", rule.id)
            return asdict(rule)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.put("/api/rules/{rule_id}")
    async def update_rule(rule_id: str, body: RuleUpdateRequest) -> dict[str, Any]:
        engine = get_rule_engine()
        if engine is None:
            raise HTTPException(status_code=503, detail="Rule engine not available")

        updates = {k: v for k, v in body.model_dump().items() if v is not None}
        if not updates:
            raise HTTPException(status_code=422, detail="No fields to update")

        try:
            rule = engine.update_rule(rule_id, **updates)
            logger.info("Rule updated via API: %s", rule_id)
            return asdict(rule)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.delete("/api/rules/{rule_id}", status_code=204)
    async def delete_rule(rule_id: str) -> None:
        engine = get_rule_engine()
        if engine is None:
            raise HTTPException(status_code=503, detail="Rule engine not available")
        try:
            engine.remove_rule(rule_id)
            logger.info("Rule deleted via API: %s", rule_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.put("/api/rules/{rule_id}/toggle")
    async def toggle_rule(rule_id: str) -> dict[str, Any]:
        engine = get_rule_engine()
        if engine is None:
            raise HTTPException(status_code=503, detail="Rule engine not available")
        try:
            rule = engine.toggle_rule(rule_id)
            logger.info("Rule toggled via API: %s (active=%s)", rule_id, rule.active)
            return asdict(rule)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.post("/api/focus/start")
    async def focus_start() -> dict[str, str]:
        psm = get_pet_state_manager()
        if psm is None:
            raise HTTPException(
                status_code=503, detail="Pet state manager not available"
            )
        psm.start_focus()
        logger.info("Focus session started via API")
        return {"status": "started"}

    @router.post("/api/focus/stop")
    async def focus_stop() -> dict[str, str]:
        psm = get_pet_state_manager()
        if psm is None:
            raise HTTPException(
                status_code=503, detail="Pet state manager not available"
            )
        psm.stop_focus()
        logger.info("Focus session stopped via API")
        return {"status": "stopped"}

    return router


def _default_state() -> dict[str, Any]:
    """Return a fallback state when the pet state manager is unavailable."""
    return {
        "emotion": "neutral",
        "growth_stage": 0,
        "growth_stage_name": "Egg",
        "xp": 0,
        "xp_next": 15,
        "posture": "unknown",
        "focus_active": False,
        "focus_elapsed": 0,
        "today_focus_minutes": 0,
        "posture_violations": 0,
        "phone_violations": 0,
    }
