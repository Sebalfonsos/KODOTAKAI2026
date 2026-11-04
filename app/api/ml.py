"""Predicciones con IA que se autoentrenan (solo administradores). Datos de entrenamiento SIMULADOS."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.errors import respuestas
from app.core.security import SoloAdmin
from app.db import get_session
from app.ml import autoentrenamiento, servicio
from app.schemas.ml import (
    AvanceSimulacionOut,
    EntrenamientosOut,
    EstadoAutoentrenamientoOut,
    ModelosOut,
    PronosticoOut,
    ResultadoEntrenamiento,
    RiesgoOut,
)

# Sin prefijo: las rutas viven bajo /admin/ml y /admin/simulador (main.py añade /api/v1).
router = APIRouter(tags=["Predicciones IA"])
Sesion = Annotated[AsyncSession, Depends(get_session)]


@router.get(
    "/admin/ml/modelos",
    response_model=ModelosOut,
    summary="Modelos activos e historial",
    responses=respuestas(401, 403),
)
async def modelos(_: SoloAdmin, s: Sesion):
    """Modelos activos y los últimos 50 (candidatos, retirados, rechazados) con métricas y línea base."""
    return await servicio.listar_modelos(s)


@router.get(
    "/admin/ml/entrenamientos",
    response_model=EntrenamientosOut,
    summary="Corridas de entrenamiento",
    responses=respuestas(401, 403, 422),
)
async def entrenamientos(
    _: SoloAdmin,
    s: Sesion,
    pagina: Annotated[int, Query(ge=1)] = 1,
    tamano: Annotated[int, Query(ge=1, le=100)] = 20,
):
    """Corridas con su motivo (inicial, nuevos_datos, deriva, antiguedad, manual) y la decisión champion/challenger."""
    return await servicio.listar_entrenamientos(s, pagina, tamano)


@router.get(
    "/admin/ml/estado",
    response_model=EstadoAutoentrenamientoOut,
    summary="Reglas y estado del autoentrenamiento",
    responses=respuestas(401, 403),
)
async def estado(_: SoloAdmin, s: Sesion):
    """Qué dispararía el próximo reentrenamiento: reglas configuradas y valores medidos ahora."""
    cfg = get_settings()
    return EstadoAutoentrenamientoOut(
        revision_cada_min=cfg.ml_check_min,
        min_etiquetas_nuevas=cfg.ml_min_nuevos,
        max_horas=cfg.ml_max_horas,
        delta_deriva=autoentrenamiento.DELTA_DERIVA,
        min_etiquetados=servicio.MIN_ETIQUETADOS,
        **await servicio.estado_disparo(s),
    )


@router.post(
    "/admin/ml/entrenar",
    status_code=202,
    response_model=ResultadoEntrenamiento,
    summary="Reentrenar ahora (manual)",
    responses=respuestas(401, 403, 409),
)
async def entrenar(_: SoloAdmin, s: Sesion):
    """Entrena retadores en un proceso aparte y los promueve solo si superan al campeón en el mismo holdout.
    409 si ya hay un entrenamiento en curso o faltan datos."""
    return await servicio.entrenar(s, "manual")


@router.get(
    "/admin/ml/riesgo-retraso",
    response_model=RiesgoOut,
    summary="Riesgo de retraso de una guía",
    responses=respuestas(401, 403, 404, 422, 503),
)
async def riesgo_retraso(
    _: SoloAdmin,
    s: Sesion,
    guia: Annotated[str, Query(pattern=r"^TLX-\d{6}-CO$", examples=["TLX-984021-CO"])],
):
    """Probabilidad de que la guía supere su fecha estimada, nivel y factores que más la explican."""
    return await servicio.predecir_riesgo(s, guia)


@router.get(
    "/admin/ml/pronostico-demanda",
    response_model=PronosticoOut,
    summary="Pronóstico de despachos por origen",
    responses=respuestas(401, 403, 404, 422, 503),
)
async def pronostico_demanda(
    _: SoloAdmin,
    s: Sesion,
    origen: Annotated[
        str, Query(min_length=2, max_length=120, examples=["Bogotá D.C."], description="Municipio de origen o su hub")
    ],
    dias: Annotated[int, Query(ge=1, le=30)] = 14,
):
    """Despachos diarios esperados con intervalo del 80 % (p10–p90) y los últimos 28 días observados."""
    return await servicio.pronosticar_demanda(s, origen, dias)


@router.post(
    "/admin/simulador/avanzar",
    response_model=AvanceSimulacionOut,
    summary="Avanzar el simulador N días",
    responses=respuestas(401, 403, 409, 422),
)
async def avanzar(_: SoloAdmin, s: Sesion, dias: Annotated[int, Query(ge=1, le=60)] = 7):
    """Crea envíos simulados nuevos y cierra los pendientes; aporta etiquetas nuevas para el autoentrenamiento."""
    return await servicio.avanzar_simulacion(s, dias)
