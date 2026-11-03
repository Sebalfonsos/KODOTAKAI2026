"""Autenticación (JWT de acceso + refresh rotativo), hashing argon2 y autorización por rol."""

import hashlib
import secrets
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select

from app.config import get_settings
from app.core.errors import ApiError
from app.models.base import Rol

_hasher = PasswordHasher()
_bearer = HTTPBearer(auto_error=False, description="Token de acceso JWT obtenido en /api/v1/auth/login")
ALG = "HS256"
EMISOR = "translogix-backend"


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verificar_password(hash_: str, password: str) -> bool:
    try:
        return _hasher.verify(hash_, password)
    except (VerificationError, InvalidHashError):
        return False


# Hash fijo para igualar el tiempo de respuesta cuando el email no existe (evita enumeración de usuarios).
HASH_SENUELO = _hasher.hash(secrets.token_urlsafe(16))


def crear_access_token(usuario_id: uuid.UUID, rol: Rol, cuenta_id: int | None) -> tuple[str, int]:
    s = get_settings()
    ahora = datetime.now(UTC)
    exp = ahora + timedelta(minutes=s.jwt_access_min)
    payload = {
        "sub": str(usuario_id),
        "rol": rol.value,
        "cta": cuenta_id,
        "iat": ahora,
        "exp": exp,
        "iss": EMISOR,
        "typ": "access",
    }
    return jwt.encode(payload, s.jwt_secret.get_secret_value(), algorithm=ALG), s.jwt_access_min * 60


def nuevo_refresh_token() -> tuple[str, str]:
    """Devuelve (token en claro para el cliente, sha256 para guardar)."""
    token = secrets.token_urlsafe(48)
    return token, hash_token(token)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@dataclass(frozen=True)
class Actor:
    """Quién hace la petición. `id is None` = invitado (sin login)."""

    id: uuid.UUID | None
    rol: Rol | None
    cuenta_id: int | None
    ip: str

    @property
    def es_invitado(self) -> bool:
        return self.id is None

    @property
    def sujeto(self) -> str:
        return str(self.id) if self.id else f"ip:{self.ip}"


def _decodificar(token: str) -> dict:
    try:
        datos = jwt.decode(
            token,
            get_settings().jwt_secret.get_secret_value(),
            algorithms=[ALG],
            issuer=EMISOR,
            options={"require": ["exp", "sub", "iss"]},
        )
    except jwt.ExpiredSignatureError as e:
        raise ApiError(
            401, "El token expiró; renueva con /auth/refresh.", "TOKEN_EXPIRADO", {"WWW-Authenticate": "Bearer"}
        ) from e
    except jwt.PyJWTError as e:
        raise ApiError(401, "Token inválido.", "TOKEN_INVALIDO", {"WWW-Authenticate": "Bearer"}) from e
    if datos.get("typ") != "access":
        raise ApiError(401, "Token inválido.", "TOKEN_INVALIDO", {"WWW-Authenticate": "Bearer"})
    return datos


# ponytail: caché por proceso de 30 s para no consultar la BD en cada petición; Redis si hay varias réplicas.
_vigencia: dict[uuid.UUID, tuple[float, tuple[Rol, int | None] | None]] = {}


async def _usuario_vigente(uid: uuid.UUID) -> tuple[Rol, int | None] | None:
    ahora = time.monotonic()
    if (c := _vigencia.get(uid)) and ahora - c[0] < 30:
        return c[1]
    from app.db import SessionLocal  # import tardío: evita el ciclo security -> db -> config
    from app.models import Usuario

    async with SessionLocal() as s:
        fila = (
            await s.execute(select(Usuario.rol, Usuario.cuenta_id, Usuario.activo).where(Usuario.id == uid))
        ).first()
    valor = (fila.rol, fila.cuenta_id) if fila and fila.activo else None
    _vigencia[uid] = (ahora, valor)
    return valor


def olvidar_usuario(uid: uuid.UUID) -> None:
    """Invalida la caché tras desactivar o cambiar el rol de un usuario."""
    _vigencia.pop(uid, None)


def ip_cliente(request: Request) -> str:
    # ponytail: la API solo escucha en loopback sin proxy; si se pone detrás de uno, leer X-Forwarded-For confiable.
    return request.client.host if request.client else "desconocida"


async def actor_opcional(
    request: Request, cred: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)]
) -> Actor:
    if cred is None:
        return Actor(None, None, None, ip_cliente(request))
    datos = _decodificar(cred.credentials)
    uid = uuid.UUID(datos["sub"])
    vigente = await _usuario_vigente(uid)
    if vigente is None:
        raise ApiError(401, "Usuario inactivo o inexistente.", "USUARIO_INACTIVO", {"WWW-Authenticate": "Bearer"})
    # El rol y la cuenta salen de la BD (no del token): un cambio de rol aplica en ≤ 30 s, sin esperar a que expire.
    return Actor(uid, vigente[0], vigente[1], ip_cliente(request))


async def actor_requerido(actor: Annotated[Actor, Depends(actor_opcional)]) -> Actor:
    if actor.es_invitado:
        raise ApiError(401, "Debes iniciar sesión.", "NO_AUTENTICADO", {"WWW-Authenticate": "Bearer"})
    return actor


def requiere_rol(*roles: Rol):
    """Dependencia de autorización: 403 si el rol del token no está permitido."""

    async def _dep(actor: Annotated[Actor, Depends(actor_requerido)]) -> Actor:
        if actor.rol not in roles:
            raise ApiError(403, "No tienes permiso para este recurso.", "SIN_PERMISO")
        return actor

    return _dep


ActorOpcional = Annotated[Actor, Depends(actor_opcional)]
ActorAutenticado = Annotated[Actor, Depends(actor_requerido)]
SoloAdmin = Annotated[Actor, Depends(requiere_rol(Rol.ADMIN))]
AsesorOAdmin = Annotated[Actor, Depends(requiere_rol(Rol.ASESOR, Rol.ADMIN))]
SoloCliente = Annotated[Actor, Depends(requiere_rol(Rol.CLIENTE))]
