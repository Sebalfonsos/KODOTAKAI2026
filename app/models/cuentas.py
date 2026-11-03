"""Cuentas de clientes, usuarios con rol y refresh tokens rotativos."""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Uuid, text
from sqlalchemy.dialects.postgresql import CITEXT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, ConCreacion, Rol, TipoCuenta, pg_enum


class Cuenta(ConCreacion, Base):
    __tablename__ = "cuentas"
    __table_args__ = (CheckConstraint("envios_mensuales >= 0", name="envios_no_negativos"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    nit: Mapped[str] = mapped_column(String(20), unique=True)
    razon_social: Mapped[str] = mapped_column(String(160))
    tipo_cuenta: Mapped[TipoCuenta] = mapped_column(
        pg_enum(TipoCuenta, "tipo_cuenta"), server_default=TipoCuenta.ESTANDAR.value
    )
    envios_mensuales: Mapped[int] = mapped_column(server_default="0")


class Usuario(ConCreacion, Base):
    __tablename__ = "usuarios"
    __table_args__ = (CheckConstraint("char_length(nombre) BETWEEN 2 AND 120", name="nombre_longitud"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text("gen_random_uuid()"))
    email: Mapped[str] = mapped_column(CITEXT, unique=True)
    nombre: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(200))
    rol: Mapped[Rol] = mapped_column(pg_enum(Rol, "rol_usuario"), index=True)
    cuenta_id: Mapped[int | None] = mapped_column(ForeignKey("cuentas.id", ondelete="SET NULL"), index=True)
    activo: Mapped[bool] = mapped_column(server_default="true")
    ultimo_login: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    cuenta: Mapped[Cuenta | None] = relationship(lazy="joined")


class RefreshToken(ConCreacion, Base):
    __tablename__ = "refresh_tokens"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text("gen_random_uuid()"))
    usuario_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("usuarios.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, comment="SHA-256 del token; nunca el token")
    familia: Mapped[uuid.UUID] = mapped_column(Uuid, index=True, comment="Detecta reutilización de tokens rotados")
    expira_en: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revocado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    usado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
