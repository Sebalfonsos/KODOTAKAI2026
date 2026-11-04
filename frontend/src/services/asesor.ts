import type { components } from "./api";
import { escucharEventos } from "./chat";
import { json } from "./http";
import type { Pagina, SesionDetalle } from "./admin";

type S = components["schemas"];
export type Escalamiento = S["EscalamientoOut"];
export type EstadoEscalamiento = Escalamiento["estado"];
export type MensajeSesion = SesionDetalle["mensajes"][number];

const R = "/api/v1/asesor";

export const verCola = (estado: EstadoEscalamiento) => json<Pagina<Escalamiento>>(`${R}/escalamientos?estado=${estado}&tamano=100`);
export const tomar = (id: string) => json<S["EscalamientoDetalleOut"]>(`${R}/escalamientos/${id}/tomar`, {});
export const verSesion = (id: string) => json<SesionDetalle>(`${R}/sesiones/${id}`);
export const responder = (id: string, texto: string) => json<MensajeSesion>(`${R}/sesiones/${id}/mensajes`, { texto });
export const resolver = (id: string, nota: string) => json<S["EscalamientoDetalleOut"]>(`${R}/escalamientos/${id}/resolver`, nota ? { nota } : {});

/** Cualquier evento significa "cambió la conversación": el historial del servidor es la única fuente de verdad. */
export const escucharSesion = (id: string, alCambio: () => void) => escucharEventos(`${R}/sesiones/${id}/eventos`, alCambio, alCambio);
