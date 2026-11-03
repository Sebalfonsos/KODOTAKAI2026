"""Base declarativa, convención de nombres de restricciones y enums nativos de PostgreSQL."""

import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, MetaData, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Nombres deterministas para que Alembic genere migraciones estables.
CONVENCION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=CONVENCION)


class ConCreacion:
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


def pg_enum(cls: type[enum.Enum], nombre: str) -> Enum:
    """Enum nativo de PostgreSQL que guarda el `value` (no el nombre del miembro)."""
    return Enum(cls, name=nombre, values_callable=lambda e: [m.value for m in e], validate_strings=True)


class TipoCobertura(enum.StrEnum):
    URBANA_PRINCIPAL = "urbana_principal"
    FRONTERA = "frontera"
    TRAYECTO_ESPECIAL = "trayecto_especial"
    ZOMAC = "zomac"  # D-07: "Zona ZOMAC" y "Zona ZOMAC / Difícil Acceso" se normalizan aquí


class TipoCuenta(enum.StrEnum):
    ESTANDAR = "ESTANDAR"
    CORPORATIVO = "CORPORATIVO"
    CORPORATIVO_GOLD = "CORPORATIVO_GOLD"


class Rol(enum.StrEnum):
    CLIENTE = "cliente"
    ASESOR = "asesor"
    ADMIN = "admin"


class OrigenDato(enum.StrEnum):
    DATASET = "dataset"
    SIMULADO = "simulado"
    SISTEMA = "sistema"


class TipoServicio(enum.StrEnum):
    PAQUETERIA = "paqueteria"
    CARGA_MASIVA = "carga_masiva"
    CARGA_SEMIMASIVA = "carga_semimasiva"
    CADENA_FRIO = "cadena_frio"
    MERCANCIA_PELIGROSA = "mercancia_peligrosa"


class TipoPqrs(enum.StrEnum):
    PETICION = "P"
    QUEJA = "Q"
    RECLAMO = "R"
    SINIESTRO = "S"


class EstadoPqrs(enum.StrEnum):
    INCOMPLETO = "incompleto"
    RADICADO = "radicado"
    EN_REVISION = "en_revision"
    APROBADO = "aprobado"
    RECHAZADO = "rechazado"
    CERRADO = "cerrado"


class TipoDocumento(enum.StrEnum):
    GUIA = "guia"
    FACTURA = "factura"
    CARTA_RECLAMACION = "carta_reclamacion"
    CERTIFICACION_BANCARIA = "certificacion_bancaria"
    FOTO_EMPAQUE = "foto_empaque"
    FOTO_DANO = "foto_dano"
    FOTO_AMORTIGUACION = "foto_amortiguacion"
    DOCUMENTO_IDENTIDAD = "documento_identidad"
    ACTA_SALVEDAD = "acta_salvedad"
    OTRO = "otro"


class PoliticaMercancia(enum.StrEnum):
    PERMITIDO = "permitido"
    RESTRINGIDO = "restringido"
    SOLO_FTL = "solo_ftl"
    PROHIBIDO = "prohibido"


class Canal(enum.StrEnum):
    WEB = "web"
    WHATSAPP = "whatsapp"
    PBX = "pbx"
    ADMIN = "admin"


class EstadoSesion(enum.StrEnum):
    ACTIVA = "activa"
    ESCALADA = "escalada"
    CERRADA = "cerrada"


class RolMensaje(enum.StrEnum):
    USUARIO = "usuario"
    ASISTENTE = "asistente"
    ASESOR = "asesor"
    SISTEMA = "sistema"


class EstadoEscalamiento(enum.StrEnum):
    PENDIENTE = "pendiente"
    TOMADO = "tomado"
    RESUELTO = "resuelto"


class EstadoModelo(enum.StrEnum):
    CANDIDATO = "candidato"
    ACTIVO = "activo"
    RETIRADO = "retirado"
    RECHAZADO = "rechazado"
