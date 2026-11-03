"""Pub/sub en memoria para empujar mensajes del asesor al cliente (SSE) sin sondear la BD."""

import asyncio
import uuid
from collections import defaultdict
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
