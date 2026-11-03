"""Champion/challenger y disparadores de reentrenamiento (lógica pura, sin BD)."""

import math

import pandas as pd

from app.ml import modelos
from app.ml.features import serie_demanda

# Métrica de decisión por modelo: (clave, mayor_es_mejor).
METRICA_DECISION = {"riesgo_retraso": ("roc_auc", True), "demanda": ("mase", False)}


def decidir_promocion(
    metricas_campeon: dict | None,
    metricas_retador: dict,
    metrica: str,
    mayor_es_mejor: bool,
    tolerancia: float = 0.0,
) -> tuple[bool, str]:
    """El retador se promueve solo si mejora al campeón en más de `tolerancia` en el mismo holdout."""
    r = metricas_retador.get(metrica)
    if r is None or not math.isfinite(r):
        return False, f"retador sin {metrica} válida"
    if metricas_campeon is None or metricas_campeon.get(metrica) is None:
        return True, "no hay campeón: el retador se promueve"
    c = metricas_campeon[metrica]
    mejora = r - c if mayor_es_mejor else c - r
    texto = f"{metrica}: retador {r:.4f} vs campeón {c:.4f} (mejora {mejora:+.4f}, tolerancia {tolerancia})"
    return mejora > tolerancia, ("promovido; " if mejora > tolerancia else "rechazado; ") + texto


def detectar_disparo(
    n_nuevos_etiquetados: int,
    umbral: int,
    error_vivo: float | None,
    error_entrenamiento: float | None,
    delta_deriva: float,
    horas_desde_ultimo: float | None,
    max_horas: float,
    manual: bool = False,
) -> str | None:
    """Motivo para reentrenar ('manual'|'nuevos_datos'|'deriva'|'antiguedad') o None.

    `horas_desde_ultimo=None` significa que nunca se ha entrenado (cuenta como antigüedad).
    """
    if manual:
        return "manual"
    if n_nuevos_etiquetados >= umbral:
        return "nuevos_datos"
    if error_vivo is not None and error_entrenamiento is not None:
        if error_vivo - error_entrenamiento > delta_deriva:
            return "deriva"
    if horas_desde_ultimo is None or horas_desde_ultimo >= max_horas:
        return "antiguedad"
    return None


def entrenar_todo(envios_df: pd.DataFrame, campeones: dict[str, bytes] | None = None, tolerancia: float = 0.0) -> dict:
    """Entrena ambos retadores y los compara con sus campeones en el mismo holdout.

    Función de módulo con argumentos picklables: apta para `ProcessPoolExecutor`.
    Devuelve {nombre: {"artefacto", "metadatos", "metricas", "metricas_campeon", "promover", "motivo"}}.
    """
    campeones = campeones or {}
    riesgo = modelos.entrenar_riesgo(envios_df)
    _, holdout_riesgo, _ = modelos.particion_riesgo(envios_df)
    serie = serie_demanda(envios_df)
    demanda = modelos.entrenar_demanda(serie)
    corte = pd.Timestamp(demanda["metricas"]["holdout"]["corte"])

    evaluar = {
        "riesgo_retraso": (riesgo, riesgo["metricas"], lambda m: modelos.evaluar_riesgo(m, holdout_riesgo)),
        "demanda": (demanda, demanda["metricas"]["holdout"], lambda m: modelos.evaluar_demanda(m, serie, corte)),
    }
    resultado = {}
    for nombre, (retador, m_retador, evaluar_en_holdout) in evaluar.items():
        m_campeon = None
        if nombre in campeones:
            m_campeon = evaluar_en_holdout(modelos.desde_bytes(campeones[nombre]))
        metrica, mayor = METRICA_DECISION[nombre]
        promover, motivo = decidir_promocion(m_campeon, m_retador, metrica, mayor, tolerancia)
        resultado[nombre] = {
            "artefacto": modelos.a_bytes(retador),
            "metadatos": modelos.metadatos(retador),
            "metricas": retador["metricas"],
            "metricas_campeon": m_campeon,
            "promover": promover,
            "motivo": motivo,
        }
    return resultado
