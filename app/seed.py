"""Carga idempotente de datos de referencia, dataset del reto, usuarios demo y corpus RAG.

Uso: `uv run python -m app.seed [--sin-rag] [--historial-meses N]`. Se puede ejecutar varias veces.
"""

import argparse
import asyncio
import csv
import json
import logging
import re
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import holidays
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.security import hash_password
from app.db import SessionLocal
from app.domain.cotizador import Trayecto as TrayectoDominio
from app.domain.estados import _ESTADOS, traducir_estado
from app.domain.mercancias import CATALOGO, SEVERIDAD
from app.domain.pii import enmascarar_documento
from app.domain.sanitizar import normalizar_para_busqueda
from app.models import (
    ArticuloProhibido,
    ClaseOnu,
    CriterioEscalamiento,
    Cuenta,
    Departamento,
    Envio,
    EstadoEnvio,
    EventoEnvio,
    Festivo,
    Hub,
    Municipio,
    PruebaEntrega,
    Trayecto,
    Usuario,
)
from app.models.base import OrigenDato, Rol, TipoCobertura, TipoCuenta, TipoServicio

log = logging.getLogger("app.seed")

COBERTURA = {
    "urbana principal": TipoCobertura.URBANA_PRINCIPAL,
    "frontera": TipoCobertura.FRONTERA,
    "trayecto especial": TipoCobertura.TRAYECTO_ESPECIAL,
    "zona zomac": TipoCobertura.ZOMAC,  # D-07
    "zona zomac dificil acceso": TipoCobertura.ZOMAC,
}

# Nombres de clases y subclases tal como los titula el manual DOC-OPS-2026-03 §2.
NOMBRES_CLASE = {
    "1": "Explosivos",
    "2.1": "Gas inflamable",
    "2.2": "Gas no inflamable y no tóxico",
    "2.3": "Gas tóxico por inhalación",
    "3": "Líquidos inflamables",
    "4.1": "Sólidos inflamables",
    "4.2": "Sustancias espontáneamente combustibles",
    "4.3": "Sustancias que en contacto con el agua emiten gases inflamables",
    "5.1": "Sustancias comburentes",
    "5.2": "Peróxidos orgánicos",
    "6.1": "Sustancias tóxicas",
    "6.2": "Sustancias infecciosas",
    "7": "Material radiactivo",
    "8": "Sustancias corrosivas",
    "9": "Sustancias y objetos peligrosos diversos",
}

# D-13: orden de prioridad de los criterios (1 = más urgente).
PRIORIDAD_CRITERIO = {"CRIT-005": 1, "CRIT-002": 2, "CRIT-003": 3, "CRIT-004": 4, "CRIT-001": 5}

# D-11: el dataset no trae tipo de cuenta; mock CRM con cuentas de prueba asociadas por NIT.
CRM = {
    "900.123.456-7": (TipoCuenta.CORPORATIVO_GOLD, 850),  # Laboratorios PharmaSur: cuenta VIP
    "890.987.654-3": (TipoCuenta.CORPORATIVO, 320),
}


def _tipo_servicio(texto: str) -> tuple[TipoServicio, str | None]:
    t = normalizar_para_busqueda(texto)
    if "peligrosa" in t:
        clase = re.search(r"clase (\d(?:\.\d)?)", t)
        return TipoServicio.MERCANCIA_PELIGROSA, clase.group(1) if clase else None
    if "frio" in t:
        return TipoServicio.CADENA_FRIO, None
    if "semimasiva" in t:
        return TipoServicio.CARGA_SEMIMASIVA, None
    if "masiva" in t:
        return TipoServicio.CARGA_MASIVA, None
    return TipoServicio.PAQUETERIA, None


async def _upsert(s: AsyncSession, modelo, filas: list[dict], claves: list[str], actualizar: bool = True) -> None:
    if not filas:
        return
    stmt = insert(modelo).values(filas)
    if actualizar:
        cols = {c: stmt.excluded[c] for c in filas[0] if c not in claves}
        stmt = stmt.on_conflict_do_update(index_elements=claves, set_=cols) if cols else stmt.on_conflict_do_nothing()
    else:
        stmt = stmt.on_conflict_do_nothing(index_elements=claves)
    await s.execute(stmt)


