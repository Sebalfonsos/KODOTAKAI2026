"""Servicio ML: une el núcleo puro de app/ml con PostgreSQL (siembra, entrenamiento, predicción y simulación).

Los modelos se entrenan con datos SIMULADOS (`origen_dato='simulado'`) más las guías del dataset del reto.
Todas las respuestas llevan `datos_simulados=True`.
"""

import asyncio
import json
import logging
import multiprocessing
import time
from concurrent.futures import ProcessPoolExecutor
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from functools import lru_cache
from zoneinfo import ZoneInfo

import pandas as pd
from sqlalchemy import case, exists, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.config import get_settings
from app.core.errors import ApiError
from app.domain.sanitizar import normalizar_para_busqueda
from app.ml import modelos, registro, simulador
from app.ml.features import features_riesgo
from app.models import Entrenamiento, Envio, EventoEnvio, Hub, ModeloMl, Municipio, Prediccion, Trayecto
from app.models.base import EstadoModelo, OrigenDato, TipoCobertura, TipoServicio
from app.schemas.artifacts import Eje, Factor, Grafico, MetricaModelo, MetricasModelo, Punto, Serie, TarjetaPrediccion

log = logging.getLogger("app.ml")

TZ = "America/Bogota"
SEMILLA = 2026
MIN_ETIQUETADOS = 200  # por debajo, particion_riesgo no puede entrenar
LOTE = 5000
COBERTURA_SIM = {
    TipoCobertura.URBANA_PRINCIPAL: "Urbana Principal",
    TipoCobertura.FRONTERA: "Frontera",
    TipoCobertura.TRAYECTO_ESPECIAL: "Trayecto Especial",
    TipoCobertura.ZOMAC: "Zona ZOMAC",
}
SERVICIO_ENUM = dict(
    zip(
        (s[0] for s in simulador.SERVICIOS),
        (
            TipoServicio.PAQUETERIA,
            TipoServicio.CARGA_SEMIMASIVA,
            TipoServicio.CARGA_MASIVA,
            TipoServicio.CADENA_FRIO,
            TipoServicio.MERCANCIA_PELIGROSA,
        ),
        strict=True,
    )
)
# ponytail: clase ONU simulada rotando entre clases no prohibidas del manual; sortear con pesos si importa.
CLASES_SIMULADAS = ("3", "8", "9")
# ponytail: umbrales fijos de nivel alrededor de la tasa base simulada (~20 %); calibrar con datos reales.
UMBRALES_NIVEL = ((0.2, "bajo"), (0.4, "medio"))

_lock_entreno = asyncio.Lock()
_lock_simulacion = asyncio.Lock()
_pool: ProcessPoolExecutor | None = None
_cache: dict[str, tuple[int, dict]] = {}  # nombre → (id del modelo activo, modelo deserializado)


# ---------- utilidades ----------


def pool() -> ProcessPoolExecutor:
    """Un proceso aparte para entrenar sin bloquear la API. `spawn`: el fork tras usar OpenMP se bloquea."""
    global _pool
    if _pool is None:
        _pool = ProcessPoolExecutor(max_workers=1, mp_context=multiprocessing.get_context("spawn"))
    return _pool


def cerrar_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.shutdown(wait=False, cancel_futures=True)
        _pool = None


@lru_cache
def _referencia() -> tuple[pd.DataFrame, pd.DataFrame, dict[str, str]]:
    """Trayectos y municipios en el formato del simulador (KODOTAKAIINFO) y nombre de municipio → DANE."""
    datos = get_settings().datos_dir
    t = pd.read_csv(datos / "matriz_tarifas_y_fletes.csv", encoding="utf-8-sig")
    m = pd.DataFrame(json.loads((datos / "directorio_cobertura_y_tiempos.json").read_text(encoding="utf-8")))
    return t, m, dict(zip(m.municipio, m.codigo_dane, strict=True))


