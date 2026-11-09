"""Inspect real multilingual extraction before recording a demo."""

import asyncio
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from app.reasoning import MultilingualReasoner  # noqa: E402


async def main():
    reasoner = MultilingualReasoner()
    cases = [
        ("en-IN", "My kitchen tap is leaking in Mysuru"),
        ("hi-IN", "मुझे नांदेड़ में प्लंबर चाहिए, पानी का नल टूट गया है"),
        ("ta-IN", "சேலத்தில் என் washing machine பழுதாகிவிட்டது"),
        ("hi-IN", "Mere ghar ka tap leak ho raha hai, plumber chahiye in Nanded"),
        ("ta-IN", "Salem la washing machine work aagala, repair venum"),
    ]
    for language, request in cases:
        result = await reasoner.interpret(request, language, "new")
        print(language, result)
        if result["service"]:
            reply = await reasoner.localize(f"You need {result['service']} in {result['location'] or 'your area'}. Is that right?", language)
            print("reply:", reply)


if __name__ == "__main__":
    asyncio.run(main())
