"""Esquemas de autenticación."""

import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.base import Rol

EMAIL = r"^[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,180}\.[A-Za-z]{2,24}$"


class RegistroIn(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [{"email": "ana.perez@correo.co", "nombre": "Ana Pérez", "password": "Clave-Segura-2026"}]
        },
    )
    email: str = Field(pattern=EMAIL, max_length=254)
    nombre: str = Field(min_length=2, max_length=120)
    password: str = Field(min_length=12, max_length=128, description="Mínimo 12 caracteres, con letras y números")

    @field_validator("password")
    @classmethod
    def _robusta(cls, v: str) -> str:
        if not (any(c.isalpha() for c in v) and any(c.isdigit() for c in v)):
            raise ValueError("La contraseña debe combinar letras y números.")
        return v

    @field_validator("nombre")
    @classmethod
    def _nombre(cls, v: str) -> str:
        return " ".join(v.split())


class LoginIn(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={"examples": [{"email": "cliente@translogix.demo", "password": "••••••••••••"}]},
    )
    email: str = Field(max_length=254)
    password: str = Field(max_length=128)


class RefreshIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    refresh_token: str = Field(min_length=20, max_length=200)


class TokensOut(BaseModel):
    access_token: str
    token_type: str = "bearer"  # noqa: S105 - tipo de token OAuth2, no es un secreto
    expires_in: int = Field(description="Segundos de vida del access token", examples=[900])
    refresh_token: str = Field(description="Un solo uso: cada /auth/refresh devuelve uno nuevo")
    rol: Rol


class UsuarioOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    email: str
    nombre: str
    rol: Rol
    cuenta_id: int | None
    tipo_cuenta: str | None = None