async def cargar_catalogos(s: AsyncSession, datos: Path) -> dict[str, str]:
    """Geografía, hubs, municipios, trayectos, estados, festivos, mercancías y criterios. Devuelve nombre→DANE."""
    directorio = json.loads((datos / "directorio_cobertura_y_tiempos.json").read_text(encoding="utf-8"))

    deps = {m["codigo_dane"][:2]: m["departamento"] for m in directorio}
    await _upsert(s, Departamento, [{"codigo": c, "nombre": n} for c, n in deps.items()], ["codigo"])
    await _upsert(s, Hub, [{"nombre": n} for n in sorted({m["hub_operativo_asignado"] for m in directorio})],
                  ["nombre"], actualizar=False)  # fmt: skip
    hubs = dict((await s.execute(select(Hub.nombre, Hub.id))).all())

    await _upsert(
        s,
        Municipio,
        [
            {
                "codigo_dane": m["codigo_dane"],
                "nombre": m["municipio"],
                "departamento_codigo": m["codigo_dane"][:2],
                "tipo_cobertura": COBERTURA[normalizar_para_busqueda(m["tipo_cobertura"])],
                "tiempo_entrega_estandar_horas": m["tiempo_entrega_estandar_horas"],
                "servicio_same_day": m["servicio_same_day_disponible"],
                "servicio_refrigerado": m["servicio_refrigerado_disponible"],
                "peso_maximo_paquete_kg": Decimal(str(m["peso_maximo_paquete_kg"])),
                "volumen_maximo_m3": Decimal(str(m["volumen_maximo_m3"])),
                "hub_id": hubs[m["hub_operativo_asignado"]],
                "frecuencia_despacho": m["frecuencia_despacho"],
                "restricciones_operativas": m["restricciones_operativas"],
            }
            for m in directorio
        ],
        ["codigo_dane"],
    )
    dane = {normalizar_para_busqueda(m["municipio"]): m["codigo_dane"] for m in directorio}

    with (datos / "matriz_tarifas_y_fletes.csv").open(encoding="utf-8-sig") as f:
        filas = list(csv.DictReader(f))
    trayectos = []
    for fila in filas:
        t = TrayectoDominio.desde_fila(fila)
        trayectos.append(
            {
                "codigo": t.codigo_trayecto,
                "origen_dane": dane[normalizar_para_busqueda(fila["ciudad_origen"])],
                "destino_dane": dane[normalizar_para_busqueda(fila["ciudad_destino"])],
                "tipo_cobertura": COBERTURA[normalizar_para_busqueda(fila["tipo_cobertura"])],
                "tarifa_kg_real": t.tarifa_base_kg_real_cop,
                "tarifa_kg_volumetrico": t.tarifa_base_kg_volumetrico_cop,
                "factor_volumetrico": int(t.factor_divisitivas_volumetrico),
                "flete_minimo": t.flete_minimo_cop,
                "porcentaje_seguro": t.porcentaje_seguro,
                "seguro_minimo": t.seguro_minimo_cop,
                "recargo_cadena_frio_pct": t.recargo_cadena_frio_pct,
                "recargo_mercancia_peligrosa": t.recargo_mercancia_peligrosa_cop,
                "tiempo_entrega_horas": t.tiempo_entrega_estimado_horas,
                "observaciones": t.observaciones_ruta,
            }
        )
    await _upsert(s, Trayecto, trayectos, ["codigo"])

    await _upsert(
        s,
        EstadoEnvio,
        [
            {
                "codigo": c,
                "descripcion_cliente": (e := traducir_estado(c)).texto,
                "orden": e.orden or 0,
                "es_final": e.es_final,
            }
            for c in _ESTADOS
        ],
        ["codigo"],
    )

    fest = holidays.Colombia(years=range(2025, 2028), language="es")  # type: ignore[call-arg]
    await _upsert(s, Festivo, [{"fecha": d, "nombre": n} for d, n in sorted(fest.items())], ["fecha"])

    por_clase: dict[str, list] = {}
    for e in CATALOGO:
        if e.clase_onu:
            por_clase.setdefault(e.clase_onu, []).append(e)
    await _upsert(
        s,
        ClaseOnu,
        [
            {
                "codigo": c,
                "nombre": NOMBRES_CLASE[c],
                # La política de la clase es la más restrictiva de sus entradas del catálogo.
                "politica": max((e.veredicto for e in es), key=SEVERIDAD.__getitem__),
                "condiciones": " ".join(dict.fromkeys(e.motivo for e in es)),
            }
            for c, es in sorted(por_clase.items())
        ],
        ["codigo"],
    )
    await _upsert(
        s,
        ArticuloProhibido,
        [
            {"categoria": e.nombre, "palabras_clave": list(e.sinonimos), "fundamento": f"{e.fuente}: {e.motivo}"}
            for e in CATALOGO
            if e.veredicto == "prohibido"
        ],
        ["categoria"],
    )

    reglas = json.loads((datos / "reglas_escalacion_humana.json").read_text(encoding="utf-8"))
    await _upsert(
        s,
        CriterioEscalamiento,
        [
            {
                "id": c["id_criterio"],
                "categoria": c["categoria"],
                "descripcion": c["descripcion"],
                "regla_evaluacion": c.get("regla_evaluacion"),
                "palabras_clave": c.get("keywords_disparadoras"),
                "accion": c["accion"],
                "mensaje_cliente": c["mensaje_cliente"],
                "prioridad": PRIORIDAD_CRITERIO[c["id_criterio"]],
            }
            for c in reglas["criterios_escalacion"]
        ],
        ["id"],
    )
    return dane


