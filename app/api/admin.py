"""Administración REST: usuarios, métricas, conversaciones, envíos, PQRS, base de conocimiento y auditoría."""

import uuid
from dataclasses import asdict
from datetime import UTC, date, datetime, time, timedelta
from typing import Annotated, Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, File, Form, Path, Query, UploadFile, status
from sqlalchemy import Float, exists, func, select, true, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import rag
from app.api.asesor import detalle_sesion
from app.core.errors import ApiError, respuestas
from app.core.security import SoloAdmin, hash_password
from app.db import get_session
from app.domain.pii import enmascarar_nombre
from app.models import (
    Auditoria,
    Calificacion,
    Chunk,
    Documento,
    Envio,
    Escalamiento,
    Mensaje,
    RefreshToken,
    SesionChat,
    TicketPqrs,
    Usuario,
)
from app.models.base import EstadoPqrs, EstadoSesion, OrigenDato, Rol, RolMensaje, TipoPqrs
from app.schemas.admin import (
    AuditoriaOut,
    Conteo,
    ConversacionOut,
    DocumentoRagOut,
    EnvioAdminOut,
    IngestaOut,
    MetricasOut,
    PqrsAdminOut,
    PqrsPatchIn,
    ResultadoRagOut,
    SesionDetalleOut,
    UsuarioAdminOut,
    UsuarioCrearIn,
    UsuarioPatchIn,
)
from app.schemas.catalogo import Pagina
from app.servicios.auditoria import auditar

router = APIRouter(prefix="/admin", tags=["Administración"])
ZONA = ZoneInfo("America/Bogota")
PAGINA = Annotated[int, Query(ge=1)]
TAMANO = Annotated[int, Query(ge=1, le=100)]
TipoRag = Literal["mercancia_peligrosa", "embalaje", "prohibido", "pqrs", "cobertura", "trayecto", "politica", "legal"]
MAX_DOC_BYTES = 2 * 1024 * 1024
# radicado → en_revision → aprobado|rechazado → cerrado; incompleto → radicado solo con checklist completo.
TRANSICIONES_PQRS = {
    EstadoPqrs.INCOMPLETO: {EstadoPqrs.RADICADO},
    EstadoPqrs.RADICADO: {EstadoPqrs.EN_REVISION},
    EstadoPqrs.EN_REVISION: {EstadoPqrs.APROBADO, EstadoPqrs.RECHAZADO},
    EstadoPqrs.APROBADO: {EstadoPqrs.CERRADO},
    EstadoPqrs.RECHAZADO: {EstadoPqrs.CERRADO},
    EstadoPqrs.CERRADO: set(),
}


async def _paginar(s: AsyncSession, q, pagina: int, tamano: int) -> tuple[int, list]:
    total = await s.scalar(select(func.count()).select_from(q.order_by(None).subquery()))
    filas = (await s.execute(q.offset((pagina - 1) * tamano).limit(tamano))).all()
    return total, filas


# ----------------------------------------------------------------------------------------- usuarios


@router.get(
    "/usuarios", response_model=Pagina[UsuarioAdminOut], summary="Listar usuarios", responses=respuestas(401, 403, 422)
)
async def listar_usuarios(
    actor: SoloAdmin,
    rol: Rol | None = None,
    pagina: PAGINA = 1,
    tamano: TAMANO = 20,
    s: AsyncSession = Depends(get_session),
):
    q = select(Usuario).order_by(Usuario.creado_en, Usuario.email)
    if rol:
        q = q.where(Usuario.rol == rol)
    total, filas = await _paginar(s, q, pagina, tamano)
    return Pagina(
        items=[UsuarioAdminOut.model_validate(u) for (u,) in filas], total=total, pagina=pagina, tamano=tamano
    )


