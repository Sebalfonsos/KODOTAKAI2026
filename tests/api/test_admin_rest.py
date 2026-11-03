"""Administración REST: RBAC, usuarios, métricas, conversaciones, envíos, PQRS, base de conocimiento y auditoría."""

import hashlib
import uuid
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
import pytest
from sqlalchemy import select

from app.ai import rag
from app.config import get_settings
from app.db import SessionLocal
from app.models import Auditoria, Calificacion, Escalamiento, Mensaje, SesionChat, TicketPqrs, Usuario
from app.models.base import EstadoPqrs, RolMensaje, TipoPqrs
from tests.api.conftest import CREDENCIALES, problema

R = "/api/v1/admin"
ZONA = ZoneInfo("America/Bogota")
CLAVE = "Clave-Admin-2026"

RUTAS = [
    ("GET", "/usuarios"),
    ("POST", "/usuarios"),
    ("PATCH", f"/usuarios/{uuid.uuid4()}"),
    ("GET", "/metricas"),
    ("GET", "/conversaciones"),
    ("GET", f"/conversaciones/{uuid.uuid4()}"),
    ("GET", "/envios"),
    ("GET", "/pqrs"),
    ("PATCH", "/pqrs/PQRS-2026-000001"),
    ("GET", "/rag/documentos"),
    ("POST", "/rag/documentos"),
    ("DELETE", "/rag/documentos/1"),
    ("GET", "/rag/buscar?q=hola"),
    ("GET", "/auditoria"),
]


async def _id(rol: str) -> uuid.UUID:
    async with SessionLocal() as s:
        return await s.scalar(select(Usuario.id).where(Usuario.email == CREDENCIALES[rol][0].lower()))


async def _auditado(accion: str, entidad_id: str) -> bool:
    async with SessionLocal() as s:
        return (
            await s.scalar(select(Auditoria.id).where(Auditoria.accion == accion, Auditoria.entidad_id == entidad_id))
            is not None
        )


@pytest.mark.parametrize(("metodo", "ruta"), RUTAS)
async def test_rbac_admin(cliente, h_cliente, h_asesor, metodo, ruta):
    problema(await cliente.request(metodo, R + ruta), 401, "NO_AUTENTICADO")
    for h in (h_cliente, h_asesor):
        problema(await cliente.request(metodo, R + ruta, headers=h), 403, "SIN_PERMISO")


# --- usuarios ---------------------------------------------------------------------------------


async def test_usuarios_crear_listar_editar_y_desactivar(cliente, h_admin):
    email = f"Nuevo.{uuid.uuid4().hex[:6]}@TransLogix.demo"
    cuerpo = {"email": email, "nombre": "  Nuevo   Asesor ", "password": CLAVE, "rol": "asesor"}
    r = await cliente.post(f"{R}/usuarios", json=cuerpo, headers=h_admin)
    assert r.status_code == 201, r.text
    u = r.json()
    assert u["email"] == email.lower() and u["nombre"] == "Nuevo Asesor" and u["activo"] and "password" not in r.text
    assert await _auditado("usuario.crear", u["id"])
    problema(await cliente.post(f"{R}/usuarios", json=cuerpo, headers=h_admin), 409, "EMAIL_DUPLICADO")
    for malo in ({"password": "corta1"}, {"password": "solo-letras-largas"}, {"rol": "root"}, {"email": "x@"}):
        problema(await cliente.post(f"{R}/usuarios", json=cuerpo | malo, headers=h_admin), 422, "VALIDACION")

    r = await cliente.get(f"{R}/usuarios", params={"rol": "asesor", "tamano": 100}, headers=h_admin)
    assert r.status_code == 200 and all(i["rol"] == "asesor" for i in r.json()["items"])
    assert u["id"] in {i["id"] for i in r.json()["items"]}

    # El usuario inicia sesión; al desactivarlo ya no puede ni hacer login ni renovar.
    login = await cliente.post("/api/v1/auth/login", json={"email": email, "password": CLAVE})
    assert login.status_code == 200
    r = await cliente.patch(f"{R}/usuarios/{u['id']}", json={"activo": False, "nombre": "Ex Asesor"}, headers=h_admin)
    assert r.status_code == 200 and r.json()["activo"] is False and r.json()["nombre"] == "Ex Asesor"
    assert await _auditado("usuario.editar", u["id"])
    r = await cliente.post("/api/v1/auth/login", json={"email": email, "password": CLAVE})
    problema(r, 401, "CREDENCIALES_INVALIDAS")
    r = await cliente.post("/api/v1/auth/refresh", json={"refresh_token": login.json()["refresh_token"]})
    problema(r, 401)

    problema(
        await cliente.patch(f"{R}/usuarios/{uuid.uuid4()}", json={"activo": True}, headers=h_admin),
        404,
        "USUARIO_NO_ENCONTRADO",
    )


