"""Multilingual semantic parsing with a hosted OpenAI-compatible endpoint."""

from __future__ import annotations

import json
import os
import re

import httpx

from .adapters import ServiceError
from .core import LANGUAGES


class MultilingualReasoner:
    """Translate spoken meaning to English fields, then render replies in the same language."""

    def __init__(self):
        self.base_url = os.getenv("ECHOLANG_LLM_BASE_URL", "").rstrip("/")
        self.key = os.getenv("ECHOLANG_LLM_API_KEY", "")
        self.model = os.getenv("ECHOLANG_LLM_MODEL", "")

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.key and self.model)

    async def _json(self, system: str, user: dict, schema_name: str, fields: dict) -> dict:
        if not self.configured:
            raise ServiceError("Set the reasoning endpoint, model and key on the backend.", 503, "reasoning_not_configured")
        payload = {
            "model": self.model, "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
            ],
        }
        if self.model == "openai/gpt-oss-120b" and self.base_url.startswith("https://api.groq.com/"):
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": schema_name, "strict": True,
                    "schema": {
                        "type": "object", "properties": fields,
                        "required": list(fields), "additionalProperties": False,
                    },
                },
            }
            payload["reasoning_effort"] = "low"
            payload["include_reasoning"] = False
            payload["max_completion_tokens"] = 512
        try:
            async with httpx.AsyncClient(timeout=45) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self.key}"}, json=payload,
                )
        except httpx.RequestError as exc:
            raise ServiceError("Reasoning is offline. Please retry.", 502, "reasoning_unavailable") from exc
        if response.status_code == 429:
            raise ServiceError("Reasoning is busy. Wait a moment and retry.", 429, "rate_limited")
        if response.status_code >= 400:
            raise ServiceError("Reasoning endpoint rejected the request. Check its key and model.", 502, "reasoning_unavailable")
        try:
            raw = response.json()["choices"][0]["message"]["content"]
            result = json.loads(raw)
            if not isinstance(result, dict):
                raise ValueError("Expected object")
            return result
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise ServiceError("Could not understand the reasoning reply. Please retry.", 502, "invalid_reasoning_response") from exc

    async def interpret(self, transcript: str, language: str, phase: str) -> dict:
        result = await self._json(
            "Interpret a local-service request in India. Read the language directly, including code-mixed speech. "
            "Return JSON string fields english_request, service, location, alternative, answer, availability, preferred_language. "
            "english_request is a faithful short English translation. service is a short English directory "
            "search phrase (such as plumber, fridge repair, ambulance), or empty string if unclear. "
            "location is only a city, town, village or neighbourhood explicitly spoken in this utterance, "
            "in common Latin spelling, or empty string. Never infer a place. alternative is a possible service "
            "only when there is genuine ambiguity; otherwise empty string. If phase is awaiting_location, "
            "treat the utterance as a place answer and set service empty. If phase is awaiting_confirmation, "
            "set answer to yes, no, or empty string according to the utterance. Otherwise answer is empty. "
            "availability is only an explicitly requested time: now, today, tomorrow, weekday, weekend, "
            "morning, afternoon, evening, night, or a full English weekday name. Use comma-separated terms "
            "for combined constraints, such as today, evening. Otherwise empty. preferred_language is the "
            "language the customer explicitly wants the provider to speak, in English, otherwise empty. "
            "Never infer availability or a preferred language. Never invent providers.",
            {"phase": phase, "language": language, "transcript": transcript},
            "service_request",
            {field: {"type": "string"} for field in ("english_request", "service", "location", "alternative", "answer", "availability", "preferred_language")},
        )
        def short(value: object, limit: int) -> str | None:
            if not isinstance(value, str):
                return None
            cleaned = re.sub(r"[\r\n<>]", " ", value).strip()[:limit]
            return cleaned or None
        return {
            "english_request": short(result.get("english_request"), 500) or transcript,
            "service": short(result.get("service"), 80),
            "location": short(result.get("location"), 100),
            "alternative": short(result.get("alternative"), 80),
            "answer": result.get("answer") if result.get("answer") in {"yes", "no"} else None,
            "availability": short(result.get("availability"), 80),
            "preferred_language": short(result.get("preferred_language"), 60),
        }

    async def navigate_results(self, transcript: str, language: str) -> str:
        result = await self._json(
            "The user is browsing local service results. Understand any Indian language or code-mixed speech. "
            "Return action as exactly one of next, previous, repeat, new_search, new_request, or call. "
            "Use new_request if the user starts asking for a different service or place. "
            "Use new_search only if they explicitly ask to start over. Use call only if they explicitly ask "
            "to contact the selected provider. Use repeat for unclear navigation requests. Do not invent results.",
            {"language": language, "transcript": transcript}, "result_navigation",
            {"action": {"type": "string"}},
        )
        action = result.get("action")
        return action if action in {"next", "previous", "repeat", "new_search", "new_request", "call"} else "repeat"

    async def localize(self, english: str, language: str) -> str:
        if language == "en-IN":
            return english
        result = await self._json(
            "Translate this short local-service app message into the requested language. "
            "Return JSON with exactly one string field: text. Use common, clear words. "
            "Keep place names as spoken. Preserve questions. Do not add information.",
            {"language": LANGUAGES[language][0], "text": english},
            "localized_reply", {"text": {"type": "string"}},
        )
        localized = result.get("text")
        if not isinstance(localized, str) or not localized.strip():
            raise ServiceError("Could not prepare the spoken reply. Please retry.", 502, "invalid_reasoning_response")
        return localized.strip()[:500]

    async def provider_answer(self, field: str, transcript: str) -> dict:
        """Extract only the detail currently being requested, in English where appropriate."""
        result = await self._json(
            "You are collecting one field for a local service provider's public directory entry. "
            "Return exactly value (string) and skip (boolean). Understand Indian languages and code-mixed speech. "
            "For services, return short searchable service phrases separated by commas; preserve every distinct skill. "
            "For area, give only the spoken city/neighborhoods in common Latin spelling, never infer an address. "
            "For languages, use common English names such as Hindi or Tamil. "
            "For hours, use English weekday and time words while preserving the spoken schedule; never guess hours. "
            "For phone, output digits only, including the country code if spoken. "
            "For price, never invent a number. Skip only when the speaker explicitly says to skip. "
            "Do not include unrelated details or fabricate missing information.",
            {"field": field, "transcript": transcript}, "provider_answer",
            {"value": {"type": "string"}, "skip": {"type": "boolean"}},
        )
        value = result.get("value")
        return {"value": re.sub(r"[\r\n<>]", " ", value).strip()[:240] if isinstance(value, str) else "",
                "skip": result.get("skip") is True}

    async def provider_command(self, transcript: str) -> dict:
        """Interpret a review or edit instruction without applying it."""
        result = await self._json(
            "Interpret a local service provider's spoken instruction in any Indian language. "
            "Return action as one of publish, change, cancel, or unclear; field as one of "
            "name, services, area, delivery, phone, hours, languages, price, or empty string; "
            "value as the new field value if it was spoken, otherwise empty string. "
            "Say publish only for an explicit approval to publish/save. Do not infer consent.",
            {"transcript": transcript}, "provider_command",
            {key: {"type": "string"} for key in ("action", "field", "value")},
        )
        return {key: result.get(key, "") if isinstance(result.get(key), str) else "" for key in ("action", "field", "value")}

    async def provider_edit(self, transcript: str) -> dict:
        result = await self._json(
            "Extract one proposed update to a local service provider's own listing. "
            "Return field (one of name, services, area, delivery, phone, hours, languages, price, or empty) "
            "and value (the new complete field value, or empty). For services, give the complete desired list "
            "only if the speaker stated it clearly. Do not invent existing services or missing details. "
            "For a request like 'add fan repair' return field services, value 'fan repair', and operation add. "
            "Use operation replace for a complete new value, or when the speaker does not explicitly say add. "
            "For phone, use digits only.",
            {"transcript": transcript}, "provider_edit",
            {"field": {"type": "string"}, "value": {"type": "string"}, "operation": {"type": "string"}},
        )
        return {key: result.get(key, "") if isinstance(result.get(key), str) else "" for key in ("field", "value", "operation")}
