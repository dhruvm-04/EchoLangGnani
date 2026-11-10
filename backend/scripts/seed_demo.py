"""Add clearly fictional providers to an existing local EchoLang directory."""

from pathlib import Path

from dotenv import load_dotenv

from app.demo_seed import CITIES, SERVICES, demo_listings, seed_demo
from app.directory import DirectoryStore


load_dotenv(Path(__file__).resolve().parents[1] / ".env")
added, removed = seed_demo(DirectoryStore())
print(f"Demo directory: {sum(1 for _ in demo_listings())} listings across "
      f"{len(CITIES)} cities and {len(SERVICES)} service types; "
      f"{added} added, {removed} old samples removed.")
