"""Rastreo de guías (ruta literal del dosier: GET /api/v1/tracking/{guia})."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError, respuestas
from app.core.ratelimit import limite
from app.core.security import ActorOpcional
from app.db import get_session
from app.domain.sanitizar import extraer_guias
from app.schemas.tracking import TrackingOut
from app.servicios.envios import tracking

router = APIRouter(tags=["Rastreo"])


@router.get(
    "/tracking/{guia}",
    response_model=TrackingOut,
    summary="Estado y línea de tiempo de una guía",
    responses=respuestas(401, 404, 422, 429),
    dependencies=[Depends(limite("tracking", 60, 60))],
)
async def rastrear(
    guia: Annotated[str, Path(min_length=10, max_length=20, examples=["TLX-984021-CO"])],
    actor: ActorOpcional,
    s: AsyncSession = Depends(get_session),
):
    """Público (invitado): estado, eventos (con datos personales enmascarados), ubicación y ETA.
    El titular de la cuenta, asesores y administradores reciben además `detalle`."""
    canonicas = extraer_guias(guia)
    if not canonicas:
        raise ApiError(422, "Formato de guía inválido. Usa TLX-XXXXXX-CO (6 dígitos).", "GUIA_FORMATO_INVALIDO")
    return await tracking(s, canonicas[0], actor)
