"""Logs JSON con request_id/turno_id; middleware de request id, tiempos y cabeceras de seguridad."""

import json
import logging
import time
import uuid
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)

CABECERAS_SEGURIDAD = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}


class _FormatoJson(logging.Formatter):
    CAMPOS_EXTRA = ("ruta", "metodo", "status", "ms", "turno_id", "sesion_id", "intencion", "latencias", "criterio")

    def format(self, record: logging.LogRecord) -> str:
        datos = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "nivel": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "request_id": request_id_var.get(),
        }
        datos |= {k: getattr(record, k) for k in self.CAMPOS_EXTRA if hasattr(record, k)}
        if record.exc_info:
            datos["exc"] = self.formatException(record.exc_info)
        return json.dumps(datos, ensure_ascii=False, default=str)


def configurar_logs(nivel: int = logging.INFO) -> None:
    manejador = logging.StreamHandler()
    manejador.setFormatter(_FormatoJson())
    raiz = logging.getLogger()
    raiz.handlers[:] = [manejador]
    raiz.setLevel(nivel)
    logging.getLogger("uvicorn.access").disabled = True  # el middleware ya registra cada petición


class MiddlewarePeticion(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        entrante = request.headers.get("x-request-id", "")
        rid = entrante if 8 <= len(entrante) <= 64 and entrante.replace("-", "").isalnum() else uuid.uuid4().hex
        token = request_id_var.set(rid)
        inicio = time.perf_counter()
        try:
            respuesta = await call_next(request)
        finally:
            request_id_var.reset(token)
        ms = round((time.perf_counter() - inicio) * 1000, 1)
        respuesta.headers["X-Request-ID"] = rid
        respuesta.headers["Server-Timing"] = f"app;dur={ms}"
        for k, v in CABECERAS_SEGURIDAD.items():
            respuesta.headers.setdefault(k, v)
        logging.getLogger("app.http").info(
            "peticion",
            extra={"ruta": request.url.path, "metodo": request.method, "status": respuesta.status_code, "ms": ms},
        )
        return respuesta
