"""SQLite storage for provider drafts, listings, and reports."""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import sqlite3
from contextlib import closing, contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

from .matching import area_matches, availability_matches, language_matches, service_score


FIELDS = ("name", "services", "area", "delivery", "phone", "hours", "languages", "price")
QUESTIONS = {
    "name": "What should customers call you or your business?",
    "services": "What services do you offer? You can name more than one.",
    "area": "Which city or neighborhoods do you serve? Your home address will not be shown.",
    "delivery": "Do you visit customers, work online, or receive them at your place?",
    "phone": "What phone number should customers call? I will read it back before saving.",
    "hours": "When are you usually available? You can say skip.",
    "languages": "Which languages can you speak with customers? You can say skip.",
    "price": "Do you have a starting price, or do you quote each job? You can say skip.",
}
REQUIRED = set(FIELDS[:5])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def clean(value: str, limit: int = 160) -> str:
    return re.sub(r"[<>\r\n\x00-\x1f]", " ", value).strip()[:limit]


def phone_digits(value: str) -> str:
    return re.sub(r"\D", "", value)


def split_services(value: str) -> list[str]:
    parts = re.split(r"[,;]|\band\b", value, flags=re.I)
    return list(dict.fromkeys(clean(part, 80) for part in parts if clean(part, 80)))[:10]


