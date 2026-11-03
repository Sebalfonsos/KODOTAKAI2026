"""PQRS e indemnizaciones: plazos legales, checklist documental, radicación y carga de soportes."""

import hashlib
import uuid
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.core.errors import ApiError
from app.core.security import Actor
from app.domain.escalamiento import ContextoTurno, evaluar_escalamiento
from app.domain.plazos import evaluar_plazo_reclamo, fecha_limite_respuesta
from app.models import DocumentoPqrs, Envio, TicketPqrs
from app.models.base import EstadoPqrs, Rol, TipoDocumento, TipoPqrs
from app.schemas.pqrs import PlazoOut, TicketIn, TicketOut

ZONA = ZoneInfo("America/Bogota")
FIRMAS = {
    b"%PDF-": ("application/pdf", ".pdf"),
    b"\xff\xd8\xff": ("image/jpeg", ".jpg"),
    b"\x89PNG\r\n\x1a\n": ("image/png", ".png"),
}


def hoy() -> date:
    return datetime.now(ZONA).date()


def documentos_requeridos(tipo: TipoPqrs, tipo_averia: str | None) -> list[TipoDocumento]:
    """Checklist del protocolo DOC-PQRS-2026-04 §4 (+ acta con salvedad para avería aparente, D-09)."""
    if tipo is not TipoPqrs.SINIESTRO:
        return []
    docs = [
        TipoDocumento.FACTURA,
        TipoDocumento.CARTA_RECLAMACION,
        TipoDocumento.CERTIFICACION_BANCARIA,
        TipoDocumento.DOCUMENTO_IDENTIDAD,
    ]
    if tipo_averia in ("aparente", "oculta"):
        docs += [TipoDocumento.FOTO_EMPAQUE, TipoDocumento.FOTO_DANO, TipoDocumento.FOTO_AMORTIGUACION]
    if tipo_averia == "aparente":
        docs.append(TipoDocumento.ACTA_SALVEDAD)
    return docs


def _checklist(tipo: TipoPqrs, tipo_averia: str | None, numero_guia: str | None, cargados: set[str]) -> dict:
    items = {d.value: d.value in cargados for d in documentos_requeridos(tipo, tipo_averia)}
    if tipo is TipoPqrs.SINIESTRO:
        items[TipoDocumento.GUIA.value] = numero_guia is not None  # el número de guía cumple el ítem 1
    return items


def _referencia_plazo(envio: Envio, tipo_averia: str) -> date:
    if tipo_averia == "perdida":
        return envio.fecha_estimada_entrega.astimezone(ZONA).date()
    if envio.fecha_entrega_real is None:
        raise ApiError(
            422, "La guía aún no registra entrega; para pérdida usa tipo_averia='perdida'.", "ENVIO_NO_ENTREGADO"
        )
    return envio.fecha_entrega_real.astimezone(ZONA).date()


async def _envio_propio(s: AsyncSession, guia: str, actor: Actor) -> Envio:
    envio = await s.get(Envio, guia)
    # 404 (no 403) para no revelar la existencia de guías ajenas.
    if envio is None or (actor.rol is Rol.CLIENTE and envio.cuenta_id != actor.cuenta_id):
        raise ApiError(404, f"No encontramos la guía {guia} entre tus envíos.", "GUIA_NO_ENCONTRADA")
    return envio


async def plazo(s: AsyncSession, guia: str, tipo_averia: str, anotada: bool, actor: Actor) -> PlazoOut:
    envio = await _envio_propio(s, guia, actor)
    ref = _referencia_plazo(envio, tipo_averia)
    ev = evaluar_plazo_reclamo(tipo_averia, ref, hoy(), anotada_en_guia=anotada)
    return PlazoOut(
        numero_guia=guia,
        tipo_averia=tipo_averia,
        fecha_referencia=ref,
        vigente=ev.vigente,
        fecha_limite=ev.fecha_limite,
        dias_habiles_restantes=ev.dias_habiles_restantes,
        fundamento=ev.fundamento,
    )


def a_salida(t: TicketPqrs, escalado: bool = False) -> TicketOut:
    out = TicketOut.model_validate(t)
    out.escalado = escalado or t.prioridad == 1
    return out


