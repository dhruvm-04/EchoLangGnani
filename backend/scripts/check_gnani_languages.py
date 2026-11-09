"""Check Gnani Hindi and Tamil speech paths using short generated clips."""

import asyncio
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from app.adapters import GnaniClient, ServiceError  # noqa: E402


async def main():
    client = GnaniClient()
    for language, text in [
        ("hi-IN", "मुझे नांदेड़ में प्लंबर चाहिए।"),
        ("ta-IN", "எனக்கு சேலத்தில் பிளம்பர் வேண்டும்."),
    ]:
        try:
            audio = await client.synthesize(text, language)
            transcript, detected, model = await client.transcribe(audio, language)
            print(f"{language}: TTS {client.tts_model} OK, STT {model} detected {detected}, transcript={ascii(transcript)}")
        except ServiceError as exc:
            print(f"{language}: {exc.code} — {exc}")


if __name__ == "__main__":
    asyncio.run(main())
