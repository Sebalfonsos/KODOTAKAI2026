"""Saneamiento de texto de entrada y detección de guías.

API:
- `limpiar_texto(texto, max_len=4000) -> str`: NFC, sin caracteres de control (salvo \\n y \\t),
  sin espacios en los extremos y recortado a `max_len`.
- `normalizar_para_busqueda(texto) -> str`: minúsculas, sin tildes, signos -> espacio,
  espacios colapsados. Para comparar palabras clave y productos ("Ácido-Clorhídrico" -> "acido clorhidrico").
- `extraer_guias(texto) -> list[str]`: guías `TLX-\\d{6}-CO` en forma canónica, sin duplicados y en
  orden de aparición. Tolera minúsculas, espacios y guiones omitidos ("tlx 984021 co").
"""

import re
import unicodedata

_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")
_NO_ALFANUM = re.compile(r"[^a-z0-9]+")
_GUIA = re.compile(r"\bTLX[\s-]*(\d(?:\s*\d){5})[\s-]*CO\b", re.IGNORECASE)


def limpiar_texto(texto: str, max_len: int = 4000) -> str:
    texto = _CONTROL.sub("", unicodedata.normalize("NFC", texto))
    return texto.strip()[:max_len]


def normalizar_para_busqueda(texto: str) -> str:
    sin_tildes = "".join(c for c in unicodedata.normalize("NFKD", texto.lower()) if not unicodedata.combining(c))
    # ponytail: NFKD convierte ñ en n; da igual para comparar porque ambos lados se normalizan igual.
    return _NO_ALFANUM.sub(" ", sin_tildes).strip()


def extraer_guias(texto: str) -> list[str]:
    guias = (f"TLX-{re.sub(r'\s', '', m.group(1))}-CO" for m in _GUIA.finditer(texto))
    return list(dict.fromkeys(guias))
