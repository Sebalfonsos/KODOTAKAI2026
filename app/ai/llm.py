"""Cliente del LLM local (LFM3 vía HAProxy, API compatible con OpenAI).

Medido el 2026-11-03: con razonamiento ~3,8 s por respuesta; sin razonamiento ~0,6 s. Por eso todas las
llamadas desactivan el razonamiento. LFM3 no emite `tool_calls`; la extracción estructurada usa `json_schema`.
"""

import json
import logging
import time
from collections.abc import AsyncIterator

import httpx

from app.config import get_settings
from app.core.errors import ApiError

log = logging.getLogger("app.llm")
SIN_RAZONAMIENTO = {"enable_thinking": False}


class ClienteLLM:
    def __init__(self, base_url: str, api_key: str | None, timeout_s: float):
        cabeceras = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        # Conexión persistente (keep-alive) para no pagar handshake en cada turno.
        self._http = httpx.AsyncClient(
            base_url=base_url,
            headers=cabeceras,
            timeout=httpx.Timeout(timeout_s, connect=3.0),
            limits=httpx.Limits(max_keepalive_connections=16, max_connections=32),
        )

    async def cerrar(self) -> None:
        await self._http.aclose()

    def _cuerpo(self, mensajes: list[dict], max_tokens: int, **extra) -> dict:
        return {
            "model": "lfm3",
            "messages": mensajes,
            "max_tokens": max_tokens,
            "temperature": 0.1,
            "chat_template_kwargs": SIN_RAZONAMIENTO,
            "cache_prompt": True,
            **extra,
        }

    async def _post(self, cuerpo: dict) -> dict:
        try:
            r = await self._http.post("/chat/completions", json=cuerpo)
        except httpx.TimeoutException as e:
            raise ApiError(504, "El modelo de IA tardó demasiado en responder.", "LLM_TIMEOUT") from e
        except httpx.HTTPError as e:
            raise ApiError(
                503, "El modelo de IA no está disponible.", "LLM_NO_DISPONIBLE", {"Retry-After": "10"}
            ) from e
        if r.status_code >= 500:
            raise ApiError(503, "El modelo de IA no está disponible.", "LLM_NO_DISPONIBLE", {"Retry-After": "10"})
        r.raise_for_status()
        return r.json()

    async def extraer_json(self, mensajes: list[dict], schema: dict, max_tokens: int = 160) -> dict:
        """Salida forzada por gramática a `schema`. Devuelve el objeto JSON."""
        cuerpo = self._cuerpo(
            mensajes, max_tokens, response_format={"type": "json_schema", "json_schema": {"schema": schema}}
        )
        datos = await self._post(cuerpo)
        contenido = datos["choices"][0]["message"].get("content") or "{}"
        try:
            return json.loads(contenido)
        except json.JSONDecodeError:
            log.warning("llm_json_invalido")
            return {}

    async def completar(self, mensajes: list[dict], max_tokens: int | None = None) -> str:
        datos = await self._post(self._cuerpo(mensajes, max_tokens or get_settings().llm_max_tokens))
        return (datos["choices"][0]["message"].get("content") or "").strip()

    async def stream(self, mensajes: list[dict], max_tokens: int | None = None) -> AsyncIterator[str]:
        """Genera fragmentos de texto (SSE del servidor llama.cpp)."""
        cuerpo = self._cuerpo(mensajes, max_tokens or get_settings().llm_max_tokens, stream=True)
        try:
            async with self._http.stream("POST", "/chat/completions", json=cuerpo) as r:
                if r.status_code >= 400:
                    raise ApiError(
                        503, "El modelo de IA no está disponible.", "LLM_NO_DISPONIBLE", {"Retry-After": "10"}
                    )
                async for linea in r.aiter_lines():
                    if not linea.startswith("data: ") or linea == "data: [DONE]":
                        continue
                    delta = json.loads(linea[6:])["choices"][0].get("delta", {}).get("content")
                    if delta:
                        yield delta
        except httpx.TimeoutException as e:
            raise ApiError(504, "El modelo de IA tardó demasiado en responder.", "LLM_TIMEOUT") from e
        except httpx.HTTPError as e:
            raise ApiError(
                503, "El modelo de IA no está disponible.", "LLM_NO_DISPONIBLE", {"Retry-After": "10"}
            ) from e

    async def salud(self) -> tuple[bool, float]:
        inicio = time.perf_counter()
        try:
            r = await self._http.get(self._http.base_url.join("/health"), timeout=3.0)
            ok = r.status_code == 200
        except httpx.HTTPError:
            ok = False
        return ok, round((time.perf_counter() - inicio) * 1000, 1)


_cliente: ClienteLLM | None = None


def get_llm() -> ClienteLLM:
    global _cliente
    if _cliente is None:
        s = get_settings()
        _cliente = ClienteLLM(s.llm_base_url, s.llm_api_key(), s.llm_timeout_s)
    return _cliente
