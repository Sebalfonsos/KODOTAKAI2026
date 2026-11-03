import pytest

from tests.api.conftest import problema


async def test_busqueda_sin_tildes(cliente):
    for q in ("medellin", "MEDELLÍN", "antioquia"):
        r = await cliente.get("/api/v1/cobertura/municipios", params={"q": q})
        nombres = [m["nombre"] for m in r.json()["items"]]
        assert "Medellín" in nombres, (q, nombres)


async def test_paginacion(cliente):
    todos = (await cliente.get("/api/v1/cobertura/municipios", params={"tamano": 100})).json()
    assert todos["total"] == 31 and len(todos["items"]) == 31
    p2 = (await cliente.get("/api/v1/cobertura/municipios", params={"tamano": 5, "pagina": 2})).json()
    assert p2["pagina"] == 2 and p2["tamano"] == 5 and p2["total"] == 31
    assert [m["codigo_dane"] for m in p2["items"]] == [m["codigo_dane"] for m in todos["items"][5:10]]
    problema(await cliente.get("/api/v1/cobertura/municipios", params={"tamano": 0}), 422, "VALIDACION")
    problema(await cliente.get("/api/v1/cobertura/municipios", params={"tamano": 101}), 422, "VALIDACION")


async def test_filtro_tipo_cobertura(cliente):
    r = await cliente.get("/api/v1/cobertura/municipios", params={"tipo_cobertura": "zomac", "tamano": 100})
    assert r.json()["total"] >= 1 and all(m["tipo_cobertura"] == "zomac" for m in r.json()["items"])
    problema(await cliente.get("/api/v1/cobertura/municipios", params={"tipo_cobertura": "x"}), 422, "VALIDACION")


async def test_ficha_dane(cliente):
    m = (await cliente.get("/api/v1/cobertura/municipios/05001")).json()
    assert m["nombre"] == "Medellín" and m["hub"] == "Hub Regional Itagüí - Antioquia"
    problema(await cliente.get("/api/v1/cobertura/municipios/99999"), 404, "SIN_COBERTURA")
    problema(await cliente.get("/api/v1/cobertura/municipios/5001"), 422, "VALIDACION")


async def test_origenes_y_destinos(cliente):
    origenes = [o["valor"] for o in (await cliente.get("/api/v1/trayectos/origenes")).json()]
    assert "Bogotá D.C." in origenes
    destinos = (await cliente.get("/api/v1/trayectos/destinos", params={"origen": "bogota"})).json()
    med = next(d for d in destinos if d["valor"] == "Medellín")
    assert med["codigo_trayecto"] == "TLX-BOG-MED-001" and med["tiempo_entrega_horas"] == 24
    r = await cliente.get("/api/v1/trayectos/destinos", params={"origen": "Leticia"})
    problema(r, 404, "SIN_RUTAS_DESDE_ORIGEN")


@pytest.mark.parametrize(
    ("producto", "veredicto", "clase"),
    [
        ("perro", "prohibido", None),
        ("¿Puedo enviar un gato?", "prohibido", None),
        ("pólvora", "prohibido", "1"),
        ("dinero en efectivo", "prohibido", None),
        ("5 litros de ácido clorhídrico", "restringido", "8"),
        ("baterías de litio", "restringido", "9"),
    ],
)
async def test_veredictos_mercancia(cliente, producto, veredicto, clase):
    r = await cliente.get("/api/v1/mercancias/consultar", params={"producto": producto})
    v = r.json()
    assert (v["veredicto"], v["clase_onu"]) == (veredicto, clase), v
    assert v["fuente"].startswith("DOC-OPS-2026-03")


async def test_mercancia_desconocida_no_inventa(cliente):
    v = (await cliente.get("/api/v1/mercancias/consultar", params={"producto": "zapatos de cuero"})).json()
    assert v["veredicto"] == "desconocido" and v["fuente"] is None


async def test_clases_onu(cliente):
    clases = {c["codigo"]: c for c in (await cliente.get("/api/v1/mercancias/clases")).json()}
    assert {"1", "8", "9"} <= set(clases)
    assert clases["1"]["politica"] == "prohibido"
