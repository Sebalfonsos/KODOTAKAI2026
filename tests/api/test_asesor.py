"""Consola del asesor (HITL): RBAC, cola, toma con SKIP LOCKED, chat por SSE, resolución y auditoría."""

import asyncio
import uuid

import pytest
from sqlalchemy import select

from app.ai.eventos import publicar, stream_sse, suscribir
from app.db import SessionLocal
from app.models import Auditoria, Escalamiento, Mensaje, SesionChat, Usuario
from app.models.base import RolMensaje
from tests.api.conftest import CREDENCIALES, bearer, login, problema

R = "/api/v1/asesor"
CLAVE = "Asesor-Prueba-2026"


async def _usuario_id(rol: str) -> uuid.UUID:
    async with SessionLocal() as s:
        return await s.scalar(select(Usuario.id).where(Usuario.email == CREDENCIALES[rol][0].lower()))


async def crear_escalamiento(
    rol_cliente: str = "cliente", criterio: str = "CRIT-002", prioridad: int = 2, guia: str = "TLX-551904-CO"
) -> tuple[uuid.UUID, uuid.UUID]:
    """Inserta una sesión escalada con un mensaje del cliente, como lo dejaría el orquestador."""
    async with SessionLocal() as s:
        sesion = SesionChat(usuario_id=await _usuario_id(rol_cliente), estado="escalada", contexto={"guia": guia})
        s.add(sesion)
        await s.flush()
        s.add(
            Mensaje(
                sesion_id=sesion.id,
                turno_id=uuid.uuid4(),
                rol=RolMensaje.USUARIO,
                contenido="Esto es una estafa, quiero hablar con humano",
                intencion="queja",
            )
        )
        esc = Escalamiento(
            sesion_id=sesion.id,
            criterio_id=criterio,
            prioridad=prioridad,
            resumen_ia="Cliente molesto por demora de su guía.",
            payload={"session_id": str(sesion.id), "numero_guia_consultada": guia, "intentos_previos": 0},
        )
        s.add(esc)
        await s.commit()
        return sesion.id, esc.id


@pytest.fixture(scope="session")
async def h_asesor2(cliente, h_admin):
    """Segundo asesor creado por la API de administración (para concurrencia y propiedad)."""
    email = f"asesor2.{uuid.uuid4().hex[:6]}@translogix.demo"
    r = await cliente.post(
        "/api/v1/admin/usuarios",
        json={"email": email, "nombre": "Segundo Asesor", "password": CLAVE, "rol": "asesor"},
        headers=h_admin,
    )
    assert r.status_code == 201, r.text
    r = await cliente.post("/api/v1/auth/login", json={"email": email, "password": CLAVE})
    assert r.status_code == 200, r.text
    return bearer(r.json())


RUTAS = [
    ("GET", "/escalamientos"),
    ("POST", f"/escalamientos/{uuid.uuid4()}/tomar"),
    ("GET", f"/sesiones/{uuid.uuid4()}"),
    ("POST", f"/sesiones/{uuid.uuid4()}/mensajes"),
    ("POST", f"/escalamientos/{uuid.uuid4()}/resolver"),
]


@pytest.mark.parametrize(("metodo", "ruta"), RUTAS)
async def test_rbac_asesor(cliente, h_cliente, h_vip, metodo, ruta):
    problema(await cliente.request(metodo, R + ruta, json={"texto": "x"}), 401, "NO_AUTENTICADO")
    for h in (h_cliente, h_vip):
        problema(await cliente.request(metodo, R + ruta, json={"texto": "x"}, headers=h), 403, "SIN_PERMISO")


async def test_cola_ordenada_por_prioridad(cliente, h_asesor):
    _, baja = await crear_escalamiento(criterio="CRIT-001", prioridad=5)
    _, alta = await crear_escalamiento(criterio="CRIT-005", prioridad=1, guia="TLX-310482-CO")
    r = await cliente.get(f"{R}/escalamientos", params={"tamano": 100}, headers=h_asesor)
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    ids = [i["id"] for i in items]
    assert ids.index(str(alta)) < ids.index(str(baja))
    assert [i["prioridad"] for i in items] == sorted(i["prioridad"] for i in items)
    fila = next(i for i in items if i["id"] == str(alta))
    assert fila["numero_guia"] == "TLX-310482-CO" and fila["criterio_id"] == "CRIT-005"
    assert fila["accion"] == "ESCALAR_Urgencia_OPERACIONES" and fila["espera_s"] >= 0
    assert fila["resumen_ia"] and fila["estado"] == "pendiente"


