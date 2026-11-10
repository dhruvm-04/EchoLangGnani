"""Conservative local matching for spoken service and area names."""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timedelta, timezone
from functools import lru_cache


# This expands common spoken terms without limiting the directory to these services.
SERVICE_ALIASES = {
    "plumber": ("plumber", "plumbing", "pipe repair", "tap repair", "water leak"),
    "electrician": ("electrician", "electrical work", "wiring", "electrical repair"),
    "fan repair": ("fan repair", "ceiling fan repair", "fan service", "fan mechanic", "fix fan"),
    "mixer repair": ("mixer repair", "mixer grinder repair", "mixie repair", "mixie service"),
    "carpenter": ("carpenter", "carpentry", "woodwork", "furniture repair"),
    "tailor": ("tailor", "tailoring", "stitching", "clothes alteration", "seamstress"),
    "tutor": ("tutor", "tuition", "home tuition", "private teacher", "tutoring"),
    "house cleaning": ("house cleaning", "home cleaning", "cleaner", "cleaning service"),
    "cook": ("cook", "home cook", "personal chef", "cooking service"),
    "driver": ("driver", "chauffeur", "driving service"),
}
AREA_ALIASES = {
    "bangalore": "bengaluru", "bengaluru": "bengaluru",
    "bombay": "mumbai", "mumbai": "mumbai",
    "calcutta": "kolkata", "kolkata": "kolkata",
    "madras": "chennai", "chennai": "chennai",
}
LANGUAGE_ALIASES = {
    "bengali": ("bengali", "bangla", "bn-in"),
    "english": ("english", "en-in"),
    "gujarati": ("gujarati", "gu-in"),
    "hindi": ("hindi", "hi-in"),
    "kannada": ("kannada", "kn-in"),
    "malayalam": ("malayalam", "ml-in"),
    "marathi": ("marathi", "mr-in"),
    "punjabi": ("punjabi", "pa-in"),
    "tamil": ("tamil", "ta-in"),
    "telugu": ("telugu", "te-in"),
}
DAY_NAMES = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
INDIA_TIME = timezone(timedelta(hours=5, minutes=30))
SERVICE_FILLER = {"repair", "service", "services", "help", "home", "local", "work", "person", "someone"}
AREA_FILLER = {"near", "around", "in", "at", "area", "areas", "nearby", "city", "town"}


@lru_cache(maxsize=8192)
def normalized(value: str) -> str:
    ascii_value = unicodedata.normalize("NFKD", value.casefold()).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", ascii_value)).strip()


@lru_cache(maxsize=8192)
def tokens(value: str) -> frozenset[str]:
    return frozenset(word[:-1] if len(word) > 4 and word.endswith("s") else word for word in normalized(value).split())


@lru_cache(maxsize=8192)
def concepts(value: str) -> frozenset[str]:
    phrase = f" {normalized(value)} "
    return frozenset(key for key, aliases in SERVICE_ALIASES.items()
                     if any(f" {normalized(alias)} " in phrase for alias in aliases))


def service_score(query: str, offered: str) -> int:
    query_concepts, offered_concepts = concepts(query), concepts(offered)
    if query_concepts and offered_concepts and query_concepts & offered_concepts:
        return 100 + len(query_concepts & offered_concepts)
    specific = tokens(query) - SERVICE_FILLER
    if not specific:
        specific = tokens(query)
    return len(specific) if specific and specific.issubset(tokens(offered)) else 0


def area_matches(requested: str | None, served: str) -> bool:
    if not requested:
        return True
    def parts(value: str) -> list[set[str]]:
        return [{AREA_ALIASES.get(word, word) for word in tokens(part) - AREA_FILLER}
                for part in re.split(r"[,;]|\band\b", value, flags=re.I)]
    requested_parts = [part for part in parts(requested) if part]
    served_parts = [part for part in parts(served) if part]
    return bool(requested_parts) and all(any(wanted.issubset(covered) for covered in served_parts)
                                         for wanted in requested_parts)


