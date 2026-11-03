"""Rate limit de ventana deslizante en memoria, como dependencia de FastAPI."""

import time
from collections import defaultdict, deque

from fastapi import Depends, Request

from app.core.errors import ApiError
from app.core.security import Actor, actor_opcional

# ponytail: estado en memoria de un solo proceso; con varios workers/réplicas, mover a Redis.
_ventanas: dict[str, deque[float]] = defaultdict(deque)


def limite(nombre: str, maximo: int, segundos: int):
    """Permite `maximo` peticiones por `segundos` por usuario (o IP si es invitado) para el grupo `nombre`."""

    async def _dep(request: Request, actor: Actor = Depends(actor_opcional)) -> None:
        clave = f"{nombre}:{actor.sujeto}"
        ahora = time.monotonic()
        cola = _ventanas[clave]
        while cola and ahora - cola[0] > segundos:
            cola.popleft()
        if len(cola) >= maximo:
            espera = int(segundos - (ahora - cola[0])) + 1
            raise ApiError(
                429,
                f"Has superado el límite de {maximo} solicitudes en {segundos} s.",
                "LIMITE_EXCEDIDO",
                {"Retry-After": str(espera)},
            )
        cola.append(ahora)

    return _dep


def reiniciar() -> None:
    """Solo para pruebas."""
    _ventanas.clear()
