import unittest

from app.core import LANGUAGES, State, clean_location, decide, location_from_request


class CoreTests(unittest.TestCase):
    def test_ten_supported_languages(self):
        self.assertEqual(set(LANGUAGES), {"bn-IN", "en-IN", "gu-IN", "hi-IN", "kn-IN", "ml-IN", "mr-IN", "pa-IN", "ta-IN", "te-IN"})

    def test_location_extraction_requires_a_real_place(self):
        self.assertEqual(location_from_request("I need a plumber in Mysuru to fix a tap"), "Mysuru")
        self.assertIsNone(clean_location("near me"))

    def test_spoken_place_is_confirmed_before_search(self):
        state, prompt = decide(State(), "I need a plumber in Nanded", "hi-IN", "plumber", None, "Nanded")
        self.assertEqual(state.location, "Nanded")
        self.assertEqual(state.phase, "awaiting_confirmation")
        self.assertIn("Nanded", prompt)
        state, reply = decide(state, "yes", "hi-IN", None, None)
        self.assertEqual(state.phase, "done")
        self.assertIn("Nanded", reply)

    def test_open_service_category(self):
        state, _ = decide(State(), "I need a pump repair person", "en-IN", "water pump repair", None, "Akola")
        self.assertEqual(state.category, "water pump repair")

    def test_missing_place_is_asked_by_voice(self):
        state, prompt = decide(State(), "I need a plumber", "hi-IN", "plumber", None)
        self.assertEqual(state.phase, "awaiting_location")
        self.assertIn("city", prompt)
        state, prompt = decide(state, "I am in Salem", "hi-IN", None, None)
        self.assertEqual(state.phase, "awaiting_confirmation")
        self.assertIn("Salem", prompt)
        state, _ = decide(state, "yes", "hi-IN", None, None)
        self.assertEqual(state.phase, "done")

    def test_rejection_resets_service(self):
        state = State("awaiting_confirmation", "plumber", "Mysuru", "hi-IN")
        state, _ = decide(state, "no", "hi-IN", None, None)
        self.assertEqual(state.phase, "new")
        self.assertIsNone(state.category)

    def test_unclear_intent_asks_for_detail(self):
        state, prompt = decide(State(), "help me", "en-IN", None, "plumber or electrician")
        self.assertEqual(state.phase, "new")
        self.assertIn("describe", prompt)


if __name__ == "__main__":
    unittest.main()
