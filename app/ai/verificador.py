"""Verificador anti-alucinación: la respuesta del LLM no puede afirmar nada que el contexto no respalde.

Comprobaciones (deterministas, < 1 ms):
1. Cifras: todo número del texto debe aparecer en hechos/contexto/pregunta (normalizado sin separadores).
2. Guías: ninguna guía TLX que no esté en el contexto.
3. Polaridad: si el veredicto determinista es «prohibido», el texto no puede afirmar que se puede enviar (y viceversa).
"""

import re
from dataclasses import dataclass

from app.domain.sanitizar import extraer_guias, normalizar_para_busqueda

_NUM = re.compile(r"\d[\d.,]*\d|\d")
_AFIRMA = re.compile(
    r"\b(si,? (se )?puede|si,? puedes|puedes enviar|puede enviar|podemos (enviar|transportar|recibir)|"
    r"aceptamos|se acepta|esta permitido|es posible enviar|si lo recibimos|si transportamos)\b"
)
_NIEGA = re.compile(
    r"\b(no (se )?(puede|puedes|podemos|aceptamos|acepta|transportamos|recibimos)|prohibid[oa]s?|no esta permitido)\b"
)


_GUIA = re.compile(r"TLX\W*\d{6}\W*CO", re.I)


def _respuesta_numeros(texto: str) -> set[str]:
    """Cada número de la respuesta, solo dígitos ("$190.975" -> "190975", "45,5" -> "455")."""
    return {re.sub(r"\D", "", n).lstrip("0") or "0" for n in _NUM.findall(_GUIA.sub(" ", texto))}


def _fuente_numeros(texto: str) -> set[str]:
    """Formas aceptadas en las fuentes: solo dígitos y, si hay decimales, también la parte entera."""
    salida = set()
    for n in _NUM.findall(_GUIA.sub(" ", texto)):
        salida.add(re.sub(r"\D", "", n).lstrip("0") or "0")
        decimal = re.match(r"^(.*?)[.,](\d{1,2})$", n)
        if decimal:
            salida.add(re.sub(r"\D", "", decimal.group(1)).lstrip("0") or "0")
    return salida


@dataclass(frozen=True)
class Verificacion:
    ok: bool
    motivo: str | None = None


def verificar(respuesta: str, fuentes: str, veredicto: str | None = None) -> Verificacion:
    norm_resp = normalizar_para_busqueda(respuesta)
    if set(extraer_guias(respuesta)) - set(extraer_guias(fuentes)):
        return Verificacion(False, "guia_inventada")
    # Números de un dígito ("3 frases", "1 litro") pueden venir de la redacción; solo se exige respaldo a los demás.
    extra = {n for n in _respuesta_numeros(respuesta) - _fuente_numeros(fuentes) if len(n) > 1}
    if extra:
        return Verificacion(False, f"cifras_sin_respaldo:{','.join(sorted(extra))}")
    if veredicto == "prohibido" and _AFIRMA.search(norm_resp) and not _NIEGA.search(norm_resp):
        return Verificacion(False, "contradice_prohibicion")
    if veredicto in ("permitido", "restringido", "solo_ftl") and re.search(r"\bprohibid[oa]\b", norm_resp):
        return Verificacion(False, "contradice_veredicto")
    return Verificacion(True)
