"""Esquemas de cotización (RF-COT)."""

import uuid
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class CotizacionIn(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "origen": "Bogotá D.C.",
                    "destino": "Medellín",
                    "alto_cm": 40,
                    "ancho_cm": 50,
                    "largo_cm": 60,
                    "peso_kg": 45.5,
                    "valor_declarado": 12500000,
                    "modalidad": "carga",
                    "cadena_frio": True,
                    "mercancia_peligrosa": False,
                    "unidades": 2,
                    "contenido": "medicamentos refrigerados",
                }
            ]
        },
    )
    origen: str = Field(min_length=2, max_length=80)
    destino: str = Field(min_length=2, max_length=80)
    alto_cm: Decimal = Field(gt=0, le=1000, decimal_places=2)
    ancho_cm: Decimal = Field(gt=0, le=1000, decimal_places=2)
    largo_cm: Decimal = Field(gt=0, le=2000, decimal_places=2)
    peso_kg: Decimal = Field(gt=0, le=40000, decimal_places=2)
    valor_declarado: Decimal = Field(gt=0, le=10_000_000_000, decimal_places=2, description="COP")
    modalidad: Literal["paqueteria", "carga"] = "paqueteria"
    cadena_frio: bool = False
    mercancia_peligrosa: bool = False
    unidades: int = Field(default=1, ge=1, le=500)
    contenido: str | None = Field(
        default=None, max_length=200, description="Descripción del contenido: se valida contra la lista de prohibidos"
    )


class DesgloseOut(BaseModel):
    peso_real_kg: Decimal
    peso_volumetrico_kg: Decimal
    peso_facturable_kg: Decimal
    base_cobro: Literal["real", "volumetrico"]
    tarifa_aplicada_kg: Decimal
    flete_base: Decimal
    flete_minimo_aplicado: bool
    flete: Decimal
    recargo_cadena_frio: Decimal
    recargo_mercancia_peligrosa: Decimal
    seguro: Decimal
    total_sin_redondeo: Decimal


class CotizacionOut(BaseModel):
    id: uuid.UUID
    codigo_trayecto: str = Field(examples=["TLX-BOG-MED-001"])
    origen: str
    destino: str
    desglose: DesgloseOut
    total: Decimal = Field(description="COP redondeado a pesos (ROUND_HALF_UP)", examples=[207469])
    moneda: str = "COP"
    tiempo_estimado_horas: int
    observaciones: list[str]
    version_reglas: str = Field(examples=["2026.1"])
