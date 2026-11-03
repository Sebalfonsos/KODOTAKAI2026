"""Pruebas de la API REST contra PostgreSQL real (BD exclusiva `translogix_apitest`).

El esquema se reconstruye con Alembic (downgrade base + upgrade head) y se carga la semilla sin RAG.
"""

import asyncio
import os
import tempfile
from concurrent.futures import ThreadPoolExecutor

from app.config import RAIZ, Settings, get_settings

# --- entorno ANTES de importar la app (app.db crea el engine al importarse) -------------------
_cfg = Settings()
if not _cfg.apitest_database_url:
    raise RuntimeError("Define APITEST_DATABASE_URL en .env (BD translogix_apitest, exclusiva de tests/api).")
os.environ["DATABASE_URL"] = _cfg.apitest_database_url
os.environ["UPLOAD_DIR"] = tempfile.mkdtemp(prefix="tlx-apitest-uploads-")
get_settings.cache_clear()

import httpx  # noqa: E402
import pytest  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

from alembic import command  # noqa: E402
from app.core import ratelimit  # noqa: E402
from app.core.errors import PROBLEM  # noqa: E402
from app.main import app  # noqa: E402

URL = os.environ["DATABASE_URL"]


def _migrar() -> None:
    cfg = Config(str(RAIZ / "alembic.ini"))
    cfg.set_main_option("script_location", str(RAIZ / "alembic"))
    cfg.attributes["url"] = URL
    command.downgrade(cfg, "base")  # valida también que la migración baja limpia
    command.upgrade(cfg, "head")


async def _sembrar() -> None:
    from app.seed import cargar_catalogos, cargar_dataset, cargar_usuarios

    # Engine propio (NullPool): este bucle de eventos es distinto del de las pruebas.
    engine = create_async_engine(URL, poolclass=NullPool)
    async with async_sessionmaker(engine)() as s, s.begin():
        datos = get_settings().datos_dir
        dane = await cargar_catalogos(s, datos)
        await cargar_dataset(s, datos, dane)
        await cargar_usuarios(s)
    await engine.dispose()


@pytest.fixture(scope="session", autouse=True)
def bd():
    # En un hilo aparte: alembic/env.py y la semilla usan asyncio.run, que no puede anidarse.
    with ThreadPoolExecutor(1) as ex:
        ex.submit(_migrar).result()
        ex.submit(asyncio.run, _sembrar()).result()


@pytest.fixture(autouse=True)
def _limpiar_rate_limit():
    ratelimit.reiniciar()
    yield
    ratelimit.reiniciar()


@pytest.fixture(scope="session")
async def cliente():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        yield c


# --- autenticación ----------------------------------------------------------------------------

CREDENCIALES = {
    "admin": (_cfg.demo_admin_email, _cfg.demo_admin_password),
    "asesor": (_cfg.demo_asesor_email, _cfg.demo_asesor_password),
    "cliente": (_cfg.demo_cliente_email, _cfg.demo_cliente_password),
    "vip": (_cfg.demo_vip_email, _cfg.demo_vip_password),
}


async def login(c: httpx.AsyncClient, rol: str) -> dict:
    email, pwd = CREDENCIALES[rol]
    assert email and pwd, f"Faltan DEMO_{rol.upper()}_EMAIL/PASSWORD en .env"
    r = await c.post("/api/v1/auth/login", json={"email": email, "password": pwd.get_secret_value()})
    assert r.status_code == 200, r.text
    return r.json()


def bearer(tokens: dict) -> dict:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


@pytest.fixture(scope="session")
async def tokens(cliente) -> dict[str, dict]:
    """Un par de tokens por rol para toda la sesión (no usar para probar logout/refresh)."""
    return {rol: await login(cliente, rol) for rol in CREDENCIALES}


@pytest.fixture(scope="session")
def h_admin(tokens):
    return bearer(tokens["admin"])


@pytest.fixture(scope="session")
def h_asesor(tokens):
    return bearer(tokens["asesor"])


@pytest.fixture(scope="session")
def h_cliente(tokens):
    """Cliente estándar, dueño de TLX-551904-CO."""
    return bearer(tokens["cliente"])


@pytest.fixture(scope="session")
def h_vip(tokens):
    """Cliente PharmaSur (CORPORATIVO_GOLD), dueño de TLX-984021-CO."""
    return bearer(tokens["vip"])


# --- aserciones -------------------------------------------------------------------------------


def problema(r: httpx.Response, status: int, codigo: str | None = None) -> dict:
    """Comprueba que la respuesta es un problem+json RFC 9457 completo y lo devuelve."""
    assert r.status_code == status, f"{r.status_code} != {status}: {r.text}"
    assert r.headers["content-type"].startswith(PROBLEM), r.headers["content-type"]
    p = r.json()
    assert p["status"] == status
    assert p["title"] and p["request_id"] == r.headers["x-request-id"]
    assert p["instance"] == r.request.url.path
    if codigo:
        assert p["codigo"] == codigo, p
        assert p["type"].endswith("/" + codigo.lower().replace("_", "-"))
    return p
