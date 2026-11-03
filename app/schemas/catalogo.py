"""Esquemas de cobertura, trayectos, mercancías y paginación."""

from decimal import Decimal

from pydantic import BaseModel, Field


class Pagina[T](BaseModel):
    items: list[T]
    total: int
    pagina: int
    tamano: int


class MunicipioOut(BaseModel):
    codigo_dane: str = Field(examples=["27001"])
    nombre: str = Field(examples=["Quibdó"])
    departamento: str = Field(examples=["Chocó"])
    tipo_cobertura: str = Field(examples=["zomac"])
    tiempo_entrega_estandar_horas: int = Field(examples=[96])
    servicio_same_day: bool
    servicio_refrigerado: bool
    peso_maximo_paquete_kg: Decimal
    volumen_maximo_m3: Decimal
    hub: str
    frecuencia_despacho: str
    restricciones_operativas: str


class OpcionCiudad(BaseModel):
    valor: str = Field(description="Nombre a enviar en /cotizar", examples=["Medellín"])
    etiqueta: str = Field(examples=["Medellín (Antioquia)"])
    codigo_dane: str
    codigo_trayecto: str | None = Field(default=None, description="Solo en destinos")
    tiempo_entrega_horas: int | None = None


class VeredictoOut(BaseModel):
    producto_consultado: str
    veredicto: str = Field(
        description="permitido | restringido | solo_ftl | prohibido | desconocido", examples=["prohibido"]
    )
    producto: str | None = Field(examples=["animales vivos"])
    clase_onu: str | None
    motivo: str
    fuente: str | None = Field(examples=["DOC-OPS-2026-03 §5.5"])
    documentos_requeridos: list[str]
    categoria_embalaje: str | None


class ClaseOnuOut(BaseModel):
    codigo: str = Field(examples=["8"])
    nombre: str = Field(examples=["Sustancias corrosivas"])
    politica: str = Field(examples=["restringido"])
    condiciones: str
