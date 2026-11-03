"""Modelos `riesgo_retraso` y `demanda`: entrenamiento, evaluación temporal, predicción y serialización.

Un modelo es un dict: {"nombre", "algoritmo", "estimador"|"estimadores", "metricas", "n_train",
"features", "entrenado_hasta", ...}. `metadatos(modelo)` devuelve todo menos los estimadores (JSON).
"""

import pickle

import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.calibration import CalibratedClassifierCV
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score
from sklearn.model_selection import TimeSeriesSplit
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder, OrdinalEncoder, StandardScaler

from app.ml.features import (
    CATEGORICAS_RIESGO,
    FEATURES_DEMANDA,
    FEATURES_RIESGO,
    NUMERICAS_RIESGO,
    features_demanda,
    features_riesgo,
)

DIAS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
MESES = "enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre".split()
# Grupos de features que se perturban juntos (están correlacionados entre sí).
GRUPOS_FACTORES = {
    "ruta": ["codigo_trayecto", "tipo_cobertura", "horas_estimadas"],
    "dia": ["dia_semana", "fin_semana"],
    "hora": ["hora"],
    "mes": ["mes"],
    "servicio": ["tipo_servicio", "requiere_refrigeracion", "mercancia_peligrosa"],
    "peso": ["peso_kg"],
    "valor": ["log_valor"],
}


# ---------- serialización ----------


def a_bytes(modelo: dict) -> bytes:
    return pickle.dumps(modelo, protocol=5)


def desde_bytes(datos: bytes) -> dict:
    # Solo se cargan artefactos que esta misma app escribió en su BD (ml_modelos.artefacto).
    return pickle.loads(datos)  # noqa: S301


def metadatos(modelo: dict) -> dict:
    return {k: v for k, v in modelo.items() if k not in ("estimador", "estimadores")}


# ---------- riesgo de retraso ----------


def _ordinal(categoricas: list[str], numericas: list[str]) -> ColumnTransformer:
    cod = OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=np.nan)
    return ColumnTransformer([("cat", cod, categoricas), ("num", "passthrough", numericas)])


def _logistica():
    prep = ColumnTransformer(
        [
            ("cat", OneHotEncoder(handle_unknown="ignore"), CATEGORICAS_RIESGO),
            ("num", StandardScaler(), NUMERICAS_RIESGO),
        ]
    )
    return make_pipeline(prep, LogisticRegression(max_iter=2000))


def _hgb_clasificador():
    cats = list(range(len(CATEGORICAS_RIESGO)))
    return make_pipeline(
        _ordinal(CATEGORICAS_RIESGO, NUMERICAS_RIESGO),
        HistGradientBoostingClassifier(categorical_features=cats, random_state=0),
    )


def particion_riesgo(envios: pd.DataFrame, frac_test: float = 0.2):
    """Partición TEMPORAL: holdout = último `frac_test` de envíos etiquetados por fecha de despacho.

    En entrenamiento solo entran envíos cuya etiqueta ya se conocía en el corte (entregados antes).
    """
    e = envios[envios.retrasado.notna()].sort_values("fecha_despacho", kind="stable")
    if len(e) < 200:
        raise ValueError("Se necesitan al menos 200 envíos etiquetados para entrenar riesgo_retraso")
    corte = e.fecha_despacho.iloc[int(len(e) * (1 - frac_test))]
    entreno = e[(e.fecha_despacho < corte) & (pd.to_datetime(e.fecha_entrega_real) < corte)]
    return entreno, e[e.fecha_despacho >= corte], corte


def _metricas_clf(y, p, tasa_base: float) -> dict:
    y = np.asarray(y, dtype=int)
    return {
        "roc_auc": float(roc_auc_score(y, p)),
        "brier": float(brier_score_loss(y, p)),
        "log_loss": float(log_loss(y, p, labels=[0, 1])),
        "tasa_base": float(tasa_base),
        "brier_tasa_base": float(brier_score_loss(y, np.full(len(y), tasa_base))),
        "n_test": len(y),
    }


