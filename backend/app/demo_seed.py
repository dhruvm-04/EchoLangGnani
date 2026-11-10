"""A small, deterministic set of fictional listings for the public demo."""

from __future__ import annotations

import re

from .directory import DirectoryStore


# City, local language, service, searchable phrases, and delivery method.
SAMPLES = (
    ("Udaipur", "Hindi", "Fan repair", ("fan repair", "ceiling fan repair", "fan service"), "Home visits"),
    ("Nanded", "Marathi", "Plumber", ("plumber", "plumbing", "pipe repair", "tap repair"), "Home visits"),
    ("Delhi", "Hindi", "Electrician", ("electrician", "electrical work", "wiring"), "Home visits"),
    ("Chennai", "Tamil", "AC repair", ("AC repair", "air conditioner repair", "AC service"), "Home visits"),
    ("Kolkata", "Bengali", "Mobile phone repair", ("mobile phone repair", "phone repair"), "At the shop"),
    ("Kochi", "Malayalam", "Pest control", ("pest control", "termite treatment"), "Home visits"),
)

CITIES = tuple((city, language) for city, language, *_ in SAMPLES)
SERVICES = tuple((label, phrases, delivery) for _, _, label, phrases, delivery in SAMPLES)


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")


def demo_listings():
    """Yield six sample entries with stable IDs and unreachable 000 numbers."""
    for number, (city, local_language, label, phrases, delivery) in enumerate(SAMPLES, 1):
        yield {
            "id": f"demo-{_slug(city)}-{_slug(label)}-1",
            "name": f"Demo — {city} {label}",
            "area": "New Delhi, Delhi" if city == "Delhi" else city,
            "delivery": delivery,
            "phone": f"000{number:07d}",
            "hours": "Daily 9:00-21:00",
            "languages": ", ".join(dict.fromkeys((local_language, "Hindi", "English"))),
            "price": "Demo listing; quote on request",
            "services": phrases,
        }


def seed_demo(store: DirectoryStore) -> tuple[int, int]:
    return store.seed_demo(demo_listings())
