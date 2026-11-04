"""Chat administrativo: intenciones en lista blanca → consultas SQL parametrizadas fijas → artifacts.

Sin texto-a-SQL: el LLM solo clasifica la pregunta y resume los datos que devuelve el código (sin inventar cifras).
"""

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.herramientas_cliente import nuevo_id
from app.ai.llm import ClienteLLM
from app.ai.prompts import SISTEMA_ROUTER
from app.domain.pii import enmascarar_texto
from app.domain.sanitizar import extraer_guias, normalizar_para_busqueda
from app.schemas import artifacts as A

INTENCIONES_ADMIN = (
    "kpis",
    "escalamientos",
    "envios_novedad",
    "envios_por_estado",
    "pqrs_resumen",
    "rendimiento_ia",
    "riesgo_retraso",
    "pronostico_demanda",
    "estado_modelos",
    "desconocida",
)

_REGLAS = (
    ("riesgo_retraso", r"riesgo|probabilidad de retraso|se va a retrasar|retrasar"),
    ("pronostico_demanda", r"pronostic|demanda|proyecc|cuantos despachos|prediccion de despachos"),
    ("estado_modelos", r"modelo|entrenamiento|reentren|champion|metricas del modelo"),
    ("escalamientos", r"escalad|escalamiento|cola|asesor"),
    ("envios_novedad", r"retenid|novedad|siniestro|problema|alerta"),
    ("envios_por_estado", r"envios por estado|estado de los envios|cuantos envios"),
    ("pqrs_resumen", r"pqrs|reclam|queja|peticion|indemniz"),
    ("rendimiento_ia", r"latencia|rendimiento|velocidad|tiempo de respuesta|intencion"),
    ("kpis", r"kpi|resumen|indicador|como vamos|metricas|interacciones|satisfaccion|csat"),
)


@dataclass
class ResultadoAdmin:
    artifacts: list[BaseModel] = field(default_factory=list)
    datos: str = ""  # texto con las cifras exactas para que el LLM resuma
    texto: str | None = None  # respuesta determinista (sin LLM)


async def clasificar(llm: ClienteLLM, pregunta: str) -> str:
    t = normalizar_para_busqueda(pregunta)
    for intencion, patron in _REGLAS:
        if re.search(patron, t):
            return intencion
    datos = await llm.extraer_json(
        [
            {"role": "system", "content": SISTEMA_ROUTER},
            {
                "role": "user",
                "content": f"Clasifica la pregunta de un administrador de logística. Opciones: "
                f"{', '.join(INTENCIONES_ADMIN)}.\n\nPregunta: {pregunta}",
            },
        ],
        {
            "type": "object",
            "properties": {"intencion": {"type": "string", "enum": list(INTENCIONES_ADMIN)}},
            "required": ["intencion"],
        },
        max_tokens=20,
    )
    return datos.get("intencion") if datos.get("intencion") in INTENCIONES_ADMIN else "desconocida"


def _kpi(id_, etiqueta, valor, formato="numero", unidad=None) -> A.Kpi:
    return A.Kpi(id=id_, etiqueta=etiqueta, valor=Decimal(str(round(valor or 0, 2))), formato=formato, unidad=unidad)


