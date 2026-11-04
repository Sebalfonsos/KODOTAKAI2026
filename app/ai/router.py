"""Enrutador de intención: reglas deterministas (< 1 ms) y, solo si no deciden, el LLM con JSON forzado (~0,4 s)."""

import re
from dataclasses import dataclass, field

from app.ai.llm import ClienteLLM
from app.ai.prompts import SISTEMA_ROUTER
from app.domain.mercancias import evaluar_producto
from app.domain.sanitizar import extraer_guias, normalizar_para_busqueda

INTENCIONES_CLIENTE = (
    "saludo",
    "rastrear",
    "cotizar",
    "enviar",
    "mercancia",
    "embalaje",
    "cobertura",
    "pqrs_radicar",
    "pqrs_info",
    "asesor",
    "general",
    "fuera_de_alcance",
)


@dataclass
class Ruta:
    intencion: str
    certeza: float  # 1.0 regla determinista; 0.85 LLM
    fuente: str  # "regla" | "llm" | "contexto"
    guia: str | None = None
    entidades: dict = field(default_factory=dict)


def _hay(texto: str, *patrones: str) -> bool:
    return any(re.search(rf"\b{p}", texto) for p in patrones)


_SALUDOS = {"hola", "buenas", "buenos dias", "buenas tardes", "buenas noches", "hey", "saludos", "buen dia", "holi"}
_PREGUNTA_INFO = (
    "que documentos",
    "que papeles",
    "cuanto tiempo",
    "cuales son",
    "como reclamo",
    "como hago",
    "plazo",
    "que necesito",
    "requisitos",
    "como funciona",
    "cuantos dias",
)
_VERBOS_ENVIO = (
    "enviar",
    "mandar",
    "transportar",
    "despachar",
    "llevar",
    "reciben",
    "aceptan",
    "puedo",
    "se puede",
    "envian",
)


# "Quiero enviar X" pide despachar algo; "¿puedo enviar X?" solo pregunta si se acepta (intención mercancia).
_QUIERE_ENVIAR = re.compile(
    r"\b(?:quiero|quisiera|necesito|deseo|voy a|vamos a|tengo que|me gustaria|ayudame a)\s+(?:\w+\s+)?"
    r"(?:enviar|mandar|despachar|transportar)\b"
    r"|^(?:enviar|mandar|despachar)\s"
    r"|\bcomo\s+(?:enviar|mandar|envio|mando|despacho)\b"
)


def por_reglas(texto: str) -> Ruta | None:
    t = normalizar_para_busqueda(texto)
    guias = extraer_guias(texto)
    # Pedir una persona gana a todo: mencionar la guía o el daño no puede dejar al cliente sin asesor.
    if _hay(t, "asesor", "humano", "persona real", "agente humano", "operador"):
        return Ruta("asesor", 1.0, "regla", guias[0] if guias else None)
    novedad = _hay(
        t,
        "reclam",
        "queja",
        "indemniz",
        "rot[oa]",
        "partid",
        "dan[oa]",
        "danad",
        "aplast",
        "averi",
        "perdi",
        "extravi",
        "no llego",
        "saque",
        "robad",
        "incomplet",
    )
    if novedad:
        if any(p in t for p in _PREGUNTA_INFO) and not guias:
            return Ruta("pqrs_info", 1.0, "regla")
        return Ruta("pqrs_radicar", 1.0, "regla", guias[0] if guias else None)
    if guias:
        return Ruta("rastrear", 1.0, "regla", guias[0])
    if t in _SALUDOS or (len(t.split()) <= 3 and t.split() and t.split()[0] in {"hola", "buenas", "buenos"}):
        return Ruta("saludo", 1.0, "regla")
    if _hay(
        t,
        "cotiz",
        "cuanto cuesta",
        "cuanto vale",
        "cuanto sale",
        "cuanto cobran",
        "precio",
        "tarifa",
        "flete",
        "valor del envio",
    ):
        return Ruta("cotizar", 1.0, "regla")
    if _hay(
        t, "rastre", "donde esta mi", "donde va mi", "seguimiento", "mi guia", "mi paquete", "mi envio", "estado de mi"
    ):
        return Ruta("rastrear", 1.0, "regla")
    if _hay(t, "seguro", "poliza", "asegur", "politica", "horario", "same day", "mismo dia"):
        return Ruta("general", 1.0, "regla")
    if _hay(t, "embal", "empac", "empaque", "como envuelvo", "como protejo"):
        return Ruta("embalaje", 1.0, "regla")
    veredicto = evaluar_producto(texto).veredicto
    if _QUIERE_ENVIAR.search(t) and veredicto != "prohibido":
        return Ruta("enviar", 1.0, "regla")
    if any(v in t for v in _VERBOS_ENVIO) and veredicto != "desconocido":
        return Ruta("mercancia", 1.0, "regla")
    if _hay(
        t,
        "llegan a",
        "cobertura",
        "cubren",
        "hacen envios a",
        "envian a",
        "tiempo de entrega",
        "cuanto se demora",
        "cuanto tarda",
        "same day",
        "mismo dia",
    ):
        return Ruta("cobertura", 1.0, "regla")
    return None


