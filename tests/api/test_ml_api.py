"""Predicciones que se autoentrenan: permisos, siembra, entrenamiento inicial, champion/challenger tras
avanzar el simulador, riesgo de una guía real, pronóstico de demanda y bloqueo de entrenamientos concurrentes.

Los pasos dependen del orden (misma BD): se ejecutan en el orden del archivo.
"""

import asyncio
from datetime import date

import pytest
from sqlalchemy import func, select

from app.db import SessionLocal
from app.ml import autoentrenamiento, servicio
from app.models import Envio, ModeloMl, Prediccion
from app.models.base import EstadoModelo, OrigenDato
from app.schemas.artifacts import Grafico, MetricasModelo, TarjetaPrediccion
from tests.api.conftest import problema

R = "/api/v1/admin"
HOY = date(2026, 11, 3)
RUTAS = [
    ("get", "/ml/modelos"),
    ("get", "/ml/entrenamientos"),
    ("get", "/ml/estado"),
    ("post", "/ml/entrenar"),
    ("get", "/ml/riesgo-retraso?guia=TLX-984021-CO"),
    ("get", "/ml/pronostico-demanda?origen=Cali"),
    ("post", "/simulador/avanzar?dias=1"),
]


@pytest.fixture(scope="module")
async def sembrado():
    async with SessionLocal() as s:
        return await servicio.sembrar_historial(s, 4, hoy=HOY)


async def test_solo_admin(cliente, h_cliente, h_asesor):
    for h in (h_cliente, h_asesor):
        for metodo, ruta in RUTAS:
            problema(await cliente.request(metodo, R + ruta, headers=h), 403, "SIN_PERMISO")
    problema(await cliente.get(R + "/ml/modelos"), 401)


async def test_sin_modelo_activo_503(cliente, h_admin):
    r = await cliente.get(R + "/ml/riesgo-retraso", params={"guia": "TLX-984021-CO"}, headers=h_admin)
    problema(r, 503, "MODELO_NO_ENTRENADO")


async def test_estado_expone_reglas_y_medicion(cliente, h_admin, sembrado):
    r = await cliente.get(R + "/ml/estado", headers=h_admin)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["min_etiquetas_nuevas"] == 200 and d["max_horas"] == 24 and d["delta_deriva"] == 0.05
    assert d["n_etiquetados"] >= d["min_etiquetados"] and d["datos_simulados"] is True


async def test_siembra_respeta_esquema_y_es_idempotente(sembrado):
    assert sembrado["envios"] > 5000 and sembrado["hasta"] == "2026-11-02"
    async with SessionLocal() as s:
        n = await s.scalar(select(func.count()).select_from(Envio).where(Envio.origen_dato == OrigenDato.SIMULADO))
        assert n == sembrado["envios"]
        assert await servicio.sembrar_historial(s, 4, hoy=HOY) == {
            "envios": 0,
            "eventos": 0,
            "omitido": f"ya hay {n} envíos simulados",
        }
        sin_clase = await s.scalar(select(func.count()).where(Envio.mercancia_peligrosa, Envio.clase_onu.is_(None)))
        assert sin_clase == 0


async def test_entrenamiento_inicial_activa_ambos(cliente, h_admin, sembrado):
    r = await cliente.post(R + "/ml/entrenar", headers=h_admin)
    assert r.status_code == 202, r.text
    for nombre, m in r.json()["modelos"].items():
        assert m["promovido"] and m["estado"] == "activo" and m["motivo_entrenamiento"] == "inicial", nombre

    r = await cliente.get(R + "/ml/modelos", headers=h_admin)
    assert r.status_code == 200
    activos = {m["nombre"]: m for m in r.json()["activos"]}
    assert set(activos) == {"riesgo_retraso", "demanda"}
    assert activos["riesgo_retraso"]["metricas"]["roc_auc"] > 0.6
    assert activos["riesgo_retraso"]["linea_base"]["brier_tasa_base"] > activos["riesgo_retraso"]["metricas"]["brier"]
    assert activos["demanda"]["metricas"]["mase"] < activos["demanda"]["linea_base"]["mase_naive"]
    MetricasModelo.model_validate(servicio.artifact_metricas(r.json()["activos"]).model_dump())


