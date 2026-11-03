"""Ingeniería de features (separada del modelado para auditar fuga temporal)."""

import holidays
import numpy as np
import pandas as pd

TZ = "America/Bogota"

# Riesgo de retraso: SOLO columnas conocidas en el momento del despacho. fecha_entrega_real,
# estado_actual y retrasado nunca entran (las pruebas lo verifican).
COLUMNAS_DESPACHO = [
    "codigo_trayecto",
    "tipo_cobertura",
    "tipo_servicio",
    "peso_kg",
    "valor_declarado",
    "requiere_refrigeracion",
    "mercancia_peligrosa",
    "fecha_despacho",
    "fecha_estimada_entrega",
]
CATEGORICAS_RIESGO = ["codigo_trayecto", "tipo_cobertura", "tipo_servicio"]
NUMERICAS_RIESGO = [
    "peso_kg",
    "log_valor",
    "requiere_refrigeracion",
    "mercancia_peligrosa",
    "dia_semana",
    "fin_semana",
    "hora",
    "mes",
    "horas_estimadas",
]
FEATURES_RIESGO = CATEGORICAS_RIESGO + NUMERICAS_RIESGO

FEATURES_DEMANDA = ["origen", "lag1", "lag7", "lag14", "mm7", "dia_semana", "mes", "festivo"]
_FESTIVOS = holidays.country_holidays("CO")


def _local(col: pd.Series) -> pd.Series:
    d = pd.to_datetime(col)
    return d.dt.tz_convert(TZ) if d.dt.tz is not None else d


def features_riesgo(envios: pd.DataFrame) -> pd.DataFrame:
    """Una fila por envío con FEATURES_RIESGO, solo con información disponible al despacho."""
    e = envios[COLUMNAS_DESPACHO]
    despacho = _local(e.fecha_despacho)
    estimada = _local(e.fecha_estimada_entrega)
    # ponytail: peso real, no facturable (el volumétrico necesita el factor del trayecto); el modelo
    # ya ve el trayecto. Añadir peso_liquidado si la BD lo trae.
    return pd.DataFrame(
        {
            "codigo_trayecto": e.codigo_trayecto.astype(str),
            "tipo_cobertura": e.tipo_cobertura.astype(str),
            "tipo_servicio": e.tipo_servicio.astype(str),
            "peso_kg": e.peso_kg.astype(float),
            "log_valor": np.log1p(e.valor_declarado.astype(float)),
            "requiere_refrigeracion": e.requiere_refrigeracion.astype(int),
            "mercancia_peligrosa": e.mercancia_peligrosa.astype(int),
            "dia_semana": despacho.dt.day_of_week,
            "fin_semana": (despacho.dt.day_of_week >= 5).astype(int),
            "hora": despacho.dt.hour,
            "mes": despacho.dt.month,
            "horas_estimadas": (estimada - despacho).dt.total_seconds() / 3600,
        },
        index=envios.index,
    )


def serie_demanda(envios: pd.DataFrame) -> pd.DataFrame:
    """Despachos diarios por origen (fecha local), con días sin despachos en 0: columnas fecha, origen, y."""
    fecha = _local(envios.fecha_despacho).dt.tz_localize(None).dt.normalize()
    conteo = envios.groupby([fecha.rename("fecha"), envios.origen.rename("origen")]).size()
    rejilla = pd.MultiIndex.from_product(
        [pd.date_range(fecha.min(), fecha.max()), sorted(envios.origen.unique())], names=["fecha", "origen"]
    )
    return conteo.reindex(rejilla, fill_value=0).rename("y").astype(float).reset_index()


def features_demanda(serie: pd.DataFrame) -> pd.DataFrame:
    """Rezagos y media móvil por origen usando solo días ESTRICTAMENTE anteriores.

    Supone días consecutivos por origen (como entrega `serie_demanda`).
    """
    s = serie.sort_values(["origen", "fecha"]).reset_index(drop=True)
    g = s.groupby("origen").y
    return s.assign(
        lag1=g.shift(1),
        lag7=g.shift(7),
        lag14=g.shift(14),
        mm7=g.transform(lambda y: y.shift(1).rolling(7).mean()),
        dia_semana=s.fecha.dt.day_of_week,
        mes=s.fecha.dt.month,
        festivo=s.fecha.map(lambda d: d in _FESTIVOS).astype(int),
    )
