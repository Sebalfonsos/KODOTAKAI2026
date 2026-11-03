"""Chat con el agente: sesiones, mensajes (SSE o JSON), eventos del asesor en vivo y calificación."""

import asyncio
import json
import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Body, Depends, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.eventos import suscribir
from app.ai.orquestador import Entrada, agregar, ejecutar, formulario_guardado
from app.core.errors import ApiError, respuestas
from app.core.ratelimit import limite
from app.core.security import Actor, ActorOpcional
from app.db import get_session
from app.domain.sanitizar import limpiar_texto
from app.models import Calificacion, Mensaje, SesionChat
from app.models.base import Canal, EstadoSesion, Rol
from app.schemas.chat import ChatTurnResponse, ErrorFormulario, MensajeEntrada, formatear_sse, validar_envio_formulario

router = APIRouter(prefix="/chat", tags=["Chat"])
SSE = "text/event-stream"


class SesionOut(BaseModel):
    id: uuid.UUID
    estado: EstadoSesion
    canal: Canal
    creado_en: datetime


class MensajeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    turno_id: uuid.UUID
    rol: str
    contenido: str
    artifacts: list[dict]
    intencion: str | None
    confianza: float | None
    creado_en: datetime


class HistorialOut(SesionOut):
    mensajes: list[MensajeOut]


class CalificacionIn(BaseModel):
    model_config = ConfigDict(
        extra="forbid", json_schema_extra={"examples": [{"puntaje": 5, "comentario": "Muy rápido"}]}
    )
    puntaje: int = Field(ge=1, le=5)
    comentario: str | None = Field(default=None, max_length=500)


async def sesion_propia(s: AsyncSession, sesion_id: uuid.UUID, actor: Actor) -> SesionChat:
    """Una sesión de invitado se usa con su id (UUID aleatorio, no adivinable); la de un usuario, solo con su token."""
    sesion = await s.get(SesionChat, sesion_id)
    if sesion is None or (
        sesion.usuario_id is not None and sesion.usuario_id != actor.id and actor.rol not in (Rol.ADMIN, Rol.ASESOR)
    ):
        raise ApiError(404, "No encontramos esa conversación.", "SESION_NO_ENCONTRADA")
    return sesion


@router.post(
    "/sesiones",
    status_code=status.HTTP_201_CREATED,
    response_model=SesionOut,
    summary="Iniciar una conversación",
    responses=respuestas(429),
    dependencies=[Depends(limite("sesiones", 20, 3600))],
)
async def crear_sesion(actor: ActorOpcional, s: AsyncSession = Depends(get_session)):
    """Invitados y clientes. Con token, la sesión queda ligada al usuario (habilita PQRS y datos de su cuenta)."""
    sesion = SesionChat(usuario_id=actor.id, canal=Canal.WEB, contexto={})
    s.add(sesion)
    await s.commit()
    await s.refresh(sesion)
    return SesionOut(id=sesion.id, estado=sesion.estado, canal=sesion.canal, creado_en=sesion.creado_en)


@router.get(
    "/sesiones/{sesion_id}",
    response_model=HistorialOut,
    summary="Historial de la conversación",
    responses=respuestas(404, 422),
)
async def historial(sesion_id: uuid.UUID, actor: ActorOpcional, s: AsyncSession = Depends(get_session)):
    """Mensajes con sus artifacts, en orden. Sirve para reconstruir la UI tras recargar o perder la conexión."""
    sesion = await sesion_propia(s, sesion_id, actor)
    filas = (await s.scalars(select(Mensaje).where(Mensaje.sesion_id == sesion.id).order_by(Mensaje.id))).all()
    return HistorialOut(
        id=sesion.id,
        estado=sesion.estado,
        canal=sesion.canal,
        creado_en=sesion.creado_en,
        mensajes=[
            MensajeOut(
                id=m.id,
                turno_id=m.turno_id,
                rol=m.rol.value,
                contenido=m.contenido,
                artifacts=m.artifacts,
                intencion=m.intencion,
                confianza=float(m.confianza) if m.confianza is not None else None,
                creado_en=m.creado_en,
            )
            for m in filas
        ],
    )


