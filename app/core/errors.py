"""Errores HTTP en formato RFC 9457 (`application/problem+json`)."""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import request_id_var

log = logging.getLogger("app.errors")
PROBLEM = "application/problem+json"

TITULOS = {
    400: "Solicitud inválida",
    401: "No autenticado",
    403: "Prohibido",
    404: "No encontrado",
    405: "Método no permitido",
    409: "Conflicto",
    413: "Archivo demasiado grande",
    415: "Tipo de contenido no soportado",
    422: "Datos inválidos",
    429: "Demasiadas solicitudes",
    500: "Error interno",
    503: "Servicio no disponible",
    504: "Tiempo de espera agotado",
}


class Problema(BaseModel):
    """Cuerpo de error estándar (RFC 9457)."""

    type: str = Field(default="about:blank", examples=["https://translogix.demo/errores/trayecto-inexistente"])
    title: str = Field(examples=["No encontrado"])
    status: int = Field(examples=[404])
    detail: str | None = Field(default=None, examples=["No existe la guía TLX-000000-CO."])
    instance: str | None = Field(default=None, examples=["/api/v1/tracking/TLX-000000-CO"])
    codigo: str | None = Field(
        default=None, description="Código estable para el frontend", examples=["GUIA_NO_ENCONTRADA"]
    )
    request_id: str | None = None
    errores: list[dict] | None = Field(default=None, description="Detalle por campo (422)")


class ApiError(Exception):
    """Lanzar desde cualquier capa para responder un problema HTTP semántico."""

    def __init__(
        self,
        status: int,
        detail: str,
        codigo: str | None = None,
        headers: dict[str, str] | None = None,
        errores: list[dict] | None = None,
    ):
        self.status, self.detail, self.codigo, self.headers, self.errores = status, detail, codigo, headers, errores


def problema(request: Request, status: int, detail: str | None, codigo: str | None = None, errores=None, headers=None):
    tipo = f"https://translogix.demo/errores/{codigo.lower().replace('_', '-')}" if codigo else "about:blank"
    cuerpo = Problema(
        type=tipo,
        title=TITULOS.get(status, "Error"),
        status=status,
        detail=detail,
        instance=request.url.path,
        codigo=codigo,
        request_id=request_id_var.get(),
        errores=errores,
    )
    return JSONResponse(cuerpo.model_dump(exclude_none=True), status_code=status, media_type=PROBLEM, headers=headers)


def _limpiar(err: dict) -> dict:
    # No devolvemos el valor recibido (puede contener datos personales), solo ubicación y motivo.
    return {
        "campo": ".".join(str(p) for p in err.get("loc", []) if p != "body"),
        "mensaje": err.get("msg"),
        "tipo": err.get("type"),
    }


def registrar(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api(request: Request, exc: ApiError):
        return problema(request, exc.status, exc.detail, exc.codigo, exc.errores, exc.headers)

    @app.exception_handler(RequestValidationError)
    async def _validacion(request: Request, exc: RequestValidationError):
        errores = [_limpiar(e) for e in exc.errors()]
        return problema(request, 422, "Revisa los campos indicados.", "VALIDACION", errores)

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException):
        detalle = exc.detail if isinstance(exc.detail, str) else None
        if detalle in ("Not Found", "Method Not Allowed"):  # textos por defecto de Starlette, en inglés
            detalle = (
                "La ruta solicitada no existe." if exc.status_code == 404 else "Método no permitido para esta ruta."
            )
        return problema(request, exc.status_code, detalle, None, None, getattr(exc, "headers", None))

    @app.exception_handler(Exception)
    async def _inesperado(request: Request, exc: Exception):
        log.exception("error_no_controlado", extra={"ruta": request.url.path})
        return problema(
            request, 500, "Ocurrió un error inesperado. Usa el request_id para reportarlo.", "ERROR_INTERNO"
        )


# Respuestas de error reutilizables para documentar endpoints en OpenAPI.
def respuestas(*codigos: int) -> dict:
    return {c: {"model": Problema, "content": {PROBLEM: {}}, "description": TITULOS.get(c, "Error")} for c in codigos}
