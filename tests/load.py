"""Benchmark de latencia y carga contra la API real (LLM, embeddings y BD reales).

Uso: `RATE_CHAT_POR_MIN=10000 make dev` (todas las conversaciones salen de la misma IP)
y luego `uv run python tests/load.py [--concurrencias 1 4 8] [--rondas 2]`.
Reporta p50/p95 por etapa (router, tool, retrieval, primer token, LLM, total), tiempo al primer evento y errores.
"""

import argparse
import asyncio
import json
import shutil
import statistics
import subprocess
import time

import httpx

BASE = "http://127.0.0.1:8100/api/v1"
MENSAJES = [
    "hola",
    "TLX-984021-CO",
    "¿Puedo enviar un perro de Bogotá a Medellín?",
    "quiero cotizar de Bogotá a Cali una caja de 30x30x30 de 5 kg con valor de 300000",
    "¿llegan a Quibdó?",
    "¿qué papeles necesito para reclamar por un daño?",
    "¿cómo embalo una botella de vino?",
    "¿puedo mandar baterías de litio sueltas?",
]


async def conversacion(c: httpx.AsyncClient, resultados: list) -> None:
    sid = (await c.post(f"{BASE}/chat/sesiones")).json()["id"]
    for texto in MENSAJES:
        inicio = time.perf_counter()
        primero, fin, error = None, None, None
        async with c.stream(
            "POST", f"{BASE}/chat/sesiones/{sid}/mensajes", json={"tipo": "texto", "texto": texto}
        ) as r:
            if r.status_code != 200:
                error = r.status_code
            async for linea in r.aiter_lines():
                if linea.startswith("event: ") and primero is None and linea != "event: meta":
                    primero = (time.perf_counter() - inicio) * 1000
                if linea.startswith("data: ") and '"latencias_ms"' in linea:
                    fin = json.loads(linea[6:])
                if linea == "event: error":
                    error = "evento_error"
        resultados.append(
            {
                "texto": texto,
                "primer_evento": primero,
                "fin": fin,
                "error": error,
                "total_cliente": (time.perf_counter() - inicio) * 1000,
            }
        )


def pct(valores: list[float], p: float) -> float:
    v = sorted(x for x in valores if x is not None)
    return round(v[min(len(v) - 1, int(p * (len(v) - 1) + 0.5))], 1) if v else float("nan")


def vram() -> str:
    try:
        return subprocess.run(
            [
                shutil.which("nvidia-smi") or "nvidia-smi",
                "--query-gpu=memory.used,memory.total",
                "--format=csv,noheader",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "n/d"


async def main(concurrencias: list[int], rondas: int) -> None:
    async with httpx.AsyncClient(timeout=120) as c:
        for n in concurrencias:
            resultados: list = []
            inicio = time.perf_counter()
            for _ in range(rondas):
                await asyncio.gather(*(conversacion(c, resultados) for _ in range(n)))
            dur = time.perf_counter() - inicio
            etapas = {
                e: [r["fin"]["latencias_ms"].get(e) for r in resultados if r["fin"]]
                for e in ("router", "tool", "retrieval", "llm_first_token", "llm_total", "total")
            }
            print(
                f"\n## Concurrencia {n} — {len(resultados)} turnos en {dur:.1f} s, errores: "
                f"{sum(1 for r in resultados if r['error'])}, VRAM: {vram()}"
            )
            print("| etapa | p50 ms | p95 ms |\n|---|---|---|")
            print(
                f"| primer evento (cliente) | {pct([r['primer_evento'] for r in resultados], 0.5)} | "
                f"{pct([r['primer_evento'] for r in resultados], 0.95)} |"
            )
            for e, v in etapas.items():
                print(f"| {e} | {pct(v, 0.5)} | {pct(v, 0.95)} |")
            print(
                f"| total (cliente) | {pct([r['total_cliente'] for r in resultados], 0.5)} | "
                f"{pct([r['total_cliente'] for r in resultados], 0.95)} |"
            )
            por_texto = {}
            for r in resultados:
                por_texto.setdefault(r["texto"][:40], []).append(r["total_cliente"])
            print("\n| mensaje | mediana ms |\n|---|---|")
            for t, v in por_texto.items():
                print(f"| {t} | {round(statistics.median(v), 1)} |")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--concurrencias", type=int, nargs="+", default=[1, 4, 8])
    p.add_argument("--rondas", type=int, default=2)
    a = p.parse_args()
    asyncio.run(main(a.concurrencias, a.rondas))
