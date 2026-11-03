import pytest

from app.domain.mercancias import DOCUMENTOS_MP, evaluar_producto


def test_t_mp_1_acido_clorhidrico():
    r = evaluar_producto("¿Puedo enviar 5 litros de ácido clorhídrico de Bogotá a Cali?")
    assert r.veredicto == "restringido" and r.clase_onu == "8"
    assert "5 litros" in r.motivo and "doble pared" in r.motivo
    assert r.documentos_requeridos == DOCUMENTOS_MP
    assert any("NTC 4532" in d for d in r.documentos_requeridos)
    assert any("16 secciones" in d for d in r.documentos_requeridos)


@pytest.mark.parametrize("texto", ["¿Puedo enviar un perro o gato de Bogotá a Medellín?", "mi mascota", "dos PERROS"])
def test_t_mp_2_animales_vivos(texto):
    r = evaluar_producto(texto)
    assert r.veredicto == "prohibido" and r.producto == "animales vivos" and "§5.5" in r.fuente


@pytest.mark.parametrize(
    ("texto", "producto"),
    [
        ("Quiero enviar pólvora", "explosivos y pólvora"),
        ("unos fuegos artificiales", "explosivos y pólvora"),
        ("dinero en efectivo", "dinero en efectivo y títulos valores"),
        ("billetes de 50 mil", "dinero en efectivo y títulos valores"),
    ],
)
def test_t_mp_3_prohibidos(texto, producto):
    r = evaluar_producto(texto)
    assert r.veredicto == "prohibido" and r.producto == producto and r.documentos_requeridos == ()


@pytest.mark.parametrize(
    ("texto", "veredicto", "clase"),
    [
        ("ácido muriático", "restringido", "8"),
        ("un galón de gasolina", "restringido", "3"),
        ("Thinner y acetona", "restringido", "3"),
        ("cilindro de propano", "solo_ftl", "2.1"),
        ("baterías de litio sueltas", "restringido", "9"),
        ("un celular con batería de litio instalada", "permitido", "9"),
        ("sodio metálico", "prohibido", "4.3"),
        ("uranio", "prohibido", "7"),
        ("residuos hospitalarios", "prohibido", "6.2"),
        ("batería de plomo para el carro", "restringido", "8"),
    ],
)
def test_clases_onu(texto, veredicto, clase):
    r = evaluar_producto(texto)
    assert (r.veredicto, r.clase_onu) == (veredicto, clase)


def test_gana_el_mas_severo():
    assert evaluar_producto("un celular y un perro").veredicto == "prohibido"


def test_carga_general_con_categoria_de_embalaje():
    assert evaluar_producto("copas de vidrio").categoria_embalaje == "A"
    assert evaluar_producto("vacunas").categoria_embalaje == "C"


@pytest.mark.parametrize("texto", ["unos libros", "cloruro de sodio", "un armario", "llaves"])
def test_desconocido_no_inventa(texto):
    r = evaluar_producto(texto)
    assert r.veredicto == "desconocido" and r.clase_onu is None
