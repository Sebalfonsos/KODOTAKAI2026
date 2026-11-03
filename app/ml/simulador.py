"""Simulador etiquetado de envíos. TODOS sus datos son SIMULADOS (`origen_dato='simulado'`).

Los trayectos, municipios, hubs, horas de SLA y observaciones de ruta salen de KODOTAKAIINFO; los
parámetros de abajo son la mecánica del simulador (supuestos plausibles), no datos de negocio.

Demanda: cada trayecto despacha Poisson(λ) envíos por día, con
    λ = DEMANDA_BASE[cobertura] × FACTOR_SEMANA[día] × FACTOR_MES[mes] × (FACTOR_FESTIVO si festivo CO)
        × (1 + TENDENCIA_ANUAL × años desde REFERENCIA_TENDENCIA).
Los trayectos con frecuencia restringida en `observaciones_ruta` (p. ej. "martes y viernes") solo
despachan esos días. Solo despachan los municipios de origen de la matriz.

Retraso (entrega real > estimada): retrasado ~ Bernoulli(sigmoide(logit)), con
    logit = LOGIT_COBERTURA[cobertura] (Urbana < Especial < Frontera < ZOMAC)
          + EFECTOS si: paso de montaña en observaciones ("montaña", "La Linea", "Páramo"),
            despacho en fin de semana, cadena de frío, mercancía peligrosa, diciembre,
            despacho tarde (>= 17 h), carga pesada (>= 1000 kg)
          + RUIDO × ruido logístico.
Un envío retrasado llega 2 h + Exp(media 35 % del SLA) después de lo estimado; uno a tiempo llega
hasta 25 % del SLA antes.

Determinismo: cada día usa su propio RNG (semilla, día) y el desenlace de cada guía sale de un hash
(número de guía, semilla). Por eso `generar(d0, d1)` seguido de `avanzar(n)` produce exactamente lo
mismo que `generar(d0, d1 + n)`, y `avanzar` puede cerrar pendientes leyendo solo las filas guardadas.

`envios_df`: numero_guia (TLX-NNNNNN-CO), codigo_trayecto, origen, destino, hub_origen, tipo_cobertura,
tipo_servicio, peso_kg, dimensiones (dict alto/ancho/largo en cm), valor_declarado (Decimal COP),
requiere_refrigeracion, mercancia_peligrosa, fecha_despacho, fecha_estimada_entrega,
fecha_entrega_real (NaT si no ha llegado), estado_actual, retrasado (boolean, <NA> si no ha llegado),
origen_dato. Fechas tz-aware America/Bogota.
`eventos_df`: numero_guia, timestamp, estado, hub_ubicacion, descripcion.
"""

from datetime import date, timedelta
from decimal import Decimal

import holidays
import numpy as np
import pandas as pd

TZ = "America/Bogota"

DEMANDA_BASE = {"Urbana Principal": 4.0, "Trayecto Especial": 2.5, "Frontera": 2.5, "Zona ZOMAC": 3.0}
FACTOR_SEMANA = (1.0, 1.05, 1.05, 1.1, 1.15, 0.6, 0.25)  # lunes..domingo
FACTOR_MES = {1: 0.8, 11: 1.2, 12: 1.6}
FACTOR_FESTIVO = 0.3
TENDENCIA_ANUAL = 0.08
REFERENCIA_TENDENCIA = date(2025, 1, 1)
# ponytail: dos patrones de frecuencia de la matriz; si aparecen otros, añadirlos aquí.
FRECUENCIAS = {"martes y viernes": {1, 4}, "3 veces por semana": {0, 2, 4}}

LOGIT_COBERTURA = {"Urbana Principal": -2.4, "Trayecto Especial": -1.7, "Frontera": -1.2, "Zona ZOMAC": -0.3}
EFECTOS = {
    "montana": 0.7,
    "fin_semana": 0.6,
    "frio": 0.4,
    "peligrosa": 0.5,
    "diciembre": 0.4,
    "tarde": 0.3,
    "pesada": 0.3,
}
RUIDO = 0.5
PALABRAS_MONTANA = ("montaña", "la linea", "páramo")

# nombre, probabilidad, mediana de peso kg, sigma log-peso, mediana valor COP, frío, peligrosa
SERVICIOS = (
    ("Paquetería Exprés Última Milla", 0.40, 3, 0.8, 300_000, False, False),
    ("Carga Semimasiva", 0.25, 80, 0.7, 3_000_000, False, False),
    ("Transporte de Carga Masiva (FTL)", 0.10, 1500, 0.4, 40_000_000, False, False),
    ("Transporte Cadena de Frío (2°C a 8°C)", 0.15, 40, 0.6, 8_000_000, True, False),
    ("Transporte de Mercancía Peligrosa", 0.10, 60, 0.6, 5_000_000, False, True),
)
SEMIMASIVA = 1  # sustituye a cadena de frío cuando el destino no tiene servicio refrigerado

