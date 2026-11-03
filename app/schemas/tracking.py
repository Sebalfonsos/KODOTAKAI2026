"""Esquemas de rastreo de guías (RF-TRK)."""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class EventoOut(BaseModel):
    ocurrido_en: datetime
    estado: str = Field(examples=["EN_TRANSITO"])
    estado_texto: str
    ubicacion: str
    descripcion: str = Field(description="Datos personales enmascarados")


class UbicacionOut(BaseModel):
    latitud: Decimal | None
    longitud: Decimal | None
    referencia: str | None


class DetalleEnvioOut(BaseModel):
    """Solo para el titular de la cuenta, asesores y administradores."""

    remitente: str | None
    destinatario: str | None
    direccion_entrega: str | None
    peso_facturable_kg: Decimal
    valor_declarado: Decimal
    unidades: int
    recibido_por: str | None = None
    documento_receptor: str | None = Field(default=None, examples=["C.C. **.**9.432"])
    observaciones_entrega: str | None = None


class TrackingOut(BaseModel):
    numero_guia: str = Field(examples=["TLX-984021-CO"])
    estado: str = Field(examples=["EN_TRANSITO"])
    estado_texto: str = Field(examples=["Tu envío va en camino hacia la ciudad de destino."])
    progreso_pct: int | None = Field(examples=[57])
    es_final: bool
    novedad: bool = Field(description="True si el envío está retenido o en investigación")
    servicio: str
    origen: str
    destino: str
    fecha_despacho: datetime
    fecha_estimada_entrega: datetime
    fecha_entrega_real: datetime | None
    ubicacion: UbicacionOut
    eventos: list[EventoOut]
    detalle: DetalleEnvioOut | None = Field(default=None, description="null para invitados o cuentas ajenas")
