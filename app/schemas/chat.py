"""Mensajes de entrada del chat, eventos SSE y validación server-side de formularios."""

import re
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Annotated, Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.core.errors import Problema
from app.schemas.artifacts import SESION_EJ, Artifact, Cita, Criterio, FormularioBase

# --- entrada ----------------------------------------------------------------------------------


class MensajeTexto(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={"examples": [{"tipo": "texto", "texto": "¿Dónde está la TLX-984021-CO?"}]},
    )
    tipo: Literal["texto"]
    texto: str = Field(min_length=1, max_length=2000)


class MensajeArtifactSubmit(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "tipo": "artifact_submit",
                    "artifact_id": "art-cot-01",
                    "valores": {
                        "origen": "Bogotá D.C.",
                        "destino": "Medellín",
                        "alto_cm": 40,
                        "ancho_cm": 50,
                        "largo_cm": 60,
                        "peso_kg": 45.5,
                        "valor_declarado_cop": 12500000,
                        "servicio": "paqueteria",
                    },
                }
            ]
        },
    )
    tipo: Literal["artifact_submit"]
    artifact_id: str = Field(min_length=1, max_length=64)
    valores: dict[str, Any] = Field(max_length=50)


MensajeEntrada = Annotated[MensajeTexto | MensajeArtifactSubmit, Field(discriminator="tipo")]


# --- eventos SSE ------------------------------------------------------------------------------


class _Evento(BaseModel):
    model_config = ConfigDict(extra="forbid")
    EVENTO: ClassVar[str]


class EventoMeta(_Evento):
    EVENTO: ClassVar[str] = "meta"
    turno_id: str
    sesion_id: str
    intencion: str
    confianza_enrutador: float | None = Field(default=None, ge=0, le=1)


class EventoArtifact(_Evento):
    EVENTO: ClassVar[str] = "artifact"
    artifact: Artifact


class EventoDelta(_Evento):
    EVENTO: ClassVar[str] = "delta"
    texto: str


class EventoReemplazo(_Evento):
    """El verificador rechazó el texto emitido: el cliente debe sustituirlo por `texto`."""

    EVENTO: ClassVar[str] = "reemplazo"
    texto: str
    motivo: str


class EventoCitas(_Evento):
    EVENTO: ClassVar[str] = "citas"
    citas: list[Cita]


class EventoEscalamiento(_Evento):
    EVENTO: ClassVar[str] = "escalamiento"
    escalamiento_id: str
    criterio: Criterio
    prioridad: Literal["alta", "media", "normal"]
    mensaje: str
    espera_estimada_s: int = Field(ge=0)


class Latencias(BaseModel):
    """Milisegundos por etapa; `None` si la etapa no se ejecutó en el turno."""

    router: float | None = None
    tool: float | None = None
    retrieval: float | None = None
    llm_first_token: float | None = None
    llm_total: float | None = None
    verify: float | None = None
    total: float


class EventoFin(_Evento):
    EVENTO: ClassVar[str] = "fin"
    turno_id: str
    confianza: float = Field(ge=0, le=1)
    latencias_ms: Latencias


class EventoError(Problema):
    """`data` del evento `error`: el mismo problem+json de las respuestas HTTP."""

    EVENTO: ClassVar[str] = "error"
    status: int = Field(ge=400, le=599)


def formatear_sse(evento: BaseModel) -> str:
    """Serializa un evento al formato de cable SSE (`event:` + `data:` + línea en blanco)."""
    return f"event: {evento.EVENTO}\ndata: {evento.model_dump_json(exclude_none=True)}\n\n"