COLUMNAS_BASE = [
    "numero_guia",
    "codigo_trayecto",
    "origen",
    "destino",
    "hub_origen",
    "tipo_cobertura",
    "tipo_servicio",
    "peso_kg",
    "dimensiones",
    "valor_declarado",
    "requiere_refrigeracion",
    "mercancia_peligrosa",
    "fecha_despacho",
    "fecha_estimada_entrega",
]


def _corte(dia: date) -> pd.Timestamp:
    """Inicio del día siguiente: todo lo anterior (estricto) ya ocurrió."""
    return pd.Timestamp(dia + timedelta(days=1)).tz_localize(TZ)


def _simular_despachos(trayectos, municipios, desde, hasta, semilla, inicio, excluir) -> pd.DataFrame:
    t = trayectos.reset_index(drop=True)
    muni = municipios.set_index("municipio")
    base = t.tipo_cobertura.map(DEMANDA_BASE).to_numpy()
    if np.isnan(base).any():
        raise ValueError(f"tipo_cobertura desconocido: {set(t.tipo_cobertura) - set(DEMANDA_BASE)}")
    obs = t.observaciones_ruta.str.lower()
    permitidos = [next((dias for patron, dias in FRECUENCIAS.items() if patron in o), set(range(7))) for o in obs]
    peso_max = np.minimum(
        muni.loc[t.ciudad_origen, "peso_maximo_paquete_kg"].to_numpy(),
        muni.loc[t.ciudad_destino, "peso_maximo_paquete_kg"].to_numpy(),
    )
    sin_frio = ~muni.loc[t.ciudad_destino, "servicio_refrigerado_disponible"].to_numpy(bool)
    probs = [s[1] for s in SERVICIOS]
    festivos = holidays.country_holidays("CO")

    partes = []
    for dia in pd.date_range(desde, hasta).date:
        rng = np.random.default_rng([semilla, dia.toordinal()])
        factor = FACTOR_SEMANA[dia.weekday()] * FACTOR_MES.get(dia.month, 1.0)
        factor *= FACTOR_FESTIVO if dia in festivos else 1.0
        factor *= 1 + TENDENCIA_ANUAL * (dia - REFERENCIA_TENDENCIA).days / 365
        lam = base * factor * np.array([dia.weekday() in p for p in permitidos])
        idx = np.repeat(np.arange(len(t)), rng.poisson(lam))
        n = len(idx)
        servicio = rng.choice(len(SERVICIOS), size=n, p=probs)
        servicio[(servicio == 3) & sin_frio[idx]] = SEMIMASIVA
        partes.append(
            pd.DataFrame(
                {
                    "i": idx,
                    "dia": pd.Timestamp(dia),
                    "minutos": rng.integers(6 * 60, 21 * 60, size=n),
                    "servicio": servicio,
                    "z_peso": rng.standard_normal(n),
                    "z_valor": rng.standard_normal(n),
                    "u_dim": rng.uniform(0.6, 1.4, size=n),
                }
            )
        )
    d = pd.concat(partes, ignore_index=True)

    numeros, n = [], inicio
    while len(numeros) < len(d):
        if f"TLX-{n:06d}-CO" not in excluir:
            numeros.append(n)
        n += 1

    serv = d.servicio.to_numpy()
    mediana_peso = np.array([s[2] for s in SERVICIOS])[serv]
    sigma_peso = np.array([s[3] for s in SERVICIOS])[serv]
    peso = np.minimum(mediana_peso * np.exp(sigma_peso * d.z_peso), peso_max[d.i]).round(1).clip(0.1)
    valor = np.array([s[4] for s in SERVICIOS])[serv] * np.exp(0.8 * d.z_valor)
    lado = np.cbrt(peso * t.factor_divisitivas_volumetrico.to_numpy()[d.i] * d.u_dim)
    tr = t.iloc[d.i].reset_index(drop=True)
    despacho = (d.dia + pd.to_timedelta(d.minutos, unit="min")).dt.tz_localize(TZ)
    return pd.DataFrame(
        {
            "numero_guia": [f"TLX-{x:06d}-CO" for x in numeros],
            "codigo_trayecto": tr.codigo_trayecto,
            "origen": tr.ciudad_origen,
            "destino": tr.ciudad_destino,
            "hub_origen": muni.loc[tr.ciudad_origen, "hub_operativo_asignado"].to_numpy(),
            "tipo_cobertura": tr.tipo_cobertura,
            "tipo_servicio": [SERVICIOS[s][0] for s in serv],
            "peso_kg": peso,
            "dimensiones": [{"alto": round(x * 0.8), "ancho": round(x), "largo": round(x * 1.25)} for x in lado],
            "valor_declarado": [Decimal(int(round(v, -3)) or 1000) for v in valor],
            "requiere_refrigeracion": np.array([s[5] for s in SERVICIOS])[serv],
            "mercancia_peligrosa": np.array([s[6] for s in SERVICIOS])[serv],
            "fecha_despacho": despacho,
            "fecha_estimada_entrega": despacho + pd.to_timedelta(tr.tiempo_entrega_estimado_horas, unit="h"),
        }
    )


