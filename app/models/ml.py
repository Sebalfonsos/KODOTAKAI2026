"""Registro de modelos de ML (champion/challenger), corridas de entrenamiento y predicciones."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    LargeBinary,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, ConCreacion, EstadoModelo, pg_enum


class ModeloMl(ConCreacion, Base):
    __tablename__ = "ml_modelos"
    __table_args__ = (
        UniqueConstraint("nombre", "version", name="uq_ml_modelos_nombre_version"),
        Index("uq_ml_modelos_activo", "nombre", unique=True, postgresql_where=text("estado = 'activo'")),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(40))
    version: Mapped[int]
    algoritmo: Mapped[str] = mapped_column(String(80))
    metricas: Mapped[dict] = mapped_column(JSONB)
    features: Mapped[list] = mapped_column(JSONB)
    n_train: Mapped[int]
    entrenado_hasta: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    estado: Mapped[EstadoModelo] = mapped_column(pg_enum(EstadoModelo, "estado_modelo"))
    artefacto: Mapped[bytes] = mapped_column(LargeBinary)


class Entrenamiento(Base):
    __tablename__ = "ml_entrenamientos"
    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(40), index=True)
    motivo: Mapped[str] = mapped_column(String(20), comment="nuevos_datos | deriva | antiguedad | manual | inicial")
    resultado: Mapped[str] = mapped_column(String(20), server_default="en_curso")
    modelo_id: Mapped[int | None] = mapped_column(ForeignKey("ml_modelos.id", ondelete="SET NULL"))
    detalle: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    iniciado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    terminado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Prediccion(Base):
    __tablename__ = "ml_predicciones"
    __table_args__ = (
        UniqueConstraint("modelo_id", "numero_guia", name="uq_ml_predicciones_modelo_guia"),
        CheckConstraint("probabilidad >= 0 AND probabilidad <= 1", name="probabilidad_rango"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    modelo_id: Mapped[int] = mapped_column(ForeignKey("ml_modelos.id", ondelete="CASCADE"), index=True)
    numero_guia: Mapped[str] = mapped_column(ForeignKey("envios.numero_guia", ondelete="CASCADE"), index=True)
    probabilidad: Mapped[Decimal] = mapped_column(Numeric(5, 4))
    factores: Mapped[list] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    valor_real: Mapped[bool | None] = mapped_column(comment="Se llena al cerrar el envío: alimenta la deriva")
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