def _fecha(valor: str) -> datetime:
    ts = pd.Timestamp(valor)
    return (ts if ts.tz is not None else ts.tz_localize(TZ)).to_pydatetime()


def _ahora() -> datetime:
    return datetime.now(UTC)


def nivel(probabilidad: float) -> str:
    return next((n for limite, n in UMBRALES_NIVEL if probabilidad < limite), "alto")


def _cuatro(x: float) -> Decimal:
    return Decimal(str(round(float(x), 4)))


# ---------- datos ----------


def _filas_envio(envios: pd.DataFrame) -> list[dict]:
    _, _, dane = _referencia()
    factor = dict(zip(_referencia()[0].codigo_trayecto, _referencia()[0].factor_divisitivas_volumetrico, strict=True))
    filas = []
    for r in envios.itertuples(index=False):
        mp = bool(r.mercancia_peligrosa)
        filas.append(
            {
                "numero_guia": r.numero_guia,
                "trayecto_codigo": r.codigo_trayecto,
                "origen_dane": dane[r.origen],
                "destino_dane": dane[r.destino],
                "tipo_servicio": SERVICIO_ENUM[r.tipo_servicio],
                "descripcion_servicio": r.tipo_servicio,
                "peso_kg": Decimal(str(r.peso_kg)),
                "alto_cm": Decimal(r.dimensiones["alto"]),
                "ancho_cm": Decimal(r.dimensiones["ancho"]),
                "largo_cm": Decimal(r.dimensiones["largo"]),
                "factor_volumetrico": int(factor[r.codigo_trayecto]),
                "valor_declarado": Decimal(r.valor_declarado),
                "requiere_refrigeracion": bool(r.requiere_refrigeracion),
                "mercancia_peligrosa": mp,
                "clase_onu": CLASES_SIMULADAS[int(r.numero_guia[4:10]) % 3] if mp else None,
                "estado_actual": r.estado_actual,
                "fecha_despacho": r.fecha_despacho.to_pydatetime(),
                "fecha_estimada_entrega": r.fecha_estimada_entrega.to_pydatetime(),
                "fecha_entrega_real": None if pd.isna(r.fecha_entrega_real) else r.fecha_entrega_real.to_pydatetime(),
                "origen_dato": OrigenDato.SIMULADO,
            }
        )
    return filas


async def _insertar(s: AsyncSession, envios: pd.DataFrame, eventos: pd.DataFrame, actualizar: bool) -> None:
    """Inserta por lotes; con `actualizar` cierra pendientes (estado y entrega real). Idempotente."""
    stmt = insert(Envio)
    if actualizar:
        stmt = stmt.on_conflict_do_update(
            index_elements=["numero_guia"],
            set_={"estado_actual": stmt.excluded.estado_actual, "fecha_entrega_real": stmt.excluded.fecha_entrega_real},
        )
    else:
        stmt = stmt.on_conflict_do_nothing(index_elements=["numero_guia"])
    filas = _filas_envio(envios)
    for i in range(0, len(filas), LOTE):
        await s.execute(stmt, filas[i : i + LOTE])
    filas_ev = [
        {
            "numero_guia": e.numero_guia,
            "ocurrido_en": e.timestamp.to_pydatetime(),
            "estado": e.estado,
            "ubicacion": e.hub_ubicacion,
            "descripcion": e.descripcion,
        }
        for e in eventos.itertuples(index=False)
    ]
    stmt_ev = insert(EventoEnvio).on_conflict_do_nothing(index_elements=["numero_guia", "ocurrido_en", "estado"])
    for i in range(0, len(filas_ev), LOTE):
        await s.execute(stmt_ev, filas_ev[i : i + LOTE])


