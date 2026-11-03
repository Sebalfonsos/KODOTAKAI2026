from decimal import Decimal

import pytest

from app.domain import ErrorDominio, redondear_pesos
from app.domain.cotizador import SolicitudCotizacion, buscar_municipio, buscar_trayecto, cotizar


def _cotizar(trayectos, municipios, origen, destino, **kw):
    return cotizar(
        buscar_trayecto(trayectos, origen, destino), buscar_municipio(municipios, destino), SolicitudCotizacion(**kw)
    )


def _de_guia(g, **extra):
    c = g["especificaciones_carga"]
    d = c["dimensiones_cm"]
    return dict(
        alto_cm=d["alto"],
        ancho_cm=d["ancho"],
        largo_cm=d["largo"],
        peso_kg=c["peso_kg"],
        valor_declarado=c["declarado_cop"],
        unidades=c["unidades"],
        **extra,
    )


def test_t_cot_1_bog_med_cadena_frio(trayectos, municipios, guias):
    g = guias["TLX-984021-CO"]
    sin_frio = _cotizar(trayectos, municipios, "Bogotá", "Medellín", **_de_guia(g))
    assert sin_frio.codigo_trayecto == "TLX-BOG-MED-001"
    assert sin_frio.peso_volumetrico == 30
    assert sin_frio.peso_facturable == Decimal("45.5") and sin_frio.base_cobro == "real"
    assert sin_frio.flete_base == 65975 and sin_frio.seguro == 125000
    assert sin_frio.total == 190975

    con_frio = _cotizar(trayectos, municipios, "Bogotá D.C.", "Medellín", **_de_guia(g, cadena_frio=True))
    assert con_frio.recargo_frio == Decimal("16493.75")
    assert con_frio.total_sin_redondeo == Decimal("207468.75")
    assert con_frio.total == 207469  # ROUND_HALF_UP solo en el total mostrado
    assert con_frio.horas_estimadas == 24
    assert any("Same Day" in o for o in con_frio.observaciones[:1])


def test_t_cot_2_bog_pei_volumetrico_con_minimo(trayectos, municipios, guias):
    c = _cotizar(trayectos, municipios, "Bogotá", "Pereira", **_de_guia(guias["TLX-551904-CO"]))
    assert c.peso_volumetrico == 6 and c.base_cobro == "volumetrico"
    assert c.tarifa_aplicada == 1580 and c.flete_base == 9480
    assert c.flete_minimo_aplicado and c.flete == 18000
    assert c.seguro == 4500
    assert c.flete_base + c.seguro == 13980  # total "sin mínimo" del golden
    assert c.total == 22500


def test_t_cot_3_seguro_minimo_del_csv(trayectos, municipios):
    c = _cotizar(
        trayectos,
        municipios,
        "Bogotá",
        "Barranquilla",
        alto_cm=30,
        ancho_cm=30,
        largo_cm=30,
        peso_kg=2,
        valor_declarado=200000,
    )
    assert c.peso_volumetrico == Decimal("6.75")
    assert c.seguro == 4000  # D-01: CSV, no los $2.500 del dosier


def test_t_cot_4_med_clo_carga_masiva(trayectos, municipios, guias):
    g = guias["TLX-752190-CO"]
    c = _cotizar(trayectos, municipios, "Medellín", "Cali", **_de_guia(g, modalidad="carga"))
    assert c.peso_volumetrico == g["especificaciones_carga"]["peso_volumetrico_kg"] == 3960
    assert c.seguro == 850000
    assert c.tarifa_aplicada == 1700 and c.flete_base == 6732000
    assert c.total == 6732000 + 850000


@pytest.mark.parametrize(("origen", "destino"), [("Barranquilla", "Bucaramanga"), ("Villavicencio", "Florencia")])
def test_t_cot_5_trayecto_inexistente(trayectos, origen, destino):
    with pytest.raises(ErrorDominio) as e:
        buscar_trayecto(trayectos, origen, destino)
    assert e.value.codigo == "TRAYECTO_INEXISTENTE" and "asesor" in e.value.mensaje


