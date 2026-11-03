"""Esquemas de la consola del asesor (HITL) y de la administración REST."""

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.base import (
    Canal,
    EstadoEscalamiento,
    EstadoPqrs,
    EstadoSesion,
    OrigenDato,
    Rol,
    RolMensaje,
    TipoCuenta,
    TipoPqrs,
    TipoServicio,
)
from app.schemas.auth import EMAIL

# --------------------------------------------------------------------------------- asesor


class EscalamientoOut(BaseModel):
    id: uuid.UUID
    sesion_id: uuid.UUID
    criterio_id: str = Field(examples=["CRIT-002"])
    criterio_categoria: str = Field(examples=["Sentimiento y Frustración del Cliente"])
    accion: str = Field(examples=["ESCALAR_PRIORIDAD_ALTA"])
    prioridad: int = Field(description="1 = más urgente (D-13)", examples=[2])
    estado: EstadoEscalamiento
    asesor_id: uuid.UUID | None
    resumen_ia: str | None
    numero_guia: str | None = Field(examples=["TLX-310482-CO"])
    espera_s: int = Field(description="Segundos en cola: hasta ahora, o hasta que se tomó", examples=[42])
    creado_en: datetime
    tomado_en: datetime | None
    resuelto_en: datetime | None


class EscalamientoDetalleOut(EscalamientoOut):
    payload: dict = Field(description="Payload de transferencia (flujo_transferencia_pwa)")


class MensajeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    turno_id: uuid.UUID
    rol: RolMensaje
    autor_id: uuid.UUID | None
    contenido: str
    artifacts: list
    intencion: str | None
    confianza: Decimal | None
    creado_en: datetime


class CuentaResumen(BaseModel):
    razon_social: str
    nit_enmascarado: str = Field(examples=["***.***.456-7"])
    tipo_cuenta: TipoCuenta
    envios_mensuales: int
    es_vip: bool = Field(description="CORPORATIVO_GOLD o más de 500 envíos al mes (CRIT-004)")


class UsuarioResumen(BaseModel):
    id: uuid.UUID
    nombre: str
    email: str
    rol: Rol


class SesionDetalleOut(BaseModel):
    id: uuid.UUID
    estado: EstadoSesion
    canal: Canal
    creado_en: datetime
    ultima_actividad: datetime
    resumen: str | None
    contexto: dict
    usuario: UsuarioResumen | None
    cuenta: CuentaResumen | None
    escalamiento: EscalamientoDetalleOut | None = Field(description="El abierto o, si no hay, el último")
    mensajes: list[MensajeOut]


class MensajeAsesorIn(BaseModel):
    model_config = ConfigDict(
        extra="forbid", json_schema_extra={"examples": [{"texto": "Hola, soy Laura. Ya reviso tu guía."}]}
    )
    texto: str = Field(min_length=1, max_length=2000)

    @field_validator("texto")
    @classmethod
    def _sin_vacio(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("El mensaje no puede estar vacío.")
        return v.strip()


class ResolverIn(BaseModel):
    model_config = ConfigDict(
        extra="forbid", json_schema_extra={"examples": [{"nota": "Se reprogramó la entrega para mañana."}]}
    )
    nota: str | None = Field(default=None, max_length=1000)


# --------------------------------------------------------------------------------- usuarios


class UsuarioAdminOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    email: str
    nombre: str
    rol: Rol
    activo: bool
    cuenta_id: int | None
    creado_en: datetime
    ultimo_login: datetime | None


class UsuarioCrearIn(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "email": "laura.gomez@translogix.co",
                    "nombre": "Laura Gómez",
                    "password": "Asesora-2026-ok",
                    "rol": "asesor",
                }
            ]
        },
    )
    email: str = Field(pattern=EMAIL, max_length=254)
    nombre: str = Field(min_length=2, max_length=120)
    password: str = Field(min_length=12, max_length=128, description="Mínimo 12 caracteres, con letras y números")
    rol: Rol
    cuenta_id: int | None = None

    @field_validator("password")
    @classmethod
    def _robusta(cls, v: str) -> str:
        if not (any(c.isalpha() for c in v) and any(c.isdigit() for c in v)):
            raise ValueError("La contraseña debe combinar letras y números.")
        return v

    @field_validator("nombre")
    @classmethod
    def _nombre(cls, v: str) -> str:
        return " ".join(v.split())


class UsuarioPatchIn(BaseModel):
    model_config = ConfigDict(extra="forbid", json_schema_extra={"examples": [{"activo": False}]})
    rol: Rol | None = None
    activo: bool | None = None
    nombre: str | None = Field(default=None, min_length=2, max_length=120)


# --------------------------------------------------------------------------------- métricas


class Conteo(BaseModel):
    clave: str = Field(examples=["CRIT-002"])
    total: int = Field(examples=[12])


