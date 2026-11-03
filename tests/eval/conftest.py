"""Fixtures de evaluación: BD de pruebas (TEST_DATABASE_URL) con esquema creado y corpus RAG ingerido de verdad."""

import time

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.models  # noqa: F401  (registra todas las tablas)
from app.ai import rag
from app.ai.embeddings import ClienteEmbeddings
from app.config import get_settings
from app.models import Base, Documento

CODIGOS_PRUEBA = ("TEST-DOC-RAG",)


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def engine_eval():
    s = get_settings()
    if not s.test_database_url:
        pytest.skip("TEST_DATABASE_URL no está configurada")
    try:
        async with httpx.AsyncClient(timeout=3) as http:
            (await http.get(f"{s.ollama_url}/api/tags")).raise_for_status()
    except httpx.HTTPError:
        pytest.skip("Ollama no responde: make eval requiere embeddings reales")
    engine = create_async_engine(s.test_database_url)
    async with engine.begin() as con:
        await con.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await con.execute(text("CREATE EXTENSION IF NOT EXISTS citext"))
        await con.execute(text("CREATE SEQUENCE IF NOT EXISTS pqrs_radicado_seq"))
        await con.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def embeddings_eval():
    s = get_settings()
    cliente = ClienteEmbeddings(s.ollama_url, s.embed_model, s.embed_num_gpu)
    yield cliente
    await cliente.cerrar()


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def corpus_ingerido(engine_eval, embeddings_eval):
    """Borra el corpus en la BD de pruebas, lo ingiere desde cero y devuelve (resumen, segundos)."""
    Sesion = async_sessionmaker(engine_eval, expire_on_commit=False)
    codigos = [c for c, *_ in rag.corpus(get_settings().datos_dir)] + list(CODIGOS_PRUEBA)
    async with Sesion() as session:
        await session.execute(delete(Documento).where(Documento.codigo.in_(codigos)))
        inicio = time.perf_counter()
        resumen = await rag.ingestar_corpus(session, get_settings().datos_dir, embeddings_eval)
        await session.commit()
    return resumen, time.perf_counter() - inicio


@pytest_asyncio.fixture(loop_scope="session")
async def session_eval(engine_eval, corpus_ingerido):
    async with async_sessionmaker(engine_eval, expire_on_commit=False)() as session:
        yield session
