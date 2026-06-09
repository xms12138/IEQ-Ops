"""ops/scripts/voice_smoke.py — validate the real Qwen3-TTS cascade end to end.

Needs DASHSCOPE_API_KEY in .env. Exercises the same DashScopeVoiceProvider the web app
uses (Qwen3-TTS-Flash realtime, Singapore endpoint, Jennifer voice), so a green run here
means /api/voice/stream will speak too.

  # streaming TTS → writes a 24 kHz wav + prints first-package latency
  uv run python -m ops.scripts.voice_smoke "Air quality is good, CO2 is 650 ppm."

  # English STT round-trip on a recorded wav
  uv run python -m ops.scripts.voice_smoke --stt path/to/english.wav

The text is fed in small chunks to mimic the LLM token stream, so the first-package
latency reported is representative of the live pipeline.
"""

from __future__ import annotations

import argparse
import struct
import sys

from core.config import get_settings
from voice.provider import DashScopeVoiceProvider


def _wav_header(n_bytes: int, rate: int = 24000) -> bytes:
    """44-byte PCM mono 16-bit WAV header for `n_bytes` of audio data."""
    return (
        b"RIFF"
        + struct.pack("<I", 36 + n_bytes)
        + b"WAVE"
        + b"fmt "
        + struct.pack("<IHHIIHH", 16, 1, 1, rate, rate * 2, 2, 16)
        + b"data"
        + struct.pack("<I", n_bytes)
    )


def _synth_to_wav(provider: DashScopeVoiceProvider, text: str, out: str) -> None:
    """Synthesise `text` to a 24 kHz wav, feeding it in small chunks (mimics the LLM
    token stream), and report the size + first-package latency."""
    words = text.split(" ")
    chunks = [" ".join(words[i : i + 3]) + " " for i in range(0, len(words), 3)]
    pcm = b"".join(provider.synthesize_stream(iter(chunks)))
    with open(out, "wb") as f:
        f.write(_wav_header(len(pcm)))
        f.write(pcm)
    print(f"  → {out}: {len(pcm)} bytes PCM, first_package_ms={provider.last_first_package_ms}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Qwen3-TTS cascade smoke test")
    ap.add_argument("text", nargs="?", default="Air quality is good. CO2 is 650 ppm, within range.")
    ap.add_argument("--stt", help="transcribe this wav (English) instead of synthesising")
    ap.add_argument("--out", default="voice_smoke.wav", help="output wav path for TTS")
    ap.add_argument("--repl", action="store_true", help="type sentences interactively, hear each")
    args = ap.parse_args()

    if not get_settings().dashscope_api_key:
        sys.exit("DASHSCOPE_API_KEY not set in .env — fill it before running this smoke test.")

    provider = DashScopeVoiceProvider()

    if args.stt:
        with open(args.stt, "rb") as f:
            audio = f.read()
        print("STT result:", repr(provider.transcribe(audio)))
        return

    if args.repl:
        print("Type English text + Enter to synthesise (Ctrl-D / Ctrl-C to quit).")
        i = 0
        try:
            for line in sys.stdin:
                text = line.strip()
                if not text:
                    continue
                _synth_to_wav(provider, text, f"voice_smoke_{i}.wav")
                i += 1
        except KeyboardInterrupt:
            pass
        return

    _synth_to_wav(provider, args.text, args.out)


if __name__ == "__main__":
    main()
