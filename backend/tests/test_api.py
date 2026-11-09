import io
import json
import os
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.directory import DirectoryStore


class FakeGnani:
    stt_model = "prisma-v3.0"
    tts_model = "timbre-v2.5"
    key = "test-only"

    async def transcribe(self, audio, language):
        return "I need a plumber in Nanded", language or "en-IN", "prisma-v3.0"

    async def synthesize(self, text, language):
        return b"RIFFtest"


class FakeReasoner:
    model = "test-reasoner"
    configured = True

    async def interpret(self, transcript, language, phase):
        return {
            "english_request": transcript,
            "service": "plumber" if "plumber" in transcript else None,
            "location": "Nanded" if "Nanded" in transcript else None,
            "alternative": None,
            "answer": "yes" if transcript.lower() == "yes" else None,
            "availability": "weekend" if "weekend" in transcript.lower() else None,
            "preferred_language": "Hindi" if "hindi" in transcript.lower() else None,
        }

    async def navigate_results(self, transcript, language):
        return "previous" if "back" in transcript else "next" if "next" in transcript else "repeat"

    async def localize(self, english, language):
        self.last_localize_language = language
        return english

    async def provider_answer(self, field, transcript):
        return {"value": transcript, "skip": transcript.lower() == "skip"}

    async def provider_command(self, transcript):
        return {"action": "publish" if transcript.lower() == "publish" else "unclear", "field": "", "value": ""}

    async def provider_edit(self, transcript):
        return {"field": "hours", "value": "Weekdays 9 to 5"}