def evaluar_riesgo(modelo: dict, envios: pd.DataFrame) -> dict:
    """Métricas del modelo sobre envíos etiquetados (p. ej. el holdout de un retador)."""
    e = envios[envios.retrasado.notna()]
    p = modelo["estimador"].predict_proba(features_riesgo(e))[:, 1]
    return _metricas_clf(e.retrasado.astype(int), p, modelo["metricas"]["tasa_base"])


def entrenar_riesgo(envios: pd.DataFrame) -> dict:
    """Regresión logística (base) vs HistGradientBoosting; gana el mayor ROC-AUC en el holdout temporal.

    Luego se prueba calibración sigmoide (CV temporal dentro del entrenamiento) y se queda si baja el Brier.
    El modelo desplegado es el entrenado antes del corte (no se reajusta con el holdout) para que
    champion y challenger se comparen en datos que ninguno vio.
    """
    entreno, prueba, corte = particion_riesgo(envios)
    x_tr, y_tr = features_riesgo(entreno), entreno.retrasado.astype(int)
    x_te, y_te = features_riesgo(prueba), prueba.retrasado.astype(int)
    tasa = float(y_tr.mean())
    candidatos = {"logistica": _logistica(), "hist_gradient_boosting": _hgb_clasificador()}
    por_candidato = {}
    for nombre, est in candidatos.items():
        est.fit(x_tr, y_tr)
        por_candidato[nombre] = _metricas_clf(y_te, est.predict_proba(x_te)[:, 1], tasa)
    mejor = max(por_candidato, key=lambda n: por_candidato[n]["roc_auc"])
    estimador, algoritmo, metricas = candidatos[mejor], mejor, por_candidato[mejor]
    # ponytail: el holdout elige algoritmo y reporta métricas (sesgo leve con 2 candidatos);
    # separar validación y prueba si se añaden más candidatos.
    calibrado = CalibratedClassifierCV(clone(estimador), method="sigmoid", cv=TimeSeriesSplit(3))
    calibrado.fit(x_tr, y_tr)
    m_cal = _metricas_clf(y_te, calibrado.predict_proba(x_te)[:, 1], tasa)
    if m_cal["brier"] < metricas["brier"]:
        estimador, algoritmo, metricas = calibrado, f"{mejor}+calibracion_sigmoide", m_cal
    return {
        "nombre": "riesgo_retraso",
        "algoritmo": algoritmo,
        "estimador": estimador,
        "metricas": {**metricas, "candidatos": por_candidato, "calibrado": m_cal},
        "n_train": len(entreno),
        "features": FEATURES_RIESGO,
        "entrenado_hasta": corte.isoformat(),
        "referencia": _referencia(x_tr),
    }


def _referencia(x: pd.DataFrame) -> dict:
    """Envío 'típico' contra el que se perturba: ruta y servicio más frecuentes, numéricos en mediana."""
    med = x[NUMERICAS_RIESGO].median()
    ruta = x[x.codigo_trayecto == x.codigo_trayecto.mode()[0]].iloc[0]
    servicio = x[x.tipo_servicio == x.tipo_servicio.mode()[0]].iloc[0]
    dia = int(round(med.dia_semana))
    return {
        "codigo_trayecto": ruta.codigo_trayecto,
        "tipo_cobertura": ruta.tipo_cobertura,
        "horas_estimadas": float(ruta.horas_estimadas),
        "tipo_servicio": servicio.tipo_servicio,
        "requiere_refrigeracion": int(servicio.requiere_refrigeracion),
        "mercancia_peligrosa": int(servicio.mercancia_peligrosa),
        "dia_semana": dia,
        "fin_semana": int(dia >= 5),
        "hora": int(round(med.hora)),
        "mes": int(round(med.mes)),
        "peso_kg": float(med.peso_kg),
        "log_valor": float(med.log_valor),
    }


