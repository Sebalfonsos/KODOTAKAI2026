import uuid
from datetime import UTC, datetime, timedelta

import jwt

from app.config import get_settings
from tests.api.conftest import CREDENCIALES, bearer, login, problema

R = "/api/v1/auth"


def _email() -> str:
    return f"prueba.{uuid.uuid4().hex[:10]}@correo.co"


async def test_registro_201_y_email_duplicado_409(cliente):
    email = _email()
    datos = {"email": email, "nombre": "  Ana   Pérez ", "password": "Clave-Segura-2026"}
    r = await cliente.post(f"{R}/registro", json=datos)
    assert r.status_code == 201, r.text
    u = r.json()
    assert u["rol"] == "cliente" and u["nombre"] == "Ana Pérez" and "password" not in r.text
    # El correo se normaliza: mayúsculas no evitan el duplicado.
    problema(await cliente.post(f"{R}/registro", json=datos | {"email": email.upper()}), 409, "EMAIL_REGISTRADO")


async def test_registro_no_permite_escalar_rol(cliente):
    datos = {"email": _email(), "nombre": "Mallory", "password": "Clave-Segura-2026", "rol": "admin"}
    p = problema(await cliente.post(f"{R}/registro", json=datos), 422, "VALIDACION")
    assert any(e["campo"] == "rol" for e in p["errores"])


async def test_registro_contrasena_debil_422_sin_eco_del_valor(cliente):
    for clave in ("corta1", "solo-letras-sin-numeros"):
        r = await cliente.post(f"{R}/registro", json={"email": _email(), "nombre": "Ana", "password": clave})
        p = problema(r, 422, "VALIDACION")
        assert p["errores"][0]["campo"] == "password"
        assert clave not in r.text  # el valor recibido no se devuelve


async def test_login_ok_y_401_generico(cliente):
    t = await login(cliente, "cliente")
    assert t["token_type"] == "bearer"  # noqa: S105 and t["expires_in"] == 15 * 60 and t["rol"] == "cliente"
    email, _ = CREDENCIALES["cliente"]
    mala = await cliente.post(f"{R}/login", json={"email": email, "password": "no-es-la-clave-1"})
    inexistente = await cliente.post(f"{R}/login", json={"email": _email(), "password": "no-es-la-clave-1"})
    p1, p2 = problema(mala, 401, "CREDENCIALES_INVALIDAS"), problema(inexistente, 401, "CREDENCIALES_INVALIDAS")
    assert p1["detail"] == p2["detail"]  # no revela si el correo existe


async def test_me(cliente, h_vip):
    r = await cliente.get(f"{R}/me", headers=h_vip)
    assert r.status_code == 200
    assert r.json()["tipo_cuenta"] == "CORPORATIVO_GOLD"
    problema(await cliente.get(f"{R}/me"), 401, "NO_AUTENTICADO")


async def test_refresh_rota_y_reuso_revoca_la_familia(cliente):
    t1 = await login(cliente, "cliente")
    r = await cliente.post(f"{R}/refresh", json={"refresh_token": t1["refresh_token"]})
    assert r.status_code == 200, r.text
    t2 = r.json()
    assert t2["refresh_token"] != t1["refresh_token"]
    # Reusar el viejo = posible robo: 401 y se revoca toda la familia...
    viejo = await cliente.post(f"{R}/refresh", json={"refresh_token": t1["refresh_token"]})
    problema(viejo, 401, "REFRESH_REUTILIZADO")
    # ...incluido el refresh nuevo, que nunca se usó.
    nuevo = await cliente.post(f"{R}/refresh", json={"refresh_token": t2["refresh_token"]})
    problema(nuevo, 401, "REFRESH_INVALIDO")


async def test_refresh_desconocido_401(cliente):
    problema(await cliente.post(f"{R}/refresh", json={"refresh_token": "x" * 64}), 401, "REFRESH_INVALIDO")


async def test_logout_revoca_refresh(cliente):
    t = await login(cliente, "asesor")
    problema(await cliente.post(f"{R}/logout", json={"refresh_token": t["refresh_token"]}), 401, "NO_AUTENTICADO")
    r = await cliente.post(f"{R}/logout", json={"refresh_token": t["refresh_token"]}, headers=bearer(t))
    assert r.status_code == 204
    problema(await cliente.post(f"{R}/refresh", json={"refresh_token": t["refresh_token"]}), 401, "REFRESH_INVALIDO")


async def test_token_manipulado_o_expirado_401(cliente, tokens):
    acceso = tokens["cliente"]["access_token"]
    cab, carga, firma = acceso.split(".")
    otra_firma = ("A" if firma[0] != "A" else "B") + firma[1:]
    for malo in (f"{cab}.{carga}.{otra_firma}", "no.es.jwt", acceso[:-4]):
        r = await cliente.get(f"{R}/me", headers={"Authorization": f"Bearer {malo}"})
        p = problema(r, 401, "TOKEN_INVALIDO")
        assert r.headers["www-authenticate"] == "Bearer" and p
    # alg=none: no se acepta un token sin firma
    sin_firma = jwt.encode({"sub": str(uuid.uuid4()), "rol": "admin", "iss": "translogix-backend"}, None, "none")
    problema(await cliente.get(f"{R}/me", headers={"Authorization": f"Bearer {sin_firma}"}), 401, "TOKEN_INVALIDO")
    # Firmado con el secreto real pero vencido.
    vencido = jwt.encode(
        {
            "sub": str(uuid.uuid4()),
            "rol": "admin",
            "iss": "translogix-backend",
            "typ": "access",
            "exp": datetime.now(UTC) - timedelta(minutes=1),
        },
        get_settings().jwt_secret.get_secret_value(),
        "HS256",
    )
    problema(await cliente.get(f"{R}/me", headers={"Authorization": f"Bearer {vencido}"}), 401, "TOKEN_EXPIRADO")


async def test_rate_limit_login_429_con_retry_after(cliente):
    cuerpo = {"email": _email(), "password": "no-es-la-clave-1"}
    for _ in range(10):
        problema(await cliente.post(f"{R}/login", json=cuerpo), 401, "CREDENCIALES_INVALIDAS")
    r = await cliente.post(f"{R}/login", json=cuerpo)
    problema(r, 429, "LIMITE_EXCEDIDO")
    assert 1 <= int(r.headers["retry-after"]) <= 300
