import type { components } from "./api";

export type Problema = components["schemas"]["Problema"];
export type Token = components["schemas"]["TokensOut"];

/** Error con formato RFC 9457 (`application/problem+json`). */
export class ErrorApi extends Error {
  constructor(
    readonly problema: Problema,
    readonly reintentarEnS?: number,
  ) {
    super(problema.detail ?? problema.title);
  }
  get status() {
    return this.problema.status;
  }
}

/** Sin respuesta del servidor: red caída, CORS o backend apagado. */
export class ErrorRed extends Error {}

// Access token en memoria. El refresh rota en cada uso: se guarda siempre el último (docs/frontend.md §2).
const CLAVE_REFRESH = "translogix.refresh";
let accessToken: string | null = null;
let refrescando: Promise<boolean> | null = null;

export function guardarTokens(t: Pick<Token, "access_token" | "refresh_token"> | null) {
  accessToken = t?.access_token ?? null;
  try {
    if (t) sessionStorage.setItem(CLAVE_REFRESH, t.refresh_token);
    else sessionStorage.removeItem(CLAVE_REFRESH);
  } catch {
    // Sin almacenamiento la sesión dura lo que dure la pestaña.
  }
}

export function leerRefresh(): string | null {
  try {
    return sessionStorage.getItem(CLAVE_REFRESH);
  } catch {
    return null;
  }
}

/** Una sola renovación a la vez: dos usos del mismo refresh invalidarían la sesión. */
export function refrescar(): Promise<boolean> {
  refrescando ??= (async () => {
    const refresh_token = leerRefresh();
    if (!refresh_token) return false;
    try {
      const r = await fetch("/api/v1/auth/refresh", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token }),
      });
      if (!r.ok) {
        guardarTokens(null);
        return false;
      }
      guardarTokens((await r.json()) as Token);
      return true;
    } catch {
      return false;
    }
  })().finally(() => {
    refrescando = null;
  });
  return refrescando;
}

async function problemaDe(r: Response): Promise<ErrorApi> {
  const espera = Number(r.headers.get("Retry-After")) || undefined;
  try {
    return new ErrorApi((await r.json()) as Problema, espera);
  } catch {
    return new ErrorApi({ type: "about:blank", title: "Error del servidor", status: r.status } as Problema, espera);
  }
}

/** Petición autenticada: ante un 401 renueva una vez y reintenta. Devuelve la respuesta cruda si es correcta. */
export async function peticion(ruta: string, init: RequestInit = {}): Promise<Response> {
  const enviar = () => {
    const headers = new Headers(init.headers);
    if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);
    return fetch(ruta, { ...init, headers });
  };
  let r: Response;
  try {
    r = await enviar();
    if (r.status === 401 && leerRefresh() && (await refrescar())) r = await enviar();
  } catch (e) {
    if (e instanceof DOMException && e.name === "AbortError") throw e;
    throw new ErrorRed("No hay conexión con el servidor.");
  }
  if (!r.ok) throw await problemaDe(r);
  return r;
}

export async function json<T>(ruta: string, cuerpo?: unknown, init: RequestInit = {}): Promise<T> {
  const r = await peticion(ruta, {
    method: cuerpo === undefined ? "GET" : "POST",
    ...init,
    headers: { ...(cuerpo === undefined ? {} : { "Content-Type": "application/json" }), ...init.headers },
    body: cuerpo === undefined ? undefined : JSON.stringify(cuerpo),
  });
  return r.status === 204 ? (undefined as T) : ((await r.json()) as T);
}