async def sembrar_historial(s: AsyncSession, meses: int, hoy: date | None = None) -> dict:
    """Genera `meses` de historial simulado hasta ayer y lo inserta. No hace nada si ya existe historial."""
    existentes = await s.scalar(select(func.count()).select_from(Envio).where(Envio.origen_dato == OrigenDato.SIMULADO))
    if existentes:
        return {"envios": 0, "eventos": 0, "omitido": f"ya hay {existentes} envíos simulados"}
    hoy = hoy or datetime.now(ZoneInfo(TZ)).date()
    desde = (pd.Timestamp(hoy) - pd.DateOffset(months=meses)).date()
    hasta = hoy - timedelta(days=1)
    t, m, _ = _referencia()
    reales = frozenset(await s.scalars(select(Envio.numero_guia)))
    envios, eventos = simulador.generar_historial(t, m, desde, hasta, SEMILLA, reales)
    await _insertar(s, envios, eventos, actualizar=False)
    await s.commit()
    return {"envios": len(envios), "eventos": len(eventos), "desde": desde.isoformat(), "hasta": hasta.isoformat()}


async def cargar_dataframe(s: AsyncSession, *filtros) -> pd.DataFrame:
    """Envíos (dataset + simulados) en el formato del núcleo ML; fechas en hora de Bogotá."""
    o, d = aliased(Municipio), aliased(Municipio)
    q = (
        select(
            Envio.numero_guia,
            Envio.trayecto_codigo.label("codigo_trayecto"),
            o.nombre.label("origen"),
            d.nombre.label("destino"),
            Hub.nombre.label("hub_origen"),
            func.coalesce(Trayecto.tipo_cobertura, d.tipo_cobertura).label("tipo_cobertura"),
            Envio.descripcion_servicio.label("tipo_servicio"),
            Envio.peso_kg,
            Envio.alto_cm,
            Envio.ancho_cm,
            Envio.largo_cm,
            Envio.valor_declarado,
            Envio.requiere_refrigeracion,
            Envio.mercancia_peligrosa,
            Envio.fecha_despacho,
            Envio.fecha_estimada_entrega,
            Envio.fecha_entrega_real,
            Envio.estado_actual,
            Envio.origen_dato,
        )
        .join(o, Envio.origen_dane == o.codigo_dane)
        .join(d, Envio.destino_dane == d.codigo_dane)
        .join(Hub, o.hub_id == Hub.id)
        .outerjoin(Trayecto, Envio.trayecto_codigo == Trayecto.codigo)
        .where(*filtros)
    )
    filas = (await s.execute(q)).all()
    df = pd.DataFrame(filas, columns=list(q.selected_columns.keys()))
    if df.empty:
        return df
    df["codigo_trayecto"] = df.codigo_trayecto.fillna("SIN_TRAYECTO")
    df["tipo_cobertura"] = df.tipo_cobertura.map(lambda c: COBERTURA_SIM[TipoCobertura(c)])
    df["peso_kg"] = df.peso_kg.astype(float)
    df["dimensiones"] = [
        {"alto": float(a), "ancho": float(b), "largo": float(c)}
        for a, b, c in zip(df.alto_cm, df.ancho_cm, df.largo_cm, strict=True)
    ]
    for col in ("fecha_despacho", "fecha_estimada_entrega", "fecha_entrega_real"):
        df[col] = pd.to_datetime(df[col], utc=True).dt.tz_convert(TZ)
    llego = df.fecha_entrega_real.notna()
    df["retrasado"] = pd.array(df.fecha_entrega_real > df.fecha_estimada_entrega, dtype="boolean")
    df.loc[~llego, "retrasado"] = pd.NA
    df["origen_dato"] = df.origen_dato.map(lambda v: OrigenDato(v).value)
    return df.drop(columns=["alto_cm", "ancho_cm", "largo_cm"])


# ---------- entrenamiento ----------


