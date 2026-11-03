import json
import multiprocessing
from concurrent.futures import ProcessPoolExecutor
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from app.ml import registro, simulador

INFO = Path(__file__).resolve().parents[2] / "KODOTAKAIINFO"


@pytest.mark.parametrize(
    ("campeon", "retador", "mayor", "tol", "esperado"),
    [
        (None, {"auc": 0.7}, True, 0.0, True),
        ({"auc": 0.7}, {"auc": 0.72}, True, 0.0, True),
        ({"auc": 0.7}, {"auc": 0.7}, True, 0.0, False),
        ({"auc": 0.7}, {"auc": 0.705}, True, 0.01, False),
        ({"auc": 0.7}, {"auc": 0.65}, True, 0.0, False),
        ({"auc": 0.8}, {"auc": 0.6}, False, 0.0, True),  # menor es mejor (p. ej. MASE)
        ({"auc": 0.7}, {"auc": float("nan")}, True, 0.0, False),
    ],
)
def test_decidir_promocion(campeon, retador, mayor, tol, esperado):
    promover, motivo = registro.decidir_promocion(campeon, retador, "auc", mayor, tol)
    assert promover is esperado and motivo


@pytest.mark.parametrize(
    ("kw", "esperado"),
    [
        ({"manual": True}, "manual"),
        ({"n_nuevos_etiquetados": 600}, "nuevos_datos"),
        ({"error_vivo": 0.25}, "deriva"),
        ({"horas_desde_ultimo": 30}, "antiguedad"),
        ({"horas_desde_ultimo": None}, "antiguedad"),
        ({}, None),
        ({"error_vivo": None}, None),
    ],
)
def test_detectar_disparo(kw, esperado):
    base = {
        "n_nuevos_etiquetados": 10,
        "umbral": 500,
        "error_vivo": 0.16,
        "error_entrenamiento": 0.15,
        "delta_deriva": 0.05,
        "horas_desde_ultimo": 2,
        "max_horas": 24,
    }
    assert registro.detectar_disparo(**(base | kw)) == esperado


def test_entrenar_todo_en_proceso_aparte_y_champion_challenger():
    t = pd.read_csv(INFO / "matriz_tarifas_y_fletes.csv", encoding="utf-8-sig")
    m = pd.DataFrame(json.loads((INFO / "directorio_cobertura_y_tiempos.json").read_text()))
    envios = simulador.generar_historial(t, m, date(2026, 1, 1), date(2026, 6, 30))[0]

    # spawn: hacer fork de un proceso que ya usó OpenMP (HistGradientBoosting) puede bloquear al hijo.
    with ProcessPoolExecutor(max_workers=1, mp_context=multiprocessing.get_context("spawn")) as pool:
        primero = pool.submit(registro.entrenar_todo, envios).result()
    assert set(primero) == {"riesgo_retraso", "demanda"}
    for r in primero.values():
        assert r["promover"] and r["metricas_campeon"] is None
        assert isinstance(r["artefacto"], bytes)
        json.dumps(r["metadatos"])

    # Mismo modelo como campeón y mismo holdout: empate → no se promueve.
    campeones = {k: v["artefacto"] for k, v in primero.items()}
    segundo = registro.entrenar_todo(envios, campeones)
    assert not segundo["riesgo_retraso"]["promover"] and not segundo["demanda"]["promover"]
    assert segundo["riesgo_retraso"]["metricas_campeon"]["roc_auc"] == pytest.approx(
        segundo["riesgo_retraso"]["metricas"]["roc_auc"]
    )
