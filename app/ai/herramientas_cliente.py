"""Herramientas deterministas del chat de clientes: cada intención produce artifacts y hechos verificables.

El LLM nunca calcula: estas funciones consultan la BD y el dominio; el orquestador decide si además redacta con el LLM.
"""

import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from functools import lru_cache
from zoneinfo import ZoneInfo

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.rag import ResultadoRag
from app.config import get_settings
from app.core.errors import ApiError
from app.core.security import Actor
from app.domain import ErrorDominio
from app.domain.cotizador import LIMITE_PAQUETERIA_KG
from app.domain.mercancias import EvaluacionProducto, evaluar_producto
from app.domain.sanitizar import extraer_envio, normalizar_para_busqueda
from app.models import Envio, Municipio, SesionChat, Trayecto
from app.models.base import Rol, TipoPqrs
from app.schemas import artifacts as A
from app.schemas.cotizacion import CotizacionIn, CotizacionOut
from app.schemas.pqrs import TicketIn
from app.servicios import pqrs as svc_pqrs
from app.servicios.cotizaciones import cotizar_y_guardar
from app.servicios.envios import tracking
from app.servicios.reglas import reglas_escalamiento

ZONA = ZoneInfo("America/Bogota")


@dataclass
class Resultado:
    """Salida de una herramienta. `texto` = respuesta determinista; `pregunta_llm` = pedir redacción al LLM."""

    artifacts: list[BaseModel] = field(default_factory=list)
    texto: str | None = None
    pregunta_llm: str | None = None
    hechos: str = ""
    rag_tipos: list[str] | None = None
    veredicto: str | None = None
    plantilla_segura: str | None = None
    confianza: float = 0.95
    escalamiento: dict = field(default_factory=dict)  # campos de ContextoTurno (flujo, valor_declarado, ...)
    forzar_criterio: str | None = None
    contexto: dict = field(default_factory=dict)  # cambios a sesiones_chat.contexto
    guia: str | None = None


# ----------------------------------------------------------------------------- utilidades de presentación


def pesos(v: Decimal | int | float) -> str:
    return "$" + f"{int(Decimal(v).quantize(Decimal(1))):,}".replace(",", ".")


def fecha_local(d: datetime) -> str:
    return d.astimezone(ZONA).strftime("%d/%m/%Y %I:%M %p").replace("AM", "a. m.").replace("PM", "p. m.")


def nuevo_id(prefijo: str) -> str:
    return f"{prefijo}_{uuid.uuid4().hex[:12]}"


def endpoint_mensajes(sesion: SesionChat) -> str:
    return f"/api/v1/chat/sesiones/{sesion.id}/mensajes"


def accion_enviar(sesion: SesionChat, artifact_id: str, etiqueta: str = "Enviar") -> A.Accion:
    return A.Accion(
        id="enviar",
        etiqueta=etiqueta,
        tipo="submit",
        metodo="POST",
        endpoint=endpoint_mensajes(sesion),
        payload={"tipo": "artifact_submit", "artifact_id": artifact_id},
        estilo="primario",
    )


def respuestas_rapidas(*pares: tuple[str, str]) -> A.RespuestasRapidas:
    return A.RespuestasRapidas(
        id=nuevo_id("rr"),
        acciones=[
            A.Accion(id=f"rr{i}", etiqueta=e, tipo="mensaje", mensaje=m, estilo="secundario")
            for i, (e, m) in enumerate(pares)
        ],
    )


MENU = (
    ("Rastrear un envío", "Quiero rastrear mi envío"),
    ("Cotizar", "Quiero cotizar un envío"),
    ("¿Puedo enviar…?", "¿Qué mercancías están prohibidas?"),
    ("Reclamar por daño o pérdida", "Quiero radicar un reclamo"),
    ("Hablar con un asesor", "Quiero hablar con un asesor"),
)


def citas(resultados: list[ResultadoRag]) -> A.Citas | None:
    if not resultados:
        return None
    return A.Citas(
        id=nuevo_id("cit"),
        citas=[
            A.Cita(
                doc_codigo=r.doc_codigo,
                documento=r.titulo_doc,
                seccion=r.seccion[:200],
                fragmento=r.contenido[:240],
                puntuacion=round(r.score_vector, 3),
            )
            for r in resultados
        ],
    )


# ----------------------------------------------------------------------------- herramientas


def saludo(actor: Actor) -> Resultado:
    return Resultado(
        artifacts=[respuestas_rapidas(*MENU)],
        texto="¡Hola! Soy el asistente virtual de TransLogix. Puedo rastrear tu guía, cotizar un envío, decirte si un "
        "producto se puede enviar o ayudarte a radicar un reclamo. ¿En qué te ayudo?",
        confianza=1.0,
    )


def fuera_de_alcance() -> Resultado:
    return Resultado(
        artifacts=[respuestas_rapidas(*MENU)],
        texto="Solo puedo ayudarte con envíos de TransLogix: rastreo, cotizaciones, normativa de carga, "
        "cobertura y reclamos.",
        confianza=0.9,
    )