class ChatTurnResponse(BaseModel):
    """Respuesta de `?stream=false`: el turno completo, equivalente a todos los eventos SSE."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "turno_id": "c2d3e4f5-0a1b-4c2d-8e3f-4a5b6c7d8e9f",
                    "sesion_id": SESION_EJ,
                    "intencion": "rastrear",
                    "artifacts": [
                        {
                            "id": "art-trk-02",
                            "tipo": "mapa_ubicacion",
                            "guia": "TLX-984021-CO",
                            "latitud": 5.06889,
                            "longitud": -75.51738,
                            "referencia": "Paso de Montaña Alto de la Línea - Sentido Bogotá-Ibague-Medellín",
                        }
                    ],
                    "texto": "Tu envío TLX-984021-CO va en tránsito por el Alto de La Línea y llega "
                    "hoy 3 de noviembre hacia las 4:00 p. m.",
                    "reemplazado": False,
                    "citas": [],
                    "escalamiento": None,
                    "confianza": 0.93,
                    "latencias_ms": {"router": 1.2, "tool": 14.8, "llm_first_token": 210.0, "total": 612.4},
                }
            ]
        },
    )
    turno_id: str
    sesion_id: str
    intencion: str
    artifacts: list[Artifact] = []
    texto: str
    reemplazado: bool = False
    citas: list[Cita] = []
    escalamiento: EventoEscalamiento | None = None
    confianza: float = Field(ge=0, le=1)
    latencias_ms: Latencias


# --- validación de formularios ----------------------------------------------------------------


class ErrorFormulario(ValueError):
    """Valores de `artifact_submit` inválidos. `errores`: {campo: mensaje} → 422 con `errores`."""

    def __init__(self, errores: dict[str, str]):
        super().__init__(f"{len(errores)} campo(s) con error")
        self.errores = errores

    def como_problema(self) -> list[dict]:
        """Formato `Problema.errores`: [{campo, mensaje, tipo}] para `ApiError(422, ..., errores=...)`."""
        tipos = {"Campo obligatorio": "obligatorio", "Campo desconocido": "desconocido"}
        return [{"campo": k, "mensaje": v, "tipo": tipos.get(v, "invalido")} for k, v in self.errores.items()]


def _vacio(v: Any) -> bool:
    return v is None or (isinstance(v, str) and not v.strip())


def _numero(v: Any) -> Decimal:
    if isinstance(v, bool) or not isinstance(v, int | float | str | Decimal):
        raise ValueError("Debe ser un número")
    try:
        d = Decimal(str(v).strip())
    except InvalidOperation:
        raise ValueError("Debe ser un número") from None
    if not d.is_finite():
        raise ValueError("Debe ser un número")
    return d


def _validar_campo(campo, v: Any) -> Any:
    """Devuelve el valor normalizado o lanza ValueError con el mensaje para el usuario."""
    match campo.tipo:
        case "texto" | "archivo":
            if not isinstance(v, str):
                raise ValueError("Debe ser texto")
            v = v.strip()
            # ponytail: en `archivo` el valor es el id del documento ya subido por multipart
            minimo, maximo = int(campo.min or 0), int(campo.max or 2000)
            if not minimo <= len(v) <= maximo:
                raise ValueError(f"Debe tener entre {minimo} y {maximo} caracteres")
            if campo.patron and not re.fullmatch(campo.patron, v):
                raise ValueError("Formato inválido")
        case "numero" | "moneda":
            v = _numero(v)
            if campo.tipo == "moneda" and (v < 0 or -v.as_tuple().exponent > 2):
                raise ValueError("Debe ser un valor en pesos, positivo y con máximo 2 decimales")
            if campo.min is not None and v < campo.min:
                raise ValueError(f"Debe ser mayor o igual a {campo.min}")
            if campo.max is not None and v > campo.max:
                raise ValueError(f"Debe ser menor o igual a {campo.max}")
        case "seleccion":
            if str(v) not in {o.valor for o in campo.opciones}:
                raise ValueError("Opción no válida")
            v = str(v)
        case "fecha":
            try:
                v = date.fromisoformat(str(v))
            except ValueError:
                raise ValueError("Fecha inválida (AAAA-MM-DD)") from None
        case "booleano":
            if not isinstance(v, bool):
                raise ValueError("Debe ser verdadero o falso")
    return v


def validar_envio_formulario(formulario: FormularioBase, valores: dict[str, Any]) -> dict[str, Any]:
    """Valida `valores` contra los campos del formulario emitido por el servidor.

    Devuelve los valores normalizados (números como Decimal, fechas como date, texto sin espacios
    sobrantes; los opcionales vacíos quedan en None). Lanza ErrorFormulario con los errores por campo.
    """
    campos = {c.nombre: c for c in formulario.campos}
    errores = {k: "Campo desconocido" for k in valores if k not in campos}
    limpios: dict[str, Any] = {}
    for nombre, campo in campos.items():
        v = valores.get(nombre)
        if _vacio(v):
            if campo.requerido:
                errores[nombre] = "Campo obligatorio"
            limpios[nombre] = None
            continue
        try:
            limpios[nombre] = _validar_campo(campo, v)
        except ValueError as e:
            errores[nombre] = str(e)
    if errores:
        raise ErrorFormulario(errores)
    return limpios
