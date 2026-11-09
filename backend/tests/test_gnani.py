import io
import unittest
import wave
from unittest.mock import patch

import httpx

from app.adapters import GnaniClient, ServiceError


class FakeClient:
    def __init__(self, response):
        self.response = response
        self.sent = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def post(self, url, **kwargs):
        self.sent = (url, kwargs)
        return self.response


def placeholder_wav():
    output = io.BytesIO()
    with wave.open(output, "wb") as sound:
        sound.setnchannels(1)
        sound.setsampwidth(2)
        sound.setframerate(24000)
        sound.writeframes(b"\x00\x00" * 24000)
    raw = bytearray(output.getvalue())
    raw[4:8] = b"\xff" * 4
    raw[40:44] = b"\xff" * 4
    return bytes(raw)


class GnaniTests(unittest.IsolatedAsyncioTestCase):
    async def test_selected_language_is_a_v3_hint(self):
        gnani = GnaniClient(key="test-only", stt_model="prisma-v3.0")
        response = httpx.Response(200, json={"transcript": "मुझे प्लंबर चाहिए", "detected_language_code": "hi-IN"})
        client = FakeClient(response)
        with patch("app.adapters.httpx.AsyncClient", return_value=client):
            transcript, detected, model = await gnani.transcribe(b"audio", "hi-IN")
        self.assertEqual(model, "prisma-v3.0")
        self.assertEqual(detected, "hi-IN")
        self.assertTrue(transcript)
        self.assertEqual(client.sent[1]["data"], {"model": "prisma-v3.0", "language_code": "hi-IN"})

    async def test_v25_needs_selected_language(self):
        gnani = GnaniClient(key="test-only", stt_model="prisma-v2.5")
        with self.assertRaises(ServiceError) as raised:
            await gnani.transcribe(b"audio", None)
        self.assertEqual(raised.exception.code, "language_selection_required")

    async def test_timbre_streaming_wav_header_is_repaired(self):
        gnani = GnaniClient(key="test-only", tts_model="timbre-v3.0")
        client = FakeClient(httpx.Response(200, content=placeholder_wav()))
        with patch("app.adapters.httpx.AsyncClient", return_value=client):
            audio = await gnani.synthesize("Hello", "en-IN")
        with wave.open(io.BytesIO(audio), "rb") as sound:
            self.assertEqual(sound.getnframes(), 24000)
            self.assertEqual(sound.getframerate(), 24000)


if __name__ == "__main__":
    unittest.main()
