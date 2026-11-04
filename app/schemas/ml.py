"""Esquemas de la API de predicciones (modelos entrenados con datos SIMULADOS)."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.artifacts import Paginacion


class ModeloOut(BaseModel):
    id: int
    nombre: Literal["riesgo_retraso", "demanda"]
    version: int = Field(examples=[3])
    algoritmo: str = Field(examples=["hist_gradient_boosting"])
    estado: Literal["candidato", "activo", "retirado", "rechazado"]
    metricas: dict[str, float | None] = Field(examples=[{"roc_auc": 0.668, "brier": 0.1406, "log_loss": 0.4493}])
    linea_base: dict[str, float | None] = Field(
        description="Riesgo: regresión logística y tasa base. Demanda: naive estacional (t-7).",
        examples=[{"roc_auc_logistica": 0.6659, "brier_tasa_base": 0.1525}],
    )
    n_train: int
    entrenado_hasta: datetime
    creado_en: datetime


class ModelosOut(BaseModel):
    activos: list[ModeloOut]
    historial: list[ModeloOut] = Field(description="Últimos 50 modelos, del más reciente al más antiguo")
    datos_simulados: bool = True


class EntrenamientoOut(BaseModel):
    id: int
    nombre: str = Field(examples=["riesgo_retraso"])
    motivo: str = Field(examples=["nuevos_datos"], description="inicial | nuevos_datos | deriva | antiguedad | manual")
    resultado: str = Field(examples=["promovido"], description="en_curso | promovido | rechazado | error")
    modelo_id: int | None
    detalle: dict = Field(description="Métricas del retador y del campeón en el mismo holdout, decisión y duración")
    iniciado_en: datetime
    terminado_en: datetime | None


class EntrenamientosOut(BaseModel):
    items: list[EntrenamientoOut]
    paginacion: Paginacion


class ResultadoModelo(BaseModel):
    version: int
    estado: str = Field(examples=["activo"])
    promovido: bool
    motivo_entrenamiento: str = Field(examples=["manual"])
    decision: str = Field(
        examples=["promovido; roc_auc: retador 0.6702 vs campeón 0.6650 (mejora +0.0052, tolerancia 0.0)"]
    )


class ResultadoEntrenamiento(BaseModel):
    duracion_s: float = Field(examples=[6.4])
    modelos: dict[str, ResultadoModelo]


class FactorOut(BaseModel):
    factor: str = Field(examples=["Trayecto Zona ZOMAC (TLX-BOG-QUI-025)"])
    impacto: float = Field(description="Puntos de probabilidad que aporta frente a un envío típico", examples=[0.358])


class RiesgoOut(BaseModel):
    guia: str = Field(examples=["TLX-984021-CO"])
    probabilidad: float = Field(ge=0, le=1, examples=[0.27])
    nivel: Literal["bajo", "medio", "alto"] = Field(description="bajo < 0,20 ≤ medio < 0,40 ≤ alto")
    factores: list[FactorOut]
    modelo: str = "riesgo_retraso"
    version: int
    estado_actual: str = Field(examples=["EN_TRANSITO"])
    retrasado_real: bool | None = Field(description="Desenlace real si el envío ya se entregó")
    datos_simulados: bool = True


class PuntoHistorico(BaseModel):
    fecha: date
    valor: float


class PuntoPronostico(BaseModel):
    fecha: date
    prediccion: float = Field(examples=[66.0])
    p10: float = Field(examples=[53.4], description="Límite inferior del intervalo del 80 %")
    p90: float = Field(examples=[71.9], description="Límite superior del intervalo del 80 %")


class PronosticoOut(BaseModel):
    origen: str = Field(examples=["Bogotá D.C."])
    hub: str = Field(examples=["Hub Central Zona Franca Fontibón"])
    dias: int
    modelo: str = "demanda"
    version: int
    historico: list[PuntoHistorico] = Field(description="Últimos 28 días observados")
    pronostico: list[PuntoPronostico]
    datos_simulados: bool = True


class EstadoAutoentrenamientoOut(BaseModel):
    """Reglas vigentes (variables de entorno `ML_*`) y su medición actual. Las reglas no se editan por API."""

    revision_cada_min: int = Field(description="`ML_CHECK_MIN`", examples=[10])
    min_etiquetas_nuevas: int = Field(description="`ML_MIN_NUEVOS`: reentrena al llegar a este número", examples=[200])
    max_horas: int = Field(description="`ML_MAX_HORAS`: reentrena si el último es más antiguo", examples=[24])
    delta_deriva: float = Field(description="Reentrena si Brier en vivo − Brier de entrenamiento lo supera")
    min_etiquetados: int = Field(description="Por debajo de este número no se puede entrenar")
    n_etiquetados: int
    n_nuevos: int
    error_vivo: float | None = Field(description="Brier en vivo; requiere al menos 50 predicciones con desenlace")
    n_vivo: int
    error_entrenamiento: float | None
    horas_desde_ultimo: float | None
    datos_simulados: bool = True


class AvanceSimulacionOut(BaseModel):
    dias: int
    desde: date
    hasta: date
    envios_nuevos: int
    envios_cerrados: int = Field(description="Pendientes que se entregaron en el periodo simulado")
    eventos: int
    datos_simulados: bool = True