async def crear_ticket(
    s: AsyncSession, datos: TicketIn, actor: Actor, reglas: dict, sesion_id: uuid.UUID | None = None
) -> TicketOut:
    envio = await _envio_propio(s, datos.numero_guia, actor) if datos.numero_guia else None
    if datos.tipo is TipoPqrs.SINIESTRO:
        if envio is None or datos.tipo_averia is None:
            raise ApiError(422, "Una indemnización requiere numero_guia y tipo_averia.", "DATOS_SINIESTRO_INCOMPLETOS")
        ev = evaluar_plazo_reclamo(
            datos.tipo_averia, _referencia_plazo(envio, datos.tipo_averia), hoy(), datos.anotada_en_guia
        )
        if not ev.vigente:
            raise ApiError(422, ev.fundamento, "PLAZO_VENCIDO")

    disparados = evaluar_escalamiento(
        reglas,
        ContextoTurno(
            confidence_score=1.0,
            texto_usuario=datos.descripcion,
            flujo="pqrs",
            valor_declarado=envio.valor_declarado if envio else None,
            valor_reclamacion=datos.valor_reclamado,
            mercancia_peligrosa=envio.mercancia_peligrosa if envio else False,
            requiere_refrigeracion=envio.requiere_refrigeracion if envio else False,
            estado_envio=envio.estado_actual if envio else None,
        ),
    )
    checklist = _checklist(datos.tipo, datos.tipo_averia, datos.numero_guia, set())
    ticket = TicketPqrs(
        tipo=datos.tipo,
        estado=EstadoPqrs.RADICADO if all(checklist.values()) else EstadoPqrs.INCOMPLETO,
        usuario_id=actor.id,
        numero_guia=datos.numero_guia,
        sesion_id=sesion_id,
        descripcion=datos.descripcion,
        tipo_averia=datos.tipo_averia,
        valor_reclamado=datos.valor_reclamado,
        fecha_limite_respuesta=fecha_limite_respuesta(hoy()),
        prioridad=1 if disparados else 3,
        checklist=checklist,
    )
    s.add(ticket)
    await s.flush()
    await s.refresh(ticket, ["radicado", "creado_en", "documentos"])
    return a_salida(ticket, escalado=bool(disparados))


async def obtener_ticket(s: AsyncSession, radicado: str, actor: Actor, bloquear: bool = False) -> TicketPqrs:
    q = select(TicketPqrs).where(TicketPqrs.radicado == radicado).options(selectinload(TicketPqrs.documentos))
    if bloquear:
        q = q.with_for_update()
    t = await s.scalar(q)
    if t is None or (actor.rol is Rol.CLIENTE and t.usuario_id != actor.id):
        raise ApiError(404, f"No encontramos el radicado {radicado}.", "RADICADO_NO_ENCONTRADO")
    return t


async def adjuntar(
    s: AsyncSession, radicado: str, tipo_documento: TipoDocumento, archivo: UploadFile, actor: Actor
) -> TicketOut:
    cfg = get_settings()
    ticket = await obtener_ticket(s, radicado, actor, bloquear=True)
    if ticket.estado in (EstadoPqrs.CERRADO, EstadoPqrs.APROBADO, EstadoPqrs.RECHAZADO):
        raise ApiError(409, "El radicado ya está cerrado; no admite más documentos.", "RADICADO_CERRADO")
    contenido = await archivo.read(cfg.max_upload_bytes + 1)
    if len(contenido) > cfg.max_upload_bytes:
        raise ApiError(413, f"El archivo supera {cfg.max_upload_bytes // (1024 * 1024)} MB.", "ARCHIVO_GRANDE")
    if not contenido:
        raise ApiError(422, "El archivo está vacío.", "ARCHIVO_VACIO")
    # El tipo se decide por la firma binaria, nunca por la extensión o el Content-Type del cliente.
    tipo = next((v for firma, v in FIRMAS.items() if contenido.startswith(firma)), None)
    if tipo is None:
        raise ApiError(415, "Solo se aceptan PDF, JPG o PNG.", "TIPO_ARCHIVO_NO_PERMITIDO")
    mime, ext = tipo
    sha = hashlib.sha256(contenido).hexdigest()
    relativa = Path(str(ticket.id)) / f"{uuid.uuid4().hex}{ext}"
    destino = cfg.upload_dir / relativa
    destino.parent.mkdir(parents=True, exist_ok=True)
    nombre = Path(archivo.filename or "documento").name[:200]
    s.add(
        DocumentoPqrs(
            ticket_id=ticket.id,
            tipo_documento=tipo_documento,
            nombre_original=nombre,
            ruta=str(relativa),
            mime=mime,
            tamano_bytes=len(contenido),
            sha256=sha,
        )
    )
    try:
        await s.flush()
    except IntegrityError as e:
        raise ApiError(409, "Ese mismo archivo ya fue adjuntado a este radicado.", "DOCUMENTO_DUPLICADO") from e
    destino.write_bytes(contenido)
    await s.refresh(ticket, ["documentos"])
    cargados = {d.tipo_documento.value for d in ticket.documentos}
    ticket.checklist = _checklist(ticket.tipo, ticket.tipo_averia, ticket.numero_guia, cargados)
    if ticket.estado is EstadoPqrs.INCOMPLETO and all(ticket.checklist.values()):
        ticket.estado = EstadoPqrs.RADICADO
    await s.flush()
    await s.refresh(ticket, ["actualizado_en"])
    return a_salida(ticket)
