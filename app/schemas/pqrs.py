"""Esquemas de PQRS, plazos e indemnizaciones (RF-PQRS)."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.base import EstadoPqrs, TipoDocumento, TipoPqrs

GUIA = r"^TLX-[0-9]{6}-CO$"


class TicketIn(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "tipo": "S",
                    "numero_guia": "TLX-551904-CO",
                    "descripcion": "La caja llegó aplastada y el producto interno está roto.",
                    "tipo_averia": "oculta",
                    "valor_reclamado": 450000,
                }
            ]
        },
    )
    tipo: TipoPqrs
    numero_guia: str | None = Field(default=None, pattern=GUIA)
    descripcion: str = Field(min_length=10, max_length=4000)
    tipo_averia: Literal["aparente", "oculta", "perdida"] | None = None
    anotada_en_guia: bool = False
    valor_reclamado: Decimal | None = Field(default=None, gt=0, le=10_000_000_000, decimal_places=2)


class DocumentoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    tipo_documento: TipoDocumento
    nombre_original: str
    mime: str
    tamano_bytes: int
    sha256: str
    creado_en: datetime


class TicketOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    radicado: str = Field(examples=["PQRS-2026-000001"])
    tipo: TipoPqrs
    estado: EstadoPqrs
    numero_guia: str | None
    descripcion: str
    tipo_averia: str | None
    valor_reclamado: Decimal | None
    fecha_limite_respuesta: date
    prioridad: int
    checklist: dict
    escalado: bool = False
    creado_en: datetime
    documentos: list[DocumentoOut] = []


class PlazoOut(BaseModel):
    numero_guia: str
    tipo_averia: Literal["aparente", "oculta", "perdida"]
    fecha_referencia: date
    vigente: bool
    fecha_limite: date | None
    dias_habiles_restantes: int | None
    fundamento: str


class LiquidacionIn(BaseModel):
    model_config = ConfigDict(
        extra="forbid", json_schema_extra={"examples": [{"valor_declarado": 3000000, "valor_factura": 2800000}]}
    )
    valor_declarado: Decimal = Field(gt=0, decimal_places=2)
    valor_factura: Decimal = Field(gt=0, decimal_places=2)
    flete_cobrado: Decimal = Field(default=Decimal(0), ge=0, decimal_places=2)
    tipo_siniestro: Literal["averia_parcial", "perdida_total", "averia_total"] = "averia_parcial"
    negligencia_demostrada: bool = False


class LiquidacionOut(BaseModel):
    base: Decimal
    deducible: Decimal
    flete_devuelto: Decimal
    total: Decimal = Field(examples=[2660000])
    aplica_deducible: bool
    sujeto_aprobacion: bool = True
    nota: str = "Estimación sujeta a revisión documental; respuesta formal en 15 días hábiles."