def test_t_cot_6_paqueteria_60_kg(trayectos, municipios):
    kw = dict(alto_cm=40, ancho_cm=40, largo_cm=40, peso_kg=60, valor_declarado=500000)
    with pytest.raises(ErrorDominio) as e:
        _cotizar(trayectos, municipios, "Bogotá", "Cali", **kw)
    assert e.value.codigo == "PAQUETERIA_EXCEDE_50_KG" and "carga" in e.value.mensaje
    assert _cotizar(trayectos, municipios, "Bogotá", "Cali", modalidad="carga", **kw).peso_facturable == 60


def test_peso_volumetrico_coincide_con_dataset(trayectos, guias):
    factor = trayectos[0].factor_divisitivas_volumetrico
    for g in guias.values():
        c = g["especificaciones_carga"]
        d = c["dimensiones_cm"]
        assert Decimal(d["alto"] * d["ancho"] * d["largo"]) / factor == Decimal(str(c["peso_volumetrico_kg"]))


def test_recargo_mercancia_peligrosa_suma_fija(trayectos, municipios):
    base = dict(alto_cm=10, ancho_cm=10, largo_cm=10, peso_kg=20, valor_declarado=100000)
    sin = _cotizar(trayectos, municipios, "Bogotá", "Cali", **base)
    con = _cotizar(trayectos, municipios, "Bogotá", "Cali", mercancia_peligrosa=True, **base)
    t = buscar_trayecto(trayectos, "Bogotá", "Cali")
    assert con.recargo_mp == t.recargo_mercancia_peligrosa_cop
    assert con.total - sin.total == t.recargo_mercancia_peligrosa_cop


def test_d06_frio_a_destino_sin_refrigerado(trayectos, municipios):
    with pytest.raises(ErrorDominio) as e:
        _cotizar(
            trayectos, municipios, "Bogotá", "Quibdó", alto_cm=10, ancho_cm=10, largo_cm=10, peso_kg=5,
            valor_declarado=100000, cadena_frio=True,
        )  # fmt: skip
    assert e.value.codigo == "REFRIGERADO_NO_DISPONIBLE"


def test_d05_same_day_lo_decide_el_directorio(trayectos, municipios):
    c = _cotizar(
        trayectos, municipios, "Barranquilla", "Santa Marta", alto_cm=10, ancho_cm=10, largo_cm=10, peso_kg=1,
        valor_declarado=10000,
    )  # fmt: skip
    assert any("Same Day no está disponible en Santa Marta" in o for o in c.observaciones)


def test_peso_por_unidad_supera_maximo_destino(trayectos, municipios):
    with pytest.raises(ErrorDominio) as e:
        _cotizar(
            trayectos, municipios, "Bogotá", "Quibdó", alto_cm=100, ancho_cm=100, largo_cm=100, peso_kg=600,
            valor_declarado=1000000, modalidad="carga",
        )  # fmt: skip
    assert e.value.codigo == "PESO_EXCEDE_MAXIMO_DESTINO"


@pytest.mark.parametrize(
    ("campo", "valor", "codigo"),
    [
        ("alto_cm", 0, "DATOS_INVALIDOS"),
        ("peso_kg", -1, "DATOS_INVALIDOS"),
        ("valor_declarado", 0, "DATOS_INVALIDOS"),
        ("unidades", 0, "DATOS_INVALIDOS"),
        ("modalidad", "ftl", "MODALIDAD_INVALIDA"),
    ],
)
def test_validaciones_de_entrada(trayectos, municipios, campo, valor, codigo):
    kw = dict(alto_cm=10, ancho_cm=10, largo_cm=10, peso_kg=1, valor_declarado=10000) | {campo: valor}
    with pytest.raises(ErrorDominio) as e:
        _cotizar(trayectos, municipios, "Bogotá", "Cali", **kw)
    assert e.value.codigo == codigo


def test_sin_cobertura():
    with pytest.raises(ErrorDominio) as e:
        buscar_municipio([], "Leticia")
    assert e.value.codigo == "SIN_COBERTURA"


def test_redondeo_half_up():
    assert redondear_pesos(Decimal("10.5")) == 11 and redondear_pesos(Decimal("10.49")) == 10
