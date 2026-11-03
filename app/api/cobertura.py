"""Cobertura geográfica y opciones de origen/destino para formularios."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError, respuestas
from app.db import get_session
from app.domain.sanitizar import normalizar_para_busqueda
from app.models import Municipio, Trayecto
from app.schemas.catalogo import MunicipioOut, OpcionCiudad, Pagina

router = APIRouter(tags=["Cobertura"])


def _salida(m: Municipio) -> MunicipioOut:
    return MunicipioOut(
        codigo_dane=m.codigo_dane,
        nombre=m.nombre,
        departamento=m.departamento.nombre,
        tipo_cobertura=m.tipo_cobertura.value,
        tiempo_entrega_estandar_horas=m.tiempo_entrega_estandar_horas,
        servicio_same_day=m.servicio_same_day,
        servicio_refrigerado=m.servicio_refrigerado,
        peso_maximo_paquete_kg=m.peso_maximo_paquete_kg,
        volumen_maximo_m3=m.volumen_maximo_m3,
        hub=m.hub.nombre,
        frecuencia_despacho=m.frecuencia_despacho,
        restricciones_operativas=m.restricciones_operativas,
    )


@router.get(
    "/cobertura/municipios",
    response_model=Pagina[MunicipioOut],
    summary="Buscar municipios con cobertura",
    responses=respuestas(422),
)
async def listar_municipios(
    s: AsyncSession = Depends(get_session),
    q: Annotated[str | None, Query(max_length=60, description="Texto a buscar (sin importar tildes)")] = None,
    tipo_cobertura: Annotated[
        str | None, Query(pattern="^(urbana_principal|frontera|trayecto_especial|zomac)$")
    ] = None,
    pagina: Annotated[int, Query(ge=1)] = 1,
    tamano: Annotated[int, Query(ge=1, le=100)] = 20,
):
    # ponytail: el directorio tiene 31 municipios; filtrar en Python permite ignorar tildes sin la extensión unaccent.
    todos = (await s.scalars(select(Municipio).order_by(Municipio.nombre))).unique().all()
    clave = normalizar_para_busqueda(q) if q else ""
    filtrados = [
        m
        for m in todos
        if clave in normalizar_para_busqueda(f"{m.nombre} {m.departamento.nombre}")
        and (tipo_cobertura is None or m.tipo_cobertura.value == tipo_cobertura)
    ]
    inicio = (pagina - 1) * tamano
    return Pagina(
        items=[_salida(m) for m in filtrados[inicio : inicio + tamano]],
        total=len(filtrados),
        pagina=pagina,
        tamano=tamano,
    )


@router.get(
    "/cobertura/municipios/{codigo_dane}",
    response_model=MunicipioOut,
    summary="Ficha de cobertura de un municipio",
    responses=respuestas(404, 422),
)
async def ficha_municipio(
    codigo_dane: Annotated[str, Path(pattern=r"^\d{5}$")], s: AsyncSession = Depends(get_session)
):
    m = await s.get(Municipio, codigo_dane)
    if m is None:
        raise ApiError(404, f"No hay cobertura registrada para el código DANE {codigo_dane}.", "SIN_COBERTURA")
    return _salida(m)


@router.get("/trayectos/origenes", response_model=list[OpcionCiudad], summary="Ciudades de origen disponibles")
async def origenes(s: AsyncSession = Depends(get_session)):
    """Opciones para el campo `origen` del formulario de cotización."""
    filas = (
        (
            await s.scalars(
                select(Municipio)
                .where(Municipio.codigo_dane.in_(select(Trayecto.origen_dane)))
                .order_by(Municipio.nombre)
            )
        )
        .unique()
        .all()
    )
    return [
        OpcionCiudad(valor=m.nombre, etiqueta=f"{m.nombre} ({m.departamento.nombre})", codigo_dane=m.codigo_dane)
        for m in filas
    ]


@router.get(
    "/trayectos/destinos",
    response_model=list[OpcionCiudad],
    summary="Destinos disponibles desde un origen",
    responses=respuestas(404, 422),
)
async def destinos(
    origen: Annotated[str, Query(min_length=2, max_length=80, examples=["Bogotá D.C."])],
    s: AsyncSession = Depends(get_session),
):
    clave = normalizar_para_busqueda(origen)
    trayectos = (await s.scalars(select(Trayecto))).unique().all()
    validos = [t for t in trayectos if normalizar_para_busqueda(t.origen.nombre) in (clave, f"{clave} d c")]
    if not validos:
        raise ApiError(404, f"No tenemos rutas registradas desde {origen}.", "SIN_RUTAS_DESDE_ORIGEN")
    return sorted(
        (
            OpcionCiudad(
                valor=t.destino.nombre,
                etiqueta=f"{t.destino.nombre} ({t.destino.departamento.nombre})",
                codigo_dane=t.destino_dane,
                codigo_trayecto=t.codigo,
                tiempo_entrega_horas=t.tiempo_entrega_horas,
            )
            for t in validos
        ),
        key=lambda o: o.valor,
    )
