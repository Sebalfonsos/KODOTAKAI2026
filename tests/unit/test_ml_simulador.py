import json
import re
from datetime import date
from pathlib import Path

import holidays
import pandas as pd
import pytest

from app.ml import simulador

INFO = Path(__file__).resolve().parents[2] / "KODOTAKAIINFO"


@pytest.fixture(scope="module")
def datos():
    t = pd.read_csv(INFO / "matriz_tarifas_y_fletes.csv", encoding="utf-8-sig")
    m = pd.DataFrame(json.loads((INFO / "directorio_cobertura_y_tiempos.json").read_text()))
    return t, m


@pytest.fixture(scope="module")
def anio(datos):
    return simulador.generar_historial(*datos, date(2025, 11, 1), date(2026, 10, 31))


def test_determinista_con_semilla(datos):
    a = simulador.generar_historial(*datos, date(2026, 1, 1), date(2026, 1, 31))
    b = simulador.generar_historial(*datos, date(2026, 1, 1), date(2026, 1, 31))
    c = simulador.generar_historial(*datos, date(2026, 1, 1), date(2026, 1, 31), semilla=7)
    pd.testing.assert_frame_equal(a[0], b[0])
    pd.testing.assert_frame_equal(a[1], b[1])
    assert not a[0].retrasado.equals(c[0].retrasado)


def test_guias_validas_y_sin_colision_con_las_reales(datos, anio):
    envios, _ = anio
    assert envios.numero_guia.str.fullmatch(r"TLX-\d{6}-CO").all()
    assert envios.numero_guia.is_unique
    reales = {g["numero_guia"] for g in json.loads((INFO / "dataset_guias_simuladas_tms.json").read_text())}
    assert not reales & set(envios.numero_guia)
    corto, _ = simulador.generar_historial(
        *datos, date(2026, 1, 1), date(2026, 1, 3), excluir=frozenset({"TLX-000002-CO"})
    )
    assert "TLX-000002-CO" not in set(corto.numero_guia)
    assert (envios.origen_dato == "simulado").all()


def test_coherencia_con_la_matriz(datos, anio):
    trayectos, _ = datos
    envios, _ = anio
    assert set(envios.origen) <= set(trayectos.ciudad_origen)
    horas = envios.codigo_trayecto.map(trayectos.set_index("codigo_trayecto").tiempo_entrega_estimado_horas)
    assert (envios.fecha_estimada_entrega - envios.fecha_despacho == pd.to_timedelta(horas, unit="h")).all()
    llego = envios.fecha_entrega_real.notna()
    assert (envios.retrasado[llego] == (envios.fecha_entrega_real > envios.fecha_estimada_entrega)[llego]).all()
    assert envios.retrasado[~llego].isna().all()
    assert (envios.estado_actual[llego] == "ENTREGADO").all()
    assert not envios.requiere_refrigeracion[envios.destino.isin(["Ipiales", "Florencia", "Quibdó"])].any()
    quibdo = envios[envios.codigo_trayecto == "TLX-BOG-QUI-025"]
    assert set(quibdo.fecha_despacho.dt.day_of_week) == {1, 4}  # "martes y viernes"


def test_retraso_por_cobertura_y_factores(anio):
    envios, _ = anio
    tasa = envios.groupby("tipo_cobertura").retrasado.mean()
    assert tasa["Urbana Principal"] < tasa["Trayecto Especial"] < tasa["Frontera"] < tasa["Zona ZOMAC"]
    finde = envios.fecha_despacho.dt.day_of_week >= 5
    assert envios.retrasado[finde].mean() > envios.retrasado[~finde].mean()
    assert envios.retrasado[envios.mercancia_peligrosa].mean() > envios.retrasado[~envios.mercancia_peligrosa].mean()


def test_demanda_estacional(anio):
    envios, _ = anio
    dia = envios.fecha_despacho.dt.tz_localize(None).dt.normalize()
    diaria = envios.groupby(dia).size()
    diaria = diaria.reindex(pd.date_range(diaria.index.min(), diaria.index.max()), fill_value=0)
    assert diaria[diaria.index.month == 12].mean() > 1.3 * diaria[diaria.index.month != 12].mean()
    assert diaria[diaria.index.day_of_week == 6].mean() < 0.5 * diaria[diaria.index.day_of_week < 5].mean()
    festivo = diaria.index.map(lambda d: d in holidays.country_holidays("CO")) & (diaria.index.day_of_week < 5)
    assert diaria[festivo].mean() < 0.5 * diaria[~festivo & (diaria.index.day_of_week < 5)].mean()


def test_eventos_ordenados_y_entrega_registrada(anio):
    envios, eventos = anio
    entregados = set(eventos.numero_guia[eventos.estado == "ENTREGADO"])
    assert entregados == set(envios.numero_guia[envios.estado_actual == "ENTREGADO"])
    assert eventos.groupby("numero_guia").timestamp.is_monotonic_increasing.all()


def test_avanzar_equivale_a_generar_mas_dias_y_cierra_pendientes(datos):
    trayectos, municipios = datos
    envios, eventos = simulador.generar_historial(*datos, date(2026, 3, 1), date(2026, 3, 20))
    estado = {"envios": envios, "trayectos": trayectos, "municipios": municipios, "hasta": date(2026, 3, 20)}
    nuevo, cambios, eventos_nuevos = simulador.avanzar(estado, 10)
    largo, eventos_largo = simulador.generar_historial(*datos, date(2026, 3, 1), date(2026, 3, 30))

    def orden(df):
        return df.sort_values("numero_guia").reset_index(drop=True)

    pd.testing.assert_frame_equal(orden(nuevo["envios"]), orden(largo))
    juntos = pd.concat([eventos, eventos_nuevos]).sort_values(["timestamp", "numero_guia"], kind="stable")
    pd.testing.assert_frame_equal(juntos.reset_index(drop=True), eventos_largo, check_like=True)
    pendientes = set(envios.numero_guia[envios.estado_actual != "ENTREGADO"])
    assert pendientes and pendientes <= set(cambios.numero_guia)
    assert (cambios.set_index("numero_guia").loc[list(pendientes)].estado_actual == "ENTREGADO").any()
    assert nuevo["hasta"] == date(2026, 3, 30)
    assert re.fullmatch(r"TLX-\d{6}-CO", cambios.numero_guia.iloc[-1])
