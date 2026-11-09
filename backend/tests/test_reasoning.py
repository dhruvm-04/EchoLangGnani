import json
import unittest
from unittest.mock import patch

import httpx

from app.reasoning import MultilingualReasoner


class FakeClient:
    def __init__(self, response):
        self.response = response
        self.sent = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def post(self, url, headers, json):
        self.sent = (url, headers, json)
        return self.response


class ReasoningTests(unittest.IsolatedAsyncioTestCase):
    async def test_multilingual_parse_contract(self):
        reasoner = MultilingualReasoner()
        reasoner.base_url = "https://example.test/v1"
        reasoner.key = "test-only"
        reasoner.model = "multilingual-model"
        response = httpx.Response(200, json={"choices": [{"message": {"content": json.dumps({
            "english_request": "I need a plumber in Nanded",
            "service": "plumber", "location": "Nanded", "alternative": None, "answer": None,
        })}}]})
        client = FakeClient(response)
        with patch("app.reasoning.httpx.AsyncClient", return_value=client):
            result = await reasoner.interpret("मुझे नांदेड़ में प्लंबर चाहिए", "hi-IN", "new")
        self.assertEqual(result["service"], "plumber")
        self.assertEqual(result["location"], "Nanded")
        self.assertEqual(client.sent[0], "https://example.test/v1/chat/completions")
        self.assertEqual(client.sent[2]["response_format"], {"type": "json_object"})

    async def test_groq_gpt_oss_uses_strict_json_and_short_reasoning(self):
        reasoner = MultilingualReasoner()
        reasoner.base_url = "https://api.groq.com/openai/v1"
        reasoner.key = "test-only"
        reasoner.model = "openai/gpt-oss-120b"
        response = httpx.Response(200, json={"choices": [{"message": {"content": '{"text":"नल ठीक करने वाला चाहिए।"}'}}]})
        client = FakeClient(response)
        with patch("app.reasoning.httpx.AsyncClient", return_value=client):
            text = await reasoner.localize("I need a plumber.", "hi-IN")
        self.assertTrue(text)
        payload = client.sent[2]
        self.assertEqual(payload["response_format"]["type"], "json_schema")
        self.assertTrue(payload["response_format"]["json_schema"]["strict"])
        self.assertEqual(payload["reasoning_effort"], "low")
        self.assertFalse(payload["include_reasoning"])


if __name__ == "__main__":
    unittest.main()
