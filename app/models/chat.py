"""Chat: sesiones, mensajes con artifacts, criterios y cola de escalamientos, calificaciones."""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    SmallInteger,
    String,
    Text,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, Canal, ConCreacion, EstadoEscalamiento, EstadoSesion, RolMensaje, pg_enum


class SesionChat(ConCreacion, Base):
    __tablename__ = "sesiones_chat"
    __table_args__ = (Index("ix_sesiones_chat_estado_actividad", "estado", "ultima_actividad"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text("gen_random_uuid()"))
    usuario_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuarios.id", ondelete="SET NULL"), index=True)
    canal: Mapped[Canal] = mapped_column(pg_enum(Canal, "canal"), server_default=Canal.WEB.value)
    estado: Mapped[EstadoSesion] = mapped_column(pg_enum(EstadoSesion, "estado_sesion"), server_default="activa")
    ultima_actividad: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    contexto: Mapped[dict] = mapped_column(
        JSONB, server_default=text("'{}'::jsonb"), comment="Datos ya capturados (guía consultada, cotización a medias)"
    )
    resumen: Mapped[str | None] = mapped_column(Text)


class Mensaje(ConCreacion, Base):
    __tablename__ = "mensajes"
    __table_args__ = (
        CheckConstraint("confianza IS NULL OR (confianza >= 0 AND confianza <= 1)", name="confianza_rango"),
        Index("ix_mensajes_sesion_id", "sesion_id", "id"),
        Index("ix_mensajes_creado", "creado_en"),
        Index("ix_mensajes_intencion", "intencion"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    sesion_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sesiones_chat.id", ondelete="CASCADE"))
    turno_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    rol: Mapped[RolMensaje] = mapped_column(pg_enum(RolMensaje, "rol_mensaje"))
    autor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuarios.id", ondelete="SET NULL"))
    contenido: Mapped[str] = mapped_column(Text)
    artifacts: Mapped[list] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    intencion: Mapped[str | None] = mapped_column(String(40))
    confianza: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    latencias_ms: Mapped[dict | None] = mapped_column(JSONB)
    verificado: Mapped[bool | None] = mapped_column(comment="False si el verificador reemplazó la respuesta")


class CriterioEscalamiento(Base):
    __tablename__ = "criterios_escalamiento"
    id: Mapped[str] = mapped_column(String(10), primary_key=True)
    categoria: Mapped[str] = mapped_column(String(120))
    descripcion: Mapped[str] = mapped_column(Text)
    regla_evaluacion: Mapped[str | None] = mapped_column(Text)
    palabras_clave: Mapped[list[str] | None] = mapped_column(ARRAY(String(60)))
    accion: Mapped[str] = mapped_column(String(60))
    mensaje_cliente: Mapped[str] = mapped_column(Text)
    prioridad: Mapped[int] = mapped_column(SmallInteger, comment="1 = más urgente (D-13)")


class Escalamiento(Base):
    __tablename__ = "escalamientos"
    __table_args__ = (
        Index("ix_escalamientos_cola", "estado", "prioridad", "creado_en"),
        # Una sola escalada abierta por sesión.
        Index(
            "uq_escalamientos_sesion_abierta",
            "sesion_id",
            unique=True,
            postgresql_where=text("estado IN ('pendiente', 'tomado')"),
        ),
        CheckConstraint("estado <> 'tomado' OR asesor_id IS NOT NULL", name="tomado_con_asesor"),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text("gen_random_uuid()"))
    sesion_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sesiones_chat.id", ondelete="CASCADE"))
    criterio_id: Mapped[str] = mapped_column(ForeignKey("criterios_escalamiento.id"))
    prioridad: Mapped[int] = mapped_column(SmallInteger)
    estado: Mapped[EstadoEscalamiento] = mapped_column(
        pg_enum(EstadoEscalamiento, "estado_escalamiento"), server_default="pendiente"
    )
    asesor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuarios.id", ondelete="SET NULL"))
    resumen_ia: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    tomado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resuelto_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Calificacion(ConCreacion, Base):
    __tablename__ = "calificaciones"
    __table_args__ = (CheckConstraint("puntaje BETWEEN 1 AND 5", name="puntaje_rango"),)
    sesion_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sesiones_chat.id", ondelete="CASCADE"), primary_key=True)
    puntaje: Mapped[int] = mapped_column(SmallInteger)
    comentario: Mapped[str | None] = mapped_column(String(500))
