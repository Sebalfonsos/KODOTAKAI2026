"""Soporte de la cabecera `Idempotency-Key` en POST que crean recursos."""

import hashlib
import json

from fastapi.encoders import jsonable_encoder
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.models import Idempotencia


def _hash(cuerpo) -> str:
    return hashlib.sha256(json.dumps(jsonable_encoder(cuerpo), sort_keys=True).encode()).hexdigest()


async def buscar(s: AsyncSession, clave: str | None, endpoint: str, sujeto: str, cuerpo) -> dict | None:
    """Devuelve la respuesta guardada si la clave ya se usó con el mismo cuerpo; 409 si el cuerpo cambió."""
    if not clave:
        return None
    if not 8 <= len(clave) <= 80:
        raise ApiError(400, "Idempotency-Key debe tener entre 8 y 80 caracteres.", "IDEMPOTENCY_KEY_INVALIDA")
    previo = await s.get(Idempotencia, (clave, endpoint))
    if previo is None:
        return None
    if previo.sujeto != sujeto or previo.hash_cuerpo != _hash(cuerpo):
        raise ApiError(409, "Esta Idempotency-Key ya se usó con otra solicitud.", "IDEMPOTENCY_KEY_REUTILIZADA")
    return previo.respuesta


def guardar(s: AsyncSession, clave: str | None, endpoint: str, sujeto: str, cuerpo, status: int, respuesta) -> None:
    if clave:
        s.add(
            Idempotencia(
                clave=clave,
                endpoint=endpoint,
                sujeto=sujeto,
                hash_cuerpo=_hash(cuerpo),
                status=status,
                respuesta=jsonable_encoder(respuesta),
            )
        )
