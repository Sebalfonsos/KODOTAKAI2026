import type { components } from "./api";
import { json, peticion } from "./http";
import { leerStream, type EventoSSE } from "./sse";
import type { EventoChat } from "./chat";

type S = components["schemas"];
export type Metricas = S["MetricasOut"];
export type Modelo = S["ModeloOut"];
export type Modelos = S["ModelosOut"];
export type Entrenamientos = S["EntrenamientosOut"];
export type EstadoMl = S["EstadoAutoentrenamientoOut"];
export type ResultadoEntrenamiento = S["ResultadoEntrenamiento"];
export type Riesgo = S["RiesgoOut"];
export type Pronostico = S["PronosticoOut"];
export type AvanceSimulacion = S["AvanceSimulacionOut"];
export type UsuarioAdmin = S["UsuarioAdminOut"];
export type UsuarioNuevo = S["UsuarioCrearIn"];
export type UsuarioCambio = S["UsuarioPatchIn"];
export type Rol = UsuarioAdmin["rol"];
export type Conversacion = S["ConversacionOut"];
export type SesionDetalle = S["SesionDetalleOut"];
export type Envio = S["EnvioAdminOut"];
export type Pqrs = S["PqrsAdminOut"];
export type DocumentoRag = S["DocumentoRagOut"];
export type ResultadoRag = S["ResultadoRagOut"];
export type Auditoria = S["AuditoriaOut"];
export type Ciudad = S["OpcionCiudad"];

export interface Pagina<T> {
  items: T[];
  total: number;
  pagina: number;
  tamano: number;
}

const A = "/api/v1/admin";

/** Omite los filtros vacíos: el servidor valida los enums y un `estado=` sin valor sería un 422. */
function consulta(params: Record<string, string | number | undefined>) {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== "") q.set(k, String(v));
  const texto = q.toString();
  return texto ? `?${texto}` : "";
}

export const verMetricas = (desde: string, hasta: string) => json<Metricas>(`${A}/metricas${consulta({ desde, hasta })}`);

export const verModelos = () => json<Modelos>(`${A}/ml/modelos`);
export const verEstadoMl = () => json<EstadoMl>(`${A}/ml/estado`);
export const verEntrenamientos = (pagina: number) => json<Entrenamientos>(`${A}/ml/entrenamientos${consulta({ pagina, tamano: 10 })}`);
export const entrenar = () => json<ResultadoEntrenamiento>(`${A}/ml/entrenar`, {});
export const verRiesgo = (guia: string) => json<Riesgo>(`${A}/ml/riesgo-retraso${consulta({ guia })}`);
export const verPronostico = (origen: string, dias: number) => json<Pronostico>(`${A}/ml/pronostico-demanda${consulta({ origen, dias })}`);
export const avanzarSimulador = (dias: number) => json<AvanceSimulacion>(`${A}/simulador/avanzar${consulta({ dias })}`, {});
export const verOrigenes = () => json<Ciudad[]>("/api/v1/trayectos/origenes");

export const verUsuarios = (rol: string, pagina: number) => json<Pagina<UsuarioAdmin>>(`${A}/usuarios${consulta({ rol, pagina })}`);
export const crearUsuario = (u: UsuarioNuevo) => json<UsuarioAdmin>(`${A}/usuarios`, u);
export const editarUsuario = (id: string, c: UsuarioCambio) => json<UsuarioAdmin>(`${A}/usuarios/${id}`, c, { method: "PATCH" });

export const verConversaciones = (estado: string, pagina: number) => json<Pagina<Conversacion>>(`${A}/conversaciones${consulta({ estado, pagina })}`);
export const verConversacion = (id: string) => json<SesionDetalle>(`${A}/conversaciones/${id}`);

export const verEnvios = (estado: string, origen_dato: string, pagina: number) =>
  json<Pagina<Envio>>(`${A}/envios${consulta({ estado, origen_dato, pagina })}`);

export const verPqrs = (estado: string, tipo: string, pagina: number) => json<Pagina<Pqrs>>(`${A}/pqrs${consulta({ estado, tipo, pagina })}`);
export const editarPqrs = (radicado: string, c: S["PqrsPatchIn"]) => json<Pqrs>(`${A}/pqrs/${radicado}`, c, { method: "PATCH" });

export const verDocumentos = () => json<DocumentoRag[]>(`${A}/rag/documentos`);
export const desactivarDocumento = (id: number) => peticion(`${A}/rag/documentos/${id}`, { method: "DELETE" });
export const buscarRag = (q: string) => json<ResultadoRag[]>(`${A}/rag/buscar${consulta({ q })}`);
export async function subirDocumento(datos: FormData) {
  const r = await peticion(`${A}/rag/documentos`, { method: "POST", body: datos });
  return (await r.json()) as S["IngestaOut"];
}

export const verAuditoria = (entidad: string, pagina: number) => json<Pagina<Auditoria>>(`${A}/auditoria${consulta({ entidad, pagina })}`);

/** Mismo protocolo SSE del chat de clientes (docs/frontend.md §4); la sesión se crea en el primer mensaje. */
export async function preguntarAdmin(texto: string, sesion_id: string | null, alEvento: (e: EventoChat) => void) {
  const r = await peticion(`${A}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify({ texto, ...(sesion_id ? { sesion_id } : {}) }),
  });
  if (r.body) await leerStream(r.body, (e: EventoSSE) => alEvento(e as EventoChat));
}
