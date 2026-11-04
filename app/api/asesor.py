"""Consola del asesor (human-in-the-loop): cola de escalamientos, toma con bloqueo, chat y resolución."""

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.eventos import publicar, stream_sse
from app.core.errors import ApiError, respuestas
from app.core.security import Actor, AsesorOAdmin
from app.db import get_session
from app.domain.pii import enmascarar_nit
from app.models import CriterioEscalamiento, Cuenta, Escalamiento, Mensaje, SesionChat, Usuario
from app.models.base import EstadoEscalamiento, EstadoSesion, Rol, RolMensaje
from app.schemas.admin import (
    CuentaResumen,
    EscalamientoDetalleOut,
    EscalamientoOut,
    MensajeAsesorIn,
    MensajeOut,
    ResolverIn,
    SesionDetalleOut,
    UsuarioResumen,
)
from app.schemas.catalogo import Pagina
from app.servicios.auditoria import auditar

router = APIRouter(prefix="/asesor", tags=["Asesor"])
ABIERTOS = (EstadoEscalamiento.PENDIENTE, EstadoEscalamiento.TOMADO)
UMBRAL_VIP_ENVIOS = 500  # CRIT-004 (reglas_escalacion_humana.json)


def _escalamiento_out(e: Escalamiento, c: CriterioEscalamiento, detalle: bool = False):
    fin = e.tomado_en or e.resuelto_en or datetime.now(UTC)
    datos = dict(
        id=e.id,
        sesion_id=e.sesion_id,
        criterio_id=e.criterio_id,
        criterio_categoria=c.categoria,
        accion=c.accion,
        prioridad=e.prioridad,
        estado=e.estado,
        asesor_id=e.asesor_id,
        resumen_ia=e.resumen_ia,
        numero_guia=(e.payload or {}).get("numero_guia_consultada"),
        espera_s=max(0, int((fin - e.creado_en).total_seconds())),
        creado_en=e.creado_en,
        tomado_en=e.tomado_en,
        resuelto_en=e.resuelto_en,
    )
    return EscalamientoDetalleOut(**datos, payload=e.payload or {}) if detalle else EscalamientoOut(**datos)


async def detalle_sesion(s: AsyncSession, sesion_id: uuid.UUID) -> SesionDetalleOut:
    """Historial completo + escalamiento (abierto o último) + cuenta. Lo reutiliza /admin/conversaciones/{id}."""
    sesion = await s.get(SesionChat, sesion_id)
    if sesion is None:
        raise ApiError(404, "No existe la sesión indicada.", "SESION_NO_ENCONTRADA")
    usuario = await s.get(Usuario, sesion.usuario_id) if sesion.usuario_id else None
    cuenta: Cuenta | None = usuario.cuenta if usuario else None
    fila = (
        await s.execute(
            select(Escalamiento, CriterioEscalamiento)
            .join(CriterioEscalamiento)
            .where(Escalamiento.sesion_id == sesion_id)
            .order_by(Escalamiento.estado.in_(ABIERTOS).desc(), Escalamiento.creado_en.desc())
            .limit(1)
        )
    ).first()
    mensajes = (await s.scalars(select(Mensaje).where(Mensaje.sesion_id == sesion_id).order_by(Mensaje.id))).all()
    return SesionDetalleOut(
        id=sesion.id,
        estado=sesion.estado,
        canal=sesion.canal,
        creado_en=sesion.creado_en,
        ultima_actividad=sesion.ultima_actividad,
        resumen=sesion.resumen,
        contexto=sesion.contexto or {},
        usuario=UsuarioResumen(id=usuario.id, nombre=usuario.nombre, email=usuario.email, rol=usuario.rol)
        if usuario
        else None,
        cuenta=CuentaResumen(
            razon_social=cuenta.razon_social,
            nit_enmascarado=enmascarar_nit(cuenta.nit),
            tipo_cuenta=cuenta.tipo_cuenta,
            envios_mensuales=cuenta.envios_mensuales,
            es_vip=cuenta.tipo_cuenta.value == "CORPORATIVO_GOLD" or cuenta.envios_mensuales > UMBRAL_VIP_ENVIOS,
        )
        if cuenta
        else None,
        escalamiento=_escalamiento_out(*fila, detalle=True) if fila else None,
        mensajes=[MensajeOut.model_validate(m) for m in mensajes],
    )


async def _criterio(s: AsyncSession, e: Escalamiento) -> CriterioEscalamiento:
    return await s.get(CriterioEscalamiento, e.criterio_id)