async def test_admin_no_puede_desactivarse_ni_quitarse_el_rol(cliente, h_admin):
    yo = await _id("admin")
    for cambio in ({"activo": False}, {"rol": "asesor"}, {"rol": "cliente", "activo": True}):
        problema(await cliente.patch(f"{R}/usuarios/{yo}", json=cambio, headers=h_admin), 409, "AUTO_MODIFICACION")
    r = await cliente.patch(f"{R}/usuarios/{yo}", json={"nombre": "Administración TransLogix"}, headers=h_admin)
    assert r.status_code == 200 and r.json()["rol"] == "admin" and r.json()["activo"]


# --- métricas ---------------------------------------------------------------------------------

DIA = date(2025, 1, 15)  # día aislado: ninguna otra prueba escribe en esa fecha


def _en(hora: int) -> datetime:
    return datetime(DIA.year, DIA.month, DIA.day, hora, tzinfo=ZONA)


@pytest.fixture(scope="module")
async def datos_metricas():
    cliente_id = await _id("cliente")
    async with SessionLocal() as s:
        s1 = SesionChat(usuario_id=cliente_id, creado_en=_en(9))
        s2 = SesionChat(usuario_id=cliente_id, creado_en=_en(23))  # 23:00 en Bogotá = 04:00 UTC del día siguiente
        s.add_all([s1, s2])
        await s.flush()

        def msg(sesion, rol, hora, **kw):
            return Mensaje(
                sesion_id=sesion.id,
                turno_id=uuid.uuid4(),
                rol=rol,
                contenido=f"{rol} {hora}",
                creado_en=_en(hora),
                **kw,
            )

        s.add_all(
            [
                msg(s1, RolMensaje.USUARIO, 9, intencion="rastreo"),
                msg(
                    s1,
                    RolMensaje.ASISTENTE,
                    9,
                    intencion="rastreo",
                    confianza=0.8,
                    latencias_ms={"total": 100, "llm": 80},
                ),
                msg(s1, RolMensaje.USUARIO, 10, intencion="metricas_prueba"),
                msg(s2, RolMensaje.USUARIO, 23, intencion="rastreo"),
                msg(s2, RolMensaje.ASISTENTE, 23, intencion="cotizacion", confianza=0.6, latencias_ms={"total": 300}),
                msg(s2, RolMensaje.ASISTENTE, 23, confianza=None, latencias_ms=None),
                Escalamiento(
                    sesion_id=s2.id, criterio_id="CRIT-001", prioridad=5, creado_en=_en(23), estado="resuelto"
                ),
                Calificacion(sesion_id=s1.id, puntaje=4, creado_en=_en(11)),
                Calificacion(sesion_id=s2.id, puntaje=5, creado_en=_en(23)),
                TicketPqrs(
                    tipo=TipoPqrs.QUEJA,
                    estado=EstadoPqrs.RADICADO,
                    usuario_id=cliente_id,
                    descripcion="El conductor fue grosero conmigo.",
                    fecha_limite_respuesta=DIA + timedelta(days=21),
                    creado_en=_en(12),
                ),
            ]
        )
        await s.commit()
        return s1.id, s2.id


async def test_metricas_con_datos_insertados(cliente, h_admin, datos_metricas):
    r = await cliente.get(f"{R}/metricas", params={"desde": DIA.isoformat(), "hasta": DIA.isoformat()}, headers=h_admin)
    assert r.status_code == 200, r.text
    m = r.json()
    assert m["interacciones"] == 3 and m["sesiones"] == 2 and m["sesiones_escaladas"] == 1
    assert m["pct_resuelto_sin_humano"] == 50.0
    assert m["escalamientos_por_criterio"] == [{"clave": "CRIT-001", "total": 1}]
    assert m["intenciones_top"][0] == {"clave": "rastreo", "total": 3}
    assert {"clave": "cotizacion", "total": 1} in m["intenciones_top"]
    assert m["confianza_media"] == 0.7
    assert m["latencia_p50_ms"] == 200.0 and m["latencia_p95_ms"] == 290.0
    assert m["csat_promedio"] == 4.5 and m["calificaciones"] == 2
    assert m["pqrs_por_estado"] == [{"clave": "radicado", "total": 1}]
    assert sum(e["total"] for e in m["envios_por_estado"]) >= 5  # foto actual del dataset


