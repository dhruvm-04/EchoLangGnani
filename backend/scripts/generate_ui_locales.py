"""Generate reviewable static UI translations with the configured reasoning model."""

from __future__ import annotations

import asyncio
import json
import os
import re
from pathlib import Path

import httpx
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[2]
LOCALES = ROOT / "frontend" / "src" / "locales"
NAMES = {
    "bn-IN": "Bengali", "gu-IN": "Gujarati", "hi-IN": "Hindi",
    "kn-IN": "Kannada", "ml-IN": "Malayalam", "mr-IN": "Marathi",
    "pa-IN": "Punjabi (Gurmukhi)", "ta-IN": "Tamil", "te-IN": "Telugu",
}


async def translate(client: httpx.AsyncClient, code: str, name: str, source: dict, semaphore: asyncio.Semaphore) -> None:
    keys = list(source)
    target = LOCALES / f"{code}.json"
    translated = json.loads(target.read_text(encoding="utf-8")) if target.exists() else {}
    for start in range(0, len(keys), 45):
        chunk = {key: source[key] for key in keys[start:start + 45]}
        if set(chunk).issubset(translated):
            continue
        payload = {
            "model": os.environ["ECHOLANG_LLM_MODEL"], "temperature": 0,
            "response_format": {"type": "json_object"},
            "reasoning_effort": "low", "include_reasoning": False,
            "max_completion_tokens": 5000,
            "messages": [
                {"role": "system", "content": (
                    f"Translate every value in the JSON object to natural, concise {name} for a voice-first local services app in India. "
                    "Return exactly the same JSON keys, with string values only. Use native script, common words, respectful tone, "
                    "and short button labels. Preserve placeholders such as {index}, {total}, {field}, and {value} exactly. "
                    "Keep the brand names EchoLang and Gnani AI. Do not omit or add keys. Do not translate the key names."
                )},
                {"role": "user", "content": json.dumps(chunk, ensure_ascii=False)},
            ],
        }
        for attempt in range(12):
            async with semaphore:
                response = await client.post(
                    os.environ["ECHOLANG_LLM_BASE_URL"].rstrip("/") + "/chat/completions",
                    headers={"Authorization": "Bearer " + os.environ["ECHOLANG_LLM_API_KEY"]},
                    json=payload,
                )
            if response.status_code == 429 and attempt < 11:
                delay = max(15, int(response.headers.get("retry-after", "0") or "0"), min(90, 15 * (attempt + 1)))
                print(f"{code}: rate limited, retrying in {delay}s", flush=True)
                await asyncio.sleep(delay)
                continue
            response.raise_for_status()
            break
        result = json.loads(response.json()["choices"][0]["message"]["content"])
        if set(result) != set(chunk) or any(not isinstance(value, str) or not value.strip() for value in result.values()):
            raise ValueError(f"Incomplete translation for {code}: {start}")
        for key, value in result.items():
            if set(re.findall(r"\{\w+\}", value)) != set(re.findall(r"\{\w+\}", chunk[key])):
                raise ValueError(f"Placeholder mismatch in {code}: {key}")
        translated.update(result)
        target.write_text(json.dumps(translated, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"{code}: {len(translated)}/{len(source)}", flush=True)


async def main() -> None:
    load_dotenv(ROOT / "backend" / ".env")
    source = json.loads((LOCALES / "en-IN.json").read_text(encoding="utf-8"))
    async with httpx.AsyncClient(timeout=120) as client:
        semaphore = asyncio.Semaphore(1)
        for code, name in NAMES.items():
            await translate(client, code, name, source, semaphore)


if __name__ == "__main__":
    asyncio.run(main())
