"""Liquidación estimada de indemnizaciones (RF-PQRS-5, protocolo DOC-PQRS-2026-04 §5).

API:
- `liquidar_indemnizacion(valor_declarado, valor_factura, *, flete_cobrado=0,
  tipo_siniestro='averia_parcial', negligencia_demostrada=False) -> Liquidacion`
  - base = min(valor_declarado, valor_factura)
  - deducible = 5 % de la base si valor_declarado > $2.000.000
  - flete_devuelto = 100 % del flete solo si tipo_siniestro in {perdida_total, averia_total} y hay negligencia
  - total = base - deducible + flete_devuelto, redondeado a pesos (ROUND_HALF_UP)
  Es una estimación sujeta a aprobación en 15 días hábiles (ver plazos.fecha_limite_respuesta).
  Errores: VALOR_INVALIDO si algún valor es negativo o la base es 0.
"""

from dataclasses import dataclass
from decimal import Decimal

from app.domain import ErrorDominio, a_decimal, redondear_pesos

UMBRAL_DEDUCIBLE = Decimal("2000000")
PCT_DEDUCIBLE = Decimal("0.05")
SINIESTROS_CON_FLETE = {"perdida_total", "averia_total"}


@dataclass(frozen=True)
class Liquidacion:
    base: Decimal
    deducible: Decimal
    flete_devuelto: Decimal
    total: Decimal
    aplica_deducible: bool
    sujeto_aprobacion: bool = True


def liquidar_indemnizacion(
    valor_declarado,
    valor_factura,
    *,
    flete_cobrado=0,
    tipo_siniestro: str = "averia_parcial",
    negligencia_demostrada: bool = False,
) -> Liquidacion:
    vd, vf, flete = a_decimal(valor_declarado), a_decimal(valor_factura), a_decimal(flete_cobrado)
    if min(vd, vf, flete) < 0 or min(vd, vf) == 0:
        raise ErrorDominio("VALOR_INVALIDO", "El valor declarado y la factura deben ser mayores a cero.")
    base = min(vd, vf)
    aplica = vd > UMBRAL_DEDUCIBLE
    deducible = base * PCT_DEDUCIBLE if aplica else Decimal(0)
    devuelto = flete if tipo_siniestro in SINIESTROS_CON_FLETE and negligencia_demostrada else Decimal(0)
    return Liquidacion(
        base=base,
        deducible=deducible,
        flete_devuelto=devuelto,
        total=redondear_pesos(base - deducible + devuelto),
        aplica_deducible=aplica,
    )