class MetricasOut(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "desde": "2026-10-28",
                    "hasta": "2026-11-03",
                    "interacciones": 1840,
                    "sesiones": 512,
                    "sesiones_escaladas": 61,
                    "pct_resuelto_sin_humano": 88.09,
                    "escalamientos_por_criterio": [
                        {"clave": "CRIT-001", "total": 30},
                        {"clave": "CRIT-002", "total": 19},
                    ],
                    "intenciones_top": [{"clave": "rastreo", "total": 900}, {"clave": "cotizacion", "total": 410}],
                    "confianza_media": 0.842,
                    "latencia_p50_ms": 1450.0,
                    "latencia_p95_ms": 3900.0,
                    "csat_promedio": 4.3,
                    "calificaciones": 120,
                    "pqrs_por_estado": [{"clave": "radicado", "total": 14}],
                    "envios_por_estado": [{"clave": "EN_TRANSITO", "total": 230}],
                }
            ]
        }
    )
    desde: date
    hasta: date
    interacciones: int = Field(description="Mensajes de usuario en el periodo")
    sesiones: int
    sesiones_escaladas: int
    pct_resuelto_sin_humano: float | None = Field(description="Sesiones sin escalamiento / sesiones × 100")
    escalamientos_por_criterio: list[Conteo]
    intenciones_top: list[Conteo]
    confianza_media: float | None
    latencia_p50_ms: float | None = Field(description="Sobre latencias_ms.total de los mensajes del asistente")
    latencia_p95_ms: float | None
    csat_promedio: float | None
    calificaciones: int
    pqrs_por_estado: list[Conteo] = Field(description="Tickets creados en el periodo, por estado actual")
    envios_por_estado: list[Conteo] = Field(description="Foto actual de todos los envíos (sin filtro de fechas)")


# --------------------------------------------------------------------------------- conversaciones


class ConversacionOut(BaseModel):
    id: uuid.UUID
    estado: EstadoSesion
    canal: Canal
    usuario_id: uuid.UUID | None
    creado_en: datetime
    ultima_actividad: datetime
    mensajes: int
    escalada: bool
    ultimo_mensaje: str | None = Field(description="Primeros 200 caracteres")
    ultimo_mensaje_en: datetime | None


# --------------------------------------------------------------------------------- envíos


class EnvioAdminOut(BaseModel):
    numero_guia: str
    estado_actual: str
    origen_dato: OrigenDato
    tipo_servicio: TipoServicio
    origen_dane: str
    destino_dane: str
    trayecto_codigo: str | None
    destinatario: str | None = Field(description="Nombre enmascarado (Ley 1581)", examples=["R. B."])
    peso_facturable_kg: Decimal
    valor_declarado: Decimal
    mercancia_peligrosa: bool
    requiere_refrigeracion: bool
    fecha_despacho: datetime
    fecha_estimada_entrega: datetime
    fecha_entrega_real: datetime | None


# --------------------------------------------------------------------------------- PQRS


class PqrsAdminOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    radicado: str = Field(examples=["PQRS-2026-000001"])
    tipo: TipoPqrs
    estado: EstadoPqrs
    prioridad: int
    usuario_id: uuid.UUID
    numero_guia: str | None
    tipo_averia: str | None
    valor_reclamado: Decimal | None
    fecha_limite_respuesta: date
    asignado_a: uuid.UUID | None
    checklist: dict
    creado_en: datetime
    actualizado_en: datetime


class PqrsPatchIn(BaseModel):
    model_config = ConfigDict(extra="forbid", json_schema_extra={"examples": [{"estado": "en_revision"}]})
    estado: EstadoPqrs | None = None
    asignado_a: uuid.UUID | None = Field(default=None, description="Usuario asesor o admin")


# --------------------------------------------------------------------------------- RAG


class DocumentoRagOut(BaseModel):
    id: int
    codigo: str = Field(examples=["DOC-OPS-2026-03"])
    titulo: str
    tipo: str
    fuente: str
    activo: bool
    chunks: int
    creado_en: datetime


class IngestaOut(BaseModel):
    codigo: str
    chunks: int = Field(description="Chunks insertados (0 si el contenido no cambió)")
    omitido: bool = Field(description="True si el documento ya estaba indexado con el mismo contenido")


class ResultadoRagOut(BaseModel):
    chunk_id: int
    doc_codigo: str
    titulo_doc: str
    seccion: str
    contenido: str
    score_vector: float = Field(description="Similitud coseno (1 - distancia)")
    score_texto: float
    score_rrf: float
    metadatos: dict


# --------------------------------------------------------------------------------- auditoría


class AuditoriaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    usuario_id: uuid.UUID | None
    accion: str = Field(examples=["escalamiento.tomar"])
    entidad: str = Field(examples=["escalamiento"])
    entidad_id: str | None
    detalle: dict
    ip: str | None
    ocurrido_en: datetime

    @field_validator("ip", mode="before")
    @classmethod
    def _ip(cls, v):
        return str(v) if v is not None else None
