import tempfile
import unittest
from pathlib import Path

from app.demo_seed import CITIES, SERVICES, demo_listings, seed_demo
from app.directory import DirectoryStore


class DemoSeedTests(unittest.TestCase):
    def test_seed_has_small_searchable_demo_set_without_duplicates(self):
        listings = list(demo_listings())
        self.assertEqual(len(listings), 6)
        self.assertEqual(len({item["id"] for item in listings}), len(listings))
        self.assertEqual(len({item["phone"] for item in listings}), len(listings))
        self.assertTrue(all(item["name"].startswith("Demo — ") for item in listings))
        self.assertTrue(all(item["phone"].startswith("000") and len(item["phone"]) == 10 for item in listings))
        for city, _ in CITIES:
            self.assertTrue(any(item["name"].startswith(f"Demo — {city} ") for item in listings), city)
        for label, _, _ in SERVICES:
            self.assertTrue(any(item["id"].endswith(f"-{label.casefold().replace(' ', '-')}-1") for item in listings), label)

    def test_seed_is_repeatable_and_last_city_remains_searchable(self):
        with tempfile.TemporaryDirectory() as folder:
            store = DirectoryStore(Path(folder) / "directory.sqlite3")
            self.assertEqual(seed_demo(store), (6, 0))
            obsolete = dict(next(demo_listings()), id="demo-obsolete", phone="0000000999")
            self.assertEqual(store.seed_demo([*demo_listings(), obsolete]), (1, 0))
            self.assertEqual(seed_demo(store), (0, 1))
            self.assertEqual(seed_demo(store), (0, 0))
            self.assertEqual(len(store.search("fan repair", "Udaipur")), 1)
            self.assertEqual(len(store.search("plumber", "Nanded")), 1)
            self.assertTrue(store.search("electrician", "New Delhi"))
            self.assertTrue(store.search("pest control", CITIES[-1][0]))
            self.assertEqual(store.metrics().get("listings_published", 0), 0)


if __name__ == "__main__":
    unittest.main()