async def cargar_dataset(s: AsyncSession, datos: Path, dane: dict[str, str]) -> int:
    guias = json.loads((datos / "dataset_guias_simuladas_tms.json").read_text(encoding="utf-8"))
    cuentas = [
        {
            "nit": g["remitente"]["nit"],
            "razon_social": g["remitente"]["nombre_empresa"],
            "tipo_cuenta": CRM.get(g["remitente"]["nit"], (TipoCuenta.ESTANDAR, 40))[0],
            "envios_mensuales": CRM.get(g["remitente"]["nit"], (TipoCuenta.ESTANDAR, 40))[1],
        }
        for g in guias
    ]
    await _upsert(s, Cuenta, cuentas, ["nit"])
    ids_cuenta = dict((await s.execute(select(Cuenta.nit, Cuenta.id))).all())
    trayectos = {(t.origen_dane, t.destino_dane): t.codigo for t in (await s.scalars(select(Trayecto))).all()}

    for g in guias:
        c = g["especificaciones_carga"]
        origen = dane[normalizar_para_busqueda(g["remitente"]["ciudad_origen"])]
        destino = dane[normalizar_para_busqueda(g["destinatario"]["ciudad_destino"])]
        servicio, clase = _tipo_servicio(c["tipo_servicio"])
        gps = g.get("ubicacion_gps_actual") or {}
        fila = {
            "numero_guia": g["numero_guia"],
            "cuenta_id": ids_cuenta[g["remitente"]["nit"]],
            "trayecto_codigo": trayectos.get((origen, destino)),  # None en 2 guías (D-04)
            "origen_dane": origen,
            "destino_dane": destino,
            "direccion_recogida": g["remitente"].get("direccion_recogida"),
            "destinatario_nombre": g["destinatario"].get("nombre_contacto"),
            "destinatario_empresa": g["destinatario"].get("empresa_destino"),
            "direccion_entrega": g["destinatario"].get("direccion_entrega"),
            "tipo_servicio": servicio,
            "descripcion_servicio": c["tipo_servicio"],
            "peso_kg": Decimal(str(c["peso_kg"])),
            "alto_cm": Decimal(str(c["dimensiones_cm"]["alto"])),
            "ancho_cm": Decimal(str(c["dimensiones_cm"]["ancho"])),
            "largo_cm": Decimal(str(c["dimensiones_cm"]["largo"])),
            "unidades": c.get("unidades", 1),
            "valor_declarado": Decimal(str(c["declarado_cop"])),
            "requiere_refrigeracion": c["requiere_refrigeracion"],
            "mercancia_peligrosa": c["mercancia_peligrosa"],
            "clase_onu": clase if c["mercancia_peligrosa"] else None,
            "estado_actual": g["estado_actual"],
            "latitud": Decimal(str(gps["latitud"])) if gps.get("latitud") is not None else None,
            "longitud": Decimal(str(gps["longitud"])) if gps.get("longitud") is not None else None,
            "referencia_ubicacion": gps.get("referencia"),
            "fecha_despacho": datetime.fromisoformat(g["fecha_despacho"]),
            "fecha_estimada_entrega": datetime.fromisoformat(g["fecha_estimada_entrega"]),
            "fecha_entrega_real": datetime.fromisoformat(g["prueba_entrega"]["fecha_hora_entrega"])
            if g.get("prueba_entrega")
            else None,
            "origen_dato": OrigenDato.DATASET,
        }
        await _upsert(s, Envio, [fila], ["numero_guia"])
        await _upsert(
            s,
            EventoEnvio,
            [
                {
                    "numero_guia": g["numero_guia"],
                    "ocurrido_en": datetime.fromisoformat(h["timestamp"]),
                    "estado": h["estado"],
                    "ubicacion": h["hub_ubicacion"],
                    "descripcion": h["descripcion"],
                }
                for h in g["historial_trazabilidad"]
            ],
            ["numero_guia", "ocurrido_en", "estado"],
            actualizar=False,
        )
        if p := g.get("prueba_entrega"):
            await _upsert(
                s,
                PruebaEntrega,
                [
                    {
                        "numero_guia": g["numero_guia"],
                        "recibido_por": p["recibido_por"],
                        "documento_enmascarado": enmascarar_documento(p["documento_identidad"]),
                        "fecha_hora_entrega": datetime.fromisoformat(p["fecha_hora_entrega"]),
                        "firma_url": p.get("firma_digital_url"),
                        "observaciones": p.get("observaciones_recibido"),
                    }
                ],
                ["numero_guia"],
            )
    return len(guias)


