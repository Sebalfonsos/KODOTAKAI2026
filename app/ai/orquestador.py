"""Orquestador del chat: un turno = enrutar → herramienta determinista → (RAG + LLM) → verificar → escalar → persistir.

Emite eventos tipados (app/schemas/chat.py) que la API serializa como SSE o agrega en una respuesta JSON.
Presupuesto de latencia: reglas < 5 ms, artifact antes que cualquier texto, LLM sin razonamiento y en streaming.
"""

import asyncio
import logging
import re
import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from pydantic import BaseModel, TypeAdapter
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.ai import herramientas_cliente as H
from app.ai import rag
from app.ai.eventos import publicar
from app.ai.llm import get_llm
from app.ai.prompts import NO_SE, SISTEMA_CLIENTE, SISTEMA_RESUMEN, mensaje_usuario
from app.ai.router import Ruta, enrutar, extraer_cotizacion
from app.ai.verificador import verificar
from app.core.errors import ApiError
from app.core.security import Actor
from app.db import SessionLocal
from app.domain.escalamiento import ContextoTurno, detectar_palabras_clave, evaluar_escalamiento
from app.domain.sanitizar import extraer_guias, guia_dictada
from app.models import Cuenta, Escalamiento, Mensaje, SesionChat
from app.models.base import EstadoEscalamiento, EstadoSesion, RolMensaje
from app.schemas import artifacts as A
from app.schemas import chat as C
from app.servicios.reglas import reglas_escalamiento

log = logging.getLogger("app.chat")
_ADAPTADOR = TypeAdapter(A.Artifact)
PRIORIDAD_UI = {"CRIT-005": "alta", "CRIT-002": "alta", "CRIT-003": "media", "CRIT-004": "media", "CRIT-001": "normal"}
PRIORIDAD_BD = {"CRIT-005": 1, "CRIT-002": 2, "CRIT-003": 3, "CRIT-004": 4, "CRIT-001": 5}
UMBRAL = reglas_escalamiento()["parametros_generales"]["confidence_score_minimo"]
INACTIVIDAD = timedelta(minutes=reglas_escalamiento()["parametros_generales"]["tiempo_maximo_inactividad_minutos"])
MAX_FORMULARIOS = 10
# Solo con medidas, peso o valor se llama al LLM: "5 litros de ácido" no es un peso que deba adivinar.
_TRAE_MEDIDAS = re.compile(r"\d\s*(?:cm|centimetros|m|metros|kg|kilos?|millones?|mil|pesos|\$)|\$\s*\d", re.IGNORECASE)
_tareas: set[asyncio.Task] = set()  # referencias a tareas en segundo plano (resúmenes IA)


@dataclass
class Entrada:
    """Mensaje ya validado antes de abrir el stream (los 422 se devuelven como HTTP normal)."""

    sesion_id: uuid.UUID
    actor: Actor
    texto: str | None = None
    formulario: str | None = None  # tipo del artifact enviado
    valores: dict | None = None


def formulario_guardado(sesion: SesionChat, artifact_id: str) -> A.FormularioBase:
    """El servidor solo acepta envíos de formularios que él mismo emitió en esta sesión."""
    datos = sesion.contexto.get("formularios", {}).get(artifact_id)
    if datos is None:
        raise ApiError(404, "Ese formulario no existe o expiró; pide uno nuevo.", "FORMULARIO_NO_ENCONTRADO")
    return _ADAPTADOR.validate_python(datos)


def _ms(inicio: float) -> float:
    return round((time.perf_counter() - inicio) * 1000, 1)


def _confianza_rag(resultados: list, ruta: Ruta, verificado: bool, no_se: bool) -> float:
    if not resultados:
        return 0.2
    sim = max(r.score_vector for r in resultados)
    # bge-m3: similitud coseno < 0,45 = poco relacionado; > 0,70 = muy relacionado (calibrado con el set T-RAG).
    norm = min(max((sim - 0.45) / 0.25, 0.0), 1.0)
    conf = 0.25 * ruta.certeza + 0.45 * norm + 0.30 * (1.0 if verificado else 0.0)
    return round(min(conf, 0.5) if no_se else conf, 3)


