"""External Gnani calls and local language models."""

from __future__ import annotations

import asyncio
import os
import io
import wave
from functools import lru_cache

import httpx

from .core import LANGUAGES

GNANI_BASE = "https://api.vachana.ai"


class ServiceError(Exception):
    def __init__(self, message: str, status: int = 502, code: str = "service_error"):
        super().__init__(message)
        self.status = status
        self.code = code


class GnaniClient:
    def __init__(self, key: str | None = None, stt_model: str | None = None, tts_model: str | None = None):
        self.key = key or os.getenv("GNANI_API_KEY", "")
        self.stt_model = stt_model or os.getenv("GNANI_STT_MODEL", "prisma-v3.0")
        self.tts_model = tts_model or os.getenv("GNANI_TTS_MODEL", "timbre-v3.0")

    def _headers(self) -> dict[str, str]:
        if not self.key:
            raise ServiceError("Set GNANI_API_KEY on the backend before using speech.", 503, "missing_api_key")
        return {"X-API-Key-ID": self.key}

    async def transcribe(self, audio: bytes, language: str | None) -> tuple[str, str, str]:
        model = self.stt_model
        if model == "prisma-v2.5" and not language:
            raise ServiceError("Choose a language for Prisma v2.5.", 400, "language_selection_required")
        fields = {"model": model, "language_code": language or "indic-auto"}
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.post(
                    f"{GNANI_BASE}/stt/v3", headers=self._headers(),
                    data=fields, files={"audio_file": ("request.wav", audio, "audio/wav")},
                )
        except httpx.RequestError as exc:
            raise ServiceError("Could not reach Gnani speech recognition. Please retry.", 502, "stt_unavailable") from exc
        if response.status_code >= 400:
            if model == "prisma-v3.0" and language is None and response.status_code == 400:
                raise ServiceError("Choose a language and try again.", 400, "language_selection_required")
            self._raise_api_error(response, "speech recognition")
        try:
            payload = response.json()
        except ValueError as exc:
            raise ServiceError("Gnani returned an unreadable transcript response.", 502, "invalid_stt_response") from exc
        transcript = str(payload.get("transcript") or "").strip()
        if not transcript:
            raise ServiceError("No speech was detected. Please record again in a quieter place.", 422, "empty_transcript")
        detected = payload.get("detected_language_code") or language
        if detected not in LANGUAGES:
            raise ServiceError("Choose a language so I can answer in the same language.", 400, "language_selection_required")
        return transcript, detected, model

    async def synthesize(self, text: str, language: str) -> bytes:
        voice = LANGUAGES[language][1] if self.tts_model == "timbre-v2.5" else "Shivani"
        payload = {
            "text": text, "model": self.tts_model, "voice": voice, "language": language,
            "audio_config": {"encoding": "linear_pcm", "container": "wav", "num_channels": 1, "sample_rate": 24000, "sample_width": 2},
        }
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.post(
                    f"{GNANI_BASE}/api/v1/tts/inference", headers=self._headers(), json=payload,
                )
        except httpx.RequestError as exc:
            raise ServiceError("Could not reach Gnani speech synthesis.", 502, "tts_unavailable") from exc
        if response.status_code >= 400:
            self._raise_api_error(response, "speech synthesis")
        if not response.content:
            raise ServiceError("Gnani returned empty speech audio.", 502, "empty_audio")
        # Timbre REST may use streaming WAV placeholders (RIFF/data size 0xffffffff).
        # Rewrite the header with the actual bytes so browsers and duration checks work.
        try:
            with wave.open(io.BytesIO(response.content), "rb") as source:
                if source.getnchannels() != 1 or source.getsampwidth() != 2:
                    raise wave.Error("Unexpected PCM format")
                channels, width, rate = source.getnchannels(), source.getsampwidth(), source.getframerate()
                frames = source.readframes(10_000_000)
            output = io.BytesIO()
            with wave.open(output, "wb") as target:
                target.setnchannels(channels)
                target.setsampwidth(width)
                target.setframerate(rate)
                target.writeframes(frames)
            return output.getvalue()
        except (wave.Error, EOFError, ValueError) as exc:
            raise ServiceError("Gnani returned unreadable speech audio.", 502, "invalid_tts_audio") from exc

    @staticmethod
    def _raise_api_error(response: httpx.Response, service: str) -> None:
        if response.status_code == 429:
            raise ServiceError(f"Gnani {service} is rate limited. Wait a moment and retry.", 429, "rate_limited")
        if response.status_code in {401, 403}:
            raise ServiceError(f"Gnani {service} rejected the API key or model access. Check the dashboard and model settings.", 403, "gnani_access_denied")
        if response.status_code == 400:
            raise ServiceError(f"Gnani {service} rejected the request. Check the selected model and language.", 400, "gnani_bad_request")
        raise ServiceError(f"Gnani {service} failed (HTTP {response.status_code}). Please retry.", 502, "gnani_error")