async def test_metricas_rango_vacio_y_por_defecto(cliente, h_admin):
    r = await cliente.get(f"{R}/metricas", params={"desde": "2001-01-01", "hasta": "2001-01-02"}, headers=h_admin)
    m = r.json()
    assert r.status_code == 200 and m["sesiones"] == 0 and m["pct_resuelto_sin_humano"] is None
    assert m["latencia_p50_ms"] is None and m["csat_promedio"] is None
    r = await cliente.get(f"{R}/metricas", headers=h_admin)
    assert (
        r.status_code == 200
        and (date.fromisoformat(r.json()["hasta"]) - date.fromisoformat(r.json()["desde"])).days == 6
    )
    r = await cliente.get(f"{R}/metricas", params={"desde": "2026-02-01", "hasta": "2026-01-01"}, headers=h_admin)
    problema(r, 422, "RANGO_INVALIDO")


# --- conversaciones ---------------------------------------------------------------------------


async def test_conversaciones_listado_filtros_y_detalle(cliente, h_admin, datos_metricas):
    s1, s2 = datos_metricas
    r = await cliente.get(f"{R}/conversaciones", params={"intencion": "metricas_prueba"}, headers=h_admin)
    assert r.status_code == 200, r.text
    assert r.json()["total"] == 1
    conv = r.json()["items"][0]
    assert conv["id"] == str(s1) and conv["mensajes"] == 3 and conv["escalada"] is False
    assert conv["ultimo_mensaje"] == "usuario 10"

    r = await cliente.get(f"{R}/conversaciones", params={"tamano": 100, "estado": "activa"}, headers=h_admin)
    assert r.status_code == 200 and all(c["estado"] == "activa" for c in r.json()["items"])

    r = await cliente.get(f"{R}/conversaciones/{s2}", headers=h_admin)
    assert r.status_code == 200 and len(r.json()["mensajes"]) == 3
    assert r.json()["escalamiento"]["criterio_id"] == "CRIT-001"
    problema(await cliente.get(f"{R}/conversaciones/{uuid.uuid4()}", headers=h_admin), 404, "SESION_NO_ENCONTRADA")


# --- envíos -----------------------------------------------------------------------------------


async def test_envios_filtrados_y_enmascarados(cliente, h_admin):
    r = await cliente.get(f"{R}/envios", params={"estado": "ENTREGADO", "origen_dato": "dataset"}, headers=h_admin)
    assert r.status_code == 200, r.text
    guia = next(e for e in r.json()["items"] if e["numero_guia"] == "TLX-752190-CO")
    assert guia["destinatario"] == "I. R. B."
    assert "Bermúdez" not in r.text and "16.789.432" not in r.text
    r = await cliente.get(f"{R}/envios", params={"origen_dato": "dataset", "tamano": 2}, headers=h_admin)
    assert r.json()["total"] >= 5 and len(r.json()["items"]) == 2
    problema(await cliente.get(f"{R}/envios", params={"origen_dato": "otro"}, headers=h_admin), 422, "VALIDACION")


# --- PQRS -------------------------------------------------------------------------------------


async def _ticket(estado: EstadoPqrs, checklist: dict | None = None) -> str:
    async with SessionLocal() as s:
        t = TicketPqrs(
            tipo=TipoPqrs.SINIESTRO,
            estado=estado,
            usuario_id=await _id("cliente"),
            numero_guia="TLX-551904-CO",
            descripcion="Paquete perdido sin actualización.",
            tipo_averia="perdida",
            fecha_limite_respuesta=date(2026, 11, 25),
            checklist=checklist or {"guia": True},
        )
        s.add(t)
        await s.commit()
        await s.refresh(t, ["radicado"])
        return t.radicado


async def test_pqrs_transiciones_validas_e_invalidas(cliente, h_admin):
    rad = await _ticket(EstadoPqrs.RADICADO)

    async def cambiar(estado):
        return await cliente.patch(f"{R}/pqrs/{rad}", json={"estado": estado}, headers=h_admin)

    problema(await cambiar("cerrado"), 409, "TRANSICION_INVALIDA")
    problema(await cambiar("aprobado"), 409, "TRANSICION_INVALIDA")
    for estado in ("en_revision", "rechazado", "cerrado"):
        r = await cambiar(estado)
        assert r.status_code == 200 and r.json()["estado"] == estado, r.text
    problema(await cambiar("radicado"), 409, "TRANSICION_INVALIDA")
    assert await _auditado("pqrs.editar", rad)

    r = await cliente.get(f"{R}/pqrs", params={"estado": "cerrado", "tipo": "S", "tamano": 100}, headers=h_admin)
    assert r.status_code == 200 and rad in {t["radicado"] for t in r.json()["items"]}