def formulario_guia(sesion: SesionChat) -> Resultado:
    aid = nuevo_id("fgu")
    form = A.FormularioGuia(
        id=aid,
        titulo="Rastrear un envío",
        campos=[
            A.CampoFormulario(
                nombre="guia",
                etiqueta="Número de guía",
                tipo="texto",
                requerido=True,
                patron=r"(?i)^\s*TLX\s*-?\s*\d{6}\s*-?\s*CO\s*$",
                ayuda="Formato TLX-XXXXXX-CO (está en tu comprobante de envío).",
            )
        ],
        acciones=[accion_enviar(sesion, aid, "Rastrear")],
    )
    return Resultado(
        artifacts=[form],
        texto="Claro. Escribe tu número de guía (formato TLX-XXXXXX-CO).",
        confianza=1.0,
        contexto={"esperando": "guia"},  # el siguiente mensaje puede ser la guía dictada (`guia_dictada`)
    )


async def rastrear(s: AsyncSession, actor: Actor, sesion: SesionChat, guia: str | None) -> Resultado:
    guia = guia or sesion.contexto.get("guia")
    if not guia:
        return formulario_guia(sesion)
    try:
        t = await tracking(s, guia, actor)
    except ApiError as e:
        r = formulario_guia(sesion)
        r.texto = e.detail
        r.confianza = 0.95
        return r
    envio = await s.get(Envio, guia)
    alerta = None
    if t.novedad:
        alerta = A.Alerta(nivel="advertencia", mensaje=t.eventos[-1].descripcion if t.eventos else t.estado_texto)
    artifacts: list[BaseModel] = [
        A.LineaTiempoEnvio(
            id=nuevo_id("ltm"),
            guia=t.numero_guia,
            origen=t.origen,
            destino=t.destino,
            servicio=t.servicio,
            estado_actual=t.estado,
            estado_texto=t.estado_texto,
            progreso_pct=t.progreso_pct if t.progreso_pct is not None else 0,
            eta=None if t.es_final else t.fecha_estimada_entrega,
            eventos=[
                A.EventoLinea(
                    ts=e.ocurrido_en,
                    estado=e.estado,
                    estado_texto=e.estado_texto,
                    ubicacion=e.ubicacion,
                    descripcion=e.descripcion,
                )
                for e in t.eventos
            ],
            alerta=alerta,
        )
    ]
    if t.ubicacion.latitud is not None and not t.es_final:
        artifacts.append(
            A.MapaUbicacion(
                id=nuevo_id("map"),
                guia=t.numero_guia,
                latitud=float(t.ubicacion.latitud),
                longitud=float(t.ubicacion.longitud),
                referencia=t.ubicacion.referencia,
                actualizado=t.eventos[-1].ocurrido_en if t.eventos else None,
            )
        )
    texto = f"Tu envío {t.numero_guia} ({t.origen} → {t.destino}): {t.estado_texto}"
    if t.es_final and t.fecha_entrega_real:
        texto += f" Entregado el {fecha_local(t.fecha_entrega_real)}."
    elif not t.es_final:
        texto += f" Entrega estimada: {fecha_local(t.fecha_estimada_entrega)}."
    if alerta:
        texto += f" Novedad: {alerta.mensaje}"
    return Resultado(
        artifacts=artifacts,
        texto=texto,
        confianza=1.0,
        guia=guia,
        contexto={"guia": guia},
        escalamiento={
            "flujo": "rastreo",
            "valor_declarado": envio.valor_declarado,
            "mercancia_peligrosa": envio.mercancia_peligrosa,
            "requiere_refrigeracion": envio.requiere_refrigeracion,
            "estado_envio": envio.estado_actual,
        },
    )


SERVICIOS = [
    A.Opcion(valor="paqueteria", etiqueta="Paquetería (hasta 50 kg)"),
    A.Opcion(valor="carga", etiqueta="Carga (FTL/LTL)"),
    A.Opcion(valor="cadena_frio", etiqueta="Cadena de frío"),
    A.Opcion(valor="mercancia_peligrosa", etiqueta="Mercancía peligrosa"),
]
CAMPOS_COTIZACION = ("origen", "destino", "alto_cm", "ancho_cm", "largo_cm", "peso_kg", "valor_declarado_cop")


