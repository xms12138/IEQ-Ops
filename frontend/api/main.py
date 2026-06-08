"""frontend/api/main.py — FastAPI gateway for the Q&A butler.

Serves a single-page chat UI and the chat endpoints. Text questions go to
ConversationalAgent.respond; voice questions run the cascade (transcribe → respond →
synthesize), with the browser's Web Speech API doing STT/TTS in the MVP (zero keys).

    uvicorn frontend.api.main:app --reload
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

from agents.conversational import ConversationalAgent
from core.logging import get_logger
from mcp_servers.client import call_tool
from mcp_servers.sensor.server import mcp as sensor_server
from mcp_servers.ticket.server import init_schema
from voice.provider import get_voice_provider

log = get_logger("frontend")

_APP_DIR = Path(__file__).resolve().parent.parent / "app"
templates = Jinja2Templates(directory=str(_APP_DIR))

_agent = ConversationalAgent()
_voice = get_voice_provider()

_MAX_TURNS = 6  # sliding window: keep only the last N messages so tokens stay bounded


def _parse_history(raw: str) -> list[dict[str, str]]:
    """Parse client-supplied chat history defensively → the last _MAX_TURNS
    {role, content} messages. Malformed input degrades to no history (never 500s)."""
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(data, list):
        return []
    turns: list[dict[str, str]] = []
    for m in data:
        if (
            isinstance(m, dict)
            and m.get("role") in ("user", "assistant")
            and isinstance(m.get("content"), str)
        ):
            turns.append({"role": m["role"], "content": m["content"]})
    return turns[-_MAX_TURNS:]


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    init_schema()  # ensure tables exist (incidents + sensor_readings)
    log.info("frontend_ready")
    yield


app = FastAPI(title="IEQ-Ops 问答管家", lifespan=lifespan)


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> Any:
    return templates.TemplateResponse(request, "index.html")


@app.post("/api/chat")
def chat(query: str = Form(...), history: str = Form("[]")) -> StreamingResponse:
    """Text question → grounded answer, streamed as plain-text token chunks (UTF-8)."""
    turns = _parse_history(history)
    return StreamingResponse(
        _agent.respond_stream(query, turns), media_type="text/plain; charset=utf-8"
    )


@app.post("/api/voice/chat")
async def voice_chat(
    audio: UploadFile | None = None, debug_text: str = Form(""), history: str = Form("[]")
) -> JSONResponse:
    """Voice cascade: transcribe (mock echoes browser-recognised text) → respond →
    synthesize (None → browser speaks). Non-streaming: TTS needs the whole answer.
    Returns the recognised query + the answer."""
    turns = _parse_history(history)
    raw = await audio.read() if audio is not None else b""
    query = _voice.transcribe(raw, debug_text=debug_text)
    if not query:
        return JSONResponse(
            {"text": "Sorry, I didn't catch that. Please try again.", "query": "", "spoken": False}
        )
    answer = _agent.respond(query, turns)
    audio_out = _voice.synthesize(answer)
    return JSONResponse({"text": answer, "query": query, "spoken": audio_out is not None})


@app.get("/api/sensors/current")
def sensors_current() -> JSONResponse:
    """Latest reading of every sensor (for the top readings bar)."""
    return JSONResponse(call_tool(sensor_server, "read_sensors"))
