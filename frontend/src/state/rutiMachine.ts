import type { EstadoChat, FaseEscalamiento } from "./chatStore";

/** Los valores coinciden con `data-state` del SVG; `reposo` no activa ningún indicador. */
export type EstadoRuti = "reposo" | "escuchando" | "pensando" | "resuelto" | "escalamiento" | "error";

export interface VistaRuti {
  estado: EstadoRuti;
  fase: FaseEscalamiento | null;
  mensaje: string;
}

const FORMULARIOS = new Set(["formulario_cotizacion", "formulario_guia", "formulario_pqrs", "checklist_documentos"]);

export interface SenalesRuti {
  chat: Pick<EstadoChat, "entradas" | "enCurso" | "fallo" | "escalamiento">;
  escribiendo: boolean;
  /** `resuelto` dura poco: al vencer, RUTI vuelve a reposo. */
  resueltoVigente: boolean;
}

/** Función pura: el estado de RUTI se deriva de datos reales, nunca de un temporizador que simule progreso. */
export function derivarRuti({ chat, escribiendo, resueltoVigente }: SenalesRuti): VistaRuti {
  const { escalamiento } = chat;
  if (escalamiento && escalamiento.fase !== "resuelto") {
    return {
      estado: "escalamiento",
      fase: escalamiento.fase,
      mensaje:
        escalamiento.fase === "conectado"
          ? "Un asesor ya está contigo."
          : "Estoy solicitando la ayuda de un asesor.",
    };
  }
  if (chat.fallo) return { estado: "error", fase: null, mensaje: chat.fallo.titulo };
  if (chat.enCurso) return { estado: "pensando", fase: null, mensaje: "Estoy consultando la información…" };
  if (resueltoVigente && turnoResuelto(chat)) {
    return { estado: "resuelto", fase: null, mensaje: "¡Listo! Aquí tienes el resultado." };
  }
  if (escribiendo) return { estado: "escuchando", fase: null, mensaje: "Te leo." };
  return { estado: "reposo", fase: null, mensaje: "¿En qué te ayudo?" };
}

/** Un turno que pide datos (formulario) todavía no resuelve nada. */
export function turnoResuelto(chat: Pick<EstadoChat, "entradas">): boolean {
  const ultimo = chat.entradas.at(-1);
  if (ultimo?.rol !== "agente" || !ultimo.completo) return false;
  return !ultimo.artifacts.some((a) => FORMULARIOS.has(a.tipo));
}