async def formulario_cotizacion(s: AsyncSession, sesion: SesionChat, previos: dict) -> A.FormularioCotizacion:
    trayectos = (await s.scalars(select(Trayecto))).unique().all()
    origenes = sorted({t.origen.nombre for t in trayectos})
    destinos = sorted({t.destino.nombre for t in trayectos})
    aid = nuevo_id("fco")

    def num(nombre, etiqueta, unidad, mn, mx):
        return A.CampoFormulario(
            nombre=nombre,
            etiqueta=etiqueta,
            tipo="numero",
            requerido=True,
            min=Decimal(mn),
            max=Decimal(mx),
            unidad=unidad,
            valor=_valor(previos.get(nombre)),
        )

    return A.FormularioCotizacion(
        id=aid,
        titulo="Cotiza tu envío",
        campos=[
            A.CampoFormulario(
                nombre="origen",
                etiqueta="Ciudad de origen",
                tipo="seleccion",
                requerido=True,
                opciones=[A.Opcion(valor=o, etiqueta=o) for o in origenes],
                valor=previos.get("origen"),
                ayuda="Destinos disponibles por origen: GET /api/v1/trayectos/destinos?origen=",
            ),
            A.CampoFormulario(
                nombre="destino",
                etiqueta="Ciudad de destino",
                tipo="seleccion",
                requerido=True,
                opciones=[A.Opcion(valor=d, etiqueta=d) for d in destinos],
                valor=previos.get("destino"),
            ),
            num("alto_cm", "Alto", "cm", "0.1", "1000"),
            num("ancho_cm", "Ancho", "cm", "0.1", "1000"),
            num("largo_cm", "Largo", "cm", "0.1", "2000"),
            num("peso_kg", "Peso real", "kg", "0.1", "40000"),
            A.CampoFormulario(
                nombre="valor_declarado_cop",
                etiqueta="Valor declarado",
                tipo="moneda",
                requerido=True,
                min=Decimal(1),
                unidad="COP",
                valor=_valor(previos.get("valor_declarado_cop")),
                ayuda="El seguro es el 1 % de este valor (con un mínimo por ruta).",
            ),
            A.CampoFormulario(
                nombre="servicio",
                etiqueta="Tipo de servicio",
                tipo="seleccion",
                requerido=True,
                opciones=SERVICIOS,
                valor=previos.get("servicio") or "paqueteria",
            ),
            A.CampoFormulario(
                nombre="unidades",
                etiqueta="Unidades",
                tipo="numero",
                requerido=False,
                min=Decimal(1),
                max=Decimal(500),
                valor=_valor(previos.get("unidades")) or 1,
            ),
            A.CampoFormulario(
                nombre="contenido",
                etiqueta="¿Qué contiene?",
                tipo="texto",
                requerido=False,
                max=Decimal(200),
                valor=previos.get("contenido"),
                ayuda="Lo validamos contra la lista de mercancías prohibidas.",
            ),
        ],
        acciones=[accion_enviar(sesion, aid, "Cotizar")],
    )


def _valor(v):
    if v is None:
        return None
    if isinstance(v, Decimal | float):
        return str(v)
    return v


def _a_cotizacion_in(v: dict) -> CotizacionIn:
    servicio = v.get("servicio") or "paqueteria"
    return CotizacionIn(
        origen=v["origen"],
        destino=v["destino"],
        alto_cm=v["alto_cm"],
        ancho_cm=v["ancho_cm"],
        largo_cm=v["largo_cm"],
        peso_kg=v["peso_kg"],
        valor_declarado=v["valor_declarado_cop"],
        modalidad="paqueteria" if servicio == "paqueteria" else "carga",
        cadena_frio=servicio == "cadena_frio",
        mercancia_peligrosa=servicio == "mercancia_peligrosa",
        unidades=int(v.get("unidades") or 1),
        contenido=v.get("contenido") or None,
    )


def resultado_cotizacion(c: CotizacionOut, servicio: str) -> A.ResultadoCotizacion:
    d = c.desglose
    recargos = [
        A.Recargo(concepto=k, valor=val)
        for k, val in (
            ("Cadena de frío", d.recargo_cadena_frio),
            ("Mercancía peligrosa", d.recargo_mercancia_peligrosa),
        )
        if val > 0
    ]
    return A.ResultadoCotizacion(
        id=nuevo_id("rco"),
        titulo=f"Cotización {c.origen} → {c.destino}",
        cotizacion_id=str(c.id),
        trayecto=c.codigo_trayecto,
        origen=c.origen,
        destino=c.destino,
        servicio=servicio,
        peso_real_kg=d.peso_real_kg,
        peso_volumetrico_kg=d.peso_volumetrico_kg,
        peso_facturable_kg=d.peso_facturable_kg,
        base_facturacion=d.base_cobro,
        tarifa_kg=d.tarifa_aplicada_kg,
        flete_base=d.flete,
        flete_minimo_aplicado=d.flete_minimo_aplicado,
        seguro=d.seguro,
        recargos=recargos,
        total=c.total,
        tiempo_estimado_horas=c.tiempo_estimado_horas,
        observaciones=" ".join(c.observaciones) or None,
        advertencias=["Se aplicó el flete mínimo de la ruta."] if d.flete_minimo_aplicado else [],
    )


