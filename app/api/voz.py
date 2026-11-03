"""Canal de voz: STT (CrispASR en A) y TTS (LFM3-Audio en B) como proxy del clúster.

El texto transcrito entra al mismo orquestador de chat (RF-VOZ): aquí no hay lógica de negocio.
"""

import re
from typing import Annotated, Literal

import httpx
from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.config import get_settings
from app.core.errors import ApiError, respuestas
from app.core.ratelimit import limite

router = APIRouter(prefix="/voz", tags=["Voz"])
_transporte: httpx.AsyncBaseTransport | None = None  # solo para pruebas (httpx.MockTransport)


class Transcripcion(BaseModel):
    texto: str = Field(examples=["Quiero rastrear la guía TLX-984021-CO"])


class Sintesis(BaseModel):
    texto: str = Field(min_length=1, max_length=1000, examples=["Su envío llega mañana a Barranquilla."])
    voz: Literal["female", "male"] = "female"


async def _llamar(base: str, ruta: str, **kw) -> httpx.Response:
    s = get_settings()
    try:
        async with httpx.AsyncClient(base_url=base, timeout=s.voz_timeout_s, transport=_transporte) as c:
            r = await c.post(ruta, **kw)
    except httpx.TimeoutException as e:
        raise ApiError(504, "El servicio de voz no respondió a tiempo.", "VOZ_TIMEOUT") from e
    except httpx.HTTPError as e:
        raise ApiError(503, "El servicio de voz no está disponible.", "VOZ_NO_DISPONIBLE") from e
    if r.status_code != 200:
        raise ApiError(503, f"El servicio de voz respondió {r.status_code}.", "VOZ_NO_DISPONIBLE")
    return r


@router.post(
    "/transcribir",
    response_model=Transcripcion,
    summary="Voz a texto (español)",
    responses=respuestas(413, 422, 429, 503, 504),
    dependencies=[Depends(limite("voz", 30, 60))],
)
async def transcribir(
    audio: Annotated[UploadFile, File(description="wav, mp3, ogg o webm/opus (MediaRecorder)")],
):
    """Transcribe el audio con Cohere Transcribe. Envía solo segmentos con voz: con silencio o ruido el modelo
    puede inventar frases. El texto se manda luego a `POST /chat/sesiones/{id}/mensajes` como cualquier mensaje."""
    s = get_settings()
    datos = await audio.read(s.max_upload_bytes + 1)
    if len(datos) > s.max_upload_bytes:
        raise ApiError(413, f"El audio supera {s.max_upload_bytes // (1024 * 1024)} MB.", "ARCHIVO_GRANDE")
    if not datos:
        raise ApiError(422, "El audio está vacío.", "AUDIO_VACIO")
    nombre = audio.filename or "audio.webm"
    r = await _llamar(s.stt_url, "/v1/audio/transcriptions", files={"file": (nombre, datos)}, data={"language": "es"})
    return Transcripcion(texto=r.json().get("text", "").strip())


@router.post(
    "/sintetizar",
    summary="Texto a voz (WAV 24 kHz)",
    response_class=Response,
    responses={200: {"content": {"audio/wav": {}}, "description": "WAV mono 24 kHz"}, **respuestas(422, 429, 503, 504)},
    dependencies=[Depends(limite("voz", 30, 60))],
)
async def sintetizar(cuerpo: Sintesis):
    """Lee el texto en voz alta con LFM3-Audio (equipo B). Quita el Markdown antes de sintetizar.
    B genera una frase a la vez: pide las frases en orden, no en paralelo."""
    texto = re.sub(r"[*#_`>|]", "", cuerpo.texto).strip()
    if not texto:
        raise ApiError(422, "No hay texto para leer.", "TEXTO_VACIO")
    r = await _llamar(get_settings().tts_url, "/tts", json={"input": texto, "lang": "es", "voice": cuerpo.voz})
    return Response(r.content, media_type="audio/wav")
