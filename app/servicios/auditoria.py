"""Registro de auditoría para acciones de asesores y administradores."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import Actor
from app.models import Auditoria


def auditar(s: AsyncSession, actor: Actor, accion: str, entidad: str, entidad_id: str | None = None, **detalle) -> None:
    """Agrega el registro a la transacción en curso (se confirma junto con la acción auditada)."""
    s.add(
        Auditoria(
            usuario_id=actor.id,
            accion=accion,
            entidad=entidad,
            entidad_id=entidad_id,
            detalle=detalle,
            ip=actor.ip if actor.ip != "desconocida" else None,
        )
    )