ESQUEMA = {
    "type": "object",
    "properties": {
        "intencion": {"type": "string", "enum": list(INTENCIONES_CLIENTE)},
        "producto": {"type": ["string", "null"]},
        "ciudad": {"type": ["string", "null"]},
    },
    "required": ["intencion", "producto", "ciudad"],
}

_GUIA_INTENCIONES = (
    "saludo: saluda. rastrear: estado de un envío o guía. cotizar: precio de un envío. "
    "enviar: quiere despachar un producto y necesita los pasos y el formulario. "
    "mercancia: si un producto se puede enviar (peligroso o prohibido). embalaje: cómo empacar. "
    "cobertura: si llegan a una ciudad o cuánto tardan. pqrs_radicar: quiere reclamar o reportar daño/pérdida/queja. "
    "pqrs_info: pregunta requisitos o plazos de reclamos. asesor: pide hablar con una persona. "
    "general: otra pregunta sobre servicios, normas o políticas de la empresa. "
    "fuera_de_alcance: nada que ver con logística (chistes, tareas, programación, política)."
)


async def por_llm(llm: ClienteLLM, texto: str) -> Ruta:
    datos = await llm.extraer_json(
        [
            {"role": "system", "content": SISTEMA_ROUTER},
            {"role": "user", "content": f"Intenciones: {_GUIA_INTENCIONES}\n\nMensaje: {texto}"},
        ],
        ESQUEMA,
        max_tokens=60,
    )
    intencion = datos.get("intencion") if datos.get("intencion") in INTENCIONES_CLIENTE else "general"
    entidades = {k: v for k in ("producto", "ciudad") if isinstance(v := datos.get(k), str) and v.strip()}
    return Ruta(intencion, 0.85, "llm", entidades=entidades)


async def enrutar(llm: ClienteLLM, texto: str) -> Ruta:
    return por_reglas(texto) or await por_llm(llm, texto)


ESQUEMA_COTIZACION = {
    "type": "object",
    "properties": {
        k: {"type": ["number", "null"]} for k in ("alto_cm", "ancho_cm", "largo_cm", "peso_kg", "valor_declarado_cop")
    }
    | {
        "origen": {"type": ["string", "null"]},
        "destino": {"type": ["string", "null"]},
        "servicio": {
            "type": ["string", "null"],
            "enum": ["paqueteria", "carga", "cadena_frio", "mercancia_peligrosa", None],
        },
    },
    "required": ["origen", "destino", "alto_cm", "ancho_cm", "largo_cm", "peso_kg", "valor_declarado_cop", "servicio"],
}


async def extraer_cotizacion(llm: ClienteLLM, texto: str) -> dict:
    """Campos de cotización mencionados explícitamente. Solo se llama si el mensaje trae cifras o ciudades."""
    datos = await llm.extraer_json(
        [
            {"role": "system", "content": SISTEMA_ROUTER},
            {
                "role": "user",
                "content": "Extrae los datos de envío. Dimensiones en cm, peso en kg, valor declarado en pesos COP "
                '("2 millones" = 2000000). servicio: paqueteria, carga, cadena_frio o mercancia_peligrosa.\n\n'
                f"Mensaje: {texto}",
            },
        ],
        ESQUEMA_COTIZACION,
        max_tokens=120,
    )
    return {k: v for k, v in datos.items() if v not in (None, "", 0)}