async def test_riesgo_de_guia_real(cliente, h_admin):
    r = await cliente.get(R + "/ml/riesgo-retraso", params={"guia": "TLX-984021-CO"}, headers=h_admin)
    assert r.status_code == 200, r.text
    p = r.json()
    assert 0 <= p["probabilidad"] <= 1 and p["nivel"] in ("bajo", "medio", "alto")
    assert p["datos_simulados"] is True and p["version"] == 1
    TarjetaPrediccion.model_validate(servicio.artifact_prediccion(p).model_dump())
    async with SessionLocal() as s:
        assert await s.scalar(select(func.count()).where(Prediccion.numero_guia == "TLX-984021-CO")) == 1

    r = await cliente.get(R + "/ml/riesgo-retraso", params={"guia": "TLX-000000-CO"}, headers=h_admin)
    problema(r, 404, "GUIA_NO_ENCONTRADA")
    problema(await cliente.get(R + "/ml/riesgo-retraso", params={"guia": "984021"}, headers=h_admin), 422)


async def test_pronostico_por_origen_o_hub(cliente, h_admin):
    r = await cliente.get(R + "/ml/pronostico-demanda", params={"origen": "bogota d.c.", "dias": 14}, headers=h_admin)
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["origen"] == "Bogotá D.C." and len(p["pronostico"]) == 14 and len(p["historico"]) == 28
    assert all(x["p10"] <= x["prediccion"] <= x["p90"] for x in p["pronostico"])
    Grafico.model_validate(servicio.artifact_pronostico(p).model_dump())

    r = await cliente.get(R + "/ml/pronostico-demanda", params={"origen": "Bogotá", "dias": 1}, headers=h_admin)
    assert r.status_code == 200 and r.json()["origen"] == "Bogotá D.C."

    r = await cliente.get(
        R + "/ml/pronostico-demanda", params={"origen": "Hub Regional Yumbo - Valle", "dias": 3}, headers=h_admin
    )
    assert r.status_code == 200 and r.json()["origen"] == "Cali"
    problema(await cliente.get(R + "/ml/pronostico-demanda", params={"origen": "Leticia"}, headers=h_admin), 404)
    problema(
        await cliente.get(R + "/ml/pronostico-demanda", params={"origen": "Cali", "dias": 31}, headers=h_admin), 422
    )


async def test_avanzar_dispara_reentrenamiento_champion_challenger(cliente, h_admin):
    r = await cliente.post(R + "/simulador/avanzar", params={"dias": 30}, headers=h_admin)
    assert r.status_code == 200, r.text
    a = r.json()
    assert a["desde"] == "2026-11-03" and a["hasta"] == "2026-12-02"
    assert a["envios_nuevos"] > 1000 and a["envios_cerrados"] > 0 and a["datos_simulados"]

    assert await autoentrenamiento.ciclo() == "nuevos_datos"

    r = await cliente.get(R + "/ml/entrenamientos", params={"tamano": 2}, headers=h_admin)
    assert r.status_code == 200
    corridas = r.json()
    assert corridas["paginacion"]["total"] == 4
    for c in corridas["items"]:
        assert c["motivo"] == "nuevos_datos" and c["resultado"] in ("promovido", "rechazado")
        assert c["detalle"]["metricas_campeon"] is not None and c["detalle"]["version_campeon"] == 1
    async with SessionLocal() as s:
        activos = (
            await s.execute(
                select(ModeloMl.nombre, func.count())
                .where(ModeloMl.estado == EstadoModelo.ACTIVO)
                .group_by(ModeloMl.nombre)
            )
        ).all()
    assert dict(activos) == {"riesgo_retraso": 1, "demanda": 1}
    # Sin datos nuevos ni deriva y recién entrenado: no hay disparo.
    assert await autoentrenamiento.ciclo() is None


async def test_entrenamiento_concurrente_409(cliente, h_admin):
    primero = asyncio.create_task(cliente.post(R + "/ml/entrenar", headers=h_admin))
    async with asyncio.timeout(10):
        while not servicio._lock_entreno.locked():  # noqa: ASYNC110 - espera a que el 1.º tome el lock
            await asyncio.sleep(0.01)
    problema(await cliente.post(R + "/ml/entrenar", headers=h_admin), 409, "ENTRENAMIENTO_EN_CURSO")
    r = await primero
    assert r.status_code == 202, r.text
    assert {m["motivo_entrenamiento"] for m in r.json()["modelos"].values()} == {"manual"}
