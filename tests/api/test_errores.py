"""Transversal: RFC 9457, request id, cabeceras de seguridad y mensajes en español."""

import pytest

from app.core.logging import CABECERAS_SEGURIDAD
from tests.api.conftest import problema


async def test_cabeceras_de_seguridad_y_request_id(cliente):
    for r in (await cliente.get("/health"), await cliente.get("/api/v1/tracking/TLX-000000-CO")):
        for k, v in CABECERAS_SEGURIDAD.items():
            assert r.headers[k] == v
        assert len(r.headers["x-request-id"]) >= 8 and r.headers["server-timing"].startswith("app;dur=")


async def test_request_id_entrante_valido_se_respeta_e_invalido_se_reemplaza(cliente):
    r = await cliente.get("/health", headers={"X-Request-ID": "soporte-12345678"})
    assert r.headers["x-request-id"] == "soporte-12345678"
    r = await cliente.get("/health", headers={"X-Request-ID": "<script>alert(1)</script>"})
    assert "<" not in r.headers["x-request-id"]


async def test_ruta_inexistente_404_en_espanol(cliente):
    p = problema(await cliente.get("/api/v1/no-existe"), 404)
    assert p["detail"] == "La ruta solicitada no existe." and p["title"] == "No encontrado"


async def test_metodo_no_permitido_405_en_espanol(cliente):
    p = problema(await cliente.delete("/api/v1/cotizar"), 405)
    assert p["detail"] == "Método no permitido para esta ruta."


async def test_404_y_405_traen_codigo(cliente):
    assert (await cliente.get("/api/v1/no-existe")).json().get("codigo")
    assert (await cliente.delete("/api/v1/cotizar")).json().get("codigo")


async def test_json_malformado_422_problem_json(cliente):
    r = await cliente.post("/api/v1/cotizar", content=b'{"origen": ', headers={"Content-Type": "application/json"})
    p = problema(r, 422, "VALIDACION")
    assert p["errores"]


@pytest.mark.parametrize(
    ("metodo", "ruta", "kw", "status", "codigo"),
    [
        ("post", "/api/v1/cotizar", {"json": {}, "headers": {"Idempotency-Key": "x"}}, 422, "VALIDACION"),
        ("get", "/api/v1/auth/me", {}, 401, "NO_AUTENTICADO"),
        ("get", "/api/v1/tracking/TLX-000000-CO", {}, 404, "GUIA_NO_ENCONTRADA"),
        ("get", "/api/v1/cobertura/municipios/00000", {}, 404, "SIN_COBERTURA"),
        ("get", "/api/v1/mercancias/consultar", {"params": {"producto": "x"}}, 422, "VALIDACION"),
    ],
)
async def test_todo_error_es_problem_json_con_codigo(cliente, metodo, ruta, kw, status, codigo):
    p = problema(await getattr(cliente, metodo)(ruta, **kw), status, codigo)
    assert "Traceback" not in str(p)


async def test_mensajes_de_validacion_no_devuelven_el_valor_recibido(cliente):
    secreto = "CC-1032456789-dato-personal"
    r = await cliente.get("/api/v1/cobertura/municipios", params={"tamano": secreto})
    problema(r, 422, "VALIDACION")
    assert secreto not in r.text


async def test_health(cliente):
    assert (await cliente.get("/health")).status_code == 200
