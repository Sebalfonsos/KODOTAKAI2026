import pytest

from app.domain import ErrorDominio
from app.domain.escalamiento import ContextoTurno, detectar_palabras_clave, evaluar_escalamiento


def _ids(reglas, **kw):
    return [d.id_criterio for d in evaluar_escalamiento(reglas, ContextoTurno(**kw))]


def _criterio(reglas, cid):
    return next(c for c in reglas["criterios_escalacion"] if c["id_criterio"] == cid)


def test_t_esc_1_estafa_y_demandar(reglas):
    [d] = evaluar_escalamiento(reglas, ContextoTurno(texto_usuario="Esto es una ESTAFA, voy a demandar"))
    assert d.id_criterio == "CRIT-002" and d.accion == "ESCALAR_PRIORIDAD_ALTA"
    assert d.mensaje_cliente == _criterio(reglas, "CRIT-002")["mensaje_cliente"]
    assert d.palabras_detectadas == ["demandar", "estafa"]


@pytest.mark.parametrize(
    "texto", ["Necesito un servicio básico de envío", "Es una prueba física", "Un modelo clásico", "Basico"]
)
def test_t_esc_2_sic_no_dispara_dentro_de_palabras(reglas, texto):
    assert _ids(reglas, texto_usuario=texto) == []


@pytest.mark.parametrize(
    "texto",
    ["Voy a ir a la SIC", "Los denuncio ante la Supertransporte", "quiero HABLAR con  humano", "perdi mi dinero"],
)
def test_palabras_clave_completas_sin_tildes(reglas, texto):
    assert _ids(reglas, texto_usuario=texto) == ["CRIT-002"]


def test_t_esc_3_confianza_baja(reglas):
    assert _ids(reglas, confidence_score=0.4) == ["CRIT-001"]
    assert _ids(reglas, confidence_score=0.75) == []
    assert _ids(reglas) == []  # sin puntaje no dispara


def test_t_pqrs_3_y_d12_crit_003_solo_en_pqrs(reglas):
    assert _ids(reglas, flujo="pqrs", valor_reclamacion=6_000_000) == ["CRIT-003"]
    assert _ids(reglas, flujo="pqrs", valor_declarado=5_000_001) == ["CRIT-003"]
    assert _ids(reglas, flujo="pqrs", valor_reclamacion=5_000_000) == []
    assert _ids(reglas, flujo="rastreo", valor_declarado=12_500_000) == []  # T-TRK-1 con D-12


def test_crit_004_cuenta_corporativa(reglas):
    assert _ids(reglas, tipo_cuenta="CORPORATIVO_GOLD") == ["CRIT-004"]
    assert _ids(reglas, envios_mensuales_cuenta=501) == ["CRIT-004"]
    assert _ids(reglas, envios_mensuales_cuenta=500) == []


def test_t_trk_3_crit_005_con_guia_del_dataset(reglas, guias):
    g = guias["TLX-310482-CO"]
    c = g["especificaciones_carga"]
    ids = _ids(
        reglas,
        flujo="rastreo",
        mercancia_peligrosa=c["mercancia_peligrosa"],
        requiere_refrigeracion=c["requiere_refrigeracion"],
        estado_envio=g["estado_actual"],
        valor_declarado=c["declarado_cop"],
    )
    assert ids == ["CRIT-005"]


def test_crit_005_frio_solo_con_novedad(reglas):
    assert _ids(reglas, requiere_refrigeracion=True, estado_envio="RETENIDO_NOVEDAD") == ["CRIT-005"]
    assert _ids(reglas, requiere_refrigeracion=True, estado_envio="EN_TRANSITO") == []  # T-TRK-1


def test_d13_prioridad_005_002_003_004_001(reglas):
    todos = _ids(
        reglas,
        confidence_score=0.1,
        texto_usuario="gerente",
        flujo="pqrs",
        valor_reclamacion=9_000_000,
        tipo_cuenta="CORPORATIVO_GOLD",
        mercancia_peligrosa=True,
    )
    assert todos == ["CRIT-005", "CRIT-002", "CRIT-003", "CRIT-004", "CRIT-001"]


def test_umbral_desde_regla_si_falta_parametro_general(reglas):
    sin_param = {"criterios_escalacion": reglas["criterios_escalacion"]}
    assert _ids(sin_param, confidence_score=0.7) == ["CRIT-001"]


def test_regla_sin_umbral_es_invalida(reglas):
    rota = {"criterios_escalacion": [{**_criterio(reglas, "CRIT-003"), "regla_evaluacion": "valor alto"}]}
    with pytest.raises(ErrorDominio) as e:
        evaluar_escalamiento(rota, ContextoTurno(flujo="pqrs", valor_reclamacion=1))
    assert e.value.codigo == "REGLA_INVALIDA"
    rota = {"criterios_escalacion": [{**_criterio(reglas, "CRIT-005"), "regla_evaluacion": "x == true"}]}
    with pytest.raises(ErrorDominio):
        evaluar_escalamiento(rota, ContextoTurno(requiere_refrigeracion=True))


def test_detectar_palabras_clave_directo():
    assert detectar_palabras_clave("¡Pésimo servicio!", ["pésimo servicio", "sic"]) == ["pésimo servicio"]
