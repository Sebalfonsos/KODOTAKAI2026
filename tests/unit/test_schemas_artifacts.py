import json
from decimal import Decimal

import pytest
from pydantic import TypeAdapter, ValidationError

from app.schemas.artifacts import (
    MODELOS_ARTIFACT,
    Accion,
    Artifact,
    CampoFormulario,
    ResultadoCotizacion,
    TablaDatos,
)

ADAPTER = TypeAdapter(Artifact)
EJEMPLOS = [
    pytest.param(m, ej, id=f"{m.__name__}-{i}")
    for m in MODELOS_ARTIFACT
    for i, ej in enumerate(m.model_config["json_schema_extra"]["examples"])
]


def test_catalogo_completo_y_tipos_unicos():
    tipos = [m.model_fields["tipo"].default for m in MODELOS_ARTIFACT]
    assert len(tipos) == len(set(tipos)) == 23
    esquema = ADAPTER.json_schema()
    assert set(esquema["discriminator"]["mapping"]) == set(tipos)


@pytest.mark.parametrize(("modelo", "ejemplo"), EJEMPLOS)
def test_ejemplo_valido_y_round_trip(modelo, ejemplo):
    art = ADAPTER.validate_python(ejemplo)
    assert type(art) is modelo
    texto = ADAPTER.dump_json(art)
    assert ADAPTER.validate_json(texto) == art


def test_discriminador_rechaza_tipo_desconocido_o_ausente():
    with pytest.raises(ValidationError):
        ADAPTER.validate_python({"id": "x", "tipo": "no_existe"})
    with pytest.raises(ValidationError):
        ADAPTER.validate_python({"id": "x"})


def test_extra_forbid():
    ej = dict(ResultadoCotizacion.model_config["json_schema_extra"]["examples"][0], inventado=1)
    with pytest.raises(ValidationError):
        ADAPTER.validate_python(ej)


def test_dinero_se_serializa_como_string_sin_perder_centavos():
    ej = dict(ResultadoCotizacion.model_config["json_schema_extra"]["examples"][0])
    ej |= {
        "recargos": [{"concepto": "Cadena de frío (25 %)", "valor": "16493.75"}],
        "total": "207468.75",
    }
    datos = json.loads(ADAPTER.dump_json(ADAPTER.validate_python(ej)))
    assert datos["total"] == "207468.75"
    assert datos["recargos"][0]["valor"] == "16493.75"
    assert Decimal(datos["flete_base"]) + Decimal(datos["seguro"]) + Decimal("16493.75") == Decimal(datos["total"])


def test_dinero_negativo_o_con_tres_decimales_falla():
    ej = ResultadoCotizacion.model_config["json_schema_extra"]["examples"][0]
    for malo in ("-1", "10.001"):
        with pytest.raises(ValidationError):
            ADAPTER.validate_python(dict(ej, total=malo))


def test_guia_mal_formada_falla():
    ej = {"id": "m", "tipo": "mapa_ubicacion", "guia": "TLX-98402-CO", "latitud": 5, "longitud": -75}
    with pytest.raises(ValidationError):
        ADAPTER.validate_python(ej)


def test_acciones_coherentes():
    with pytest.raises(ValidationError):
        Accion(id="a", etiqueta="A", tipo="mensaje")
    with pytest.raises(ValidationError):
        Accion(id="a", etiqueta="A", tipo="submit")
    assert Accion(id="a", etiqueta="A", tipo="enlace", endpoint="/x").estilo == "primario"


def test_campo_seleccion_sin_opciones_y_rango_invertido():
    with pytest.raises(ValidationError):
        CampoFormulario(nombre="x", etiqueta="X", tipo="seleccion")
    with pytest.raises(ValidationError):
        CampoFormulario(nombre="x", etiqueta="X", tipo="numero", min=5, max=1)


def test_tabla_rechaza_filas_con_claves_sin_columna():
    with pytest.raises(ValidationError):
        TablaDatos(id="t", columnas=[{"clave": "guia", "etiqueta": "Guía"}], filas=[{"otra": 1}])


def test_respuestas_rapidas_exige_al_menos_una_accion():
    with pytest.raises(ValidationError):
        ADAPTER.validate_python({"id": "r", "tipo": "respuestas_rapidas", "acciones": []})
