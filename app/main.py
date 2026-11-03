"""Aplicación FastAPI: metadatos OpenAPI (Swagger), middlewares, manejo de errores y routers."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.ai.embeddings import get_embeddings
from app.ai.llm import get_llm
from app.api import health
from app.config import get_settings
from app.core import errors
from app.core.logging import MiddlewarePeticion, configurar_logs

DESCRIPCION = """
Backend del **agente de atención con IA local** de TransLogix Colombia S.A.S. (reto KODO TAKAI 2026).

* **IA 100 % local**: LFM3-1.7B (llama.cpp) para lenguaje y `bge-m3` (Ollama) para embeddings.
  Ningún dato sale del equipo.
* **RAG** sobre PostgreSQL + pgvector (búsqueda híbrida vectorial + texto completo en español).
* **Reglas de negocio deterministas**: el modelo no calcula tarifas, plazos ni decide escalamientos.
* **Chat con artifacts**: cada respuesta puede traer componentes de UI tipados (formularios, líneas de tiempo, tablas…).
  Ver `docs/frontend.md` y el esquema `Artifact` al final de esta página.

**Roles:** invitado (sin token), `cliente`, `asesor`, `admin`. Autentícate con *Authorize* usando el `access_token`
de `POST /api/v1/auth/login`.

**Errores:** RFC 9457 (`application/problem+json`) con `codigo` estable y `request_id` para soporte.
"""

TAGS = [
    {"name": "Autenticación", "description": "Registro, login, rotación de refresh tokens y perfil."},
    {"name": "Chat", "description": "Conversación con el agente (SSE o JSON) y artifacts de UI."},
    {"name": "Rastreo", "description": "Estado y trazabilidad de guías (`TLX-XXXXXX-CO`)."},
    {"name": "Cotización", "description": "Cálculo determinista de fletes según la matriz tarifaria."},
    {"name": "Cobertura", "description": "Municipios, hubs y trayectos disponibles."},
    {"name": "Mercancías", "description": "Mercancías peligrosas, prohibidas y requisitos (manual DOC-OPS-2026-03)."},
    {"name": "PQRS", "description": "Peticiones, quejas, reclamos e indemnizaciones (DOC-PQRS-2026-04)."},
    {"name": "Asesor", "description": "Cola de escalamientos y atención humana (human-in-the-loop)."},
    {
        "name": "Administración",
        "description": "Usuarios, métricas, conversaciones, base de conocimiento y chat administrativo.",
    },
    {"name": "Predicciones IA", "description": "Modelos que se autoentrenan: riesgo de retraso y demanda."},
    {"name": "Salud", "description": "Liveness y readiness."},
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    configurar_logs()
    yield
    await get_llm().cerrar()
    await get_embeddings().cerrar()


def crear_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(
        title="TransLogix IA — API del agente de atención",
        version="1.0.0",
        description=DESCRIPCION,
        openapi_tags=TAGS,
        lifespan=lifespan,
        contact={"name": "Equipo backend KODO TAKAI 2026"},
        servers=[{"url": "http://127.0.0.1:8100", "description": "Local"}],
        swagger_ui_parameters={"persistAuthorization": True, "displayRequestDuration": True, "tryItOutEnabled": True},
    )
    app.add_middleware(MiddlewarePeticion)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=s.cors_lista,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-Request-ID"],
        expose_headers=["X-Request-ID", "Retry-After", "Server-Timing"],
    )
    errors.registrar(app)
    app.include_router(health.router)
    for router in _routers_v1():
        app.include_router(router, prefix="/api/v1")
    from app.api.chat import router_admin

    app.include_router(router_admin, prefix="/api/v1")

    demo = Path(__file__).parent / "static" / "demo.html"
    if s.demo_enabled and demo.exists():

        @app.get("/demo", include_in_schema=False)
        async def _demo():
            return FileResponse(demo, media_type="text/html")

    return app


def _routers_v1():
    # Importación tardía: cada módulo de app/api expone `router`.
    import importlib

    for nombre in (
        "auth", "chat", "tracking", "cotizar", "cobertura", "mercancias", "pqrs", "asesor", "admin", "ml",
    ):  # fmt: skip
        try:
            yield importlib.import_module(f"app.api.{nombre}").router
        except ModuleNotFoundError as e:
            if e.name != f"app.api.{nombre}":
                raise


app = crear_app()