async def cotizar(s: AsyncSession, actor: Actor, sesion: SesionChat, valores: dict) -> Resultado:
    previos = {**sesion.contexto.get("cotizacion", {}), **{k: v for k, v in valores.items() if v not in (None, "")}}
    faltan = [c for c in CAMPOS_COTIZACION if previos.get(c) in (None, "")]
    if faltan:
        form = await formulario_cotizacion(s, sesion, previos)
        ya = [c for c in CAMPOS_COTIZACION if c not in faltan]
        texto = "Con gusto te cotizo. Completa los datos del envío" + (" (ya tomé los que me diste)." if ya else ".")
        return Resultado(artifacts=[form], texto=texto, confianza=1.0, contexto={"cotizacion": _serializable(previos)})
    try:
        datos = _a_cotizacion_in(previos)
        c = await cotizar_y_guardar(s, datos, actor, sesion.id)
    except (ErrorDominio, ApiError) as e:
        mensaje = e.mensaje if isinstance(e, ErrorDominio) else e.detail
        codigo = e.codigo
        form = await formulario_cotizacion(s, sesion, previos)
        extra = (
            [respuestas_rapidas(("Hablar con un asesor", "Quiero hablar con un asesor"))]
            if codigo == "TRAYECTO_INEXISTENTE"
            else []
        )
        return Resultado(
            artifacts=[form, *extra],
            texto=f"No pude cotizar: {mensaje}",
            confianza=0.95,
            contexto={"cotizacion": _serializable(previos)},
        )
    except ValueError as e:  # datos que no pasan CotizacionIn
        form = await formulario_cotizacion(s, sesion, previos)
        return Resultado(artifacts=[form], texto=f"Revisa los datos del envío: {str(e)[:200]}", confianza=0.95)
    servicio = next((o.etiqueta for o in SERVICIOS if o.valor == previos.get("servicio")), "Paquetería")
    texto = (
        f"El envío {c.origen} → {c.destino} cuesta {pesos(c.total)} COP: flete {pesos(c.desglose.flete)}, "
        f"seguro {pesos(c.desglose.seguro)}"
        + (
            f" y recargos por {pesos(c.desglose.recargo_cadena_frio + c.desglose.recargo_mercancia_peligrosa)}"
            if c.desglose.recargo_cadena_frio + c.desglose.recargo_mercancia_peligrosa > 0
            else ""
        )
        + f". Peso facturable {c.desglose.peso_facturable_kg} kg; entrega estimada en {c.tiempo_estimado_horas} horas."
    )
    return Resultado(
        artifacts=[
            resultado_cotizacion(c, servicio),
            respuestas_rapidas(("Cotizar otro envío", "Quiero cotizar otro envío")),
        ],
        texto=texto,
        confianza=1.0,
        contexto={"cotizacion": {}},
        escalamiento={"flujo": "cotizacion", "mercancia_peligrosa": False},
    )


def _serializable(d: dict) -> dict:
    return {k: (str(v) if isinstance(v, Decimal) else v) for k, v in d.items()}


@lru_cache
def guias_embalaje() -> dict[str, tuple[str, str | None, list[str]]]:
    """Categorías A-D del manual DOC-OPS-2026-03 §4: {letra: (nombre, requisito, pasos)}."""
    texto = (get_settings().datos_dir / "manual_de_mercanc_as_peligrosas_y_embalaje.md").read_text(encoding="utf-8")
    seccion = texto.split("## 4.", 1)[1].split("## 5.", 1)[0]
    salida = {}
    for bloque in re.split(r"\n### ", seccion)[1:]:
        cabecera, _, cuerpo = bloque.partition("\n")
        letra, _, nombre = cabecera.partition(". ")
        requisito = re.search(r"\*\*Requisito:\*\*\s*(.+)", cuerpo)
        pasos = [_limpiar_md(p) for p in re.findall(r"^\s+\d+\.\s+(.+)$", cuerpo, re.M)]
        salida[letra.strip()] = (nombre.strip(), _limpiar_md(requisito.group(1)) if requisito else None, pasos)
    return salida


def _limpiar_md(t: str) -> str:
    t = re.sub(r"\$([^$]+)\$", lambda m: re.sub(r"\\text\{\s*([^}]*)\}", r" \1", m.group(1)).replace("^\\circ", "°"), t)
    return re.sub(r"\*\*|\*|`", "", t).replace("  ", " ").strip()


_CATEGORIA_EMBALAJE = (
    ("A", r"fragil|vidrio|ceramic|porcelana|jarron|espejo|instrumento|copa|botella de vidrio"),
    ("C", r"perecedero|medicament|vacuna|alimento|comida|refrigerad|congelad|insulina|frio|carne|queso"),
    ("D", r"electronic|laptop|portatil|computador|celular|telefono|servidor|tablet|televisor|camara"),
    ("B", r"liquido|aceite|bebida|cosmetic|perfume|shampoo|crema|vino|licor|jabon"),
)


def categoria_embalaje(texto: str) -> str | None:
    t = normalizar_para_busqueda(texto)
    return next((c for c, patron in _CATEGORIA_EMBALAJE if re.search(patron, t)), None)


def artifact_embalaje(letra: str) -> A.GuiaEmbalaje:
    nombre, requisito, pasos = guias_embalaje()[letra]
    return A.GuiaEmbalaje(
        id=nuevo_id("emb"),
        categoria=letra,
        nombre_categoria=nombre,
        requisito=requisito,
        pasos=pasos,
        fuentes=[
            A.Cita(
                doc_codigo="DOC-OPS-2026-03",
                documento="Manual de mercancías peligrosas y embalaje",
                seccion=f"§4.{letra} {nombre}",
            )
        ],
    )


