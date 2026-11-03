"""Operación: cotizaciones, PQRS con documentos, idempotencia y auditoría."""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Sequence,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, ConCreacion, EstadoPqrs, TipoDocumento, TipoPqrs, pg_enum

seq_radicado = Sequence("pqrs_radicado_seq", metadata=Base.metadata)


class Cotizacion(ConCreacion, Base):
    __tablename__ = "cotizaciones"
    __table_args__ = (CheckConstraint("total > 0", name="total_positivo"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text("gen_random_uuid()"))
    trayecto_codigo: Mapped[str] = mapped_column(ForeignKey("trayectos.codigo"), index=True)
    usuario_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuarios.id", ondelete="SET NULL"), index=True)
    sesion_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("sesiones_chat.id", ondelete="SET NULL"))
    entrada: Mapped[dict] = mapped_column(JSONB)
    desglose: Mapped[dict] = mapped_column(JSONB)
    total: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    version_reglas: Mapped[str] = mapped_column(String(20))


class TicketPqrs(ConCreacion, Base):
    __tablename__ = "pqrs_tickets"
    __table_args__ = (
        CheckConstraint("valor_reclamado IS NULL OR valor_reclamado > 0", name="valor_positivo"),
        CheckConstraint("prioridad BETWEEN 1 AND 5", name="prioridad_rango"),
        CheckConstraint("char_length(descripcion) BETWEEN 10 AND 4000", name="descripcion_longitud"),
        Index("ix_pqrs_tickets_estado_creado", "estado", "creado_en"),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text("gen_random_uuid()"))
    radicado: Mapped[str] = mapped_column(
        String(20),
        unique=True,
        server_default=text(
            "'PQRS-' || to_char(now(), 'YYYY') || '-' || lpad(nextval('pqrs_radicado_seq')::text, 6, '0')"
        ),
    )
    tipo: Mapped[TipoPqrs] = mapped_column(pg_enum(TipoPqrs, "tipo_pqrs"))
    estado: Mapped[EstadoPqrs] = mapped_column(pg_enum(EstadoPqrs, "estado_pqrs"))
    usuario_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("usuarios.id"), index=True)
    numero_guia: Mapped[str | None] = mapped_column(ForeignKey("envios.numero_guia"), index=True)
    sesion_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("sesiones_chat.id", ondelete="SET NULL"))
    descripcion: Mapped[str] = mapped_column(Text)
    tipo_averia: Mapped[str | None] = mapped_column(String(20))
    valor_reclamado: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    fecha_limite_respuesta: Mapped[date] = mapped_column(Date)
    prioridad: Mapped[int] = mapped_column(SmallInteger, server_default="3")
    asignado_a: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuarios.id"))
    checklist: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    documentos: Mapped[list["DocumentoPqrs"]] = relationship(back_populates="ticket", cascade="all, delete-orphan")


class DocumentoPqrs(ConCreacion, Base):
    __tablename__ = "pqrs_documentos"
    __table_args__ = (
        UniqueConstraint("ticket_id", "sha256", name="uq_pqrs_documentos_ticket_sha"),
        CheckConstraint("tamano_bytes > 0 AND tamano_bytes <= 10485760", name="tamano_rango"),
        CheckConstraint("mime IN ('application/pdf', 'image/jpeg', 'image/png')", name="mime_permitido"),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text("gen_random_uuid()"))
    ticket_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pqrs_tickets.id", ondelete="CASCADE"), index=True)
    tipo_documento: Mapped[TipoDocumento] = mapped_column(pg_enum(TipoDocumento, "tipo_documento"))
    nombre_original: Mapped[str] = mapped_column(String(200))
    ruta: Mapped[str] = mapped_column(String(300), comment="Relativa a UPLOAD_DIR, fuera del webroot")
    mime: Mapped[str] = mapped_column(String(40))
    tamano_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))

    ticket: Mapped[TicketPqrs] = relationship(back_populates="documentos")


class Idempotencia(ConCreacion, Base):
    """Respuesta guardada por `Idempotency-Key` para que reintentos no dupliquen tickets ni cotizaciones."""

    __tablename__ = "idempotencia"
    clave: Mapped[str] = mapped_column(String(80), primary_key=True)
    endpoint: Mapped[str] = mapped_column(String(80), primary_key=True)
    sujeto: Mapped[str] = mapped_column(String(80), comment="usuario o IP que usó la clave")
    hash_cuerpo: Mapped[str] = mapped_column(String(64))
    status: Mapped[int] = mapped_column(SmallInteger)
    respuesta: Mapped[dict] = mapped_column(JSONB)


class Auditoria(Base):
    __tablename__ = "auditoria"
    __table_args__ = (Index("ix_auditoria_ocurrido", "ocurrido_en"),)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    usuario_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuarios.id", ondelete="SET NULL"), index=True)
    accion: Mapped[str] = mapped_column(String(60))
    entidad: Mapped[str] = mapped_column(String(60))
    entidad_id: Mapped[str | None] = mapped_column(String(80))
    detalle: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    ip: Mapped[str | None] = mapped_column(INET)
    ocurrido_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
