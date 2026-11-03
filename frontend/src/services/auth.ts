import type { components } from "./api";
import { guardarTokens, json, leerRefresh, refrescar, type Token } from "./http";

export type Usuario = components["schemas"]["UsuarioOut"];

export async function login(email: string, password: string): Promise<Usuario> {
  guardarTokens(await json<Token>("/api/v1/auth/login", { email, password }));
  return yo();
}

export const yo = () => json<Usuario>("/api/v1/auth/me");

export async function logout() {
  const refresh_token = leerRefresh();
  try {
    if (refresh_token) await json<void>("/api/v1/auth/logout", { refresh_token });
  } finally {
    guardarTokens(null);
  }
}

/** Recupera la sesión al recargar: el access token vive en memoria y se pierde. */
export async function restaurarSesion(): Promise<Usuario | null> {
  if (!leerRefresh() || !(await refrescar())) return null;
  return yo();
}