def embalaje(texto: str, categoria: str | None = None) -> Resultado:
    letra = categoria or categoria_embalaje(texto)
    if not letra:
        nombres = guias_embalaje()
        return Resultado(
            artifacts=[
                respuestas_rapidas(
                    *(
                        (f"{k}. {v[0].split(' (')[0]}", f"¿Cómo embalo {v[0].split(' (')[0].lower()}?")
                        for k, v in nombres.items()
                    )
                )
            ],
            texto="¿Qué tipo de producto vas a enviar? Elige una categoría para darte las instrucciones de embalaje.",
            confianza=0.95,
        )
    nombre, requisito, pasos = guias_embalaje()[letra]
    return Resultado(
        artifacts=[artifact_embalaje(letra)],
        pregunta_llm=texto,
        hechos=f"Categoría de embalaje {letra}: {nombre}. Requisito: {requisito}. Pasos: " + " ".join(pasos),
        rag_tipos=["embalaje"],
        plantilla_segura=f"Para {nombre.lower()} el requisito es: {requisito} Sigue los pasos de la guía de embalaje.",
        confianza=0.95,
    )


def mercancia(texto: str, producto: str | None = None) -> Resultado:
    v = evaluar_producto(producto or texto)
    if v.veredicto == "desconocido":
        return Resultado(pregunta_llm=texto, rag_tipos=["mercancia_peligrosa", "prohibido", "embalaje"], confianza=0.0)
    pasos = list(guias_embalaje()[v.categoria_embalaje][2]) if v.categoria_embalaje in guias_embalaje() else []
    artefacto = A.VeredictoMercancia(
        id=nuevo_id("ver"),
        producto=v.producto or (producto or texto)[:80],
        veredicto=v.veredicto,
        categoria=v.producto,
        clase_onu=v.clase_onu,
        motivo=v.motivo,
        documentos=list(v.documentos_requeridos),
        embalaje=pasos,
        fuentes=[
            A.Cita(
                doc_codigo="DOC-OPS-2026-03",
                documento="Manual de mercancías peligrosas y embalaje",
                seccion=v.fuente or "DOC-OPS-2026-03",
            )
        ],
    )
    etiqueta = {
        "permitido": "SÍ se puede enviar",
        "restringido": "se puede enviar CON RESTRICCIONES",
        "solo_ftl": "solo se acepta en carga completa (FTL)",
        "prohibido": "está PROHIBIDO: no se puede enviar",
    }[v.veredicto]
    hechos = (
        f"Veredicto oficial: {v.producto} {etiqueta}. Motivo: {v.motivo}"
        + (f" Clase ONU {v.clase_onu}." if v.clase_onu else "")
        + (f" Documentos obligatorios: {'; '.join(v.documentos_requeridos)}." if v.documentos_requeridos else "")
        + f" Fuente: {v.fuente}."
    )
    plantilla = {
        "prohibido": f"No. {(v.producto or 'ese artículo').capitalize()} está en la lista de prohibidos de "
        f"TransLogix ({v.fuente}): no lo recibimos ni lo transportamos.",
        "permitido": f"Sí, puedes enviarlo. {v.motivo}",
        "restringido": f"Se puede enviar con restricciones: {v.motivo}",
        "solo_ftl": f"Solo lo aceptamos en carga completa (FTL): {v.motivo}",
    }[v.veredicto]
    return Resultado(
        artifacts=[artefacto],
        pregunta_llm=texto,
        hechos=hechos,
        rag_tipos=["mercancia_peligrosa", "prohibido"],
        veredicto=v.veredicto,
        plantilla_segura=plantilla,
        confianza=0.95,
    )


MANUAL = "Manual de mercancías peligrosas y embalaje"
_ETIQUETA_PLAN = {
    "permitido": "Se puede enviar",
    "restringido": "Se puede enviar con restricciones",
    "solo_ftl": "Solo se acepta en carga completa (FTL)",
}


def _plan_envio(producto: str | None, v: EvaluacionProducto) -> A.PlanEnvio:
    conocido = v.veredicto != "desconocido"
    nombre = producto or "tu mercancía"
    if conocido:
        estado, resumen = v.veredicto, f"{_ETIQUETA_PLAN[v.veredicto]}. {v.motivo}"
    elif producto:
        # El catálogo no lo clasifica: se dice tal cual, sin convertirlo en un "sí" que ningún documento respalda.
        estado = "sin_registro"
        resumen = (
            f"«{producto}» no aparece en nuestro catálogo de prohibidos y mercancías peligrosas. "
            "No es una aprobación: si tiene químicos, baterías o dudas, un asesor lo confirma."
        )
    else:
        estado = "sin_producto"
        resumen = "Cuéntame qué vas a enviar o escríbelo en «¿Qué contiene?»: lo revisamos contra los prohibidos."

    guia = guias_embalaje().get(v.categoria_embalaje or "")
    embalaje = (
        A.PasoPlan(titulo="Embala", detalle=guia[1] or guia[0], items=guia[2])
        if guia
        else A.PasoPlan(
            titulo="Embala",
            detalle="Tú respondes por entregarlo embalado para resistir vibración, frenado, inclinación y apilamiento. "
            "El manual no trae instrucciones específicas para este producto.",
        )
    )
    documentos = (
        A.PasoPlan(
            titulo="Reúne los documentos",
            detalle="Son obligatorios para este envío:",
            items=list(v.documentos_requeridos),
        )
        if v.documentos_requeridos
        else A.PasoPlan(
            titulo="Reúne los documentos",
            detalle="El manual solo exige documentos especiales para mercancía peligrosa."
            if conocido or producto
            else "Dependen de lo que envíes: la mercancía peligrosa exige documentos especiales.",
        )
    )
    return A.PlanEnvio(
        id=nuevo_id("pln"),
        titulo=f"Plan para enviar {nombre}"[:120],
        producto=producto,
        estado=estado,
        resumen=resumen[:500],
        pasos=[
            embalaje,
            documentos,
            A.PasoPlan(
                titulo="Completa el formulario",
                detalle="Con origen, destino, medidas, peso y valor declarado te doy el flete, el seguro y el tiempo.",
                items=[
                    f"Paquetería hasta {LIMITE_PAQUETERIA_KG} kg; con más peso, elige carga.",
                    "Se cobra por el mayor entre el peso real y el volumétrico.",
                ],
            ),
        ],
        fuentes=[A.Cita(doc_codigo="DOC-OPS-2026-03", documento=MANUAL, seccion=v.fuente or "§4 y §5")],
    )


