"""Pub/sub en memoria para empujar mensajes del asesor al cliente (SSE) sin sondear la BD."""

import asyncio
import json
import uuid
from collections import defaultdict
from collections.abc import AsyncIterator
from contextlib import contextmanager

# ponytail: un solo proceso; con varias réplicas usar LISTEN/NOTIFY de PostgreSQL o Redis.
_suscriptores: dict[uuid.UUID, set[asyncio.Queue]] = defaultdict(set)


def publicar(sesion_id: uuid.UUID, evento) -> None:
    for cola in list(_suscriptores.get(sesion_id, ())):
        if cola.qsize() < 100:
            cola.put_nowait(evento)


@contextmanager
def suscribir(sesion_id: uuid.UUID):
    cola: asyncio.Queue = asyncio.Queue()
    _suscriptores[sesion_id].add(cola)
    try:
        yield cola
    finally:
        _suscriptores[sesion_id].discard(cola)
        if not _suscriptores[sesion_id]:
            _suscriptores.pop(sesion_id, None)


async def stream_sse(sesion_id: uuid.UUID, ocultar: frozenset[str] = frozenset()) -> AsyncIterator[str]:
    """Cuerpo SSE de los eventos de una sesión, con `: ping` cada 15 s para detectar conexiones muertas."""
    with suscribir(sesion_id) as cola:
        yield ": conectado\n\n"
        while True:
            try:
                nombre, datos = await asyncio.wait_for(cola.get(), timeout=15)
            except TimeoutError:
                yield ": ping\n\n"
                continue
            if nombre not in ocultar:
                yield f"event: {nombre}\ndata: {json.dumps(datos, ensure_ascii=False, default=str)}\n\n"