def _puede_operar(e: Escalamiento, actor: Actor) -> bool:
    return e.estado is EstadoEscalamiento.TOMADO and (e.asesor_id == actor.id or actor.rol is Rol.ADMIN)


@router.get(
    "/escalamientos",
    response_model=Pagina[EscalamientoOut],
    summary="Cola de escalamientos",
    responses=respuestas(401, 403, 422),
)
async def cola(
    actor: AsesorOAdmin,
    estado: EstadoEscalamiento = EstadoEscalamiento.PENDIENTE,
    pagina: Annotated[int, Query(ge=1)] = 1,
    tamano: Annotated[int, Query(ge=1, le=100)] = 20,
    s: AsyncSession = Depends(get_session),
):
    """Ordenada por prioridad (1 = más urgente) y antigüedad. Incluye resumen IA, guía y tiempo de espera."""
    total = await s.scalar(select(func.count()).select_from(Escalamiento).where(Escalamiento.estado == estado))
    filas = (
        await s.execute(
            select(Escalamiento, CriterioEscalamiento)
            .join(CriterioEscalamiento)
            .where(Escalamiento.estado == estado)
            .order_by(Escalamiento.prioridad, Escalamiento.creado_en)
            .offset((pagina - 1) * tamano)
            .limit(tamano)
        )
    ).all()
    return Pagina(items=[_escalamiento_out(e, c) for e, c in filas], total=total, pagina=pagina, tamano=tamano)


@router.post(
    "/escalamientos/{escalamiento_id}/tomar",
    response_model=EscalamientoDetalleOut,
    summary="Tomar un escalamiento",
    responses=respuestas(401, 403, 404, 409, 422),
)
async def tomar(escalamiento_id: uuid.UUID, actor: AsesorOAdmin, s: AsyncSession = Depends(get_session)):
    """`SELECT … FOR UPDATE SKIP LOCKED`: si otro asesor lo está tomando o ya lo tomó, responde 409 YA_TOMADO.
    Volver a tomar uno propio es idempotente."""
    e = await s.scalar(select(Escalamiento).where(Escalamiento.id == escalamiento_id).with_for_update(skip_locked=True))
    if e is None:
        if await s.scalar(select(Escalamiento.id).where(Escalamiento.id == escalamiento_id)) is None:
            raise ApiError(404, "No existe el escalamiento indicado.", "ESCALAMIENTO_NO_ENCONTRADO")
        raise ApiError(409, "Otro asesor está tomando este escalamiento.", "YA_TOMADO")
    if e.estado is EstadoEscalamiento.RESUELTO:
        raise ApiError(409, "El escalamiento ya fue resuelto.", "ESCALAMIENTO_RESUELTO")
    if e.estado is EstadoEscalamiento.TOMADO and e.asesor_id != actor.id:
        raise ApiError(409, "Otro asesor ya tomó este escalamiento.", "YA_TOMADO")
    if e.estado is EstadoEscalamiento.PENDIENTE:
        e.estado, e.asesor_id, e.tomado_en = EstadoEscalamiento.TOMADO, actor.id, datetime.now(UTC)
        sesion = await s.get(SesionChat, e.sesion_id)
        sesion.estado = EstadoSesion.ESCALADA
        auditar(s, actor, "escalamiento.tomar", "escalamiento", str(e.id), sesion_id=str(e.sesion_id))
        await s.commit()
    return _escalamiento_out(e, await _criterio(s, e), detalle=True)


@router.get(
    "/sesiones/{sesion_id}",
    response_model=SesionDetalleOut,
    summary="Historial y contexto de una sesión",
    responses=respuestas(401, 403, 404, 422),
)
async def ver_sesion(sesion_id: uuid.UUID, actor: AsesorOAdmin, s: AsyncSession = Depends(get_session)):
    """Mensajes completos (con artifacts), payload de transferencia y datos de la cuenta (VIP)."""
    return await detalle_sesion(s, sesion_id)


