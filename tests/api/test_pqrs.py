"""PQRS: propiedad, plazos en días hábiles, checklist, carga de soportes y escalamiento (golden T-PQRS)."""

import uuid
from datetime import date

import pytest

from app.servicios import pqrs as svc
from tests.api.conftest import problema

R = "/api/v1/pqrs"
HOY = date(2026, 11, 3)  # martes; el 2 de noviembre de 2026 es festivo (Todos los Santos)


@pytest.fixture(autouse=True)
def _hoy_fijo(monkeypatch):
    monkeypatch.setattr(svc, "hoy", lambda: HOY)


def _perdida(**extra) -> dict:
    return {
        "tipo": "S",
        "numero_guia": "TLX-551904-CO",
        "descripcion": "El paquete no ha llegado y el rastreo no se actualiza.",
        "tipo_averia": "perdida",
        "valor_reclamado": 450000,
    } | extra


def _pdf(etiqueta: str = "") -> bytes:
    return b"%PDF-1.4\n% soporte " + (etiqueta or uuid.uuid4().hex).encode() + b"\n%%EOF\n"


async def _crear(cliente, h, cuerpo=None, **kw) -> dict:
    r = await cliente.post(f"{R}/crear-ticket", json=cuerpo or _perdida(), headers=h, **kw)
    assert r.status_code == 201, r.text
    return r.json()


async def _subir(cliente, h, radicado, tipo, contenido, nombre="soporte.pdf", mime="application/pdf"):
    return await cliente.post(
        f"{R}/{radicado}/documentos",
        headers=h,
        data={"tipo_documento": tipo},
        files={"archivo": (nombre, contenido, mime)},
    )


# --- autenticación, rol y propiedad -----------------------------------------------------------


async def test_crear_sin_login_401(cliente):
    problema(await cliente.post(f"{R}/crear-ticket", json=_perdida()), 401, "NO_AUTENTICADO")


async def test_asesor_y_admin_no_crean_tickets_403(cliente, h_asesor, h_admin):
    for h in (h_asesor, h_admin):
        problema(await cliente.post(f"{R}/crear-ticket", json=_perdida(), headers=h), 403, "SIN_PERMISO")


async def test_guia_ajena_404(cliente, h_vip):
    problema(await cliente.post(f"{R}/crear-ticket", json=_perdida(), headers=h_vip), 404, "GUIA_NO_ENCONTRADA")


async def test_radicado_ajeno_404(cliente, h_cliente, h_vip, h_admin):
    t = await _crear(cliente, h_cliente)
    url = f"{R}/{t['radicado']}"
    assert (await cliente.get(url, headers=h_cliente)).json()["id"] == t["id"]
    assert (await cliente.get(url, headers=h_admin)).status_code == 200
    problema(await cliente.get(url, headers=h_vip), 404, "RADICADO_NO_ENCONTRADO")
    problema(await _subir(cliente, h_vip, t["radicado"], "factura", _pdf()), 404, "RADICADO_NO_ENCONTRADO")
    problema(await cliente.get(f"{R}/PQRS-2026-999999", headers=h_cliente), 404, "RADICADO_NO_ENCONTRADO")
    problema(await cliente.get(f"{R}/no-es-radicado", headers=h_cliente), 422, "VALIDACION")


# --- reglas de negocio ------------------------------------------------------------------------


async def test_siniestro_sin_tipo_averia_422(cliente, h_cliente):
    r = await cliente.post(f"{R}/crear-ticket", json=_perdida(tipo_averia=None), headers=h_cliente)
    problema(r, 422, "DATOS_SINIESTRO_INCOMPLETOS")


async def test_averia_en_guia_no_entregada_422(cliente, h_cliente):
    r = await cliente.post(f"{R}/crear-ticket", json=_perdida(tipo_averia="oculta"), headers=h_cliente)
    problema(r, 422, "ENVIO_NO_ENTREGADO")


async def test_plazo_vencido_422(cliente, h_cliente, monkeypatch):
    monkeypatch.setattr(svc, "hoy", lambda: date(2027, 2, 1))  # mucho después de 5 + 10 días hábiles
    p = problema(await cliente.post(f"{R}/crear-ticket", json=_perdida(), headers=h_cliente), 422, "PLAZO_VENCIDO")
    assert p["detail"]


async def test_creacion_incompleta_con_checklist(cliente, h_cliente):
    t = await _crear(cliente, h_cliente)
    assert t["estado"] == "incompleto" and t["radicado"].startswith("PQRS-2026-")
    assert t["checklist"] == {
        "factura": False,
        "carta_reclamacion": False,
        "certificacion_bancaria": False,
        "documento_identidad": False,
        "guia": True,
    }
    assert t["fecha_limite_respuesta"] == "2026-11-25"  # 15 días hábiles con el festivo del 16-nov
    assert t["escalado"] is False


async def test_reclamo_sin_checklist_queda_radicado(cliente, h_cliente):
    cuerpo = {"tipo": "R", "numero_guia": "TLX-551904-CO", "descripcion": "El repartidor fue grosero conmigo."}
    t = await _crear(cliente, h_cliente, cuerpo)
    assert t["estado"] == "radicado" and t["checklist"] == {}


async def test_valor_reclamado_mayor_5m_escala(cliente, h_cliente):
    t = await _crear(cliente, h_cliente, _perdida(tipo="R", tipo_averia=None, valor_reclamado=6000000))
    assert t["escalado"] is True and t["prioridad"] == 1  # CRIT-003 (T-PQRS-3)


