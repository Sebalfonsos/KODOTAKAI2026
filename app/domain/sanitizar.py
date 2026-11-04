"""Saneamiento de texto de entrada y detección de guías.

API:
- `limpiar_texto(texto, max_len=4000) -> str`: NFC, sin caracteres de control (salvo \\n y \\t),
  sin espacios en los extremos y recortado a `max_len`.
- `normalizar_para_busqueda(texto) -> str`: minúsculas, sin tildes, signos -> espacio,
  espacios colapsados. Para comparar palabras clave y productos ("Ácido-Clorhídrico" -> "acido clorhidrico").
- `extraer_guias(texto) -> list[str]`: guías `TLX-\\d{6}-CO` en forma canónica, sin duplicados y en
  orden de aparición. Tolera minúsculas, espacios y guiones omitidos ("tlx 984021 co").
- `extraer_envio(texto, origenes, destinos) -> DatosEnvio`: producto y ciudades de "quiero enviar X de A a B".
"""

import re
import unicodedata
from dataclasses import dataclass

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


@dataclass(frozen=True)
class DatosEnvio:
    producto: str | None = None
    origen: str | None = None
    destino: str | None = None


_VERBO_ENVIO = re.compile(r"\b(?:enviar|mandar|despachar|transportar|envio|mando|despacho)\s+")
_FIN_PRODUCTO = re.compile(r"\s+(?:a|al|desde|hacia|para|por)\s|[.,;:?!]")
_ARTICULO = re.compile(r"^(?:un|una|unos|unas|el|la|los|las|mis?|este|esta|estos|estas|algunos|algunas)\s+")
_GENERICOS = {
    *("algo", "carga", "cosas", "encomienda", "envio", "mercancia", "mercancias"),
    *("paquete", "paquetes", "caja", "cajas", "producto", "productos"),
}


def _plegar(texto: str) -> str:
    """Minúsculas y sin tildes conservando la longitud: los índices sirven para recortar el texto original."""
    return "".join(unicodedata.normalize("NFKD", c)[0].lower()[0] for c in texto)


def _ciudades(plegado: str, nombres: list[str], preposiciones: str) -> tuple[str | None, int]:
    # Primero los nombres largos: "san andres" no debe ceder ante un municipio contenido en él.
    for nombre in sorted(nombres, key=len, reverse=True):
        base = normalizar_para_busqueda(nombre).removesuffix(" d c").replace(" ", r"\s+")
        m = re.search(rf"\s(?:{preposiciones})\s+(?:la\s+ciudad\s+de\s+)?{base}\b", plegado)
        if m:
            return nombre, m.start()
    return None, len(plegado)


def extraer_envio(texto: str, origenes: list[str], destinos: list[str]) -> DatosEnvio:
    """Sin LLM y sin suponer: lo que no se reconoce queda en None para que el formulario lo pida."""
    plegado = _plegar(texto)
    origen, corte_origen = _ciudades(plegado, origenes, "de|desde")
    destino, corte_destino = _ciudades(plegado, destinos, "a|al|hacia|para")
    verbo = _VERBO_ENVIO.search(plegado)
    if not verbo:
        return DatosEnvio(None, origen, destino)
    inicio = verbo.end()
    fin = min(corte_origen, corte_destino, len(plegado))
    # ponytail: una preposición dentro del nombre del producto ("cinta para embalar") recorta el nombre; el usuario
    # lo corrige en el campo "¿Qué contiene?" del formulario.
    otro = _FIN_PRODUCTO.search(plegado, inicio)
    if otro:
        fin = min(fin, otro.start())
    fragmento = texto[inicio : max(inicio, fin)].strip()
    sin_articulo = _ARTICULO.match(_plegar(fragmento))
    if sin_articulo:
        fragmento = fragmento[sin_articulo.end() :]
    producto = fragmento[:200] or None
    if producto and normalizar_para_busqueda(producto) in _GENERICOS:
        producto = None
    return DatosEnvio(producto, origen, destino)