async def kpis(s: AsyncSession, dias: int = 7) -> ResultadoAdmin:
    desde = datetime.now(UTC) - timedelta(days=dias)
    r = (
        await s.execute(
            text("""
        WITH ses AS (SELECT id FROM sesiones_chat WHERE creado_en >= :d AND canal <> 'admin'),
             esc AS (SELECT DISTINCT sesion_id FROM escalamientos WHERE sesion_id IN (SELECT id FROM ses))
        SELECT
          (SELECT count(*) FROM ses)                                                   AS sesiones,
          (SELECT count(*) FROM mensajes WHERE rol = 'usuario' AND creado_en >= :d)    AS interacciones,
          (SELECT count(*) FROM esc)                                                   AS escaladas,
          (SELECT avg(puntaje) FROM calificaciones WHERE creado_en >= :d)              AS csat,
          (SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY (latencias_ms->>'total')::float)
             FROM mensajes WHERE rol = 'asistente' AND creado_en >= :d)                AS p50,
          (SELECT percentile_cont(0.95) WITHIN GROUP (ORDER BY (latencias_ms->>'total')::float)
             FROM mensajes WHERE rol = 'asistente' AND creado_en >= :d)                AS p95,
          (SELECT avg(confianza) FROM mensajes WHERE rol = 'asistente' AND creado_en >= :d) AS confianza
    """),
            {"d": desde},
        )
    ).one()
    automatizado = 100 * (1 - r.escaladas / r.sesiones) if r.sesiones else 0
    tarjetas = [
        _kpi("interacciones", "Mensajes de clientes", r.interacciones),
        _kpi("sesiones", "Conversaciones", r.sesiones),
        _kpi("automatizado", "Resueltas sin humano", automatizado, "porcentaje", "%"),
        _kpi("csat", "Satisfacción (CSAT 1-5)", r.csat or 0),
        _kpi("p50", "Latencia p50", r.p50 or 0, "duracion_ms", "ms"),
        _kpi("p95", "Latencia p95", r.p95 or 0, "duracion_ms", "ms"),
        _kpi("confianza", "Confianza media IA", float(r.confianza or 0), "numero"),
    ]
    hoy = datetime.now(UTC).date()
    art = A.TarjetasKpi(
        id=nuevo_id("kpi"),
        titulo=f"Últimos {dias} días",
        periodo={"desde": hoy - timedelta(days=dias), "hasta": hoy},
        tarjetas=tarjetas,
    )
    datos = "; ".join(f"{k.etiqueta}: {k.valor}{(' ' + k.unidad) if k.unidad else ''}" for k in tarjetas)
    return ResultadoAdmin([art], datos)


async def escalamientos(s: AsyncSession) -> ResultadoAdmin:
    filas = (
        await s.execute(
            text("""SELECT e.id, e.sesion_id, e.criterio_id, e.prioridad, e.estado, e.creado_en, e.resumen_ia,
                       e.payload->>'numero_guia_consultada' AS guia
                FROM escalamientos e WHERE e.estado IN ('pendiente', 'tomado')
                ORDER BY e.prioridad, e.creado_en LIMIT 50""")
        )
    ).all()
    ahora = datetime.now(UTC)
    nivel = {1: "alta", 2: "alta", 3: "media", 4: "media", 5: "normal"}
    items = [
        A.ItemCola(
            escalamiento_id=str(f.id),
            sesion_id=str(f.sesion_id),
            criterio=f.criterio_id,
            prioridad=nivel[f.prioridad],
            estado=f.estado,
            creado=f.creado_en,
            espera_s=int((ahora - f.creado_en).total_seconds()),
            resumen=f.resumen_ia or "Resumen en preparación",
            guia=f.guia if f.guia and extraer_guias(f.guia) else None,
        )
        for f in filas
    ]
    pend = sum(1 for f in filas if f.estado == "pendiente")
    return ResultadoAdmin(
        [A.ColaEscalamientos(id=nuevo_id("col"), titulo="Escalamientos abiertos", items=items)],
        f"Escalamientos abiertos: {len(filas)} ({pend} pendientes, {len(filas) - pend} tomados).",
    )


def _tabla(titulo: str, columnas: list[tuple[str, str, str]], filas: list[dict]) -> A.TablaDatos:
    return A.TablaDatos(
        id=nuevo_id("tab"),
        titulo=titulo,
        columnas=[A.Columna(clave=c, etiqueta=e, tipo=t) for c, e, t in columnas],
        filas=filas,
        paginacion=A.Paginacion(pagina=1, tamano=max(len(filas), 1), total=len(filas)),
    )


