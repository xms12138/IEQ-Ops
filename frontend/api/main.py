"""frontend/api/main.py — FastAPI gateway for the Q&A butler.

Serves a single-page chat UI and the chat endpoints. Text questions go to
ConversationalAgent.respond; voice questions run the cascade (transcribe → respond →
synthesize), with the browser's Web Speech API doing STT/TTS in the MVP (zero keys).

    uvicorn frontend.api.main:app --reload
"""

from __future__ import annotations

import base64
import json
import queue
import threading
import time
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

from agents.conversational import ConversationalAgent
from core.config import get_settings
from core.logging import get_logger
from frontend.api import ops
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


def _prewarm_rag() -> None:
    """Load the RAG stack (BGE-M3 + reranker + BM25) in the background at startup so the
    FIRST injected incident doesn't pay the ~100 s cold load on the Pi CPU (P-028/P-030).
    Best-effort: a failure just means the first incident pays the cold start, never a crash."""
    try:
        from mcp_servers.rag.server import mcp as rag_server

        t0 = time.monotonic()
        call_tool(rag_server, "retrieve", query="ventilation co2", domain="airquality", top_k=1)
        log.info("rag_prewarmed", seconds=round(time.monotonic() - t0, 1))
    except Exception as exc:  # noqa: BLE001 — warmup is best-effort, never block/crash the web
        log.warning("rag_prewarm_failed", error=str(exc))


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    init_schema()  # ensure tables exist (incidents + sensor_readings)
    if get_settings().exhibit_mode:  # exhibit: warm RAG so the first incident isn't slow
        threading.Thread(target=_prewarm_rag, name="rag-prewarm", daemon=True).start()
        log.info("rag_prewarm_started")
    log.info("frontend_ready")
    yield


app = FastAPI(title="IEQ-Ops 问答管家", lifespan=lifespan)
app.include_router(ops.router)  # operator dashboard: /ops + /api/incidents + /api/inject


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


@app.post("/api/voice/stream")
async def voice_stream(
    audio: UploadFile | None = None, debug_text: str = Form(""), history: str = Form("[]")
) -> StreamingResponse:
    """Lowest-latency voice cascade: transcribe → respond_stream → CosyVoice streaming
    TTS, all pipelined. Emits newline-delimited JSON events so the page shows the answer
    text as it streams while PCM audio frames arrive and play incrementally:

        {"type":"query","text":..}  {"type":"token","text":..}
        {"type":"audio","pcm_b64":..}  (base64 PCM 24 kHz mono 16-bit)
        {"type":"done","first_package_ms":N,"text":..}

    With the mock provider no audio events are sent — the browser speaks the text. The
    first audio frame arrives before the LLM finishes, so the first sentence is spoken
    while the rest is still being generated."""
    turns = _parse_history(history)
    raw = await audio.read() if audio is not None else b""
    query = _voice.transcribe(raw, debug_text=debug_text)

    def _events() -> Iterator[str]:
        if not query:
            yield json.dumps({"type": "error", "text": "Sorry, I didn't catch that."}) + "\n"
            return
        yield json.dumps({"type": "query", "text": query}) + "\n"
        bus: queue.Queue[tuple[str, Any]] = queue.Queue()

        def _tee() -> Iterator[str]:
            # Pull the LLM token stream; mirror each token to the page AND feed it to TTS.
            for tok in _agent.respond_stream(query, turns):
                bus.put(("token", tok))
                yield tok

        def _drive() -> None:
            try:
                for frame in _voice.synthesize_stream(_tee()):
                    bus.put(("audio", frame))
            except Exception as exc:  # noqa: BLE001 — surface as an event, never 500
                bus.put(("error", str(exc)))
            finally:
                bus.put(("end", None))

        threading.Thread(target=_drive, name="voice-stream", daemon=True).start()
        answer: list[str] = []
        while True:
            kind, payload = bus.get()
            if kind == "end":
                break
            if kind == "token":
                answer.append(payload)
                yield json.dumps({"type": "token", "text": payload}) + "\n"
            elif kind == "audio":
                b64 = base64.b64encode(payload).decode("ascii")
                yield json.dumps({"type": "audio", "pcm_b64": b64}) + "\n"
            elif kind == "error":
                yield json.dumps({"type": "error", "text": payload}) + "\n"
        fpm = getattr(_voice, "last_first_package_ms", None)
        yield (
            json.dumps({"type": "done", "first_package_ms": fpm, "text": "".join(answer).strip()})
            + "\n"
        )

    return StreamingResponse(_events(), media_type="application/x-ndjson")


@app.get("/api/sensors/current")
def sensors_current() -> JSONResponse:
    """Latest reading of every sensor (for the top readings bar)."""
    return JSONResponse(call_tool(sensor_server, "read_sensors"))