def _fuente_segura(resultados: list) -> str:
    if not resultados:
        return NO_SE
    r = resultados[0]
    frases = " ".join(r.contenido.replace("\n", " ").split(". ")[:2])
    return f"Según {r.doc_codigo} ({r.seccion[:80]}): {frases[:400]}"


async def _cuenta(s, actor: Actor) -> Cuenta | None:
    return await s.get(Cuenta, actor.cuenta_id) if actor.cuenta_id else None


async def _resumir(escalamiento_id: uuid.UUID, sesion_id: uuid.UUID) -> None:
    """Resumen IA para el asesor, en segundo plano: no suma latencia al turno del cliente."""
    try:
        async with SessionLocal() as s:
            filas = (
                await s.scalars(
                    select(Mensaje).where(Mensaje.sesion_id == sesion_id).order_by(Mensaje.id.desc()).limit(10)
                )
            ).all()
            dialogo = "\n".join(f"{m.rol.value}: {m.contenido[:400]}" for m in reversed(filas))
            resumen = await get_llm().completar(
                [{"role": "system", "content": SISTEMA_RESUMEN}, {"role": "user", "content": dialogo}], max_tokens=120
            )
            esc = await s.get(Escalamiento, escalamiento_id)
            if esc and resumen:
                esc.resumen_ia = resumen
                await s.commit()
    except Exception:  # noqa: BLE001 - el resumen es opcional; nunca rompe el escalamiento
        log.warning("resumen_ia_fallo", exc_info=True)


async def _escalar(s, sesion: SesionChat, criterio: str, conf: float, guia: str | None, sentimiento: list[str]):
    """Crea (o reutiliza) el escalamiento abierto de la sesión y devuelve el artifact de aviso."""
    abierto = await s.scalar(
        select(Escalamiento).where(
            Escalamiento.sesion_id == sesion.id,
            Escalamiento.estado.in_([EstadoEscalamiento.PENDIENTE, EstadoEscalamiento.TOMADO]),
        )
    )
    reglas = reglas_escalamiento()
    if abierto is None:
        previos = await s.scalar(
            select(func.count()).select_from(Escalamiento).where(Escalamiento.sesion_id == sesion.id)
        )
        abierto = Escalamiento(
            sesion_id=sesion.id,
            criterio_id=criterio,
            prioridad=PRIORIDAD_BD[criterio],
            payload={
                "session_id": str(sesion.id),
                "numero_guia_consultada": guia or sesion.contexto.get("guia"),
                "confidence_score_promedio": conf,
                "sentimiento_detectado": "negativo" if sentimiento else "neutro",
                "palabras_detectadas": sentimiento,
                "intentos_previos": previos or 0,
            },
        )
        s.add(abierto)
        try:
            async with s.begin_nested():
                await s.flush()
        except IntegrityError:  # otra petición concurrente ya lo abrió
            abierto = await s.scalar(
                select(Escalamiento).where(
                    Escalamiento.sesion_id == sesion.id, Escalamiento.estado == EstadoEscalamiento.PENDIENTE
                )
            )
    sesion.estado = EstadoSesion.ESCALADA
    delante = await s.scalar(
        select(func.count())
        .select_from(Escalamiento)
        .where(
            Escalamiento.estado == EstadoEscalamiento.PENDIENTE,
            Escalamiento.prioridad <= abierto.prioridad,
            Escalamiento.creado_en < (abierto.creado_en or datetime.now(UTC)),
        )
    )
    mensaje = next(
        c["mensaje_cliente"] for c in reglas["criterios_escalacion"] if c["id_criterio"] == abierto.criterio_id
    )
    espera = reglas["flujo_transferencia_pwa"]["tiempo_espera_estimado_segundos"]
    aviso = A.AvisoEscalamiento(
        id=H.nuevo_id("esc"),
        escalamiento_id=str(abierto.id),
        criterio=abierto.criterio_id,
        prioridad=PRIORIDAD_UI[abierto.criterio_id],
        mensaje=mensaje,
        espera_estimada_s=espera,
        posicion_cola=(delante or 0) + 1,
    )
    evento = C.EventoEscalamiento(
        escalamiento_id=str(abierto.id),
        criterio=abierto.criterio_id,
        prioridad=aviso.prioridad,
        mensaje=mensaje,
        espera_estimada_s=espera,
    )
    return abierto, aviso, evento