@router.post(
    "/usuarios",
    status_code=status.HTTP_201_CREATED,
    response_model=UsuarioAdminOut,
    summary="Crear un usuario (asesor, admin o cliente)",
    responses=respuestas(401, 403, 409, 422),
)
async def crear_usuario(datos: UsuarioCrearIn, actor: SoloAdmin, s: AsyncSession = Depends(get_session)):
    u = Usuario(
        email=datos.email.lower(),
        nombre=datos.nombre,
        password_hash=hash_password(datos.password),
        rol=datos.rol,
        cuenta_id=datos.cuenta_id,
    )
    s.add(u)
    try:
        await s.flush()
    except IntegrityError as e:
        raise ApiError(409, "Ya existe un usuario con ese correo o la cuenta no existe.", "EMAIL_DUPLICADO") from e
    auditar(s, actor, "usuario.crear", "usuario", str(u.id), rol=datos.rol.value)
    await s.commit()
    await s.refresh(u)
    return UsuarioAdminOut.model_validate(u)


@router.patch(
    "/usuarios/{usuario_id}",
    response_model=UsuarioAdminOut,
    summary="Cambiar rol, estado o nombre de un usuario",
    responses=respuestas(401, 403, 404, 409, 422),
)
async def editar_usuario(
    usuario_id: uuid.UUID, datos: UsuarioPatchIn, actor: SoloAdmin, s: AsyncSession = Depends(get_session)
):
    """Un admin no puede desactivarse ni quitarse el rol de admin a sí mismo (409). Desactivar revoca los
    refresh tokens del usuario; su access token vence en máximo 15 minutos."""
    # OF usuarios: la cuenta viene en LEFT JOIN (lazy="joined") y no se puede bloquear el lado nulo.
    u = await s.scalar(select(Usuario).where(Usuario.id == usuario_id).with_for_update(of=Usuario))
    if u is None:
        raise ApiError(404, "No existe el usuario indicado.", "USUARIO_NO_ENCONTRADO")
    cambios = datos.model_dump(exclude_none=True)
    if u.id == actor.id and (cambios.get("activo") is False or cambios.get("rol", Rol.ADMIN) is not Rol.ADMIN):
        raise ApiError(409, "No puedes desactivarte ni quitarte el rol de administrador.", "AUTO_MODIFICACION")
    for campo, valor in cambios.items():
        setattr(u, campo, " ".join(valor.split()) if campo == "nombre" else valor)
    if cambios.get("activo") is False:
        await s.execute(
            update(RefreshToken)
            .where(RefreshToken.usuario_id == u.id, RefreshToken.revocado_en.is_(None))
            .values(revocado_en=datetime.now(UTC))
        )
    auditar(s, actor, "usuario.editar", "usuario", str(u.id), **{k: str(v) for k, v in cambios.items()})
    await s.commit()
    await s.refresh(u)
    return UsuarioAdminOut.model_validate(u)


# ----------------------------------------------------------------------------------------- métricas


def _conteos(filas) -> list[Conteo]:
    return [Conteo(clave=str(getattr(k, "value", k)), total=n) for k, n in filas]