async def entrenar(s: AsyncSession, motivo: str) -> dict:
    """Entrena retadores en otro proceso, los registra y aplica champion/challenger en una transacción."""
    if _lock_entreno.locked():
        raise ApiError(409, "Ya hay un entrenamiento en curso; espera a que termine.", "ENTRENAMIENTO_EN_CURSO")
    async with _lock_entreno:
        t0 = time.monotonic()
        df = await cargar_dataframe(s)
        n_etiquetados = int(df.retrasado.notna().sum()) if len(df) else 0
        if n_etiquetados < MIN_ETIQUETADOS:
            raise ApiError(
                409,
                f"Hay {n_etiquetados} envíos con desenlace conocido; se necesitan {MIN_ETIQUETADOS}. "
                "Siembra historial con `python -m app.seed --historial-meses 6`.",
                "DATOS_INSUFICIENTES",
            )
        activos = {m.nombre: m for m in await s.scalars(select(ModeloMl).where(ModeloMl.estado == EstadoModelo.ACTIVO))}
        corridas = {}
        for nombre in registro.METRICA_DECISION:
            corridas[nombre] = Entrenamiento(
                nombre=nombre,
                motivo=motivo if nombre in activos else "inicial",
                resultado="en_curso",
                detalle={"n_etiquetados": n_etiquetados, "n_envios": len(df)},
            )
            s.add(corridas[nombre])
        await s.commit()  # la corrida "en_curso" queda visible mientras entrena

        campeones = {n: m.artefacto for n, m in activos.items()}
        try:
            res = await asyncio.get_running_loop().run_in_executor(pool(), registro.entrenar_todo, df, campeones)
        except Exception as exc:
            for e in corridas.values():
                e.resultado, e.terminado_en = "error", _ahora()
                e.detalle = {**e.detalle, "error": f"{type(exc).__name__}: {exc}"[:500]}
            await s.commit()
            raise

        duracion = round(time.monotonic() - t0, 2)
        salida = {"duracion_s": duracion, "modelos": {}}
        for nombre, r in res.items():
            meta = r["metadatos"]
            version = (await s.scalar(select(func.max(ModeloMl.version)).where(ModeloMl.nombre == nombre)) or 0) + 1
            nuevo = ModeloMl(
                nombre=nombre,
                version=version,
                algoritmo=meta["algoritmo"],
                metricas=meta["metricas"],
                features=meta["features"],
                n_train=meta["n_train"],
                entrenado_hasta=_fecha(meta["entrenado_hasta"]),
                estado=EstadoModelo.CANDIDATO,
                artefacto=r["artefacto"],
            )
            s.add(nuevo)
            await s.flush()
            if r["promover"]:
                if nombre in activos:
                    activos[nombre].estado = EstadoModelo.RETIRADO
                    await s.flush()  # antes de activar el nuevo: índice único parcial de 'activo'
                nuevo.estado = EstadoModelo.ACTIVO
            else:
                nuevo.estado = EstadoModelo.RECHAZADO
            e = corridas[nombre]
            e.modelo_id, e.terminado_en = nuevo.id, _ahora()
            e.resultado = "promovido" if r["promover"] else "rechazado"
            e.detalle = {
                **e.detalle,
                "version": version,
                "decision": r["motivo"],
                "metricas_retador": r["metricas"],
                "metricas_campeon": r["metricas_campeon"],
                "version_campeon": activos[nombre].version if nombre in activos else None,
                "duracion_s": duracion,
            }
            salida["modelos"][nombre] = {
                "version": version,
                "estado": nuevo.estado.value,
                "promovido": r["promover"],
                "motivo_entrenamiento": e.motivo,
                "decision": r["motivo"],
            }
        await s.commit()
        log.info("ml_entrenamiento", extra={"motivo": motivo, "duracion_s": duracion})
        return salida


# ---------- predicción ----------


