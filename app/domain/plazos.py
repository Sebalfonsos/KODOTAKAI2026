"""Plazos en días hábiles de Colombia (sábados, domingos y festivos de `holidays.Colombia` no cuentan).

API (aceptan `date` o `datetime`; un datetime se reduce a su fecha local):
- `es_dia_habil(fecha) -> bool`
- `sumar_dias_habiles(fecha, n) -> date`: el n-ésimo día hábil DESPUÉS de `fecha` (n=0 -> la misma fecha).
- `dias_habiles_entre(a, b) -> int`: días hábiles d con a < d <= b (negativo si b < a).
- `evaluar_plazo_reclamo(tipo_averia, fecha_referencia, fecha_reclamo, anotada_en_guia=False)
  -> EvaluacionPlazo` (RF-PQRS-2). `fecha_referencia` es la fecha de entrega (aparente/oculta) o la
  fecha estimada de entrega (pérdida). Reglas del protocolo §3:
  - aparente: vigente solo si se anotó en la guía/POD al recibir; si no, presunción del Art. 1028.
  - oculta: hasta 3 días hábiles después de la entrega.
  - perdida (D-08): 5 días hábiles sin actualización -> EN_INVESTIGACION_SINIESTRO, y 10 hábiles más.
  Error: TIPO_AVERIA_INVALIDO.
- `fecha_limite_respuesta(fecha_radicado) -> date`: 15 días hábiles contados desde el día siguiente.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta

import holidays

from app.domain import ErrorDominio

_FESTIVOS = holidays.Colombia()  # se expande por año a demanda

PLAZO_OCULTA = 3
PLAZO_SIN_ACTUALIZACION = 5
PLAZO_RECLAMO_PERDIDA = 10
PLAZO_RESPUESTA_PQRS = 15

_ART_1028 = (
    "opera la presunción de entrega a satisfacción del Art. 1028 del Código de Comercio (protocolo DOC-PQRS-2026-04 §3)"
)


@dataclass(frozen=True)
class EvaluacionPlazo:
    vigente: bool
    fecha_limite: date
    dias_habiles_restantes: int | None
    fundamento: str
    fecha_investigacion_siniestro: date | None = None


def _fecha(valor: date) -> date:
    return valor.date() if isinstance(valor, datetime) else valor


def es_dia_habil(fecha: date) -> bool:
    fecha = _fecha(fecha)
    return fecha.weekday() < 5 and fecha not in _FESTIVOS


def sumar_dias_habiles(fecha: date, n: int) -> date:
    fecha = _fecha(fecha)
    while n > 0:
        fecha += timedelta(days=1)
        n -= es_dia_habil(fecha)
    return fecha


def dias_habiles_entre(a: date, b: date) -> int:
    a, b = _fecha(a), _fecha(b)
    if b < a:
        return -dias_habiles_entre(b, a)
    return sum(es_dia_habil(a + timedelta(days=i)) for i in range(1, (b - a).days + 1))


def fecha_limite_respuesta(fecha_radicado: date) -> date:
    return sumar_dias_habiles(fecha_radicado, PLAZO_RESPUESTA_PQRS)


def _restantes(reclamo: date, limite: date) -> int:
    return max(0, dias_habiles_entre(reclamo, limite))


def evaluar_plazo_reclamo(
    tipo_averia: str, fecha_referencia: date, fecha_reclamo: date, anotada_en_guia: bool = False
) -> EvaluacionPlazo:
    ref, reclamo = _fecha(fecha_referencia), _fecha(fecha_reclamo)

    if tipo_averia == "aparente":
        if anotada_en_guia:
            return EvaluacionPlazo(
                True, ref, None, "La avería aparente quedó anotada en la guía/POD al recibir; puedes radicar."
            )
        return EvaluacionPlazo(
            False,
            ref,
            None,
            f"La avería aparente debía anotarse en la guía/POD al momento de la entrega; {_ART_1028}.",
        )

    if tipo_averia == "oculta":
        limite = sumar_dias_habiles(ref, PLAZO_OCULTA)
        if reclamo <= limite:
            return EvaluacionPlazo(
                True,
                limite,
                _restantes(reclamo, limite),
                f"La avería oculta se puede radicar hasta {PLAZO_OCULTA} días hábiles después de la entrega.",
            )
        return EvaluacionPlazo(
            False,
            limite,
            0,
            f"Venció el plazo de {PLAZO_OCULTA} días hábiles siguientes a la entrega; {_ART_1028}.",
        )

    if tipo_averia == "perdida":
        investigacion = sumar_dias_habiles(ref, PLAZO_SIN_ACTUALIZACION)
        limite = sumar_dias_habiles(investigacion, PLAZO_RECLAMO_PERDIDA)
        if reclamo < investigacion:
            fundamento = (
                f"Aún no se cumplen {PLAZO_SIN_ACTUALIZACION} días hábiles sin actualización desde la fecha "
                "estimada de entrega; el envío pasará a investigación de siniestro el "
                f"{investigacion.isoformat()}."
            )
        elif reclamo <= limite:
            fundamento = (
                f"El envío está en investigación de siniestro; tienes {PLAZO_RECLAMO_PERDIDA} días hábiles "
                "para radicar la reclamación económica (protocolo DOC-PQRS-2026-04 §3)."
            )
        else:
            return EvaluacionPlazo(
                False,
                limite,
                0,
                f"Venció el plazo de {PLAZO_RECLAMO_PERDIDA} días hábiles para reclamar la pérdida "
                "(protocolo DOC-PQRS-2026-04 §3).",
                investigacion,
            )
        return EvaluacionPlazo(True, limite, _restantes(reclamo, limite), fundamento, investigacion)

    raise ErrorDominio("TIPO_AVERIA_INVALIDO", "El tipo de novedad debe ser aparente, oculta o pérdida.")