@router.post(
    "/sesiones/{sesion_id}/mensajes",
    summary="Enviar un mensaje (respuesta en SSE o JSON)",
    response_model=ChatTurnResponse,
    responses={
        200: {
            "description": "Por defecto `text/event-stream` con eventos `meta`, `artifact`, `delta`, `reemplazo`, "
            "`citas`, "
            "`escalamiento`, `fin` y `error` (ver docs/frontend.md). Con `?stream=false`, un `ChatTurnResponse` JSON.",
            "content": {SSE: {"schema": {"type": "string"}}},
        },
        **respuestas(404, 422, 429),
    },
    dependencies=[Depends(limite("chat", 30, 60))],
)
async def enviar(
    sesion_id: uuid.UUID,
    entrada: Annotated[MensajeEntrada, Body()],
    actor: ActorOpcional,
    s: AsyncSession = Depends(get_session),
    stream: Annotated[bool, Query(description="false = respuesta JSON única")] = True,
):
    """Texto libre (`tipo: texto`) o envío de un formulario emitido por el servidor (`tipo: artifact_submit`).
    Los formularios se validan aquí contra el esquema que emitió el servidor: un 422 llega antes de abrir el stream."""
    sesion = await sesion_propia(s, sesion_id, actor)
    if sesion.estado == EstadoSesion.CERRADA:
        raise ApiError(409, "La conversación está cerrada; inicia una nueva.", "SESION_CERRADA")
    if entrada.tipo == "texto":
        texto = limpiar_texto(entrada.texto, max_len=2000)
        if not texto:
            raise ApiError(422, "El mensaje está vacío.", "MENSAJE_VACIO")
        e = Entrada(sesion_id=sesion.id, actor=actor, texto=texto)
    else:
        formulario = formulario_guardado(sesion, entrada.artifact_id)
        try:
            valores = validar_envio_formulario(formulario, entrada.valores)
        except ErrorFormulario as err:
            raise ApiError(
                422,
                f"El formulario tiene {len(err.errores)} campo(s) con error.",
                "FORMULARIO_INVALIDO",
                errores=err.como_problema(),
            ) from err
        e = Entrada(sesion_id=sesion.id, actor=actor, formulario=formulario.tipo, valores=valores)
    await s.close()  # el turno usa su propia conexión; esta se libera ya
    if not stream:
        return await agregar(e)

    async def cuerpo():
        async for evento in ejecutar(e):
            yield formatear_sse(evento)

    return StreamingResponse(cuerpo(), media_type=SSE, headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get(
    "/sesiones/{sesion_id}/eventos",
    summary="Eventos en vivo del asesor (SSE)",
    responses={
        200: {"description": "Eventos `mensaje_asesor` y `escalamiento_resuelto`", "content": {SSE: {}}},
        **respuestas(404, 422),
    },
)
async def eventos(sesion_id: uuid.UUID, actor: ActorOpcional, s: AsyncSession = Depends(get_session)):
    """Mantener abierto mientras la conversación esté escalada. Envía un comentario `: ping` cada 15 s."""
    sesion = await sesion_propia(s, sesion_id, actor)
    await s.close()

    async def cuerpo():
        with suscribir(sesion.id) as cola:
            yield ": conectado\n\n"
            while True:
                try:
                    nombre, datos = await asyncio.wait_for(cola.get(), timeout=15)
                except TimeoutError:
                    yield ": ping\n\n"
                    continue
                if nombre == "mensaje_cliente":
                    continue  # eco del propio cliente: solo le interesa al asesor
                yield f"event: {nombre}\ndata: {json.dumps(datos, ensure_ascii=False, default=str)}\n\n"

    return StreamingResponse(cuerpo(), media_type=SSE, headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post(
    "/sesiones/{sesion_id}/calificacion",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Calificar la atención (CSAT 1-5)",
    responses=respuestas(404, 422),
)
async def calificar(
    sesion_id: uuid.UUID, datos: CalificacionIn, actor: ActorOpcional, s: AsyncSession = Depends(get_session)
):
    sesion = await sesion_propia(s, sesion_id, actor)
    await s.execute(
        insert(Calificacion)
        .values(sesion_id=sesion.id, puntaje=datos.puntaje, comentario=datos.comentario, creado_en=datetime.now(UTC))
        .on_conflict_do_update(
            index_elements=["sesion_id"], set_={"puntaje": datos.puntaje, "comentario": datos.comentario}
        )
    )
    await s.commit()