@router.get(
    "/sesiones/{sesion_id}/eventos",
    summary="Eventos en vivo de la sesión (SSE)",
    responses={
        200: {
            "description": "Eventos `mensaje_cliente`, `mensaje_asesor` y `escalamiento_resuelto`",
            "content": {"text/event-stream": {}},
        },
        **respuestas(401, 403, 404, 422),
    },
)
async def eventos_sesion(sesion_id: uuid.UUID, actor: AsesorOAdmin, s: AsyncSession = Depends(get_session)):
    """El chat punto a punto del lado del asesor. Envía `: ping` cada 15 s. Lo publicado durante un corte no se
    reenvía: al reconectar, consulta `GET /asesor/sesiones/{id}`."""
    if await s.get(SesionChat, sesion_id) is None:
        raise ApiError(404, "No existe la sesión indicada.", "SESION_NO_ENCONTRADA")
    await s.close()
    return StreamingResponse(
        stream_sse(sesion_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post(
    "/sesiones/{sesion_id}/mensajes",
    status_code=status.HTTP_201_CREATED,
    response_model=MensajeOut,
    summary="Responder al cliente como asesor",
    responses=respuestas(401, 403, 404, 409, 422),
)
async def responder(
    sesion_id: uuid.UUID, datos: MensajeAsesorIn, actor: AsesorOAdmin, s: AsyncSession = Depends(get_session)
):
    """Solo si el escalamiento abierto de la sesión está tomado por ti (un admin puede intervenir siempre que
    esté tomado). El mensaje llega al cliente por SSE (`mensaje_asesor`)."""
    sesion = await s.get(SesionChat, sesion_id, with_for_update=True)
    if sesion is None:
        raise ApiError(404, "No existe la sesión indicada.", "SESION_NO_ENCONTRADA")
    e = await s.scalar(
        select(Escalamiento).where(Escalamiento.sesion_id == sesion_id, Escalamiento.estado.in_(ABIERTOS))
    )
    if e is None or not _puede_operar(e, actor):
        raise ApiError(409, "Primero debes tomar el escalamiento de esta sesión.", "ESCALAMIENTO_NO_TOMADO")
    m = Mensaje(
        sesion_id=sesion_id, turno_id=uuid.uuid4(), rol=RolMensaje.ASESOR, autor_id=actor.id, contenido=datos.texto
    )
    s.add(m)
    sesion.ultima_actividad = datetime.now(UTC)
    auditar(s, actor, "sesion.mensaje_asesor", "sesion", str(sesion_id), caracteres=len(datos.texto))
    await s.flush()
    await s.refresh(m)
    nombre = await s.scalar(select(Usuario.nombre).where(Usuario.id == actor.id))
    await s.commit()
    publicar(
        sesion_id, ("mensaje_asesor", {"texto": m.contenido, "asesor": nombre, "creado_en": m.creado_en.isoformat()})
    )
    return MensajeOut.model_validate(m)


@router.post(
    "/escalamientos/{escalamiento_id}/resolver",
    response_model=EscalamientoDetalleOut,
    summary="Resolver un escalamiento y devolver la sesión a la IA",
    responses=respuestas(401, 403, 404, 409, 422),
)
async def resolver(
    escalamiento_id: uuid.UUID,
    actor: AsesorOAdmin,
    datos: ResolverIn | None = None,
    s: AsyncSession = Depends(get_session),
):
    """Debe estar tomado por ti (o eres admin). La sesión vuelve a `activa` y el cliente recibe
    `escalamiento_resuelto`."""
    e = await s.scalar(select(Escalamiento).where(Escalamiento.id == escalamiento_id).with_for_update())
    if e is None:
        raise ApiError(404, "No existe el escalamiento indicado.", "ESCALAMIENTO_NO_ENCONTRADO")
    if e.estado is EstadoEscalamiento.RESUELTO:
        raise ApiError(409, "El escalamiento ya fue resuelto.", "ESCALAMIENTO_RESUELTO")
    if not _puede_operar(e, actor):
        raise ApiError(409, "Primero debes tomar este escalamiento.", "ESCALAMIENTO_NO_TOMADO")
    nota = datos.nota if datos else None
    e.estado, e.resuelto_en = EstadoEscalamiento.RESUELTO, datetime.now(UTC)
    e.payload = (e.payload or {}) | {"nota_resolucion": nota}
    sesion = await s.get(SesionChat, e.sesion_id)
    sesion.estado = EstadoSesion.ACTIVA
    sesion.ultima_actividad = e.resuelto_en
    auditar(s, actor, "escalamiento.resolver", "escalamiento", str(e.id), con_nota=nota is not None)
    await s.commit()
    publicar(e.sesion_id, ("escalamiento_resuelto", {"escalamiento_id": str(e.id), "nota": nota}))
    return _escalamiento_out(e, await _criterio(s, e), detalle=True)
