"""Catálogo de artifacts (generative UI): unión discriminada por `tipo`.

Convenciones del contrato (ver docs/frontend.md):
- Dinero: `Decimal` en COP, serializado en JSON como **string decimal** ("190975", "207468.75").
  Así no se pierden centavos ni precisión en JavaScript; el frontend lo formatea con Intl.NumberFormat.
- Fechas: ISO 8601 con zona horaria de Colombia (-05:00).
- Cada artifact lleva `id` (único en la sesión), `tipo`, `version` y `acciones[]` genéricas.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, model_validator

Dinero = Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=2)]
Guia = Annotated[str, Field(pattern=r"^TLX-\d{6}-CO$", examples=["TLX-984021-CO"])]
Criterio = Annotated[str, Field(pattern=r"^CRIT-\d{3}$", examples=["CRIT-002"])]
# Valor de celda o precarga: los decimales viajan como string (igual que el dinero) para que el
# round-trip JSON sea estable y no haya ambigüedad int/Decimal/str en la unión.
Valor = Annotated[bool | int | str | None, BeforeValidator(lambda v: str(v) if isinstance(v, Decimal | float) else v)]

SESION_EJ = "3f6c0a52-8e1b-4d7a-9c2e-5b1d0f9a7e41"
ENDPOINT_MENSAJES = f"/api/v1/chat/sesiones/{SESION_EJ}/mensajes"


def _cfg(*ejemplos: dict) -> ConfigDict:
    return ConfigDict(extra="forbid", json_schema_extra={"examples": list(ejemplos)})


# --- piezas comunes ---------------------------------------------------------------------------


class Accion(BaseModel):
    """Botón genérico. `submit`: envía el formulario como `artifact_submit` a `endpoint`;
    `mensaje`: envía `mensaje` como texto del usuario; `enlace`: abre/llama `endpoint`."""

    model_config = _cfg(
        {
            "id": "enviar",
            "etiqueta": "Cotizar",
            "tipo": "submit",
            "metodo": "POST",
            "endpoint": ENDPOINT_MENSAJES,
            "estilo": "primario",
        }
    )

    id: str = Field(min_length=1, max_length=64)
    etiqueta: str = Field(min_length=1, max_length=80)
    tipo: Literal["submit", "mensaje", "enlace"]
    metodo: Literal["GET", "POST", "PUT", "PATCH", "DELETE"] | None = None
    endpoint: str | None = Field(default=None, max_length=300)
    mensaje: str | None = Field(default=None, max_length=2000)
    payload: dict[str, Any] | None = None
    estilo: Literal["primario", "secundario", "peligro", "enlace"] = "primario"

    @model_validator(mode="after")
    def _coherente(self):
        if self.tipo == "mensaje" and not self.mensaje:
            raise ValueError("una acción 'mensaje' requiere `mensaje`")
        if self.tipo in ("submit", "enlace") and not self.endpoint:
            raise ValueError(f"una acción '{self.tipo}' requiere `endpoint`")
        return self


class Opcion(BaseModel):
    model_config = _cfg({"valor": "BOG", "etiqueta": "Bogotá D.C."})

    valor: str = Field(min_length=1, max_length=100)
    etiqueta: str = Field(min_length=1, max_length=120)


class CampoFormulario(BaseModel):
    """Campo de formulario. `min`/`max`: rango de valor (numero, moneda) o de longitud (texto)."""

    model_config = _cfg(
        {
            "nombre": "peso_kg",
            "etiqueta": "Peso real",
            "tipo": "numero",
            "requerido": True,
            "min": "0.1",
            "max": "2500",
            "valor": "45.5",
            "unidad": "kg",
            "ayuda": "Peso en báscula, con empaque.",
        }
    )

    nombre: str = Field(pattern=r"^[a-z_][a-z0-9_]{0,49}$")
    etiqueta: str = Field(min_length=1, max_length=120)
    tipo: Literal["texto", "numero", "moneda", "seleccion", "fecha", "booleano", "archivo"]
    requerido: bool = True
    min: Decimal | None = None
    max: Decimal | None = None
    patron: str | None = Field(default=None, max_length=200)
    opciones: list[Opcion] = []
    valor: Valor = None
    ayuda: str | None = Field(default=None, max_length=300)
    unidad: str | None = Field(default=None, max_length=20)
    accept: str | None = Field(default=None, max_length=100, examples=["application/pdf,image/jpeg"])
    max_bytes: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def _coherente(self):
        if self.tipo == "seleccion" and not self.opciones:
            raise ValueError("un campo 'seleccion' requiere `opciones`")
        if self.min is not None and self.max is not None and self.min > self.max:
            raise ValueError("`min` no puede ser mayor que `max`")
        return self


class Cita(BaseModel):
    model_config = _cfg(
        {
            "doc_codigo": "DOC-OPS-2026-03",
            "documento": "Manual de mercancías peligrosas y embalaje",
            "seccion": "5. Lista expresa de artículos prohibidos",
            "fragmento": "Animales vivos (mamíferos, aves, reptiles, insectos, peces).",
            "puntuacion": 0.91,
        }
    )

    doc_codigo: str = Field(max_length=40)
    documento: str = Field(max_length=200)
    seccion: str = Field(max_length=200)
    fragmento: str | None = Field(default=None, max_length=1000)
    puntuacion: float | None = Field(default=None, ge=0, le=1)


class Alerta(BaseModel):
    nivel: Literal["info", "advertencia", "critica"]
    mensaje: str = Field(max_length=500)


class ArtifactBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=64, description="Único dentro de la sesión")
    version: Literal[1] = 1
    titulo: str | None = Field(default=None, max_length=120)
    acciones: list[Accion] = []


class FormularioBase(ArtifactBase):
    """Base de los formularios; se validan en servidor con `validar_envio_formulario`."""

    campos: list[CampoFormulario] = Field(min_length=1)


# --- artifacts de cliente ---------------------------------------------------------------------

_SUBMIT = {"id": "enviar", "tipo": "submit", "metodo": "POST", "endpoint": ENDPOINT_MENSAJES}


class FormularioCotizacion(FormularioBase):
    model_config = _cfg(
        {
            "id": "art-cot-01",
            "tipo": "formulario_cotizacion",
            "version": 1,
            "titulo": "Cotiza tu envío",
            "campos": [
                {
                    "nombre": "origen",
                    "etiqueta": "Ciudad de origen",
                    "tipo": "seleccion",
                    "opciones": [{"valor": "Bogotá D.C.", "etiqueta": "Bogotá D.C."}],
                    "valor": "Bogotá D.C.",
                },
                {
                    "nombre": "destino",
                    "etiqueta": "Ciudad de destino",
                    "tipo": "seleccion",
                    "opciones": [
                        {"valor": "Medellín", "etiqueta": "Medellín"},
                        {"valor": "Cali", "etiqueta": "Cali"},
                    ],
                    "valor": "Medellín",
                },
                {
                    "nombre": "alto_cm",
                    "etiqueta": "Alto",
                    "tipo": "numero",
                    "min": "1",
                    "max": "400",
                    "unidad": "cm",
                },
                {
                    "nombre": "ancho_cm",
                    "etiqueta": "Ancho",
                    "tipo": "numero",
                    "min": "1",
                    "max": "400",
                    "unidad": "cm",
                },
                {
                    "nombre": "largo_cm",
                    "etiqueta": "Largo",
                    "tipo": "numero",
                    "min": "1",
                    "max": "1400",
                    "unidad": "cm",
                },
                {
                    "nombre": "peso_kg",
                    "etiqueta": "Peso real",
                    "tipo": "numero",
                    "min": "0.1",
                    "max": "2500",
                    "unidad": "kg",
                },
                {
                    "nombre": "valor_declarado_cop",
                    "etiqueta": "Valor declarado",
                    "tipo": "moneda",
                    "min": "0",
                    "max": "1000000000",
                    "unidad": "COP",
                },
                {
                    "nombre": "servicio",
                    "etiqueta": "Tipo de servicio",
                    "tipo": "seleccion",
                    "opciones": [
                        {"valor": "paqueteria", "etiqueta": "Paquetería exprés (hasta 50 kg)"},
                        {"valor": "carga", "etiqueta": "Carga (LTL / FTL)"},
                        {"valor": "cadena_frio", "etiqueta": "Cadena de frío"},
                        {"valor": "mercancia_peligrosa", "etiqueta": "Mercancía peligrosa"},
                    ],
                    "valor": "paqueteria",
                },
            ],
            "acciones": [{**_SUBMIT, "etiqueta": "Cotizar"}],
        }
    )
    tipo: Literal["formulario_cotizacion"] = "formulario_cotizacion"


class Recargo(BaseModel):
    concepto: str = Field(max_length=120)
    valor: Dinero


class ResultadoCotizacion(ArtifactBase):
    model_config = _cfg(
        {
            "id": "art-cot-02",
            "tipo": "resultado_cotizacion",
            "titulo": "Cotización Bogotá D.C. → Medellín",
            "cotizacion_id": "8d1e2f30-6a7b-4c8d-9e0f-1a2b3c4d5e6f",
            "trayecto": "TLX-BOG-MED-001",
            "origen": "Bogotá D.C.",
            "destino": "Medellín",
            "servicio": "paqueteria",
            "peso_real_kg": "45.5",
            "peso_volumetrico_kg": "30",
            "peso_facturable_kg": "45.5",
            "base_facturacion": "real",
            "tarifa_kg": "1450",
            "flete_base": "65975",
            "flete_minimo_aplicado": False,
            "seguro": "125000",
            "recargos": [],
            "total": "190975",
            "tiempo_estimado_horas": 24,
            "observaciones": "Ruta de alto flujo por Corredor Bogotá-Medellín. Admite Same Day si se "
            "despacha antes de las 09:00 AM.",
            "acciones": [
                {
                    "id": "nueva",
                    "etiqueta": "Nueva cotización",
                    "tipo": "mensaje",
                    "mensaje": "Quiero cotizar",
                }
            ],
        }
    )
    tipo: Literal["resultado_cotizacion"] = "resultado_cotizacion"
    cotizacion_id: str = Field(max_length=64)
    trayecto: str = Field(pattern=r"^TLX-[A-Z]{3}-[A-Z]{3}-\d{3}$")
    origen: str
    destino: str
    servicio: str
    peso_real_kg: Decimal = Field(gt=0)
    peso_volumetrico_kg: Decimal = Field(ge=0)
    peso_facturable_kg: Decimal = Field(gt=0)
    base_facturacion: Literal["real", "volumetrico"]
    tarifa_kg: Dinero
    flete_base: Dinero
    flete_minimo_aplicado: bool
    seguro: Dinero
    recargos: list[Recargo] = []
    total: Dinero
    tiempo_estimado_horas: int = Field(gt=0)
    observaciones: str | None = None
    advertencias: list[str] = []


class FormularioGuia(FormularioBase):
    model_config = _cfg(
        {
            "id": "art-trk-00",
            "tipo": "formulario_guia",
            "titulo": "¿Cuál es tu número de guía?",
            "campos": [
                {
                    "nombre": "guia",
                    "etiqueta": "Número de guía",
                    "tipo": "texto",
                    "patron": r"^TLX-\d{6}-CO$",
                    "ayuda": "Formato TLX-123456-CO",
                }
            ],
            "acciones": [{**_SUBMIT, "etiqueta": "Rastrear"}],
        }
    )
    tipo: Literal["formulario_guia"] = "formulario_guia"


class EventoLinea(BaseModel):
    ts: datetime
    estado: str = Field(max_length=40)
    estado_texto: str = Field(max_length=120)
    ubicacion: str | None = Field(default=None, max_length=200)
    descripcion: str | None = Field(default=None, max_length=500)


class LineaTiempoEnvio(ArtifactBase):
    model_config = _cfg(
        {
            "id": "art-trk-01",
            "tipo": "linea_tiempo_envio",
            "titulo": "Guía TLX-984021-CO",
            "guia": "TLX-984021-CO",
            "origen": "Bogotá D.C.",
            "destino": "Medellín",
            "servicio": "Transporte Cadena de Frío (2°C a 8°C)",
            "estado_actual": "EN_TRANSITO",
            "estado_texto": "En camino a la ciudad de destino",
            "progreso_pct": 60,
            "eta": "2026-11-03T16:00:00-05:00",
            "eventos": [
                {
                    "ts": "2026-11-02T11:15:00-05:00",
                    "estado": "SOLICITUD_GENERADA",
                    "estado_texto": "Guía generada",
                    "ubicacion": "Portal Web Clientes TransLogix",
                    "descripcion": "Orden de despacho creada y guía generada exitosamente.",
                },
                {
                    "ts": "2026-11-03T08:30:00-05:00",
                    "estado": "EN_TRANSITO",
                    "estado_texto": "En camino a la ciudad de destino",
                    "ubicacion": "Corredor Calarcá - Pereira",
                    "descripcion": "Vehículo en ruta regular. Arribo estimado a Hub Itagüí a las 12:30 PM.",
                },
            ],
            "alerta": None,
        }
    )
    tipo: Literal["linea_tiempo_envio"] = "linea_tiempo_envio"
    guia: Guia
    origen: str
    destino: str
    servicio: str | None = None
    estado_actual: str = Field(max_length=40)
    estado_texto: str = Field(max_length=120)
    progreso_pct: int = Field(ge=0, le=100)
    eta: datetime | None = None
    eventos: list[EventoLinea]
    alerta: Alerta | None = None


class MapaUbicacion(ArtifactBase):
    model_config = _cfg(
        {
            "id": "art-trk-02",
            "tipo": "mapa_ubicacion",
            "guia": "TLX-984021-CO",
            "latitud": 5.06889,
            "longitud": -75.51738,
            "referencia": "Paso de Montaña Alto de la Línea - Sentido Bogotá-Ibague-Medellín",
            "actualizado": "2026-11-03T08:30:00-05:00",
        }
    )
    tipo: Literal["mapa_ubicacion"] = "mapa_ubicacion"
    guia: Guia
    latitud: float = Field(ge=-90, le=90)
    longitud: float = Field(ge=-180, le=180)
    referencia: str | None = Field(default=None, max_length=200)
    actualizado: datetime | None = None


class VeredictoMercancia(ArtifactBase):
    model_config = _cfg(
        {
            "id": "art-mp-01",
            "tipo": "veredicto_mercancia",
            "producto": "perro",
            "veredicto": "prohibido",
            "categoria": "Animales vivos",
            "clase_onu": None,
            "motivo": "Los animales vivos están en la lista de artículos prohibidos de TransLogix.",
            "condiciones": [],
            "documentos": [],
            "embalaje": [],
            "fuentes": [
                {
                    "doc_codigo": "DOC-OPS-2026-03",
                    "documento": "Manual de mercancías peligrosas y embalaje",
                    "seccion": "5. Lista expresa de artículos prohibidos",
                }
            ],
        },
        {
            "id": "art-mp-02",
            "tipo": "veredicto_mercancia",
            "producto": "5 litros de ácido clorhídrico",
            "veredicto": "restringido",
            "categoria": "Sustancias corrosivas",
            "clase_onu": "8",
            "motivo": "Corrosivo Clase 8: se acepta en paquetería con envases de máximo 5 litros.",
            "condiciones": ["Envases no superiores a 5 litros en paquetería"],
            "documentos": [
                "Hoja de Seguridad (MSDS/HDS) SGA de 16 secciones, en español",
                "Tarjeta de Emergencia NTC 4532",
            ],
            "embalaje": ["Sobre-empaque en caja de cartón corrugado de doble pared (7 capas)"],
            "fuentes": [
                {
                    "doc_codigo": "DOC-OPS-2026-03",
                    "documento": "Manual de mercancías peligrosas y embalaje",
                    "seccion": "Clase 8: Sustancias Corrosivas",
                }
            ],
        },
    )
    tipo: Literal["veredicto_mercancia"] = "veredicto_mercancia"
    producto: str = Field(max_length=200)
    veredicto: Literal["permitido", "restringido", "solo_ftl", "prohibido"]
    categoria: str | None = Field(default=None, max_length=120)
    clase_onu: str | None = Field(default=None, pattern=r"^[1-9](\.[1-6])?$")
    motivo: str = Field(max_length=500)
    condiciones: list[str] = []
    documentos: list[str] = []
    embalaje: list[str] = []
    fuentes: list[Cita] = []


class PasoPlan(BaseModel):
    titulo: str = Field(max_length=120)
    detalle: str = Field(max_length=500)
    items: list[str] = []


class PlanEnvio(ArtifactBase):
    """Lo que hay que saber y hacer para despachar un producto; va seguido del formulario de cotización."""

    model_config = _cfg(
        {
            "id": "art-plan-01",
            "tipo": "plan_envio",
            "titulo": "Plan para enviar clavos",
            "producto": "clavos",
            "estado": "sin_registro",
            "resumen": "No aparece en nuestro catálogo de prohibidos y mercancías peligrosas. No es una aprobación.",
            "pasos": [
                {
                    "titulo": "Embala",
                    "detalle": "El remitente responde por un embalaje que resista vibración, frenado y apilamiento.",
                    "items": [],
                }
            ],
            "fuentes": [
                {
                    "doc_codigo": "DOC-OPS-2026-03",
                    "documento": "Manual de mercancías peligrosas y embalaje",
                    "seccion": "§4 Estándares de embalaje",
                }
            ],
        }
    )
    tipo: Literal["plan_envio"] = "plan_envio"
    producto: str | None = Field(default=None, max_length=200)
    # sin_registro: el catálogo no lo clasifica (no equivale a permitido). sin_producto: aún no se sabe qué se envía.
    estado: Literal["permitido", "restringido", "solo_ftl", "sin_registro", "sin_producto"]
    resumen: str = Field(max_length=500)
    pasos: list[PasoPlan] = Field(min_length=1)
    fuentes: list[Cita] = []


class GuiaEmbalaje(ArtifactBase):
    model_config = _cfg(
        {
            "id": "art-emb-01",
            "tipo": "guia_embalaje",
            "categoria": "A",
            "nombre_categoria": "Productos frágiles (vidrio, cerámica, instrumentos de medición)",
            "requisito": "Sistema de protección «caja dentro de caja».",
            "pasos": [
                "Envuelve cada producto con plástico burbuja de al menos 3 cm de espesor.",
                "Deja mínimo 5 cm entre el producto y las paredes internas de la caja exterior.",
                "Rellena el espacio libre con maní de poliestireno o espuma inyectada.",
                "Marca la caja con cinta roja «FRÁGIL - MANEJE CON CUIDADO» y flechas «ESTE LADO ARRIBA».",
            ],
            "fuentes": [
                {
                    "doc_codigo": "DOC-OPS-2026-03",
                    "documento": "Manual de mercancías peligrosas y embalaje",
                    "seccion": "4.A Productos Frágiles",
                }
            ],
        }
    )
    tipo: Literal["guia_embalaje"] = "guia_embalaje"
    categoria: Literal["A", "B", "C", "D"]
    nombre_categoria: str = Field(max_length=200)
    requisito: str | None = Field(default=None, max_length=300)
    pasos: list[str] = Field(min_length=1)
    fuentes: list[Cita] = []


class FichaCobertura(ArtifactBase):
    model_config = _cfg(
        {
            "id": "art-cob-01",
            "tipo": "ficha_cobertura",
            "municipio": "Medellín",
            "departamento": "Antioquia",
            "codigo_dane": "05001",
            "tipo_cobertura": "Urbana Principal",
            "hub": "Hub Regional Itagüí - Antioquia",
            "same_day": True,
            "refrigerado": True,
            "peso_maximo_kg": "2000",
            "volumen_maximo_m3": "40",
            "tiempo_estandar_horas": 24,
            "frecuencia_despacho": "Continuo (4 salidas diarias)",
            "restricciones": "Restricción de ingreso al centro urbano para camiones de más de 2 ejes "
            "entre 06:00 y 20:00.",
        }
    )
    tipo: Literal["ficha_cobertura"] = "ficha_cobertura"
    municipio: str
    departamento: str
    codigo_dane: str = Field(pattern=r"^\d{5}$")
    tipo_cobertura: str
    hub: str
    same_day: bool
    refrigerado: bool
    peso_maximo_kg: Decimal = Field(gt=0)
    volumen_maximo_m3: Decimal = Field(gt=0)
    tiempo_estandar_horas: int = Field(gt=0)
    frecuencia_despacho: str | None = None
    restricciones: str | None = None


class FormularioPqrs(FormularioBase):
    model_config = _cfg(
        {
            "id": "art-pqrs-01",
            "tipo": "formulario_pqrs",
            "titulo": "Radicar reclamo",
            "campos": [
                {
                    "nombre": "tipo",
                    "etiqueta": "Tipo de solicitud",
                    "tipo": "seleccion",
                    "opciones": [
                        {"valor": "P", "etiqueta": "Petición"},
                        {"valor": "Q", "etiqueta": "Queja"},
                        {"valor": "R", "etiqueta": "Reclamo"},
                        {"valor": "S", "etiqueta": "Sugerencia"},
                    ],
                    "valor": "R",
                },
                {
                    "nombre": "guia",
                    "etiqueta": "Número de guía",
                    "tipo": "texto",
                    "patron": r"^TLX-\d{6}-CO$",
                },
                {
                    "nombre": "novedad",
                    "etiqueta": "¿Qué pasó?",
                    "tipo": "seleccion",
                    "opciones": [
                        {"valor": "averia_aparente", "etiqueta": "Daño visible al recibir"},
                        {"valor": "averia_oculta", "etiqueta": "Daño descubierto al abrir"},
                        {"valor": "perdida", "etiqueta": "Pérdida o extravío"},
                    ],
                    "valor": "averia_oculta",
                },
                {
                    "nombre": "fecha_entrega",
                    "etiqueta": "Fecha de entrega",
                    "tipo": "fecha",
                    "requerido": False,
                },
                {
                    "nombre": "descripcion",
                    "etiqueta": "Descripción",
                    "tipo": "texto",
                    "min": "10",
                    "max": "2000",
                },
                {
                    "nombre": "valor_reclamado_cop",
                    "etiqueta": "Valor reclamado",
                    "tipo": "moneda",
                    "unidad": "COP",
                },
                {
                    "nombre": "anotada_en_guia",
                    "etiqueta": "¿Dejaste anotación en la guía o POD al recibir?",
                    "tipo": "booleano",
                    "requerido": False,
                },
            ],
            "acciones": [{**_SUBMIT, "etiqueta": "Continuar"}],
        }
    )
    tipo: Literal["formulario_pqrs"] = "formulario_pqrs"


class EstadoPlazo(ArtifactBase):
    model_config = _cfg(
        {
            "id": "art-pqrs-02",
            "tipo": "estado_plazo",
            "guia": "TLX-752190-CO",
            "novedad": "averia_oculta",
            "fecha_referencia": "2026-11-02",
            "fecha_limite": "2026-11-05",
            "dias_habiles_plazo": 3,
            "dias_habiles_restantes": 2,
            "vigente": True,
            "mensaje": "Estás dentro del plazo: tienes hasta el 5 de noviembre de 2026 para radicar.",
            "fundamento": "Protocolo PQRS §3: avería oculta, 3 días hábiles tras la entrega.",
        }
    )
    tipo: Literal["estado_plazo"] = "estado_plazo"
    guia: Guia | None = None
    novedad: Literal["averia_aparente", "averia_oculta", "perdida"]
    fecha_referencia: date
    fecha_limite: date | None = None
    dias_habiles_plazo: int = Field(ge=0)
    dias_habiles_restantes: int
    vigente: bool
    mensaje: str = Field(max_length=500)
    fundamento: str | None = Field(default=None, max_length=300)


class ItemChecklist(BaseModel):
    id: str = Field(pattern=r"^[a-z_][a-z0-9_]{0,49}$")
    etiqueta: str = Field(max_length=120)
    descripcion: str | None = Field(default=None, max_length=500)
    requerido: bool = True
    completado: bool = False
    accept: str | None = Field(default="application/pdf,image/jpeg", max_length=100)
    max_bytes: int | None = Field(default=10 * 1024 * 1024, gt=0)


class ChecklistDocumentos(ArtifactBase):
    model_config = _cfg(
        {
            "id": "art-pqrs-03",
            "tipo": "checklist_documentos",
            "radicado": "PQRS-2026-000123",
            "endpoint_carga": "/api/v1/pqrs/PQRS-2026-000123/documentos",
            "items": [
                {
                    "id": "guia",
                    "etiqueta": "Número de guía de transporte",
                    "completado": True,
                    "accept": None,
                },
                {"id": "factura", "etiqueta": "Factura comercial de venta (con IVA)"},
                {
                    "id": "carta_reclamacion",
                    "etiqueta": "Carta de reclamación formal",
                    "descripcion": "Firmada, con valor reclamado, descripción y certificación bancaria "
                    "(no mayor a 30 días).",
                },
                {"id": "fotos", "etiqueta": "Registro fotográfico (empaque, daño y amortiguación)"},
                {"id": "identidad", "etiqueta": "Cédula o RUT"},
            ],
            "completo": False,
            "acciones": [
                {
                    "id": "radicar",
                    "etiqueta": "Radicar",
                    "tipo": "submit",
                    "metodo": "POST",
                    "endpoint": ENDPOINT_MENSAJES,
                }
            ],
        }
    )
    tipo: Literal["checklist_documentos"] = "checklist_documentos"
    radicado: str | None = Field(default=None, max_length=40)
    endpoint_carga: str | None = Field(default=None, max_length=300, description="multipart, campo `archivo`")
    items: list[ItemChecklist] = Field(min_length=1)
    completo: bool


class Liquidacion(BaseModel):
    base: Dinero
    deducible: Dinero
    flete_devuelto: Dinero
    total: Dinero
    nota: str = Field(max_length=300)


class TicketPqrs(ArtifactBase):
    model_config = _cfg(
        {
            "id": "art-pqrs-04",
            "tipo": "ticket_pqrs",
            "radicado": "PQRS-2026-000123",
            "tipo_pqrs": "R",
            "estado": "radicado",
            "guia": "TLX-551904-CO",
            "fecha_radicacion": "2026-11-03T10:12:00-05:00",
            "fecha_limite_respuesta": "2026-11-25",
            "checklist_completo": True,
            "liquidacion_estimada": {
                "base": "420000",
                "deducible": "0",
                "flete_devuelto": "0",
                "total": "420000",
                "nota": "Estimación sujeta a aprobación (15 días hábiles).",
            },
            "escalado_a": None,
        }
    )
    tipo: Literal["ticket_pqrs"] = "ticket_pqrs"
    radicado: str = Field(max_length=40)
    tipo_pqrs: Literal["P", "Q", "R", "S"]
    estado: str = Field(max_length=40)
    guia: Guia | None = None
    fecha_radicacion: datetime
    fecha_limite_respuesta: date
    checklist_completo: bool
    liquidacion_estimada: Liquidacion | None = None
    escalado_a: Criterio | None = None


class AvisoEscalamiento(ArtifactBase):
    model_config = _cfg(
        {
            "id": "art-esc-01",
            "tipo": "aviso_escalamiento",
            "escalamiento_id": "b7c1d2e3-4f50-4a6b-8c7d-9e0f1a2b3c4d",
            "criterio": "CRIT-002",
            "prioridad": "alta",
            "mensaje": "Lamento profundamente la molestia ocasionada. Estoy transfiriendo tu chat de "
            "inmediato a un supervisor de servicio al cliente para resolver tu situación.",
            "espera_estimada_s": 45,
            "posicion_cola": 2,
        }
    )
    tipo: Literal["aviso_escalamiento"] = "aviso_escalamiento"
    escalamiento_id: str = Field(max_length=64)
    criterio: Criterio
    prioridad: Literal["alta", "media", "normal"]
    mensaje: str = Field(max_length=500)
    espera_estimada_s: int = Field(ge=0)
    posicion_cola: int | None = Field(default=None, ge=1)


class Citas(ArtifactBase):
    model_config = _cfg(
        {
            "id": "art-cit-01",
            "tipo": "citas",
            "citas": [
                {
                    "doc_codigo": "DOC-PQRS-2026-04",
                    "documento": "Protocolo de PQRS e indemnizaciones",
                    "seccion": "3. Tiempos y plazos legales de radicación",
                    "puntuacion": 0.88,
                }
            ],
        }
    )
    tipo: Literal["citas"] = "citas"
    citas: list[Cita] = Field(min_length=1)


class RespuestasRapidas(ArtifactBase):
    """Chips: cada acción de tipo `mensaje` envía su texto como mensaje del usuario."""

    model_config = _cfg(
        {
            "id": "art-rr-01",
            "tipo": "respuestas_rapidas",
            "acciones": [
                {
                    "id": "rastrear",
                    "etiqueta": "Rastrear una guía",
                    "tipo": "mensaje",
                    "mensaje": "Quiero rastrear",
                },
                {
                    "id": "cotizar",
                    "etiqueta": "Cotizar un envío",
                    "tipo": "mensaje",
                    "mensaje": "Quiero cotizar",
                },
                {
                    "id": "pqrs",
                    "etiqueta": "Radicar un reclamo",
                    "tipo": "mensaje",
                    "mensaje": "Quiero radicar un reclamo",
                },
            ],
        }
    )
    tipo: Literal["respuestas_rapidas"] = "respuestas_rapidas"
    acciones: list[Accion] = Field(min_length=1)


class Confirmacion(ArtifactBase):
    model_config = _cfg(
        {
            "id": "art-conf-01",
            "tipo": "confirmacion",
            "mensaje": "¿Quieres que te conecte con un asesor?",
            "acciones": [
                {"id": "si", "etiqueta": "Sí", "tipo": "mensaje", "mensaje": "Sí, quiero un asesor"},
                {
                    "id": "no",
                    "etiqueta": "No",
                    "tipo": "mensaje",
                    "mensaje": "No, gracias",
                    "estilo": "secundario",
                },
            ],
        }
    )
    tipo: Literal["confirmacion"] = "confirmacion"
    mensaje: str = Field(max_length=500)
    acciones: list[Accion] = Field(min_length=1)


class EncuestaSatisfaccion(ArtifactBase):
    model_config = _cfg(
        {
            "id": "art-csat-01",
            "tipo": "encuesta_satisfaccion",
            "pregunta": "¿Qué tan satisfecho quedaste con la atención?",
            "escala_min": 1,
            "escala_max": 5,
            "permite_comentario": True,
            "acciones": [
                {
                    "id": "calificar",
                    "etiqueta": "Enviar",
                    "tipo": "enlace",
                    "metodo": "POST",
                    "endpoint": f"/api/v1/chat/sesiones/{SESION_EJ}/calificacion",
                }
            ],
        }
    )
    tipo: Literal["encuesta_satisfaccion"] = "encuesta_satisfaccion"
    pregunta: str = Field(max_length=200)
    escala_min: int = 1
    escala_max: int = 5
    permite_comentario: bool = True


# --- artifacts de administración --------------------------------------------------------------


class Kpi(BaseModel):
    id: str = Field(max_length=64)
    etiqueta: str = Field(max_length=120)
    valor: Decimal
    formato: Literal["numero", "porcentaje", "moneda", "duracion_ms"] = "numero"
    unidad: str | None = Field(default=None, max_length=20)
    variacion_pct: Decimal | None = None
    tendencia: Literal["sube", "baja", "estable"] | None = None


class TarjetasKpi(ArtifactBase):
    model_config = _cfg(
        {
            "id": "art-kpi-01",
            "tipo": "tarjetas_kpi",
            "titulo": "Últimos 7 días",
            "periodo": {"desde": "2026-10-27", "hasta": "2026-11-03"},
            "tarjetas": [
                {"id": "interacciones", "etiqueta": "Interacciones", "valor": "1284", "tendencia": "sube"},
                {
                    "id": "automatizado",
                    "etiqueta": "Resuelto sin humano",
                    "valor": "81.4",
                    "formato": "porcentaje",
                },
                {"id": "p95", "etiqueta": "Latencia p95", "valor": "1850", "formato": "duracion_ms"},
                {"id": "csat", "etiqueta": "CSAT", "valor": "4.3", "unidad": "/5"},
            ],
        }
    )
    tipo: Literal["tarjetas_kpi"] = "tarjetas_kpi"
    periodo: dict[Literal["desde", "hasta"], date] | None = None
    tarjetas: list[Kpi] = Field(min_length=1)


class Punto(BaseModel):
    x: str = Field(max_length=40, description="Categoría o fecha ISO")
    y: Decimal
    y_inf: Decimal | None = None
    y_sup: Decimal | None = None


class Serie(BaseModel):
    nombre: str = Field(max_length=80)
    puntos: list[Punto]
    estilo: Literal["solida", "punteada"] = "solida"


class Eje(BaseModel):
    etiqueta: str = Field(max_length=80)
    tipo: Literal["categoria", "fecha", "numero"] = "categoria"
    unidad: str | None = Field(default=None, max_length=20)


class Grafico(ArtifactBase):
    model_config = _cfg(
        {
            "id": "art-graf-01",
            "tipo": "grafico",
            "titulo": "Pronóstico de despachos — Hub Central Zona Franca Fontibón",
            "tipo_grafico": "linea",
            "eje_x": {"etiqueta": "Fecha", "tipo": "fecha"},
            "eje_y": {"etiqueta": "Despachos", "tipo": "numero", "unidad": "envíos"},
            "series": [
                {
                    "nombre": "Histórico",
                    "puntos": [{"x": "2026-11-02", "y": "142"}, {"x": "2026-11-03", "y": "151"}],
                },
                {
                    "nombre": "Pronóstico",
                    "estilo": "punteada",
                    "puntos": [{"x": "2026-11-04", "y": "148", "y_inf": "131", "y_sup": "166"}],
                },
            ],
            "datos_simulados": True,
        }
    )
    tipo: Literal["grafico"] = "grafico"
    tipo_grafico: Literal["linea", "barras"]
    eje_x: Eje
    eje_y: Eje
    series: list[Serie] = Field(min_length=1)
    datos_simulados: bool = False


class Columna(BaseModel):
    clave: str = Field(pattern=r"^[a-z_][a-z0-9_]{0,49}$")
    etiqueta: str = Field(max_length=80)
    tipo: Literal["texto", "numero", "moneda", "fecha", "estado"] = "texto"


class Paginacion(BaseModel):
    pagina: int = Field(ge=1)
    tamano: int = Field(ge=1, le=200)
    total: int = Field(ge=0)


class TablaDatos(ArtifactBase):
    model_config = _cfg(
        {
            "id": "art-tab-01",
            "tipo": "tabla_datos",
            "titulo": "Envíos retenidos",
            "columnas": [
                {"clave": "guia", "etiqueta": "Guía"},
                {"clave": "ruta", "etiqueta": "Ruta"},
                {"clave": "estado", "etiqueta": "Estado", "tipo": "estado"},
                {"clave": "declarado", "etiqueta": "Valor declarado", "tipo": "moneda"},
            ],
            "filas": [
                {
                    "guia": "TLX-310482-CO",
                    "ruta": "Barranquilla → Bucaramanga",
                    "estado": "RETENIDO_NOVEDAD",
                    "declarado": "34000000",
                }
            ],
            "paginacion": {"pagina": 1, "tamano": 20, "total": 1},
        }
    )
    tipo: Literal["tabla_datos"] = "tabla_datos"
    columnas: list[Columna] = Field(min_length=1)
    filas: list[dict[str, Valor]] = []
    paginacion: Paginacion | None = None

    @model_validator(mode="after")
    def _filas_en_columnas(self):
        claves = {c.clave for c in self.columnas}
        for i, fila in enumerate(self.filas):
            if sobra := set(fila) - claves:
                raise ValueError(f"fila {i}: claves sin columna {sorted(sobra)}")
        return self


class Factor(BaseModel):
    nombre: str = Field(max_length=80)
    efecto: Decimal = Field(description="Cambio en la probabilidad (puntos, con signo)")
    descripcion: str | None = Field(default=None, max_length=200)


class TarjetaPrediccion(ArtifactBase):
    model_config = _cfg(
        {
            "id": "art-pred-01",
            "tipo": "tarjeta_prediccion",
            "modelo": "riesgo_retraso",
            "version_modelo": 3,
            "guia": "TLX-984021-CO",
            "probabilidad": "0.34",
            "intervalo": {"inferior": "0.26", "superior": "0.42"},
            "nivel": "medio",
            "factores": [
                {"nombre": "paso_montana", "efecto": "0.12", "descripcion": "Ruta por el Alto de La Línea"},
                {"nombre": "cadena_frio", "efecto": "0.05", "descripcion": "Requiere refrigeración"},
            ],
            "datos_simulados": True,
        }
    )
    tipo: Literal["tarjeta_prediccion"] = "tarjeta_prediccion"
    modelo: str = Field(max_length=60)
    version_modelo: int = Field(ge=1)
    guia: Guia | None = None
    probabilidad: Decimal = Field(ge=0, le=1)
    intervalo: dict[Literal["inferior", "superior"], Decimal] | None = None
    nivel: Literal["bajo", "medio", "alto"]
    factores: list[Factor] = []
    datos_simulados: bool = True


class MetricaModelo(BaseModel):
    nombre: str = Field(max_length=60)
    version: int = Field(ge=1)
    algoritmo: str = Field(max_length=80)
    estado: Literal["candidato", "activo", "retirado"]
    metricas: dict[str, Decimal]
    linea_base: dict[str, Decimal] = {}
    n_train: int = Field(ge=0)
    entrenado_en: datetime


class MetricasModelo(ArtifactBase):
    model_config = _cfg(
        {
            "id": "art-ml-01",
            "tipo": "metricas_modelo",
            "modelos": [
                {
                    "nombre": "riesgo_retraso",
                    "version": 3,
                    "algoritmo": "HistGradientBoostingClassifier",
                    "estado": "activo",
                    "metricas": {"roc_auc": "0.81", "brier": "0.162"},
                    "linea_base": {"roc_auc": "0.72", "brier": "0.191"},
                    "n_train": 8420,
                    "entrenado_en": "2026-11-03T06:00:00-05:00",
                }
            ],
            "datos_simulados": True,
        }
    )
    tipo: Literal["metricas_modelo"] = "metricas_modelo"
    modelos: list[MetricaModelo] = Field(min_length=1)
    datos_simulados: bool = True


class ItemCola(BaseModel):
    escalamiento_id: str = Field(max_length=64)
    sesion_id: str = Field(max_length=64)
    criterio: Criterio
    prioridad: Literal["alta", "media", "normal"]
    estado: Literal["pendiente", "tomado", "resuelto"]
    creado: datetime
    espera_s: int = Field(ge=0)
    resumen: str = Field(max_length=1000)
    guia: Guia | None = None


class ColaEscalamientos(ArtifactBase):
    model_config = _cfg(
        {
            "id": "art-cola-01",
            "tipo": "cola_escalamientos",
            "items": [
                {
                    "escalamiento_id": "b7c1d2e3-4f50-4a6b-8c7d-9e0f1a2b3c4d",
                    "sesion_id": SESION_EJ,
                    "criterio": "CRIT-005",
                    "prioridad": "alta",
                    "estado": "pendiente",
                    "creado": "2026-11-03T10:05:00-05:00",
                    "espera_s": 38,
                    "resumen": "Cliente consulta guía retenida por la POLFA con mercancía Clase 3.",
                    "guia": "TLX-310482-CO",
                }
            ],
        }
    )
    tipo: Literal["cola_escalamientos"] = "cola_escalamientos"
    items: list[ItemCola] = []


# --- unión discriminada -----------------------------------------------------------------------

MODELOS_ARTIFACT: tuple[type[ArtifactBase], ...] = (
    FormularioCotizacion,
    ResultadoCotizacion,
    FormularioGuia,
    LineaTiempoEnvio,
    MapaUbicacion,
    VeredictoMercancia,
    PlanEnvio,
    GuiaEmbalaje,
    FichaCobertura,
    FormularioPqrs,
    EstadoPlazo,
    ChecklistDocumentos,
    TicketPqrs,
    AvisoEscalamiento,
    Citas,
    RespuestasRapidas,
    Confirmacion,
    EncuestaSatisfaccion,
    TarjetasKpi,
    Grafico,
    TablaDatos,
    TarjetaPrediccion,
    MetricasModelo,
    ColaEscalamientos,
)

Artifact = Annotated[
    FormularioCotizacion
    | ResultadoCotizacion
    | FormularioGuia
    | LineaTiempoEnvio
    | MapaUbicacion
    | VeredictoMercancia
    | PlanEnvio
    | GuiaEmbalaje
    | FichaCobertura
    | FormularioPqrs
    | EstadoPlazo
    | ChecklistDocumentos
    | TicketPqrs
    | AvisoEscalamiento
    | Citas
    | RespuestasRapidas
    | Confirmacion
    | EncuestaSatisfaccion
    | TarjetasKpi
    | Grafico
    | TablaDatos
    | TarjetaPrediccion
    | MetricasModelo
    | ColaEscalamientos,
    Field(discriminator="tipo"),
]
Formulario = FormularioCotizacion | FormularioGuia | FormularioPqrs
