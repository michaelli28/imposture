"""Main FastAPI application for the Wamm AI Desk Pet dashboard.

Serves the web dashboard with real-time WebSocket updates for pet state,
rule management, and focus session controls.
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, Response, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from src.dashboard.routes import create_router

logger = logging.getLogger(__name__)

_BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="Wamm Dashboard")

app.mount(
    "/static",
    StaticFiles(directory=_BASE_DIR / "static"),
    name="static",
)

templates = Jinja2Templates(directory=_BASE_DIR / "templates")

_active_connections: set[WebSocket] = set()

_pet_state_manager: Any = None
_rule_engine: Any = None
_cv_pipeline: Any = None


def _get_pet_state_manager() -> Any:
    return _pet_state_manager


def _get_rule_engine() -> Any:
    return _rule_engine


def _get_cv_pipeline() -> Any:
    return _cv_pipeline


router = create_router(
    templates=templates,
    get_pet_state_manager=_get_pet_state_manager,
    get_rule_engine=_get_rule_engine,
    get_cv_pipeline=_get_cv_pipeline,
)
app.include_router(router)


@app.get("/api/camera_frame")
async def camera_frame() -> Response:
    """Return the latest webcam frame as a JPEG snapshot."""
    from src.cv_pipeline import get_latest_jpeg

    jpeg = get_latest_jpeg()
    if jpeg is None:
        return Response(status_code=204)
    return Response(content=jpeg, media_type="image/jpeg")


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    """Accept a WebSocket connection and stream pet state updates."""
    await ws.accept()
    _active_connections.add(ws)
    logger.info("WebSocket client connected (%d total)", len(_active_connections))

    try:
        while True:
            data: dict[str, Any] = {}
            if _pet_state_manager is not None:
                data = _pet_state_manager.get_state()
            if _cv_pipeline is not None:
                data["calibration"] = _cv_pipeline.get_calibration_status()
                data["cv"] = _cv_pipeline.get_analysis_data()
            if data:
                await ws.send_json(data)
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
    except Exception:
        logger.exception("WebSocket error")
    finally:
        _active_connections.discard(ws)
        logger.debug("Active WebSocket connections: %d", len(_active_connections))


async def broadcast_state(state_dict: dict[str, Any]) -> None:
    """Send a state snapshot to every connected WebSocket client."""
    if not _active_connections:
        return

    stale: list[WebSocket] = []
    for ws in _active_connections:
        try:
            await ws.send_json(state_dict)
        except Exception:
            logger.debug("Removing stale WebSocket connection")
            stale.append(ws)

    for ws in stale:
        _active_connections.discard(ws)


def start_server(pet_state_manager: Any, rule_engine: Any, cv_pipeline: Any = None) -> None:
    """Configure dependencies and run the Uvicorn server.

    Reads host/port from BUDDY_HOST and BUDDY_PORT environment variables,
    defaulting to 0.0.0.0:8080.
    """
    global _pet_state_manager, _rule_engine, _cv_pipeline  # noqa: PLW0603
    _pet_state_manager = pet_state_manager
    _rule_engine = rule_engine
    _cv_pipeline = cv_pipeline

    host = os.getenv("WAMM_HOST", "0.0.0.0")
    port = int(os.getenv("WAMM_PORT", "8080"))

    logger.info("Starting Wamm Dashboard on %s:%d", host, port)
    uvicorn.run(app, host=host, port=port, log_level="info")