def language_matches(requested: str | None, spoken: str) -> bool:
    if not requested:
        return True
    request = normalized(requested)
    wanted = next((name for name, aliases in LANGUAGE_ALIASES.items()
                   if request == name or request in (normalized(alias) for alias in aliases)), request)
    offered = normalized(spoken)
    return any(wanted == name and any(f" {normalized(alias)} " in f" {offered} " for alias in aliases)
               for name, aliases in LANGUAGE_ALIASES.items())


def _days_in_hours(hours: str) -> set[int] | None:
    value = normalized(hours)
    if any(term in value for term in ("24 7", "every day", "everyday", "daily", "all days", "seven days")):
        return set(range(7))
    days = set()
    if "weekdays" in value or "weekday" in value:
        days.update(range(5))
    if "weekends" in value or "weekend" in value:
        days.update((5, 6))
    aliases = {day[:3]: index for index, day in enumerate(DAY_NAMES)}
    aliases.update({day: index for index, day in enumerate(DAY_NAMES)})
    for first, last in re.findall(r"\b(mon(?:day)?|tue(?:sday)?|wed(?:nesday)?|thu(?:rsday)?|fri(?:day)?|sat(?:urday)?|sun(?:day)?)\s*(?:to|through|-)\s*(mon(?:day)?|tue(?:sday)?|wed(?:nesday)?|thu(?:rsday)?|fri(?:day)?|sat(?:urday)?|sun(?:day)?)\b", hours.casefold()):
        start, end = aliases[first], aliases[last]
        days.update(range(start, end + 1) if start <= end else list(range(start, 7)) + list(range(end + 1)))
    days.update(index for index, day in enumerate(DAY_NAMES) if day in value or day[:3] in value.split())
    return days or None


def _time_range(hours: str) -> tuple[int, int] | None:
    # Require explicit AM/PM to avoid guessing whether "9 to 5" means morning or evening.
    match = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\s*(?:to|-|until)\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", hours.casefold())
    if not match:
        clock = re.search(r"\b(\d{1,2}):(\d{2})\s*(?:to|-)\s*(\d{1,2}):(\d{2})\b", hours.casefold())
        if not clock:
            return None
        start, end = int(clock[1]) * 60 + int(clock[2]), int(clock[3]) * 60 + int(clock[4])
        return (start, end) if 0 <= start < 24 * 60 and 0 <= end < 24 * 60 else None
    def minutes(hour: str, minute: str | None, period: str) -> int:
        return (int(hour) % 12 + (12 if period == "pm" else 0)) * 60 + int(minute or 0)
    return minutes(match[1], match[2], match[3]), minutes(match[4], match[5], match[6])


def availability_matches(requested: str | None, hours: str, now: datetime | None = None) -> bool:
    if not requested:
        return True
    constraints = [part.strip() for part in requested.split(",") if part.strip()]
    if len(constraints) > 1:
        return all(availability_matches(part, hours, now) for part in constraints)
    if not hours.strip():
        return False
    value = normalized(hours)
    request = normalized(requested)
    today = (now or datetime.now(INDIA_TIME)).astimezone(INDIA_TIME)
    days = _days_in_hours(hours)
    if request in {"weekend", "weekends"}:
        return days is not None and bool(days & {5, 6})
    if request in {"weekday", "weekdays"}:
        return days is not None and bool(days & set(range(5)))
    if request in DAY_NAMES:
        return days is not None and DAY_NAMES.index(request) in days
    if request in {"today", "tomorrow", "now"}:
        day = today if request != "tomorrow" else today + timedelta(days=1)
        if days is None or day.weekday() not in days:
            return False
        if request != "now":
            return True
        if "24 7" in value or "24 hours" in value:
            return True
        interval = _time_range(hours)
        if interval is None:
            return False
        minute = today.hour * 60 + today.minute
        start, end = interval
        return start <= minute < end if start <= end else minute >= start or minute < end
    periods = {"morning": (5, 12), "afternoon": (12, 17), "evening": (17, 22), "night": (22, 29)}
    if request in periods:
        if request in value or "24 7" in value:
            return True
        interval = _time_range(hours)
        if interval:
            start, end = interval
            if end <= start:
                end += 24 * 60
            lower, upper = periods[request]
            return start < upper * 60 and end > lower * 60
    return False