def _texto_factor(grupo: str, x: pd.Series) -> str:
    match grupo:
        case "ruta":
            return f"Trayecto {x.tipo_cobertura} ({x.codigo_trayecto})"
        case "dia":
            return "Despacho en fin de semana" if x.fin_semana else f"Despacho en {DIAS[x.dia_semana]}"
        case "hora":
            return f"Despacho a las {x.hora}:00"
        case "mes":
            return "Temporada alta de diciembre" if x.mes == 12 else f"Despacho en {MESES[x.mes - 1]}"
        case "servicio":
            if x.mercancia_peligrosa:
                return "Mercancía peligrosa"
            return "Requiere cadena de frío" if x.requiere_refrigeracion else f"Servicio {x.tipo_servicio}"
        case "peso":
            return f"Carga de {x.peso_kg:g} kg"
        case _:
            return "Valor declarado"


def predecir_riesgo(modelo: dict, envio, max_factores: int = 3) -> dict:
    """Probabilidad de retraso y factores que más la suben.

    Factor = cuánto baja la probabilidad si ese grupo de features toma el valor de un envío típico
    (perturbación). Solo se listan los que suben el riesgo más de 0,5 puntos.
    """
    x = features_riesgo(pd.DataFrame([dict(envio)]))
    filas = [x]
    for columnas in GRUPOS_FACTORES.values():
        filas.append(x.assign(**{c: modelo["referencia"][c] for c in columnas}))
    p = modelo["estimador"].predict_proba(pd.concat(filas, ignore_index=True))[:, 1]
    fila = x.iloc[0]
    factores = sorted(
        (
            {"factor": _texto_factor(grupo, fila), "impacto": round(float(p[0] - p_ref), 3)}
            for grupo, p_ref in zip(GRUPOS_FACTORES, p[1:], strict=True)
            if p[0] - p_ref > 0.005
        ),
        key=lambda f: -f["impacto"],
    )
    return {"probabilidad": round(float(p[0]), 4), "factores": factores[:max_factores]}


# ---------- demanda ----------

CUANTILES = {"p10": 0.1, "p90": 0.9}


def _hgb_regresor(**kw):
    return make_pipeline(
        _ordinal(["origen"], FEATURES_DEMANDA[1:]),
        HistGradientBoostingRegressor(categorical_features=[0], random_state=0, **kw),
    )


def _ajustar_demanda(serie: pd.DataFrame, corte: pd.Timestamp):
    f = features_demanda(serie[serie.fecha < corte]).dropna(subset=["lag14", "mm7"])
    x, y = f[FEATURES_DEMANDA], f.y
    estimadores = {"punto": _hgb_regresor(loss="poisson").fit(x, y)}
    for nombre, q in CUANTILES.items():
        estimadores[nombre] = _hgb_regresor(loss="quantile", quantile=q).fit(x, y)
    return estimadores, len(f)


def _recursivo(estimadores: dict, historia: pd.DataFrame, dias: int) -> pd.DataFrame:
    """Pronóstico recursivo: cada día predicho alimenta los rezagos del siguiente."""
    fin = historia.fecha.max()
    s = historia.loc[historia.fecha > fin - pd.Timedelta(days=30), ["fecha", "origen", "y"]]
    origenes = sorted(s.origen.unique())
    salida = []
    for i in range(1, dias + 1):
        dia = fin + pd.Timedelta(days=i)
        s = pd.concat([s, pd.DataFrame({"fecha": dia, "origen": origenes, "y": np.nan})], ignore_index=True)
        f = features_demanda(s)
        x = f.loc[f.fecha == dia, FEATURES_DEMANDA]
        punto = estimadores["punto"].predict(x).clip(0)
        p10 = np.minimum(estimadores["p10"].predict(x), punto).clip(0)
        p90 = np.maximum(estimadores["p90"].predict(x), punto)
        s.loc[s.fecha == dia, "y"] = s.loc[s.fecha == dia, "origen"].map(dict(zip(x.origen, punto, strict=True)))
        salida.append(pd.DataFrame({"fecha": dia, "origen": x.origen, "prediccion": punto, "p10": p10, "p90": p90}))
    return pd.concat(salida, ignore_index=True)