def _servicio_sugerido(v: EvaluacionProducto) -> str | None:
    if v.veredicto in ("restringido", "solo_ftl"):
        return "mercancia_peligrosa"
    return "cadena_frio" if v.categoria_embalaje == "C" else None


async def enviar(
    s: AsyncSession, actor: Actor, sesion: SesionChat, texto: str, extraidos: dict | None = None
) -> Resultado:
    """Tarea "quiero enviar X": plan con los requisitos del manual + formulario. Sin LLM: responde aunque esté caído."""
    v = evaluar_producto(texto)
    if v.veredicto == "prohibido":
        return mercancia(texto)  # T-MP-3: un prohibido no llega al formulario.
    trayectos = (await s.scalars(select(Trayecto))).unique().all()
    datos = extraer_envio(
        texto, sorted({t.origen.nombre for t in trayectos}), sorted({t.destino.nombre for t in trayectos})
    )
    # Un envío nuevo no hereda los datos de una cotización anterior de la sesión.
    sesion.contexto = {**sesion.contexto, "cotizacion": {}}
    valores = {**(extraidos or {})}
    valores.update(
        {
            k: val
            for k, val in {
                "origen": datos.origen,
                "destino": datos.destino,
                "contenido": datos.producto,
                "servicio": valores.get("servicio") or _servicio_sugerido(v),
            }.items()
            if val
        }
    )
    res = await cotizar(s, actor, sesion, valores)
    plan = _plan_envio(datos.producto, v)
    for a in res.artifacts:
        if isinstance(a, A.FormularioCotizacion):
            a.titulo = f"Datos para enviar {datos.producto or 'tu mercancía'}"[:120]
    res.artifacts.insert(0, plan)
    if any(isinstance(a, A.FormularioCotizacion) for a in res.artifacts) and not res.texto.startswith("No pude"):
        res.texto = f"Te dejo los pasos y el formulario para enviar {datos.producto or 'tu mercancía'}."
    if plan.estado == "sin_registro":
        res.artifacts.append(respuestas_rapidas(("Confirmar con un asesor", "Quiero hablar con un asesor")))
    return res


async def cobertura(s: AsyncSession, texto: str, ciudad: str | None, sesion: SesionChat) -> Resultado:
    municipios = (await s.scalars(select(Municipio))).unique().all()
    t = f" {normalizar_para_busqueda(ciudad or texto)} "
    m = next(
        (
            m
            for m in sorted(municipios, key=lambda x: -len(x.nombre))
            if f" {normalizar_para_busqueda(m.nombre).replace(' d c', '')} " in t
        ),
        None,
    )
    if m is None:
        if ciudad:
            return Resultado(
                artifacts=[respuestas_rapidas(("Hablar con un asesor", "Quiero hablar con un asesor"))],
                texto=f"No tenemos cobertura registrada en {ciudad}. Un asesor puede revisar alternativas de envío.",
                confianza=0.9,
            )
        return Resultado(
            texto="¿A qué ciudad o municipio quieres enviar?", confianza=0.95, contexto={"esperando": "ciudad"}
        )
    ficha = A.FichaCobertura(
        id=nuevo_id("cob"),
        municipio=m.nombre,
        departamento=m.departamento.nombre,
        codigo_dane=m.codigo_dane,
        tipo_cobertura=m.tipo_cobertura.value,
        hub=m.hub.nombre,
        same_day=m.servicio_same_day,
        refrigerado=m.servicio_refrigerado,
        peso_maximo_kg=m.peso_maximo_paquete_kg,
        volumen_maximo_m3=m.volumen_maximo_m3,
        tiempo_estandar_horas=m.tiempo_entrega_estandar_horas,
        frecuencia_despacho=m.frecuencia_despacho,
        restricciones=m.restricciones_operativas,
    )
    texto = (
        f"Sí llegamos a {m.nombre} ({m.departamento.nombre}): entrega estándar en "
        f"{m.tiempo_entrega_estandar_horas} horas, "
        f"despachos {m.frecuencia_despacho.lower()}. Mismo día: {'sí' if m.servicio_same_day else 'no'}; "
        f"cadena de frío: {'sí' if m.servicio_refrigerado else 'no'}."
    )
    return Resultado(
        artifacts=[ficha, respuestas_rapidas(("Cotizar a esta ciudad", f"Quiero cotizar un envío a {m.nombre}"))],
        texto=texto,
        confianza=1.0,
        contexto={"esperando": None},
    )


