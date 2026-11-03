"""Datos de referencia (trayectos y municipios) convertidos a objetos del dominio, con caché por proceso."""

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.cotizador import MunicipioCobertura, Trayecto
from app.models import Municipio
from app.models import Trayecto as TrayectoOrm
from app.models.base import TipoCobertura

ETIQUETA_COBERTURA = {
    TipoCobertura.URBANA_PRINCIPAL: "Urbana Principal",
    TipoCobertura.FRONTERA: "Frontera",
    TipoCobertura.TRAYECTO_ESPECIAL: "Trayecto Especial",
    TipoCobertura.ZOMAC: "Zona ZOMAC",
}

# ponytail: 25 trayectos y 31 municipios caben en memoria; se invalida al recargar catálogos (seed/admin).
_cache: tuple[list[Trayecto], list[MunicipioCobertura]] | None = None


def invalidar() -> None:
    global _cache
    _cache = None


def a_municipio(m: Municipio) -> MunicipioCobertura:
    return MunicipioCobertura(
        codigo_dane=m.codigo_dane,
        municipio=m.nombre,
        departamento=m.departamento.nombre,
        tipo_cobertura=ETIQUETA_COBERTURA[m.tipo_cobertura],
        tiempo_entrega_estandar_horas=m.tiempo_entrega_estandar_horas,
        servicio_same_day_disponible=m.servicio_same_day,
        servicio_refrigerado_disponible=m.servicio_refrigerado,
        peso_maximo_paquete_kg=float(m.peso_maximo_paquete_kg),
        volumen_maximo_m3=float(m.volumen_maximo_m3),
        hub_operativo_asignado=m.hub.nombre,
        frecuencia_despacho=m.frecuencia_despacho,
        restricciones_operativas=m.restricciones_operativas,
    )


def a_trayecto(t: TrayectoOrm) -> Trayecto:
    return Trayecto(
        codigo_trayecto=t.codigo,
        ciudad_origen=t.origen.nombre,
        departamento_origen=t.origen.departamento.nombre,
        ciudad_destino=t.destino.nombre,
        departamento_destino=t.destino.departamento.nombre,
        tipo_cobertura=ETIQUETA_COBERTURA[t.tipo_cobertura],
        tarifa_base_kg_real_cop=t.tarifa_kg_real,
        tarifa_base_kg_volumetrico_cop=t.tarifa_kg_volumetrico,
        factor_divisitivas_volumetrico=Decimal(t.factor_volumetrico),
        flete_minimo_cop=t.flete_minimo,
        porcentaje_seguro=t.porcentaje_seguro,
        seguro_minimo_cop=t.seguro_minimo,
        recargo_cadena_frio_pct=t.recargo_cadena_frio_pct,
        recargo_mercancia_peligrosa_cop=t.recargo_mercancia_peligrosa,
        tiempo_entrega_estimado_horas=t.tiempo_entrega_horas,
        observaciones_ruta=t.observaciones,
    )


async def referencia(s: AsyncSession) -> tuple[list[Trayecto], list[MunicipioCobertura]]:
    global _cache
    if _cache is None:
        trayectos = [a_trayecto(t) for t in (await s.scalars(select(TrayectoOrm))).unique().all()]
        municipios = [a_municipio(m) for m in (await s.scalars(select(Municipio))).unique().all()]
        _cache = (trayectos, municipios)
    return _cache
