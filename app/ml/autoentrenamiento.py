"""Bucle de autoentrenamiento: etiqueta, vigila y reentrena cuando hay motivo (nuevos datos, deriva o antigüedad).

Uso en el lifespan: `iniciar()` al arrancar y `await detener()` al cerrar.
"""

import asyncio
import contextlib
import logging

from app.config import get_settings
from app.core.errors import ApiError
from app.db import SessionLocal
from app.ml import servicio
from app.ml.registro import detectar_disparo

log = logging.getLogger("app.ml")

# ponytail: umbral de deriva fijo (Brier en vivo − Brier de entrenamiento); pasarlo a Settings si se ajusta.
DELTA_DERIVA = 0.05

_tarea: asyncio.Task | None = None
_stop: asyncio.Event | None = None


async def ciclo() -> str | None:
    """Una revisión completa. Devuelve el motivo del reentrenamiento disparado, o None."""
    cfg = get_settings()
    async with SessionLocal() as s:
        await servicio.etiquetar_reales(s)
        await servicio.puntuar_pendientes(s)
        e = await servicio.estado_disparo(s)
        if e["n_etiquetados"] < servicio.MIN_ETIQUETADOS:
            return None
        motivo = detectar_disparo(
            e["n_nuevos"],
            cfg.ml_min_nuevos,
            e["error_vivo"],
            e["error_entrenamiento"],
            DELTA_DERIVA,
            e["horas_desde_ultimo"],
            cfg.ml_max_horas,
        )
        if motivo:
            log.info("ml_disparo", extra={"motivo": motivo, **{k: e[k] for k in ("n_nuevos", "error_vivo")}})
            await servicio.entrenar(s, motivo)
        return motivo


async def bucle(stop: asyncio.Event) -> None:
    """Revisa cada `ML_CHECK_MIN` minutos hasta que `stop` se active. Ningún error detiene el bucle."""
    while not stop.is_set():
        try:
            await ciclo()
        except ApiError as e:  # p. ej. entrenamiento manual en curso
            log.info("ml_ciclo_omitido", extra={"codigo": e.codigo})
        except Exception:
            log.exception("ml_ciclo_error")
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=get_settings().ml_check_min * 60)


def iniciar() -> asyncio.Task:
    global _tarea, _stop
    _stop = asyncio.Event()
    _tarea = asyncio.create_task(bucle(_stop), name="ml-autoentrenamiento")
    return _tarea


async def detener() -> None:
    if _stop is not None:
        _stop.set()
    if _tarea is not None and not _tarea.done():
        try:
            await asyncio.wait_for(_tarea, timeout=5)
        except TimeoutError:  # entrenando: se cancela y el proceso de entrenamiento se descarta
            _tarea.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await _tarea
    servicio.cerrar_pool()