@router.get(
    "/metricas", response_model=MetricasOut, summary="Indicadores del agente", responses=respuestas(401, 403, 422)
)
async def metricas(
    actor: SoloAdmin,
    desde: date | None = None,
    hasta: date | None = None,
    s: AsyncSession = Depends(get_session),
):
    """Agregados en SQL sobre el periodo [desde, hasta] en hora de Colombia (por defecto, los últimos 7 días)."""
    hasta = hasta or datetime.now(ZONA).date()
    desde = desde or hasta - timedelta(days=6)
    if desde > hasta:
        raise ApiError(422, "`desde` no puede ser posterior a `hasta`.", "RANGO_INVALIDO")
    ini, fin = datetime.combine(desde, time.min, ZONA), datetime.combine(hasta + timedelta(days=1), time.min, ZONA)

    def rango(col):
        return (col >= ini) & (col < fin)

    interacciones = await s.scalar(
        select(func.count()).where(Mensaje.rol == RolMensaje.USUARIO, rango(Mensaje.creado_en))
    )
    escalada = exists().where(Escalamiento.sesion_id == SesionChat.id)
    sesiones, escaladas = (
        await s.execute(select(func.count(), func.count().filter(escalada)).where(rango(SesionChat.creado_en)))
    ).one()
    por_criterio = (
        await s.execute(
            select(Escalamiento.criterio_id, func.count())
            .where(rango(Escalamiento.creado_en))
            .group_by(Escalamiento.criterio_id)
            .order_by(Escalamiento.criterio_id)
        )
    ).all()
    intenciones = (
        await s.execute(
            select(Mensaje.intencion, func.count().label("n"))
            .where(Mensaje.intencion.is_not(None), rango(Mensaje.creado_en))
            .group_by(Mensaje.intencion)
            .order_by(func.count().desc(), Mensaje.intencion)
            .limit(10)
        )
    ).all()
    latencia = Mensaje.latencias_ms["total"].astext.cast(Float)
    confianza, p50, p95 = (
        await s.execute(
            select(
                func.avg(Mensaje.confianza),
                func.percentile_cont(0.5).within_group(latencia),
                func.percentile_cont(0.95).within_group(latencia),
            ).where(Mensaje.rol == RolMensaje.ASISTENTE, rango(Mensaje.creado_en))
        )
    ).one()
    csat, n_calif = (
        await s.execute(select(func.avg(Calificacion.puntaje), func.count()).where(rango(Calificacion.creado_en)))
    ).one()
    pqrs = (
        await s.execute(
            select(TicketPqrs.estado, func.count())
            .where(rango(TicketPqrs.creado_en))
            .group_by(TicketPqrs.estado)
            .order_by(TicketPqrs.estado)
        )
    ).all()
    envios = (
        await s.execute(
            select(Envio.estado_actual, func.count()).group_by(Envio.estado_actual).order_by(Envio.estado_actual)
        )
    ).all()

    def redondo(v, n=3):
        return round(float(v), n) if v is not None else None

    return MetricasOut(
        desde=desde,
        hasta=hasta,
        interacciones=interacciones,
        sesiones=sesiones,
        sesiones_escaladas=escaladas,
        pct_resuelto_sin_humano=round((sesiones - escaladas) * 100 / sesiones, 2) if sesiones else None,
        escalamientos_por_criterio=_conteos(por_criterio),
        intenciones_top=_conteos(intenciones),
        confianza_media=redondo(confianza),
        latencia_p50_ms=redondo(p50, 1),
        latencia_p95_ms=redondo(p95, 1),
        csat_promedio=redondo(csat, 2),
        calificaciones=n_calif,
        pqrs_por_estado=_conteos(pqrs),
        envios_por_estado=_conteos(envios),
    )


# ----------------------------------------------------------------------------------------- conversaciones


@router.get(
    "/conversaciones",
    response_model=Pagina[ConversacionOut],
    summary="Listar conversaciones",
    responses=respuestas(401, 403, 422),
)
async def listar_conversaciones(
    actor: SoloAdmin,
    estado: EstadoSesion | None = None,
    intencion: Annotated[str | None, Query(max_length=40)] = None,
    pagina: PAGINA = 1,
    tamano: TAMANO = 20,
    s: AsyncSession = Depends(get_session),
):
    """Más recientes primero; `intencion` filtra sesiones con al menos un mensaje de esa intención."""
    n_mensajes = select(func.count()).where(Mensaje.sesion_id == SesionChat.id).scalar_subquery()
    ultimo = (
        select(Mensaje.contenido, Mensaje.creado_en)
        .where(Mensaje.sesion_id == SesionChat.id)
        .order_by(Mensaje.id.desc())
        .limit(1)
        .lateral()
    )
    escalada = exists().where(Escalamiento.sesion_id == SesionChat.id)
    q = (
        select(SesionChat, n_mensajes, escalada, ultimo.c.contenido, ultimo.c.creado_en)
        .outerjoin(ultimo, true())
        .order_by(SesionChat.ultima_actividad.desc())
    )
    if estado:
        q = q.where(SesionChat.estado == estado)
    if intencion:
        q = q.where(exists().where(Mensaje.sesion_id == SesionChat.id, Mensaje.intencion == intencion))
    total, filas = await _paginar(s, q, pagina, tamano)
    items = [
        ConversacionOut(
            id=c.id,
            estado=c.estado,
            canal=c.canal,
            usuario_id=c.usuario_id,
            creado_en=c.creado_en,
            ultima_actividad=c.ultima_actividad,
            mensajes=n,
            escalada=esc,
            ultimo_mensaje=texto[:200] if texto else None,
            ultimo_mensaje_en=en,
        )
        for c, n, esc, texto, en in filas
    ]
    return Pagina(items=items, total=total, pagina=pagina, tamano=tamano)