async def test_flujo_completo_tomar_responder_resolver(cliente, h_asesor, h_asesor2):
    sesion_id, esc_id = await crear_escalamiento()

    # Sin tomar no se puede responder.
    r = await cliente.post(f"{R}/sesiones/{sesion_id}/mensajes", json={"texto": "Hola"}, headers=h_asesor)
    problema(r, 409, "ESCALAMIENTO_NO_TOMADO")

    r = await cliente.post(f"{R}/escalamientos/{esc_id}/tomar", headers=h_asesor)
    assert r.status_code == 200, r.text
    tomado = r.json()
    assert tomado["estado"] == "tomado" and tomado["asesor_id"] == str(await _usuario_id("asesor"))
    assert tomado["payload"]["numero_guia_consultada"] == "TLX-551904-CO"
    # Idempotente para el mismo asesor; 409 para otro.
    assert (await cliente.post(f"{R}/escalamientos/{esc_id}/tomar", headers=h_asesor)).status_code == 200
    problema(await cliente.post(f"{R}/escalamientos/{esc_id}/tomar", headers=h_asesor2), 409, "YA_TOMADO")
    r = await cliente.post(f"{R}/sesiones/{sesion_id}/mensajes", json={"texto": "Yo atiendo"}, headers=h_asesor2)
    problema(r, 409, "ESCALAMIENTO_NO_TOMADO")

    with suscribir(sesion_id) as cola:
        r = await cliente.post(
            f"{R}/sesiones/{sesion_id}/mensajes", json={"texto": "  Hola, ya reviso tu guía.  "}, headers=h_asesor
        )
        assert r.status_code == 201, r.text
        assert r.json()["rol"] == "asesor" and r.json()["contenido"] == "Hola, ya reviso tu guía."
        tipo, datos = cola.get_nowait()
        assert tipo == "mensaje_asesor" and datos["texto"] == "Hola, ya reviso tu guía."
        assert datos["asesor"] == "Asesora de servicio" and datos["creado_en"]

        r = await cliente.post(
            f"{R}/escalamientos/{esc_id}/resolver", json={"nota": "Entrega reprogramada"}, headers=h_asesor
        )
        assert r.status_code == 200, r.text
        assert r.json()["estado"] == "resuelto" and r.json()["resuelto_en"]
        assert r.json()["payload"]["nota_resolucion"] == "Entrega reprogramada"
        assert cola.get_nowait() == (
            "escalamiento_resuelto",
            {"escalamiento_id": str(esc_id), "nota": "Entrega reprogramada"},
        )

    r = await cliente.get(f"{R}/sesiones/{sesion_id}", headers=h_asesor)
    assert r.status_code == 200, r.text
    detalle = r.json()
    assert detalle["estado"] == "activa"  # la IA retoma
    assert [m["rol"] for m in detalle["mensajes"]] == ["usuario", "asesor"]
    assert detalle["usuario"]["rol"] == "cliente" and detalle["escalamiento"]["estado"] == "resuelto"
    assert detalle["cuenta"]["es_vip"] is False and "*" in detalle["cuenta"]["nit_enmascarado"]

    problema(await cliente.post(f"{R}/escalamientos/{esc_id}/resolver", headers=h_asesor), 409, "ESCALAMIENTO_RESUELTO")
    problema(await cliente.post(f"{R}/escalamientos/{esc_id}/tomar", headers=h_asesor), 409, "ESCALAMIENTO_RESUELTO")
    r = await cliente.post(f"{R}/sesiones/{sesion_id}/mensajes", json={"texto": "¿Sigues?"}, headers=h_asesor)
    problema(r, 409, "ESCALAMIENTO_NO_TOMADO")

    async with SessionLocal() as s:
        acciones = set(
            await s.scalars(select(Auditoria.accion).where(Auditoria.entidad_id.in_([str(esc_id), str(sesion_id)])))
        )
    assert acciones == {"escalamiento.tomar", "sesion.mensaje_asesor", "escalamiento.resolver"}


async def test_concurrencia_skip_locked_un_solo_ganador(cliente, h_asesor, h_asesor2):
    for _ in range(3):
        _, esc_id = await crear_escalamiento()
        url = f"{R}/escalamientos/{esc_id}/tomar"
        r1, r2 = await asyncio.gather(cliente.post(url, headers=h_asesor), cliente.post(url, headers=h_asesor2))
        assert sorted([r1.status_code, r2.status_code]) == [200, 409], (r1.text, r2.text)
        perdedor = r1 if r1.status_code == 409 else r2
        problema(perdedor, 409, "YA_TOMADO")