async def _activo(s: AsyncSession, nombre: str) -> tuple[int, int, dict]:
    fila = (
        await s.execute(
            select(ModeloMl.id, ModeloMl.version).where(
                ModeloMl.nombre == nombre, ModeloMl.estado == EstadoModelo.ACTIVO
            )
        )
    ).first()
    if fila is None:
        raise ApiError(
            503, f"Aún no hay un modelo {nombre} activo; entrénalo con POST /admin/ml/entrenar.", "MODELO_NO_ENTRENADO"
        )
    if _cache.get(nombre, (None,))[0] != fila.id:
        artefacto = await s.scalar(select(ModeloMl.artefacto).where(ModeloMl.id == fila.id))
        _cache[nombre] = (fila.id, modelos.desde_bytes(artefacto))
    return fila.id, fila.version, _cache[nombre][1]


async def predecir_riesgo(s: AsyncSession, guia: str) -> dict:
    """Probabilidad de retraso de una guía con el modelo activo; guarda/actualiza la predicción."""
    modelo_id, version, modelo = await _activo(s, "riesgo_retraso")
    df = await cargar_dataframe(s, Envio.numero_guia == guia)
    if df.empty:
        raise ApiError(404, f"No existe la guía {guia}.", "GUIA_NO_ENCONTRADA")
    fila = df.iloc[0]
    r = modelos.predecir_riesgo(modelo, fila.to_dict())
    real = None if pd.isna(fila.retrasado) else bool(fila.retrasado)
    stmt = insert(Prediccion).values(
        modelo_id=modelo_id,
        numero_guia=guia,
        probabilidad=_cuatro(r["probabilidad"]),
        factores=r["factores"],
        valor_real=real,
    )
    await s.execute(
        stmt.on_conflict_do_update(
            constraint="uq_ml_predicciones_modelo_guia",
            set_={"probabilidad": stmt.excluded.probabilidad, "factores": stmt.excluded.factores},
        )
    )
    await s.commit()
    return {
        "guia": guia,
        "probabilidad": r["probabilidad"],
        "nivel": nivel(r["probabilidad"]),
        "factores": r["factores"],
        "modelo": "riesgo_retraso",
        "version": version,
        "estado_actual": fila.estado_actual,
        "retrasado_real": real,
        "datos_simulados": True,
    }


async def _serie(s: AsyncSession, origenes: list[str]) -> pd.DataFrame:
    """Despachos diarios por municipio de origen (fecha local), días sin despachos en 0."""
    dia = func.date(func.timezone(TZ, Envio.fecha_despacho)).label("fecha")
    q = (
        select(dia, Municipio.nombre.label("origen"), func.count().label("y"))
        .join(Municipio, Envio.origen_dane == Municipio.codigo_dane)
        .where(Municipio.nombre.in_(origenes))
        .group_by(dia, Municipio.nombre)
    )
    df = pd.DataFrame((await s.execute(q)).all(), columns=["fecha", "origen", "y"])
    if df.empty:
        return df
    df["fecha"] = pd.to_datetime(df.fecha)
    rejilla = pd.MultiIndex.from_product(
        [pd.date_range(df.fecha.min(), df.fecha.max()), sorted(origenes)], names=["fecha", "origen"]
    )
    return df.set_index(["fecha", "origen"]).y.reindex(rejilla, fill_value=0).astype(float).reset_index()


