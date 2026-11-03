"""Consulta de envíos para rastreo (REST y chat), con control de acceso a datos personales."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import ApiError
from app.core.security import Actor
from app.domain.estados import traducir_estado
from app.domain.pii import enmascarar_texto
from app.models import Cuenta, Envio, Municipio
from app.models.base import Rol
from app.schemas.tracking import DetalleEnvioOut, EventoOut, TrackingOut, UbicacionOut

ESTADOS_NOVEDAD = {"RETENIDO_NOVEDAD", "EN_INVESTIGACION_SINIESTRO"}


def puede_ver_detalle(actor: Actor, envio: Envio) -> bool:
    if actor.rol in (Rol.ADMIN, Rol.ASESOR):
        return True
    return actor.cuenta_id is not None and actor.cuenta_id == envio.cuenta_id


async def cargar_envio(s: AsyncSession, guia: str) -> Envio:
    envio = await s.scalar(
        select(Envio)
        .where(Envio.numero_guia == guia)
        .options(selectinload(Envio.eventos), selectinload(Envio.prueba_entrega))
    )
    if envio is None:
        raise ApiError(
            404, f"No encontramos la guía {guia}. Revisa el número (formato TLX-XXXXXX-CO).", "GUIA_NO_ENCONTRADA"
        )
    return envio


async def tracking(s: AsyncSession, guia: str, actor: Actor) -> TrackingOut:
    envio = await cargar_envio(s, guia)
    municipios = {m.codigo_dane: m.nombre for m in (await s.scalars(select(Municipio))).unique().all()}
    estado = traducir_estado(envio.estado_actual)
    detalle = None
    if puede_ver_detalle(actor, envio):
        cuenta = await s.get(Cuenta, envio.cuenta_id) if envio.cuenta_id else None
        p = envio.prueba_entrega
        detalle = DetalleEnvioOut(
            remitente=cuenta.razon_social if cuenta else None,
            destinatario=envio.destinatario_empresa or envio.destinatario_nombre,
            direccion_entrega=envio.direccion_entrega,
            peso_facturable_kg=envio.peso_facturable_kg,
            valor_declarado=envio.valor_declarado,
            unidades=envio.unidades,
            recibido_por=p.recibido_por if p else None,
            documento_receptor=p.documento_enmascarado if p else None,
            observaciones_entrega=p.observaciones if p else None,
        )
    return TrackingOut(
        numero_guia=envio.numero_guia,
        estado=envio.estado_actual,
        estado_texto=estado.texto,
        progreso_pct=estado.progreso_pct,
        es_final=estado.es_final,
        novedad=envio.estado_actual in ESTADOS_NOVEDAD,
        servicio=envio.descripcion_servicio,
        origen=municipios.get(envio.origen_dane, envio.origen_dane),
        destino=municipios.get(envio.destino_dane, envio.destino_dane),
        fecha_despacho=envio.fecha_despacho,
        fecha_estimada_entrega=envio.fecha_estimada_entrega,
        fecha_entrega_real=envio.fecha_entrega_real,
        ubicacion=UbicacionOut(latitud=envio.latitud, longitud=envio.longitud, referencia=envio.referencia_ubicacion),
        eventos=[
            EventoOut(
                ocurrido_en=e.ocurrido_en,
                estado=e.estado,
                estado_texto=traducir_estado(e.estado).texto,
                ubicacion=e.ubicacion,
                # Ley 1581: teléfonos y cédulas dentro de descripciones nunca salen completos.
                descripcion=enmascarar_texto(e.descripcion),
            )
            for e in envio.eventos
        ],
        detalle=detalle,
    )