async def test_pqrs_incompleto_solo_con_checklist_completo(cliente, h_admin):
    rad = await _ticket(EstadoPqrs.INCOMPLETO, {"guia": True, "factura": False})
    r = await cliente.patch(f"{R}/pqrs/{rad}", json={"estado": "radicado"}, headers=h_admin)
    problema(r, 409, "CHECKLIST_INCOMPLETO")
    rad = await _ticket(EstadoPqrs.INCOMPLETO, {"guia": True, "factura": True})
    r = await cliente.patch(f"{R}/pqrs/{rad}", json={"estado": "radicado"}, headers=h_admin)
    assert r.status_code == 200 and r.json()["estado"] == "radicado"


async def test_pqrs_asignacion(cliente, h_admin):
    rad = await _ticket(EstadoPqrs.RADICADO)
    r = await cliente.patch(f"{R}/pqrs/{rad}", json={"asignado_a": str(await _id("cliente"))}, headers=h_admin)
    problema(r, 422, "ASIGNADO_INVALIDO")
    asesor = str(await _id("asesor"))
    r = await cliente.patch(f"{R}/pqrs/{rad}", json={"asignado_a": asesor, "estado": "en_revision"}, headers=h_admin)
    assert r.status_code == 200 and r.json()["asignado_a"] == asesor and r.json()["estado"] == "en_revision"
    problema(await cliente.patch(f"{R}/pqrs/{rad}", json={}, headers=h_admin), 422, "SIN_CAMBIOS")
    problema(
        await cliente.patch(f"{R}/pqrs/PQRS-1999-999999", json={"estado": "cerrado"}, headers=h_admin),
        404,
        "RADICADO_NO_ENCONTRADO",
    )
    problema(
        await cliente.patch(f"{R}/pqrs/no-es-radicado", json={"estado": "cerrado"}, headers=h_admin), 422, "VALIDACION"
    )


# --- base de conocimiento ---------------------------------------------------------------------


class _EmbeddingsFalsos:
    """Vector determinista por texto: sin red, suficiente para probar la ingesta y el filtro `activo`."""

    async def embeber(self, textos):
        return [self._vector(t) for t in textos]

    async def embeber_consulta(self, texto):
        return self._vector(texto)

    @staticmethod
    def _vector(texto):
        h = hashlib.sha256(texto.encode()).digest()
        return [(h[i % 32] - 127.5) / 127.5 for i in range(get_settings().embed_dim)]


@pytest.fixture
async def embeddings_rag(monkeypatch):
    """bge-m3 real si Ollama responde; si no, embeddings falsos."""
    try:
        async with httpx.AsyncClient(timeout=2) as http:
            (await http.get(f"{get_settings().ollama_url}/api/tags")).raise_for_status()
        return True
    except httpx.HTTPError:
        monkeypatch.setattr(rag, "get_embeddings", lambda: _EmbeddingsFalsos())
        return False


def _md(etiqueta: str) -> bytes:
    return (
        f"# Manual de prueba {etiqueta}\n\nPreámbulo.\n\n"
        "## 1. Mascotas exóticas\nLos iguanodontes y tortugas gigantes no se reciben en ninguna oficina.\n\n"
        "## 2. Horarios\nLas oficinas abren de lunes a sábado.\n"
    ).encode()


async def _subir(cliente, h, contenido, nombre="manual.md", codigo="TEST-ADM-RAG", tipo="politica"):
    return await cliente.post(
        f"{R}/rag/documentos",
        headers=h,
        data={"codigo": codigo, "titulo": "Manual de prueba", "tipo": tipo},
        files={"archivo": (nombre, contenido, "text/markdown")},
    )


