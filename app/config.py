"""Configuración leída de variables de entorno / `.env` (pydantic-settings)."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

RAIZ = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=RAIZ / ".env", extra="ignore")

    database_url: str
    test_database_url: str | None = None
    apitest_database_url: str | None = None

    llm_base_url: str = "http://127.0.0.1:8000/v1"
    llm_api_key_file: Path | None = None
    llm_timeout_s: float = 30.0
    llm_max_tokens: int = 120  # ~3 frases: acota la latencia total de la respuesta

    ollama_url: str = "http://127.0.0.1:11434"
    embed_model: str = "bge-m3"
    embed_dim: int = 1024
    # ponytail: 0 = embeddings en CPU para no competir por VRAM con el clúster de voz.
    embed_num_gpu: int = 0

    jwt_secret: SecretStr
    jwt_access_min: int = 15
    jwt_refresh_dias: int = 7
    cors_origins: str = ""
    demo_enabled: bool = True

    datos_dir: Path = RAIZ / "KODOTAKAIINFO"
    upload_dir: Path = RAIZ / "var" / "uploads"
    max_upload_bytes: int = 10 * 1024 * 1024
    max_mensaje_chars: int = 2000
    rate_chat_por_min: int = 30  # por usuario o IP; subirlo solo para pruebas de carga

    ml_check_min: int = Field(default=10, ge=1)
    ml_min_nuevos: int = Field(default=200, ge=1)
    ml_max_horas: int = Field(default=24, ge=1)

    demo_admin_email: str | None = None
    demo_admin_password: SecretStr | None = None
    demo_asesor_email: str | None = None
    demo_asesor_password: SecretStr | None = None
    demo_cliente_email: str | None = None
    demo_cliente_password: SecretStr | None = None
    demo_vip_email: str | None = None
    demo_vip_password: SecretStr | None = None

    @property
    def cors_lista(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def llm_api_key(self) -> str | None:
        if self.llm_api_key_file and self.llm_api_key_file.exists():
            return self.llm_api_key_file.read_text().splitlines()[0].strip()
        return None


@lru_cache
def get_settings() -> Settings:
    return Settings()
