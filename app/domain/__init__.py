"""Dominio TransLogix: lógica de negocio pura (sin BD, red ni FastAPI).

Los errores de negocio se lanzan como `ErrorDominio(codigo, mensaje)`: `codigo` es estable
(p. ej. `TRAYECTO_INEXISTENTE`) y `mensaje` va en español, listo para el cliente.
"""

from decimal import ROUND_HALF_UP, Decimal


class ErrorDominio(Exception):
    """Error de negocio con código estable y mensaje para el cliente."""

    def __init__(self, codigo: str, mensaje: str):
        super().__init__(f"{codigo}: {mensaje}")
        self.codigo = codigo
        self.mensaje = mensaje


def redondear_pesos(valor: Decimal) -> Decimal:
    """Redondea a pesos enteros con ROUND_HALF_UP (0,5 sube). Solo para el total mostrado."""
    return valor.quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def a_decimal(valor) -> Decimal:
    """Convierte int/float/str/Decimal a Decimal sin arrastrar el error binario del float."""
    return valor if isinstance(valor, Decimal) else Decimal(str(valor))
