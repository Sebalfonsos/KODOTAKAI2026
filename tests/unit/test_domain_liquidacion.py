import pytest

from app.domain import ErrorDominio
from app.domain.liquidacion import liquidar_indemnizacion


def test_t_pqrs_4_minimo_menos_deducible():
    r = liquidar_indemnizacion(3_000_000, 2_800_000)
    assert r.base == 2_800_000 and r.deducible == 140_000 and r.total == 2_660_000
    assert r.aplica_deducible and r.sujeto_aprobacion


def test_sin_deducible_hasta_2_millones():
    r = liquidar_indemnizacion(2_000_000, 2_500_000)
    assert not r.aplica_deducible and r.total == 2_000_000


@pytest.mark.parametrize(
    ("tipo", "negligencia", "flete"),
    [
        ("perdida_total", True, 50_000),
        ("averia_total", True, 50_000),
        ("perdida_total", False, 0),
        ("averia_parcial", True, 0),
    ],
)
def test_flete_devuelto_solo_con_perdida_o_averia_total_y_negligencia(tipo, negligencia, flete):
    r = liquidar_indemnizacion(
        1_000_000, 1_000_000, flete_cobrado=50_000, tipo_siniestro=tipo, negligencia_demostrada=negligencia
    )
    assert r.flete_devuelto == flete and r.total == 1_000_000 + flete


def test_valores_invalidos():
    with pytest.raises(ErrorDominio) as e:
        liquidar_indemnizacion(0, 100)
    assert e.value.codigo == "VALOR_INVALIDO"
