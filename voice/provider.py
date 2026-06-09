"""voice/provider.py — cascade voice adapter (STT → text LLM → TTS).

The butler uses a CASCADE, not an end-to-end speech model: speech-to-text, then the
text ConversationalAgent, then text-to-speech — because tool calls happen between the
words and the answer. This module is only the STT/TTS edges; the LLM in the middle is
the ConversationalAgent.

Two providers:
  - MockVoiceProvider (zero keys): transcribe echoes the browser's Web-Speech text;
    synthesize/synthesize_stream emit nothing so the browser's SpeechSynthesis voices
    the answer. The voice path is demonstrable with no cloud dependency.
  - DashScopeVoiceProvider (阿里云百炼): real English STT (Paraformer) + real streaming
    TTS (Qwen3-TTS-Flash realtime). synthesize_stream feeds the LLM token stream into a
    duplex WebSocket (append_text) and yields audio frames as they arrive — so the FIRST
    sentence is spoken before the LLM finishes the rest (lowest time-to-first-audio).
    Targets the Singapore (intl) endpoint, ~5 s faster than Beijing for the author.

The agent speaks ENGLISH only (see ConversationalAgent), so STT is biased to English
and the TTS voice (Jennifer / 詹妮弗) and language_type are English.

Select via VOICE_PROVIDER; both implement the same Protocol, so the call sites in
frontend/api/main.py never change.
"""

from __future__ import annotations

import base64
import contextlib
import queue
import tempfile
import threading
import time
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Protocol

from core.config import get_settings
from core.logging import get_logger

log = get_logger("voice")

# Sentinel pushed onto the audio queue when synthesis completes or errors.
_DONE = object()
# Realtime event types that mean "this response's audio is finished".
_TERMINAL_EVENTS = frozenset(
    {"response.audio.done", "response.done", "response.completed", "session.finished"}
)
# Stop waiting if no audio frame arrives for this long after the text is fully sent
# (safety net in case the SDK uses a terminal event name we don't recognise).
_SILENCE_TIMEOUT_S = 3.0


class VoiceProvider(Protocol):
    """STT/TTS edges of the cascade. Implementations must be swappable by config."""

    def transcribe(self, audio: bytes, *, debug_text: str | None = None) -> str:
        """Audio → text query."""
        ...

    def synthesize(self, text: str) -> bytes | None:
        """Whole-text answer → audio bytes, or None to let the browser speak it."""
        ...

    def synthesize_stream(self, text_iter: Iterable[str]) -> Iterator[bytes]:
        """Streaming answer → audio frames, yielded as they are synthesised. Yields
        nothing (an empty iterator) when the provider defers speech to the browser."""
        ...


class MockVoiceProvider:
    """No-key cascade stand-in. transcribe echoes the frontend's recognised text;
    synthesis emits no audio so the browser's SpeechSynthesis voices the answer — the
    voice path is end-to-end demonstrable and the answer truly matches the question."""

    def transcribe(self, audio: bytes, *, debug_text: str | None = None) -> str:
        text = (debug_text or "").strip()
        log.info("mock_transcribe", n_bytes=len(audio), text=text[:60])
        return text

    def synthesize(self, text: str) -> bytes | None:
        log.info("mock_synthesize", n_chars=len(text))
        return None  # browser SpeechSynthesis speaks it

    def synthesize_stream(self, text_iter: Iterable[str]) -> Iterator[bytes]:
        # Drain the token stream (so the caller's LLM still runs) but emit no audio;
        # the browser speaks the accumulated text. `yield from ()` keeps this a generator.
        for _ in text_iter:
            pass
        yield from ()