def _naive_estacional(historia: pd.DataFrame, dias: int) -> pd.DataFrame:
    """Repite la última semana observada (y_t = y_{t-7})."""
    fin = historia.fecha.max()
    semana = historia[historia.fecha > fin - pd.Timedelta(days=7)]
    copias = [semana.assign(fecha=semana.fecha + pd.Timedelta(days=7 * k)) for k in range(1, dias // 7 + 2)]
    n = pd.concat(copias)
    return n[n.fecha <= fin + pd.Timedelta(days=dias)].rename(columns={"y": "naive"})[["fecha", "origen", "naive"]]


def evaluar_demanda(modelo: dict, serie: pd.DataFrame, corte: pd.Timestamp, dias: int = 14) -> dict:
    """Pronostica `dias` desde `corte` con la historia previa y compara con lo observado y el naive."""
    historia = serie[serie.fecha < corte]
    real = serie[(serie.fecha >= corte) & (serie.fecha < corte + pd.Timedelta(days=dias))]
    r = (
        _recursivo(modelo["estimadores"], historia, dias)
        .merge(real, on=["fecha", "origen"])
        .merge(_naive_estacional(historia, dias), on=["fecha", "origen"])
    )
    escala = historia.sort_values("fecha").groupby("origen").y.diff(7).abs().mean()  # MAE naive in-sample
    mae, mae_naive = (r.prediccion - r.y).abs().mean(), (r.naive - r.y).abs().mean()
    pinball = np.mean([np.maximum(q * (r.y - r[c]), (q - 1) * (r.y - r[c])).mean() for c, q in CUANTILES.items()])
    return {
        "mae": float(mae),
        "mae_naive": float(mae_naive),
        "mase": float(mae / escala),
        "mase_naive": float(mae_naive / escala),
        "cobertura_80": float(((r.y >= r.p10) & (r.y <= r.p90)).mean()),
        "pinball": float(pinball),
        "corte": corte.date().isoformat(),
        "n": len(r),
    }


def entrenar_demanda(serie: pd.DataFrame, cortes: int = 3, dias: int = 14) -> dict:
    """HistGradientBoosting (Poisson + cuantiles 0,1/0,9) vs naive estacional con backtest walk-forward.

    `cortes` ventanas consecutivas de `dias` al final de la serie (expanding window). El modelo
    desplegado es el del último corte (sus rezagos se alimentan con la historia más reciente al pronosticar).
    """
    fin = serie.fecha.max()
    if (fin - serie.fecha.min()).days < dias * (cortes + 2):
        raise ValueError("Historia insuficiente para el backtest de demanda")
    por_corte = []
    for k in range(cortes, 0, -1):
        corte = fin - pd.Timedelta(days=dias * k - 1)
        estimadores, n_train = _ajustar_demanda(serie, corte)
        por_corte.append(evaluar_demanda({"estimadores": estimadores}, serie, corte, dias))
    claves = ("mae", "mae_naive", "mase", "mase_naive", "cobertura_80", "pinball")
    return {
        "nombre": "demanda",
        "algoritmo": "hist_gradient_boosting_poisson+cuantiles",
        "estimadores": estimadores,
        "metricas": {
            **{c: float(np.mean([m[c] for m in por_corte])) for c in claves},
            "por_corte": por_corte,
            "holdout": por_corte[-1],
        },
        "n_train": n_train,
        "features": FEATURES_DEMANDA,
        "entrenado_hasta": (corte - pd.Timedelta(days=1)).date().isoformat(),
        "horizonte_dias": dias,
        "origenes": sorted(serie.origen.unique()),
    }


def pronosticar(modelo: dict, historia: pd.DataFrame, origen: str, dias: int = 14) -> pd.DataFrame:
    """Pronóstico de despachos diarios de `origen` a `dias` con intervalo 80 % (p10-p90).

    `historia`: serie diaria (fecha, origen, y) como la de `features.serie_demanda`.
    """
    h = historia[historia.origen == origen]
    if h.empty or origen not in modelo["origenes"]:
        raise ValueError(f"Origen sin modelo de demanda: {origen}")
    if not 1 <= dias <= 60:
        raise ValueError("dias debe estar entre 1 y 60")
    return _recursivo(modelo["estimadores"], h, int(dias))
