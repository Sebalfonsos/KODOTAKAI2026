"""Salud del servicio: liveness y readiness con estado y latencia de cada componente."""

import time

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.ai.embeddings import get_embeddings
from app.ai.llm import get_llm
from app.db import engine

router = APIRouter(tags=["Salud"])


class Componente(BaseModel):
    ok: bool
    latencia_ms: float


class EstadoSalud(BaseModel):
    estado: str = Field(examples=["ok"], description="ok | degradado")
    componentes: dict[str, Componente]


@router.get("/health", summary="Liveness", response_model=dict[str, str])
async def vivo() -> dict[str, str]:
    """Responde 200 si el proceso está vivo. No consulta dependencias."""
    return {"estado": "ok"}


@router.get(
    "/health/ready",
    summary="Readiness con estado de BD, LLM y embeddings",
    response_model=EstadoSalud,
    responses={503: {"model": EstadoSalud, "description": "Algún componente no responde"}},
)
async def listo():
    """200 si BD, LLM local y embeddings responden; 503 (estado `degradado`) si alguno falla."""
    inicio = time.perf_counter()
    try:
        async with engine.connect() as c:
            await c.execute(text("SELECT 1"))
        bd = Componente(ok=True, latencia_ms=round((time.perf_counter() - inicio) * 1000, 1))
    except Exception:  # noqa: BLE001 - cualquier fallo de BD es "no listo"
        bd = Componente(ok=False, latencia_ms=round((time.perf_counter() - inicio) * 1000, 1))
    llm_ok, llm_ms = await get_llm().salud()
    emb_ok, emb_ms = await get_embeddings().salud()
    comp = {
        "base_datos": bd,
        "llm": Componente(ok=llm_ok, latencia_ms=llm_ms),
        "embeddings": Componente(ok=emb_ok, latencia_ms=emb_ms),
    }
    ok = all(c.ok for c in comp.values())
    cuerpo = EstadoSalud(estado="ok" if ok else "degradado", componentes=comp)
    return JSONResponse(cuerpo.model_dump(), status_code=200 if ok else 503)