@router.get(
    "/conversaciones/{sesion_id}",
    response_model=SesionDetalleOut,
    summary="Ver una conversación completa",
    responses=respuestas(401, 403, 404, 422),
)
async def ver_conversacion(sesion_id: uuid.UUID, actor: SoloAdmin, s: AsyncSession = Depends(get_session)):
    return await detalle_sesion(s, sesion_id)


# ----------------------------------------------------------------------------------------- envíos


@router.get(
    "/envios",
    response_model=Pagina[EnvioAdminOut],
    summary="Listar envíos (datos personales enmascarados)",
    responses=respuestas(401, 403, 422),
)
async def listar_envios(
    actor: SoloAdmin,
    estado: Annotated[str | None, Query(max_length=40, examples=["EN_TRANSITO"])] = None,
    origen_dato: OrigenDato | None = None,
    pagina: PAGINA = 1,
    tamano: TAMANO = 20,
    s: AsyncSession = Depends(get_session),
):
    q = select(Envio).order_by(Envio.fecha_despacho.desc(), Envio.numero_guia)
    if estado:
        q = q.where(Envio.estado_actual == estado)
    if origen_dato:
        q = q.where(Envio.origen_dato == origen_dato)
    total, filas = await _paginar(s, q, pagina, tamano)
    items = [
        EnvioAdminOut(
            numero_guia=e.numero_guia,
            estado_actual=e.estado_actual,
            origen_dato=e.origen_dato,
            tipo_servicio=e.tipo_servicio,
            origen_dane=e.origen_dane,
            destino_dane=e.destino_dane,
            trayecto_codigo=e.trayecto_codigo,
            destinatario=enmascarar_nombre(e.destinatario_nombre) if e.destinatario_nombre else None,
            peso_facturable_kg=e.peso_facturable_kg,
            valor_declarado=e.valor_declarado,
            mercancia_peligrosa=e.mercancia_peligrosa,
            requiere_refrigeracion=e.requiere_refrigeracion,
            fecha_despacho=e.fecha_despacho,
            fecha_estimada_entrega=e.fecha_estimada_entrega,
            fecha_entrega_real=e.fecha_entrega_real,
        )
        for (e,) in filas
    ]
    return Pagina(items=items, total=total, pagina=pagina, tamano=tamano)


# ----------------------------------------------------------------------------------------- PQRS


@router.get("/pqrs", response_model=Pagina[PqrsAdminOut], summary="Listar PQRS", responses=respuestas(401, 403, 422))
async def listar_pqrs(
    actor: SoloAdmin,
    estado: EstadoPqrs | None = None,
    tipo: TipoPqrs | None = None,
    pagina: PAGINA = 1,
    tamano: TAMANO = 20,
    s: AsyncSession = Depends(get_session),
):
    """Ordenadas por prioridad (1 = escalada) y fecha límite de respuesta."""
    q = select(TicketPqrs).order_by(TicketPqrs.prioridad, TicketPqrs.fecha_limite_respuesta, TicketPqrs.creado_en)
    if estado:
        q = q.where(TicketPqrs.estado == estado)
    if tipo:
        q = q.where(TicketPqrs.tipo == tipo)
    total, filas = await _paginar(s, q, pagina, tamano)
    return Pagina(items=[PqrsAdminOut.model_validate(t) for (t,) in filas], total=total, pagina=pagina, tamano=tamano)