async def test_rag_subir_listar_buscar_desactivar(cliente, h_admin, embeddings_rag):
    etiqueta = uuid.uuid4().hex
    r = await _subir(cliente, h_admin, _md(etiqueta))
    assert r.status_code == 201, r.text
    assert r.json() == {"codigo": "TEST-ADM-RAG", "chunks": 2, "omitido": False}
    assert (await _subir(cliente, h_admin, _md(etiqueta))).json()["omitido"] is True
    assert await _auditado("rag.ingestar", "TEST-ADM-RAG")

    docs = (await cliente.get(f"{R}/rag/documentos", headers=h_admin)).json()
    doc = next(d for d in docs if d["codigo"] == "TEST-ADM-RAG")
    assert doc["chunks"] == 2 and doc["activo"] and doc["tipo"] == "politica" and doc["fuente"] == "manual.md"

    r = await cliente.get(f"{R}/rag/buscar", params={"q": "iguanodontes tortugas gigantes", "k": 3}, headers=h_admin)
    assert r.status_code == 200, r.text
    res = r.json()
    assert res and res[0]["doc_codigo"] == "TEST-ADM-RAG" and res[0]["seccion"] == "1. Mascotas exóticas"
    assert {"score_vector", "score_texto", "score_rrf", "metadatos"} <= set(res[0])
    r = await cliente.get(f"{R}/rag/buscar", params={"q": "iguanodontes", "tipos": "pqrs"}, headers=h_admin)
    assert all(x["doc_codigo"] != "TEST-ADM-RAG" for x in r.json())

    assert (await cliente.delete(f"{R}/rag/documentos/{doc['id']}", headers=h_admin)).status_code == 204
    assert await _auditado("rag.desactivar", "TEST-ADM-RAG")
    r = await cliente.get(f"{R}/rag/buscar", params={"q": "iguanodontes tortugas gigantes"}, headers=h_admin)
    assert all(x["doc_codigo"] != "TEST-ADM-RAG" for x in r.json())
    docs = (await cliente.get(f"{R}/rag/documentos", headers=h_admin)).json()
    assert next(d for d in docs if d["codigo"] == "TEST-ADM-RAG")["activo"] is False

    # Re-subir el mismo contenido lo reactiva sin re-embeber.
    r = await _subir(cliente, h_admin, _md(etiqueta))
    assert r.status_code == 201 and r.json()["omitido"] is True
    docs = (await cliente.get(f"{R}/rag/documentos", headers=h_admin)).json()
    assert next(d for d in docs if d["codigo"] == "TEST-ADM-RAG")["activo"] is True
    problema(await cliente.delete(f"{R}/rag/documentos/999999", headers=h_admin), 404, "DOCUMENTO_NO_ENCONTRADO")


async def test_rag_texto_plano_sin_encabezados(cliente, h_admin, embeddings_rag):
    texto = f"Aviso {uuid.uuid4().hex}: los envíos a San Andrés salen los lunes.".encode()
    r = await _subir(cliente, h_admin, texto, nombre="aviso.txt", codigo="TEST-ADM-TXT")
    assert r.status_code == 201 and r.json()["chunks"] == 1, r.text


async def test_rag_validaciones_de_archivo(cliente, h_admin, embeddings_rag):
    problema(await _subir(cliente, h_admin, b"%PDF-1.4", nombre="x.pdf"), 415, "TIPO_ARCHIVO_NO_PERMITIDO")
    problema(await _subir(cliente, h_admin, "## á\nñ".encode("latin-1")), 422, "CODIFICACION_INVALIDA")
    problema(await _subir(cliente, h_admin, b"   \n"), 422, "ARCHIVO_VACIO")
    problema(await _subir(cliente, h_admin, b"## a\n" + b"x" * (2 * 1024 * 1024)), 413, "ARCHIVO_GRANDE")
    problema(await _subir(cliente, h_admin, _md("v"), codigo="minusculas"), 422, "VALIDACION")
    problema(await _subir(cliente, h_admin, _md("v"), tipo="inventado"), 422, "VALIDACION")


# --- auditoría --------------------------------------------------------------------------------


async def test_auditoria_paginada_y_filtrada(cliente, h_admin):
    email = f"audit.{uuid.uuid4().hex[:6]}@translogix.demo"
    r = await cliente.post(
        f"{R}/usuarios",
        json={"email": email, "nombre": "Auditable", "password": CLAVE, "rol": "cliente"},
        headers=h_admin,
    )
    nuevo = r.json()["id"]
    r = await cliente.get(
        f"{R}/auditoria", params={"entidad": "usuario", "accion": "usuario.crear", "tamano": 5}, headers=h_admin
    )
    assert r.status_code == 200, r.text
    pagina = r.json()
    assert pagina["total"] >= 1 and len(pagina["items"]) <= 5
    ultimo = pagina["items"][0]
    assert ultimo["entidad_id"] == nuevo and ultimo["usuario_id"] == str(await _id("admin"))
    assert ultimo["detalle"] == {"rol": "cliente"}
    ids = [a["id"] for a in pagina["items"]]
    assert ids == sorted(ids, reverse=True)
