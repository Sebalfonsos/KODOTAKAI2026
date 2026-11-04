import type { components } from "./api";
import { json, peticion } from "./http";
import { leerStream, type EventoSSE } from "./sse";

type S = components["schemas"];
export type Artifact = S["ChatTurnResponse"]["artifacts"][number];
export type TipoArtifact = Artifact["tipo"];
export type Accion = S["Accion"];
export type Cita = S["Cita"];
export type MensajeEntrada = S["MensajeTexto"] | S["MensajeArtifactSubmit"];
export type Historial = S["HistorialOut"];

/** Sin este límite, un proxy que no propaga un corte dejaría a RUTI "pensando" para siempre. */
const SILENCIO_MAX_MS = Number(import.meta.env.VITE_SSE_SILENCIO_MS) || 60_000;

export interface Latencias {
  total: number;
  router?: number | null;
  tool?: number | null;
  retrieval?: number | null;
  llm_first_token?: number | null;
  llm_total?: number | null;
  verify?: number | null;
}

/** OpenAPI no tipa un stream: estos eventos siguen `app/schemas/chat.py` y docs/frontend.md §4.2. */
export type EventoChat =
  | { evento: "meta"; data: { turno_id: string; sesion_id: string; intencion: string; confianza_enrutador?: number | null } }
  | { evento: "artifact"; data: { artifact: Artifact } }
  | { evento: "delta"; data: { texto: string } }
  | { evento: "reemplazo"; data: { texto: string; motivo: string } }
  | { evento: "citas"; data: { citas: Cita[] } }
  | { evento: "escalamiento"; data: S["EventoEscalamiento"] }
  | { evento: "fin"; data: { turno_id: string; confianza: number; latencias_ms: Latencias } }
  | { evento: "error"; data: S["Problema"] };

export const crearSesion = () => json<S["SesionOut"]>("/api/v1/chat/sesiones", {});
export const verHistorial = (id: string) => json<Historial>(`/api/v1/chat/sesiones/${id}`);

export async function enviarMensaje(
  ruta: string,
  cuerpo: MensajeEntrada,
  alEvento: (e: EventoChat) => void,
  signal?: AbortSignal,
) {
  const r = await peticion(ruta, {
    method: "POST",
    signal,
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify(cuerpo),
  });
  if (!r.body) throw new Error("Respuesta sin cuerpo");
  await leerStream(r.body, (e: EventoSSE) => alEvento(e as EventoChat), SILENCIO_MAX_MS);
}

export type EventoAsesor =
  | { evento: "mensaje_asesor"; data: { texto: string; asesor: string | null; creado_en: string } }
  | { evento: "escalamiento_resuelto"; data: { escalamiento_id: string; nota: string | null } };

/**
 * Eventos del asesor. Reconecta con espera exponencial (1 s … 30 s) y avisa para reconciliar con el historial,
 * porque lo publicado durante un corte no se reenvía (docs/frontend.md §4.4).
 */
export function escucharEventos(ruta: string, alEvento: (e: EventoSSE) => void, alReconectar: () => void): () => void {
  const control = new AbortController();
  void (async () => {
    let espera = 1000;
    let primeraVez = true;
    while (!control.signal.aborted) {
      try {
        const r = await peticion(ruta, {
          signal: control.signal,
          headers: { Accept: "text/event-stream" },
        });
        if (!primeraVez) alReconectar();
        primeraVez = false;
        espera = 1000;
        if (r.body) await leerStream(r.body, alEvento);
      } catch {
        if (control.signal.aborted) return;
        primeraVez = false;
      }
      await new Promise((ok) => setTimeout(ok, espera));
      espera = Math.min(espera * 2, 30_000);
    }
  })();
  return () => control.abort();
}

export const escucharAsesor = (sesionId: string, alEvento: (e: EventoAsesor) => void, alReconectar: () => void) =>
  escucharEventos(`/api/v1/chat/sesiones/${sesionId}/eventos`, (e) => alEvento(e as EventoAsesor), alReconectar);

export const calificar = (sesionId: string, puntaje: number, comentario?: string) =>
  json<void>(`/api/v1/chat/sesiones/${sesionId}/calificacion`, { puntaje, comentario });
