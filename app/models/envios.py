"""Envíos (guías), su trazabilidad y prueba de entrega. Origen: dataset del reto o simulador."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Computed,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, ConCreacion, OrigenDato, TipoServicio, pg_enum

GUIA_REGEX = r"^TLX-[0-9]{6}-CO$"


class Envio(ConCreacion, Base):
    __tablename__ = "envios"
    __table_args__ = (
        CheckConstraint(f"numero_guia ~ '{GUIA_REGEX}'", name="guia_formato"),
        CheckConstraint("peso_kg > 0 AND alto_cm > 0 AND ancho_cm > 0 AND largo_cm > 0", name="medidas_positivas"),
        CheckConstraint("unidades > 0", name="unidades_positivas"),
        CheckConstraint("valor_declarado >= 0", name="valor_no_negativo"),
        CheckConstraint("fecha_estimada_entrega >= fecha_despacho", name="eta_posterior_despacho"),
        CheckConstraint("fecha_entrega_real IS NULL OR fecha_entrega_real >= fecha_despacho", name="entrega_posterior"),
        CheckConstraint("(latitud IS NULL) = (longitud IS NULL)", name="gps_completo"),
        CheckConstraint("NOT mercancia_peligrosa OR clase_onu IS NOT NULL", name="mp_requiere_clase"),
        Index("ix_envios_trayecto_despacho", "trayecto_codigo", "fecha_despacho"),
        Index("ix_envios_origen_despacho", "origen_dane", "fecha_despacho"),
    )
    numero_guia: Mapped[str] = mapped_column(String(13), primary_key=True)
    cuenta_id: Mapped[int | None] = mapped_column(ForeignKey("cuentas.id"), index=True)
    # D-04: dos guías del dataset no tienen trayecto en la matriz; origen/destino son obligatorios, trayecto no.
    trayecto_codigo: Mapped[str | None] = mapped_column(ForeignKey("trayectos.codigo"))
    origen_dane: Mapped[str] = mapped_column(ForeignKey("municipios.codigo_dane"))
    destino_dane: Mapped[str] = mapped_column(ForeignKey("municipios.codigo_dane"))
    direccion_recogida: Mapped[str | None] = mapped_column(String(200))
    destinatario_nombre: Mapped[str | None] = mapped_column(String(120))
    destinatario_empresa: Mapped[str | None] = mapped_column(String(160))
    direccion_entrega: Mapped[str | None] = mapped_column(String(200))
    tipo_servicio: Mapped[TipoServicio] = mapped_column(pg_enum(TipoServicio, "tipo_servicio"))
    descripcion_servicio: Mapped[str] = mapped_column(String(160))
    peso_kg: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    alto_cm: Mapped[Decimal] = mapped_column(Numeric(8, 2))
    ancho_cm: Mapped[Decimal] = mapped_column(Numeric(8, 2))
    largo_cm: Mapped[Decimal] = mapped_column(Numeric(8, 2))
    factor_volumetrico: Mapped[int] = mapped_column(SmallInteger, server_default="4000")
    peso_volumetrico_kg: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), Computed("round(alto_cm * ancho_cm * largo_cm / factor_volumetrico, 2)", persisted=True)
    )
    peso_facturable_kg: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        Computed("GREATEST(peso_kg, round(alto_cm * ancho_cm * largo_cm / factor_volumetrico, 2))", persisted=True),
    )
    unidades: Mapped[int] = mapped_column(SmallInteger, server_default="1")
    valor_declarado: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    requiere_refrigeracion: Mapped[bool] = mapped_column(server_default="false")
    mercancia_peligrosa: Mapped[bool] = mapped_column(server_default="false")
    clase_onu: Mapped[str | None] = mapped_column(ForeignKey("clases_onu.codigo"))
    estado_actual: Mapped[str] = mapped_column(ForeignKey("estados_envio.codigo"), index=True)
    latitud: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    longitud: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    referencia_ubicacion: Mapped[str | None] = mapped_column(String(200))
    fecha_despacho: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    fecha_estimada_entrega: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    fecha_entrega_real: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    origen_dato: Mapped[OrigenDato] = mapped_column(pg_enum(OrigenDato, "origen_dato"), index=True)

    eventos: Mapped[list["EventoEnvio"]] = relationship(
        back_populates="envio", order_by="EventoEnvio.ocurrido_en", cascade="all, delete-orphan"
    )
    prueba_entrega: Mapped["PruebaEntrega | None"] = relationship(cascade="all, delete-orphan")


class EventoEnvio(Base):
    __tablename__ = "eventos_envio"
    __table_args__ = (
        UniqueConstraint("numero_guia", "ocurrido_en", "estado", name="uq_eventos_envio_guia_ts_estado"),
        Index("ix_eventos_envio_guia_ts", "numero_guia", "ocurrido_en"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    numero_guia: Mapped[str] = mapped_column(ForeignKey("envios.numero_guia", ondelete="CASCADE"))
    ocurrido_en: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    estado: Mapped[str] = mapped_column(ForeignKey("estados_envio.codigo"))
    ubicacion: Mapped[str] = mapped_column(String(200))
    descripcion: Mapped[str] = mapped_column(Text)

    envio: Mapped[Envio] = relationship(back_populates="eventos")


class PruebaEntrega(Base):
    __tablename__ = "pruebas_entrega"
    numero_guia: Mapped[str] = mapped_column(ForeignKey("envios.numero_guia", ondelete="CASCADE"), primary_key=True)
    recibido_por: Mapped[str] = mapped_column(String(120))
    documento_enmascarado: Mapped[str] = mapped_column(String(40), comment="Ley 1581: nunca se guarda completo")
    fecha_hora_entrega: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    firma_url: Mapped[str | None] = mapped_column(String(300))
    observaciones: Mapped[str | None] = mapped_column(Text)