async def test_idempotency_key_pqrs(cliente, h_cliente):
    clave = {"Idempotency-Key": f"pqrs-{uuid.uuid4()}"}
    a = await _crear(cliente, h_cliente | clave)
    b = await _crear(cliente, h_cliente | clave)
    assert a["radicado"] == b["radicado"]
    r = await cliente.post(f"{R}/crear-ticket", json=_perdida(valor_reclamado=1), headers=h_cliente | clave)
    problema(r, 409, "IDEMPOTENCY_KEY_REUTILIZADA")


# --- soportes ---------------------------------------------------------------------------------


async def test_carga_completa_el_checklist_y_radica(cliente, h_cliente):
    t = await _crear(cliente, h_cliente)
    jpg = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00" + uuid.uuid4().bytes
    r = await _subir(cliente, h_cliente, t["radicado"], "factura", jpg, "factura.jpg", "image/jpeg")
    assert r.status_code == 201, r.text
    doc = r.json()["documentos"][0]
    assert doc["mime"] == "image/jpeg" and len(doc["sha256"]) == 64 and r.json()["estado"] == "incompleto"
    for tipo in ("carta_reclamacion", "certificacion_bancaria", "documento_identidad"):
        r = await _subir(cliente, h_cliente, t["radicado"], tipo, _pdf())
        assert r.status_code == 201, r.text
    final = r.json()
    assert final["estado"] == "radicado" and all(final["checklist"].values()) and len(final["documentos"]) == 4


async def test_documento_duplicado_409(cliente, h_cliente):
    t = await _crear(cliente, h_cliente)
    contenido = _pdf("mismo")
    assert (await _subir(cliente, h_cliente, t["radicado"], "factura", contenido)).status_code == 201
    r = await _subir(cliente, h_cliente, t["radicado"], "carta_reclamacion", contenido)
    problema(r, 409, "DOCUMENTO_DUPLICADO")


@pytest.mark.parametrize(
    ("nombre", "contenido", "mime"),
    [
        ("virus.exe", b"MZ\x90\x00\x03\x00\x00\x00", "application/octet-stream"),
        ("falso.pdf", b"esto es texto plano renombrado", "application/pdf"),  # extensión y mime mienten
        ("script.pdf", b"<script>alert(1)</script>", "application/pdf"),
    ],
)
async def test_tipo_no_permitido_415(cliente, h_cliente, nombre, contenido, mime):
    t = await _crear(cliente, h_cliente)
    r = await _subir(cliente, h_cliente, t["radicado"], "factura", contenido, nombre, mime)
    problema(r, 415, "TIPO_ARCHIVO_NO_PERMITIDO")


async def test_archivo_mayor_10mb_413(cliente, h_cliente):
    t = await _crear(cliente, h_cliente)
    grande = b"%PDF-1.4\n" + b"0" * (10 * 1024 * 1024)
    problema(await _subir(cliente, h_cliente, t["radicado"], "factura", grande), 413, "ARCHIVO_GRANDE")


async def test_archivo_vacio_y_tipo_documento_invalido_422(cliente, h_cliente):
    t = await _crear(cliente, h_cliente)
    problema(await _subir(cliente, h_cliente, t["radicado"], "factura", b""), 422, "ARCHIVO_VACIO")
    problema(await _subir(cliente, h_cliente, t["radicado"], "pasaporte", _pdf()), 422, "VALIDACION")


# --- plazo y liquidación ----------------------------------------------------------------------


async def test_plazo_averia_oculta_vigente(cliente, h_admin):
    r = await cliente.get(f"{R}/plazo", params={"guia": "TLX-752190-CO", "tipo_averia": "oculta"}, headers=h_admin)
    p = r.json()
    assert r.status_code == 200, r.text
    # Entregada el 2026-11-02 (festivo): 3 días hábiles → 5 de noviembre.
    assert p["vigente"] is True and p["fecha_referencia"] == "2026-11-02" and p["fecha_limite"] == "2026-11-05"
    assert p["dias_habiles_restantes"] == 2


async def test_plazo_vencido_responde_200_con_vigente_false(cliente, h_admin, monkeypatch):
    monkeypatch.setattr(svc, "hoy", lambda: date(2026, 11, 10))
    r = await cliente.get(f"{R}/plazo", params={"guia": "TLX-752190-CO", "tipo_averia": "oculta"}, headers=h_admin)
    assert r.json()["vigente"] is False


async def test_plazo_errores(cliente, h_cliente):
    q = {"guia": "TLX-752190-CO", "tipo_averia": "oculta"}
    problema(await cliente.get(f"{R}/plazo", params=q), 401, "NO_AUTENTICADO")
    problema(await cliente.get(f"{R}/plazo", params=q, headers=h_cliente), 404, "GUIA_NO_ENCONTRADA")
    problema(await cliente.get(f"{R}/plazo", params=q | {"tipo_averia": "x"}, headers=h_cliente), 422, "VALIDACION")


async def test_liquidacion_t_pqrs_4(cliente):
    r = await cliente.post(f"{R}/liquidacion-estimada", json={"valor_declarado": 3000000, "valor_factura": 2800000})
    d = r.json()
    assert float(d["base"]) == 2800000 and float(d["deducible"]) == 140000
    assert float(d["total"]) == 2660000 and d["aplica_deducible"] is True and d["sujeto_aprobacion"] is True
    problema(await cliente.post(f"{R}/liquidacion-estimada", json={"valor_declarado": 0, "valor_factura": 1}), 422)
