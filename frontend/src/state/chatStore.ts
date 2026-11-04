import type { Artifact, Cita, EventoAsesor, EventoChat, Historial } from "../services/chat";

export interface TurnoAgente {
  rol: "agente";
  turnoId: string | null;
  artifacts: Artifact[];
  texto: string;
  citas: Cita[];
  confianza: number | null;
  completo: boolean;
  /** Confirmación de que el mensaje llegó al asesor: no es una respuesta, no se pinta ni se lee en voz alta. */
  acuse?: boolean;
}
export interface MensajeSimple {
  rol: "usuario" | "asesor" | "sistema";
  texto: string;
  autor?: string | null;
}
export type Entrada = TurnoAgente | MensajeSimple;

export interface Escalamiento {
  id: string;
  criterio: string;
  prioridad: string;
  mensaje: string;
  esperaS: number;
  fase: FaseEscalamiento;
}
/** El backend no emite un evento al tomar el caso: `conectado` solo se confirma con el primer mensaje del asesor. */
export type FaseEscalamiento = "transfiriendo" | "conectado" | "resuelto";

export interface EstadoChat {
  sesionId: string | null;
  entradas: Entrada[];
  enCurso: boolean;
  fallo: { titulo: string; detalle?: string; reintentable: boolean } | null;
  escalamiento: Escalamiento | null;
}

export const estadoInicial: EstadoChat = {
  sesionId: null,
  entradas: [],
  enCurso: false,
  fallo: null,
  escalamiento: null,
};

export type Accion =
  | { tipo: "sesion"; id: string }
  | { tipo: "enviar"; texto: string | null }
  | { tipo: "evento"; evento: EventoChat }
  | { tipo: "asesor"; evento: EventoAsesor }
  | { tipo: "fallo"; titulo: string; detalle?: string; reintentable: boolean }
  | { tipo: "historial"; historial: Historial }
  | { tipo: "reiniciar" };

function turnoVacio(turnoId: string | null = null): TurnoAgente {
  return { rol: "agente", turnoId, artifacts: [], texto: "", citas: [], confianza: null, completo: false };
}

/** Aplica un cambio al turno abierto, o abre uno si el evento llegó sin `meta`. */
function enTurno(e: EstadoChat, cambio: (t: TurnoAgente) => TurnoAgente): EstadoChat {
  const ultimo = e.entradas.at(-1);
  if (ultimo?.rol === "agente" && !ultimo.completo) {
    return { ...e, entradas: [...e.entradas.slice(0, -1), cambio(ultimo)] };
  }
  return { ...e, entradas: [...e.entradas, cambio(turnoVacio())] };
}

function aplicarEvento(e: EstadoChat, ev: EventoChat): EstadoChat {
  switch (ev.evento) {
    case "meta":
      return { ...e, entradas: [...e.entradas, { ...turnoVacio(ev.data.turno_id), acuse: ev.data.intencion === "asesor_humano" }] };
    case "artifact":
      return enTurno(e, (t) => ({ ...t, artifacts: [...t.artifacts, ev.data.artifact] }));
    case "delta":
      return enTurno(e, (t) => ({ ...t, texto: t.texto + ev.data.texto }));
    case "reemplazo": // El verificador corrigió el texto: se sustituye todo lo emitido en el turno.
      return enTurno(e, (t) => ({ ...t, texto: ev.data.texto }));
    case "citas":
      return enTurno(e, (t) => ({ ...t, citas: ev.data.citas }));
    case "escalamiento":
      return {
        ...e,
        escalamiento: {
          id: ev.data.escalamiento_id,
          criterio: ev.data.criterio,
          prioridad: ev.data.prioridad,
          mensaje: ev.data.mensaje,
          esperaS: ev.data.espera_estimada_s,
          fase: "transfiriendo",
        },
      };
    case "fin":
      return { ...enTurno(e, (t) => ({ ...t, confianza: ev.data.confianza, completo: true })), enCurso: false };
    case "error":
      return {
        ...enTurno(e, (t) => ({ ...t, completo: true })),
        enCurso: false,
        fallo: { titulo: ev.data.title, detalle: ev.data.detail ?? undefined, reintentable: false },
      };
  }
}

/** Reconstruye la conversación desde el servidor: tras recargar o cuando un stream se corta. */
function desdeHistorial(e: EstadoChat, h: Historial): EstadoChat {
  const entradas: Entrada[] = [];
  for (const m of h.mensajes) {
    if (m.rol === "usuario") {
      // Un formulario enviado se guarda como "[formulario_guia] guia=…": es un registro técnico, no un mensaje.
      if (!/^\[[a-z_]+\] /.test(m.contenido)) entradas.push({ rol: "usuario", texto: m.contenido });
    }
    else if (m.rol === "asesor") entradas.push({ rol: "asesor", texto: m.contenido });
    else if (m.rol === "asistente") {
      entradas.push({
        ...turnoVacio(m.turno_id),
        artifacts: m.artifacts as unknown as Artifact[],
        texto: m.contenido,
        confianza: m.confianza ?? null,
        completo: true,
      });
    }
  }
  const huboAsesor = h.mensajes.some((m) => m.rol === "asesor");
  const aviso = entradas
    .flatMap((x) => (x.rol === "agente" ? x.artifacts : []))
    .findLast((a) => a.tipo === "aviso_escalamiento");
  const escalamiento: Escalamiento | null =
    h.estado === "escalada" && aviso?.tipo === "aviso_escalamiento"
      ? {
          id: aviso.escalamiento_id,
          criterio: aviso.criterio,
          prioridad: aviso.prioridad,
          mensaje: aviso.mensaje,
          esperaS: aviso.espera_estimada_s,
          fase: huboAsesor ? "conectado" : "transfiriendo",
        }
      : e.escalamiento;
  return { ...e, sesionId: h.id, entradas, enCurso: false, escalamiento };
}

export function chatReducer(e: EstadoChat, a: Accion): EstadoChat {
  switch (a.tipo) {
    case "sesion":
      return { ...e, sesionId: a.id };
    case "enviar":
      return {
        ...e,
        enCurso: true,
        fallo: null,
        entradas: a.texto === null ? e.entradas : [...e.entradas, { rol: "usuario", texto: a.texto }],
      };
    case "evento":
      return aplicarEvento(e, a.evento);
    case "asesor":
      if (a.evento.evento === "mensaje_asesor") {
        return {
          ...e,
          entradas: [...e.entradas, { rol: "asesor", texto: a.evento.data.texto, autor: a.evento.data.asesor }],
          escalamiento: e.escalamiento && { ...e.escalamiento, fase: "conectado" },
        };
      }
      return { ...e, escalamiento: e.escalamiento && { ...e.escalamiento, fase: "resuelto" } };
    case "fallo":
      return { ...e, enCurso: false, fallo: { titulo: a.titulo, detalle: a.detalle, reintentable: a.reintentable } };
    case "historial":
      return desdeHistorial(e, a.historial);
    case "reiniciar":
      return estadoInicial;
  }
}