NOVEDADES = {"averia_aparente": "aparente", "averia_oculta": "oculta", "perdida": "perdida"}


def detectar_novedad(texto: str) -> str | None:
    t = normalizar_para_busqueda(texto)
    if re.search(r"no llego|perdi|extravi|nunca llego|robad|se perdio", t):
        return "perdida"
    if re.search(
        r"al recibir|en la entrega|cuando me lo entregaron|caja rota|cinta violada|llego roto|llego aplastad", t
    ):
        return "averia_aparente"
    if re.search(r"rot[oa]|partid|dan[oa]|aplast|averi|incomplet|saque|falta", t):
        return "averia_oculta"
    return None


ETIQUETAS_DOC = {
    "guia": "Número de guía",
    "factura": "Factura comercial (con IVA) o comprobante de compra",
    "carta_reclamacion": "Carta de reclamación firmada (valor exacto y descripción)",
    "certificacion_bancaria": "Certificación bancaria (no mayor a 30 días)",
    "documento_identidad": "Cédula o RUT",
    "foto_empaque": "Foto del empaque exterior con la etiqueta",
    "foto_dano": "Foto del daño y del producto",
    "foto_amortiguacion": "Foto del material de amortiguación",
    "acta_salvedad": "Guía/POD con la salvedad anotada al recibir",
}


def checklist(radicado: str | None, items: dict[str, bool]) -> A.ChecklistDocumentos:
    return A.ChecklistDocumentos(
        id=nuevo_id("chk"),
        titulo="Documentos para tu reclamación",
        radicado=radicado,
        endpoint_carga=f"/api/v1/pqrs/{radicado}/documentos" if radicado else None,
        items=[
            A.ItemChecklist(
                id=k,
                etiqueta=ETIQUETAS_DOC.get(k, k),
                requerido=True,
                completado=v,
                accept=None if k == "guia" else "application/pdf,image/jpeg,image/png",
                max_bytes=None if k == "guia" else get_settings().max_upload_bytes,
            )
            for k, v in items.items()
        ],
        completo=all(items.values()),
    )


async def formulario_pqrs(
    sesion: SesionChat, guia: str | None, novedad: str | None, descripcion: str | None
) -> A.FormularioPqrs:
    aid = nuevo_id("fpq")
    return A.FormularioPqrs(
        id=aid,
        titulo="Radicar PQRS o reclamación",
        campos=[
            A.CampoFormulario(
                nombre="tipo",
                etiqueta="Tipo de solicitud",
                tipo="seleccion",
                requerido=True,
                opciones=[
                    A.Opcion(valor="P", etiqueta="Petición"),
                    A.Opcion(valor="Q", etiqueta="Queja"),
                    A.Opcion(valor="R", etiqueta="Reclamo"),
                    A.Opcion(valor="S", etiqueta="Indemnización por daño o pérdida"),
                ],
                valor="S" if novedad else None,
            ),
            A.CampoFormulario(
                nombre="guia",
                etiqueta="Número de guía",
                tipo="texto",
                requerido=False,
                patron=r"(?i)^\s*TLX\s*-?\s*\d{6}\s*-?\s*CO\s*$",
                valor=guia,
            ),
            A.CampoFormulario(
                nombre="novedad",
                etiqueta="¿Qué pasó?",
                tipo="seleccion",
                requerido=False,
                opciones=[
                    A.Opcion(valor="averia_aparente", etiqueta="Daño visible al recibir"),
                    A.Opcion(valor="averia_oculta", etiqueta="Daño que descubrí después"),
                    A.Opcion(valor="perdida", etiqueta="El envío no llegó"),
                ],
                valor=novedad,
                ayuda="Obligatorio para indemnizaciones.",
            ),
            A.CampoFormulario(
                nombre="descripcion",
                etiqueta="Describe lo ocurrido",
                tipo="texto",
                requerido=True,
                min=Decimal(10),
                max=Decimal(4000),
                valor=descripcion,
            ),
            A.CampoFormulario(
                nombre="valor_reclamado_cop",
                etiqueta="Valor reclamado",
                tipo="moneda",
                requerido=False,
                min=Decimal(1),
                unidad="COP",
            ),
            A.CampoFormulario(
                nombre="anotada_en_guia",
                etiqueta="¿Dejaste la anotación en la guía al recibir?",
                tipo="booleano",
                requerido=False,
                valor=False,
            ),
        ],
        acciones=[accion_enviar(sesion, aid, "Radicar")],
    )