async def test_admin_puede_intervenir_y_resolver(cliente, h_asesor, h_admin):
    sesion_id, esc_id = await crear_escalamiento()
    problema(await cliente.post(f"{R}/escalamientos/{esc_id}/resolver", headers=h_admin), 409, "ESCALAMIENTO_NO_TOMADO")
    assert (await cliente.post(f"{R}/escalamientos/{esc_id}/tomar", headers=h_asesor)).status_code == 200
    r = await cliente.post(f"{R}/sesiones/{sesion_id}/mensajes", json={"texto": "Supervisión"}, headers=h_admin)
    assert r.status_code == 201, r.text
    r = await cliente.post(f"{R}/escalamientos/{esc_id}/resolver", headers=h_admin)
    assert r.status_code == 200 and r.json()["payload"]["nota_resolucion"] is None


async def test_sesion_vip_muestra_cuenta_corporativa(cliente, h_asesor):
    sesion_id, _ = await crear_escalamiento(rol_cliente="vip", criterio="CRIT-004", prioridad=4, guia="TLX-984021-CO")
    r = await cliente.get(f"{R}/sesiones/{sesion_id}", headers=h_asesor)
    assert r.status_code == 200, r.text
    cuenta = r.json()["cuenta"]
    assert cuenta["tipo_cuenta"] == "CORPORATIVO_GOLD" and cuenta["es_vip"] is True
    assert cuenta["nit_enmascarado"].endswith("456-7") and "900" not in cuenta["nit_enmascarado"]


async def test_no_encontrados_y_validacion(cliente, h_asesor):
    problema(
        await cliente.post(f"{R}/escalamientos/{uuid.uuid4()}/tomar", headers=h_asesor),
        404,
        "ESCALAMIENTO_NO_ENCONTRADO",
    )
    problema(
        await cliente.post(f"{R}/escalamientos/{uuid.uuid4()}/resolver", headers=h_asesor),
        404,
        "ESCALAMIENTO_NO_ENCONTRADO",
    )
    problema(await cliente.get(f"{R}/sesiones/{uuid.uuid4()}", headers=h_asesor), 404, "SESION_NO_ENCONTRADA")
    r = await cliente.post(f"{R}/sesiones/{uuid.uuid4()}/mensajes", json={"texto": "hola"}, headers=h_asesor)
    problema(r, 404, "SESION_NO_ENCONTRADA")
    sesion_id, _ = await crear_escalamiento()
    for texto in ("", "   ", "x" * 2001):
        r = await cliente.post(f"{R}/sesiones/{sesion_id}/mensajes", json={"texto": texto}, headers=h_asesor)
        problema(r, 422, "VALIDACION")
    problema(await cliente.get(f"{R}/escalamientos", params={"estado": "otro"}, headers=h_asesor), 422, "VALIDACION")


async def test_login_independiente_del_fixture(cliente):
    """El asesor demo puede iniciar sesión (sanidad del fixture de credenciales)."""
    assert (await login(cliente, "asesor"))["rol"] == "asesor"


async def test_fila_bloqueada_por_otra_transaccion_responde_409_sin_esperar(cliente, h_asesor):
    """Determinista: otra transacción tiene la fila con FOR UPDATE; SKIP LOCKED no espera y responde 409."""
    _, esc_id = await crear_escalamiento()
    async with SessionLocal() as otra:
        await otra.scalar(select(Escalamiento).where(Escalamiento.id == esc_id).with_for_update())
        r = await asyncio.wait_for(cliente.post(f"{R}/escalamientos/{esc_id}/tomar", headers=h_asesor), timeout=5)
        p = problema(r, 409, "YA_TOMADO")
        assert "está tomando" in p["detail"]
        await otra.rollback()
    assert (await cliente.post(f"{R}/escalamientos/{esc_id}/tomar", headers=h_asesor)).status_code == 200


async def test_eventos_del_asesor_permisos_y_contenido(cliente, h_asesor, h_cliente):
    sesion_id, _ = await crear_escalamiento()
    problema(await cliente.get(f"{R}/sesiones/{sesion_id}/eventos"), 401)
    problema(await cliente.get(f"{R}/sesiones/{sesion_id}/eventos", headers=h_cliente), 403)
    problema(await cliente.get(f"{R}/sesiones/{uuid.uuid4()}/eventos", headers=h_asesor), 404)

    # A diferencia del stream del cliente, este sí entrega lo que escribe el cliente.
    stream = stream_sse(sesion_id)
    assert await anext(stream) == ": conectado\n\n"
    publicar(sesion_id, ("mensaje_cliente", {"texto": "¿Sigues ahí?"}))
    assert await anext(stream) == 'event: mensaje_cliente\ndata: {"texto": "¿Sigues ahí?"}\n\n'
    await stream.aclose()

    stream = stream_sse(sesion_id, ocultar=frozenset({"mensaje_cliente"}))
    await anext(stream)
    publicar(sesion_id, ("mensaje_cliente", {"texto": "eco"}))
    publicar(sesion_id, ("mensaje_asesor", {"texto": "Hola"}))
    assert (await anext(stream)).startswith("event: mensaje_asesor")
    await stream.aclose()
