"""Validador de reglas de escalamiento a humano (RF-ESC).

Las reglas llegan ya cargadas con la estructura de `reglas_escalacion_humana.json`; los umbrales y
literales se leen de `regla_evaluacion` / `parametros_generales` (no se usa eval()).

API:
- `evaluar_escalamiento(reglas: dict, ctx: ContextoTurno) -> list[CriterioDisparado]`: criterios
  disparados ordenados por prioridad D-13 (005 > 002 > 003 > 004 > 001). `[0]` es el que manda:
  su `accion` y su `mensaje_cliente` (literal del JSON) son los que se usan.
- `detectar_palabras_clave(texto, palabras) -> list[str]`: palabras/frases completas encontradas,
  sin importar mayúsculas ni tildes ("sic" no dispara con "básico").
Reglas: CRIT-003 solo cuando `ctx.flujo == 'pqrs'` (D-12). Un campo en None no dispara su criterio.
Error: REGLA_INVALIDA si una `regla_evaluacion` no trae el umbral esperado.
"""

import re
from dataclasses import dataclass, field

from app.domain import ErrorDominio
from app.domain.sanitizar import normalizar_para_busqueda

PRIORIDAD = ("CRIT-005", "CRIT-002", "CRIT-003", "CRIT-004", "CRIT-001")  # D-13


@dataclass(frozen=True)
class ContextoTurno:
    confidence_score: float | None = None
    texto_usuario: str = ""
    flujo: str = ""  # 'pqrs' | 'rastreo' | 'cotizacion' | 'normativa' | ...
    valor_declarado: float | None = None
    valor_reclamacion: float | None = None
    tipo_cuenta: str | None = None
    envios_mensuales_cuenta: int | None = None
    mercancia_peligrosa: bool = False
    requiere_refrigeracion: bool = False
    estado_envio: str | None = None


@dataclass(frozen=True)
class CriterioDisparado:
    id_criterio: str
    accion: str
    mensaje_cliente: str
    motivo: str
    palabras_detectadas: list[str] = field(default_factory=list)


def detectar_palabras_clave(texto: str, palabras: list[str]) -> list[str]:
    norm = f" {normalizar_para_busqueda(texto)} "
    return [p for p in palabras if f" {normalizar_para_busqueda(p)} " in norm]


def _numero(regla: str) -> float:
    m = re.search(r"[<>]=?\s*(\d+(?:\.\d+)?)", regla)
    if not m:
        raise ErrorDominio("REGLA_INVALIDA", f"La regla '{regla}' no trae un umbral numérico.")
    return float(m.group(1))


def _literal(regla: str) -> str:
    m = re.search(r"'([^']+)'", regla)
    if not m:
        raise ErrorDominio("REGLA_INVALIDA", f"La regla '{regla}' no trae un literal entre comillas.")
    return m.group(1)


def _supera(valor, umbral: float) -> bool:
    return valor is not None and valor > umbral


def _motivo(c: dict, ctx: ContextoTurno, umbral_confianza: float) -> tuple[str, list[str]] | None:
    """Devuelve (motivo, palabras) si el criterio dispara, o None."""
    regla = c.get("regla_evaluacion", "")
    match c["id_criterio"]:
        case "CRIT-001":
            if ctx.confidence_score is not None and ctx.confidence_score < umbral_confianza:
                return f"confidence_score {ctx.confidence_score:.2f} < {umbral_confianza}", []
        case "CRIT-002":
            palabras = detectar_palabras_clave(ctx.texto_usuario, c.get("keywords_disparadoras", []))
            if palabras:
                return "palabras clave: " + ", ".join(palabras), palabras
        case "CRIT-003":
            limite = _numero(regla)
            if ctx.flujo == "pqrs" and (_supera(ctx.valor_declarado, limite) or _supera(ctx.valor_reclamacion, limite)):
                return f"valor declarado o reclamado > {limite:,.0f} en flujo PQRS", []
        case "CRIT-004":
            if _supera(ctx.envios_mensuales_cuenta, _numero(regla)) or ctx.tipo_cuenta == _literal(regla):
                return "cuenta corporativa prioritaria", []
        case "CRIT-005":
            frio_con_novedad = ctx.requiere_refrigeracion and ctx.estado_envio == _literal(regla)
            if ctx.mercancia_peligrosa or frio_con_novedad:
                return "carga especial: mercancía peligrosa o cadena de frío con novedad", []
    return None


def evaluar_escalamiento(reglas: dict, ctx: ContextoTurno) -> list[CriterioDisparado]:
    umbral = reglas.get("parametros_generales", {}).get("confidence_score_minimo")
    criterios = reglas["criterios_escalacion"]
    if umbral is None:
        crit1 = next((c for c in criterios if c["id_criterio"] == "CRIT-001"), {})
        umbral = _numero(crit1.get("regla_evaluacion", "")) if crit1 else 0.0
    disparados = []
    for c in criterios:
        res = _motivo(c, ctx, float(umbral))
        if res:
            disparados.append(CriterioDisparado(c["id_criterio"], c["accion"], c["mensaje_cliente"], *res))
    orden = {cid: i for i, cid in enumerate(PRIORIDAD)}
    return sorted(disparados, key=lambda d: orden.get(d.id_criterio, len(PRIORIDAD)))
