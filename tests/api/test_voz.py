"""Proxy de voz con el clúster simulado (httpx.MockTransport): sin STT ni TTS reales."""

import json

import httpx
import pytest

from app.api import voz
from tests.api.conftest import problema

WAV = b"RIFF\x00\x00\x00\x00WAVEfmt "


@pytest.fixture
def cluster(monkeypatch):
    vistos = []

    def responder(req: httpx.Request) -> httpx.Response:
        vistos.append(req)
        if req.url.path == "/v1/audio/transcriptions":
            assert b'name="language"\r\n\r\nes' in req.content
            return httpx.Response(200, json={"text": " Quiero rastrear mi guía. "})
        if req.url.path == "/tts":
            return httpx.Response(200, content=WAV, headers={"content-type": "audio/wav"})
        return httpx.Response(404)

    monkeypatch.setattr(voz, "_transporte", httpx.MockTransport(responder))
    return vistos


async def test_transcribir(cliente, cluster):
    r = await cliente.post("/api/v1/voz/transcribir", files={"audio": ("a.webm", b"\x1aE\xdf\xa3", "audio/webm")})
    assert r.status_code == 200 and r.json() == {"texto": "Quiero rastrear mi guía."}
    assert str(cluster[0].url).startswith("http://127.0.0.1:8082/")


async def test_sintetizar_quita_markdown_y_fija_espanol(cliente, cluster):
    r = await cliente.post("/api/v1/voz/sintetizar", json={"texto": "Su envío **llega mañana**.", "voz": "male"})
    assert r.status_code == 200 and r.headers["content-type"] == "audio/wav" and r.content == WAV
    assert json.loads(cluster[0].content) == {"input": "Su envío llega mañana.", "lang": "es", "voice": "male"}


async def test_validaciones(cliente, cluster):
    problema(await cliente.post("/api/v1/voz/sintetizar", json={"texto": "hola", "voz": "xyz"}), 422, "VALIDACION")
    problema(await cliente.post("/api/v1/voz/sintetizar", json={"texto": "**"}), 422, "TEXTO_VACIO")
    problema(await cliente.post("/api/v1/voz/transcribir", files={"audio": ("a.wav", b"")}), 422, "AUDIO_VACIO")
    assert cluster == []


async def test_cluster_caido(cliente, monkeypatch):
    def caido(req):
        raise httpx.ConnectError("sin ruta")

    monkeypatch.setattr(voz, "_transporte", httpx.MockTransport(caido))
    problema(await cliente.post("/api/v1/voz/sintetizar", json={"texto": "hola"}), 503, "VOZ_NO_DISPONIBLE")
