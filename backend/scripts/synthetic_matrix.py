"""Synthetic ten-language smoke check using Groq text and Gnani TTS/STT.

Generated speech checks API routing, not human-speaker accuracy.
"""

import argparse
import asyncio
import json
import time
from pathlib import Path

from dotenv import load_dotenv
from fastapi.testclient import TestClient

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from app.adapters import ServiceError  # noqa: E402
from app.core import LANGUAGES  # noqa: E402
from app.main import app  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--count", type=int, default=10)
    args = parser.parse_args()
    codes = list(LANGUAGES)[args.start:args.start + args.count]
    with TestClient(app) as client:
        for code in codes:
            started = time.perf_counter()
            try:
                phrase = asyncio.run(app.state.reasoner.localize("I need a plumber in Nanded.", code))
                audio = asyncio.run(app.state.gnani.synthesize(phrase, code))
                response = client.post(
                    "/api/turn", data={"state": "{}", "selected_language": code},
                    files={"audio": ("request.wav", audio, "audio/wav")},
                )
                if response.status_code != 200:
                    result = {"expected": code, "status": response.status_code, "error": response.json()}
                else:
                    body = response.json()
                    result = {
                        "expected": code, "status": 200,
                        "detected": body["detectedLanguage"],
                        "transcript": body["transcript"],
                        "english": body["englishTranscript"],
                        "service": body["category"],
                        "location": body["location"],
                        "reply": body["replyText"],
                        "speechReady": bool(body["replyAudioBase64"]),
                        "phase": body["state"]["phase"],
                    }
            except ServiceError as exc:
                result = {"expected": code, "error": exc.code, "message": str(exc)}
            result["seconds"] = round(time.perf_counter() - started, 2)
            print(json.dumps(result, ensure_ascii=False), flush=True)
            time.sleep(2)


if __name__ == "__main__":
    main()
