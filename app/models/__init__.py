"""Modelo de datos completo. Importar este paquete registra todas las tablas en `Base.metadata`."""

from app.models.base import Base  # noqa: F401
from app.models.catalogo import (  # noqa: F401
    ArticuloProhibido,
    ClaseOnu,
    Departamento,
    EstadoEnvio,
    Festivo,
    Hub,
    Municipio,
    Trayecto,
)
from app.models.chat import Calificacion, CriterioEscalamiento, Escalamiento, Mensaje, SesionChat  # noqa: F401
from app.models.cuentas import Cuenta, RefreshToken, Usuario  # noqa: F401
from app.models.envios import Envio, EventoEnvio, PruebaEntrega  # noqa: F401
from app.models.ml import Entrenamiento, ModeloMl, Prediccion  # noqa: F401
from app.models.operacion import Auditoria, Cotizacion, DocumentoPqrs, Idempotencia, TicketPqrs  # noqa: F401
from app.models.rag import Chunk, Documento  # noqa: F401
