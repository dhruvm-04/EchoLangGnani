"""Conversation rules kept separate from API and model adapters."""

from __future__ import annotations

import re
from dataclasses import dataclass, asdict

LANGUAGES = {
    "bn-IN": ("Bengali", "Dhruva"),
    "en-IN": ("English", "Kaveri"),
    "gu-IN": ("Gujarati", "Falak"),
    "hi-IN": ("Hindi", "Nalini"),
    "kn-IN": ("Kannada", "Saanvi"),
    "ml-IN": ("Malayalam", "Reshma"),
    "mr-IN": ("Marathi", "Ishaan"),
    "pa-IN": ("Punjabi", "Mehuli"),
    "ta-IN": ("Tamil", "Asmita"),
    "te-IN": ("Telugu", "Suhana"),
}

YES = {"yes", "yeah", "yep", "correct", "right", "okay", "ok", "sure", "confirm", "please do", "go ahead"}
NO = {"no", "nope", "wrong", "incorrect", "change", "not that"}
GENERIC_LOCATIONS = {"me", "here", "my house", "my home", "home", "my area", "the house", "the shop"}


@dataclass
class State:
    phase: str = "new"
    category: str | None = None
    location: str | None = None
    language: str | None = None
    availability: str | None = None
    preferred_language: str | None = None
    result_index: int = 0

    @classmethod
    def from_dict(cls, raw: dict | None) -> "State":
        raw = raw or {}
        if not isinstance(raw, dict):
            raise ValueError("Conversation state must be an object")
        return cls(
            phase=raw.get("phase") if raw.get("phase") in {"new", "awaiting_location", "awaiting_confirmation", "done"} else "new",
            category=str(raw.get("category"))[:80] if raw.get("category") else None,
            location=str(raw.get("location"))[:100] if raw.get("location") else None,
            language=raw.get("language") if raw.get("language") in LANGUAGES else None,
            availability=str(raw.get("availability"))[:80] if raw.get("availability") else None,
            preferred_language=str(raw.get("preferred_language"))[:60] if raw.get("preferred_language") else None,
            result_index=max(0, min(99, raw.get("result_index", 0))) if isinstance(raw.get("result_index", 0), int) else 0,
        )


def clean_location(value: str) -> str | None:
    value = re.sub(r"\b(?:please|thanks|thank you)\b.*$", "", value, flags=re.I)
    value = re.sub(r"\b(?:I am|I'm|I live|we are|it is|search|look|find|around|near|at|in|from)\b\s*", "", value, flags=re.I)
    value = re.sub(r"[^\w\s,.-]", "", value, flags=re.UNICODE).strip(" ,.-")
    value = re.sub(r"\s+", " ", value)[:100]
    return value if value and value.lower() not in GENERIC_LOCATIONS else None


def location_from_request(english: str) -> str | None:
    # The app confirms extracted locations; never silently treat a phrase as a precise address.
    match = re.search(r"\b(?:in|around|near|at)\s+([\w][\w\s,.-]{1,80})", english, flags=re.I)
    if not match:
        return None
    phrase = re.split(r"\b(?:for|because|today|tomorrow|who|that|which|please|to)\b|[.!?]", match.group(1), maxsplit=1, flags=re.I)[0]
    return clean_location(phrase)


def confirmation(english: str) -> bool | None:
    words = re.sub(r"[^a-z\s]", " ", english.lower()).strip()
    if words in YES or words.startswith(("yes ", "correct ", "right ", "okay ")):
        return True
    if words in NO or words.startswith(("no ", "wrong ", "change ")):
        return False
    return None


def decide(state: State, english: str, detected_language: str, category: str | None, alternative: str | None, spoken_location: str | None = None) -> tuple[State, str]:
    """Return the next conversation state and an English reply."""
    language = state.language or detected_language
    if state.phase == "awaiting_confirmation":
        answer = confirmation(english)
        if answer is True and state.category:
            if not state.location:
                next_state = State("awaiting_location", state.category, None, language)
                return next_state, "Which city or neighbourhood should I search in?"
            next_state = State("done", state.category, state.location, language)
            return next_state, f"Searching for {state.category} near {state.location}."
        if answer is False:
            next_state = State(language=language)
            return next_state, "Please describe the service and location again."
        return state, "Please say yes to search, or no to change the request."

    if state.phase == "awaiting_location" and state.category:
        location = clean_location(spoken_location or english)
        if not location:
            return state, "I did not catch the place. Please say the city or neighbourhood again."
        next_state = State("awaiting_confirmation", state.category, location, language)
        return next_state, f"You need a {state.category} in {location}. Is that right?"

    location = spoken_location or state.location or location_from_request(english)

    if category and alternative:
        return State(language=language, location=location), f"Do you need {category} or {alternative}? Please say which one."
    if not category:
        hint = f" Did you mean {alternative}?" if alternative else ""
        return State(language=language, location=location), "I could not identify the service clearly. Please describe what needs help." + hint
    if not location:
        next_state = State("awaiting_location", category, None, language)
        return next_state, f"I heard {category}. Which city or neighbourhood should I search in?"
    next_state = State("awaiting_confirmation", category, location, language)
    return next_state, f"You need a {category} near {location}. Is that right?"


def state_dict(state: State) -> dict:
    return asdict(state)
