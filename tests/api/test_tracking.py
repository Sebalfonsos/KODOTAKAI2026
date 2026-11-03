import pytest

from tests.api.conftest import problema

R = "/api/v1/tracking"


async def test_invitado_sin_detalle_y_telefono_enmascarado(cliente):
    r = await cliente.get(f"{R}/TLX-551904-CO")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["estado"] == "EN_REPARTO" and d["detalle"] is None
    assert d["origen"] == "Bogotá D.C." and d["destino"] == "Pereira"
    descripciones = " ".join(e["descripcion"] for e in d["eventos"])
    assert "310-987-6543" not in descripciones and "***-***-6543" in descripciones


async def test_dueno_ve_detalle(cliente, h_cliente, h_vip):
    d = (await cliente.get(f"{R}/TLX-551904-CO", headers=h_cliente)).json()
    assert d["detalle"]["valor_declarado"] == "450000.00" and d["detalle"]["unidades"] == 1
    d = (await cliente.get(f"{R}/TLX-984021-CO", headers=h_vip)).json()
    assert d["detalle"]["remitente"] == "Laboratorios PharmaSur S.A."


async def test_cuenta_ajena_no_ve_detalle(cliente, h_cliente, h_vip):
    assert (await cliente.get(f"{R}/TLX-984021-CO", headers=h_cliente)).json()["detalle"] is None
    assert (await cliente.get(f"{R}/TLX-752190-CO", headers=h_vip)).json()["detalle"] is None


async def test_admin_ve_detalle_con_cedula_enmascarada(cliente, h_admin):
    r = await cliente.get(f"{R}/TLX-752190-CO", headers=h_admin)
    d = r.json()
    assert d["estado"] == "ENTREGADO" and d["es_final"] is True
    assert d["detalle"]["recibido_por"] == "Roberto Bermúdez"
    assert d["detalle"]["documento_receptor"] == "C.C. **.**9.432"
    assert "16.789.432" not in r.text  # la palabra "Firmado" del evento no es un dato personal


@pytest.mark.parametrize("guia", ["tlx-984021-co", "TLX 984021 CO", " TLX-984021-CO "])
async def test_formato_flexible(cliente, guia):
    r = await cliente.get(f"{R}/{guia}")
    assert r.status_code == 200, r.text
    assert r.json()["numero_guia"] == "TLX-984021-CO"


@pytest.mark.parametrize("guia", ["TLX-98402-CO", "ABC-984021-CO", "TLX-9840211-CO"])
async def test_formato_invalido_422(cliente, guia):
    problema(await cliente.get(f"{R}/{guia}"), 422, "GUIA_FORMATO_INVALIDO")


async def test_inexistente_404_sin_inventar_estado(cliente):
    p = problema(await cliente.get(f"{R}/TLX-000000-CO"), 404, "GUIA_NO_ENCONTRADA")
    assert "TLX-000000-CO" in p["detail"]


async def test_retenido_marca_novedad(cliente):
    d = (await cliente.get(f"{R}/TLX-310482-CO")).json()
    assert d["estado"] == "RETENIDO_NOVEDAD" and d["novedad"] is True