async def pronosticar_demanda(s: AsyncSession, origen_o_hub: str, dias: int = 14) -> dict:
    """Pronóstico diario de despachos de un municipio de origen (o su hub) con intervalo 80 %."""
    _, version, modelo = await _activo(s, "demanda")
    hubs = dict(
        (
            await s.execute(
                select(Municipio.nombre, Hub.nombre)
                .join(Hub, Municipio.hub_id == Hub.id)
                .where(Municipio.nombre.in_(modelo["origenes"]))
            )
        ).all()
    )

    # "Bogotá" también es "Bogotá D.C.": así lo dice cualquiera que pregunte.
    def clave(nombre: str) -> str:
        return normalizar_para_busqueda(nombre).removesuffix(" d c")

    buscado = clave(origen_o_hub)
    origen = next((o for o, h in hubs.items() if buscado in (clave(o), clave(h))), None)
    if origen is None:
        raise ApiError(
            404,
            f"Sin pronóstico para «{origen_o_hub}». Orígenes disponibles: {', '.join(sorted(hubs))}.",
            "ORIGEN_SIN_PRONOSTICO",
        )
    serie = await _serie(s, modelo["origenes"])
    p = modelos.pronosticar(modelo, serie, origen, dias)
    hist = serie[serie.origen == origen].tail(28)
    return {
        "origen": origen,
        "hub": hubs[origen],
        "dias": dias,
        "modelo": "demanda",
        "version": version,
        "historico": [{"fecha": f.date(), "valor": round(y, 1)} for f, y in zip(hist.fecha, hist.y, strict=True)],
        "pronostico": [
            {
                "fecha": r.fecha.date(),
                "prediccion": round(r.prediccion, 1),
                "p10": round(r.p10, 1),
                "p90": round(r.p90, 1),
            }
            for r in p.itertuples()
        ],
        "datos_simulados": True,
    }


# ---------- vigilancia (autoentrenamiento) ----------


async def etiquetar_reales(s: AsyncSession) -> int:
    """Llena `valor_real` de las predicciones cuyos envíos ya se entregaron."""
    r = await s.execute(
        update(Prediccion)
        .where(
            Prediccion.numero_guia == Envio.numero_guia,
            Prediccion.valor_real.is_(None),
            Envio.fecha_entrega_real.is_not(None),
        )
        .values(valor_real=Envio.fecha_entrega_real > Envio.fecha_estimada_entrega)
    )
    await s.commit()
    return r.rowcount


async def puntuar_pendientes(s: AsyncSession) -> int:
    """Predice (sin factores) los envíos aún sin entregar que no tienen predicción del modelo activo.

    Así, cuando se cierran, `etiquetar_reales` les pone el valor real y hay error en vivo para la deriva.
    """
    try:
        modelo_id, _, modelo = await _activo(s, "riesgo_retraso")
    except ApiError:
        return 0
    ya = exists().where(Prediccion.numero_guia == Envio.numero_guia, Prediccion.modelo_id == modelo_id)
    df = await cargar_dataframe(s, Envio.fecha_entrega_real.is_(None), ~ya)
    if df.empty:
        return 0
    p = modelo["estimador"].predict_proba(features_riesgo(df))[:, 1]
    filas = [
        {"modelo_id": modelo_id, "numero_guia": g, "probabilidad": _cuatro(x)}
        for g, x in zip(df.numero_guia, p, strict=True)
    ]
    stmt = insert(Prediccion).on_conflict_do_nothing(constraint="uq_ml_predicciones_modelo_guia")
    for i in range(0, len(filas), LOTE):
        await s.execute(stmt, filas[i : i + LOTE])
    await s.commit()
    return len(filas)


