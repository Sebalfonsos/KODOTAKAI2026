"""Normativa de mercancías peligrosas y prohibidas (DOC-OPS-2026-03)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import respuestas
from app.core.ratelimit import limite
from app.db import get_session
from app.domain.mercancias import evaluar_producto
from app.domain.sanitizar import limpiar_texto
from app.models import ClaseOnu
from app.schemas.catalogo import ClaseOnuOut, VeredictoOut

router = APIRouter(prefix="/mercancias", tags=["Mercancías"])


@router.get(
    "/consultar",
    response_model=VeredictoOut,
    summary="¿Se puede enviar este producto?",
    responses=respuestas(422, 429),
    dependencies=[Depends(limite("mercancias", 60, 60))],
)
async def consultar(producto: Annotated[str, Query(min_length=2, max_length=200, examples=["ácido clorhídrico"])]):
    """Veredicto determinista (permitido, restringido, solo_ftl, prohibido o desconocido) con la sección del manual
    que lo fundamenta y los documentos exigidos (MSDS de 16 secciones, tarjeta NTC 4532, RNDC)."""
    texto = limpiar_texto(producto, max_len=200)
    v = evaluar_producto(texto)
    return VeredictoOut(
        producto_consultado=texto,
        veredicto=v.veredicto,
        producto=v.producto,
        clase_onu=v.clase_onu,
        motivo=v.motivo,
        fuente=v.fuente,
        documentos_requeridos=list(v.documentos_requeridos),
        categoria_embalaje=v.categoria_embalaje,
    )


@router.get(
    "/clases", response_model=list[ClaseOnuOut], summary="Clases ONU y política de TransLogix", responses=respuestas()
)
async def clases(s: AsyncSession = Depends(get_session)):
    filas = (await s.scalars(select(ClaseOnu).order_by(ClaseOnu.codigo))).all()
    return [
        ClaseOnuOut(codigo=c.codigo, nombre=c.nombre, politica=c.politica.value, condiciones=c.condiciones)
        for c in filas
    ]
