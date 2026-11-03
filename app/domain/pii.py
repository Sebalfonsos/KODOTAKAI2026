"""Enmascaramiento de datos personales (Ley 1581 de 2012).

API:
- `enmascarar_digitos(valor, visibles=4) -> str`: cambia por `*` todos los dígitos menos los últimos
  `visibles`, conservando el formato ("C.C. 16.789.432" -> "C.C. **.**9.432").
- `enmascarar_documento`, `enmascarar_telefono`, `enmascarar_nit`: alias semánticos de lo anterior.
- `enmascarar_nombre(nombre) -> str`: solo iniciales ("Roberto Bermúdez" -> "R. B.").
- `enmascarar_texto(texto) -> str`: busca teléfonos, NIT y cédulas dentro de texto libre
  ("Asignado a conductor X (Tel: 310-987-6543)") y los enmascara. No toca montos, fechas ni guías.
"""

import re


def enmascarar_digitos(valor: str, visibles: int = 4) -> str:
    total = sum(c.isdigit() for c in valor)
    vistos = 0
    salida = []
    for c in valor:
        if c.isdigit():
            vistos += 1
            salida.append(c if vistos > total - visibles else "*")
        else:
            salida.append(c)
    return "".join(salida)


def enmascarar_nombre(nombre: str) -> str:
    """Solo iniciales: "Ing. Roberto Bermúdez" -> "I. R. B." (listados de administración)."""
    return " ".join(f"{p[0]}." for p in nombre.split() if p[0].isalpha())


enmascarar_documento = enmascarar_digitos
enmascarar_telefono = enmascarar_digitos
enmascarar_nit = enmascarar_digitos

_SEP = r"[\s.-]?"
_PATRONES = [
    # Celular (3xx) o fijo nacional (60x), con o sin +57.
    re.compile(rf"(?:\+?57{_SEP})?(?<!\d)(?:3\d\d|60\d){_SEP}\d{{3}}{_SEP}\d{{4}}(?!\d)"),
    # NIT con dígito de verificación: 900.123.456-7
    re.compile(r"(?<!\d)\d{3}\.?\d{3}\.?\d{3}-\d(?!\d)"),
    # Cédula precedida de su marcador: C.C. 16.789.432, cédula 1234567890, CC: 79.000.111
    re.compile(
        r"\b(?:C\.?\s?C\.?|c[eé]dula|documento(?: de identidad)?)\s*(?:No\.?|#|:)?\s*"
        r"\d{1,3}(?:[.\s]?\d{3}){1,3}(?!\d)",
        re.IGNORECASE,
    ),
]


def enmascarar_texto(texto: str) -> str:
    for patron in _PATRONES:
        texto = patron.sub(lambda m: enmascarar_digitos(m.group(0)), texto)
    return texto