@router.patch(
    "/pqrs/{radicado}",
    response_model=PqrsAdminOut,
    summary="Cambiar estado o asignación de una PQRS",
    responses=respuestas(401, 403, 404, 409, 422),
)
async def editar_pqrs(
    radicado: Annotated[str, Path(pattern=r"^PQRS-\d{4}-\d{6}$", examples=["PQRS-2026-000001"])],
    datos: PqrsPatchIn,
    actor: SoloAdmin,
    s: AsyncSession = Depends(get_session),
):
    """Transiciones válidas: radicado → en_revision → aprobado | rechazado → cerrado; incompleto → radicado solo
    con el checklist completo. Otra transición responde 409 TRANSICION_INVALIDA."""
    if datos.estado is None and datos.asignado_a is None:
        raise ApiError(422, "Indica `estado` o `asignado_a`.", "SIN_CAMBIOS")
    t = await s.scalar(select(TicketPqrs).where(TicketPqrs.radicado == radicado).with_for_update())
    if t is None:
        raise ApiError(404, f"No encontramos el radicado {radicado}.", "RADICADO_NO_ENCONTRADO")
    cambios: dict[str, str] = {}
    if datos.estado is not None and datos.estado is not t.estado:
        if datos.estado not in TRANSICIONES_PQRS[t.estado]:
            raise ApiError(409, f"No se puede pasar de {t.estado.value} a {datos.estado.value}.", "TRANSICION_INVALIDA")
        if t.estado is EstadoPqrs.INCOMPLETO and not all((t.checklist or {}).values()):
            raise ApiError(409, "El checklist documental está incompleto.", "CHECKLIST_INCOMPLETO")
        cambios["estado"] = f"{t.estado.value}->{datos.estado.value}"
        t.estado = datos.estado
    if datos.asignado_a is not None:
        rol = await s.scalar(select(Usuario.rol).where(Usuario.id == datos.asignado_a, Usuario.activo))
        if rol not in (Rol.ASESOR, Rol.ADMIN):
            raise ApiError(422, "Solo se puede asignar a un asesor o administrador activo.", "ASIGNADO_INVALIDO")
        t.asignado_a = datos.asignado_a
        cambios["asignado_a"] = str(datos.asignado_a)
    if cambios:
        auditar(s, actor, "pqrs.editar", "pqrs", radicado, **cambios)
        await s.flush()
        await s.refresh(t, ["actualizado_en"])
    out = PqrsAdminOut.model_validate(t)
    await s.commit()
    return out


# ----------------------------------------------------------------------------------------- RAG


@router.get(
    "/rag/documentos",
    response_model=list[DocumentoRagOut],
    summary="Documentos de la base de conocimiento",
    responses=respuestas(401, 403),
)
async def listar_documentos(actor: SoloAdmin, s: AsyncSession = Depends(get_session)):
    filas = (
        await s.execute(
            select(Documento, func.count(Chunk.id)).outerjoin(Chunk).group_by(Documento.id).order_by(Documento.codigo)
        )
    ).all()
    return [
        DocumentoRagOut(
            id=d.id,
            codigo=d.codigo,
            titulo=d.titulo,
            tipo=d.tipo,
            fuente=d.fuente,
            activo=d.activo,
            chunks=n,
            creado_en=d.creado_en,
        )
        for d, n in filas
    ]