def _uniformes(numeros: np.ndarray, semilla: int, k: int) -> np.ndarray:
    """k uniformes [0,1) por guía, deterministas por (número, semilla) (hash splitmix64)."""
    with np.errstate(over="ignore"):
        x = numeros.astype(np.uint64)[:, None] * np.uint64(0x9E3779B97F4A7C15)
        x = x ^ (np.full_like(x, semilla) * np.uint64(0xBF58476D1CE4E5B9) + np.arange(k, dtype=np.uint64))
        x = (x ^ (x >> np.uint64(30))) * np.uint64(0xBF58476D1CE4E5B9)
        x = (x ^ (x >> np.uint64(27))) * np.uint64(0x94D049BB133111EB)
        x ^= x >> np.uint64(31)
    return (x >> np.uint64(11)).astype(np.float64) / 2.0**53


def _resolver(envios: pd.DataFrame, trayectos: pd.DataFrame, semilla: int) -> pd.DataFrame:
    """Desenlace verdadero de cada envío (columnas _entrega, _retrasado, _ts_*)."""
    v = envios[COLUMNAS_BASE].reset_index(drop=True)
    obs = trayectos.set_index("codigo_trayecto").observaciones_ruta.str.lower()
    montana = obs.map(lambda o: any(p in o for p in PALABRAS_MONTANA))
    u = _uniformes(v.numero_guia.str[4:10].astype(int).to_numpy(), semilla, 4).clip(1e-12, 1 - 1e-12)
    despacho = v.fecha_despacho
    logit = (
        v.tipo_cobertura.map(LOGIT_COBERTURA).to_numpy(float)
        + EFECTOS["montana"] * v.codigo_trayecto.map(montana).to_numpy(float)
        + EFECTOS["fin_semana"] * (despacho.dt.day_of_week >= 5)
        + EFECTOS["frio"] * v.requiere_refrigeracion.astype(float)
        + EFECTOS["peligrosa"] * v.mercancia_peligrosa.astype(float)
        + EFECTOS["diciembre"] * (despacho.dt.month == 12)
        + EFECTOS["tarde"] * (despacho.dt.hour >= 17)
        + EFECTOS["pesada"] * (v.peso_kg >= 1000)
        + RUIDO * np.log(u[:, 1] / (1 - u[:, 1]))
    )
    retrasado = u[:, 0] < 1 / (1 + np.exp(-logit.to_numpy(float)))
    sla_h = (v.fecha_estimada_entrega - despacho).dt.total_seconds() / 3600
    ajuste_h = np.where(retrasado, 2 - np.log(u[:, 2]) * 0.35 * sla_h, -u[:, 2] * 0.25 * sla_h)
    v["_retrasado"] = retrasado
    v["_entrega"] = (v.fecha_estimada_entrega + pd.to_timedelta(ajuste_h, unit="h")).dt.round("min")
    duracion = v._entrega - despacho
    v["_ts_solicitud"] = (despacho - pd.to_timedelta(1 + 3 * u[:, 3], unit="h")).dt.round("min")
    v["_ts_transito"] = (despacho + 0.4 * duracion).dt.round("min")
    v["_ts_novedad"] = (despacho + 0.7 * duracion).dt.round("min").where(v._retrasado)
    return v