async def envios_novedad(s: AsyncSession) -> ResultadoAdmin:
    filas = (
        await s.execute(
            text("""SELECT e.numero_guia, e.estado_actual, e.descripcion_servicio, o.nombre AS origen, d.nombre AS destino,
                       e.valor_declarado, ev.descripcion
                FROM envios e
                JOIN municipios o ON o.codigo_dane = e.origen_dane JOIN municipios d ON d.codigo_dane = e.destino_dane
                LEFT JOIN LATERAL (SELECT descripcion FROM eventos_envio WHERE numero_guia = e.numero_guia
                                   ORDER BY ocurrido_en DESC LIMIT 1) ev ON true
                WHERE e.estado_actual IN ('RETENIDO_NOVEDAD', 'EN_INVESTIGACION_SINIESTRO')
                ORDER BY e.valor_declarado DESC LIMIT 50""")
        )
    ).all()
    datos = [
        {
            "guia": f.numero_guia,
            "estado": f.estado_actual,
            "ruta": f"{f.origen} → {f.destino}",
            "servicio": f.descripcion_servicio,
            "valor": str(int(f.valor_declarado)),
            "novedad": enmascarar_texto(f.descripcion or "")[:200],
        }
        for f in filas
    ]
    tabla = _tabla(
        "Envíos con novedad",
        [
            ("guia", "Guía", "texto"),
            ("estado", "Estado", "estado"),
            ("ruta", "Ruta", "texto"),
            ("servicio", "Servicio", "texto"),
            ("valor", "Valor declarado", "moneda"),
            ("novedad", "Última novedad", "texto"),
        ],
        datos,
    )
    resumen = "; ".join(f"{d['guia']} {d['estado']} {d['ruta']} valor {d['valor']}: {d['novedad']}" for d in datos[:5])
    return ResultadoAdmin([tabla], f"Envíos con novedad: {len(datos)}. {resumen}")


async def envios_por_estado(s: AsyncSession) -> ResultadoAdmin:
    filas = (
        await s.execute(
            text("""SELECT estado_actual, origen_dato, count(*) AS n FROM envios
                GROUP BY 1, 2 ORDER BY n DESC""")
        )
    ).all()
    datos = [{"estado": f.estado_actual, "origen": f.origen_dato, "envios": f.n} for f in filas]
    tabla = _tabla(
        "Envíos por estado",
        [("estado", "Estado", "estado"), ("origen", "Origen del dato", "texto"), ("envios", "Envíos", "numero")],
        datos,
    )
    return ResultadoAdmin([tabla], "; ".join(f"{d['estado']} ({d['origen']}): {d['envios']}" for d in datos))


async def pqrs_resumen(s: AsyncSession) -> ResultadoAdmin:
    filas = (
        await s.execute(
            text("""SELECT tipo, estado, count(*) AS n, coalesce(sum(valor_reclamado), 0) AS valor,
                       count(*) FILTER (WHERE fecha_limite_respuesta < current_date AND estado NOT IN ('cerrado', 'aprobado', 'rechazado')) AS vencidos
                FROM pqrs_tickets GROUP BY 1, 2 ORDER BY 1, 2""")
        )
    ).all()
    datos = [
        {"tipo": f.tipo, "estado": f.estado, "tickets": f.n, "valor": str(int(f.valor)), "vencidos": f.vencidos}
        for f in filas
    ]
    tabla = _tabla(
        "PQRS por tipo y estado",
        [
            ("tipo", "Tipo", "texto"),
            ("estado", "Estado", "estado"),
            ("tickets", "Tickets", "numero"),
            ("valor", "Valor reclamado", "moneda"),
            ("vencidos", "Vencidos", "numero"),
        ],
        datos,
    )
    total = sum(d["tickets"] for d in datos)
    return ResultadoAdmin(
        [tabla],
        f"PQRS totales: {total}. "
        + "; ".join(f"{d['tipo']}/{d['estado']}: {d['tickets']} (vencidos {d['vencidos']})" for d in datos),
    )


