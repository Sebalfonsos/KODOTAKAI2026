"""Cotizador determinista (RF-COT) con las decisiones D-01, D-02, D-03, D-05 y D-06.

API:
- `Trayecto.desde_fila(fila: dict)`: fila de `matriz_tarifas_y_fletes.csv` (csv.DictReader) -> Trayecto.
- `MunicipioCobertura(**item)`: item de `directorio_cobertura_y_tiempos.json`.
- `buscar_trayecto(trayectos, origen, destino) -> Trayecto` (TRAYECTO_INEXISTENTE, D-04).
- `buscar_municipio(municipios, nombre) -> MunicipioCobertura` (SIN_COBERTURA).
  Los nombres se comparan sin tildes ni mayúsculas, y "Bogotá" equivale a "Bogotá D.C.".
- `cotizar(trayecto, destino, solicitud) -> Cotizacion`.

Reglas de cálculo (dinero en Decimal, sin redondeos intermedios):
- peso_volumetrico = alto × ancho × largo / factor (CSV: 4000); peso_facturable = max(real, volumétrico).
- D-02: tarifa por kg real si gana el peso real (empate incluido); tarifa volumétrica si gana el volumen.
- D-03: flete = max(peso_facturable × tarifa, flete_minimo). Recargo frío = % del CSV sobre el flete base
  (peso × tarifa, antes del mínimo). Recargo MP = suma fija del CSV.
- D-01: seguro = max(porcentaje_seguro % × valor declarado, seguro_minimo_cop del CSV).
- total = flete + recargos + seguro, redondeado a pesos con ROUND_HALF_UP solo al final
  (`total_sin_redondeo` conserva el valor exacto).

Validaciones (ErrorDominio.codigo): DATOS_INVALIDOS (dimensiones, peso, valor o unidades <= 0),
MODALIDAD_INVALIDA, PAQUETERIA_EXCEDE_50_KG (dosier §2.B, sobre el peso real),
PESO_EXCEDE_MAXIMO_DESTINO (peso real por unidad > peso_maximo_paquete_kg del destino),
REFRIGERADO_NO_DISPONIBLE (D-06). RF-COT-5 (prohibidos) lo resuelve el orquestador con `mercancias`.
"""

import re
from dataclasses import dataclass, field
from decimal import Decimal

from app.domain import ErrorDominio, a_decimal, redondear_pesos
from app.domain.sanitizar import normalizar_para_busqueda

LIMITE_PAQUETERIA_KG = Decimal(50)
MODALIDADES = ("paqueteria", "carga")


@dataclass(frozen=True)
class Trayecto:
    codigo_trayecto: str
    ciudad_origen: str
    departamento_origen: str
    ciudad_destino: str
    departamento_destino: str
    tipo_cobertura: str
    tarifa_base_kg_real_cop: Decimal
    tarifa_base_kg_volumetrico_cop: Decimal
    factor_divisitivas_volumetrico: Decimal
    flete_minimo_cop: Decimal
    porcentaje_seguro: Decimal
    seguro_minimo_cop: Decimal
    recargo_cadena_frio_pct: Decimal
    recargo_mercancia_peligrosa_cop: Decimal
    tiempo_entrega_estimado_horas: int
    observaciones_ruta: str

    @classmethod
    def desde_fila(cls, fila: dict) -> "Trayecto":
        datos = {k.lstrip("﻿"): v for k, v in fila.items()}
        for campo, tipo in cls.__annotations__.items():
            if tipo is Decimal:
                datos[campo] = Decimal(datos[campo])
            elif tipo is int:
                datos[campo] = int(datos[campo])
        return cls(**{k: datos[k] for k in cls.__annotations__})


@dataclass(frozen=True)
class MunicipioCobertura:
    codigo_dane: str
    municipio: str
    departamento: str
    tipo_cobertura: str
    tiempo_entrega_estandar_horas: int
    servicio_same_day_disponible: bool
    servicio_refrigerado_disponible: bool
    peso_maximo_paquete_kg: float
    volumen_maximo_m3: float
    hub_operativo_asignado: str
    frecuencia_despacho: str
    restricciones_operativas: str


@dataclass(frozen=True)
class SolicitudCotizacion:
    alto_cm: Decimal
    ancho_cm: Decimal
    largo_cm: Decimal
    peso_kg: Decimal
    valor_declarado: Decimal
    modalidad: str = "paqueteria"  # 'paqueteria' | 'carga'
    cadena_frio: bool = False
    mercancia_peligrosa: bool = False
    unidades: int = 1


@dataclass(frozen=True)
class Cotizacion:
    codigo_trayecto: str
    peso_real: Decimal
    peso_volumetrico: Decimal
    peso_facturable: Decimal
    base_cobro: str  # 'real' | 'volumetrico'
    tarifa_aplicada: Decimal
    flete_base: Decimal
    flete_minimo_aplicado: bool
    flete: Decimal
    recargo_frio: Decimal
    recargo_mp: Decimal
    seguro: Decimal
    total_sin_redondeo: Decimal
    total: Decimal
    horas_estimadas: int
    observaciones: list[str] = field(default_factory=list)


