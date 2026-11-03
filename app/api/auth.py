"""Autenticación: registro de clientes, login, rotación de refresh tokens (con detección de reuso) y perfil."""

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, status
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.errors import ApiError, respuestas
from app.core.ratelimit import limite
from app.core.security import (
    HASH_SENUELO,
    ActorAutenticado,
    crear_access_token,
    hash_password,
    hash_token,
    nuevo_refresh_token,
    verificar_password,
)
from app.db import get_session
from app.models import RefreshToken, Usuario
from app.models.base import Rol
from app.schemas.auth import LoginIn, RefreshIn, RegistroIn, TokensOut, UsuarioOut

router = APIRouter(prefix="/auth", tags=["Autenticación"])


async def _emitir(s: AsyncSession, u: Usuario, familia: uuid.UUID | None = None) -> TokensOut:
    access, expira = crear_access_token(u.id, u.rol, u.cuenta_id)
    token, token_hash = nuevo_refresh_token()
    s.add(
        RefreshToken(
            usuario_id=u.id,
            token_hash=token_hash,
            familia=familia or uuid.uuid4(),
            expira_en=datetime.now(UTC) + timedelta(days=get_settings().jwt_refresh_dias),
        )
    )
    return TokensOut(access_token=access, expires_in=expira, refresh_token=token, rol=u.rol)


@router.post(
    "/registro",
    status_code=status.HTTP_201_CREATED,
    response_model=UsuarioOut,
    summary="Registrar un cliente",
    responses=respuestas(409, 422, 429),
    dependencies=[Depends(limite("registro", 5, 3600))],
)
async def registrar(datos: RegistroIn, s: AsyncSession = Depends(get_session)):
    """Crea una cuenta con rol `cliente`. Los roles `asesor` y `admin` solo los asigna un administrador."""
    u = Usuario(
        email=datos.email.lower(), nombre=datos.nombre, password_hash=hash_password(datos.password), rol=Rol.CLIENTE
    )
    s.add(u)
    try:
        await s.commit()
    except IntegrityError as e:
        raise ApiError(409, "Ya existe una cuenta con ese correo.", "EMAIL_REGISTRADO") from e
    return UsuarioOut.model_validate(u)


@router.post(
    "/login",
    response_model=TokensOut,
    summary="Iniciar sesión",
    responses=respuestas(401, 422, 429),
    dependencies=[Depends(limite("login", 10, 300))],
)
async def login(datos: LoginIn, s: AsyncSession = Depends(get_session)):
    """Devuelve un access token (15 min) y un refresh token de un solo uso."""
    u = await s.scalar(select(Usuario).where(Usuario.email == datos.email.lower()))
    # Se verifica siempre un hash para que el tiempo de respuesta no revele si el correo existe.
    valido = verificar_password(u.password_hash if u else HASH_SENUELO, datos.password)
    if not (u and valido and u.activo):
        raise ApiError(401, "Correo o contraseña incorrectos.", "CREDENCIALES_INVALIDAS")
    u.ultimo_login = datetime.now(UTC)
    tokens = await _emitir(s, u)
    await s.commit()
    return tokens


@router.post(
    "/refresh",
    response_model=TokensOut,
    summary="Rotar refresh token",
    responses=respuestas(401, 422, 429),
    dependencies=[Depends(limite("refresh", 30, 300))],
)
async def refresh(datos: RefreshIn, s: AsyncSession = Depends(get_session)):
    """Entrega un par nuevo e invalida el anterior. Reusar un token ya rotado revoca toda su familia."""
    ahora = datetime.now(UTC)
    rt = await s.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == hash_token(datos.refresh_token)).with_for_update()
    )
    if rt is None or rt.revocado_en or rt.expira_en <= ahora:
        raise ApiError(401, "Refresh token inválido o expirado.", "REFRESH_INVALIDO")
    if rt.usado_en is not None:
        await s.execute(
            update(RefreshToken)
            .where(RefreshToken.familia == rt.familia, RefreshToken.revocado_en.is_(None))
            .values(revocado_en=ahora)
        )
        await s.commit()
        raise ApiError(
            401, "Se detectó reutilización del refresh token; inicia sesión de nuevo.", "REFRESH_REUTILIZADO"
        )
    u = await s.get(Usuario, rt.usuario_id)
    if u is None or not u.activo:
        raise ApiError(401, "Usuario inactivo.", "USUARIO_INACTIVO")
    rt.usado_en = ahora
    tokens = await _emitir(s, u, familia=rt.familia)
    await s.commit()
    return tokens


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, summary="Cerrar sesión", responses=respuestas(401, 422))
async def logout(datos: RefreshIn, actor: ActorAutenticado, s: AsyncSession = Depends(get_session)):
    """Revoca la familia del refresh token indicado (todos sus sucesores)."""
    rt = await s.scalar(select(RefreshToken).where(RefreshToken.token_hash == hash_token(datos.refresh_token)))
    if rt and rt.usuario_id == actor.id:
        await s.execute(
            update(RefreshToken)
            .where(RefreshToken.familia == rt.familia, RefreshToken.revocado_en.is_(None))
            .values(revocado_en=datetime.now(UTC))
        )
        await s.commit()


@router.get("/me", response_model=UsuarioOut, summary="Perfil del usuario autenticado", responses=respuestas(401))
async def yo(actor: ActorAutenticado, s: AsyncSession = Depends(get_session)):
    u = await s.get(Usuario, actor.id)
    if u is None:
        raise ApiError(401, "Usuario no encontrado.", "TOKEN_INVALIDO")
    out = UsuarioOut.model_validate(u)
    out.tipo_cuenta = u.cuenta.tipo_cuenta.value if u.cuenta else None
    return out
