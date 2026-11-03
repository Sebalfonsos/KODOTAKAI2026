"""Chat con LLM y RAG simulados: prueba el pipeline (artifacts, verificador, escalamiento, SSE) sin la GPU."""

import json

import pytest

from app.ai import orquestador, router
from tests.api.conftest import problema

B = "/api/v1/chat/sesiones"


class LLMFalso:
    """Respuestas programables. `texto` es lo que "dice" el modelo al redactar."""

    texto = "No tengo esa información confirmada."
    intencion = "general"

    async def stream(self, mensajes, max_tokens=None):
        for parte in self.texto.split(" "):
            yield parte + " "

    async def extraer_json(self, mensajes, schema, max_tokens=160):
        if "intencion" in schema.get("properties", {}):
            return {"intencion": self.intencion, "producto": None, "ciudad": None}
        return {}

    async def completar(self, mensajes, max_tokens=None):
        return "Resumen de prueba."


@pytest.fixture
def llm(monkeypatch):
    falso = LLMFalso()
    monkeypatch.setattr(orquestador, "get_llm", lambda: falso)
    monkeypatch.setattr(router, "get_llm", lambda: falso, raising=False)

    async def sin_rag(s, consulta, k=4, tipos=None):
        return []

    monkeypatch.setattr(orquestador.rag, "buscar", sin_rag)
    return falso


async def _sesion(cliente, headers=None) -> str:
    r = await cliente.post(B, headers=headers or {})
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _turno(cliente, sid, cuerpo, headers=None) -> dict:
    r = await cliente.post(f"{B}/{sid}/mensajes?stream=false", json=cuerpo, headers=headers or {})
    assert r.status_code == 200, r.text
    return r.json()


def _tipos(d: dict) -> list[str]:
    return [a["tipo"] for a in d["artifacts"]]


async def test_saludo_y_rastreo_sin_llm(cliente, llm):
    sid = await _sesion(cliente)
    d = await _turno(cliente, sid, {"tipo": "texto", "texto": "hola"})
    assert d["intencion"] == "saludo" and "respuestas_rapidas" in _tipos(d)
    d = await _turno(cliente, sid, {"tipo": "texto", "texto": "dónde va la tlx-984021-co?"})
    assert d["intencion"] == "rastrear"
    assert _tipos(d)[:2] == ["linea_tiempo_envio", "mapa_ubicacion"]
    assert "TLX-984021-CO" in d["texto"] and d["confianza"] >= 0.95


async def test_formulario_cotizacion_validado_en_servidor(cliente, llm):
    sid = await _sesion(cliente)
    d = await _turno(cliente, sid, {"tipo": "texto", "texto": "quiero cotizar"})
    form = next(a for a in d["artifacts"] if a["tipo"] == "formulario_cotizacion")
    assert form["acciones"][0]["payload"] == {"tipo": "artifact_submit", "artifact_id": form["id"]}

    malo = {"tipo": "artifact_submit", "artifact_id": form["id"], "valores": {"origen": "Bogotá D.C.", "peso_kg": "x"}}
    r = await cliente.post(f"{B}/{sid}/mensajes?stream=false", json=malo)
    problema(r, 422, "FORMULARIO_INVALIDO")

    r = await cliente.post(
        f"{B}/{sid}/mensajes?stream=false",
        json={"tipo": "artifact_submit", "artifact_id": "fco_inventado", "valores": {}},
    )
    problema(r, 404, "FORMULARIO_NO_ENCONTRADO")

    valores = {
        "origen": "Bogotá D.C.",
        "destino": "Medellín",
        "alto_cm": 40,
        "ancho_cm": 50,
        "largo_cm": 60,
        "peso_kg": 45.5,
        "valor_declarado_cop": 12500000,
        "servicio": "cadena_frio",
        "unidades": 2,
    }
    d = await _turno(cliente, sid, {"tipo": "artifact_submit", "artifact_id": form["id"], "valores": valores})
    res = next(a for a in d["artifacts"] if a["tipo"] == "resultado_cotizacion")
    assert res["total"] == "207469" and res["base_facturacion"] == "real"
    assert "$207.469" in d["texto"]


async def test_verificador_corrige_alucinacion(cliente, llm):
    """El LLM afirma que se puede enviar un perro; el veredicto determinista dice prohibido → se reemplaza."""
    llm.texto = "Sí, podemos enviar tu perro a Medellín sin problema."
    sid = await _sesion(cliente)
    d = await _turno(cliente, sid, {"tipo": "texto", "texto": "¿Puedo enviar un perro a Medellín?"})
    veredicto = next(a for a in d["artifacts"] if a["tipo"] == "veredicto_mercancia")
    assert veredicto["veredicto"] == "prohibido"
    assert d["reemplazado"] is True and d["texto"].startswith("No.")


