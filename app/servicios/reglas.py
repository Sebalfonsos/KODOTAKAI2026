"""Reglas de escalamiento: el JSON oficial del reto es la configuración (se lee, no se copia al código)."""

import json
from functools import lru_cache

from app.config import get_settings


@lru_cache
def reglas_escalamiento() -> dict:
    return json.loads((get_settings().datos_dir / "reglas_escalacion_humana.json").read_text(encoding="utf-8"))