async def estado_disparo(s: AsyncSession) -> dict:
    """Entradas de `registro.detectar_disparo` medidas en la BD."""
    n_etiquetados = await s.scalar(select(func.count()).select_from(Envio).where(Envio.fecha_entrega_real.is_not(None)))
    ultimo = await s.scalar(
        select(Entrenamiento)
        .where(Entrenamiento.nombre == "riesgo_retraso", Entrenamiento.resultado.in_(("promovido", "rechazado")))
        .order_by(Entrenamiento.terminado_en.desc())
        .limit(1)
    )
    activo = (
        await s.execute(
            select(ModeloMl.id, ModeloMl.metricas).where(
                ModeloMl.nombre == "riesgo_retraso", ModeloMl.estado == EstadoModelo.ACTIVO
            )
        )
    ).first()
    error_vivo = error_entrenamiento = None
    n_vivo = 0
    if activo:
        error_entrenamiento = activo.metricas.get("brier")
        real = case((Prediccion.valor_real, 1), else_=0)
        fila = (
            await s.execute(
                select(func.avg(func.power(Prediccion.probabilidad - real, 2)), func.count()).where(
                    Prediccion.modelo_id == activo.id, Prediccion.valor_real.is_not(None)
                )
            )
        ).one()
        n_vivo = fila[1]
        # ponytail: mínimo de 50 etiquetas para que el Brier en vivo no sea puro ruido.
        error_vivo = float(fila[0]) if n_vivo >= 50 else None
    return {
        "n_etiquetados": n_etiquetados,
        "n_nuevos": n_etiquetados - (ultimo.detalle.get("n_etiquetados", 0) if ultimo else 0),
        "error_vivo": error_vivo,
        "n_vivo": n_vivo,
        "error_entrenamiento": error_entrenamiento,
        "horas_desde_ultimo": (_ahora() - ultimo.terminado_en).total_seconds() / 3600 if ultimo else None,
    }


# ---------- simulador ----------


async def avanzar_simulacion(s: AsyncSession, dias: int) -> dict:
    """Simula `dias` días más: crea envíos nuevos y cierra los pendientes que ya llegaron."""
    if _lock_simulacion.locked():
        raise ApiError(409, "Ya hay un avance de simulación en curso.", "SIMULACION_EN_CURSO")
    async with _lock_simulacion:
        df = await cargar_dataframe(s)
        sim = df[df.origen_dato == OrigenDato.SIMULADO.value] if len(df) else df
        if sim.empty:
            raise ApiError(
                409,
                "No hay historial simulado; ejecuta `python -m app.seed --historial-meses 6`.",
                "SIN_HISTORIAL_SIMULADO",
            )
        t, m, _ = _referencia()
        hasta = sim.fecha_despacho.max().date()
        pendientes = set(sim.numero_guia[sim.estado_actual != "ENTREGADO"])
        estado = {"envios": df, "trayectos": t, "municipios": m, "hasta": hasta}
        nuevo, cambios, eventos = simulador.avanzar(estado, dias, SEMILLA)
        await _insertar(s, cambios, eventos, actualizar=True)
        await s.commit()
        cerrados = cambios[cambios.numero_guia.isin(pendientes) & (cambios.estado_actual == "ENTREGADO")]
        return {
            "dias": dias,
            "desde": hasta + timedelta(days=1),
            "hasta": nuevo["hasta"],
            "envios_nuevos": int((~cambios.numero_guia.isin(pendientes)).sum()),
            "envios_cerrados": len(cerrados),
            "eventos": len(eventos),
            "datos_simulados": True,
        }


# ---------- consultas para la API ----------


def resumen_metricas(nombre: str, m: dict) -> tuple[dict, dict]:
    """(métricas principales, línea base) de un modelo."""
    if nombre == "riesgo_retraso":
        base = {"brier_tasa_base": m.get("brier_tasa_base")}
        if "candidatos" in m:
            base["roc_auc_logistica"] = m["candidatos"]["logistica"]["roc_auc"]
        return {k: m.get(k) for k in ("roc_auc", "brier", "log_loss")}, base
    return {k: m.get(k) for k in ("mae", "mase", "cobertura_80")}, {k: m.get(k) for k in ("mae_naive", "mase_naive")}


async def listar_modelos(s: AsyncSession, limite: int = 50) -> dict:
    cols = (
        ModeloMl.id,
        ModeloMl.nombre,
        ModeloMl.version,
        ModeloMl.algoritmo,
        ModeloMl.estado,
        ModeloMl.metricas,
        ModeloMl.n_train,
        ModeloMl.entrenado_hasta,
        ModeloMl.creado_en,
    )
    filas = (await s.execute(select(*cols).order_by(ModeloMl.creado_en.desc(), ModeloMl.id.desc()).limit(limite))).all()
    items = []
    for f in filas:
        principales, base = resumen_metricas(f.nombre, f.metricas)
        items.append(
            {
                "id": f.id,
                "nombre": f.nombre,
                "version": f.version,
                "algoritmo": f.algoritmo,
                "estado": EstadoModelo(f.estado).value,
                "metricas": principales,
                "linea_base": base,
                "n_train": f.n_train,
                "entrenado_hasta": f.entrenado_hasta,
                "creado_en": f.creado_en,
            }
        )
    return {"activos": [i for i in items if i["estado"] == "activo"], "historial": items, "datos_simulados": True}


