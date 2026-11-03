import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from app.ml import features, modelos, simulador

INFO = Path(__file__).resolve().parents[2] / "KODOTAKAIINFO"


@pytest.fixture(scope="module")
def envios():
    t = pd.read_csv(INFO / "matriz_tarifas_y_fletes.csv", encoding="utf-8-sig")
    m = pd.DataFrame(json.loads((INFO / "directorio_cobertura_y_tiempos.json").read_text()))
    return simulador.generar_historial(t, m, date(2025, 11, 1), date(2026, 10, 31))[0]


@pytest.fixture(scope="module")
def riesgo(envios):
    return modelos.entrenar_riesgo(envios)


@pytest.fixture(scope="module")
def serie(envios):
    return features.serie_demanda(envios)


@pytest.fixture(scope="module")
def demanda(serie):
    return modelos.entrenar_demanda(serie)


def test_particion_temporal(envios):
    entreno, prueba, corte = modelos.particion_riesgo(envios)
    assert entreno.fecha_despacho.max() < corte <= prueba.fecha_despacho.min()
    assert (entreno.fecha_entrega_real < corte).all()  # etiqueta conocida en el corte
    assert prueba.retrasado.notna().all()


def test_riesgo_supera_a_la_tasa_base(riesgo):
    m = riesgo["metricas"]
    assert m["roc_auc"] > 0.6
    assert m["brier"] < m["brier_tasa_base"]
    assert set(m["candidatos"]) == {"logistica", "hist_gradient_boosting"}
    json.dumps(modelos.metadatos(riesgo))


def _en(envio: dict, momento: str, horas: int) -> dict:
    t = pd.Timestamp(momento, tz="America/Bogota")
    return envio | {"fecha_despacho": t, "fecha_estimada_entrega": t + pd.Timedelta(hours=horas)}


def test_predecir_riesgo_explica_factores(riesgo, envios):
    def envio(trayecto):
        return envios[envios.codigo_trayecto == trayecto].iloc[0].to_dict()

    zomac = modelos.predecir_riesgo(riesgo, _en(envio("TLX-BOG-QUI-025"), "2026-12-18 10:00", 96))
    assert "ZOMAC" in zomac["factores"][0]["factor"]
    sabado = modelos.predecir_riesgo(riesgo, _en(envio("TLX-BOG-MED-001"), "2026-11-14 10:00", 24))
    assert any(f["factor"] == "Despacho en fin de semana" for f in sabado["factores"])
    miercoles = modelos.predecir_riesgo(riesgo, _en(envio("TLX-BOG-MED-001"), "2026-11-11 10:00", 24))
    assert zomac["probabilidad"] > sabado["probabilidad"] > miercoles["probabilidad"]
    assert 0 <= miercoles["probabilidad"] <= 1


def test_demanda_supera_al_naive_estacional(demanda):
    m = demanda["metricas"]
    assert len(m["por_corte"]) >= 3
    assert m["mase"] < 1
    assert m["mae"] < m["mae_naive"]
    assert 0 < m["cobertura_80"] <= 1
    json.dumps(modelos.metadatos(demanda))


def test_pronosticar_con_intervalo(demanda, serie):
    p = modelos.pronosticar(demanda, serie, "Bogotá D.C.", 14)
    assert len(p) == 14 and (p.origen == "Bogotá D.C.").all()
    assert (p.fecha.diff().dropna() == pd.Timedelta(days=1)).all()
    assert ((p.p10 <= p.prediccion) & (p.prediccion <= p.p90) & (p.p10 >= 0)).all()
    with pytest.raises(ValueError):
        modelos.pronosticar(demanda, serie, "Leticia", 14)


def test_serializacion_conserva_predicciones(riesgo, demanda, envios, serie):
    r2 = modelos.desde_bytes(modelos.a_bytes(riesgo))
    envio = envios.iloc[0].to_dict()
    assert modelos.predecir_riesgo(r2, envio) == modelos.predecir_riesgo(riesgo, envio)
    d2 = modelos.desde_bytes(modelos.a_bytes(demanda))
    pd.testing.assert_frame_equal(
        modelos.pronosticar(d2, serie, "Cali", 7), modelos.pronosticar(demanda, serie, "Cali", 7)
    )
