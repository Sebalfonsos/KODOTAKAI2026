from datetime import date, datetime

import pytest

from app.domain import ErrorDominio
from app.domain.plazos import (
    dias_habiles_entre,
    es_dia_habil,
    evaluar_plazo_reclamo,
    fecha_limite_respuesta,
    sumar_dias_habiles,
)


def test_festivos_y_fines_de_semana():
    assert not es_dia_habil(date(2026, 11, 2))  # Todos los Santos (trasladado)
    assert not es_dia_habil(date(2026, 11, 7))  # sábado
    assert not es_dia_habil(date(2026, 11, 16))  # Independencia de Cartagena
    assert es_dia_habil(date(2026, 11, 3))


def test_sumar_y_contar_dias_habiles():
    # Viernes 30/10/2026 + 1 hábil salta sábado, domingo y el festivo del lunes 2/11.
    assert sumar_dias_habiles(date(2026, 10, 30), 1) == date(2026, 11, 3)
    assert sumar_dias_habiles(date(2026, 10, 30), 0) == date(2026, 10, 30)
    assert dias_habiles_entre(date(2026, 10, 30), date(2026, 11, 3)) == 1
    assert dias_habiles_entre(date(2026, 11, 3), date(2026, 10, 30)) == -1
    assert sumar_dias_habiles(datetime(2026, 11, 2, 11, 45), 3) == date(2026, 11, 5)


def test_t_pqrs_1_averia_oculta_dentro_de_3_dias():
    # TLX-752190-CO entregada el 2/11/2026 (festivo): límite = 3 hábiles después.
    r = evaluar_plazo_reclamo("oculta", date(2026, 11, 2), date(2026, 11, 4))
    assert r.vigente and r.fecha_limite == date(2026, 11, 5)
    assert r.dias_habiles_restantes == 1


def test_t_pqrs_2_un_mes_despues_art_1028():
    r = evaluar_plazo_reclamo("oculta", date(2026, 10, 2), date(2026, 11, 2))
    assert not r.vigente and r.dias_habiles_restantes == 0
    assert "Art. 1028" in r.fundamento


def test_averia_aparente_depende_de_la_anotacion():
    assert evaluar_plazo_reclamo("aparente", date(2026, 11, 3), date(2026, 11, 3), anotada_en_guia=True).vigente
    r = evaluar_plazo_reclamo("aparente", date(2026, 11, 3), date(2026, 11, 4))
    assert not r.vigente and "Art. 1028" in r.fundamento


def test_d08_perdida_5_mas_10_habiles():
    estimada = date(2026, 11, 3)
    investigacion = sumar_dias_habiles(estimada, 5)
    limite = sumar_dias_habiles(estimada, 15)
    antes = evaluar_plazo_reclamo("perdida", estimada, date(2026, 11, 4))
    assert antes.vigente and antes.fecha_investigacion_siniestro == investigacion
    assert "Aún no" in antes.fundamento
    durante = evaluar_plazo_reclamo("perdida", estimada, investigacion)
    assert durante.vigente and durante.fecha_limite == limite and durante.dias_habiles_restantes == 10
    despues = evaluar_plazo_reclamo("perdida", estimada, sumar_dias_habiles(limite, 1))
    assert not despues.vigente


def test_tipo_invalido():
    with pytest.raises(ErrorDominio) as e:
        evaluar_plazo_reclamo("robo", date(2026, 11, 3), date(2026, 11, 3))
    assert e.value.codigo == "TIPO_AVERIA_INVALIDO"


def test_respuesta_pqrs_15_habiles_desde_el_dia_siguiente():
    # Radicado el martes 3/11/2026; el festivo del 16/11 no cuenta.
    assert fecha_limite_respuesta(date(2026, 11, 3)) == date(2026, 11, 25)