async def listar_entrenamientos(s: AsyncSession, pagina: int, tamano: int) -> dict:
    total = await s.scalar(select(func.count()).select_from(Entrenamiento))
    filas = await s.scalars(
        select(Entrenamiento).order_by(Entrenamiento.id.desc()).offset((pagina - 1) * tamano).limit(tamano)
    )
    items = [
        {
            "id": e.id,
            "nombre": e.nombre,
            "motivo": e.motivo,
            "resultado": e.resultado,
            "modelo_id": e.modelo_id,
            "detalle": e.detalle,
            "iniciado_en": e.iniciado_en,
            "terminado_en": e.terminado_en,
        }
        for e in filas
    ]
    return {"items": items, "paginacion": {"pagina": pagina, "tamano": tamano, "total": total}}


# ---------- artifacts para el chat administrativo ----------


def artifact_prediccion(pred: dict, id: str = "art-pred-ml") -> TarjetaPrediccion:
    return TarjetaPrediccion(
        id=id,
        titulo=f"Riesgo de retraso — {pred['guia']}",
        modelo=pred["modelo"],
        version_modelo=pred["version"],
        guia=pred["guia"],
        probabilidad=_cuatro(pred["probabilidad"]),
        nivel=pred["nivel"],
        factores=[Factor(nombre=f["factor"][:80], efecto=_cuatro(f["impacto"])) for f in pred["factores"]],
        datos_simulados=True,
    )


def artifact_pronostico(pron: dict, id: str = "art-graf-demanda") -> Grafico:
    return Grafico(
        id=id,
        titulo=f"Pronóstico de despachos — {pron['origen']}"[:120],
        tipo_grafico="linea",
        eje_x=Eje(etiqueta="Fecha", tipo="fecha"),
        eje_y=Eje(etiqueta="Despachos", tipo="numero", unidad="envíos"),
        series=[
            Serie(
                nombre="Histórico",
                puntos=[Punto(x=str(p["fecha"]), y=Decimal(str(p["valor"]))) for p in pron["historico"]],
            ),
            Serie(
                nombre="Pronóstico",
                estilo="punteada",
                puntos=[
                    Punto(
                        x=str(p["fecha"]),
                        y=Decimal(str(p["prediccion"])),
                        y_inf=Decimal(str(p["p10"])),
                        y_sup=Decimal(str(p["p90"])),
                    )
                    for p in pron["pronostico"]
                ],
            ),
        ],
        datos_simulados=True,
    )


def artifact_metricas(modelos_: list[dict], id: str = "art-ml-metricas") -> MetricasModelo:
    """`modelos_`: items de `listar_modelos` (solo activos, candidatos o retirados)."""

    def dec(d: dict) -> dict:
        return {k: _cuatro(v) for k, v in d.items() if v is not None}

    return MetricasModelo(
        id=id,
        titulo="Modelos de predicción",
        modelos=[
            MetricaModelo(
                nombre=m["nombre"],
                version=m["version"],
                algoritmo=m["algoritmo"][:80],
                estado=m["estado"],
                metricas=dec(m["metricas"]),
                linea_base=dec(m["linea_base"]),
                n_train=m["n_train"],
                entrenado_en=m["creado_en"],
            )
            for m in modelos_
            if m["estado"] != "rechazado"
        ],
        datos_simulados=True,
    )