def _observar(verdad: pd.DataFrame, corte: pd.Timestamp) -> pd.DataFrame:
    """Vista de las guías tal como se conocen antes de `corte`."""
    o = verdad[COLUMNAS_BASE].copy()
    llego = verdad._entrega < corte
    o["fecha_entrega_real"] = verdad._entrega.where(llego)
    o["estado_actual"] = np.select(
        [llego, verdad._ts_novedad < corte, verdad._ts_transito < corte, verdad.fecha_despacho < corte],
        ["ENTREGADO", "RETENIDO_NOVEDAD", "EN_TRANSITO", "RECOGIDO_EN_ORIGEN"],
        "SOLICITUD_GENERADA",
    )
    o["retrasado"] = pd.array(verdad._retrasado, dtype="boolean")
    o.loc[~llego, "retrasado"] = pd.NA
    o["origen_dato"] = "simulado"
    return o


def _eventos(verdad: pd.DataFrame, municipios: pd.DataFrame, desde, hasta) -> pd.DataFrame:
    """Eventos de trazabilidad con desde <= timestamp < hasta (desde=None: sin límite inferior)."""
    hub = municipios.set_index("municipio").hub_operativo_asignado
    hub_destino = verdad.destino.map(hub)
    tipos = [
        ("_ts_solicitud", "SOLICITUD_GENERADA", "Portal Web Clientes TransLogix", "Guía generada."),
        ("fecha_despacho", "RECOGIDO_EN_ORIGEN", verdad.hub_origen, "Carga recogida e inspeccionada."),
        ("_ts_transito", "EN_TRANSITO", verdad.hub_origen, "Vehículo en ruta hacia destino."),
        ("_ts_novedad", "RETENIDO_NOVEDAD", hub_destino, "Novedad en ruta: el envío supera su SLA."),
        ("_entrega", "ENTREGADO", hub_destino, "Entrega confirmada al destinatario."),
    ]
    partes = [
        pd.DataFrame(
            {
                "numero_guia": verdad.numero_guia,
                "timestamp": verdad[col],
                "estado": estado,
                "hub_ubicacion": lugar,
                "descripcion": texto,
            }
        )
        for col, estado, lugar, texto in tipos
    ]
    e = pd.concat(partes, ignore_index=True).dropna(subset=["timestamp"])
    dentro = (e.timestamp < hasta) & ((e.timestamp >= desde) if desde is not None else True)
    return e[dentro].sort_values(["timestamp", "numero_guia"], kind="stable").reset_index(drop=True)


def generar_historial(
    trayectos_df: pd.DataFrame,
    municipios_df: pd.DataFrame,
    desde: date,
    hasta: date,
    semilla: int = 2026,
    excluir: frozenset[str] = frozenset(),
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Envíos despachados entre `desde` y `hasta` (inclusive) observados al cierre de `hasta`.

    `excluir`: números de guía reales que no se pueden reutilizar.
    """
    despachos = _simular_despachos(trayectos_df, municipios_df, desde, hasta, semilla, 1, excluir)
    verdad = _resolver(despachos, trayectos_df, semilla)
    corte = _corte(hasta)
    return _observar(verdad, corte), _eventos(verdad, municipios_df, None, corte)


def avanzar(estado: dict, dias: int, semilla: int = 2026) -> tuple[dict, pd.DataFrame, pd.DataFrame]:
    """Simula `dias` días más: despacha envíos nuevos y cierra los pendientes que ya llegaron.

    `estado` = {"envios", "trayectos", "municipios", "hasta"} (usar la misma semilla de la generación).
    Devuelve (estado nuevo, envíos nuevos o actualizados para upsert por numero_guia, eventos nuevos).
    """
    env, hasta = estado["envios"], estado["hasta"]
    nuevo_hasta = hasta + timedelta(days=dias)
    sim = env[env.origen_dato == "simulado"]
    inicio = int(sim.numero_guia.str[4:10].astype(int).max()) + 1 if len(sim) else 1
    nuevos = _simular_despachos(
        estado["trayectos"],
        estado["municipios"],
        hasta + timedelta(days=1),
        nuevo_hasta,
        semilla,
        inicio,
        frozenset(env.numero_guia),
    )
    pendientes = sim[sim.estado_actual != "ENTREGADO"]
    verdad = _resolver(pd.concat([pendientes[COLUMNAS_BASE], nuevos]), estado["trayectos"], semilla)
    cambios = _observar(verdad, _corte(nuevo_hasta))
    eventos = _eventos(verdad, estado["municipios"], _corte(hasta), _corte(nuevo_hasta))
    envios = pd.concat([env[~env.numero_guia.isin(cambios.numero_guia)], cambios], ignore_index=True)
    return {**estado, "envios": envios, "hasta": nuevo_hasta}, cambios, eventos