async def _herramienta(s, e: Entrada, sesion: SesionChat, ruta: Ruta) -> H.Resultado:
    texto = e.texto or ""
    if e.formulario == "formulario_cotizacion":
        return await H.cotizar(s, e.actor, sesion, e.valores or {})
    if e.formulario == "formulario_guia":
        guias = extraer_guias(str((e.valores or {}).get("guia", "")))
        return await H.rastrear(s, e.actor, sesion, guias[0] if guias else None)
    if e.formulario == "formulario_pqrs":
        return await H.pqrs_enviar(s, e.actor, sesion, e.valores or {})
    match ruta.intencion:
        case "saludo":
            return H.saludo(e.actor)
        case "rastrear":
            return await H.rastrear(s, e.actor, sesion, ruta.guia)
        case "cotizar":
            valores = {}
            if any(c.isdigit() for c in texto) or len(texto.split()) > 4:
                valores = await extraer_cotizacion(get_llm(), texto)
            return await H.cotizar(s, e.actor, sesion, valores)
        case "enviar":
            extraidos = {}
            if _TRAE_MEDIDAS.search(texto):
                try:
                    extraidos = await extraer_cotizacion(get_llm(), texto)
                except ApiError:  # RF-ESC-7: sin LLM el formulario pide esos datos; la tarea no se cae.
                    log.warning("extraccion_envio_sin_llm")
            return await H.enviar(s, e.actor, sesion, texto, extraidos)
        case "mercancia":
            return H.mercancia(texto, ruta.entidades.get("producto"))
        case "embalaje":
            return H.embalaje(texto)
        case "cobertura":
            return await H.cobertura(s, texto, ruta.entidades.get("ciudad"), sesion)
        case "pqrs_radicar":
            return await H.pqrs_radicar(s, e.actor, sesion, texto, ruta.guia)
        case "pqrs_info":
            return H.rag_abierta(texto, ["pqrs", "legal"])
        case "asesor":
            return H.Resultado(forzar_criterio="CRIT-002", confianza=1.0, guia=ruta.guia)
        case "fuera_de_alcance":
            return H.fuera_de_alcance()
        case _:
            return H.rag_abierta(texto, None)


