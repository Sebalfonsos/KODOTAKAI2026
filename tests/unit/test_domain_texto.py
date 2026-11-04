"""Pruebas de estados.py, pii.py y sanitizar.py."""

import logging

import pytest

from app.domain.estados import traducir_estado
from app.domain.pii import enmascarar_digitos, enmascarar_nombre, enmascarar_texto
from app.domain.sanitizar import DatosEnvio, extraer_envio, extraer_guias, limpiar_texto, normalizar_para_busqueda


def test_todos_los_estados_del_dataset_son_conocidos(guias):
    estados = {h["estado"] for g in guias.values() for h in g["historial_trazabilidad"]}
    estados |= {g["estado_actual"] for g in guias.values()}
    assert all(traducir_estado(e).conocido for e in estados)


def test_relectura_hub_fontibon_ejemplo_dosier():
    e = traducir_estado("RELECTURA_HUB_FONTIBON")
    assert "centro principal de clasificación en Bogotá" in e.texto and "ruta nocturna" in e.texto


def test_progreso_y_final():
    assert traducir_estado("ENTREGADO").es_final and traducir_estado("ENTREGADO").progreso_pct == 100
    assert traducir_estado("EN_TRANSITO").progreso_pct == 57
    novedad = traducir_estado("RETENIDO_NOVEDAD")
    assert novedad.orden is None and novedad.progreso_pct is None and not novedad.es_final
    assert traducir_estado("EN_INVESTIGACION_SINIESTRO").conocido


def test_estado_desconocido_generico_y_aviso(caplog):
    with caplog.at_level(logging.WARNING):
        e = traducir_estado("ESTADO_RARO")
    assert not e.conocido and "ESTADO_RARO" not in e.texto
    assert "estado_tms_desconocido" in caplog.text


def test_enmascarar_cedula_del_dataset(guias):
    doc = guias["TLX-752190-CO"]["prueba_entrega"]["documento_identidad"]
    assert enmascarar_digitos(doc) == "C.C. **.**9.432"


def test_enmascarar_texto_telefono_del_dataset(guias):
    desc = guias["TLX-551904-CO"]["historial_trazabilidad"][-1]["descripcion"]
    salida = enmascarar_texto(desc)
    assert "310-987-6543" not in salida and "***-***-6543" in salida


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("NIT 900.123.456-7", "NIT ***.***.456-7"),
        ("cédula 1234567890", "cédula ******7890"),
        ("Recibió C.C. 16.789.432 ok", "Recibió C.C. **.**9.432 ok"),
        ("llamar al +57 601 288 6012", "llamar al +** *** *** 6012"),
        ("celular 3109876543", "celular ******6543"),
    ],
)
def test_enmascarar_texto_patrones(texto, esperado):
    assert enmascarar_texto(texto) == esperado


@pytest.mark.parametrize("texto", ["Valor $12.500.000", "fecha 2026-11-02", "guía TLX-984021-CO", "Peso 3,200 kg"])
def test_enmascarar_texto_no_toca_montos_fechas_ni_guias(texto):
    assert enmascarar_texto(texto) == texto


def test_limpiar_texto():
    assert limpiar_texto("  hola\x00\x07 mundo\n\tok\x1b  ") == "hola mundo\n\tok"
    assert limpiar_texto("Café") == "Café"
    assert limpiar_texto("a" * 10, max_len=3) == "aaa"


def test_normalizar_para_busqueda():
    assert normalizar_para_busqueda("  Ácido-Clorhídrico, PÉSIMO servicio!! ") == "acido clorhidrico pesimo servicio"


def test_extraer_guias_tolerante(guias):
    for numero in guias:
        assert extraer_guias(f"mi guía es {numero.lower()}") == [numero]
    texto = "tengo TLX 984021 CO, tlx-551904co y otra vez TLX-984021-CO; no TLX-9840211-CO ni TLX-12345-CO"
    assert extraer_guias(texto) == ["TLX-984021-CO", "TLX-551904-CO"]
    assert extraer_guias("TLX-984 021-CO") == ["TLX-984021-CO"]
    assert extraer_guias("sin guía") == []


def test_enmascarar_nombre_solo_iniciales():
    assert enmascarar_nombre("Ing. Roberto Bermúdez") == "I. R. B."
    assert enmascarar_nombre("  Camila   Restrepo ") == "C. R."


ORIGENES = ["Bogotá D.C.", "Medellín", "Cali"]
DESTINOS = ["Medellín", "Cali", "Bogotá D.C.", "Santa Marta"]


@pytest.mark.parametrize(
    ("texto", "producto", "origen", "destino"),
    [
        ("Quiero enviar clavos", "clavos", None, None),
        ("quiero enviar unos clavos de bogota a medellin", "clavos", "Bogotá D.C.", "Medellín"),
        (
            "Necesito mandar 5 litros de ácido clorhídrico de Cali a Santa Marta.",
            "5 litros de ácido clorhídrico",
            "Cali",
            "Santa Marta",
        ),
        ("Deseo enviar clavos de acero a Medellín desde Cali", "clavos de acero", "Cali", "Medellín"),
        ("quiero enviar un paquete a Cali", None, None, "Cali"),
        ("quiero enviar algo", None, None, None),
    ],
)
def test_extraer_envio(texto, producto, origen, destino):
    assert extraer_envio(texto, ORIGENES, DESTINOS) == DatosEnvio(producto, origen, destino)
