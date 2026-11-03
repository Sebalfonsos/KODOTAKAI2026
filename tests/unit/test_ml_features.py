import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from app.ml import features, simulador

INFO = Path(__file__).resolve().parents[2] / "KODOTAKAIINFO"


@pytest.fixture(scope="module")
def envios():
    t = pd.read_csv(INFO / "matriz_tarifas_y_fletes.csv", encoding="utf-8-sig")
    m = pd.DataFrame(json.loads((INFO / "directorio_cobertura_y_tiempos.json").read_text()))
    return simulador.generar_historial(t, m, date(2026, 1, 1), date(2026, 2, 28))[0]


def test_riesgo_sin_fuga_temporal(envios):
    posteriores = {"fecha_entrega_real", "estado_actual", "retrasado"}
    assert not posteriores & set(features.COLUMNAS_DESPACHO)
    x = features.features_riesgo(envios)
    assert list(x.columns) == features.FEATURES_RIESGO
    alterado = envios.assign(
        fecha_entrega_real=pd.NaT, estado_actual="RETENIDO_NOVEDAD", retrasado=~envios.retrasado.fillna(False)
    )
    pd.testing.assert_frame_equal(x, features.features_riesgo(alterado))


def test_riesgo_usa_hora_local_aunque_llegue_en_utc(envios):
    utc = envios.assign(
        fecha_despacho=envios.fecha_despacho.dt.tz_convert("UTC"),
        fecha_estimada_entrega=envios.fecha_estimada_entrega.dt.tz_convert("UTC"),
    )
    pd.testing.assert_frame_equal(features.features_riesgo(envios), features.features_riesgo(utc))


def test_serie_rellena_dias_sin_despachos():
    envios = pd.DataFrame(
        {
            "origen": ["A", "A", "B"],
            "fecha_despacho": pd.to_datetime(["2026-01-01 10:00", "2026-01-03 09:00", "2026-01-01 08:00"]),
        }
    )
    s = features.serie_demanda(envios)
    assert len(s) == 6  # 3 días × 2 orígenes
    assert s.set_index(["fecha", "origen"]).y.loc[(pd.Timestamp("2026-01-02"), "A")] == 0


def test_demanda_sin_fuga_temporal():
    fechas = pd.date_range("2026-01-01", periods=40)
    serie = pd.DataFrame({"fecha": fechas, "origen": "A", "y": np.arange(40, dtype=float)})
    f = features.features_demanda(serie)
    fila = f[f.fecha == fechas[20]].iloc[0]
    assert (fila.lag1, fila.lag7, fila.lag14) == (19, 13, 6)
    assert fila.mm7 == np.mean(range(13, 20))

    t = fechas[25]
    alterada = serie.assign(y=serie.y.where(serie.fecha < t, 999.0))  # cambia el día t y el futuro
    g = features.features_demanda(alterada)
    hasta_t = f.fecha <= t
    cols = [c for c in features.FEATURES_DEMANDA if c != "origen"]
    pd.testing.assert_frame_equal(f.loc[hasta_t, cols], g.loc[hasta_t, cols])
    assert g.loc[g.fecha == fechas[26], "lag1"].item() == 999.0
