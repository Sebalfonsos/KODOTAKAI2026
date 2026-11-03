"""Embeddings locales con Ollama (bge-m3, multilingüe, 1024 dimensiones) y caché LRU de consultas."""

import time
from collections import OrderedDict

import httpx

from app.config import get_settings
from app.core.errors import ApiError


class ClienteEmbeddings:
    def __init__(self, url: str, modelo: str, num_gpu: int, cache_max: int = 512):
        self._http = httpx.AsyncClient(base_url=url, timeout=httpx.Timeout(60.0, connect=3.0))
        self.modelo, self.num_gpu = modelo, num_gpu
        # ponytail: LRU en memoria por proceso; las consultas frecuentes ("¿dónde está mi guía?") no repiten embedding.
        self._cache: OrderedDict[str, list[float]] = OrderedDict()
        self._cache_max = cache_max

    async def cerrar(self) -> None:
        await self._http.aclose()

    async def embeber(self, textos: list[str]) -> list[list[float]]:
        try:
            r = await self._http.post(
                "/api/embed",
                json={"model": self.modelo, "input": textos, "keep_alive": "24h", "options": {"num_gpu": self.num_gpu}},
            )
            r.raise_for_status()
        except httpx.HTTPError as e:
            raise ApiError(503, "El servicio de embeddings no está disponible.", "EMBEDDINGS_NO_DISPONIBLE") from e
        return r.json()["embeddings"]

    async def embeber_consulta(self, texto: str) -> list[float]:
        clave = texto.strip().lower()
        if clave in self._cache:
            self._cache.move_to_end(clave)
            return self._cache[clave]
        vector = (await self.embeber([texto]))[0]
        self._cache[clave] = vector
        if len(self._cache) > self._cache_max:
            self._cache.popitem(last=False)
        return vector

    async def salud(self) -> tuple[bool, float]:
        inicio = time.perf_counter()
        try:
            r = await self._http.get("/api/tags", timeout=3.0)
            ok = r.status_code == 200 and any(m["name"].startswith(self.modelo) for m in r.json().get("models", []))
        except httpx.HTTPError:
            ok = False
        return ok, round((time.perf_counter() - inicio) * 1000, 1)


_cliente: ClienteEmbeddings | None = None


def get_embeddings() -> ClienteEmbeddings:
    global _cliente
    if _cliente is None:
        s = get_settings()
        _cliente = ClienteEmbeddings(s.ollama_url, s.embed_model, s.embed_num_gpu)
    return _cliente
