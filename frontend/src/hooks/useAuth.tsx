import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { login as apiLogin, logout as apiLogout, restaurarSesion, type Usuario } from "../services/auth";

/** Inyectada por `vite.config.ts`; `null` fuera de `npm run dev`. */
declare const __CUENTA_DEMO__: { email: string; password: string } | null;

const CLAVE_SIN_DEMO = "translogix.sinDemo";
let entrandoDemo: Promise<Usuario | null> | null = null;

/** En desarrollo entra con la cuenta demo: el cupo de sesiones es por usuario y no se gasta el de invitado. */
function entrarDemo(): Promise<Usuario | null> {
  if (!__CUENTA_DEMO__ || sessionStorage.getItem(CLAVE_SIN_DEMO)) return Promise.resolve(null);
  const { email, password } = __CUENTA_DEMO__;
  entrandoDemo ??= apiLogin(email, password)
    .catch((e: unknown) => {
      console.warn("No se pudo entrar con la cuenta demo; se sigue como invitado.", e);
      return null;
    })
    .finally(() => {
      entrandoDemo = null;
    });
  return entrandoDemo;
}

interface Auth {
  usuario: Usuario | null;
  cargando: boolean;
  login: (email: string, password: string) => Promise<Usuario>;
  logout: () => Promise<void>;
}

const Contexto = createContext<Auth | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [usuario, setUsuario] = useState<Usuario | null>(null);
  const [cargando, setCargando] = useState(true);

  useEffect(() => {
    restaurarSesion()
      .then((u) => u ?? entrarDemo())
      .then(setUsuario)
      .catch(() => setUsuario(null))
      .finally(() => setCargando(false));
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const u = await apiLogin(email, password);
    setUsuario(u);
    return u;
  }, []);

  const logout = useCallback(async () => {
    await apiLogout();
    // "Salir" deja la pestaña como invitado: así también se prueban los flujos sin sesión.
    if (__CUENTA_DEMO__) sessionStorage.setItem(CLAVE_SIN_DEMO, "1");
    setUsuario(null);
  }, []);

  const valor = useMemo(() => ({ usuario, cargando, login, logout }), [usuario, cargando, login, logout]);
  // Con cuenta demo se espera al login: si no, el chat abriría su primera sesión como invitado.
  if (cargando && __CUENTA_DEMO__) return null;
  return <Contexto.Provider value={valor}>{children}</Contexto.Provider>;
}

export function useAuth(): Auth {
  const c = useContext(Contexto);
  if (!c) throw new Error("useAuth requiere AuthProvider");
  return c;
}