@router.post(
    "/rag/documentos",
    status_code=status.HTTP_201_CREATED,
    response_model=IngestaOut,
    summary="Subir o actualizar un documento (.md o .txt, máx. 2 MB)",
    responses=respuestas(401, 403, 409, 413, 415, 422, 503),
)
async def subir_documento(
    actor: SoloAdmin,
    codigo: Annotated[str, Form(pattern=r"^[A-Z0-9][A-Z0-9-]{2,39}$", examples=["DOC-OPS-2026-05"])],
    titulo: Annotated[str, Form(min_length=3, max_length=200)],
    tipo: Annotated[TipoRag, Form()],
    archivo: Annotated[UploadFile, File(description="Markdown o texto plano en UTF-8")],
    s: AsyncSession = Depends(get_session),
):
    """Se divide por encabezados `##`/`###` (ventanas de 512 tokens con solape de 64) y se embebe con bge-m3.
    Un código existente se reemplaza si el contenido cambió; si es idéntico, no se re-embebe (`omitido`).
    Subir de nuevo un documento desactivado lo reactiva."""
    nombre = (archivo.filename or "").lower()
    if not nombre.endswith((".md", ".txt")):
        raise ApiError(415, "Solo se aceptan archivos .md o .txt.", "TIPO_ARCHIVO_NO_PERMITIDO")
    contenido = await archivo.read(MAX_DOC_BYTES + 1)
    if len(contenido) > MAX_DOC_BYTES:
        raise ApiError(413, "El documento supera 2 MB.", "ARCHIVO_GRANDE")
    try:
        texto = contenido.decode("utf-8").lstrip("﻿")
    except UnicodeDecodeError as e:
        raise ApiError(422, "El archivo debe estar codificado en UTF-8.", "CODIFICACION_INVALIDA") from e
    if not texto.strip():
        raise ApiError(422, "El archivo está vacío.", "ARCHIVO_VACIO")
    if not rag.dividir_markdown(texto):
        # Texto plano o markdown sin `##`: todo el contenido pasa a una sección con el título.
        texto = f"## {titulo}\n{texto}"
    try:
        r = await rag.ingestar_documento(s, codigo, titulo, tipo, texto, fuente=archivo.filename[:200])
    except IntegrityError as e:
        raise ApiError(409, "Ese contenido ya está indexado con otro código.", "CONTENIDO_DUPLICADO") from e
    await s.execute(update(Documento).where(Documento.codigo == codigo).values(activo=True))
    auditar(s, actor, "rag.ingestar", "documento", codigo, chunks=r["chunks"], omitido=r["omitido"])
    await s.commit()
    return IngestaOut(**r)


@router.delete(
    "/rag/documentos/{documento_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Desactivar un documento de la base de conocimiento",
    responses=respuestas(401, 403, 404, 422),
)
async def desactivar_documento(documento_id: int, actor: SoloAdmin, s: AsyncSession = Depends(get_session)):
    """Borrado lógico (`activo=false`): sus chunks quedan fuera de la búsqueda pero se conservan para auditoría.
    Para volver a activarlo, súbelo de nuevo."""
    d = await s.get(Documento, documento_id)
    if d is None:
        raise ApiError(404, "No existe el documento indicado.", "DOCUMENTO_NO_ENCONTRADO")
    d.activo = False
    auditar(s, actor, "rag.desactivar", "documento", d.codigo)
    await s.commit()


@router.get(
    "/rag/buscar",
    response_model=list[ResultadoRagOut],
    summary="Probar la búsqueda RAG (depuración)",
    responses=respuestas(401, 403, 422, 503),
)
async def probar_busqueda(
    actor: SoloAdmin,
    q: Annotated[str, Query(min_length=2, max_length=500, examples=["¿llegan a Quibdó?"])],
    k: Annotated[int, Query(ge=1, le=20)] = 4,
    tipos: Annotated[list[TipoRag] | None, Query()] = None,
    s: AsyncSession = Depends(get_session),
):
    """Devuelve los chunks con sus puntajes (coseno, texto y RRF) tal como los ve el orquestador."""
    return [ResultadoRagOut(**asdict(r)) for r in await rag.buscar(s, q, k=k, tipos=tipos)]


# ----------------------------------------------------------------------------------------- auditoría


@router.get(
    "/auditoria",
    response_model=Pagina[AuditoriaOut],
    summary="Registro de auditoría",
    responses=respuestas(401, 403, 422),
)
async def listar_auditoria(
    actor: SoloAdmin,
    entidad: Annotated[str | None, Query(max_length=60)] = None,
    accion: Annotated[str | None, Query(max_length=60)] = None,
    pagina: PAGINA = 1,
    tamano: TAMANO = 50,
    s: AsyncSession = Depends(get_session),
):
    q = select(Auditoria).order_by(Auditoria.id.desc())
    if entidad:
        q = q.where(Auditoria.entidad == entidad)
    if accion:
        q = q.where(Auditoria.accion == accion)
    total, filas = await _paginar(s, q, pagina, tamano)
    return Pagina(items=[AuditoriaOut.model_validate(a) for (a,) in filas], total=total, pagina=pagina, tamano=tamano)