class DirectoryStore:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path or os.getenv("ECHOLANG_DB_PATH") or Path(__file__).resolve().parents[1] / "data" / "echolang.sqlite3")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    @contextmanager
    def _db(self):
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 10000")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _init(self) -> None:
        with self._db() as db:
            db.execute("PRAGMA journal_mode = WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS drafts (
                    id TEXT PRIMARY KEY, fields TEXT NOT NULL, cursor INTEGER NOT NULL,
                    language TEXT NOT NULL, expires_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS providers (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL, area TEXT NOT NULL,
                    delivery TEXT NOT NULL, phone TEXT NOT NULL, hours TEXT NOT NULL,
                    languages TEXT NOT NULL, price TEXT NOT NULL, token_hash TEXT NOT NULL,
                    status TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS services (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, provider_id TEXT NOT NULL REFERENCES providers(id) ON DELETE CASCADE,
                    name TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS services_name_idx ON services(name);
                CREATE INDEX IF NOT EXISTS providers_area_idx ON providers(area);
                CREATE TABLE IF NOT EXISTS reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, provider_id TEXT NOT NULL REFERENCES providers(id),
                    reason TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS edits (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, provider_id TEXT NOT NULL REFERENCES providers(id),
                    field TEXT NOT NULL, old_value TEXT NOT NULL, new_value TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS daily_metrics (
                    day TEXT NOT NULL, event TEXT NOT NULL, count INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (day, event)
                );
            """)
            columns = {row["name"] for row in db.execute("PRAGMA table_info(reports)")}
            if "resolved_at" not in columns:
                db.execute("ALTER TABLE reports ADD COLUMN resolved_at TEXT")
            if "resolution" not in columns:
                db.execute("ALTER TABLE reports ADD COLUMN resolution TEXT")
            db.execute("CREATE INDEX IF NOT EXISTS providers_phone_idx ON providers(phone)")

    def seed_demo(self, listings: Iterable[dict]) -> tuple[int, int]:
        """Sync sample listings without changing real or retained sample rows."""
        listings = tuple(listings)
        wanted = {listing["id"] for listing in listings}
        if not listings or len(wanted) != len(listings) or any(not item.startswith("demo-") for item in wanted):
            raise ValueError("Demo listings need unique demo-prefixed IDs.")
        timestamp = _now()
        added = 0
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            obsolete = [row["id"] for row in db.execute("SELECT id FROM providers WHERE id LIKE 'demo-%'")
                        if row["id"] not in wanted]
            for provider_id in obsolete:
                db.execute("DELETE FROM reports WHERE provider_id = ?", (provider_id,))
                db.execute("DELETE FROM edits WHERE provider_id = ?", (provider_id,))
                db.execute("DELETE FROM providers WHERE id = ?", (provider_id,))
            for listing in listings:
                inserted = db.execute(
                    """INSERT OR IGNORE INTO providers
                       (id, name, area, delivery, phone, hours, languages, price,
                        token_hash, status, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'published', ?, ?)""",
                    (listing["id"], listing["name"], listing["area"], listing["delivery"],
                     listing["phone"], listing["hours"], listing["languages"], listing["price"],
                     hashlib.sha256(secrets.token_bytes(32)).hexdigest(), timestamp, timestamp),
                )
                if inserted.rowcount:
                    db.executemany(
                        "INSERT INTO services (provider_id, name) VALUES (?, ?)",
                        [(listing["id"], service) for service in listing["services"]],
                    )
                    added += 1
        return added, len(obsolete)

    def new_draft(self, language: str) -> dict:
        draft = {"id": secrets.token_urlsafe(24), "fields": {}, "cursor": 0, "language": language}
        expires = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
        with self._db() as db:
            db.execute("DELETE FROM drafts WHERE expires_at < ?", (_now(),))
            db.execute("INSERT INTO drafts VALUES (?, ?, ?, ?, ?)", (draft["id"], "{}", 0, language, expires))
        return draft

    def get_draft(self, draft_id: str) -> dict | None:
        with self._db() as db:
            row = db.execute("SELECT * FROM drafts WHERE id = ? AND expires_at > ?", (draft_id, _now())).fetchone()
        return {"id": row["id"], "fields": json.loads(row["fields"]), "cursor": row["cursor"], "language": row["language"]} if row else None

    def save_draft(self, draft: dict) -> None:
        with self._db() as db:
            db.execute("UPDATE drafts SET fields = ?, cursor = ?, language = ? WHERE id = ?",
                       (json.dumps(draft["fields"]), draft["cursor"], draft["language"], draft["id"]))

    def publish(self, draft: dict, require_approval: bool = False) -> tuple[dict, str]:
        fields = draft["fields"]
        if any(not fields.get(field) for field in REQUIRED):
            raise ValueError("The required listing details are incomplete.")
        services = split_services(fields["services"])
        phone = phone_digits(fields["phone"])
        if not services or not 10 <= len(phone) <= 15:
            raise ValueError("Services or phone number need correction.")
        provider_id = secrets.token_urlsafe(12)
        token = secrets.token_urlsafe(32)
        timestamp = _now()
        status = "pending" if require_approval else "published"
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute("SELECT id FROM providers WHERE phone = ? AND status IN ('published', 'pending', 'paused', 'hidden') LIMIT 1", (phone,)).fetchone()
            if existing:
                raise ValueError("This phone number already has a listing. Open that listing on its original device or ask an operator for help.")
            db.execute(
                "INSERT INTO providers VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (provider_id, fields["name"], fields["area"], fields["delivery"], phone,
                 fields.get("hours", ""), fields.get("languages", ""), fields.get("price", ""),
                 hashlib.sha256(token.encode()).hexdigest(), status, timestamp, timestamp),
            )
            db.executemany("INSERT INTO services (provider_id, name) VALUES (?, ?)", [(provider_id, service) for service in services])
            db.execute("DELETE FROM drafts WHERE id = ?", (draft["id"],))
        return self.get_provider(provider_id), token

    def get_provider(self, provider_id: str) -> dict | None:
        with self._db() as db:
            row = db.execute("SELECT * FROM providers WHERE id = ?", (provider_id,)).fetchone()
            if not row:
                return None
            services = [item["name"] for item in db.execute("SELECT name FROM services WHERE provider_id = ?", (provider_id,))]
        return self._public(row, services)

    @staticmethod
    def _public(row: sqlite3.Row, services: list[str]) -> dict:
        return {key: row[key] for key in ("id", "name", "area", "delivery", "phone", "hours", "languages", "price", "status", "updated_at")} | {"services": services}

    def owner(self, token: str) -> dict | None:
        if not token or len(token) > 200:
            return None
        digest = hashlib.sha256(token.encode()).hexdigest()
        with self._db() as db:
            row = db.execute("SELECT id FROM providers WHERE token_hash = ?", (digest,)).fetchone()
        return self.get_provider(row["id"]) if row else None

    def update(self, provider_id: str, field: str, value: str) -> dict:
        if field not in FIELDS:
            raise ValueError("Unknown listing field.")
        value = clean(value, 240)
        if field in REQUIRED and not value:
            raise ValueError("This detail cannot be empty.")
        if field == "phone":
            value = phone_digits(value)
            if not 10 <= len(value) <= 15:
                raise ValueError("Please give a 10 to 15 digit phone number.")
        if field == "services" and not split_services(value):
            raise ValueError("Please name at least one service.")
        before = self.get_provider(provider_id)
        if not before:
            raise ValueError("Listing not found.")
        old = ", ".join(before["services"]) if field == "services" else before[field]
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            if field == "phone":
                duplicate = db.execute("SELECT id FROM providers WHERE phone = ? AND id != ? AND status IN ('published', 'pending', 'paused', 'hidden') LIMIT 1", (value, provider_id)).fetchone()
                if duplicate:
                    raise ValueError("This phone number already has a listing.")
            if field == "services":
                db.execute("DELETE FROM services WHERE provider_id = ?", (provider_id,))
                db.executemany("INSERT INTO services (provider_id, name) VALUES (?, ?)", [(provider_id, item) for item in split_services(value)])
            else:
                db.execute(f"UPDATE providers SET {field} = ? WHERE id = ?", (value, provider_id))
            db.execute("UPDATE providers SET updated_at = ? WHERE id = ?", (_now(), provider_id))
            db.execute("INSERT INTO edits (provider_id, field, old_value, new_value, created_at) VALUES (?, ?, ?, ?, ?)", (provider_id, field, old, value, _now()))
        return self.get_provider(provider_id)

    def search(self, service: str, area: str | None = None, limit: int = 8,
               availability: str | None = None, language: str | None = None,
               now: datetime | None = None) -> list[dict]:
        if not service.strip():
            return []
        with self._db() as db:
            rows = db.execute("SELECT * FROM providers WHERE status = 'published'").fetchall()
            services_by_provider: dict[str, list[str]] = {}
            for item in db.execute("""SELECT services.provider_id, services.name FROM services
                                      JOIN providers ON providers.id = services.provider_id
                                      WHERE providers.status = 'published'"""):
                services_by_provider.setdefault(item["provider_id"], []).append(item["name"])
            candidates = []
            for row in rows:
                if not area_matches(area, row["area"]):
                    continue
                services = services_by_provider.get(row["id"], [])
                score = max((service_score(service, item) for item in services), default=0)
                if score == 0:
                    continue
                if not availability_matches(availability, row["hours"], now):
                    continue
                if not language_matches(language, row["languages"]):
                    continue
                candidates.append((score, self._public(row, services)))
        candidates.sort(key=lambda pair: (-pair[0], pair[1]["name"].casefold()))
        return [provider for _, provider in candidates[:limit]]

    def report(self, provider_id: str, reason: str) -> None:
        if not self.get_provider(provider_id):
            raise ValueError("Listing not found.")
        with self._db() as db:
            db.execute("INSERT INTO reports (provider_id, reason, created_at) VALUES (?, ?, ?)", (provider_id, clean(reason, 200), _now()))

    def pending(self) -> list[dict]:
        with self._db() as db:
            ids = [row["id"] for row in db.execute("SELECT id FROM providers WHERE status = 'pending' ORDER BY created_at")]
        return [self.get_provider(provider_id) for provider_id in ids]

    def by_phone(self, phone: str) -> list[dict]:
        digits = phone_digits(phone)
        if not 10 <= len(digits) <= 15:
            return []
        with self._db() as db:
            ids = [row["id"] for row in db.execute("SELECT id FROM providers WHERE phone = ? ORDER BY updated_at DESC LIMIT 10", (digits,))]
        return [self.get_provider(provider_id) for provider_id in ids]

    def reports(self) -> list[dict]:
        with self._db() as db:
            rows = db.execute("SELECT reports.id, reports.provider_id, reports.reason, reports.created_at, reports.resolved_at, reports.resolution, providers.name, providers.phone, providers.status FROM reports JOIN providers ON providers.id = reports.provider_id WHERE reports.resolved_at IS NULL ORDER BY reports.created_at DESC LIMIT 100").fetchall()
        return [dict(row) for row in rows]

    def resolve_report(self, report_id: int, resolution: str) -> dict | None:
        if resolution not in {"checked", "hidden"}:
            raise ValueError("Invalid report resolution.")
        with self._db() as db:
            row = db.execute("SELECT provider_id FROM reports WHERE id = ? AND resolved_at IS NULL", (report_id,)).fetchone()
            if not row:
                return None
            if resolution == "hidden":
                db.execute("UPDATE providers SET status = 'hidden', updated_at = ? WHERE id = ?", (_now(), row["provider_id"]))
            db.execute("UPDATE reports SET resolved_at = ?, resolution = ? WHERE id = ?", (_now(), resolution, report_id))
        return {"id": report_id, "provider_id": row["provider_id"], "resolution": resolution}

    def owner_status(self, provider_id: str, status: str) -> dict:
        if status not in {"published", "paused"}:
            raise ValueError("Invalid status.")
        current = self.get_provider(provider_id)
        if not current or current["status"] not in {"published", "paused"}:
            raise ValueError("This listing cannot be changed yet.")
        with self._db() as db:
            db.execute("UPDATE providers SET status = ?, updated_at = ? WHERE id = ?", (status, _now(), provider_id))
        return self.get_provider(provider_id)

    def delete_provider(self, provider_id: str) -> None:
        with self._db() as db:
            db.execute("DELETE FROM reports WHERE provider_id = ?", (provider_id,))
            db.execute("DELETE FROM providers WHERE id = ?", (provider_id,))

    def rotate_owner(self, provider_id: str) -> str:
        token = secrets.token_urlsafe(32)
        with self._db() as db:
            updated = db.execute("UPDATE providers SET token_hash = ? WHERE id = ?", (hashlib.sha256(token.encode()).hexdigest(), provider_id))
            if not updated.rowcount:
                raise ValueError("Listing not found.")
        return token

    def backup(self, destination: str | Path) -> Path:
        target = Path(destination).resolve()
        if target == self.path.resolve():
            raise ValueError("Backup destination must differ from the live database.")
        target.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path)) as source, closing(sqlite3.connect(target)) as copy:
            source.backup(copy)
        return target

    def record_event(self, event: str) -> None:
        if event not in {"provider_started", "provider_published", "search_with_results", "search_without_results", "contact_tapped", "listing_reported"}:
            raise ValueError("Unknown metric.")
        with self._db() as db:
            db.execute("INSERT INTO daily_metrics(day, event, count) VALUES (?, ?, 1) ON CONFLICT(day, event) DO UPDATE SET count = count + 1", (_now()[:10], event))

    def metrics(self, days: int = 30) -> dict[str, int]:
        since = (datetime.now(timezone.utc) - timedelta(days=days - 1)).date().isoformat()
        with self._db() as db:
            rows = db.execute("SELECT event, SUM(count) AS count FROM daily_metrics WHERE day >= ? GROUP BY event", (since,)).fetchall()
            statuses = db.execute("SELECT status, COUNT(*) AS count FROM providers WHERE id NOT LIKE 'demo-%' GROUP BY status").fetchall()
        return {**{row["event"]: row["count"] for row in rows}, **{f"listings_{row['status']}": row["count"] for row in statuses}}

    def set_status(self, provider_id: str, status: str) -> dict | None:
        if status not in {"published", "rejected", "hidden"}:
            raise ValueError("Invalid status.")
        with self._db() as db:
            db.execute("UPDATE providers SET status = ?, updated_at = ? WHERE id = ?", (status, _now(), provider_id))
        return self.get_provider(provider_id)