async def ejecutar(e: Entrada) -> AsyncIterator[BaseModel]:
    """Genera los eventos de un turno. Abre su propia sesión de BD (el stream vive más que la petición)."""
    inicio = time.perf_counter()
    lat: dict[str, float] = {}
    turno = uuid.uuid4()
    async with SessionLocal() as s:
        sesion = await s.get(SesionChat, e.sesion_id, with_for_update=True)
        texto_usuario = e.texto or f"[{e.formulario}] " + ", ".join(f"{k}={v}" for k, v in (e.valores or {}).items())
        s.add(
            Mensaje(
                sesion_id=sesion.id,
                turno_id=turno,
                rol=RolMensaje.USUARIO,
                autor_id=e.actor.id,
                contenido=texto_usuario[:4000],
            )
        )
        sesion.contexto = dict(sesion.contexto or {})
        if datetime.now(UTC) - sesion.ultima_actividad > INACTIVIDAD and sesion.estado == EstadoSesion.ACTIVA:
            # RF-ESC-6: tras 5 min de inactividad el flujo a medias se descarta (la guía consultada se conserva).
            sesion.contexto = {"guia": sesion.contexto.get("guia")}
        sesion.ultima_actividad = datetime.now(UTC)

        # Sesión ya en manos de un asesor: el mensaje va al humano, la IA no responde.
        if sesion.estado == EstadoSesion.ESCALADA:
            await s.commit()  # Antes de avisar: el asesor recarga el historial al recibir el evento.
            publicar(
                sesion.id, ("mensaje_cliente", {"texto": texto_usuario, "creado_en": datetime.now(UTC).isoformat()})
            )
            yield C.EventoMeta(turno_id=str(turno), sesion_id=str(sesion.id), intencion="asesor_humano")
            yield C.EventoDelta(texto="Tu mensaje fue enviado al asesor que atiende tu caso.")
            yield C.EventoFin(turno_id=str(turno), confianza=1.0, latencias_ms=C.Latencias(total=_ms(inicio)))
            return

        artifacts: list[BaseModel] = []
        texto_final = ""
        verificado: bool | None = None
        rag_res: list = []
        reglas = reglas_escalamiento()
        crit2 = next(c for c in reglas["criterios_escalacion"] if c["id_criterio"] == "CRIT-002")
        palabras = detectar_palabras_clave(e.texto or "", crit2["keywords_disparadoras"])

        # Lo que el turno anterior quedó esperando vale solo para este mensaje: si no lo responde, se olvida.
        esperando = sesion.contexto.pop("esperando", None)
        t0 = time.perf_counter()
        try:
            if e.formulario:
                ruta = Ruta(e.formulario.replace("formulario_", ""), 1.0, "formulario")
            elif palabras:
                ruta = Ruta("asesor", 1.0, "regla")
            elif esperando == "ciudad" and len((e.texto or "").split()) <= 4:
                ruta = Ruta("cobertura", 0.95, "contexto", entidades={"ciudad": e.texto})
            elif esperando == "guia" and (guia := guia_dictada(e.texto or "")):
                ruta = Ruta("rastrear", 0.95, "contexto", guia)
            else:
                ruta = await enrutar(get_llm(), e.texto or "")
            lat["router"] = _ms(t0)
            yield C.EventoMeta(
                turno_id=str(turno),
                sesion_id=str(sesion.id),
                intencion=ruta.intencion,
                confianza_enrutador=ruta.certeza,
            )

            t0 = time.perf_counter()
            res = (
                H.Resultado(forzar_criterio="CRIT-002", confianza=1.0)
                if palabras
                else await _herramienta(s, e, sesion, ruta)
            )
            lat["tool"] = _ms(t0)
            for a in res.artifacts:
                artifacts.append(a)
                yield C.EventoArtifact(artifact=a)
            confianza = res.confianza * ruta.certeza if res.texto else res.confianza

            if res.texto:
                texto_final = res.texto
                yield C.EventoDelta(texto=texto_final)
            elif res.pregunta_llm:
                t0 = time.perf_counter()
                rag_res = await rag.buscar(s, res.pregunta_llm, k=4, tipos=res.rag_tipos)
                lat["retrieval"] = _ms(t0)
                if rag_res:
                    citas = H.citas(rag_res)
                    yield C.EventoCitas(citas=citas.citas)
                contexto = "\n".join(
                    f"[{i}] {r.doc_codigo} — {r.seccion}: {r.contenido}" for i, r in enumerate(rag_res, 1)
                )
                mensajes = [
                    {"role": "system", "content": SISTEMA_CLIENTE},
                    {"role": "user", "content": mensaje_usuario(res.pregunta_llm, res.hechos, contexto)},
                ]
                t0 = time.perf_counter()
                partes: list[str] = []
                try:
                    async for delta in get_llm().stream(mensajes):
                        if not partes:
                            lat["llm_first_token"] = _ms(t0)
                        partes.append(delta)
                        yield C.EventoDelta(texto=delta)
                except ApiError:
                    # RF-ESC-7: sin LLM se usa la plantilla segura; si no hay, se escala a humano.
                    partes = []
                    if not res.plantilla_segura:
                        res.forzar_criterio = "CRIT-001"
                lat["llm_total"] = _ms(t0)
                texto_final = "".join(partes).strip()
                t0 = time.perf_counter()
                fuentes = f"{res.hechos}\n{contexto}\n{res.pregunta_llm}"
                v = verificar(texto_final, fuentes, res.veredicto) if texto_final else None
                lat["verify"] = _ms(t0)
                no_se = not texto_final or NO_SE.lower().rstrip(".") in texto_final.lower()
                verificado = bool(v and v.ok)
                if not verificado:
                    reemplazo = res.plantilla_segura or (_fuente_segura(rag_res) if rag_res and not no_se else NO_SE)
                    if reemplazo != texto_final:
                        texto_final = reemplazo
                        yield C.EventoReemplazo(texto=texto_final, motivo=v.motivo if v else "sin_respuesta_llm")
                if res.veredicto or res.plantilla_segura:
                    confianza = 0.95 if verificado or res.plantilla_segura else 0.6
                else:
                    confianza = _confianza_rag(rag_res, ruta, verificado, no_se)

            # Escalamiento: criterios evaluados en código con los datos de la herramienta y de la cuenta.
            cuenta = await _cuenta(s, e.actor)
            ctx = ContextoTurno(
                confidence_score=confianza,
                texto_usuario=e.texto or "",
                tipo_cuenta=cuenta.tipo_cuenta.value if cuenta else None,
                envios_mensuales_cuenta=cuenta.envios_mensuales if cuenta else None,
                **{k: v for k, v in res.escalamiento.items() if k in ContextoTurno.__dataclass_fields__},
            )
            disparados = [d.id_criterio for d in evaluar_escalamiento(reglas, ctx)]
            criterio = res.forzar_criterio or (disparados[0] if disparados else None)
            if criterio:
                esc, aviso, evento = await _escalar(s, sesion, criterio, confianza, res.guia, palabras)
                if criterio in ("CRIT-001", "CRIT-002") and texto_final != aviso.mensaje:
                    # Respuesta dudosa o cliente molesto: no se deja una respuesta automática, se transfiere.
                    texto_final = aviso.mensaje
                    yield C.EventoReemplazo(texto=texto_final, motivo=f"escalamiento_{criterio.lower()}")
                artifacts.append(aviso)
                yield C.EventoArtifact(artifact=aviso)
                yield evento
                tarea = asyncio.create_task(_resumir(esc.id, sesion.id))
                _tareas.add(tarea)
                tarea.add_done_callback(_tareas.discard)

            # Contexto de sesión: formularios emitidos (para validar envíos) y datos del flujo.
            formularios = dict(sesion.contexto.get("formularios", {}))
            for a in artifacts:
                if isinstance(a, A.FormularioBase):
                    formularios[a.id] = a.model_dump(mode="json")
            sesion.contexto = {
                **sesion.contexto,
                **res.contexto,
                "formularios": dict(list(formularios.items())[-MAX_FORMULARIOS:]),
            }
            lat["total"] = _ms(inicio)
            s.add(
                Mensaje(
                    sesion_id=sesion.id,
                    turno_id=turno,
                    rol=RolMensaje.ASISTENTE,
                    contenido=texto_final,
                    artifacts=[a.model_dump(mode="json") for a in artifacts],
                    intencion=ruta.intencion,
                    confianza=round(confianza, 3),
                    latencias_ms=lat,
                    verificado=verificado,
                )
            )
            await s.commit()
            log.info(
                "turno",
                extra={
                    "turno_id": str(turno),
                    "sesion_id": str(sesion.id),
                    "intencion": ruta.intencion,
                    "latencias": lat,
                    "criterio": criterio,
                },
            )
            yield C.EventoFin(turno_id=str(turno), confianza=round(confianza, 3), latencias_ms=C.Latencias(**lat))
        except ApiError as err:
            await s.rollback()
            yield C.EventoError(
                type="about:blank", title="Error", status=err.status, detail=err.detail, codigo=err.codigo
            )
        except Exception:
            await s.rollback()
            log.exception("turno_fallido", extra={"turno_id": str(turno)})
            yield C.EventoError(
                type="about:blank",
                title="Error interno",
                status=500,
                detail="No pudimos completar tu solicitud.",
                codigo="ERROR_INTERNO",
            )


