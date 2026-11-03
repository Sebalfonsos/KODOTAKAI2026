"""Traducción de estados técnicos del TMS a lenguaje de cliente (RF-TRK-3).

API:
- `traducir_estado(codigo) -> EstadoCliente`: texto amable, `orden` (1..7 en el camino normal,
  None en estados de excepción), `progreso_pct` (0..100 o None), `es_final` y `conocido`.
  Un estado desconocido devuelve un texto genérico, `conocido=False`, y registra un aviso.
"""

import logging
from dataclasses import dataclass

_log = logging.getLogger(__name__)

_PASOS = 7  # SOLICITUD_GENERADA .. ENTREGADO


@dataclass(frozen=True)
class EstadoCliente:
    codigo: str
    texto: str
    orden: int | None
    progreso_pct: int | None
    es_final: bool
    conocido: bool = True


# codigo -> (orden, texto). Orden None = estado de excepción fuera del camino normal.
_ESTADOS: dict[str, tuple[int | None, str]] = {
    "SOLICITUD_GENERADA": (1, "Recibimos tu solicitud y la guía ya fue generada. Pronto recogemos tu envío."),
    "RECOGIDO_EN_ORIGEN": (2, "Ya recogimos tu envío en el punto de origen."),
    "EN_BODEGA_ORIGEN": (3, "Tu envío está en nuestra bodega de origen, preparándose para el despacho."),
    # Redacción tomada del dosier §4.3.
    "RELECTURA_HUB_FONTIBON": (
        3,
        "Tu paquete ya ingresó a nuestro centro principal de clasificación en Bogotá y se encuentra "
        "programado para salir en la ruta nocturna hacia tu ciudad.",
    ),
    "EN_TRANSITO": (4, "Tu envío va en camino hacia la ciudad de destino."),
    "EN_BODEGA_DESTINO": (5, "Tu envío llegó a nuestra bodega en la ciudad de destino."),
    "EN_REPARTO": (6, "Tu envío salió a reparto y hoy lo entregamos en la dirección de destino."),
    "ENTREGADO": (7, "Tu envío fue entregado."),
    "RETENIDO_NOVEDAD": (
        None,
        "Tu envío está detenido temporalmente por una novedad operativa. Te contamos el detalle abajo.",
    ),
    # Protocolo PQRS §3: 5 días hábiles sin actualización tras la fecha estimada.
    "EN_INVESTIGACION_SINIESTRO": (
        None,
        "Tu envío está en investigación porque no ha tenido actualización de trazabilidad después de la "
        "fecha estimada de entrega. Puedes radicar tu reclamación dentro de los 10 días hábiles siguientes.",
    ),
}

_GENERICO = "Tu envío tiene una actualización de estado. Un asesor puede darte más detalle si lo necesitas."


def traducir_estado(codigo: str) -> EstadoCliente:
    if codigo not in _ESTADOS:
        _log.warning("estado_tms_desconocido", extra={"estado": codigo})
        return EstadoCliente(codigo, _GENERICO, None, None, es_final=False, conocido=False)
    orden, texto = _ESTADOS[codigo]
    progreso = round(orden * 100 / _PASOS) if orden else None
    return EstadoCliente(codigo, texto, orden, progreso, es_final=codigo == "ENTREGADO")
