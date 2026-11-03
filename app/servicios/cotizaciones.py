"""Cotización: dominio determinista + persistencia (REST y chat comparten esta ruta)."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.core.security import Actor
from app.domain.cotizador import SolicitudCotizacion, buscar_municipio, buscar_trayecto, cotizar
from app.domain.mercancias import evaluar_producto
from app.models import Cotizacion
from app.schemas.cotizacion import CotizacionIn, CotizacionOut, DesgloseOut
from app.servicios.referencia import referencia

VERSION_REGLAS = "2026.1"  # D-01..D-06 adoptadas en docs/requisitos.md


async def cotizar_y_guardar(
    s: AsyncSession, datos: CotizacionIn, actor: Actor, sesion_id: uuid.UUID | None = None
) -> CotizacionOut:
    if datos.contenido:
        v = evaluar_producto(datos.contenido)
        if v.veredicto == "prohibido":
            raise ApiError(422, f"No podemos cotizar este envío: {v.motivo} ({v.fuente}).", "MERCANCIA_PROHIBIDA")
        if v.veredicto == "solo_ftl" and datos.modalidad == "paqueteria":
            raise ApiError(422, f"{v.producto}: solo se acepta en carga completa (FTL). {v.motivo}", "SOLO_FTL")
    trayectos, municipios = await referencia(s)
    trayecto = buscar_trayecto(trayectos, datos.origen, datos.destino)
    destino = buscar_municipio(municipios, datos.destino)
    c = cotizar(
        trayecto,
        destino,
        SolicitudCotizacion(
            alto_cm=datos.alto_cm,
            ancho_cm=datos.ancho_cm,
            largo_cm=datos.largo_cm,
            peso_kg=datos.peso_kg,
            valor_declarado=datos.valor_declarado,
            modalidad=datos.modalidad,
            cadena_frio=datos.cadena_frio,
            mercancia_peligrosa=datos.mercancia_peligrosa,
            unidades=datos.unidades,
        ),
    )
    desglose = DesgloseOut(
        peso_real_kg=c.peso_real,
        peso_volumetrico_kg=c.peso_volumetrico,
        peso_facturable_kg=c.peso_facturable,
        base_cobro=c.base_cobro,
        tarifa_aplicada_kg=c.tarifa_aplicada,
        flete_base=c.flete_base,
        flete_minimo_aplicado=c.flete_minimo_aplicado,
        flete=c.flete,
        recargo_cadena_frio=c.recargo_frio,
        recargo_mercancia_peligrosa=c.recargo_mp,
        seguro=c.seguro,
        total_sin_redondeo=c.total_sin_redondeo,
    )
    fila = Cotizacion(
        trayecto_codigo=c.codigo_trayecto,
        usuario_id=actor.id,
        sesion_id=sesion_id,
        entrada=datos.model_dump(mode="json"),
        desglose=desglose.model_dump(mode="json")
        | {"tiempo_estimado_horas": c.horas_estimadas, "observaciones": c.observaciones},
        total=c.total,
        version_reglas=VERSION_REGLAS,
    )
    s.add(fila)
    await s.flush()
    return CotizacionOut(
        id=fila.id,
        codigo_trayecto=c.codigo_trayecto,
        origen=trayecto.ciudad_origen,
        destino=trayecto.ciudad_destino,
        desglose=desglose,
        total=c.total,
        tiempo_estimado_horas=c.horas_estimadas,
        observaciones=c.observaciones,
        version_reglas=VERSION_REGLAS,
    )