async def cargar_usuarios(s: AsyncSession) -> int:
    cfg = get_settings()
    nits = dict((await s.execute(select(Cuenta.nit, Cuenta.id))).all())
    demo = [
        (cfg.demo_admin_email, cfg.demo_admin_password, "Administración TransLogix", Rol.ADMIN, None),
        (cfg.demo_asesor_email, cfg.demo_asesor_password, "Asesora de servicio", Rol.ASESOR, None),
        # El cliente demo es dueño de la cuenta remitente de TLX-551904-CO (cuenta estándar).
        (cfg.demo_cliente_email, cfg.demo_cliente_password, "Cliente demo", Rol.CLIENTE, None),
        (cfg.demo_vip_email, cfg.demo_vip_password, "Compras PharmaSur", Rol.CLIENTE, nits.get("900.123.456-7")),
    ]
    guia_cliente = await s.get(Envio, "TLX-551904-CO")
    filas = []
    for email, pwd, nombre, rol, cuenta in demo:
        if not email or not pwd:
            continue
        if rol is Rol.CLIENTE and cuenta is None and guia_cliente:
            cuenta = guia_cliente.cuenta_id
        filas.append(
            {
                "email": email,
                "nombre": nombre,
                "password_hash": hash_password(pwd.get_secret_value()),
                "rol": rol,
                "cuenta_id": cuenta,
            }
        )
    await _upsert(s, Usuario, filas, ["email"])
    return len(filas)


async def main(con_rag: bool = True, historial_meses: int = 0) -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    datos = get_settings().datos_dir
    async with SessionLocal() as s, s.begin():
        dane = await cargar_catalogos(s, datos)
        n_guias = await cargar_dataset(s, datos, dane)
        n_usuarios = await cargar_usuarios(s)
    log.info("catálogos y dataset: %s municipios, %s guías, %s usuarios demo", len(dane), n_guias, n_usuarios)
    if historial_meses:
        from app.ml.servicio import sembrar_historial

        async with SessionLocal() as s:
            log.info("historial simulado: %s", await sembrar_historial(s, historial_meses))
    if con_rag:
        from app.ai import rag

        async with SessionLocal() as s:
            log.info("corpus RAG: %s", await rag.ingestar_corpus(s, datos))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--sin-rag", action="store_true", help="No ingerir el corpus RAG (requiere Ollama)")
    p.add_argument("--historial-meses", type=int, default=0, help="Meses de historial simulado para ML (0 = no)")
    a = p.parse_args()
    asyncio.run(main(con_rag=not a.sin_rag, historial_meses=a.historial_meses))
