"""voice/provider.py — cascade voice adapter (STT → text LLM → TTS).

The butler uses a CASCADE, not an end-to-end speech model: speech-to-text, then the
text ConversationalAgent, then text-to-speech — because tool calls happen between the
words and the answer. This module is only the STT/TTS edges; the LLM in the middle is
the ConversationalAgent.

MVP ships MockVoiceProvider (zero voice keys): transcribe echoes the text the frontend
sends alongside the audio (the browser's Web Speech API does the actual recognition, so
"you speak = you type"), and synthesize returns None so the browser's SpeechSynthesis
voices the answer. Swap in a real provider later by implementing the same Protocol and
setting VOICE_PROVIDER — no call-site changes.
"""

from __future__ import annotations

from typing import Protocol

from core.config import get_settings
from core.logging import get_logger

log = get_logger("voice")


class VoiceProvider(Protocol):
    """STT/TTS edges of the cascade. Implementations must be swappable by config."""

    def transcribe(self, audio: bytes, *, debug_text: str | None = None) -> str:
        """Audio → text query."""
        ...

    def synthesize(self, text: str) -> bytes | None:
        """Text answer → audio bytes, or None to let the browser speak it."""
        ...


class MockVoiceProvider:
    """No-key cascade stand-in (MVP). transcribe echoes the frontend's recognised text;
    synthesize returns None so the browser's SpeechSynthesis voices the answer — the
    voice path is end-to-end demonstrable and the answer truly matches the question."""

    def transcribe(self, audio: bytes, *, debug_text: str | None = None) -> str:
        text = (debug_text or "").strip()
        log.info("mock_transcribe", n_bytes=len(audio), text=text[:60])
        return text

    def synthesize(self, text: str) -> bytes | None:
        log.info("mock_synthesize", n_chars=len(text))
        return None  # browser SpeechSynthesis speaks it


def get_voice_provider() -> VoiceProvider:
    """Select the provider from VOICE_PROVIDER. Only 'mock' is wired in the MVP; real
    providers (openai / domestic) plug in here behind the same Protocol."""
    provider = get_settings().voice_provider.lower()
    if provider != "mock":
        log.warning("voice_provider_unknown", requested=provider, fallback="mock")
    return MockVoiceProvider()