def _clave_ciudad(nombre: str) -> str:
    return re.sub(r"\s+d\s*c$", "", normalizar_para_busqueda(nombre))


def buscar_trayecto(trayectos: list[Trayecto], origen: str, destino: str) -> Trayecto:
    o, d = _clave_ciudad(origen), _clave_ciudad(destino)
    for t in trayectos:
        if _clave_ciudad(t.ciudad_origen) == o and _clave_ciudad(t.ciudad_destino) == d:
            return t
    raise ErrorDominio(
        "TRAYECTO_INEXISTENTE",
        f"No tenemos tarifa para el trayecto {origen} → {destino}. Un asesor puede ayudarte con esta cotización.",
    )


def buscar_municipio(municipios: list[MunicipioCobertura], nombre: str) -> MunicipioCobertura:
    clave = _clave_ciudad(nombre)
    for m in municipios:
        if _clave_ciudad(m.municipio) == clave:
            return m
    raise ErrorDominio("SIN_COBERTURA", f"No tenemos cobertura registrada en {nombre}.")


def _validar(destino: MunicipioCobertura, s: SolicitudCotizacion, peso: Decimal) -> None:
    medidas = [a_decimal(x) for x in (s.alto_cm, s.ancho_cm, s.largo_cm, s.peso_kg, s.valor_declarado)]
    if min(medidas) <= 0 or s.unidades < 1:
        raise ErrorDominio(
            "DATOS_INVALIDOS",
            "Las dimensiones, el peso, el valor declarado y las unidades deben ser mayores que cero.",
        )
    if s.modalidad not in MODALIDADES:
        raise ErrorDominio("MODALIDAD_INVALIDA", "La modalidad debe ser paquetería o carga.")
    if s.modalidad == "paqueteria" and peso > LIMITE_PAQUETERIA_KG:
        raise ErrorDominio(
            "PAQUETERIA_EXCEDE_50_KG",
            f"La paquetería exprés admite hasta {LIMITE_PAQUETERIA_KG} kg. "
            f"Para {peso} kg te sugerimos la modalidad de carga.",
        )
    if peso / s.unidades > a_decimal(destino.peso_maximo_paquete_kg):
        raise ErrorDominio(
            "PESO_EXCEDE_MAXIMO_DESTINO",
            f"{destino.municipio} recibe paquetes de hasta {destino.peso_maximo_paquete_kg} kg por unidad.",
        )
    if s.cadena_frio and not destino.servicio_refrigerado_disponible:
        raise ErrorDominio(
            "REFRIGERADO_NO_DISPONIBLE", f"No tenemos servicio de cadena de frío hacia {destino.municipio}."
        )


def cotizar(trayecto: Trayecto, destino: MunicipioCobertura, solicitud: SolicitudCotizacion) -> Cotizacion:
    s = solicitud
    peso = a_decimal(s.peso_kg)
    _validar(destino, s, peso)

    volumen_cm3 = a_decimal(s.alto_cm) * a_decimal(s.ancho_cm) * a_decimal(s.largo_cm)
    vol = volumen_cm3 / trayecto.factor_divisitivas_volumetrico
    por_real = peso >= vol
    facturable = peso if por_real else vol
    tarifa = trayecto.tarifa_base_kg_real_cop if por_real else trayecto.tarifa_base_kg_volumetrico_cop
    flete_base = facturable * tarifa
    flete = max(flete_base, trayecto.flete_minimo_cop)
    recargo_frio = flete_base * trayecto.recargo_cadena_frio_pct / 100 if s.cadena_frio else Decimal(0)
    recargo_mp = trayecto.recargo_mercancia_peligrosa_cop if s.mercancia_peligrosa else Decimal(0)
    seguro = max(a_decimal(s.valor_declarado) * trayecto.porcentaje_seguro / 100, trayecto.seguro_minimo_cop)
    total = flete + recargo_frio + recargo_mp + seguro

    observaciones = [trayecto.observaciones_ruta]
    if destino.restricciones_operativas:
        observaciones.append(f"Restricciones en {destino.municipio}: {destino.restricciones_operativas}")
    # D-05: el directorio (nivel municipio) manda sobre la observación de la ruta.
    ruta_same_day = "same day" in normalizar_para_busqueda(trayecto.observaciones_ruta)
    if ruta_same_day and not destino.servicio_same_day_disponible:
        observaciones.append(f"El servicio Same Day no está disponible en {destino.municipio}.")

    return Cotizacion(
        codigo_trayecto=trayecto.codigo_trayecto,
        peso_real=peso,
        peso_volumetrico=vol,
        peso_facturable=facturable,
        base_cobro="real" if por_real else "volumetrico",
        tarifa_aplicada=tarifa,
        flete_base=flete_base,
        flete_minimo_aplicado=flete_base < trayecto.flete_minimo_cop,
        flete=flete,
        recargo_frio=recargo_frio,
        recargo_mp=recargo_mp,
        seguro=seguro,
        total_sin_redondeo=total,
        total=redondear_pesos(total),
        horas_estimadas=trayecto.tiempo_entrega_estimado_horas,
        observaciones=observaciones,
    )
