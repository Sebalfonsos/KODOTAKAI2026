"""Golden set T-COT de docs/requisitos.md §8 a través de la API."""

import asyncio
import uuid

from tests.api.conftest import problema

R = "/api/v1/cotizar"
T_COT_1 = {
    "origen": "Bogotá D.C.",
    "destino": "Medellín",
    "alto_cm": 40,
    "ancho_cm": 50,
    "largo_cm": 60,
    "peso_kg": 45.5,
    "valor_declarado": 12500000,
    "cadena_frio": True,
    "unidades": 2,
}


async def _cotizar(cliente, cuerpo, **kw):
    r = await cliente.post(R, json=cuerpo, **kw)
    assert r.status_code == 201, r.text
    return r.json()


async def test_t_cot_1_con_cadena_de_frio(cliente):
    c = await _cotizar(cliente, T_COT_1)
    d = c["desglose"]
    assert c["codigo_trayecto"] == "TLX-BOG-MED-001"
    assert d["base_cobro"] == "real" and float(d["peso_facturable_kg"]) == 45.5
    assert float(d["flete_base"]) == 65975 and float(d["seguro"]) == 125000
    assert float(d["recargo_cadena_frio"]) == 16493.75
    assert float(d["total_sin_redondeo"]) == 207468.75
    assert c["total"] == "207469" and c["moneda"] == "COP"  # ROUND_HALF_UP a pesos


async def test_t_cot_1_sin_frio_es_190975(cliente):
    c = await _cotizar(cliente, T_COT_1 | {"cadena_frio": False})
    assert c["total"] == "190975"


async def test_t_cot_2_volumetrico_con_minimo(cliente):
    c = await _cotizar(
        cliente,
        {"origen": "Bogotá D.C.", "destino": "Pereira", "alto_cm": 20, "ancho_cm": 30, "largo_cm": 40}
        | {"peso_kg": 3.2, "valor_declarado": 450000},
    )
    d = c["desglose"]
    assert c["codigo_trayecto"] == "TLX-BOG-PEI-006" and d["base_cobro"] == "volumetrico"
    assert float(d["flete_base"]) == 9480 and d["flete_minimo_aplicado"] is True
    assert float(d["seguro"]) == 4500 and c["total"] == "22500"


async def test_t_cot_3_seguro_minimo_del_csv(cliente):
    c = await _cotizar(
        cliente,
        {"origen": "bogota", "destino": "Barranquilla", "alto_cm": 30, "ancho_cm": 30, "largo_cm": 30}
        | {"peso_kg": 2, "valor_declarado": 200000},
    )
    assert float(c["desglose"]["peso_volumetrico_kg"]) == 6.75
    assert float(c["desglose"]["seguro"]) == 4000  # D-01: mínimo de la ruta, no $2.500 del dosier
    assert c["total"] == "26000"


async def test_t_cot_4_carga_masiva(cliente):
    c = await _cotizar(
        cliente,
        {"origen": "Medellín", "destino": "Cali", "alto_cm": 180, "ancho_cm": 220, "largo_cm": 400}
        | {"peso_kg": 3200, "valor_declarado": 85000000, "modalidad": "carga", "unidades": 4},
    )
    d = c["desglose"]
    assert float(d["peso_volumetrico_kg"]) == 3960 and d["base_cobro"] == "volumetrico"
    assert float(d["flete_base"]) == 6732000 and float(d["seguro"]) == 850000
    assert c["total"] == "7582000"


async def test_t_cot_5_trayecto_inexistente_404(cliente):
    for o, d in (("Barranquilla", "Bucaramanga"), ("Villavicencio", "Florencia")):
        cuerpo = T_COT_1 | {"origen": o, "destino": d, "cadena_frio": False}
        p = problema(await cliente.post(R, json=cuerpo), 404, "TRAYECTO_INEXISTENTE")
        assert "asesor" in p["detail"]


async def test_t_cot_6_paqueteria_60_kg_422(cliente):
    cuerpo = T_COT_1 | {"peso_kg": 60, "cadena_frio": False}
    problema(await cliente.post(R, json=cuerpo), 422, "PAQUETERIA_EXCEDE_50_KG")
    assert (await cliente.post(R, json=cuerpo | {"modalidad": "carga"})).status_code == 201


async def test_contenido_prohibido_422(cliente):
    p = problema(await cliente.post(R, json=T_COT_1 | {"contenido": "un perro"}), 422, "MERCANCIA_PROHIBIDA")
    assert "DOC-OPS-2026-03" in p["detail"]


async def test_validacion_de_campos_422(cliente):
    malo = T_COT_1 | {"peso_kg": -1, "alto_cm": "abc", "inventado": 1}
    p = problema(await cliente.post(R, json=malo), 422, "VALIDACION")
    assert {e["campo"] for e in p["errores"]} >= {"peso_kg", "alto_cm", "inventado"}


async def test_idempotency_key(cliente):
    clave = {"Idempotency-Key": f"cot-{uuid.uuid4()}"}
    a = await _cotizar(cliente, T_COT_1, headers=clave)
    b = await _cotizar(cliente, T_COT_1, headers=clave)
    assert a == b  # misma respuesta, mismo id: no se duplicó
    p = problema(await cliente.post(R, json=T_COT_1 | {"unidades": 3}, headers=clave), 409)
    assert p["codigo"] == "IDEMPOTENCY_KEY_REUTILIZADA"


async def test_idempotency_key_invalida_400(cliente):
    problema(await cliente.post(R, json=T_COT_1, headers={"Idempotency-Key": "corta"}), 400, "IDEMPOTENCY_KEY_INVALIDA")


async def test_idempotency_key_concurrente_no_da_500(cliente):
    """Dos reintentos simultáneos con la misma clave: uno crea y el otro repite o recibe 409, nunca 500."""
    clave = {"Idempotency-Key": f"cot-{uuid.uuid4()}"}
    r1, r2 = await asyncio.gather(*(cliente.post(R, json=T_COT_1, headers=clave) for _ in range(2)))
    assert {r1.status_code, r2.status_code} <= {201, 409}, (r1.text, r2.text)


async def test_get_cotizacion_y_propiedad(cliente, h_cliente, h_vip, h_admin):
    c = await _cotizar(cliente, T_COT_1, headers=h_cliente)
    url = f"/api/v1/cotizaciones/{c['id']}"
    r = await cliente.get(url, headers=h_cliente)
    assert r.status_code == 200 and r.json()["total"] == "207469"
    assert r.json()["desglose"] == c["desglose"]
    assert (await cliente.get(url, headers=h_admin)).status_code == 200
    problema(await cliente.get(url, headers=h_vip), 404, "COTIZACION_NO_ENCONTRADA")  # ajena
    problema(await cliente.get(url), 404, "COTIZACION_NO_ENCONTRADA")
    problema(await cliente.get(f"/api/v1/cotizaciones/{uuid.uuid4()}"), 404, "COTIZACION_NO_ENCONTRADA")
    problema(await cliente.get("/api/v1/cotizaciones/no-es-uuid"), 422, "VALIDACION")