async def test_baja_confianza_escala_crit001(cliente, llm):
    llm.intencion = "general"
    sid = await _sesion(cliente)
    d = await _turno(cliente, sid, {"tipo": "texto", "texto": "¿cuál es el color favorito del conductor de Yumbo?"})
    assert d["escalamiento"]["criterio"] == "CRIT-001" and "aviso_escalamiento" in _tipos(d)


async def test_molestia_escala_y_luego_va_al_asesor(cliente, llm):
    sid = await _sesion(cliente)
    d = await _turno(cliente, sid, {"tipo": "texto", "texto": "Esto es una estafa, voy a demandar"})
    assert d["escalamiento"]["criterio"] == "CRIT-002" and d["escalamiento"]["prioridad"] == "alta"
    d = await _turno(cliente, sid, {"tipo": "texto", "texto": "¿hola?"})
    assert d["intencion"] == "asesor_humano"


async def test_basico_no_escala(cliente, llm):
    llm.texto = "No tengo esa información confirmada."
    sid = await _sesion(cliente)
    d = await _turno(cliente, sid, {"tipo": "texto", "texto": "Hola, ¿cómo embalo un servicio básico de vidrio?"})
    assert d["escalamiento"] is None or d["escalamiento"]["criterio"] != "CRIT-002"


async def test_sse_formato_y_orden(cliente, llm):
    sid = await _sesion(cliente)
    async with cliente.stream("POST", f"{B}/{sid}/mensajes", json={"tipo": "texto", "texto": "TLX-551904-CO"}) as r:
        assert r.headers["content-type"].startswith("text/event-stream")
        cuerpo = "".join([t async for t in r.aiter_text()])
    eventos = [b.split("\n")[0].removeprefix("event: ") for b in cuerpo.strip().split("\n\n")]
    assert eventos[0] == "meta" and eventos[-1] == "fin" and "artifact" in eventos
    datos = json.loads(cuerpo.strip().split("\n\n")[-1].split("data: ", 1)[1])
    assert datos["latencias_ms"]["total"] > 0


async def test_sesion_de_usuario_es_privada(cliente, llm, h_cliente, h_vip):
    sid = await _sesion(cliente, h_cliente)
    cuerpo = {"tipo": "texto", "texto": "hola"}
    r = await cliente.post(f"{B}/{sid}/mensajes?stream=false", json=cuerpo, headers=h_vip)
    problema(r, 404, "SESION_NO_ENCONTRADA")
    r = await cliente.get(f"{B}/{sid}")
    problema(r, 404, "SESION_NO_ENCONTRADA")


async def test_pqrs_por_chat_crea_radicado(cliente, llm, h_cliente):
    sid = await _sesion(cliente, h_cliente)
    d = await _turno(cliente, sid, {"tipo": "texto", "texto": "Mi paquete TLX-551904-CO llegó roto"}, h_cliente)
    assert d["intencion"] == "pqrs_radicar"
    form = next(a for a in d["artifacts"] if a["tipo"] == "formulario_pqrs")
    valores = {"tipo": "Q", "guia": "TLX-551904-CO", "descripcion": "El conductor fue muy grosero en la entrega."}
    d = await _turno(
        cliente, sid, {"tipo": "artifact_submit", "artifact_id": form["id"], "valores": valores}, h_cliente
    )
    ticket = next(a for a in d["artifacts"] if a["tipo"] == "ticket_pqrs")
    assert ticket["radicado"].startswith("PQRS-") and ticket["tipo_pqrs"] == "Q"


async def test_historial_y_calificacion(cliente, llm):
    sid = await _sesion(cliente)
    await _turno(cliente, sid, {"tipo": "texto", "texto": "hola"})
    h = (await cliente.get(f"{B}/{sid}")).json()
    assert [m["rol"] for m in h["mensajes"]] == ["usuario", "asistente"]
    assert (await cliente.post(f"{B}/{sid}/calificacion", json={"puntaje": 5})).status_code == 204
    problema(await cliente.post(f"{B}/{sid}/calificacion", json={"puntaje": 9}), 422)


async def test_chat_admin(cliente, llm, h_admin, h_cliente):
    r = await cliente.post("/api/v1/admin/chat?stream=false", json={"texto": "kpis"}, headers=h_cliente)
    problema(r, 403)
    llm.texto = "Resumen sin cifras inventadas."
    r = await cliente.post(
        "/api/v1/admin/chat?stream=false", json={"texto": "¿Qué envíos están retenidos?"}, headers=h_admin
    )
    d = r.json()
    assert r.status_code == 200 and d["intencion"] == "envios_novedad"
    tabla = d["artifacts"][0]
    assert tabla["tipo"] == "tabla_datos" and any(f["guia"] == "TLX-310482-CO" for f in tabla["filas"])
    r = await cliente.post("/api/v1/admin/chat?stream=false", json={"texto": "dame los kpis"}, headers=h_admin)
    assert r.json()["artifacts"][0]["tipo"] == "tarjetas_kpi"
