"""Run real Gnani smoke tests with ten short, consented WAV clips.

Name files bn-IN.wav, en-IN.wav, ... in the supplied folder. Each should ask
for a local service and contain no real personal information.
"""

import argparse
import json
from pathlib import Path

import httpx

from app.core import LANGUAGES


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("samples", type=Path)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    missing = [code for code in LANGUAGES if not (args.samples / f"{code}.wav").is_file()]
    if missing:
        parser.error("Missing WAV files: " + ", ".join(missing))

    with httpx.Client(base_url=args.base_url, timeout=180) as client:
        for code in LANGUAGES:
            path = args.samples / f"{code}.wav"
            data = {"state": "{}", "selected_language": code}
            with path.open("rb") as audio:
                response = client.post("/api/turn", data=data, files={"audio": (path.name, audio, "audio/wav")})
            if response.status_code != 200:
                print(json.dumps({"expectedLanguage": code, "status": response.status_code, "error": response.json()}, ensure_ascii=False))
                continue
            first = response.json()
            result = {
                "expectedLanguage": code,
                "detectedLanguage": first["detectedLanguage"],
                "transcript": first["transcript"],
                "englishTranscript": first["englishTranscript"],
                "category": first["category"],
                "replyText": first["replyText"],
                "speechReady": bool(first["replyAudioBase64"]),
                "phase": first["state"]["phase"],
            }
            if first["state"]["phase"] == "awaiting_confirmation":
                confirm = client.post("/api/turn", data={"control": "yes", "state": json.dumps(first["state"])})
                if confirm.status_code == 200:
                    result["matchesFound"] = len(confirm.json()["matches"])
                    result["finalSpeechReady"] = bool(confirm.json()["replyAudioBase64"])
                else:
                    result["confirmError"] = confirm.json()
            print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