class DashScopeVoiceProvider:
    """阿里云百炼 cascade: Paraformer English STT + Qwen3-TTS-Flash realtime streaming TTS.

    synthesize_stream bridges the DashScope realtime SDK's push-callback model to a pull
    iterator: a feeder thread pushes LLM token fragments into the duplex WebSocket via
    append_text(), the SDK delivers audio frames to on_event() as response.audio.delta,
    and we yield them off a thread-safe queue. First-package latency (time to first audio
    frame after the text starts flowing) is measured and logged per call."""

    def __init__(self) -> None:
        import dashscope  # lazy: keep module import cheap for the mock path

        s = get_settings()
        self._api_key = s.dashscope_api_key
        self._http_url = s.dashscope_http_url
        dashscope.api_key = self._api_key
        dashscope.base_http_api_url = self._http_url  # Singapore for Qwen3-ASR (HTTP)
        self._ws_url = s.dashscope_ws_url  # Singapore for the TTS realtime websocket (explicit url)
        self._tts_model = s.tts_model
        self._tts_voice = s.tts_voice
        self._tts_language = s.tts_language
        self._asr_model = s.asr_model
        self.last_first_package_ms: int | None = None

    # ── STT ──────────────────────────────────────────────────────────────────
    def transcribe(self, audio: bytes, *, debug_text: str | None = None) -> str:
        """Recognise English speech from a WAV byte blob via Qwen3-ASR (batch). The
        audio is written to a temp file and passed as a file:// URL in the multimodal
        message. `debug_text` is ignored (real recognition); kept for Protocol parity."""
        import dashscope
        from dashscope import MultiModalConversation

        dashscope.api_key = self._api_key
        dashscope.base_http_api_url = self._http_url  # Singapore
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(audio)
            wav_path = f.name
        try:
            messages = [{"role": "user", "content": [{"audio": f"file://{wav_path}"}]}]
            resp = MultiModalConversation.call(
                model=self._asr_model,
                messages=messages,
                result_format="message",
                asr_options={"language": "en", "enable_lid": False},  # force English
            )
            text = self._extract_asr_text(resp)
            log.info("dashscope_transcribe", n_bytes=len(audio), text=text[:60])
            return text
        except Exception as exc:  # noqa: BLE001 — degrade to empty, caller handles
            log.warning("dashscope_transcribe_failed", error=str(exc))
            return ""
        finally:
            Path(wav_path).unlink(missing_ok=True)

    @staticmethod
    def _extract_asr_text(resp: object) -> str:
        """Pull the recognised text out of a Qwen3-ASR MultiModalConversation response
        (output.choices[0].message.content[*].text), defensively."""
        try:
            content = resp.output["choices"][0]["message"]["content"]  # type: ignore[attr-defined]
        except (AttributeError, KeyError, IndexError, TypeError):
            return ""
        if not isinstance(content, list):
            return ""
        parts = [c.get("text", "") for c in content if isinstance(c, dict) and c.get("text")]
        return " ".join(parts).strip()

    # ── TTS ──────────────────────────────────────────────────────────────────
    def synthesize_stream(self, text_iter: Iterable[str]) -> Iterator[bytes]:
        """Stream LLM tokens into Qwen3-TTS realtime and yield PCM audio frames (24 kHz
        mono 16-bit) as they arrive."""
        import dashscope
        from dashscope.audio.qwen_tts_realtime import QwenTtsRealtime, QwenTtsRealtimeCallback

        dashscope.api_key = self._api_key
        audio_q: queue.Queue[object] = queue.Queue()
        timing: dict[str, float | None] = {"t0": None, "first_ms": None}
        err: dict[str, str] = {}
        done = threading.Event()

        def _signal_done() -> None:
            if not done.is_set():
                done.set()
                audio_q.put(_DONE)

        class _Callback(QwenTtsRealtimeCallback):  # type: ignore[misc]
            def on_open(self) -> None:
                pass

            def on_event(self, response: dict[str, object]) -> None:
                etype = response.get("type", "")
                if etype == "response.audio.delta":
                    delta = response.get("delta")
                    if isinstance(delta, str) and delta:
                        if timing["first_ms"] is None and timing["t0"] is not None:
                            timing["first_ms"] = (time.monotonic() - timing["t0"]) * 1000
                        audio_q.put(base64.b64decode(delta))
                elif etype in _TERMINAL_EVENTS:
                    _signal_done()

            def on_close(self, code: object = None, reason: object = None) -> None:
                _signal_done()

        try:
            tts = QwenTtsRealtime(model=self._tts_model, callback=_Callback(), url=self._ws_url)
            tts.connect()
            tts.update_session(voice=self._tts_voice, language_type=self._tts_language)
        except Exception as exc:  # noqa: BLE001 — surface, yield nothing
            log.warning("qwen_tts_init_failed", error=str(exc))
            self.last_first_package_ms = None
            return

        fed_all = threading.Event()

        def _feed() -> None:
            """Drive the LLM stream into the WS, then close input. Runs off-thread so the
            main generator can yield audio that arrives while the LLM is still going."""
            try:
                timing["t0"] = time.monotonic()
                for chunk in text_iter:
                    if chunk:
                        tts.append_text(chunk)
                tts.finish()
            except Exception as exc:  # noqa: BLE001
                err["msg"] = str(exc)
                _signal_done()
            finally:
                fed_all.set()

        feeder = threading.Thread(target=_feed, name="qwen-tts-feed", daemon=True)
        feeder.start()

        n_frames = 0
        last_audio = time.monotonic()
        while True:
            try:
                item = audio_q.get(timeout=1.0)
            except queue.Empty:
                # No terminal event seen, but input is fully sent and audio has gone
                # quiet → assume the response is complete (safety net).
                if done.is_set():
                    break
                if fed_all.is_set() and (time.monotonic() - last_audio) > _SILENCE_TIMEOUT_S:
                    break
                continue
            if item is _DONE:
                break
            assert isinstance(item, bytes)
            n_frames += 1
            last_audio = time.monotonic()
            yield item

        with contextlib.suppress(Exception):
            tts.close()
        feeder.join(timeout=5)
        # Prefer the SDK's own measurement; fall back to our wall-clock timing.
        sdk_delay: float | None = None
        with contextlib.suppress(Exception):
            sdk_delay = tts.get_first_audio_delay()
        chosen = sdk_delay if sdk_delay is not None else timing["first_ms"]
        self.last_first_package_ms = int(chosen) if chosen is not None else None
        if err:
            log.warning("qwen_tts_error", error=err["msg"], frames=n_frames)
        else:
            log.info("qwen_tts_done", frames=n_frames, first_package_ms=self.last_first_package_ms)

    def synthesize(self, text: str) -> bytes | None:
        """Whole-text convenience: concatenate the streamed frames into one PCM blob."""
        return b"".join(self.synthesize_stream([text])) or None


def get_voice_provider() -> VoiceProvider:
    """Select the provider from VOICE_PROVIDER. `aliyun` needs DASHSCOPE_API_KEY; a
    missing key (or any construction failure) degrades to the mock so the voice demo
    never hard-crashes."""
    s = get_settings()
    provider = s.voice_provider.lower()
    if provider == "aliyun":
        if not s.dashscope_api_key:
            log.warning("voice_provider_no_key", requested=provider, fallback="mock")
            return MockVoiceProvider()
        try:
            return DashScopeVoiceProvider()
        except Exception as exc:  # noqa: BLE001
            log.warning("voice_provider_init_failed", error=str(exc), fallback="mock")
            return MockVoiceProvider()
    if provider != "mock":
        log.warning("voice_provider_unknown", requested=provider, fallback="mock")
    return MockVoiceProvider()
