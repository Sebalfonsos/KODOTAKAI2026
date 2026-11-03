import json
from datetime import date
from decimal import Decimal

import pytest
from pydantic import TypeAdapter, ValidationError

from app.schemas.artifacts import FormularioCotizacion, FormularioGuia, FormularioPqrs
from app.schemas.chat import (
    ChatTurnResponse,
    ErrorFormulario,
    EventoArtifact,
    EventoDelta,
    EventoError,
    EventoFin,
    MensajeArtifactSubmit,
    MensajeEntrada,
    formatear_sse,
    validar_envio_formulario,
)

ENTRADA = TypeAdapter(MensajeEntrada)


def _ejemplo(modelo, i=0):
    return modelo.model_config["json_schema_extra"]["examples"][i]


COTIZACION = FormularioCotizacion.model_validate(_ejemplo(FormularioCotizacion))
GUIA = FormularioGuia.model_validate(_ejemplo(FormularioGuia))
PQRS = FormularioPqrs.model_validate(_ejemplo(FormularioPqrs))
VALORES_OK = _ejemplo(MensajeArtifactSubmit)["valores"]


# --- entrada ----------------------------------------------------------------------------------


def test_mensaje_entrada_discriminado():
    assert ENTRADA.validate_python({"tipo": "texto", "texto": "hola"}).texto == "hola"
    sub = ENTRADA.validate_python(_ejemplo(MensajeArtifactSubmit))
    assert isinstance(sub, MensajeArtifactSubmit)


@pytest.mark.parametrize(
    "malo",
    [
        {"tipo": "texto", "texto": ""},
        {"tipo": "texto", "texto": "x" * 2001},
        {"tipo": "texto"},
        {"texto": "sin tipo"},
        {"tipo": "texto", "texto": "hola", "extra": 1},
        {"tipo": "artifact_submit", "valores": {}},
    ],
)
def test_mensaje_entrada_invalido(malo):
    with pytest.raises(ValidationError):
        ENTRADA.validate_python(malo)


# --- SSE --------------------------------------------------------------------------------------


def test_formatear_sse():
    linea = formatear_sse(EventoDelta(texto="Hola"))
    assert linea == 'event: delta\ndata: {"texto":"Hola"}\n\n'


def test_evento_artifact_y_fin_serializan():
    ev = EventoArtifact(artifact=_ejemplo(FormularioGuia))
    cuerpo = formatear_sse(ev)
    assert cuerpo.startswith("event: artifact\ndata: ")
    datos = json.loads(cuerpo.split("data: ", 1)[1])
    assert datos["artifact"]["tipo"] == "formulario_guia"
    fin = EventoFin(turno_id="t", confianza=0.9, latencias_ms={"router": 1.5, "total": 300})
    assert '"llm_total"' not in formatear_sse(fin)  # etapas no ejecutadas se omiten


def test_evento_error_es_problem_json():
    ev = EventoError(title="LLM no disponible", status=503, detail="Reintenta en 10 s")
    assert formatear_sse(ev).startswith("event: error\n")
    with pytest.raises(ValidationError):
        EventoError(title="x", status=200)


def test_chat_turn_response_ejemplo():
    r = ChatTurnResponse.model_validate(_ejemplo(ChatTurnResponse))
    assert r.artifacts[0].tipo == "mapa_ubicacion"


# --- validación de formularios ----------------------------------------------------------------


def test_cotizacion_ok_normaliza_tipos():
    limpios = validar_envio_formulario(COTIZACION, VALORES_OK)
    assert limpios["peso_kg"] == Decimal("45.5")
    assert limpios["valor_declarado_cop"] == Decimal("12500000")
    assert limpios["destino"] == "Medellín"


def test_cotizacion_acepta_numeros_como_string():
    limpios = validar_envio_formulario(COTIZACION, VALORES_OK | {"peso_kg": " 45.5 "})
    assert limpios["peso_kg"] == Decimal("45.5")


def _errores(form, valores):
    with pytest.raises(ErrorFormulario) as exc:
        validar_envio_formulario(form, valores)
    return exc.value.errores


def test_cotizacion_errores_por_campo():
    malos = VALORES_OK | {
        "peso_kg": 0,  # bajo el mínimo 0.1
        "alto_cm": "abc",
        "ancho_cm": True,  # bool no es número
        "destino": "Marte",
        "valor_declarado_cop": "100.555",  # 3 decimales
        "inventado": 1,
    }
    del malos["largo_cm"]
    errores = _errores(COTIZACION, malos)
    assert set(errores) == {
        "peso_kg",
        "alto_cm",
        "ancho_cm",
        "destino",
        "valor_declarado_cop",
        "inventado",
        "largo_cm",
    }
    assert errores["largo_cm"] == "Campo obligatorio"
    assert errores["inventado"] == "Campo desconocido"
    with pytest.raises(ErrorFormulario) as exc:
        validar_envio_formulario(COTIZACION, malos)
    lista = {e["campo"]: e["tipo"] for e in exc.value.como_problema()}
    assert lista["largo_cm"] == "obligatorio" and lista["inventado"] == "desconocido"
    assert lista["peso_kg"] == "invalido"


@pytest.mark.parametrize("malo", [float("nan"), float("inf"), "1e999999999999", None, ""])
def test_numeros_no_finitos_o_vacios(malo):
    assert "peso_kg" in _errores(COTIZACION, VALORES_OK | {"peso_kg": malo})


def test_guia_patron():
    assert validar_envio_formulario(GUIA, {"guia": "TLX-984021-CO"}) == {"guia": "TLX-984021-CO"}
    assert _errores(GUIA, {"guia": "TLX-98A021-CO"}) == {"guia": "Formato inválido"}


def test_pqrs_fecha_booleano_longitud_y_opcionales():
    base = {
        "tipo": "R",
        "guia": "TLX-551904-CO",
        "novedad": "averia_oculta",
        "descripcion": "La caja llegó aplastada y el producto está roto.",
        "valor_reclamado_cop": 420000,
    }
    limpios = validar_envio_formulario(PQRS, base | {"fecha_entrega": "2026-11-02", "anotada_en_guia": False})
    assert limpios["fecha_entrega"] == date(2026, 11, 2)
    assert limpios["anotada_en_guia"] is False
    assert validar_envio_formulario(PQRS, base)["fecha_entrega"] is None
    errores = _errores(PQRS, base | {"fecha_entrega": "02/11/2026", "anotada_en_guia": "si", "descripcion": "corta"})
    assert set(errores) == {"fecha_entrega", "anotada_en_guia", "descripcion"}
