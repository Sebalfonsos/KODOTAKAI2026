"""Evaluación T-RAG contra PostgreSQL + pgvector y bge-m3 reales (make eval)."""

import json
import statistics
import time
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.ai import rag
from app.ai.embeddings import ClienteEmbeddings
from app.config import get_settings
from app.domain.sanitizar import normalizar_para_busqueda
from app.models import Chunk, Documento

pytestmark = [pytest.mark.eval, pytest.mark.asyncio(loop_scope="session")]

CONSULTAS = json.loads((Path(__file__).parent / "consultas_rag.json").read_text(encoding="utf-8"))
K = 4
RECALL_MIN = 0.9


def _acierta(resultados, esperados) -> bool:
    return any(
        r.doc_codigo == doc and normalizar_para_busqueda(frag) in normalizar_para_busqueda(r.seccion)
        for r in resultados
        for doc, frag in esperados
    )


def _percentiles(ms: list[float]) -> str:
    q = statistics.quantiles(ms, n=20)
    return f"p50={statistics.median(ms):.0f} ms p95={q[18]:.0f} ms (n={len(ms)})"


async def test_ingesta_idempotente(session_eval, corpus_ingerido, embeddings_eval):
    resumen, segundos = corpus_ingerido
    assert resumen["documentos"] == 5 and resumen["omitidos"] == 0 and resumen["chunks_nuevos"] > 0
    por_doc = dict(
        (
            await session_eval.execute(
                select(Documento.codigo, func.count(Chunk.id)).join(Chunk).group_by(Documento.codigo)
            )
        ).all()
    )
    print(f"\n[RAG] ingesta inicial {resumen} en {segundos:.1f} s; chunks por documento: {por_doc}")
    assert sum(por_doc.values()) == resumen["chunks_nuevos"]

    otra = await rag.ingestar_corpus(session_eval, get_settings().datos_dir, embeddings_eval)
    assert otra == {"documentos": 5, "chunks_nuevos": 0, "omitidos": 5}


async def test_documento_modificado_reemplaza_chunks(session_eval, embeddings_eval):
    md = "# Doc de prueba\n\n## 1. Uno\nTexto uno.\n\n## 2. Dos\nTexto dos.\n"
    r1 = await rag.ingestar_documento(
        session_eval, "TEST-DOC-RAG", "Doc de prueba", "pqrs", md, "test", embeddings_eval
    )
    assert r1 == {"codigo": "TEST-DOC-RAG", "chunks": 2, "omitido": False}
    r2 = await rag.ingestar_documento(
        session_eval, "TEST-DOC-RAG", "Doc de prueba", "pqrs", md, "test", embeddings_eval
    )
    assert r2["omitido"]
    r3 = await rag.ingestar_documento(
        session_eval,
        "TEST-DOC-RAG",
        "Doc de prueba",
        "pqrs",
        md + "\n## 3. Tres\nTexto tres.\n",
        "test",
        embeddings_eval,
    )
    assert r3["chunks"] == 3
    n = await session_eval.scalar(
        select(func.count(Chunk.id)).join(Documento).where(Documento.codigo == "TEST-DOC-RAG")
    )
    assert n == 3
    await session_eval.rollback()


async def test_filtro_por_tipo(session_eval, embeddings_eval):
    res = await rag.buscar(session_eval, "¿llegan a Quibdó?", k=4, tipos=["cobertura"], embeddings=embeddings_eval)
    assert res and all(r.metadatos["tipo"] == "cobertura" for r in res)
    assert res[0].seccion == "Cobertura Quibdó"
    assert 0 < res[0].score_vector <= 1


async def test_recall_t_rag_y_latencias(session_eval, embeddings_eval):
    s = get_settings()
    sin_cache = ClienteEmbeddings(s.ollama_url, s.embed_model, s.embed_num_gpu, cache_max=0)
    lat_fria, lat_cache, fallos = [], [], []
    try:
        for c in CONSULTAS:
            inicio = time.perf_counter()
            res = await rag.buscar(session_eval, c["consulta"], k=K, embeddings=sin_cache)
            lat_fria.append((time.perf_counter() - inicio) * 1000)
            if not _acierta(res, c["esperados"]):
                fallos.append((c["id"], c["consulta"], [(r.doc_codigo, r.seccion[:60]) for r in res]))
        for c in CONSULTAS:
            await embeddings_eval.embeber_consulta(c["consulta"])  # calienta la caché
            inicio = time.perf_counter()
            await rag.buscar(session_eval, c["consulta"], k=K, embeddings=embeddings_eval)
            lat_cache.append((time.perf_counter() - inicio) * 1000)
        emb = []
        for c in CONSULTAS[:10]:
            inicio = time.perf_counter()
            await sin_cache.embeber([c["consulta"]])
            emb.append((time.perf_counter() - inicio) * 1000)
    finally:
        await sin_cache.cerrar()

    recall = 1 - len(fallos) / len(CONSULTAS)
    print(f"\n[RAG] recall@{K} = {recall:.3f} ({len(CONSULTAS) - len(fallos)}/{len(CONSULTAS)})")
    print(f"[RAG] buscar sin caché de embedding: {_percentiles(lat_fria)}")
    print(f"[RAG] buscar con caché de embedding: {_percentiles(lat_cache)}")
    print(f"[RAG] solo embedding de consulta (bge-m3 CPU): {_percentiles(emb)}")
    for f in fallos:
        print(f"[RAG] FALLO {f}")
    assert recall >= RECALL_MIN, fallos
