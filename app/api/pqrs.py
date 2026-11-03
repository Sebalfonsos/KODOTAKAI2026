"""PQRS e indemnizaciones (ruta literal del dosier: POST /api/v1/pqrs/crear-ticket)."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Form, Header, Path, Query, UploadFile, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import respuestas
from app.core.ratelimit import limite
from app.core.security import ActorAutenticado, SoloCliente
from app.db import get_session
from app.domain.liquidacion import liquidar_indemnizacion
from app.models.base import TipoDocumento
from app.schemas.pqrs import GUIA, LiquidacionIn, LiquidacionOut, PlazoOut, TicketIn, TicketOut
from app.servicios import idempotencia
from app.servicios import pqrs as svc
from app.servicios.reglas import reglas_escalamiento

router = APIRouter(prefix="/pqrs", tags=["PQRS"])
RADICADO = Annotated[str, Path(pattern=r"^PQRS-\d{4}-\d{6}$", examples=["PQRS-2026-000001"])]


@router.post(
    "/crear-ticket",
    status_code=status.HTTP_201_CREATED,
    response_model=TicketOut,
    summary="Radicar una PQRS o solicitud de indemnización",
    responses=respuestas(401, 403, 404, 409, 422, 429),
    dependencies=[Depends(limite("pqrs", 10, 3600))],
)
async def crear_ticket(
    datos: TicketIn,
    actor: SoloCliente,
    s: AsyncSession = Depends(get_session),
    idempotency_key: Annotated[str | None, Header(description="Recomendado: evita radicados duplicados")] = None,
):
    """Valida el plazo legal en días hábiles (avería aparente: al recibir; oculta: 3 días hábiles; pérdida: 5+10),
    arma el checklist documental del protocolo y fija la fecha límite de respuesta (15 días hábiles).
    Reclamaciones de más de $5.000.000 o con carga especial se marcan como escaladas (CRIT-003/CRIT-005)."""
    if previo := await idempotencia.buscar(s, idempotency_key, "pqrs", actor.sujeto, datos):
        return JSONResponse(previo, status_code=201)
    out = await svc.crear_ticket(s, datos, actor, reglas_escalamiento())
    idempotencia.guardar(s, idempotency_key, "pqrs", actor.sujeto, datos, 201, out)
    await s.commit()
    return out


@router.get(
    "/plazo", response_model=PlazoOut, summary="¿Estoy a tiempo de reclamar?", responses=respuestas(401, 404, 422)
)
async def consultar_plazo(
    actor: ActorAutenticado,
    guia: Annotated[str, Query(pattern=GUIA)],
    tipo_averia: Annotated[Literal["aparente", "oculta", "perdida"], Query()],
    anotada_en_guia: bool = False,
    s: AsyncSession = Depends(get_session),
):
    return await svc.plazo(s, guia, tipo_averia, anotada_en_guia, actor)


@router.post(
    "/liquidacion-estimada",
    response_model=LiquidacionOut,
    summary="Estimar el monto a indemnizar",
    responses=respuestas(422),
)
async def liquidacion(datos: LiquidacionIn):
    """mín(valor declarado, factura) − deducible del 5 % si el declarado supera $2.000.000 (+ flete si aplica)."""
    r = liquidar_indemnizacion(
        datos.valor_declarado,
        datos.valor_factura,
        flete_cobrado=datos.flete_cobrado,
        tipo_siniestro=datos.tipo_siniestro,
        negligencia_demostrada=datos.negligencia_demostrada,
    )
    return LiquidacionOut(
        base=r.base,
        deducible=r.deducible,
        flete_devuelto=r.flete_devuelto,
        total=r.total,
        aplica_deducible=r.aplica_deducible,
    )


@router.get(
    "/{radicado}", response_model=TicketOut, summary="Consultar un radicado", responses=respuestas(401, 404, 422)
)
async def ver_ticket(radicado: RADICADO, actor: ActorAutenticado, s: AsyncSession = Depends(get_session)):
    return svc.a_salida(await svc.obtener_ticket(s, radicado, actor))


@router.post(
    "/{radicado}/documentos",
    status_code=status.HTTP_201_CREATED,
    response_model=TicketOut,
    summary="Adjuntar un soporte (PDF, JPG o PNG, máx. 10 MB)",
    responses=respuestas(401, 404, 409, 413, 415, 422, 429),
    dependencies=[Depends(limite("uploads", 20, 3600))],
)
async def adjuntar(
    radicado: RADICADO,
    actor: SoloCliente,
    tipo_documento: Annotated[TipoDocumento, Form()],
    archivo: Annotated[UploadFile, File(description="PDF, JPG o PNG; el tipo se verifica por su firma binaria")],
    s: AsyncSession = Depends(get_session),
):
    out = await svc.adjuntar(s, radicado, tipo_documento, archivo, actor)
    await s.commit()
    return out