async def rendimiento_ia(s: AsyncSession, dias: int = 7) -> ResultadoAdmin:
    filas = (
        await s.execute(
            text("""SELECT intencion, count(*) AS n,
                       percentile_cont(0.5) WITHIN GROUP (ORDER BY (latencias_ms->>'total')::float) AS p50,
                       percentile_cont(0.95) WITHIN GROUP (ORDER BY (latencias_ms->>'total')::float) AS p95,
                       avg(confianza) AS conf
                FROM mensajes WHERE rol = 'asistente' AND creado_en >= :d AND intencion IS NOT NULL
                GROUP BY 1 ORDER BY n DESC"""),
            {"d": datetime.now(UTC) - timedelta(days=dias)},
        )
    ).all()
    grafico = A.Grafico(
        id=nuevo_id("gra"),
        titulo="Latencia por intención (ms)",
        tipo_grafico="barras",
        eje_x=A.Eje(etiqueta="Intención", tipo="categoria"),
        eje_y=A.Eje(etiqueta="Latencia", tipo="numero", unidad="ms"),
        series=[
            A.Serie(nombre="p50", puntos=[A.Punto(x=f.intencion, y=Decimal(str(round(f.p50 or 0, 1)))) for f in filas]),
            A.Serie(
                nombre="p95",
                puntos=[A.Punto(x=f.intencion, y=Decimal(str(round(f.p95 or 0, 1)))) for f in filas],
                estilo="punteada",
            ),
        ],
    )
    datos = "; ".join(
        f"{f.intencion}: {f.n} turnos, p50 {round(f.p50 or 0)} ms, p95 {round(f.p95 or 0)} ms" for f in filas
    )
    return ResultadoAdmin([grafico], datos or "Sin turnos registrados en el periodo.")


async def ml(s: AsyncSession, intencion: str, pregunta: str) -> ResultadoAdmin:
    """Predicciones: delega en app.ml.servicio (modelos que se autoentrenan con datos simulados etiquetados)."""
    from app.core.errors import ApiError
    from app.ml import servicio

    try:
        if intencion == "riesgo_retraso":
            guias = extraer_guias(pregunta)
            if not guias:
                return ResultadoAdmin(
                    texto="Indica la guía (formato TLX-XXXXXX-CO) para calcular su riesgo de retraso."
                )
            art = servicio.artifact_prediccion(await servicio.predecir_riesgo(s, guias[0]))
        elif intencion == "pronostico_demanda":
            art = servicio.artifact_pronostico(await servicio.pronosticar_demanda(s, _origen(pregunta)))
        else:
            historial = [m for m in (await servicio.listar_modelos(s))["historial"] if m["estado"] != "rechazado"]
            if not historial:
                return ResultadoAdmin(texto="Aún no hay modelos entrenados. Entrénalos con POST /admin/ml/entrenar.")
            art = servicio.artifact_metricas(historial)
    except ApiError as e:  # modelo sin entrenar, guía u origen inexistente: se explica en el chat
        return ResultadoAdmin(texto=e.detail)
    return ResultadoAdmin([art], art.model_dump_json(exclude={"id", "acciones"})[:1500])


def _origen(pregunta: str) -> str:
    # ponytail: "de|para|en <Ciudad>" al final de la pregunta; sin ciudad, Bogotá (el origen con más despachos).
    m = re.search(r"\b(?:de|desde|para|en)\s+([A-ZÁÉÍÓÚÑ][\wáéíóúñ. ]+?)\s*\??$", pregunta)
    return m.group(1) if m and m.group(1).lower() != "demanda" else "Bogotá D.C."


async def ejecutar(s: AsyncSession, intencion: str, pregunta: str) -> ResultadoAdmin:
    match intencion:
        case "kpis":
            return await kpis(s)
        case "escalamientos":
            return await escalamientos(s)
        case "envios_novedad":
            return await envios_novedad(s)
        case "envios_por_estado":
            return await envios_por_estado(s)
        case "pqrs_resumen":
            return await pqrs_resumen(s)
        case "rendimiento_ia":
            return await rendimiento_ia(s)
        case "riesgo_retraso" | "pronostico_demanda" | "estado_modelos":
            return await ml(s, intencion, pregunta)
    return ResultadoAdmin(
        texto="Puedo mostrarte: indicadores (KPIs), escalamientos abiertos, envíos con novedad, envíos por estado, "
        "resumen de PQRS, rendimiento de la IA, riesgo de retraso de una guía, pronóstico de demanda y estado de los modelos."
    )
