"""Catálogos de negocio: geografía, hubs, trayectos/tarifas, estados de envío, festivos y mercancías."""

from datetime import date
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, ForeignKey, Index, Numeric, SmallInteger, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, PoliticaMercancia, TipoCobertura, pg_enum

Dinero = Numeric(14, 2)


class Departamento(Base):
    __tablename__ = "departamentos"
    codigo: Mapped[str] = mapped_column(String(2), primary_key=True, comment="Código DANE de 2 dígitos")
    nombre: Mapped[str] = mapped_column(String(80), unique=True)


class Hub(Base):
    __tablename__ = "hubs"
    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(String(120), unique=True)


class Municipio(Base):
    __tablename__ = "municipios"
    __table_args__ = (
        UniqueConstraint("nombre", "departamento_codigo", name="uq_municipios_nombre_departamento"),
        CheckConstraint("tiempo_entrega_estandar_horas > 0", name="tiempo_positivo"),
        CheckConstraint("peso_maximo_paquete_kg > 0 AND volumen_maximo_m3 > 0", name="maximos_positivos"),
        CheckConstraint("codigo_dane ~ '^[0-9]{5}$'", name="codigo_dane_formato"),
    )
    codigo_dane: Mapped[str] = mapped_column(String(5), primary_key=True)
    nombre: Mapped[str] = mapped_column(String(80), index=True)
    departamento_codigo: Mapped[str] = mapped_column(ForeignKey("departamentos.codigo"))
    tipo_cobertura: Mapped[TipoCobertura] = mapped_column(pg_enum(TipoCobertura, "tipo_cobertura"))
    tiempo_entrega_estandar_horas: Mapped[int] = mapped_column(SmallInteger)
    servicio_same_day: Mapped[bool]
    servicio_refrigerado: Mapped[bool]
    peso_maximo_paquete_kg: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    volumen_maximo_m3: Mapped[Decimal] = mapped_column(Numeric(8, 2))
    hub_id: Mapped[int] = mapped_column(ForeignKey("hubs.id"))
    frecuencia_despacho: Mapped[str] = mapped_column(String(80))
    restricciones_operativas: Mapped[str] = mapped_column(Text)

    departamento: Mapped[Departamento] = relationship(lazy="joined")
    hub: Mapped[Hub] = relationship(lazy="joined")


class Trayecto(Base):
    __tablename__ = "trayectos"
    __table_args__ = (
        UniqueConstraint("origen_dane", "destino_dane", name="uq_trayectos_origen_destino"),
        CheckConstraint("origen_dane <> destino_dane", name="origen_distinto_destino"),
        CheckConstraint(
            "tarifa_kg_real > 0 AND tarifa_kg_volumetrico > 0 AND flete_minimo > 0 AND factor_volumetrico > 0",
            name="tarifas_positivas",
        ),
        CheckConstraint(
            "porcentaje_seguro > 0 AND seguro_minimo >= 0 AND recargo_cadena_frio_pct >= 0"
            " AND recargo_mercancia_peligrosa >= 0",
            name="recargos_no_negativos",
        ),
        CheckConstraint("tiempo_entrega_horas > 0", name="tiempo_positivo"),
    )
    codigo: Mapped[str] = mapped_column(String(20), primary_key=True)
    origen_dane: Mapped[str] = mapped_column(ForeignKey("municipios.codigo_dane"))
    destino_dane: Mapped[str] = mapped_column(ForeignKey("municipios.codigo_dane"), index=True)
    tipo_cobertura: Mapped[TipoCobertura] = mapped_column(pg_enum(TipoCobertura, "tipo_cobertura"))
    tarifa_kg_real: Mapped[Decimal] = mapped_column(Dinero)
    tarifa_kg_volumetrico: Mapped[Decimal] = mapped_column(Dinero)
    factor_volumetrico: Mapped[int] = mapped_column(SmallInteger)
    flete_minimo: Mapped[Decimal] = mapped_column(Dinero)
    porcentaje_seguro: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    seguro_minimo: Mapped[Decimal] = mapped_column(Dinero)
    recargo_cadena_frio_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    recargo_mercancia_peligrosa: Mapped[Decimal] = mapped_column(Dinero)
    tiempo_entrega_horas: Mapped[int] = mapped_column(SmallInteger)
    observaciones: Mapped[str] = mapped_column(Text)

    origen: Mapped[Municipio] = relationship(foreign_keys=[origen_dane], lazy="joined")
    destino: Mapped[Municipio] = relationship(foreign_keys=[destino_dane], lazy="joined")


class EstadoEnvio(Base):
    __tablename__ = "estados_envio"
    codigo: Mapped[str] = mapped_column(String(40), primary_key=True)
    descripcion_cliente: Mapped[str] = mapped_column(Text)
    orden: Mapped[int] = mapped_column(SmallInteger)
    es_final: Mapped[bool] = mapped_column(default=False)


class Festivo(Base):
    __tablename__ = "festivos"
    fecha: Mapped[date] = mapped_column(Date, primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120))


class ClaseOnu(Base):
    __tablename__ = "clases_onu"
    codigo: Mapped[str] = mapped_column(String(5), primary_key=True, comment="Clase o subclase ONU, p. ej. 2.1")
    nombre: Mapped[str] = mapped_column(String(120))
    politica: Mapped[PoliticaMercancia] = mapped_column(pg_enum(PoliticaMercancia, "politica_mercancia"))
    condiciones: Mapped[str] = mapped_column(Text)


class ArticuloProhibido(Base):
    __tablename__ = "articulos_prohibidos"
    __table_args__ = (Index("ix_articulos_prohibidos_palabras", "palabras_clave", postgresql_using="gin"),)
    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, autoincrement=True)
    categoria: Mapped[str] = mapped_column(String(120), unique=True)
    palabras_clave: Mapped[list[str]] = mapped_column(ARRAY(String(60)))
    fundamento: Mapped[str] = mapped_column(Text)
