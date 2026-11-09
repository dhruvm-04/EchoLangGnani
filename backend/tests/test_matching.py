import unittest
from datetime import datetime

from app.matching import INDIA_TIME, area_matches, availability_matches, language_matches, service_score


class MatchingTests(unittest.TestCase):
    def test_service_synonyms_and_unrelated_repairs(self):
        self.assertGreater(service_score("ceiling fan repair", "fan mechanic"), 0)
        self.assertGreater(service_score("tuition", "home tutor"), 0)
        self.assertGreater(service_score("electrical work", "electrician"), 0)
        self.assertEqual(service_score("fridge repair", "fan repair"), 0)

    def test_area_names_and_city_aliases(self):
        self.assertTrue(area_matches("Indiranagar, Bangalore", "Indiranagar, Bengaluru"))
        self.assertTrue(area_matches("Bangalore", "Bengaluru"))
        self.assertFalse(area_matches("New Delhi", "New Town, Delhi"))
        self.assertFalse(area_matches("Jayanagar", "Indiranagar, Bengaluru"))

    def test_hours_and_language_filters_require_explicit_support(self):
        sunday = datetime(2026, 11, 8, 11, 0, tzinfo=INDIA_TIME)
        monday = datetime(2026, 11, 9, 11, 0, tzinfo=INDIA_TIME)
        self.assertFalse(availability_matches("today", "Weekdays 9am to 5pm", sunday))
        self.assertTrue(availability_matches("tomorrow", "Weekdays 9am to 5pm", sunday))
        self.assertTrue(availability_matches("now", "Weekdays 9am to 5pm", monday))
        self.assertTrue(availability_matches("now", "Mon-Sat 10:00-18:00", monday))
        self.assertFalse(availability_matches("sunday", "Mon-Sat 10:00-18:00", monday))
        self.assertFalse(availability_matches("today, evening", "Daily 9am to 5pm", monday))
        self.assertFalse(availability_matches("now", "Weekdays 9 to 5", monday))
        self.assertTrue(language_matches("Hindi", "Hindi, English"))
        self.assertFalse(language_matches("Tamil", "Hindi, English"))
        self.assertFalse(language_matches("Hindi", ""))


if __name__ == "__main__":
    unittest.main()
