import tempfile
import unittest
from pathlib import Path

from app.directory import DirectoryStore


class DirectoryLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "directory.sqlite3"
        self.store = DirectoryStore(self.path)

    def tearDown(self):
        self.temp.cleanup()

    def publish(self, phone="9876543210"):
        draft = self.store.new_draft("en-IN")
        draft["fields"] = {"name": "Asha", "services": "fan repair", "area": "Nanded",
                           "delivery": "home visits", "phone": phone, "hours": "weekdays",
                           "languages": "Hindi", "price": "quote"}
        return self.store.publish(draft)

    def test_duplicate_phone_is_rejected_and_draft_remains(self):
        self.publish()
        draft = self.store.new_draft("en-IN")
        draft["fields"] = {"name": "Other", "services": "plumbing", "area": "Nanded",
                           "delivery": "home visits", "phone": "9876543210"}
        with self.assertRaisesRegex(ValueError, "already has a listing"):
            self.store.publish(draft)
        self.assertIsNotNone(self.store.get_draft(draft["id"]))

    def test_pause_report_recovery_delete_and_backup(self):
        provider, token = self.publish()
        provider_id = provider["id"]
        self.store.owner_status(provider_id, "paused")
        self.assertEqual(self.store.search("fan repair", "Nanded"), [])
        self.store.owner_status(provider_id, "published")
        self.assertEqual(len(self.store.search("fan repair", "Nanded")), 1)
        self.store.report(provider_id, "Wrong number")
        report = self.store.reports()[0]
        self.assertEqual(report["phone"], "9876543210")
        self.store.resolve_report(report["id"], "hidden")
        self.assertEqual(self.store.reports(), [])
        self.assertEqual(self.store.search("fan repair", "Nanded"), [])
        with self.assertRaises(ValueError):
            self.store.owner_status(provider_id, "published")
        new_token = self.store.rotate_owner(provider_id)
        self.assertIsNone(self.store.owner(token))
        self.assertEqual(self.store.owner(new_token)["id"], provider_id)
        backup = self.store.backup(Path(self.temp.name) / "backup.sqlite3")
        self.assertEqual(DirectoryStore(backup).get_provider(provider_id)["status"], "hidden")
        self.store.delete_provider(provider_id)
        self.assertIsNone(self.store.owner(new_token))
        self.assertIsNone(self.store.get_provider(provider_id))

    def test_aggregate_metrics_do_not_store_people_or_queries(self):
        self.store.record_event("provider_started")
        self.store.record_event("provider_started")
        self.store.record_event("search_without_results")
        self.assertEqual(self.store.metrics()["provider_started"], 2)
        self.assertEqual(self.store.metrics()["search_without_results"], 1)
        with self.assertRaises(ValueError):
            self.store.record_event("arbitrary query text")


if __name__ == "__main__":
    unittest.main()
