"""Cotización de fletes (ruta literal del dosier: POST /api/v1/cotizar)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError, respuestas
from app.core.ratelimit import limite
from app.core.security import ActorOpcional
from app.db import get_session
from app.models import Cotizacion
from app.models.base import Rol
from app.schemas.cotizacion import CotizacionIn, CotizacionOut, DesgloseOut
from app.servicios import idempotencia
from app.servicios.cotizaciones import cotizar_y_guardar

router = APIRouter(tags=["Cotización"])


@router.post(
    "/cotizar",
    status_code=status.HTTP_201_CREATED,
    response_model=CotizacionOut,
    summary="Cotizar un envío",
    responses=respuestas(404, 409, 422, 429),
    dependencies=[Depends(limite("cotizar", 30, 60))],
)
async def crear_cotizacion(
    datos: CotizacionIn,
    actor: ActorOpcional,
    s: AsyncSession = Depends(get_session),
    idempotency_key: Annotated[str | None, Header(description="Opcional: reintentos seguros")] = None,
):
    """Cálculo determinista: peso volumétrico = alto×ancho×largo/4000; se cobra el mayor entre real y volumétrico;
    seguro = máx(1 % del valor declarado, mínimo de la ruta); flete mínimo y recargos de la matriz (D-01..D-03).
    Valida cobertura, peso máximo del destino, refrigeración disponible, 50 kg en paquetería y prohibidos."""
    if previo := await idempotencia.buscar(s, idempotency_key, "cotizar", actor.sujeto, datos):
        return JSONResponse(previo, status_code=201)
    out = await cotizar_y_guardar(s, datos, actor)
    idempotencia.guardar(s, idempotency_key, "cotizar", actor.sujeto, datos, 201, out)
    await s.commit()
    return out


@router.get(
    "/cotizaciones/{cotizacion_id}",
    response_model=CotizacionOut,
    summary="Consultar una cotización",
    responses=respuestas(404, 422),
)
async def obtener_cotizacion(cotizacion_id: uuid.UUID, actor: ActorOpcional, s: AsyncSession = Depends(get_session)):
    """Visible para quien la creó (usuario autenticado) o para asesores/administradores.
    Las cotizaciones de invitados se consultan solo por quien conoce su id (UUID aleatorio)."""
    c = await s.get(Cotizacion, cotizacion_id)
    propia = c is not None and (
        c.usuario_id is None or c.usuario_id == actor.id or actor.rol in (Rol.ADMIN, Rol.ASESOR)
    )
    if not propia:
        raise ApiError(404, "No encontramos esa cotización.", "COTIZACION_NO_ENCONTRADA")
    t = c.entrada
    return CotizacionOut(
        id=c.id,
        codigo_trayecto=c.trayecto_codigo,
        origen=t["origen"],
        destino=t["destino"],
        desglose=DesgloseOut(**c.desglose),
        total=c.total,
        tiempo_estimado_horas=c.desglose.get("tiempo_estimado_horas", 0),
        observaciones=c.desglose.get("observaciones", []),
        version_reglas=c.version_reglas,
    )
