"""Check live Gnani model access with one short synthesized English clip."""

import asyncio
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from app.adapters import GnaniClient, ServiceError  # noqa: E402


async def main():
    client = GnaniClient()
    if not client.key:
        print("GNANI_API_KEY missing")
        return
    sample = "I need a plumber in Nanded."
    try:
        audio = await client.synthesize(sample, "en-IN")
        print(f"TTS {client.tts_model}: OK ({len(audio)} bytes)")
    except ServiceError as exc:
        print(f"TTS {client.tts_model}: {exc.code} — {exc}")
        return
    try:
        transcript, language, model = await client.transcribe(audio, None if client.stt_model == "prisma-v3.0" else "en-IN")
        print(f"STT {model}: OK ({language}) — {transcript}")
    except ServiceError as exc:
        print(f"STT {client.stt_model}: {exc.code} — {exc}")


if __name__ == "__main__":
    asyncio.run(main())