async def pqrs_radicar(s: AsyncSession, actor: Actor, sesion: SesionChat, texto: str, guia: str | None) -> Resultado:
    guia = guia or sesion.contexto.get("guia")
    novedad = detectar_novedad(texto)
    items = {"guia": guia is not None} | {
        d.value: False for d in svc_pqrs.documentos_requeridos(TipoPqrs.SINIESTRO, NOVEDADES.get(novedad or "", None))
    }
    if actor.es_invitado or actor.rol is not Rol.CLIENTE:
        return Resultado(
            artifacts=[checklist(None, items) if novedad else respuestas_rapidas(*MENU[:2])],
            texto="Lamentamos lo ocurrido. Para radicar tu reclamación necesitas iniciar sesión "
            "con tu cuenta de cliente. "
            "Ten a mano estos documentos.",
            confianza=0.95,
            escalamiento={"flujo": "pqrs"},
        )
    artifacts: list[BaseModel] = []
    texto_salida = "Lamentamos lo ocurrido. Completa el formulario para radicar tu solicitud."
    envio = None
    if guia:
        envio = await s.get(Envio, guia)
        if envio is not None and envio.cuenta_id != actor.cuenta_id:
            envio = None
    if guia and novedad and envio is not None:
        try:
            p = await svc_pqrs.plazo(s, guia, NOVEDADES[novedad], False, actor)
            artifacts.append(
                A.EstadoPlazo(
                    id=nuevo_id("pla"),
                    guia=guia,
                    novedad=novedad,
                    fecha_referencia=p.fecha_referencia,
                    fecha_limite=p.fecha_limite,
                    dias_habiles_plazo={"averia_aparente": 0, "averia_oculta": 3, "perdida": 15}[novedad],
                    dias_habiles_restantes=p.dias_habiles_restantes or 0,
                    vigente=p.vigente,
                    mensaje="Estás a tiempo para reclamar." if p.vigente else "El plazo legal para reclamar ya venció.",
                    fundamento=p.fundamento,
                )
            )
            texto_salida = (
                f"Lamentamos lo ocurrido. {p.fundamento} Completa el formulario y adjunta los documentos."
                if p.vigente
                else f"Lo sentimos: {p.fundamento}"
            )
        except (ApiError, ErrorDominio) as e:
            texto_salida = f"Lamentamos lo ocurrido. {e.detail if isinstance(e, ApiError) else e.mensaje}"
    artifacts += [await formulario_pqrs(sesion, guia, novedad, texto[:4000]), checklist(None, items)]
    return Resultado(
        artifacts=artifacts,
        texto=texto_salida,
        confianza=1.0,
        guia=guia,
        contexto={"guia": guia} if guia else {},
        escalamiento={
            "flujo": "pqrs",
            "valor_declarado": envio.valor_declarado if envio else None,
            "mercancia_peligrosa": envio.mercancia_peligrosa if envio else False,
            "requiere_refrigeracion": envio.requiere_refrigeracion if envio else False,
            "estado_envio": envio.estado_actual if envio else None,
        },
    )


async def pqrs_enviar(s: AsyncSession, actor: Actor, sesion: SesionChat, v: dict) -> Resultado:
    if actor.es_invitado or actor.rol is not Rol.CLIENTE:
        return Resultado(texto="Para radicar necesitas iniciar sesión con tu cuenta de cliente.", confianza=1.0)
    from app.domain.sanitizar import extraer_guias

    guias = extraer_guias(v.get("guia") or "")
    datos = TicketIn(
        tipo=TipoPqrs(v["tipo"]),
        numero_guia=guias[0] if guias else None,
        descripcion=v["descripcion"],
        tipo_averia=NOVEDADES.get(v.get("novedad") or ""),
        anotada_en_guia=bool(v.get("anotada_en_guia")),
        valor_reclamado=v.get("valor_reclamado_cop"),
    )
    try:
        t = await svc_pqrs.crear_ticket(s, datos, actor, reglas_escalamiento(), sesion.id)
    except ApiError as e:
        return Resultado(texto=f"No pude radicar: {e.detail}", confianza=0.95)
    envio = await s.get(Envio, t.numero_guia) if t.numero_guia else None
    return Resultado(
        artifacts=[
            A.TicketPqrs(
                id=nuevo_id("tik"),
                radicado=t.radicado,
                tipo_pqrs=t.tipo.value,
                estado=t.estado.value,
                guia=t.numero_guia,
                fecha_radicacion=t.creado_en,
                fecha_limite_respuesta=t.fecha_limite_respuesta,
                checklist_completo=all(t.checklist.values()) if t.checklist else True,
                escalado_a="Gestor senior de PQRS" if t.escalado else None,
            ),
            *([checklist(t.radicado, t.checklist)] if t.checklist else []),
        ],
        texto=f"Radicamos tu solicitud con el número {t.radicado}. Te responderemos a más tardar el "
        f"{t.fecha_limite_respuesta:%d/%m/%Y}."
        + (
            " Adjunta los documentos pendientes para continuar el trámite."
            if t.checklist and not all(t.checklist.values())
            else ""
        ),
        confianza=1.0,
        guia=t.numero_guia,
        escalamiento={
            "flujo": "pqrs",
            "valor_declarado": envio.valor_declarado if envio else None,
            "valor_reclamacion": t.valor_reclamado,
            "mercancia_peligrosa": envio.mercancia_peligrosa if envio else False,
            "requiere_refrigeracion": envio.requiere_refrigeracion if envio else False,
            "estado_envio": envio.estado_actual if envio else None,
        },
    )


def rag_abierta(texto: str, tipos: list[str] | None) -> Resultado:
    return Resultado(pregunta_llm=texto, rag_tipos=tipos, confianza=0.0)