def audio_file():
    stream = io.BytesIO()
    with wave.open(stream, "wb") as sound:
        sound.setnchannels(1)
        sound.setsampwidth(2)
        sound.setframerate(16000)
        sound.writeframes(b"\x00\x00" * 16000)
    return stream.getvalue()


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {"ECHOLANG_REQUIRE_APPROVAL": "0"})
        self.environment.start()
        self.gnani = app.state.gnani
        self.reasoner = app.state.reasoner
        self.store = app.state.store
        self.temp = tempfile.TemporaryDirectory()
        app.state.gnani = FakeGnani()
        app.state.reasoner = FakeReasoner()
        app.state.store = DirectoryStore(Path(self.temp.name) / "test.sqlite3")
        self.client = TestClient(app)

    def tearDown(self):
        app.state.gnani = self.gnani
        app.state.reasoner = self.reasoner
        app.state.store = self.store
        self.client.close()
        self.temp.cleanup()
        self.environment.stop()

    def test_speech_confirmation_searches_local_directory(self):
        response = self.client.post("/api/turn", files={"audio": ("request.wav", audio_file(), "audio/wav")}, data={"state": "{}"})
        self.assertEqual(response.status_code, 200, response.text)
        first = response.json()
        self.assertEqual(first["state"]["phase"], "awaiting_confirmation")
        self.assertEqual(first["detectedLanguage"], "en-IN")
        response = self.client.post("/api/turn", data={"control": "yes", "state": json.dumps(first["state"])})
        self.assertEqual(response.status_code, 200, response.text)
        second = response.json()
        self.assertEqual(second["state"]["phase"], "done")
        self.assertEqual(second["matches"], [])
        self.assertIn("prisma-v3.0", first["modelsUsed"])
        self.assertNotIn("prisma-v3.0", second["modelsUsed"])

    def test_no_location_asks_by_voice(self):
        response = self.client.post("/api/turn", data={"text": "I need a plumber", "state": "{}"})
        self.assertEqual(response.json()["state"]["phase"], "awaiting_location")

    def test_provider_opening_uses_prompt_language_then_detected_speech_language(self):
        class HindiGnani(FakeGnani):
            async def transcribe(self, audio, language):
                return "Asha Repairs", "hi-IN", "prisma-v3.0"

        app.state.gnani = HindiGnani()
        started = self.client.post("/api/providers/start", json={"language": "auto", "prompt_language": "hi-IN"})
        self.assertEqual(started.status_code, 200, started.text)
        self.assertEqual(app.state.reasoner.last_localize_language, "hi-IN")
        draft_id = started.json()["draftId"]
        response = self.client.post("/api/providers/turn", files={"audio": ("answer.wav", audio_file(), "audio/wav")}, data={"draft_id": draft_id})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(app.state.reasoner.last_localize_language, "hi-IN")
        self.assertEqual(app.state.store.get_draft(draft_id)["language"], "hi-IN")

    def test_provider_can_change_draft_language(self):
        draft_id = self.client.post("/api/providers/start", json={"language": "en-IN"}).json()["draftId"]
        resumed = self.client.get(f"/api/providers/drafts/{draft_id}", params={"selected_language": "ta-IN"})
        self.assertEqual(resumed.status_code, 200, resumed.text)
        self.assertEqual(app.state.reasoner.last_localize_language, "ta-IN")
        self.assertEqual(app.state.store.get_draft(draft_id)["language"], "ta-IN")
        answer = self.client.post("/api/providers/turn", data={"draft_id": draft_id, "selected_language": "hi-IN", "text": "Asha"})
        self.assertEqual(answer.status_code, 200, answer.text)
        self.assertEqual(app.state.reasoner.last_localize_language, "hi-IN")
        self.assertEqual(app.state.store.get_draft(draft_id)["language"], "hi-IN")

    def test_bad_audio_gets_clear_error(self):
        response = self.client.post("/api/turn", files={"audio": ("bad.wav", b"not wave", "audio/wav")})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "invalid_audio")

    def test_native_typed_request_needs_language(self):
        response = self.client.post("/api/turn", data={"text": "मुझे प्लंबर चाहिए", "state": "{}"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "language_selection_required")

    def test_provider_can_publish_search_and_edit_local_listing(self):
        started = self.client.post("/api/providers/start", json={"language": "en-IN"})
        self.assertEqual(started.status_code, 200, started.text)
        draft_id = started.json()["draftId"]
        answers = ("Asha Repairs", "fan repair, mixer repair", "Nanded", "home visits", "9876543210", "weekdays", "Hindi, English", "quotes each job")
        for answer in answers:
            response = self.client.post("/api/providers/turn", data={"draft_id": draft_id, "text": answer})
            self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["phase"], "review")
        self.assertEqual(self.client.get(f"/api/providers/drafts/{draft_id}").json()["phase"], "review")
        self.assertEqual(self.client.get("/api/directory/search", params={"service": "fan repair", "area": "Nanded"}).json()["matches"], [])
        published = self.client.post("/api/providers/turn", data={"draft_id": draft_id, "control": "publish"})
        self.assertEqual(published.status_code, 200, published.text)
        token = published.json()["ownerToken"]
        provider = published.json()["provider"]
        self.assertEqual(provider["status"], "published")
        matches = self.client.get("/api/directory/search", params={"service": "fan repair", "area": "Nanded"}).json()["matches"]
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["name"], "Asha Repairs")
        self.assertEqual(self.client.get("/api/directory/search", params={"service": "fridge repair", "area": "Nanded"}).json()["matches"], [])
        headers = {"Authorization": f"Bearer {token}"}
        self.assertEqual(self.client.get("/api/providers/me", headers=headers).json()["id"], provider["id"])
        edited = self.client.post("/api/providers/edit/confirm", json={"field": "hours", "value": "Weekdays 9 to 5"}, headers=headers)
        self.assertEqual(edited.status_code, 200, edited.text)
        self.assertEqual(edited.json()["provider"]["hours"], "Weekdays 9 to 5")
        prepared = self.client.post("/api/providers/edit/prepare", data={"text": "Change hours to weekdays 9 to 5"}, headers=headers)
        self.assertEqual(prepared.json()["field"], "hours")
        spoken_confirm = self.client.post("/api/providers/edit/answer", data={"field": "hours", "value": "Weekdays 9 to 5", "text": "yes"}, headers=headers)
        self.assertTrue(spoken_confirm.json()["saved"])
        denied = self.client.post("/api/providers/edit/confirm", json={"field": "hours", "value": "never"})
        self.assertEqual(denied.status_code, 401)

    def test_operator_approval_controls_public_search(self):
        with patch.dict(os.environ, {"ECHOLANG_ADMIN_KEY": "test-secret", "ECHOLANG_REQUIRE_APPROVAL": "1"}):
            draft_id = self.client.post("/api/providers/start", json={"language": "en-IN"}).json()["draftId"]
            for answer in ("Ravi", "plumber", "Nanded", "home visits", "9876543210", "skip", "skip", "skip"):
                self.client.post("/api/providers/turn", data={"draft_id": draft_id, "text": answer})
            published = self.client.post("/api/providers/turn", data={"draft_id": draft_id, "control": "publish"}).json()
            self.assertEqual(published["provider"]["status"], "pending")
            self.assertEqual(self.client.get("/api/directory/search", params={"service": "plumber", "area": "Nanded"}).json()["matches"], [])
            headers = {"X-Admin-Key": "test-secret"}
            self.assertEqual(len(self.client.get("/api/admin/pending", headers=headers).json()["providers"]), 1)
            self.assertEqual(self.client.get("/api/admin/pending").status_code, 403)
            approved = self.client.post(f"/api/admin/providers/{published['provider']['id']}/status", json={"status": "published"}, headers=headers)
            self.assertEqual(approved.status_code, 200)
            self.assertEqual(len(self.client.get("/api/directory/search", params={"service": "plumber", "area": "Nanded"}).json()["matches"]), 1)

    def test_result_navigation_and_spoken_filters(self):
        for name, phone, hours, languages in (("Asha", "9876543210", "weekends 9am to 5pm", "Hindi, English"),
                                              ("Ravi", "9876543211", "weekends 10am to 6pm", "Hindi"),
                                              ("Dev", "9876543212", "weekdays 9am to 5pm", "English")):
            draft = app.state.store.new_draft("en-IN")
            draft["fields"] = {"name": name, "services": "pipe repair", "area": "Nanded", "delivery": "home visits",
                               "phone": phone, "hours": hours, "languages": languages, "price": "quote"}
            app.state.store.publish(draft)
        first = self.client.post("/api/turn", data={"text": "I need a plumber in Nanded this weekend who speaks Hindi", "state": "{}"}).json()
        self.assertEqual(first["state"]["availability"], "weekend")
        self.assertEqual(first["state"]["preferred_language"], "Hindi")
        result = self.client.post("/api/turn", data={"control": "yes", "state": json.dumps(first["state"])}).json()
        self.assertEqual([item["name"] for item in result["matches"]], ["Asha", "Ravi"])
        self.assertIn("Asha", result["replyText"])
        self.assertEqual(result["activeIndex"], 0)
        next_result = self.client.post("/api/turn", data={"control": "next", "state": json.dumps(result["state"])}).json()
        self.assertEqual(next_result["activeIndex"], 1)
        self.assertIn("Ravi", next_result["replyText"])
        previous = self.client.post("/api/turn", data={"text": "go back", "state": json.dumps(next_result["state"])}).json()
        self.assertEqual(previous["activeIndex"], 0)
        self.assertIn("Asha", previous["replyText"])
        new_search = self.client.post("/api/turn", data={"control": "new_search", "state": json.dumps(previous["state"])}).json()
        self.assertEqual(new_search["state"]["phase"], "new")

    def test_owner_and_operator_lifecycle(self):
        provider, token = app.state.store.publish({"id": app.state.store.new_draft("en-IN")["id"], "fields": {
            "name": "Asha", "services": "fan repair", "area": "Nanded", "delivery": "home visits",
            "phone": "9876543210", "hours": "", "languages": "Hindi", "price": ""}})
        owner = {"Authorization": f"Bearer {token}"}
        provider_id = provider["id"]
        self.assertEqual(self.client.post("/api/providers/me/status", json={"status": "paused"}).status_code, 401)
        paused = self.client.post("/api/providers/me/status", json={"status": "paused"}, headers=owner)
        self.assertEqual(paused.json()["status"], "paused")
        self.assertEqual(self.client.get("/api/directory/search", params={"service": "fan repair", "area": "Nanded"}).json()["matches"], [])
        self.client.post("/api/providers/me/status", json={"status": "published"}, headers=owner)
        self.client.post(f"/api/directory/{provider_id}/report", json={"reason": "Wrong number"})
        with patch.dict(os.environ, {"ECHOLANG_ADMIN_KEY": "test-secret"}):
            admin = {"X-Admin-Key": "test-secret"}
            self.assertEqual(len(self.client.get("/api/admin/providers/by-phone", params={"phone": "9876543210"}, headers=admin).json()["providers"]), 1)
            report = self.client.get("/api/admin/reports", headers=admin).json()["reports"][0]
            self.assertEqual(self.client.post(f"/api/admin/reports/{report['id']}/resolve", json={"resolution": "hidden"}).status_code, 403)
            self.client.post(f"/api/admin/reports/{report['id']}/resolve", json={"resolution": "hidden"}, headers=admin)
            self.assertEqual(self.client.post("/api/providers/me/status", json={"status": "published"}, headers=owner).status_code, 400)
            recovered = self.client.post(f"/api/admin/providers/{provider_id}/recover", headers=admin).json()["ownerToken"]
        self.assertEqual(self.client.get("/api/providers/me", headers=owner).status_code, 401)
        new_owner = {"Authorization": f"Bearer {recovered}"}
        self.assertEqual(self.client.post("/api/providers/me/delete", json={"confirmation": "wrong"}, headers=new_owner).status_code, 400)
        self.assertEqual(self.client.post("/api/providers/me/delete", json={"confirmation": "delete"}, headers=new_owner).status_code, 200)
        self.assertEqual(self.client.get("/api/providers/me", headers=new_owner).status_code, 401)


if __name__ == "__main__":
    unittest.main()