async def agregar(eventos: AsyncIterator[BaseModel]) -> C.ChatTurnResponse:
    """Versión no-stream: consume los eventos de un turno y arma una respuesta JSON única."""
    datos = {"artifacts": [], "texto": "", "reemplazado": False, "citas": [], "escalamiento": None}
    async for ev in eventos:
        match ev:
            case C.EventoMeta():
                datos |= {"turno_id": ev.turno_id, "sesion_id": ev.sesion_id, "intencion": ev.intencion}
            case C.EventoArtifact():
                datos["artifacts"].append(ev.artifact)
            case C.EventoDelta():
                datos["texto"] += ev.texto
            case C.EventoReemplazo():
                datos["texto"], datos["reemplazado"] = ev.texto, True
            case C.EventoCitas():
                datos["citas"] = ev.citas
            case C.EventoEscalamiento():
                datos["escalamiento"] = ev
            case C.EventoFin():
                datos |= {"confianza": ev.confianza, "latencias_ms": ev.latencias_ms}
            case C.EventoError():
                raise ApiError(ev.status, ev.detail or "Error", ev.codigo)
    return C.ChatTurnResponse(**datos)


async def ejecutar_admin(sesion_id: uuid.UUID, actor: Actor, pregunta: str) -> AsyncIterator[BaseModel]:
    """Turno del chat administrativo: herramienta en lista blanca → artifacts → resumen del LLM verificado."""
    from app.ai import herramientas_admin as HA
    from app.ai.prompts import SISTEMA_ADMIN

    inicio, lat, turno = time.perf_counter(), {}, uuid.uuid4()
    async with SessionLocal() as s:
        sesion = await s.get(SesionChat, sesion_id)
        s.add(
            Mensaje(sesion_id=sesion.id, turno_id=turno, rol=RolMensaje.USUARIO, autor_id=actor.id, contenido=pregunta)
        )
        try:
            t0 = time.perf_counter()
            intencion = await HA.clasificar(get_llm(), pregunta)
            lat["router"] = _ms(t0)
            yield C.EventoMeta(turno_id=str(turno), sesion_id=str(sesion.id), intencion=intencion)
            t0 = time.perf_counter()
            res = await HA.ejecutar(s, intencion, pregunta)
            lat["tool"] = _ms(t0)
            for a in res.artifacts:
                yield C.EventoArtifact(artifact=a)
            verificado = None
            if res.texto:
                texto = res.texto
                yield C.EventoDelta(texto=texto)
            else:
                t0 = time.perf_counter()
                partes: list[str] = []
                try:
                    async for delta in get_llm().stream(
                        [
                            {"role": "system", "content": SISTEMA_ADMIN},
                            {"role": "user", "content": f"DATOS:\n{res.datos}\n\nPREGUNTA:\n{pregunta}"},
                        ]
                    ):
                        if not partes:
                            lat["llm_first_token"] = _ms(t0)
                        partes.append(delta)
                        yield C.EventoDelta(texto=delta)
                except ApiError:
                    partes = []
                lat["llm_total"] = _ms(t0)
                texto = "".join(partes).strip()
                v = verificar(texto, f"{res.datos}\n{pregunta}") if texto else None
                verificado = bool(v and v.ok)
                if not verificado:
                    texto = f"Datos: {res.datos[:600]}"
                    yield C.EventoReemplazo(texto=texto, motivo=v.motivo if v else "sin_respuesta_llm")
            lat["total"] = _ms(inicio)
            s.add(
                Mensaje(
                    sesion_id=sesion.id,
                    turno_id=turno,
                    rol=RolMensaje.ASISTENTE,
                    contenido=texto,
                    artifacts=[a.model_dump(mode="json") for a in res.artifacts],
                    intencion=f"admin:{intencion}",
                    confianza=1,
                    latencias_ms=lat,
                    verificado=verificado,
                )
            )
            sesion.ultima_actividad = datetime.now(UTC)
            await s.commit()
            yield C.EventoFin(turno_id=str(turno), confianza=1.0, latencias_ms=C.Latencias(**lat))
        except ApiError as err:
            await s.rollback()
            yield C.EventoError(
                type="about:blank", title="Error", status=err.status, detail=err.detail, codigo=err.codigo
            )
        except Exception:
            await s.rollback()
            log.exception("turno_admin_fallido")
            yield C.EventoError(
                type="about:blank",
                title="Error interno",
                status=500,
                detail="No pudimos completar la consulta.",
                codigo="ERROR_INTERNO",
            )
